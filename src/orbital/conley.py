# ruff: noqa: RUF002 — docstrings y comentarios matemáticos usan caracteres griegos intencionalmente
"""
ORBITAL — Conley Index Classifier (Mejora 3)
==============================================

Clasifica topológicamente los puntos fijos del COD usando el índice de Conley
en su versión linealizada (Jacobiano del mapeo F).

Fundamento matemático:
- Hartman-Grobman (1960): el mapeo no-lineal F es topológicamente conjugado
  a su linealización DF(θ*) en un punto fijo hiperbólico θ*.
- Conley (1978, Theorem 4.2): el índice de Conley de un punto fijo hiperbólico
  con u direcciones inestables es Σ^u (la u-esfera suspensionada).
- Misiurewicz-Sędziwy (1985): análogo discreto del teorema de Conley.

Marco:
- El COD itera F(θ) = θ - β·∇V(θ) hasta convergencia a θ*.
- V(θ) = -Σ_{i<j} A_i·A_j·cos(θ_i - θ_j) (Mejora 1).
- ∇V(θ)_i = Σ_j A_i·A_j·sin(θ_i - θ_j).
- H(V) = L (Laplaciano del grafo TOR con pesos w_ij = TOR(i,j)).
- Jacobiano del mapeo: J = I - β·L, donde β = convergence_scale·dt·relaxation/norm.

Simetría S^1 (rotacional):
- V es invariante bajo rotación global: V(θ + c·1) = V(θ).
- Esto implica que L·(1,...,1)^T = 0 siempre, así que λ_1 = 1 de J
  (autovalor unitario en la dirección rotacional).
- Esta dirección debe EXCLUIRSE del criterio de clasificación.

Clasificación (en el espacio cociente T^N/S^1):
- attractor: todas las direcciones no-rotacionales son estables (|λ| < 1)
- repeller: todas son inestables (|λ| > 1)
- saddle: mezcla de estables e inestables (sin marginales)
- center: existe |λ| = 1 en dirección no-rotacional (caso crítico)
- degenerate: todas son marginales (Hessiano nulo en el cociente)

Referencias:
- Conley, C. (1978). "Isolated Invariant Sets and the Morse Index". CBMS 38.
- Hartman, P. (1960). "A lemma in the theory of structural stability". Proc. AMS.
- Hirsch, Pugh, Shub (1977). "Invariant Manifolds". Springer LNM 583.
- Misiurewicz, M., Sędziwy, S. (1985). "The Conley index for maps". TAMS.

Documento de diseño: docs/orbital-conley-index-design.md
"""
from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from src.core.logging import setup_logging

if TYPE_CHECKING:
    from src.orbital.ovc import OVC
    from src.orbital.tor import TOR

logger = setup_logging(__name__)


# Tolerancia para considerar un autovalor como "marginal" (|λ| ≈ 1).
# Autovalores en [1 - ε, 1 + ε] se consideran marginales.
CONLEY_MARGINAL_TOLERANCE: float = 1e-6

# Tolerancia para detectar el autovalor rotacional λ = 1 exacto.
# Se busca el autovalor más cercano a 1 dentro de esta tolerancia.
CONLEY_ROTATIONAL_TOLERANCE: float = 1e-8


class ConleyType(enum.StrEnum):
    """Clasificación topológica del punto fijo del COD."""

    ATTRACTOR = "attractor"
    """Todas las perturbaciones decaen (mód. rotación). Índice de Conley: Σ^0 = S^0."""

    REPELLER = "repeller"
    """Todas las perturbaciones crecen. Índice de Conley: Σ^(N-1)."""

    SADDLE = "saddle"
    """Estable en s direcciones, inestable en u. Índice de Conley: Σ^u."""

    CENTER = "center"
    """Caso crítico (no-hiperbólico) con direcciones marginales no rotacionales."""

    DEGENERATE = "degenerate"
    """Hessiano nulo en el cociente; no hay dinámica no-rotacional."""

    TRIVIAL = "trivial"
    """N ≤ 1: sin parejas, sin dinámica."""


