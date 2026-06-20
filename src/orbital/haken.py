"""
ORBITAL — Haken Synergetics Analyzer (Mejora 4)
=================================================

Aplica el slaving principle de Haken (1976) al COD para identificar
order parameters (modos lentos) y modos esclavizados (rápidos).

Fundamento matemático:
- El Laplaciano L = H(V) (Mejora 3) tiene autovalores μ_k y autovectores v_k.
- El Jacobiano del mapeo del COD es J = I - β·L con autovalores λ_k = 1 - β·μ_k.
- La escala temporal exacta del mapeo discreto es τ_k = -1/ln|λ_k|
  (NO 1/(1-|λ_k|), que es incorrecta; verificada numéricamente).
- El modo rotacional (μ≈0, autovector uniforme) se excluye: es gauge S^1, no OP.
- Slaving activo cuando τ_slow / τ_fast > 10 (Haken 1976, §7.2).

Referencias:
- Haken, H. (1976). Synergetics: An Introduction. Springer.
- Haken, H. (1983). Advanced Synergetics. Springer, §8.2.
- Scholarpedia: http://www.scholarpedia.org/article/Synergetics
"""
from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from src.orbital.conley import ConleyClassifier
from src.utils.logger import setup_logging

if TYPE_CHECKING:
    from src.orbital.ovc import OVC
    from src.orbital.tor import TOR

logger = setup_logging(__name__)


HAKEN_MARGINAL_EPS: float = 1e-6
HAKEN_ROTATIONAL_EPS: float = 1e-6
HAKEN_SLAVING_THRESHOLD: float = 10.0
HAKEN_SLAVING_STRONG: float = 100.0
HAKEN_GAP_RATIO_MIN: float = 2.0
HAKEN_CONTRIBUTION_FACTOR: float = 1.0


class ModeType(str, enum.Enum):
    """Clasificación de cada modo espectral."""
    ROTATIONAL = "rotational"
    STABLE_SLOW = "stable_slow"
    STABLE_FAST = "stable_fast"
    STABLE_INTERMEDIATE = "stable_intermediate"
    UNSTABLE = "unstable"
    MARGINAL = "marginal"


class SlavingState(str, enum.Enum):
    """Estado global del slaving principle."""
    ACTIVE = "active"
    WEAK = "weak"
    DEMOCRATIC = "democratic"
    NOT_APPLICABLE_UNSTABLE = "not_applicable_unstable"
    NOT_APPLICABLE_TRIVIAL = "not_applicable_trivial"
    NOT_APPLICABLE_MARGINAL = "not_applicable_marginal"


@dataclass
class ModeInfo:
    """Información detallada de un modo espectral."""

    index: int
    eigenvalue_mu: float
    eigenvalue_lambda: float
    timescale_tau: float
    timescale_continuous: float
    mode_type: ModeType
    overlap_with_rotational: float
    eigenvector: np.ndarray
    participation_ratio: float
    contributing_variable_indices: list[int] = field(default_factory=list)
    contributing_variable_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "eigenvalue_mu": float(self.eigenvalue_mu),
            "eigenvalue_lambda": float(self.eigenvalue_lambda),
            "timescale_tau": float(self.timescale_tau) if not math.isnan(self.timescale_tau) else None,
            "timescale_continuous": float(self.timescale_continuous) if math.isfinite(self.timescale_continuous) else None,
            "mode_type": self.mode_type.value,
            "overlap_with_rotational": float(self.overlap_with_rotational),
            "participation_ratio": float(self.participation_ratio),
            "contributing_variable_indices": self.contributing_variable_indices,
            "contributing_variable_names": self.contributing_variable_names,
            "eigenvector": [float(x) for x in self.eigenvector],
        }


@dataclass
class OrderParameter:
    """Un order parameter: modo lento con coordenada espectral actual."""

    mode: ModeInfo
    coordinate_xi: float
    relative_amplitude: float

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.to_dict(),
            "coordinate_xi": float(self.coordinate_xi),
            "relative_amplitude": float(self.relative_amplitude),
        }


