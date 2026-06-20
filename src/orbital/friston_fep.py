"""
ORBITAL — Friston Free Energy Principle (Mejora 2)
====================================================

Implementa F(θ) = energía(θ) - entropía(θ) como función objetivo del COD.

Fundamento matemático (Friston 2010, Nature Reviews Neuroscience):
- Cualquier sistema auto-organizado minimiza su free energy variacional.
- F = energía - entropía.
- Minimizar F = maximizar verosimilitud + maximizar entropía.

Adaptación al motor Orbital:
- Energía U(θ) = -Σ TOR(i,j) / N   (energy baja = tensiones altas = sincronía)
  Nota: U(θ) = V(θ) del Lyapunov tracker, reescalado.
- Entropía S(θ) = -Σ p(θ_i) · ln(p(θ_i))   (Shannon sobre histograma de fases)
  donde p(θ_i) = #variables en bin(θ_i) / N_total.
- Free Energy F(θ) = U(θ) - S(θ)   (minimizar → sincronía + diversidad)

Relación con Mejora 1 (Lyapunov):
- V(θ) ya es función de Lyapunov estricta del COD (Mejora 1).
- F(θ) = V(θ) - S(θ) es una métrica observacional MÁS RICA que V sola:
  * Si S = 0 (todas las variables en misma fase): F = V (Lyapunov puro).
  * Si S > 0 (diversidad de fases): F < V (premia diversidad).
- NOTA IMPORTANTE: F es PURAMENTE OBSERVACIONAL. El COD NO usa F para
  modificar su dinámica. F se trackea y reporta, pero el descenso por
  gradiente usa exclusivamente ∇V (Lyapunov). Durante sincronización
  legítima, F puede aumentar (porque la entropía S cae), lo que produce
  fep_stable=False aunque lyapunov_stable=True. Esto NO es un error:
  indica que el sistema está perdiendo diversidad de fases.

Uso:
    from src.orbital.friston_fep import FEPTracker

    fep = FEPTracker(n_bins=12)
    F = fep.compute_F(ovc, tor)
    status = fep.update(ovc, tor)
    if status.violation:
        # F aumentó — sistema no se está auto-organizando
        ...
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.orbital.models import TWO_PI
from src.core.logging import setup_logging

if TYPE_CHECKING:
    from src.orbital.ovc import OVC
    from src.orbital.tor import TOR

logger = setup_logging(__name__)


# Tolerancia numérica para comparar F antes/después.
FEP_TOLERANCE: float = 1e-9

# Número default de bins para el histograma de fases (entropía de Shannon).
DEFAULT_N_BINS: int = 12  # 12 bins de 30° cada uno (360°/12)


@dataclass
class FEPSnapshot:
    """Snapshot de F en un momento específico del tiempo."""

    iteration: int
    F: float
    energy: float  # U(θ) = -Σ TOR / N
    entropy: float  # S(θ) = -Σ p ln p
    timestamp: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "iteration": self.iteration,
            "F": round(self.F, 8),
            "energy": round(self.energy, 8),
            "entropy": round(self.entropy, 8),
            "timestamp": self.timestamp,
        }


@dataclass
class FEPStatus:
    """Estado del FEP tracker tras una actualización."""

    F: float
    delta_F: float  # F_actual - F_anterior (negativo = decreció = bien)
    energy: float  # U(θ) actual
    entropy: float  # S(θ) actual
    iteration: int
    is_stable: bool  # True si F monótona decreciente en TODO el historial
    violation: bool  # True si F aumentó más allá de la tolerancia en ESTE step
    history_length: int
    min_F: float
    max_F: float

    def to_dict(self) -> dict[str, object]:
        return {
            "F": round(self.F, 8),
            "delta_F": round(self.delta_F, 8),
            "energy": round(self.energy, 8),
            "entropy": round(self.entropy, 8),
            "iteration": self.iteration,
            "is_stable": self.is_stable,
            "violation": self.violation,
            "history_length": self.history_length,
            "min_F": round(self.min_F, 8),
            "max_F": round(self.max_F, 8),
        }


class FEPTracker:
    """
    Trackea F(θ) = energía - entropía para verificar auto-organización.

    F(θ) = U(θ) - S(θ)

    donde:
    - U(θ) = -Σ_{i<j} TOR(i,j) / N   (energía = V del Lyapunov / N)
    - S(θ) = -Σ p(θ_i) ln(p(θ_i))    (entropía de Shannon de las fases)

    Fundamento: Friston (2010, Nature Reviews Neuroscience).
    Si F monótona decreciente → el sistema se auto-organiza.
    Si F aumenta → bug o inestabilidad detectable en tiempo real.

    Diferencia con V del Lyapunov:
    - V solo mide energía (sincronía).
    - F = V - S mide energía + diversidad.
    - F premia sistemas sincronizados pero NO colapsados (preserva diversidad).
    """

    def __init__(
        self,
        tolerance: float = FEP_TOLERANCE,
        n_bins: int = DEFAULT_N_BINS,
    ) -> None:
        """Inicializa el tracker.

        Args:
            tolerance: Tolerancia numérica para considerar F estable.
            n_bins: Número de bins para el histograma de fases (entropía).
                    Más bins = mayor resolución de entropía, pero requiere
                    más variables para que el histograma sea significativo.
        """
        self._tolerance = tolerance
        self._n_bins = n_bins
        self._history: list[FEPSnapshot] = []
        self._iteration: int = 0
        self._min_F: float = float("inf")
        self._max_F: float = float("-inf")
        self._violations_count: int = 0

    @property
    def history(self) -> list[FEPSnapshot]:
        """Historial completo de snapshots."""
        return self._history

    @property
    def violations_count(self) -> int:
        """Número total de violaciones detectadas (F aumentó)."""
        return self._violations_count

    @property
    def is_fep_stable(self) -> bool:
        """True si F ha sido monótona decreciente en todas las iteraciones."""
        return self._violations_count == 0 and len(self._history) >= 2

    def compute_energy(
        self,
        ovc: "OVC",
        tor: "TOR",
        cycle_variable_ids: list[str] | None = None,
    ) -> float:
        """
        Calcula U(θ) = -Σ_{i<j} TOR(i,j) / N.

        Esta es la "energía" del sistema en sentido Friston:
        - U baja (negativa) → tensiones altas → variables sincronizadas.
        - U alta (positiva o 0) → tensiones bajas → variables desordenadas.

        Normalización por N (número de variables en el ciclo) para hacer
        U comparable entre sistemas de diferentes tamaños.

        Args:
            ovc: Instancia de OVC.
            tor: Instancia de TOR.
            cycle_variable_ids: Restringir a variables del ciclo si se provee.

        Returns:
            U(θ): energía del sistema (float).
        """
        if cycle_variable_ids is not None:
            tor_results = tor.calculate_for_cycle(cycle_variable_ids)
            N = max(1, len(cycle_variable_ids))
        else:
            tor_results = tor.calculate_matrix()
            N = max(1, ovc.variable_count)

        sum_tor = sum(result.tor_value for result in tor_results)
        return -sum_tor / N

    def compute_entropy(
        self,
        ovc: "OVC",
        cycle_variable_ids: list[str] | None = None,
    ) -> float:
        """
        Calcula S(θ) = -Σ p(θ_i) · ln(p(θ_i)) (entropía de Shannon).

        Distribuye las fases en self._n_bins bins de [0, 2π).
        p(θ_i) = #variables en el bin de θ_i / N_total.
        S = 0 → todas las variables en el mismo bin (sin diversidad).
        S = ln(n_bins) → distribución uniforme (máxima diversidad).

        Args:
            ovc: Instancia de OVC.
            cycle_variable_ids: Restringir a variables del ciclo si se provee.

        Returns:
            S(θ): entropía de Shannon del histograma de fases.
        """
        if cycle_variable_ids is not None:
            variables = [
                ovc.get_variable(name)
                for name in cycle_variable_ids
                if ovc.get_variable(name) is not None
            ]
        else:
            variables = list(ovc.get_all_variables().values())

        N = len(variables)
        if N == 0:
            return 0.0

        # Construir histograma de fases en [0, 2π)
        bin_counts = [0] * self._n_bins
        for var in variables:
            bin_idx = int((var.theta % TWO_PI) / TWO_PI * self._n_bins)
            if bin_idx >= self._n_bins:
                bin_idx = self._n_bins - 1
            bin_counts[bin_idx] += 1

        # Calcular entropía de Shannon
        entropy = 0.0
        for count in bin_counts:
            if count > 0:
                p = count / N
                entropy -= p * math.log(p)

        return entropy

    def compute_F(
        self,
        ovc: "OVC",
        tor: "TOR",
        cycle_variable_ids: list[str] | None = None,
    ) -> tuple[float, float, float]:
        """
        Calcula F(θ) = U(θ) - S(θ).

        Args:
            ovc: Instancia de OVC.
            tor: Instancia de TOR.
            cycle_variable_ids: Restringir a variables del ciclo si se provee.

        Returns:
            Tupla (F, U, S) donde:
            - F = U - S (free energy)
            - U = energía (negativa de tensión promedio)
            - S = entropía de Shannon de las fases
        """
        U = self.compute_energy(ovc, tor, cycle_variable_ids)
        S = self.compute_entropy(ovc, cycle_variable_ids)
        F = U - S
        return F, U, S

    def update(
        self,
        ovc: "OVC",
        tor: "TOR",
        cycle_variable_ids: list[str] | None = None,
    ) -> FEPStatus:
        """
        Snapshot + comparación con el anterior. Debe llamarse en cada iteración
        del COD (o en cada tick del motor).

        Args:
            ovc: Instancia de OVC.
            tor: Instancia de TOR.
            cycle_variable_ids: Restringir a variables del ciclo si se provee.

        Returns:
            FEPStatus con F actual, delta_F, y flags de estabilidad/violación.
        """
        F, U, S = self.compute_F(ovc, tor, cycle_variable_ids)

        self._iteration += 1
        snapshot = FEPSnapshot(
            iteration=self._iteration,
            F=F,
            energy=U,
            entropy=S,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._history.append(snapshot)

        # Actualizar min/max
        self._min_F = min(self._min_F, F)
        self._max_F = max(self._max_F, F)

        # Comparar con el anterior
        delta_F = 0.0
        violation = False
        if len(self._history) >= 2:
            prev_F = self._history[-2].F
            delta_F = F - prev_F
            # F debe DECRECER (delta_F <= 0). Si aumenta más allá de la tolerancia,
            # es una violación de auto-organización.
            if delta_F > self._tolerance:
                violation = True
                self._violations_count += 1
                logger.warning(
                    f"FEP violation en iteración {self._iteration}: "
                    f"F aumentó {delta_F:.2e} (de {prev_F:.6f} a {F:.6f})"
                )

        return FEPStatus(
            F=F,
            delta_F=delta_F,
            energy=U,
            entropy=S,
            iteration=self._iteration,
            is_stable=self.is_fep_stable,
            violation=violation,
            history_length=len(self._history),
            min_F=self._min_F,
            max_F=self._max_F,
        )

    def reset(self) -> None:
        """Reinicia el tracker (limpia historial y contadores)."""
        self._history.clear()
        self._iteration = 0
        self._min_F = float("inf")
        self._max_F = float("-inf")
        self._violations_count = 0

    def summary(self) -> dict[str, object]:
        """Resumen estadístico del historial completo."""
        if not self._history:
            return {"status": "empty", "iterations": 0}

        F_values = [s.F for s in self._history]
        U_values = [s.energy for s in self._history]
        S_values = [s.entropy for s in self._history]

        decreases = sum(1 for i in range(1, len(F_values)) if F_values[i] < F_values[i - 1])
        increases = sum(1 for i in range(1, len(F_values)) if F_values[i] > F_values[i - 1])
        same = len(F_values) - 1 - decreases - increases

        return {
            "status": "fep_stable" if self.is_fep_stable else "violations_detected",
            "iterations": len(self._history),
            "violations_count": self._violations_count,
            "F_initial": round(F_values[0], 8),
            "F_final": round(F_values[-1], 8),
            "F_min": round(min(F_values), 8),
            "F_max": round(max(F_values), 8),
            "energy_initial": round(U_values[0], 8),
            "energy_final": round(U_values[-1], 8),
            "entropy_initial": round(S_values[0], 8),
            "entropy_final": round(S_values[-1], 8),
            "decreases": decreases,
            "increases": increases,
            "same": same,
            "decrease_rate": round(decreases / max(1, len(F_values) - 1), 4),
        }

    def trajectory(self) -> list[dict[str, object]]:
        """Retorna la trayectoria completa de F como lista de dicts (para graficar)."""
        return [s.to_dict() for s in self._history]