@dataclass
class ConleySpectrum:
    """Espectro del Jacobiano J = I - β·L en el punto fijo.

    Atributos:
        eigenvalues: autovalores de J (todos reales por simetría de L).
        eigenvalues_laplacian: autovalores de L (= Hessiano de V).
        rotational_idx: índice del autovalor rotacional (λ = 1 de J, μ = 0 de L).
        stable_count: número de autovalores no-rotacionales con |λ| < 1.
        unstable_count: número de autovalores no-rotacionales con |λ| > 1.
        marginal_count: número de autovalores no-rotacionales con |λ| ≈ 1.
    """

    eigenvalues: list[float] = field(default_factory=list)
    eigenvalues_laplacian: list[float] = field(default_factory=list)
    rotational_idx: int = -1
    stable_count: int = 0
    unstable_count: int = 0
    marginal_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "eigenvalues": [round(e, 8) for e in self.eigenvalues],
            "eigenvalues_laplacian": [round(e, 8) for e in self.eigenvalues_laplacian],
            "rotational_idx": self.rotational_idx,
            "stable_count": self.stable_count,
            "unstable_count": self.unstable_count,
            "marginal_count": self.marginal_count,
        }


@dataclass
class ConleyStatus:
    """Estado del clasificador Conley tras analizar un punto fijo.

    Atributos:
        conley_type: tipo topológico (attractor/repeller/saddle/center/degenerate/trivial).
        morse_index: u (número de direcciones inestables). Convenio Conley.
        spectrum: espectro completo del Jacobiano.
        beta: parámetro β = convergence_scale · dt · relaxation / norm usado.
        step_safe: True si β·μ_max(L) < 2 (condición de estabilidad del paso).
        recommended_max_beta: β máximo recomendado = 2 / max(μ_k > 0).
            Vale float('inf') si no hay autovalores positivos (repeller puro).
            to_dict() lo serializa como -1.0 para ser JSON-safe.
        is_hyperbolic: True si ningún autovalor no-rotacional tiene |λ| ≈ 1.
        n_variables: número de variables en el ciclo.
    """

    conley_type: ConleyType = ConleyType.TRIVIAL
    morse_index: int = 0
    spectrum: ConleySpectrum = field(default_factory=ConleySpectrum)
    beta: float = 0.0
    step_safe: bool = False
    recommended_max_beta: float = 0.0
    is_hyperbolic: bool = False
    n_variables: int = 0

    def to_dict(self) -> dict[str, object]:
        # JSON-safe: convertir inf a -1.0 (sentinel "no aplicable")
        rmb = self.recommended_max_beta
        if rmb == float("inf") or math.isinf(rmb):
            rmb = -1.0
        return {
            "conley_type": self.conley_type.value,
            "morse_index": self.morse_index,
            "spectrum": self.spectrum.to_dict(),
            "beta": round(self.beta, 8),
            "step_safe": self.step_safe,
            "recommended_max_beta": round(rmb, 8),
            "is_hyperbolic": self.is_hyperbolic,
            "n_variables": self.n_variables,
        }