@dataclass
class HakenStatus:
    """Resultado del análisis de Haken synergetics."""

    n_variables: int
    n_modes_total: int
    n_modes_rotational: int
    n_modes_stable_slow: int
    n_modes_stable_fast: int
    n_modes_stable_intermediate: int
    n_modes_unstable: int
    n_modes_marginal: int
    modes: list[ModeInfo] = field(default_factory=list)
    order_parameters: list[OrderParameter] = field(default_factory=list)
    fast_modes: list[ModeInfo] = field(default_factory=list)
    intermediate_modes: list[ModeInfo] = field(default_factory=list)
    tau_slow: float = float("nan")
    tau_fast: float = float("nan")
    separation_ratio: float = float("nan")
    slaving_state: SlavingState = SlavingState.NOT_APPLICABLE_TRIVIAL
    slaving_active: bool = False
    effective_dimension: int = 0
    reduction_error: float = float("nan")
    spectral_coordinates: list[float] = field(default_factory=list)
    reconstructed_state: list[float] = field(default_factory=list)
    beta: float = 0.0
    rotational_overlap: float = 0.0
    numerical_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        def _safe_float(v: float) -> float | None:
            if math.isnan(v) or math.isinf(v):
                return None
            return float(v)

        return {
            "n_variables": self.n_variables,
            "n_modes_total": self.n_modes_total,
            "n_modes_rotational": self.n_modes_rotational,
            "n_modes_stable_slow": self.n_modes_stable_slow,
            "n_modes_stable_fast": self.n_modes_stable_fast,
            "n_modes_stable_intermediate": self.n_modes_stable_intermediate,
            "n_modes_unstable": self.n_modes_unstable,
            "n_modes_marginal": self.n_modes_marginal,
            "modes": [m.to_dict() for m in self.modes],
            "order_parameters": [op.to_dict() for op in self.order_parameters],
            "fast_modes": [m.to_dict() for m in self.fast_modes],
            "intermediate_modes": [m.to_dict() for m in self.intermediate_modes],
            "tau_slow": _safe_float(self.tau_slow),
            "tau_fast": _safe_float(self.tau_fast),
            "separation_ratio": _safe_float(self.separation_ratio),
            "slaving_state": self.slaving_state.value,
            "slaving_active": self.slaving_active,
            "effective_dimension": self.effective_dimension,
            "reduction_error": _safe_float(self.reduction_error),
            "spectral_coordinates": [float(x) for x in self.spectral_coordinates],
            "reconstructed_state": [float(x) for x in self.reconstructed_state],
            "beta": float(self.beta),
            "rotational_overlap": float(self.rotational_overlap),
            "numerical_warnings": self.numerical_warnings,
        }


