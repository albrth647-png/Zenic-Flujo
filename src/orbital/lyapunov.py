# ruff: noqa: RUF002 — docstrings y comentarios matemáticos usan caracteres griegos intencionalmente
"""
ORBITAL — Lyapunov Tracker (Mejora 1, revisión 2)
==================================================

Implementa V(θ) = -Σ_{i<j} TOR(i,j) como función de Lyapunov del COD.

Fundamento matemático:
- Kuramoto (1975) y Strogatz (2000): para sistemas de osciladores acoplados
  con V(θ) = -Σ cos(θ_i - θ_j), la dinámica dθ_i/dt = -dV/dθ_i garantiza
  V monótona decreciente (función de Lyapunov estricta).
- Hopfield (1982, PNAS): análogo para redes discretas con pesos simétricos.

Propiedades matemáticas de V:
1. V acotada: V ∈ [-ΣA_iA_j, +ΣA_iA_j]
2. Gradiente: dV/dθ_i = Σ_j A_i·A_j·sin(θ_i - θ_j)
3. La dinámica del COD debe ser: θ_i_new = θ_i - α · (dV/dθ_i)  # noqa: RUF002
   para que V sea Lyapunov estricta. Si el COD usa otra fórmula
   (ej: tanh(Σ TOR) con cos en lugar de sin), V puede aumentar y
   la garantía no se cumple.

Uso:
    from src.orbital.lyapunov import LyapunovTracker

    tracker = LyapunovTracker()
    status = tracker.update(ovc, tor, cycle_variable_ids=[...])
    if status.violation:
        # V aumentó — bug o inestabilidad detectada
        ...
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.core.logging import setup_logging

if TYPE_CHECKING:
    from src.orbital.ovc import OVC
    from src.orbital.tor import TOR

logger = setup_logging(__name__)


# Tolerancia numérica para comparar V antes/después.
# Permite fluctuaciones minúsculas por redondeo de punto flotante.
LYAPUNOV_TOLERANCE: float = 1e-9


@dataclass
class LyapunovSnapshot:
    """Snapshot de V en un momento específico del tiempo."""

    iteration: int
    V: float
    gradient_norm: float
    timestamp: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "iteration": self.iteration,
            "V": round(self.V, 8),
            "gradient_norm": round(self.gradient_norm, 8),
            "timestamp": self.timestamp,
        }


@dataclass
class LyapunovStatus:
    """Estado del Lyapunov tracker tras una actualización."""

    V: float
    delta_V: float  # V_actual - V_anterior (negativo = decreció = bien)  # noqa: N815
    iteration: int
    is_stable: bool  # True si V monótona decreciente en TODO el historial
    violation: bool  # True si V aumentó más allá de la tolerancia en ESTE step
    history_length: int
    min_V: float  # mínimo histórico de V  # noqa: N815
    max_V: float  # máximo histórico de V  # noqa: N815
    average_decrease_rate: float  # tasa promedio de decrecimiento por iteración
    gradient_norm: float = 0.0  # ||∇V(θ)|| en el momento de la actualización

    def to_dict(self) -> dict[str, object]:
        return {
            "V": round(self.V, 8),
            "delta_V": round(self.delta_V, 8),
            "iteration": self.iteration,
            "is_stable": self.is_stable,
            "violation": self.violation,
            "history_length": self.history_length,
            "min_V": round(self.min_V, 8),
            "max_V": round(self.max_V, 8),
            "average_decrease_rate": round(self.average_decrease_rate, 8),
            "gradient_norm": round(self.gradient_norm, 8),
        }


class LyapunovTracker:
    """
    Trackea V(θ) y dV/dt para garantizar convergencia formal del COD.

    V(θ) = -Σ_{i<j} A_i·A_j·cos(θ_i - θ_j)

    Fundamento: Kuramoto (1975) + Strogatz (2000) + Hopfield (1982).
    Si V monótona decreciente → convergencia garantizada.
    Si V aumenta → bug o inestabilidad detectable en tiempo real.

    Nota: Para que V sea Lyapunov estricta, la dinámica del COD debe ser
    descenso por gradiente de V: θ_i_new = θ_i - α · (dV/dθ_i).  # noqa: RUF002
    El método `compute_gradient` expone dV/dθ_i para que el COD lo use.
    """

    def __init__(self, tolerance: float = LYAPUNOV_TOLERANCE) -> None:
        """Inicializa el tracker.

        Args:
            tolerance: Tolerancia numérica para considerar V estable.
                       V aumentos menores a este valor no se consideran violación.
        """
        self._tolerance = tolerance
        self._history: list[LyapunovSnapshot] = []
        self._iteration: int = 0
        self._min_V: float = float("inf")
        self._max_V: float = float("-inf")
        self._violations_count: int = 0

    @property
    def history(self) -> list[LyapunovSnapshot]:
        """Historial completo de snapshots."""
        return self._history

    @property
    def violations_count(self) -> int:
        """Número total de violaciones detectadas (V aumentó)."""
        return self._violations_count

    @property
    def is_lyapunov_stable(self) -> bool:
        """True si V ha sido monótona decreciente en todas las iteraciones."""
        return self._violations_count == 0 and len(self._history) >= 2

    def compute_V(
        self,
        ovc: OVC,
        tor: TOR,
        cycle_variable_ids: list[str] | None = None,
    ) -> float:
        """
        Calcula V(θ) = -Σ_{i<j} TOR(i,j).

        Args:
            ovc: Instancia de OVC con las variables orbitales.
            tor: Instancia de TOR para calcular tensiones.
            cycle_variable_ids: Si se provee, calcula V solo para las parejas
                del ciclo (usando calculate_for_cycle). Si es None, usa todas
                las parejas del OVC (calculate_matrix).

        Returns:
            V (float): valor actual de la función de Lyapunov.
            V = 0 → todas las variables ortogonales (cos = 0)
            V = -ΣA_iA_j → todas las variables en fase (sincronía, N=2)
            V = +ΣA_iA_j → todas las variables en antifase (N=2)
            Para N>2, los extremos absolutos no son alcanzables en general.
        """
        if cycle_variable_ids is not None:
            tor_results = tor.calculate_for_cycle(cycle_variable_ids)
        else:
            tor_results = tor.calculate_matrix()
        V = 0.0
        for result in tor_results:
            V -= result.tor_value
        return V

    def compute_gradient(
        self,
        ovc: OVC,
        tor: TOR,
        cycle_variable_ids: list[str] | None = None,
    ) -> dict[str, float]:
        """
        Calcula ∇V(θ) componente por componente.

        dV/dθ_i = Σ_j A_i·A_j·sin(θ_i - θ_j)

        Esta es la "fuerza" que el COD debe aplicar (con signo negativo)
        para hacer descenso por gradiente sobre V y garantizar Lyapunov.

        Args:
            ovc: Instancia de OVC.
            tor: Instancia de TOR.
            cycle_variable_ids: Si se provee, calcula el gradiente solo para
                las variables del ciclo. Si es None, usa todas.

        Returns:
            Dict {var_name: dV/dθ} para cada variable relevante.
        """
        # Seleccionar variables sobre las que calcular el gradiente
        if cycle_variable_ids is not None:
            relevant_vars = {
                name: ovc.get_variable(name)
                for name in cycle_variable_ids
                if ovc.get_variable(name) is not None
            }
            tor_results = tor.calculate_for_cycle(cycle_variable_ids)
        else:
            relevant_vars = ovc.get_all_variables()
            tor_results = tor.calculate_matrix()

        # Inicializar gradientes a 0
        gradient: dict[str, float] = dict.fromkeys(relevant_vars, 0.0)

        # Para cada pareja (i, j), acumular contribuciones antisimétricas
        for result in tor_results:
            i_name = result.variable_i
            j_name = result.variable_j
            if i_name not in gradient or j_name not in gradient:
                continue

            var_i = relevant_vars.get(i_name)
            var_j = relevant_vars.get(j_name)
            if var_i is None or var_j is None:
                continue

            # A_i·A_j directo del OVC (estable, sin división)
            A_i_A_j = var_i.amplitude * var_j.amplitude
            sin_diff = math.sin(result.phase_diff)  # sin(θ_i - θ_j)

            # dV/dθ_i += A_i·A_j·sin(θ_i - θ_j)
            # dV/dθ_j += A_i·A_j·sin(θ_j - θ_i) = -A_i·A_j·sin(θ_i - θ_j)
            contribution = A_i_A_j * sin_diff
            gradient[i_name] += contribution
            gradient[j_name] -= contribution

        return gradient

    def compute_gradient_norm(
        self,
        ovc: OVC,
        tor: TOR,
        cycle_variable_ids: list[str] | None = None,
    ) -> float:
        """
        Calcula ||∇V(θ)|| = √(Σ (dV/dθ_i)²).

        Si la norma es 0, el sistema está en un punto crítico (posible fijo).

        Args:
            ovc: Instancia de OVC.
            tor: Instancia de TOR.
            cycle_variable_ids: Restringir a variables del ciclo si se provee.

        Returns:
            Norma euclidiana del gradiente de V.
        """
        gradient = self.compute_gradient(ovc, tor, cycle_variable_ids)
        return math.sqrt(sum(g * g for g in gradient.values()))

    def _compute_V_and_gradient(
        self,
        ovc: OVC,
        tor: TOR,
        cycle_variable_ids: list[str] | None = None,
    ) -> tuple[float, float, dict[str, float]]:
        """Computa V, ||∇V||, y ∇V en una sola pasada (eficiencia)."""
        # Seleccionar variables
        if cycle_variable_ids is not None:
            relevant_vars = {
                name: ovc.get_variable(name)
                for name in cycle_variable_ids
                if ovc.get_variable(name) is not None
            }
            tor_results = tor.calculate_for_cycle(cycle_variable_ids)
        else:
            relevant_vars = ovc.get_all_variables()
            tor_results = tor.calculate_matrix()

        # Inicializar gradientes
        gradient: dict[str, float] = dict.fromkeys(relevant_vars, 0.0)

        # Una sola iteración sobre tor_results
        V = 0.0
        for result in tor_results:
            V -= result.tor_value

            i_name = result.variable_i
            j_name = result.variable_j
            if i_name not in gradient or j_name not in gradient:
                continue

            var_i = relevant_vars.get(i_name)
            var_j = relevant_vars.get(j_name)
            if var_i is None or var_j is None:
                continue

            A_i_A_j = var_i.amplitude * var_j.amplitude
            sin_diff = math.sin(result.phase_diff)
            contribution = A_i_A_j * sin_diff
            gradient[i_name] += contribution
            gradient[j_name] -= contribution

        gradient_norm = math.sqrt(sum(g * g for g in gradient.values()))
        return V, gradient_norm, gradient

    def update(
        self,
        ovc: OVC,
        tor: TOR,
        cycle_variable_ids: list[str] | None = None,
    ) -> LyapunovStatus:
        """
        Snapshot + comparación con el anterior. Debe llamarse en cada iteración
        del COD (o en cada tick del motor).

        Args:
            ovc: Instancia de OVC.
            tor: Instancia de TOR.
            cycle_variable_ids: Restringir a variables del ciclo si se provee.

        Returns:
            LyapunovStatus con V actual, delta_V, y flags de estabilidad/violación.
        """
        V, gradient_norm, _ = self._compute_V_and_gradient(
            ovc, tor, cycle_variable_ids
        )

        self._iteration += 1
        snapshot = LyapunovSnapshot(
            iteration=self._iteration,
            V=V,
            gradient_norm=gradient_norm,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self._history.append(snapshot)

        # Actualizar min/max
        self._min_V = min(self._min_V, V)
        self._max_V = max(self._max_V, V)

        # Comparar con el anterior
        delta_V = 0.0
        violation = False
        if len(self._history) >= 2:
            prev_V = self._history[-2].V
            delta_V = V - prev_V
            # V debe DECRECER (delta_V <= 0). Si aumenta más allá de la tolerancia,
            # es una violación de Lyapunov.
            if delta_V > self._tolerance:
                violation = True
                self._violations_count += 1
                logger.warning(
                    f"Lyapunov violation en iteración {self._iteration}: "
                    f"V aumentó {delta_V:.2e} (de {prev_V:.6f} a {V:.6f})"
                )

        # Tasa promedio de decrecimiento
        average_decrease_rate = 0.0
        if len(self._history) >= 2:
            total_decrease = self._history[0].V - self._history[-1].V
            average_decrease_rate = total_decrease / (len(self._history) - 1)

        return LyapunovStatus(
            V=V,
            delta_V=delta_V,
            iteration=self._iteration,
            is_stable=self.is_lyapunov_stable,
            violation=violation,
            history_length=len(self._history),
            min_V=self._min_V,
            max_V=self._max_V,
            average_decrease_rate=average_decrease_rate,
            gradient_norm=gradient_norm,
        )

    def reset(self) -> None:
        """Reinicia el tracker (limpia historial y contadores)."""
        self._history.clear()
        self._iteration = 0
        self._min_V = float("inf")
        self._max_V = float("-inf")
        self._violations_count = 0

    def summary(self) -> dict[str, object]:
        """Resumen estadístico del historial completo."""
        if not self._history:
            return {"status": "empty", "iterations": 0}

        V_values = [s.V for s in self._history]
        grad_values = [s.gradient_norm for s in self._history]

        # Contar decrecimientos vs incrementos
        decreases = sum(1 for i in range(1, len(V_values)) if V_values[i] < V_values[i - 1])
        increases = sum(1 for i in range(1, len(V_values)) if V_values[i] > V_values[i - 1])
        same = len(V_values) - 1 - decreases - increases

        return {
            "status": "lyapunov_stable" if self.is_lyapunov_stable else "violations_detected",
            "iterations": len(self._history),
            "violations_count": self._violations_count,
            "V_initial": round(V_values[0], 8),
            "V_final": round(V_values[-1], 8),
            "V_min": round(min(V_values), 8),
            "V_max": round(max(V_values), 8),
            "decreases": decreases,
            "increases": increases,
            "same": same,
            "decrease_rate": round(decreases / max(1, len(V_values) - 1), 4),
            "gradient_initial": round(grad_values[0], 8),
            "gradient_final": round(grad_values[-1], 8),
            "gradient_decrease_pct": round(
                (grad_values[0] - grad_values[-1]) / max(1e-10, grad_values[0]) * 100, 2
            ),
        }

    def trajectory(self) -> list[dict[str, object]]:
        """Retorna la trayectoria completa de V como lista de dicts (para graficar)."""
        return [s.to_dict() for s in self._history]
