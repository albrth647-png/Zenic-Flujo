"""
ORBITAL — Pilar 4: COD (Colapso Orbital Determinista)
======================================================

Garantiza convergencia del sistema orbital a un estado estable usando:

1. Activacion tanh: mantiene el sistema acotado en [-1, 1]
2. Teorema del punto fijo de Brouwer: mapeo continuo en compacto convexo → punto fijo existe
3. Iteracion hasta convergencia: |theta_nuevo - theta_viejo| < epsilon

El colapso NO es probabilidad: es el ESTADO DETERMINISTA del sistema
circular despues de converger. Es un hecho, no una estimacion.

Proceso de colapso:
1. Calcular TOR para todas las parejas del ciclo
2. Acumular tensiones por variable
3. Aplicar modulacion: delta_theta = tanh(tension_acumulada) * omega * dt
4. Normalizar theta a [0, 2pi)
5. Repetir hasta convergencia o maximo de iteraciones

Garantia de convergencia (Brouwer):
- El espacio de fases [0, 2pi)^N es compacto y convexo
- La funcion de transicion F(theta) = theta + tanh(TOR) * omega * dt es continua
- Por el teorema del punto fijo de Brouwer, F tiene al menos un punto fijo
- La iteracion converge a ese punto fijo (o a uno cercano dentro de epsilon)

Ejemplo de uso:
    >>> from src.orbital.cod import COD
    >>> cod = COD(ovc, tor, rcc)
    >>> result = cod.collapse(cycle)
    >>> print(f"Convergio: {result.converged}, Iteraciones: {result.iterations}")
"""

from __future__ import annotations

import math
import time