class HakenAnalyzer:
    """
    Analiza el espectro del COD bajo el slaving principle de Haken (1976).

    Identifica order parameters (modos lentos no-rotacionales) y modos
    esclavizados (rápidos). Calcula separation ratio y determina si
    el slaving principle aplica.

    Uso:
        analyzer = HakenAnalyzer()
        status = analyzer.analyze(ovc, tor, beta=0.05, cycle_variable_ids=[...])
        if status.slaving_active:
            print(f"Slaving activo: {len(status.order_parameters)} OPs")
    """

    def __init__(
        self,
        marginal_eps: float = HAKEN_MARGINAL_EPS,
        rotational_eps: float = HAKEN_ROTATIONAL_EPS,
        slaving_threshold: float = HAKEN_SLAVING_THRESHOLD,
        slaving_strong: float = HAKEN_SLAVING_STRONG,
        gap_ratio_min: float = HAKEN_GAP_RATIO_MIN,
        contribution_factor: float = HAKEN_CONTRIBUTION_FACTOR,
    ) -> None:
        self._marginal_eps = marginal_eps
        self._rotational_eps = rotational_eps
        self._slaving_threshold = slaving_threshold
        self._slaving_strong = slaving_strong
        self._gap_ratio_min = gap_ratio_min
        self._contribution_factor = contribution_factor
        self._conley = ConleyClassifier(
            marginal_tolerance=marginal_eps,
            rotational_tolerance=rotational_eps,
        )

    def analyze(
        self,
        ovc: "OVC",
        tor: "TOR",
        beta: float,
        cycle_variable_ids: list[str] | None = None,
    ) -> HakenStatus:
        """Ejecuta el análisis de Haken synergetics."""
        names = self._extract_variable_names(ovc, cycle_variable_ids)
        N = len(names)

        if N == 0:
            return self._trivial_status(N=0, beta=beta, reason="N=0: sin variables")
        if N == 1:
            return self._trivial_status(N=1, beta=beta, reason="N=1: sin dinámica")
        if beta <= 0:
            return self._trivial_status(N=N, beta=beta, reason="β<=0: sin dinámica")

        thetas = np.array([ovc.get_variable(n).theta for n in names], dtype=np.float64)

        L = self._conley.build_laplacian(ovc, tor, cycle_variable_ids)

        warnings: list[str] = []
        u = np.ones(N) / math.sqrt(N)
        L_dot_u_norm = float(np.linalg.norm(L @ u))
        L_norm = float(np.linalg.norm(L))
        if L_dot_u_norm > 1e-9 * max(1.0, L_norm):
            warnings.append(f"S^1 violada: ||L·u|| = {L_dot_u_norm:.2e}")

        try:
            mu_all, V_all = np.linalg.eigh(L)
        except np.linalg.LinAlgError as exc:
            return self._trivial_status(N=N, beta=beta, reason=f"eigh falló: {exc}")

        if not np.allclose(V_all.T @ V_all, np.eye(N), atol=1e-10):
            warnings.append("V no es ortonormal (drift numérico)")

        overlaps = np.abs(V_all.T @ u)
        rot_idx = int(np.argmax(overlaps))
        rot_overlap = float(overlaps[rot_idx])
        if rot_overlap < 1.0 - self._rotational_eps:
            warnings.append(f"Modo rotacional mal identificado (overlap={rot_overlap:.6f})")

        modes: list[ModeInfo] = []
        for k in range(N):
            mu_k = float(mu_all[k])
            lam_k = float(1.0 - beta * mu_k)
            v_k = V_all[:, k]
            abs_lam = abs(lam_k)

            if abs_lam < 1.0 - self._marginal_eps:
                tau_k = float(-1.0 / math.log(abs_lam)) if abs_lam > 1e-300 else 0.0
                mode_type = ModeType.STABLE_FAST
            elif abs_lam > 1.0 + self._marginal_eps:
                tau_k = float("nan")
                mode_type = ModeType.UNSTABLE
            else:
                tau_k = float("inf")
                mode_type = ModeType.MARGINAL

            tau_cont = float(1.0 / abs(mu_k)) if abs(mu_k) > 1e-300 else float("inf")

            pr = float(1.0 / np.sum(v_k**4)) if np.all(v_k**4 > 0) else float(N)

            threshold = self._contribution_factor / math.sqrt(N)
            contrib_idx = [i for i in range(N) if abs(v_k[i]) > threshold]
            contrib_names = [names[i] for i in contrib_idx]

            if k == rot_idx:
                mode_type = ModeType.ROTATIONAL
                tau_k = float("nan")

            modes.append(ModeInfo(
                index=k, eigenvalue_mu=mu_k, eigenvalue_lambda=lam_k,
                timescale_tau=tau_k, timescale_continuous=tau_cont,
                mode_type=mode_type, overlap_with_rotational=float(overlaps[k]),
                eigenvector=v_k.copy(), participation_ratio=pr,
                contributing_variable_indices=contrib_idx,
                contributing_variable_names=contrib_names,
            ))

        stable_indices = [k for k in range(N) if k != rot_idx and modes[k].mode_type == ModeType.STABLE_FAST]
        unstable_indices = [k for k in range(N) if k != rot_idx and modes[k].mode_type == ModeType.UNSTABLE]
        marginal_indices = [k for k in range(N) if k != rot_idx and modes[k].mode_type == ModeType.MARGINAL]

        if marginal_indices:
            return self._build_marginal_status(N, beta, modes, rot_overlap, warnings, marginal_indices)
        if unstable_indices:
            return self._build_unstable_status(N, beta, modes, rot_overlap, warnings, unstable_indices, stable_indices)
        if len(stable_indices) < 2:
            return self._build_democratic_status(N, beta, modes, rot_overlap, warnings, stable_indices,
                                                  "Solo 1 modo estable; insuficiente para slaving.")

        mu_stable = sorted([(modes[k].eigenvalue_mu, k) for k in stable_indices])
        mu_values = [m[0] for m in mu_stable]
        gaps = [mu_values[i + 1] - mu_values[i] for i in range(len(mu_values) - 1)]
        if not gaps:
            return self._build_democratic_status(N, beta, modes, rot_overlap, warnings, stable_indices,
                                                  "No hay gaps para analizar.")

        max_gap = max(gaps)
        median_gap = float(np.median(gaps))
        gap_ratio = max_gap / max(median_gap, 1e-12)
        i_gap = int(np.argmax(gaps))

        if gap_ratio < self._gap_ratio_min:
            return self._build_democratic_status(N, beta, modes, rot_overlap, warnings, stable_indices,
                                                  f"Gap espectral no significativo (ratio={gap_ratio:.2f} < {self._gap_ratio_min}).")

        slow_indices = [mu_stable[i][1] for i in range(i_gap + 1)]
        fast_indices = [mu_stable[i][1] for i in range(i_gap + 1, len(mu_stable))]

        for k in slow_indices:
            modes[k].mode_type = ModeType.STABLE_SLOW
        for k in fast_indices:
            modes[k].mode_type = ModeType.STABLE_FAST

        tau_slow = max(modes[k].timescale_tau for k in slow_indices)
        tau_fast = min(modes[k].timescale_tau for k in fast_indices)
        separation_ratio = tau_slow / tau_fast

        if separation_ratio >= self._slaving_strong:
            slaving_state = SlavingState.ACTIVE
            slaving_active = True
        elif separation_ratio >= self._slaving_threshold:
            slaving_state = SlavingState.ACTIVE
            slaving_active = True
        elif separation_ratio >= 2.0:
            slaving_state = SlavingState.WEAK
            slaving_active = False
        else:
            slaving_state = SlavingState.DEMOCRATIC
            slaving_active = False

        theta_mean = float(np.mean(thetas))
        theta_tilde = thetas - theta_mean
        V_slow = V_all[:, slow_indices]
        xi_slow = V_slow.T @ theta_tilde
        theta_reduced = V_slow @ xi_slow + theta_mean

        V_normal = V_all[:, [k for k in range(N) if k != rot_idx]]
        xi_normal = V_normal.T @ theta_tilde
        energy_slow = float(np.sum(xi_slow**2))
        energy_total = float(np.sum(xi_normal**2))
        reduction_error = float(math.sqrt(max(0.0, 1.0 - energy_slow / max(energy_total, 1e-12))))

        order_parameters: list[OrderParameter] = []
        for i, k in enumerate(slow_indices):
            xi_k = float(xi_slow[i])
            rel_amp = float(xi_k**2 / max(energy_total, 1e-12))
            order_parameters.append(OrderParameter(mode=modes[k], coordinate_xi=xi_k, relative_amplitude=rel_amp))

        return HakenStatus(
            n_variables=N, n_modes_total=N, n_modes_rotational=1,
            n_modes_stable_slow=len(slow_indices), n_modes_stable_fast=len(fast_indices),
            n_modes_stable_intermediate=0, n_modes_unstable=0, n_modes_marginal=0,
            modes=modes, order_parameters=order_parameters,
            fast_modes=[modes[k] for k in fast_indices], intermediate_modes=[],
            tau_slow=tau_slow, tau_fast=tau_fast, separation_ratio=separation_ratio,
            slaving_state=slaving_state, slaving_active=slaving_active,
            effective_dimension=len(slow_indices), reduction_error=reduction_error,
            spectral_coordinates=[float(x) for x in xi_slow],
            reconstructed_state=[float(x) for x in theta_reduced],
            beta=beta, rotational_overlap=rot_overlap, numerical_warnings=warnings,
        )

    def _extract_variable_names(self, ovc: "OVC", cycle_variable_ids: list[str] | None) -> list[str]:
        if cycle_variable_ids is not None:
            return list(dict.fromkeys(n for n in cycle_variable_ids if ovc.get_variable(n) is not None))
        return list(ovc.get_all_variables().keys())

    def _trivial_status(self, N: int, beta: float, reason: str) -> HakenStatus:
        return HakenStatus(
            n_variables=N, n_modes_total=N, n_modes_rotational=0,
            n_modes_stable_slow=0, n_modes_stable_fast=0, n_modes_stable_intermediate=0,
            n_modes_unstable=0, n_modes_marginal=0, modes=[], order_parameters=[],
            fast_modes=[], intermediate_modes=[], tau_slow=float("nan"), tau_fast=float("nan"),
            separation_ratio=float("nan"), slaving_state=SlavingState.NOT_APPLICABLE_TRIVIAL,
            slaving_active=False, effective_dimension=0, reduction_error=float("nan"),
            spectral_coordinates=[], reconstructed_state=[], beta=beta,
            rotational_overlap=0.0, numerical_warnings=[reason],
        )

    def _build_unstable_status(self, N, beta, modes, rot_overlap, warnings, unstable_indices, stable_indices) -> HakenStatus:
        warnings.append(f"Sistema no es atractor: {len(unstable_indices)} modos inestables.")
        return HakenStatus(
            n_variables=N, n_modes_total=N, n_modes_rotational=1,
            n_modes_stable_slow=0, n_modes_stable_fast=len(stable_indices), n_modes_stable_intermediate=0,
            n_modes_unstable=len(unstable_indices), n_modes_marginal=0, modes=modes,
            order_parameters=[], fast_modes=[modes[k] for k in stable_indices], intermediate_modes=[],
            tau_slow=float("nan"), tau_fast=float("nan"), separation_ratio=float("nan"),
            slaving_state=SlavingState.NOT_APPLICABLE_UNSTABLE, slaving_active=False,
            effective_dimension=0, reduction_error=float("nan"), spectral_coordinates=[],
            reconstructed_state=[], beta=beta, rotational_overlap=rot_overlap,
            numerical_warnings=warnings,
        )

    def _build_marginal_status(self, N, beta, modes, rot_overlap, warnings, marginal_indices) -> HakenStatus:
        warnings.append(f"Bifurcación: {len(marginal_indices)} modos marginales.")
        return HakenStatus(
            n_variables=N, n_modes_total=N, n_modes_rotational=1,
            n_modes_stable_slow=0, n_modes_stable_fast=0, n_modes_stable_intermediate=0,
            n_modes_unstable=0, n_modes_marginal=len(marginal_indices), modes=modes,
            order_parameters=[], fast_modes=[], intermediate_modes=[],
            tau_slow=float("inf"), tau_fast=float("nan"), separation_ratio=float("inf"),
            slaving_state=SlavingState.NOT_APPLICABLE_MARGINAL, slaving_active=False,
            effective_dimension=len(marginal_indices), reduction_error=float("nan"),
            spectral_coordinates=[], reconstructed_state=[], beta=beta,
            rotational_overlap=rot_overlap, numerical_warnings=warnings,
        )

    def _build_democratic_status(self, N, beta, modes, rot_overlap, warnings, stable_indices, reason) -> HakenStatus:
        warnings.append(reason)
        for k in stable_indices:
            modes[k].mode_type = ModeType.STABLE_INTERMEDIATE
        return HakenStatus(
            n_variables=N, n_modes_total=N, n_modes_rotational=1,
            n_modes_stable_slow=0, n_modes_stable_fast=0, n_modes_stable_intermediate=len(stable_indices),
            n_modes_unstable=0, n_modes_marginal=0, modes=modes,
            order_parameters=[], fast_modes=[], intermediate_modes=[modes[k] for k in stable_indices],
            tau_slow=float("nan"), tau_fast=float("nan"), separation_ratio=1.0,
            slaving_state=SlavingState.DEMOCRATIC, slaving_active=False,
            effective_dimension=0, reduction_error=float("nan"), spectral_coordinates=[],
            reconstructed_state=[], beta=beta, rotational_overlap=rot_overlap,
            numerical_warnings=warnings,
        )
