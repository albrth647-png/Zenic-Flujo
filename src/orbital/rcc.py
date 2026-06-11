"""
ORBITAL — Pilar 3: RCC (Resonancia de Ciclo Cerrado)
======================================================

Detecta cuando la tension orbital de un ciclo cerrado supera el umbral,
indicando resonancia determinista. Cuando hay resonancia, las variables
estan sincronizadas orbitalmente y se puede predecir multimodalmente.

RCC es el DETECTOR de patrones deterministas del sistema ORBITAL.
A diferencia de la probabilidad, RCC dice "estas variables estan
resonando juntas" — es un hecho determinista, no una estimacion.

Criterio de resonancia:
    RCC activo cuando: TOR_promedio(ciclo) > umbral

    TOR_promedio = (1/N) * sum(|TOR(i,j)|) para todas las parejas del ciclo

Ejemplo de uso:
    >>> from src.orbital.ovc import OVC
    >>> from src.orbital.tor import TOR
    >>> from src.orbital.rcc import RCC
    >>> ovc = OVC()
    >>> ovc.create_variables_batch([
    ...     {"name": "Demanda", "theta": 0.0, "amplitude": 10.0},
    ...     {"name": "Precio", "theta": 0.1, "amplitude": 50.0},
    ...     {"name": "Oferta", "theta": 0.2, "amplitude": 8.0},
    ... ])
    >>> tor = TOR(ovc)
    >>> rcc = RCC(ovc, tor)
    >>> ciclo = CicloOrbital(name="Economico", variable_ids=["Demanda", "Precio", "Oferta"], threshold=0.5)
    >>> result = rcc.detect(ciclo)
    >>> print(f"Resonante: {result.is_resonant}, Fuerza: {result.resonance_strength:.4f}")
"""

from __future__ import annotations

