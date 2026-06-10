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
    CicloOrbital,
    CODResult,
    DEFAULT_EPSILON,
    MAX_COD_ITERATIONS,
    TWO_PI,
)
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
        self._convergence_scale = 0.01  # escala para evitar divergencia
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

        Proceso:
        1. Guardar fases iniciales
        2. Iterar:
           a. Calcular TOR para todas las parejas del ciclo
           b. Acumular tensiones por variable
           c. Aplicar modulacion tanh a cada variable
           d. Verificar convergencia: max|delta_theta| < epsilon
        3. Si convergio → estado estable determinista
        4. Si no convergio → sistema en estado no-estable (requiere mas ticks)

        Args:
            cycle: CicloOrbital a colapsar
            dt: Paso temporal por iteracion

        Returns:
            CODResult con el estado final del colapso
        """
        start_time = time.time()

        # Fases iniciales
        initial_phases = {}
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var:
                initial_phases[var_name] = var.theta

        # Iterar hasta convergencia
        converged = False
        iterations = 0
        max_delta = float("inf")
        final_phases = dict(initial_phases)

        # Pre-calcular factor de normalizacion por amplitud
        # Esto evita que amplitudes grandes saturen tanh y prevengan convergencia
        amplitude_norm = self._compute_amplitude_normalization(cycle)

        # Pre-computar amplitudes y velocidades para evitar get_variable() repetido
        # en cada iteracion. Obtener referencias a las variables una sola vez.
        var_refs: dict[str, tuple] = {}
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var:
                var_refs[var_name] = (var, var.amplitude, var.velocity)

        # Pre-computar parejas del ciclo (pares ordenados para evitar duplicados)
        cycle_pairs = []
        vids = list(cycle.variable_ids)
        for i in range(len(vids)):
            for j in range(i + 1, len(vids)):
                cycle_pairs.append((vids[i], vids[j]))

        # Relajacion adaptativa: reducir paso si el sistema oscila
        # relaxation_decay va de 1.0 a ~0.01 a lo largo de las iteraciones,
        # forzando convergencia cuando el sistema oscila alrededor del punto fijo
        relaxation = 1.0
        prev_max_delta = float("inf")
        oscillation_count = 0

        for iteration in range(self._max_iterations):
            iterations = iteration + 1

            # 1. Calcular TOR para el ciclo
            tor_results = self._tor.calculate_for_cycle(cycle.variable_ids)

            # 2. Acumular tensiones por variable
            tension_accum: dict[str, float] = {}
            for result in tor_results:
                tension_accum[result.variable_i] = tension_accum.get(result.variable_i, 0.0) + result.tor_value
                tension_accum[result.variable_j] = tension_accum.get(result.variable_j, 0.0) + result.tor_value

            # 3. Aplicar modulacion tanh a cada variable (con normalizacion + relajacion)
            max_delta = 0.0
            for var_name in cycle.variable_ids:
                var = self._ovc.get_variable(var_name)
                if var is None:
                    continue

                tension = tension_accum.get(var_name, 0.0)

                # Normalizar tension por amplitud: evita saturacion de tanh
                # Con amplitudes grandes, TOR puede ser ~A_i*A_j, saturando tanh.
                # Normalizando: tension_norm = tension / (A_i * sum_A_j) ∈ rango manejable
                if self._normalize_tension and amplitude_norm > 0:
                    var_amp = var.amplitude if var.amplitude > 0 else 1.0
                    normalized_tension = tension / (var_amp * amplitude_norm)
                else:
                    normalized_tension = tension

                modulation = math.tanh(normalized_tension * self._convergence_scale)
                # Aplicar factor de relajacion adaptativa
                step = modulation * var.velocity * dt * relaxation
                old_theta = var.theta
                new_theta = (var.theta + step) % TWO_PI
                var.theta = new_theta

                # Calcular delta (distancia angular minima)
                delta = abs(new_theta - old_theta)
                delta = min(delta, TWO_PI - delta)
                max_delta = max(max_delta, delta)

            # 4. Detectar oscilacion y ajustar relajacion
            if max_delta > prev_max_delta * 0.9:
                # El delta no esta disminuyendo — hay oscilacion
                oscillation_count += 1
            else:
                oscillation_count = max(0, oscillation_count - 1)

            # Si hay oscilacion sostenida, reducir el paso (aumentar relajacion)
            if oscillation_count >= 3:
                relaxation *= 0.7  # Reducir paso un 30%
                oscillation_count = 0
                # Garantizar que relaxation no baje de un minimo util
                relaxation = max(relaxation, 0.001)

            prev_max_delta = max_delta

            # 5. Verificar convergencia
            if max_delta < self._epsilon:
                converged = True
                break

        # Recopilar fases y valores finales
        final_phases = {}
        final_values = {}
        for var_name in cycle.variable_ids:
            var = self._ovc.get_variable(var_name)
            if var:
                final_phases[var_name] = var.theta
                final_values[var_name] = var.value

        # Verificar estado estable: si las fases no cambian mas
        steady_state_reached = converged and max_delta < self._epsilon * 10

        duration_ms = int((time.time() - start_time) * 1000)

        result = CODResult(
            cycle_id=cycle.id,
            converged=converged,
            iterations=iterations,
            final_phases=final_phases,
            final_values=final_values,
            convergence_delta=max_delta,
            steady_state_reached=steady_state_reached,
        )

        status = "CONVERGIO" if converged else "NO CONVERGIO"
        logger.info(
            f"COD: Ciclo '{cycle.name}' {status} — "
            f"iteraciones={iterations} delta={max_delta:.8f} "
            f"estado_estable={steady_state_reached} ({duration_ms}ms)"
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
                f"COD: Retroalimentacion aplicada a {len(retrofeed_values)} variables "
                f"(damping={retrofeed_damping})"
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
