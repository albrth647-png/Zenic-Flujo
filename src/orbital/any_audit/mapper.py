"""
ORBITAL — Mapper: antipatrones Any → variables orbitales
========================================================

Convierte el inventario de ocurrencias `Any` (de any_audit.py) en
VariablesOrbitales y CiclosOrbitales que el OrbitalEngine puede procesar.

Mapeo:

  Módulos (src/connectors, src/api_v2, ...) → VariableOrbital
    - name = "module:<nombre>"
    - θ = fase de deuda = 2π * (deuda_real / max_deuda_entre_modulos)
      → módulos con más deuda están en fases "adelantadas"
    - A = amplitud = sqrt(deuda_real + 1) (escala logarítmica suave)
    - ω = velocidad = 0.05 (constante; el baseline lo ajusta)
    - orbit_group = "modules"
    - metadata = {deuda_real, justificados, total, debt_ratio}

  Antipatrones (bare_dict, param_annotation, ...) → VariableOrbital
    - name = "antipattern:<nombre>"
    - θ = 2π * (count / total_antipatrones)
    - A = sqrt(count + 1)
    - ω = 0.08
    - orbit_group = "antipatterns"
    - metadata = {count, description}

  Ciclos orbitales (correlaciones de deuda):
    - connectors ↔ sdk (conectores usan SDK)
    - api_v2 ↔ mobile (APIs comparten tipos)
    - hat ↔ workflow (orquestación de workflows)
    - agents ↔ sdk/decorators (wrappers)
  Cada ciclo tiene threshold = 0.4 (resonancia significativa)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from src.orbital.models import DEFAULT_THRESHOLD, CicloOrbital, VariableOrbital


# ── Ciclos de correlación de deuda ────────────────────────────────────────────
# Grupos de módulos que típicamente comparten deuda (uno afecta al otro).
DEBT_CORRELATION_CYCLES: dict[str, list[str]] = {
    "connectors_sdk": ["src/connectors", "src/sdk", "src/sdk/base"],
    "api_mobile": ["src/api_v2", "src/api_v2/routers", "src/mobile"],
    "hat_orchestration": ["src/hat/level1_orchestrator", "src/hat/level5_tools", "src/workflow"],
    "agents_wrappers": ["src/agents", "src/sdk/decorators"],
    "data_persistence": ["src/data", "src/tenant", "src/workflow"],
    "security_compliance": ["src/security", "src/compliance", "src/tenant"],
}

# Velocidades orbitales por grupo (rad/tick)
MODULE_VELOCITY = 0.05
ANTIPATTERN_VELOCITY = 0.08


@dataclass(frozen=True)
class ModuleStats:
    """Estadísticas de deuda de un módulo."""

    name: str
    total: int
    legitimate_imports: int
    justified: int
    real_debt: int

    @property
    def debt_ratio(self) -> float:
        """Proporción de deuda real sobre total (0-1)."""
        return self.real_debt / self.total if self.total > 0 else 0.0


@dataclass(frozen=True)
class AntipatternStats:
    """Estadísticas de un antipatrón."""

    name: str
    count: int
    description: str


class AnyAuditMapper:
    """Convierte estadísticas de auditoría Any en variables y ciclos orbitales."""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self._threshold = threshold

    # ── Módulos → VariablesOrbitales ──────────────────────────

    def module_to_variable(self, stats: ModuleStats) -> VariableOrbital:
        """Convierte estadísticas de un módulo en VariableOrbital.

        - θ: fase proporcional a la deuda real (módulos con más deuda = fase mayor)
        - A: amplitud = sqrt(max(0, deuda_real) + 1) para escalar suavemente
        - ω: velocidad fija de reducción (0.05 rad/tick)
        """
        # Clamp a 0: real_debt puede ser negativo por over-justification (legítimos+just > total)
        real_debt_clamped = max(0, stats.real_debt)

        # θ normalizado a [0, 2π) basado en deuda_real
        ratio = real_debt_clamped / stats.total if stats.total > 0 else 0.0
        theta = 2 * math.pi * math.sqrt(ratio) if ratio > 0 else 0.0

        # Amplitud: sqrt(real_debt + 1) — módulo con 0 deuda → A=1 (mínimo)
        amplitude = math.sqrt(real_debt_clamped + 1)

        return VariableOrbital(
            name=f"module:{stats.name}",
            theta=theta,
            amplitude=amplitude,
            velocity=MODULE_VELOCITY,
            orbit_group="modules",
            metadata={
                "module": stats.name,
                "total": stats.total,
                "legitimate_imports": stats.legitimate_imports,
                "justified": stats.justified,
                "real_debt": real_debt_clamped,
                "debt_ratio": stats.debt_ratio,
            },
        )

    def antipattern_to_variable(self, stats: AntipatternStats, total_antipatterns: int) -> VariableOrbital:
        """Convierte estadísticas de un antipatrón en VariableOrbital.

        - θ: fase proporcional a la frecuencia del antipatrón
        - A: amplitud = sqrt(count + 1)
        - ω: velocidad 0.08 (mayor que módulos: antipatrones evolucionan más rápido)
        """
        ratio = stats.count / total_antipatterns if total_antipatterns > 0 else 0.0
        theta = 2 * math.pi * ratio
        amplitude = math.sqrt(stats.count + 1)

        return VariableOrbital(
            name=f"antipattern:{stats.name}",
            theta=theta,
            amplitude=amplitude,
            velocity=ANTIPATTERN_VELOCITY,
            orbit_group="antipatterns",
            metadata={
                "antipattern": stats.name,
                "count": stats.count,
                "description": stats.description,
                "frequency_ratio": ratio,
            },
        )

    # ── Ciclos de correlación ─────────────────────────────────

    def get_correlation_cycles(self, existing_modules: set[str]) -> list[tuple[str, list[str]]]:
        """Retorna los ciclos de correlación aplicables a los módulos existentes.

        Filtra DEBT_CORRELATION_CYCLES para quedarse solo con los que
        tienen al menos 2 módulos presentes en existing_modules.
        """
        applicable: list[tuple[str, list[str]]] = []
        for cycle_name, modules in DEBT_CORRELATION_CYCLES.items():
            present = [m for m in modules if m in existing_modules]
            if len(present) >= 2:
                applicable.append((cycle_name, present))
        return applicable

    def build_cycle_specs(
        self, existing_modules: set[str]
    ) -> list[tuple[str, list[str], float]]:
        """Construye especificaciones de ciclos para OrbitalEngine.create_cycle.

        Returns:
            Lista de (cycle_name, variable_names, threshold)
        """
        specs: list[tuple[str, list[str], float]] = []
        for cycle_name, modules in self.get_correlation_cycles(existing_modules):
            # Nombres de variables orbitales correspondientes a cada módulo
            var_names = [f"module:{m}" for m in modules]
            specs.append((cycle_name, var_names, self._threshold))
        return specs

    # ── Cálculo de resonancia de deuda ────────────────────────

    @staticmethod
    def debt_tension(stats_a: ModuleStats, stats_b: ModuleStats) -> float:
        """Tensión de deuda entre dos módulos.

        Análoga a TOR(i,j) = A_i * A_j * cos(θ_i - θ_j):
        - A_i, A_j = sqrt(deuda_real + 1) de cada módulo
        - cos(θ_i - θ_j) = alineación de deuda (mismo ratio → resonancia)

        Interpretación:
        - Tensión alta = ambos módulos tienen deuda alta Y proporciones similares
          → refactorizarlos juntos tiene sinergia
        - Tensión baja = deuda desproporcionada → no hay correlación
        """
        a_i = math.sqrt(stats_a.real_debt + 1)
        a_j = math.sqrt(stats_b.real_debt + 1)
        # Diferencia de ratios → cos(0) = 1 (misma proporción), cos(π) = -1 (opuestos)
        delta_theta = 2 * math.pi * (stats_a.debt_ratio - stats_b.debt_ratio)
        return a_i * a_j * math.cos(delta_theta)