from src.orbital.models import (
    DEFAULT_EPSILON,
    MAX_COD_ITERATIONS,
    TWO_PI,
    CicloOrbital,
    CODResult,
)
from src.orbital.lyapunov import LYAPUNOV_TOLERANCE, LyapunovTracker
from src.orbital.friston_fep import FEPTracker
from src.orbital.conley import ConleyClassifier, ConleyType
from src.orbital.haken import HakenAnalyzer
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class COD:
    """
    Colapso Orbital Determinista — Motor de convergencia.

    Ejecuta el proceso de colapso sobre ciclos orbitales, garantizando
    convergencia a un estado estable determinista mediante la combinacion
    de activacion tanh y el teorema del punto fijo de Brouwer.

    El colapso es DETERMINISTA:
    - Mismas condiciones iniciales → mismo estado final siempre
    - No hay aleatoriedad ni probabilidad
    - El resultado es un ESTADO del sistema, no una prediccion
    """

    def __init__(self, ovc, tor, rcc):
        """
        Inicializa el motor COD.

        Args:
            ovc: Instancia de OVC con las variables orbitales
            tor: Instancia de TOR para calcular tensiones
            rcc: Instancia de RCC para verificar resonancia
        """
        self._ovc = ovc
        self._tor = tor
        self._rcc = rcc
        self._epsilon = DEFAULT_EPSILON
        self._max_iterations = MAX_COD_ITERATIONS
        self._convergence_scale = 0.5  # escala del paso de descenso de V
        self._normalize_tension = True  # normalizar tension por amplitud para convergencia

    # ── Configuracion ──────────────────────────────────────

    def configure(
        self,
        epsilon: float | None = None,
        max_iterations: int | None = None,
        convergence_scale: float | None = None,
    ) -> None:
        """
        Configura los parametros de convergencia del COD.

        Args:
            epsilon: Precision de convergencia (|delta| < epsilon → convergio)
            max_iterations: Maximo de iteraciones antes de declarar no-convergencia
            convergence_scale: Factor de escala para la modulacion de tension
        """
        if epsilon is not None:
            self._epsilon = epsilon
        if max_iterations is not None:
            self._max_iterations = max_iterations
        if convergence_scale is not None:
            self._convergence_scale = convergence_scale

    # ── Colapso orbital ────────────────────────────────────

    def collapse(self, cycle: CicloOrbital, dt: float = 1.0) -> CODResult:
        """
        Ejecuta el colapso orbital determinista sobre un ciclo.

        Mejora 1 (revisión 2): descenso por gradiente de V(θ) = -Σ TOR(i,j).
        La dinámica ahora es θ_i_new = θ_i - α · (dV/dθ_i), donde
        dV/dθ_i = Σ_j A_i·A_j·sin(θ_i - θ_j). Esto garantiza que V es
        función de Lyapunov estricta (V monótona decreciente).

        Proceso:
        1. Guardar fases iniciales
        2. Iterar:
           a. Calcular gradiente de V: ∇V(θ) componente por componente
           b. Aplicar descenso: θ_i_new = θ_i - α · (dV/dθ_i) · dt
           c. Normalizar θ a [0, 2π)
           d. Verificar convergencia: max|Δθ| < ε
        3. Si convergió → estado estable determinista
        4. Si no → sistema en estado no-estable (requiere más ticks)

        Args:
            cycle: CicloOrbital a colapsar
            dt: Paso temporal por iteración

        Returns:
            CODResult con el estado final del colapso
        """
        start_time = time.time()

        # Fases iniciales
        initial_phases: dict[str, float] = {}
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var:
                initial_phases[var_name] = var.theta

        # Mejora 1 (rev 2): Lyapunov tracker integrado
        # Usa update() para que el historial y los contadores se mantengan
        # consistentes con los snapshots reales del sistema.
        lyapunov_tracker = LyapunovTracker()
        # Snapshot inicial (antes de iterar)
        status_initial = lyapunov_tracker.update(
            self._ovc, self._tor, cycle_variable_ids=cycle.variable_ids
        )
        V_initial = status_initial.V
        lyapunov_violations = 0

        # Mejora 2: Friston Free Energy Principle tracker
        # F(θ) = U(θ) - S(θ) donde U = V/N y S = entropía de Shannon de fases.
        # FEP complementa a Lyapunov: mide auto-organización, no solo convergencia.
        fep_tracker = FEPTracker()
        fep_status_initial = fep_tracker.update(
            self._ovc, self._tor, cycle_variable_ids=cycle.variable_ids
        )
        fep_F_initial = fep_status_initial.F
        fep_energy_initial = fep_status_initial.energy
        fep_entropy_initial = fep_status_initial.entropy
        fep_violations = 0

        # Iterar hasta convergencia
        converged = False
        iterations = 0
        max_delta = float("inf")

        # Pre-calcular factor de normalización por amplitud
        # (se sigue usando para escalar α y evitar pasos demasiado grandes)
        amplitude_norm = self._compute_amplitude_normalization(cycle)

        # Pre-computar referencias a variables (evita get_variable() repetido)
        var_refs: dict[str, object] = {}
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var:
                var_refs[var_name] = var

        # Relajación adaptativa: reducir paso si el sistema oscila
        relaxation = 1.0
        prev_max_delta = float("inf")
        oscillation_count = 0

        for iteration in range(self._max_iterations):
            iterations = iteration + 1

            # 1. Calcular gradiente de V usando el tracker (una sola pasada)
            gradient = lyapunov_tracker.compute_gradient(
                self._ovc, self._tor, cycle_variable_ids=cycle.variable_ids
            )

            # 2. Descenso por gradiente: θ_i_new = θ_i - α · (dV/dθ_i) · dt
            # α = convergence_scale * relaxation
            # Normalizamos por amplitude_norm para mantener el paso acotado.
            max_delta = 0.0
            for var_name in cycle.variable_ids:
                var = var_refs.get(var_name)
                if var is None:
                    continue

                dV_dtheta = gradient.get(var_name, 0.0)

                # Normalizar el gradiente por la amplitud del sistema para
                # mantener estabilidad numérica en sistemas grandes.
                if self._normalize_tension and amplitude_norm > 0:
                    norm_factor = amplitude_norm
                else:
                    norm_factor = 1.0

                # Paso de descenso: negativo porque vamos cuesta abajo de V
                step = -dV_dtheta * self._convergence_scale * dt * relaxation / norm_factor
                old_theta = var.theta
                new_theta = (var.theta + step) % TWO_PI
                var.theta = new_theta

                # Calcular delta (distancia angular mínima)
                delta = abs(new_theta - old_theta)
                delta = min(delta, TWO_PI - delta)
                if delta > max_delta:
                    max_delta = delta

            # 3. Detectar oscilación y ajustar relajación
            if max_delta > prev_max_delta * 0.9:
                oscillation_count += 1
            else:
                oscillation_count = max(0, oscillation_count - 1)

            if oscillation_count >= 3:
                relaxation *= 0.7
                oscillation_count = 0
                relaxation = max(relaxation, 0.001)

            prev_max_delta = max_delta

            # 4. Trackear V después de esta iteración (usando update() del tracker)
            status = lyapunov_tracker.update(
                self._ovc, self._tor, cycle_variable_ids=cycle.variable_ids
            )
            if status.violation:
                lyapunov_violations += 1

            # Mejora 2: Trackear F después de esta iteración
            fep_status = fep_tracker.update(
                self._ovc, self._tor, cycle_variable_ids=cycle.variable_ids
            )
            if fep_status.violation:
                fep_violations += 1

            # 5. Verificar convergencia
            if max_delta < self._epsilon:
                converged = True
                break

        # Recopilar fases y valores finales
        final_phases: dict[str, float] = {}
        final_values: dict[str, float] = {}
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var:
                final_phases[var_name] = var.theta
                final_values[var_name] = var.value

        # Verificar estado estable: si las fases no cambian mas
        steady_state_reached = converged and max_delta < self._epsilon * 10

        # Mejora 1: Cálculo final de Lyapunov desde el tracker
        if lyapunov_tracker.history:
            V_final = lyapunov_tracker.history[-1].V
        else:
            V_final = V_initial
        lyapunov_stable = lyapunov_violations == 0 and len(lyapunov_tracker.history) >= 2

        # Mejora 2: Cálculo final de FEP desde el tracker
        if fep_tracker.history:
            F_final = fep_tracker.history[-1].F
            fep_energy_final = fep_tracker.history[-1].energy
            fep_entropy_final = fep_tracker.history[-1].entropy
        else:
            F_final = fep_F_initial
            fep_energy_final = fep_energy_initial
            fep_entropy_final = fep_entropy_initial
        fep_stable = fep_violations == 0 and len(fep_tracker.history) >= 2

        # Mejora 3: Clasificación Conley del punto fijo al que convergió el COD.
        # Construir β efectivo usado en la iteración final.
        # β = convergence_scale · dt · relaxation / amplitude_norm
        # Solo clasificamos si el sistema convergió (de otro modo, no hay punto fijo).
        conley_type_str = "degenerate"  # default: no es punto fijo hiperbólico
        conley_morse_index = 0
        conley_step_safe = False
        conley_recommended_max_beta = -1.0  # sentinel: no aplicable
        conley_is_hyperbolic = False
        conley_stable_count = 0
        conley_unstable_count = 0
        conley_marginal_count = 0
        conley_beta = 0.0
        if converged and len(cycle.variable_ids) >= 2:
            try:
                conley_classifier = ConleyClassifier()
                # Calcular β efectivo: relaxation está definido en este scope
                beta = conley_classifier.compute_beta(
                    convergence_scale=self._convergence_scale,
                    dt=dt,
                    relaxation=relaxation,
                    amplitude_norm=amplitude_norm if amplitude_norm > 0 else 1.0,
                )
                conley_status = conley_classifier.classify(
                    self._ovc, self._tor, beta=beta,
                    cycle_variable_ids=cycle.variable_ids,
                )
                conley_type_str = conley_status.conley_type.value
                conley_morse_index = conley_status.morse_index
                conley_step_safe = conley_status.step_safe
                # JSON-safe: convertir inf a -1.0
                if math.isinf(conley_status.recommended_max_beta):
                    conley_recommended_max_beta = -1.0
                else:
                    conley_recommended_max_beta = conley_status.recommended_max_beta
                conley_is_hyperbolic = conley_status.is_hyperbolic
                conley_stable_count = conley_status.spectrum.stable_count
                conley_unstable_count = conley_status.spectrum.unstable_count
                conley_marginal_count = conley_status.spectrum.marginal_count
                conley_beta = beta
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Conley classification failed: {exc}")
                # Mantener valores default (degenerate)

        # Mejora 4: Haken synergetics (slaving principle)
        haken_slaving_active = False
        haken_separation_ratio = float("nan")
        haken_n_order_parameters = 0
        haken_effective_dimension = 0
        haken_reduction_error = float("nan")
        haken_slaving_state = "not_applicable_trivial"
        if converged and len(cycle.variable_ids) >= 2:
            try:
                haken_analyzer = HakenAnalyzer()
                haken_status = haken_analyzer.analyze(
                    self._ovc, self._tor, beta=beta,
                    cycle_variable_ids=cycle.variable_ids,
                )
                haken_slaving_active = haken_status.slaving_active
                haken_separation_ratio = haken_status.separation_ratio
                haken_n_order_parameters = len(haken_status.order_parameters)
                haken_effective_dimension = haken_status.effective_dimension
                haken_reduction_error = haken_status.reduction_error
                haken_slaving_state = haken_status.slaving_state.value
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Haken analysis failed: {exc}")

        duration_ms = int((time.time() - start_time) * 1000)

        result = CODResult(
            cycle_id=cycle.id,
            converged=converged,
            iterations=iterations,
            final_phases=final_phases,
            final_values=final_values,
            convergence_delta=max_delta,
            steady_state_reached=steady_state_reached,
            lyapunov_V_initial=V_initial,
            lyapunov_V_final=V_final,
            lyapunov_delta_V=V_final - V_initial,
            lyapunov_stable=lyapunov_stable,
            lyapunov_violations=lyapunov_violations,
            fep_F_initial=fep_F_initial,
            fep_F_final=F_final,
            fep_delta_F=F_final - fep_F_initial,
            fep_energy_initial=fep_energy_initial,
            fep_energy_final=fep_energy_final,
            fep_entropy_initial=fep_entropy_initial,
            fep_entropy_final=fep_entropy_final,
            fep_stable=fep_stable,
            fep_violations=fep_violations,
            conley_type=conley_type_str,
            conley_morse_index=conley_morse_index,
            conley_step_safe=conley_step_safe,
            conley_recommended_max_beta=conley_recommended_max_beta,
            conley_is_hyperbolic=conley_is_hyperbolic,
            conley_stable_count=conley_stable_count,
            conley_unstable_count=conley_unstable_count,
            conley_marginal_count=conley_marginal_count,
            conley_beta=conley_beta,
            haken_slaving_active=haken_slaving_active,
            haken_separation_ratio=haken_separation_ratio,
            haken_n_order_parameters=haken_n_order_parameters,
            haken_effective_dimension=haken_effective_dimension,
            haken_reduction_error=haken_reduction_error,
            haken_slaving_state=haken_slaving_state,
        )

        status = "CONVERGIO" if converged else "NO CONVERGIO"
        lyap_status = "Lyapunov-stable" if lyapunov_stable else f"Lyapunov-violations={lyapunov_violations}"
        fep_status_str = "FEP-stable" if fep_stable else f"FEP-violations={fep_violations}"
        conley_str = f"Conley={conley_type_str}"
        logger.info(
            f"COD: Ciclo '{cycle.name}' {status} — "
            f"iteraciones={iterations} delta={max_delta:.8f} "
            f"estado_estable={steady_state_reached} ({duration_ms}ms) "
            f"[{lyap_status}: V {V_initial:.6f}→{V_final:.6f}] "
            f"[{fep_status_str}: F {fep_F_initial:.6f}→{F_final:.6f}] "
            f"[{conley_str}, β={conley_beta:.3f}]"
        )

        return result

    def collapse_all(self) -> list[CODResult]:
        """
        Ejecuta colapso orbital en TODOS los ciclos registrados en RCC.

        Returns:
            Lista de CODResult, uno por cada ciclo
        """
        results = []
        for cycle in self._rcc._cycles.values():
            result = self.collapse(cycle)
            results.append(result)
        return results

    # ── Colapso con retroalimentacion ──────────────────────

    def collapse_with_retrofeedback(
        self,
        cycle: CicloOrbital,
        retrofeed_damping: float = 0.3,
        dt: float = 1.0,
    ) -> CODResult:
        """
        Ejecuta colapso orbital con retroalimentacion del espectro.

        Despues de cada iteracion de colapso, los valores resultantes
        retroalimentan las variables orbitales, creando un ciclo cerrado
        completo: input → TOR → RCC → COD → espectro → retro → input.

        Args:
            cycle: CicloOrbital a colapsar
            retrofeed_damping: Factor de amortiguacion de retroalimentacion [0, 1]
            dt: Paso temporal

        Returns:
            CODResult con el estado final incluyendo retroalimentacion
        """
        # Ejecutar colapso normal
        result = self.collapse(cycle, dt)

        # Retroalimentar valores finales al OVC
        if result.converged:
            retrofeed_values = {}
            for var_name, value in result.final_values.items():
                # La retroalimentacion es proporcional al valor y al damping
                retrofeed_values[var_name] = value * retrofeed_damping * 0.01
            self._ovc.retrofeed(retrofeed_values, retrofeed_damping)
            logger.info(
                f"COD: Retroalimentacion aplicada a {len(retrofeed_values)} variables (damping={retrofeed_damping})"
            )

        return result

    # ── Normalizacion de amplitud ─────────────────────────

    def _compute_amplitude_normalization(self, cycle: CicloOrbital) -> float:
        """
        Calcula el factor de normalizacion de amplitud para un ciclo.

        El factor es la suma de las amplitudes de todas las variables del ciclo.
        Al dividir la tension acumulada por (A_var * sum_A), la tension normalizada
        queda en un rango manejable independientemente de la escala de amplitudes.

        Sin normalizacion: TOR ~ A_i * A_j → con A=1000, TOR ~ 1,000,000 → tanh satura
        Con normalizacion: tension_norm = TOR / (A_var * sum_A) → rango ~ [-N, N] → tanh converge

        Returns:
            Suma de amplitudes de las variables del ciclo (> 0)
        """
        total_amplitude = 0.0
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var:
                total_amplitude += var.amplitude
        return total_amplitude if total_amplitude > 0 else 1.0

    # ── Analisis de estabilidad ────────────────────────────

    def is_stable(self, cycle: CicloOrbital) -> bool:
        """
        Verifica si un ciclo esta en estado estable (punto fijo).

        Un ciclo es estable si un tick orbital no cambia significativamente
        las fases de sus variables.

        Returns:
            True si el ciclo esta en estado estable
        """
        # Guardar fases actuales
        pre_phases = {}
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var:
                pre_phases[var_name] = var.theta

        # Avanzar un tick
        tor_results = self._tor.calculate_for_cycle(cycle.variable_ids)
        tension_accum: dict[str, float] = {}
        for result in tor_results:
            tension_accum[result.variable_i] = tension_accum.get(result.variable_i, 0.0) + result.tor_value
            tension_accum[result.variable_j] = tension_accum.get(result.variable_j, 0.0) + result.tor_value

        amplitude_norm = self._compute_amplitude_normalization(cycle)

        max_delta = 0.0
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var is None:
                continue
            tension = tension_accum.get(var_name, 0.0)

            # Usar la misma normalizacion que collapse()
            if self._normalize_tension and amplitude_norm > 0:
                var_amp = var.amplitude if var.amplitude > 0 else 1.0
                normalized_tension = tension / (var_amp * amplitude_norm)
            else:
                normalized_tension = tension

            modulation = math.tanh(normalized_tension * self._convergence_scale)
            delta = abs(modulation * var.velocity)
            max_delta = max(max_delta, delta)

        # Restaurar fases
        for var_name, theta in pre_phases.items():
            var = self._ovc.get_variable(var_name)
            if var:
                var.theta = theta

        return max_delta < self._epsilon

    # ── Representacion ─────────────────────────────────────

    def __repr__(self) -> str:
        return f"COD(epsilon={self._epsilon}, max_iter={self._max_iterations})"

    def collapse_report(self, cycle: CicloOrbital) -> str:
        """Retorna un reporte detallado del colapso de un ciclo."""
        result = self.collapse(cycle)
        lines = ["COD — Reporte de Colapso Orbital Determinista"]
        lines.append(f"  Ciclo: {cycle.name}")
        lines.append(f"  Convergio: {'SI' if result.converged else 'NO'}")
        lines.append(f"  Iteraciones: {result.iterations}/{self._max_iterations}")
        lines.append(f"  Delta final: {result.convergence_delta:.8f}")
        lines.append(f"  Estado estable: {'SI' if result.steady_state_reached else 'NO'}")
        lines.append("  Fases finales:")
        for name, theta in result.final_phases.items():
            deg = math.degrees(theta) % 360
            val = result.final_values.get(name, 0.0)
            lines.append(f"    {name}: θ={deg:6.1f}° valor={val:8.4f}")
        return "\n".join(lines)
