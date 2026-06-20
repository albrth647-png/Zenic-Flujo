"""
ORBITAL — Modelos de datos (dataclasses)
=========================================

Define las estructuras de datos fundamentales del motor ORBITAL.
Cada modelo representa un concepto del paradigma circular determinista.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

# ── Constantes ──────────────────────────────────────────────

TWO_PI = 2 * math.pi
DEFAULT_AMPLITUDE = 1.0
DEFAULT_VELOCITY = 0.1  # radianes por tick
DEFAULT_THRESHOLD = 0.5  # umbral RCC
DEFAULT_EPSILON = 1e-6  # precision COD
MAX_COD_ITERATIONS = 1000
RETROFEEDBACK_DAMPING = 0.3  # factor de amortiguacion retroalimentacion


# ── VariableOrbital ────────────────────────────────────────


@dataclass
class VariableOrbital:
    """
    Variable Orbital (OVC): La unidad fundamental del motor ORBITAL.

    A diferencia de una variable lineal (valor estatico), una VariableOrbital
    tiene fase theta, amplitud A y velocidad orbital omega. Esto permite que
    la variable orbite alrededor de otras variables mutuamente.

    Atributos:
        id: Identificador unico
        name: Nombre de la variable (ej: "Demanda", "Precio")
        theta: Fase actual en radianes [0, 2pi)
        amplitude: Amplitud (magnitud de la variable) > 0
        velocity: Velocidad orbital en radianes/tick
        orbit_group: Grupo orbital al que pertenece
        metadata: Datos adicionales arbitrarios
    """

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    theta: float = 0.0
    amplitude: float = DEFAULT_AMPLITUDE
    velocity: float = DEFAULT_VELOCITY
    orbit_group: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Normalizar theta a [0, 2pi)
        self.theta = self.theta % TWO_PI
        # Amplitud siempre positiva
        if self.amplitude <= 0:
            self.amplitude = abs(self.amplitude) or DEFAULT_AMPLITUDE

    @property
    def value(self) -> float:
        """Valor instantaneo de la variable orbital: A * cos(theta)."""
        return self.amplitude * math.cos(self.theta)

    @property
    def phase_degrees(self) -> float:
        """Fase en grados [0, 360)."""
        return math.degrees(self.theta) % 360

    def advance(self, dt: float = 1.0) -> None:
        """Avanza la fase orbital: theta += omega * dt."""
        self.theta = (self.theta + self.velocity * dt) % TWO_PI

    def apply_tension(self, tension: float, dt: float = 1.0) -> None:
        """
        Aplica tension orbital a la fase.
        tension > 0: acelera (avanza fase)
        tension < 0: desacelera (retrocede fase)
        Usa tanh para mantener la modulacion acotada en [-1, 1].
        """
        modulation = math.tanh(tension)
        self.theta = (self.theta + modulation * self.velocity * dt) % TWO_PI

    def retrofeed(self, output_value: float, damping: float = RETROFEEDBACK_DAMPING) -> None:
        """
        Retroalimentacion: el output del sistema modifica esta variable.
        damping controla cuanto afecta la retroalimentacion (0=ninguno, 1=total).
        """
        delta = damping * output_value
        self.theta = (self.theta + delta) % TWO_PI

    def distance_to(self, other: VariableOrbital) -> float:
        """
        Distancia angular minima entre dos variables orbitales.
        Retorna valor en [0, pi].
        """
        diff = abs(self.theta - other.theta) % TWO_PI
        return min(diff, TWO_PI - diff)

    def phase_alignment(self, other: VariableOrbital) -> float:
        """
        Alineacion de fase entre dos variables: cos(theta_i - theta_j).
        Retorna [-1, 1]:
         1 = fases perfectamente alineadas
        -1 = fases opuestas (anti-alineadas)
         0 = fases ortogonales
        """
        return math.cos(self.theta - other.theta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "theta": self.theta,
            "amplitude": self.amplitude,
            "velocity": self.velocity,
            "value": self.value,
            "phase_degrees": self.phase_degrees,
            "orbit_group": self.orbit_group,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VariableOrbital:
        return cls(
            id=data.get("id", str(uuid4())),
            name=data.get("name", ""),
            theta=data.get("theta", 0.0),
            amplitude=data.get("amplitude", DEFAULT_AMPLITUDE),
            velocity=data.get("velocity", DEFAULT_VELOCITY),
            orbit_group=data.get("orbit_group", "default"),
            metadata=data.get("metadata", {}),
        )


# ── CicloOrbital ───────────────────────────────────────────


@dataclass
class CicloOrbital:
    """
    Ciclo Orbital: Conjunto de variables orbitales que forman un ciclo cerrado.

    Define un ciclo donde las variables orbitan mutuamente y la salida
    retroalimenta la entrada, cerrando el bucle determinista.

    Atributos:
        id: Identificador unico
        name: Nombre del ciclo (ej: "Ciclo Economico Orbital")
        variable_ids: IDs de las variables que forman el ciclo
        threshold: Umbral de resonancia RCC
        status: Estado del ciclo (active, collapsed, diverged)
        resonance_level: Nivel actual de resonancia [0, 1]
    """

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    variable_ids: list[str] = field(default_factory=list)
    threshold: float = DEFAULT_THRESHOLD
    status: str = "active"
    resonance_level: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "variable_ids": self.variable_ids,
            "threshold": self.threshold,
            "status": self.status,
            "resonance_level": self.resonance_level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CicloOrbital:
        return cls(
            id=data.get("id", str(uuid4())),
            name=data.get("name", ""),
            variable_ids=data.get("variable_ids", []),
            threshold=data.get("threshold", DEFAULT_THRESHOLD),
            status=data.get("status", "active"),
            resonance_level=data.get("resonance_level", 0.0),
        )


# ── TORResult ──────────────────────────────────────────────


@dataclass
class TORResult:
    """
    Resultado del calculo TOR entre dos variables.

    TOR(i,j) = Ai * Aj * cos(theta_i - theta_j)

    Esta fuerza orbital reciproca es computable, determinista y simetrica:
    TOR(i,j) = TOR(j,i).
    """

    variable_i: str = ""
    variable_j: str = ""
    tor_value: float = 0.0
    phase_diff: float = 0.0
    alignment: float = 0.0  # cos(theta_i - theta_j)
    is_resonant: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable_i": self.variable_i,
            "variable_j": self.variable_j,
            "tor_value": self.tor_value,
            "phase_diff": self.phase_diff,
            "alignment": self.alignment,
            "is_resonant": self.is_resonant,
        }


# ── RCCResult ──────────────────────────────────────────────


@dataclass
class RCCResult:
    """
    Resultado de la deteccion de Resonancia de Ciclo Cerrado.

    RCC se activa cuando la tension orbital promedio de un ciclo cerrado
    supera el umbral. Esto indica resonancia determinista: las variables
    estan sincronizadas orbitalmente y se puede predecir multimodalmente.
    """

    cycle_id: str = ""
    total_tension: float = 0.0
    average_tension: float = 0.0
    max_tension: float = 0.0
    min_tension: float = 0.0
    is_resonant: bool = False
    resonant_pairs: list[TORResult] = field(default_factory=list)
    resonance_strength: float = 0.0  # [0, 1]

    def to_dict(self) -> dict[str, Any]:
        # Fix Sprint 3 bug #44: total_tension serializaba average_tension por error.
        return {
            "cycle_id": self.cycle_id,
            "total_tension": self.total_tension,
            "average_tension": self.average_tension,
            "max_tension": self.max_tension,
            "min_tension": self.min_tension,
            "is_resonant": self.is_resonant,
            "resonant_pairs": [p.to_dict() for p in self.resonant_pairs],
            "resonance_strength": self.resonance_strength,
        }


# ── CODResult ──────────────────────────────────────────────


@dataclass
class CODResult:
    """
    Resultado del Colapso Orbital Determinista.

    El COD garantiza convergencia usando:
    1. Activacion tanh para mantener el sistema acotado
    2. Teorema del punto fijo de Brouwer: mapeo continuo en compacto convexo → punto fijo existe
    3. Iteracion hasta |theta_nuevo - theta_viejo| < epsilon
    4. Funcion de Lyapunov V(theta) = -Sum TOR(i,j) (Mejora 1, Hopfield 1982)
    5. Free Energy Principle F(theta) = U - S (Mejora 2, Friston 2010)

    El colapso NO es probabilidad: es el ESTADO DETERMINISTA del sistema circular.
    """

    cycle_id: str = ""
    converged: bool = False
    iterations: int = 0
    final_phases: dict[str, float] = field(default_factory=dict)
    final_values: dict[str, float] = field(default_factory=dict)
    convergence_delta: float = 0.0
    steady_state_reached: bool = False
    # Mejora 1: Lyapunov tracking (Hopfield 1982)
    lyapunov_V_initial: float = 0.0
    lyapunov_V_final: float = 0.0
    lyapunov_delta_V: float = 0.0
    lyapunov_stable: bool = False  # True si V monótona decreciente
    lyapunov_violations: int = 0  # Número de iteraciones donde V aumentó
    # Mejora 2: Friston Free Energy Principle (Friston 2010)
    fep_F_initial: float = 0.0
    fep_F_final: float = 0.0
    fep_delta_F: float = 0.0
    fep_energy_initial: float = 0.0  # U(θ) = -Σ TOR / N
    fep_energy_final: float = 0.0
    fep_entropy_initial: float = 0.0  # S(θ) = -Σ p ln p
    fep_entropy_final: float = 0.0
    fep_stable: bool = False  # True si F monótona decreciente
    fep_violations: int = 0
    # Mejora 3: Conley Index classification (Conley 1978, Hartman-Grobman 1960)
    conley_type: str = "trivial"  # attractor/repeller/saddle/center/degenerate/trivial
    conley_morse_index: int = 0  # u = número de direcciones inestables
    conley_step_safe: bool = False  # True si β·μ_max < 2
    conley_recommended_max_beta: float = 0.0
    conley_is_hyperbolic: bool = False
    conley_stable_count: int = 0
    conley_unstable_count: int = 0
    conley_marginal_count: int = 0
    conley_beta: float = 0.0
    # Mejora 4: Haken Synergetics (Haken 1976)
    haken_slaving_active: bool = False
    haken_separation_ratio: float = 0.0
    haken_n_order_parameters: int = 0
    haken_effective_dimension: int = 0
    haken_reduction_error: float = 0.0
    haken_slaving_state: str = "not_applicable_trivial"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "converged": self.converged,
            "iterations": self.iterations,
            "final_phases": self.final_phases,
            "final_values": self.final_values,
            "convergence_delta": self.convergence_delta,
            "steady_state_reached": self.steady_state_reached,
            "lyapunov_V_initial": round(self.lyapunov_V_initial, 8),
            "lyapunov_V_final": round(self.lyapunov_V_final, 8),
            "lyapunov_delta_V": round(self.lyapunov_delta_V, 8),
            "lyapunov_stable": self.lyapunov_stable,
            "lyapunov_violations": self.lyapunov_violations,
            "fep_F_initial": round(self.fep_F_initial, 8),
            "fep_F_final": round(self.fep_F_final, 8),
            "fep_delta_F": round(self.fep_delta_F, 8),
            "fep_energy_initial": round(self.fep_energy_initial, 8),
            "fep_energy_final": round(self.fep_energy_final, 8),
            "fep_entropy_initial": round(self.fep_entropy_initial, 8),
            "fep_entropy_final": round(self.fep_entropy_final, 8),
            "fep_stable": self.fep_stable,
            "fep_violations": self.fep_violations,
            "conley_type": self.conley_type,
            "conley_morse_index": self.conley_morse_index,
            "conley_step_safe": self.conley_step_safe,
            "conley_recommended_max_beta": round(self.conley_recommended_max_beta, 8),
            "conley_is_hyperbolic": self.conley_is_hyperbolic,
            "conley_stable_count": self.conley_stable_count,
            "conley_unstable_count": self.conley_unstable_count,
            "conley_marginal_count": self.conley_marginal_count,
            "conley_beta": round(self.conley_beta, 8),
            "haken_slaving_active": self.haken_slaving_active,
            "haken_separation_ratio": round(self.haken_separation_ratio, 8) if self.haken_separation_ratio == self.haken_separation_ratio else None,
            "haken_n_order_parameters": self.haken_n_order_parameters,
            "haken_effective_dimension": self.haken_effective_dimension,
            "haken_reduction_error": round(self.haken_reduction_error, 8) if self.haken_reduction_error == self.haken_reduction_error else None,
            "haken_slaving_state": self.haken_slaving_state,
        }


# ── EspectroEstado ─────────────────────────────────────────


@dataclass
class EspectroEstado:
    """
    Estado del Espectro Orbital: salida multimodal determinista.

    El espectro NO es probabilidad: es el conjunto de ESTADOS del sistema
    circular despues del colapso orbital. Cada modo representa un estado
    estable posible del sistema.

    Atributos:
        modes: Lista de estados deterministas (cada modo es un dict de {var_name: value})
        primary_mode: Indice del modo primario (mayor tension)
        retrofeedback: Valor que retroalimenta al input del sistema
    """

    modes: list[dict[str, float]] = field(default_factory=list)
    primary_mode: int = 0
    retrofeedback: dict[str, float] = field(default_factory=dict)
    tick: int = 0

    @property
    def primary(self) -> dict[str, float]:
        """Estado determinista primario del espectro."""
        if not self.modes:
            return {}
        idx = min(self.primary_mode, len(self.modes) - 1)
        return self.modes[idx]

    def to_dict(self) -> dict[str, Any]:
        return {
            "modes": self.modes,
            "primary_mode": self.primary_mode,
            "primary": self.primary,
            "retrofeedback": self.retrofeedback,
            "tick": self.tick,
        }


# ── OrbitalResult ──────────────────────────────────────────


@dataclass
class OrbitalResult:
    """
    Resultado completo de una ejecucion del motor ORBITAL.

    Contiene el estado completo del sistema despues de un tick orbital:
    - OVC: estado actual de todas las variables orbitales
    - TOR: matriz de tensiones entre todas las parejas
    - RCC: resultado de resonancia por cada ciclo
    - COD: resultado del colapso determinista
    - Espectro: salida multimodal con retroalimentacion
    """

    tick: int = 0
    variables: dict[str, VariableOrbital] = field(default_factory=dict)
    tor_results: list[TORResult] = field(default_factory=list)
    rcc_results: list[RCCResult] = field(default_factory=list)
    cod_results: list[CODResult] = field(default_factory=list)
    espectro: EspectroEstado = field(default_factory=EspectroEstado)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "variables": {k: v.to_dict() for k, v in self.variables.items()},
            "tor_results": [t.to_dict() for t in self.tor_results],
            "rcc_results": [r.to_dict() for r in self.rcc_results],
            "cod_results": [c.to_dict() for c in self.cod_results],
            "espectro": self.espectro.to_dict(),
            "duration_ms": self.duration_ms,
        }