class ConleyClassifier:
    """
    Clasifica puntos fijos del COD usando el índice de Conley linealizado.

    Algoritmo:
    1. Construir el Laplaciano L del grafo TOR (pesos w_ij = TOR(i,j)).
       L = H(V) (Hessiano de V, verificado con sympy).
    2. Calcular autovalores de L con numpy.linalg.eigvalsh (L es simétrica real).
    3. Identificar el autovalor rotacional μ = 0 (siempre existe por simetría S^1).
    4. Calcular autovalores del Jacobiano: λ_k = 1 - β·μ_k.
    5. Excluir el autovalor rotacional (λ = 1).
    6. Clasificar según |λ_k| de los autovalores no-rotacionales:
       - attractor: todos |λ| < 1
       - repeller: todos |λ| > 1
       - saddle: mezcla
       - center: alguno |λ| ≈ 1 (no rotacional)
       - degenerate: Hessiano nulo en el cociente
    7. Calcular β máximo recomendado (cota de estabilidad del paso).
    """

    def __init__(
        self,
        marginal_tolerance: float = CONLEY_MARGINAL_TOLERANCE,
        rotational_tolerance: float = CONLEY_ROTATIONAL_TOLERANCE,
    ) -> None:
        """Inicializa el clasificador.

        Args:
            marginal_tolerance: tolerancia para considerar |λ| ≈ 1 (marginal).
            rotational_tolerance: tolerancia para detectar el autovalor rotacional.
        """
        self._marginal_tol = marginal_tolerance
        self._rotational_tol = rotational_tolerance

    def build_laplacian(
        self,
        ovc: OVC,
        tor: TOR,
        cycle_variable_ids: list[str] | None = None,
    ) -> np.ndarray:
        """
        Construye el Laplaciano L del grafo TOR (pesos w_ij = TOR(i,j)).

        L_ii = Σ_{k≠i} w_ik = TOR_i (tensión neta sobre i)
        L_ij = -w_ij = -TOR(i,j) para i ≠ j

        Este L es exactamente el Hessiano de V (verificado con sympy):
        H(V)_ii = Σ_j A_i·A_j·cos(θ_i - θ_j) = +TOR_i
        H(V)_ij = -A_i·A_j·cos(θ_i - θ_j) = -TOR(i,j) para i ≠ j

        Args:
            ovc: Instancia de OVC.
            tor: Instancia de TOR.
            cycle_variable_ids: Restringir a variables del ciclo.

        Returns:
            Matriz L de dimensión N×N (numpy array simétrico real).  # noqa: RUF002
        """
        # Seleccionar variables (deduplicando IDs para evitar L malformado)
        if cycle_variable_ids is not None:
            # Usar dict.fromkeys para preservar orden y eliminar duplicados
            var_names = list(dict.fromkeys(
                name for name in cycle_variable_ids
                if ovc.get_variable(name) is not None
            ))
        else:
            var_names = list(ovc.get_all_variables().keys())

        N = len(var_names)
        if N == 0:
            return np.zeros((0, 0), dtype=np.float64)

        # Mapeo nombre → índice
        name_to_idx = {name: i for i, name in enumerate(var_names)}

        # Construir L como matriz de ceros
        L = np.zeros((N, N), dtype=np.float64)

        # Obtener tensiones del ciclo (o globales)
        if cycle_variable_ids is not None:
            tor_results = tor.calculate_for_cycle(cycle_variable_ids)
        else:
            tor_results = tor.calculate_matrix()

        # Llenar L
        for result in tor_results:
            i_name = result.variable_i
            j_name = result.variable_j
            if i_name not in name_to_idx or j_name not in name_to_idx:
                continue
            i = name_to_idx[i_name]
            j = name_to_idx[j_name]
            w_ij = result.tor_value  # = A_i·A_j·cos(θ_i - θ_j)

            # Off-diagonal: L_ij = -w_ij
            L[i, j] = -w_ij
            L[j, i] = -w_ij  # simétrico

            # Diagonal: L_ii += w_ij (acumula tensión neta)
            L[i, i] += w_ij
            L[j, j] += w_ij

        # Simetrización numérica defensiva (evita drift por redondeo flotante)
        L = 0.5 * (L + L.T)

        return L

    def classify(
        self,
        ovc: OVC,
        tor: TOR,
        beta: float,
        cycle_variable_ids: list[str] | None = None,
    ) -> ConleyStatus:
        """
        Clasifica el punto fijo actual del COD.

        Args:
            ovc: Instancia de OVC con variables en el estado actual.
            tor: Instancia de TOR.
            beta: parámetro β = convergence_scale · dt · relaxation / norm
                  usado por el COD en su iteración.
            cycle_variable_ids: Restringir a variables del ciclo.

        Returns:
            ConleyStatus con la clasificación topológica.
        """
        # Seleccionar variables (deduplicando IDs)
        if cycle_variable_ids is not None:
            var_names = list(dict.fromkeys(
                name for name in cycle_variable_ids
                if ovc.get_variable(name) is not None
            ))
        else:
            var_names = list(ovc.get_all_variables().keys())
        N = len(var_names)

        # Edge cases
        if N == 0:
            return ConleyStatus(
                conley_type=ConleyType.TRIVIAL,
                morse_index=0,
                beta=beta,
                n_variables=0,
            )
        if N == 1:
            # Sin parejas → sin dinámica → degenerate (alineado con diseño sección 5.3)
            return ConleyStatus(
                conley_type=ConleyType.DEGENERATE,
                morse_index=0,
                beta=beta,
                n_variables=1,
                is_hyperbolic=False,
            )

        # 1. Construir Laplaciano
        L = self.build_laplacian(ovc, tor, cycle_variable_ids)

        # 2. Calcular autovalores de L (todos reales por simetría)
        try:
            eigenvalues_L = np.linalg.eigvalsh(L).tolist()
        except np.linalg.LinAlgError as exc:
            logger.warning(f"Conley: eigvalsh falló: {exc}")
            return ConleyStatus(
                conley_type=ConleyType.DEGENERATE,
                morse_index=0,
                beta=beta,
                n_variables=N,
                is_hyperbolic=False,
            )

        # Sanitizar NaN/Inf
        if any(math.isnan(x) or math.isinf(x) for x in eigenvalues_L):
            logger.warning(f"Conley: autovalores no finitos: {eigenvalues_L}")
            return ConleyStatus(
                conley_type=ConleyType.DEGENERATE,
                morse_index=0,
                beta=beta,
                n_variables=N,
                is_hyperbolic=False,
            )

        # 3. Identificar el autovalor rotacional (μ ≈ 0, siempre existe por simetría S^1)
        rotational_idx = -1
        min_abs = float("inf")
        for i, mu in enumerate(eigenvalues_L):
            if abs(mu) < min_abs:
                min_abs = abs(mu)
                rotational_idx = i
        # Advertir si no se encontró un autovalor cercano a 0
        if min_abs > self._rotational_tol:
            logger.warning(
                f"Conley: no se encontró autovalor rotacional ≈ 0 "
                f"(mínimo |μ| = {min_abs:.2e}). Usando índice {rotational_idx}."
            )

        # 4. Calcular autovalores del Jacobiano: λ_k = 1 - β·μ_k
        eigenvalues_J = [1.0 - beta * mu for mu in eigenvalues_L]

        # 5. Clasificar considerando solo autovalores no-rotacionales
        stable_count = 0
        unstable_count = 0
        marginal_count = 0
        for i, lam in enumerate(eigenvalues_J):
            if i == rotational_idx:
                continue  # excluir dirección rotacional
            abs_lam = abs(lam)
            if abs(abs_lam - 1.0) < self._marginal_tol:
                marginal_count += 1
            elif abs_lam < 1.0:
                stable_count += 1
            else:  # abs_lam > 1.0
                unstable_count += 1

        # 6. Determinar tipo
        conley_type = self._classify_type(
            n_non_rotational=N - 1,
            stable=stable_count,
            unstable=unstable_count,
            marginal=marginal_count,
        )

        # 7. Verificar hiperbolicidad
        is_hyperbolic = marginal_count == 0

        # 8. Calcular β máximo recomendado y step_safe (alineado con diseño)
        # Tomar el autovalor máximo EXCLUYENDO el rotacional
        non_rotational_eigenvalues = [
            mu for i, mu in enumerate(eigenvalues_L) if i != rotational_idx
        ]
        if non_rotational_eigenvalues:
            mu_max = max(non_rotational_eigenvalues)
            if mu_max > self._rotational_tol:
                recommended_max_beta = 2.0 / mu_max
                # step_safe: β·μ_max < 2 con buffer de marginal_tol
                step_safe = (beta * mu_max) < (2.0 - self._marginal_tol)
            else:
                # Todos los autovalores no-rotacionales son ≤ 0 (repeller/saddle puro)
                # No hay cota de paso aplicable; el sistema es intrínsecamente inestable
                recommended_max_beta = float("inf")
                step_safe = False
        else:
            recommended_max_beta = float("inf")
            step_safe = False

        spectrum = ConleySpectrum(
            eigenvalues=eigenvalues_J,
            eigenvalues_laplacian=eigenvalues_L,
            rotational_idx=rotational_idx,
            stable_count=stable_count,
            unstable_count=unstable_count,
            marginal_count=marginal_count,
        )

        return ConleyStatus(
            conley_type=conley_type,
            morse_index=unstable_count,
            spectrum=spectrum,
            beta=beta,
            step_safe=step_safe,
            recommended_max_beta=recommended_max_beta,
            is_hyperbolic=is_hyperbolic,
            n_variables=N,
        )

    def _classify_type(
        self,
        n_non_rotational: int,
        stable: int,
        unstable: int,
        marginal: int,
    ) -> ConleyType:
        """Aplica el criterio de clasificación de la tabla 5.2 del diseño."""
        if n_non_rotational == 0:
            return ConleyType.DEGENERATE
        if marginal == n_non_rotational:
            return ConleyType.DEGENERATE
        if marginal > 0:
            return ConleyType.CENTER
        if stable == n_non_rotational:
            return ConleyType.ATTRACTOR
        if unstable == n_non_rotational:
            return ConleyType.REPELLER
        # Mezcla sin marginales
        return ConleyType.SADDLE

    def compute_beta(
        self,
        convergence_scale: float,
        dt: float,
        relaxation: float,
        amplitude_norm: float,
    ) -> float:
        """
        Calcula β = convergence_scale · dt · relaxation / amplitude_norm.

        Este es el β efectivo usado por el COD en su iteración de descenso
        por gradiente de V. Se requiere para construir el Jacobiano J = I - β·L.
        """
        if amplitude_norm <= 0:
            return 0.0
        return convergence_scale * dt * relaxation / amplitude_norm