from src.orbital.models import (
    DEFAULT_THRESHOLD,
    CicloOrbital,
    RCCResult,
)
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class RCC:
    """
    Resonancia de Ciclo Cerrado — Detector de resonancia determinista.

    Analiza los ciclos cerrados del sistema orbital para detectar cuando
    las variables estan en resonancia. La resonancia indica que las
    variables estan sincronizadas y el sistema ha encontrado un patron
    determinista estable.

    La resonancia NO es probabilidad: es un estado observable del sistema
    circular. Cuando las fases se alinean, la tension aumenta, y eso
    es un HECHO determinista, no una estimacion estocastica.
    """

    def __init__(self, ovc, tor):
        """
        Inicializa el detector RCC.

        Args:
            ovc: Instancia de OVC con las variables orbitales
            tor: Instancia de TOR para calcular tensiones
        """
        self._ovc = ovc
        self._tor = tor
        self._cycles: dict[str, CicloOrbital] = {}

    # ── Gestion de ciclos ──────────────────────────────────

    def register_cycle(self, cycle: CicloOrbital) -> None:
        """
        Registra un ciclo orbital para monitoreo de resonancia.

        Args:
            cycle: CicloOrbital con las variables que forman el ciclo

        Raises:
            ValueError: Si alguna variable del ciclo no existe en OVC
        """
        # Validar que todas las variables existen
        for var_name in cycle.variable_ids:
            if self._ovc.get_variable(var_name) is None:
                raise ValueError(f"Variable '{var_name}' del ciclo no existe en OVC")

        self._cycles[cycle.id] = cycle
        logger.info(f"RCC: Ciclo registrado '{cycle.name}' con {len(cycle.variable_ids)} variables")

    def register_cycle_from_names(
        self,
        name: str,
        variable_names: list[str],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> CicloOrbital:
        """
        Crea y registra un ciclo orbital a partir de nombres de variables.

        Args:
            name: Nombre del ciclo
            variable_names: Nombres de las variables que forman el ciclo
            threshold: Umbral de resonancia

        Returns:
            CicloOrbital creado y registrado
        """
        cycle = CicloOrbital(
            name=name,
            variable_ids=variable_names,
            threshold=threshold,
        )
        self.register_cycle(cycle)
        return cycle

    # ── Deteccion de resonancia ────────────────────────────

    def detect(self, cycle: CicloOrbital) -> RCCResult:
        """
        Detecta resonancia en un ciclo orbital especifico.

        Criterio: TOR_promedio > umbral del ciclo
        donde TOR_promedio = promedio de |TOR(i,j)| para todas las parejas.

        Args:
            cycle: CicloOrbital a analizar

        Returns:
            RCCResult con el estado de resonancia
        """
        # Calcular TOR para todas las parejas del ciclo
        tor_results = self._tor.calculate_for_cycle(cycle.variable_ids, threshold=cycle.threshold)

        if not tor_results:
            return RCCResult(
                cycle_id=cycle.id,
                is_resonant=False,
                resonance_strength=0.0,
            )

        # Calcular metricas
        tor_values = [abs(r.tor_value) for r in tor_results]
        total_tension = sum(tor_values)
        average_tension = total_tension / len(tor_values)
        max_tension = max(tor_values)
        min_tension = min(tor_values)

        # Deteccion de resonancia
        is_resonant = average_tension > cycle.threshold

        # Parejas resonantes
        resonant_pairs = [r for r in tor_results if r.is_resonant]

        # Fuerza de resonancia [0, 1]
        # Normalizar respecto al maximo posible (suma de Ai*Aj)
        max_possible = sum(
            self._ovc.get_variable(n_i).amplitude * self._ovc.get_variable(n_j).amplitude
            for i, n_i in enumerate(cycle.variable_ids)
            for n_j in cycle.variable_ids[i + 1 :]
            if self._ovc.get_variable(n_i) and self._ovc.get_variable(n_j)
        )
        resonance_strength = min(total_tension / max_possible, 1.0) if max_possible > 0 else 0.0

        result = RCCResult(
            cycle_id=cycle.id,
            total_tension=total_tension,
            average_tension=average_tension,
            max_tension=max_tension,
            min_tension=min_tension,
            is_resonant=is_resonant,
            resonant_pairs=resonant_pairs,
            resonance_strength=resonance_strength,
        )

        logger.info(
            f"RCC: Ciclo '{cycle.name}' — "
            f"resonante={is_resonant} fuerza={resonance_strength:.4f} "
            f"avg_tension={average_tension:.4f} umbral={cycle.threshold:.4f}"
        )

        return result

    def detect_all(self) -> list[RCCResult]:
        """
        Detecta resonancia en TODOS los ciclos registrados.

        Returns:
            Lista de RCCResult, uno por cada ciclo
        """
        results = []
        for cycle in self._cycles.values():
            result = self.detect(cycle)
            results.append(result)
        return results

    # ── Analisis de resonancia ─────────────────────────────

    def get_resonant_cycles(self) -> list[RCCResult]:
        """Retorna solo los ciclos que estan en resonancia."""
        return [r for r in self.detect_all() if r.is_resonant]

    def get_strongest_resonance(self) -> RCCResult | None:
        """Retorna el ciclo con mayor fuerza de resonancia."""
        results = self.detect_all()
        if not results:
            return None
        return max(results, key=lambda r: r.resonance_strength)

    def get_resonance_summary(self) -> dict:
        """
        Retorna un resumen del estado de resonancia del sistema.

        Returns:
            Diccionario con estadisticas de resonancia global
        """
        results = self.detect_all()
        resonant = [r for r in results if r.is_resonant]
        return {
            "total_cycles": len(results),
            "resonant_cycles": len(resonant),
            "non_resonant_cycles": len(results) - len(resonant),
            "max_strength": max((r.resonance_strength for r in results), default=0.0),
            "avg_strength": (sum(r.resonance_strength for r in results) / len(results) if results else 0.0),
        }

    # ── Actualizacion de ciclos ────────────────────────────

    def update_cycle_threshold(self, cycle_id: str, new_threshold: float) -> None:
        """Actualiza el umbral de resonancia de un ciclo."""
        if cycle_id in self._cycles:
            self._cycles[cycle_id].threshold = new_threshold
            logger.info(f"RCC: Umbral del ciclo actualizado a {new_threshold:.4f}")

    def remove_cycle(self, cycle_id: str) -> None:
        """Elimina un ciclo del monitoreo."""
        if cycle_id in self._cycles:
            del self._cycles[cycle_id]
            logger.info(f"RCC: Ciclo {cycle_id} eliminado")

    # ── Representacion ─────────────────────────────────────

    def __repr__(self) -> str:
        return f"RCC(ciclos={len(self._cycles)}, ovc={self._ovc})"

    def resonance_report(self) -> str:
        """Retorna un reporte legible del estado de resonancia."""
        results = self.detect_all()
        lines = ["RCC — Reporte de Resonancia de Ciclo Cerrado"]
        lines.append(f"  Ciclos monitoreados: {len(results)}")
        for r in results:
            cycle = self._cycles.get(r.cycle_id)
            name = cycle.name if cycle else r.cycle_id
            status = "RESONANTE" if r.is_resonant else "no resonante"
            lines.append(
                f"  [{status}] {name}: fuerza={r.resonance_strength:.4f} "
                f"avg_tension={r.average_tension:.4f} pares_resonantes={len(r.resonant_pairs)}"
            )
        return "\n".join(lines)
