"""
ORBITAL — Adapter: OrbitalAnyAuditEngine
========================================

Motor orbital de auditoría Any. Integra el sistema de antipatrones (any_audit.py)
con el OrbitalEngine para ejecutar la auditoría como un ciclo determinista circular:

    Auditoría Any → OVC → TOR → RCC → COD → Espectro → Reporte → Retro → Auditoría

Flujo:

  1. Ejecuta any_audit.py para obtener el inventario de ocurrencias.
  2. Convierte módulos y antipatrones en VariablesOrbitales vía AnyAuditMapper.
  3. Registra ciclos de correlación de deuda (connectors↔sdk, etc.).
  4. Ejecuta N ticks del OrbitalEngine.
  5. Interpreta el EspectroOrbital como reporte de auditoría orbital:
     - modes = estrategias de refactor (orden de ataque)
     - primary_mode = recomendación prioritaria
     - retrofeedback = ajuste al baseline
  6. Genera reporte markdown orbital (any_audit_orbital.md).

Este adapter NO modifica OrbitalEngine ni any_audit.py. Los envuelve.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.core.logging import setup_logging
from src.orbital.any_audit.mapper import (
    DEBT_CORRELATION_CYCLES,
    AnyAuditMapper,
    AntipatternStats,
    ModuleStats,
)
from src.orbital.engine import OrbitalEngine
from src.orbital.models import OrbitalResult

# Asegurar que scripts/any_audit está en sys.path para importar any_audit
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ANY_AUDIT_PATH = PROJECT_ROOT / "scripts" / "any_audit"
if str(ANY_AUDIT_PATH) not in sys.path:
    sys.path.insert(0, str(ANY_AUDIT_PATH))

# Import diferido para evitar circular si se invoca desde el propio any_audit
def _import_any_audit() -> Any:
    """Import diferido del módulo any_audit (script standalone)."""
    import any_audit  # type: ignore[import-not-found]
    return any_audit


logger = setup_logging(__name__)


# ── Modelos de salida ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OrbitalAuditResult:
    """Resultado de una auditoría orbital completa.

    Combina el resultado del OrbitalEngine con interpretación específica
    para el dominio de antipatrones Any.
    """

    tick: int
    total_occurrences: int
    real_debt: int
    justified: int
    legitimate_imports: int
    # Hotspots = módulos con resonancia detectada (RCC positive)
    hotspots: list[dict[str, Any]]
    # Estrategia de refactor = espectro colapsado
    refactor_strategy: list[dict[str, Any]]
    # Tensiones TOP entre módulos
    top_tensions: list[dict[str, Any]]
    # Retroalimentación al baseline (ajuste de ω)
    retrofeedback: dict[str, float]
    # Resultado orbital crudo (para inspección)
    orbital_result: OrbitalResult | None = None


# ─── Engine adapter ──────────────────────────────────────────────────────────


class OrbitalAnyAuditEngine:
    """Adapter que ejecuta la auditoría Any como ciclo orbital.

    Uso:

        from src.orbital.any_audit import OrbitalAnyAuditEngine

        engine = OrbitalAnyAuditEngine()
        result = engine.run_audit(ticks=5)
        print(f"Hotspots: {len(result.hotspots)}")
        print(f"Estrategia: {result.refactor_strategy[0]}")

    Args:
        scan_path: Directorio a escanear (default: src/)
        ticks: Número de ticks orbitales a ejecutar (default: 5)
        retrofeed_damping: Factor de retroalimentación [0,1] (default: 0.3)
    """

    def __init__(
        self,
        scan_path: Path | None = None,
        ticks: int = 5,
        retrofeed_damping: float = 0.3,
    ) -> None:
        self._scan_path = scan_path or (PROJECT_ROOT / "src")
        self._ticks = ticks
        self._retrofeed_damping = retrofeed_damping
        self._mapper = AnyAuditMapper()
        self._orbital = OrbitalEngine()
        self._last_audit_summary: dict[str, Any] | None = None

    # ── Auditoría orbital completa ────────────────────────────

    def run_audit(self, ticks: int | None = None) -> OrbitalAuditResult:
        """Ejecuta auditoría orbital completa.

        Steps:
            1. Ejecuta any_audit.py scan_project() para obtener ocurrencias.
            2. Construye VariablesOrbitales para módulos y antipatrones.
            3. Registra ciclos de correlación.
            4. Ejecuta N ticks del OrbitalEngine.
            5. Interpreta el espectro como reporte orbital.
        """
        n_ticks = ticks if ticks is not None else self._ticks

        # 1. Auditoría clásica (any_audit.py)
        any_audit = _import_any_audit()
        occurrences = any_audit.scan_project(self._scan_path)
        summary = any_audit.build_summary(occurrences)
        self._last_audit_summary = summary

        logger.info(
            "OrbitalAnyAudit: %d ocurrencias, %d deuda real, %d justificados",
            summary["total_occurrences"],
            summary["real_debt"],
            summary["justified_any"],
        )

        # 2. Mapear módulos → VariablesOrbitales
        module_stats = self._build_module_stats(summary)
        existing_modules = {s.name for s in module_stats}
        for stats in module_stats:
            var = self._mapper.module_to_variable(stats)
            # Crear en el engine (respeta exclusión de duplicados)
            if self._orbital.get_variable(var.name) is None:
                self._orbital.create_variable(
                    name=var.name,
                    theta=var.theta,
                    amplitude=var.amplitude,
                    velocity=var.velocity,
                    orbit_group=var.orbit_group,
                    metadata=var.metadata,
                )

        # 3. Mapear antipatrones → VariablesOrbitales
        antipattern_stats = self._build_antipattern_stats(summary)
        total_ap = sum(s.count for s in antipattern_stats) or 1
        for stats in antipattern_stats:
            var = self._mapper.antipattern_to_variable(stats, total_ap)
            if self._orbital.get_variable(var.name) is None:
                self._orbital.create_variable(
                    name=var.name,
                    theta=var.theta,
                    amplitude=var.amplitude,
                    velocity=var.velocity,
                    orbit_group=var.orbit_group,
                    metadata=var.metadata,
                )

        # 4. Registrar ciclos de correlación
        cycle_specs = self._mapper.build_cycle_specs(existing_modules)
        registered_cycles: list[str] = []
        for cycle_name, var_names, threshold in cycle_specs:
            try:
                self._orbital.create_cycle(cycle_name, var_names, threshold)
                registered_cycles.append(cycle_name)
            except (ValueError, KeyError) as e:
                logger.debug("Ciclo %s no registrado: %s", cycle_name, e)

        logger.info(
            "OrbitalAnyAudit: %d módulos, %d antipatrones, %d ciclos correlación",
            len(module_stats),
            len(antipattern_stats),
            len(registered_cycles),
        )

        # 5. Ejecutar ticks orbitales
        results = self._orbital.run_ticks(n_ticks, retrofeed_damping=self._retrofeed_damping)
        last_result = results[-1] if results else None

        # 6. Interpretar espectro
        return self._interpret_result(last_result, summary)

    # ── Construcción de stats desde summary ──────────────────

    @staticmethod
    def _build_module_stats(summary: dict[str, Any]) -> list[ModuleStats]:
        """Convierte summary.by_module en lista de ModuleStats."""
        stats_list: list[ModuleStats] = []
        for module_name, mod_data in summary.get("by_module", {}).items():
            total = mod_data.get("total", 0)
            legits = mod_data.get("legitimate_import_any", 0)
            # justificados en by_module incluye legitimate_imports, hay que restarlos
            justified_any = max(0, mod_data.get("justified", 0) - legits)
            real_debt = max(0, total - legits - justified_any)
            stats_list.append(
                ModuleStats(
                    name=module_name,
                    total=total,
                    legitimate_imports=legits,
                    justified=justified_any,
                    real_debt=real_debt,
                )
            )
        # Excluir módulos con 0 deuda real y 0 total (ruido)
        return [s for s in stats_list if s.total > 0]

    @staticmethod
    def _build_antipattern_stats(summary: dict[str, Any]) -> list[AntipatternStats]:
        """Convierte summary.by_antipattern en lista de AntipatternStats."""
        descriptions = summary.get("antipattern_descriptions", {})
        stats_list: list[AntipatternStats] = []
        for ap_name, count in summary.get("by_antipattern", {}).items():
            if ap_name == "legitimate_import_any":
                continue  # No es antipatrón
            stats_list.append(
                AntipatternStats(
                    name=ap_name,
                    count=count,
                    description=descriptions.get(ap_name, ""),
                )
            )
        return stats_list

    # ── Interpretación del espectro ───────────────────────────

    def _interpret_result(
        self, orbital_result: OrbitalResult | None, summary: dict[str, Any]
    ) -> OrbitalAuditResult:
        """Interpreta el resultado orbital como OrbitalAuditResult."""

        # Hotspots: ciclos RCC con resonancia positiva (resonance_strength > threshold)
        hotspots: list[dict[str, Any]] = []
        if orbital_result:
            for rcc in orbital_result.rcc_results:
                if rcc.is_resonant:
                    # Mapear ciclo → módulos involucrados
                    cycle_id = rcc.cycle_id
                    cycle_obj = self._orbital.rcc.get_cycles().get(cycle_id)
                    if cycle_obj:
                        # variable_ids contiene los nombres de variables (ej: "module:src/connectors")
                        module_names = [
                            v.replace("module:", "")
                            for v in cycle_obj.variable_ids
                            if v.startswith("module:")
                        ]
                        hotspots.append(
                            {
                                "cycle": cycle_obj.name,
                                "modules": module_names,
                                "resonance": rcc.resonance_strength,
                                "tick": orbital_result.tick,
                            }
                        )

        # Estrategia de refactor: espectro.primary_mode colapsado
        refactor_strategy: list[dict[str, Any]] = []
        if orbital_result and orbital_result.espectro.modes:
            primary = orbital_result.espectro.primary
            for var_name, value in sorted(primary.items(), key=lambda x: -abs(x[1])):
                if var_name.startswith("module:"):
                    module_name = var_name.replace("module:", "")
                    # Buscar stats del módulo
                    mod_stats = summary.get("by_module", {}).get(module_name, {})
                    # Calcular deuda real correctamente (sin doble resta de legítimos)
                    total = mod_stats.get("total", 0)
                    legits = mod_stats.get("legitimate_import_any", 0)
                    justified = mod_stats.get("justified", 0) - legits  # justificados no-legítimos
                    real_debt = max(0, total - legits - justified)
                    refactor_strategy.append(
                        {
                            "module": module_name,
                            "orbital_value": value,
                            "real_debt": real_debt,
                            "total": total,
                        }
                    )

        # Top tensiones: TOR results top 10
        top_tensions: list[dict[str, Any]] = []
        if orbital_result:
            sorted_tor = sorted(
                orbital_result.tor_results,
                key=lambda t: abs(t.tor_value),
                reverse=True,
            )
            for tor in sorted_tor[:10]:
                top_tensions.append(
                    {
                        "pair": f"{tor.variable_i} ↔ {tor.variable_j}",
                        "tension": tor.tor_value,
                    }
                )

        # Retroalimentación: ajuste sugerido al baseline
        # Módulos con real_debt > 0 → sugerir ω de reducción
        # Módulos con 0 deuda real → ω alto (ya están estables, mantener velocidad)
        retrofeedback: dict[str, float] = {}
        if orbital_result:
            for name, var in orbital_result.variables.items():
                if name.startswith("module:"):
                    real_debt = var.metadata.get("real_debt", 0)
                    module_name = name.replace("module:", "")
                    if real_debt > 0:
                        # Módulo con deuda: ω inversamente proporcional a amplitud
                        # (deuda alta → ω bajo → refactor estable)
                        suggested_omega = max(0.01, 0.1 / var.amplitude)
                    else:
                        # Módulo sin deuda: ω alto (mantener monitoreo activo)
                        suggested_omega = 0.15
                    retrofeedback[module_name] = round(suggested_omega, 4)

        return OrbitalAuditResult(
            tick=orbital_result.tick if orbital_result else 0,
            total_occurrences=summary.get("total_occurrences", 0),
            real_debt=summary.get("real_debt", 0),
            justified=summary.get("justified_any", 0),
            legitimate_imports=summary.get("legitimate_imports", 0),
            hotspots=hotspots,
            refactor_strategy=refactor_strategy,
            top_tensions=top_tensions,
            retrofeedback=retrofeedback,
            orbital_result=orbital_result,
        )

    # ── Reporte markdown orbital ──────────────────────────────

    def write_orbital_report(self, result: OrbitalAuditResult, out_path: Path) -> None:
        """Escribe reporte markdown con interpretación orbital de la auditoría."""
        lines: list[str] = []
        lines.append("# Any Audit Orbital Report — Zenic-Flujo\n")
        lines.append("Auditoría Any ejecutada como ciclo del motor Orbital.\n")
        lines.append(f"**Tick orbital final:** {result.tick}\n")
        lines.append(
            f"**Total ocurrencias:** {result.total_occurrences} | "
            f"**Deuda real:** {result.real_debt} | "
            f"**Justificados:** {result.justified} | "
            f"**Imports legítimos:** {result.legitimate_imports}\n"
        )
        lines.append("")

        # Hotspots de resonancia
        lines.append("## Hotspots de deuda (resonancia RCC)\n")
        if result.hotspots:
            lines.append("| Ciclo | Módulos | Resonancia | Tick |")
            lines.append("|-------|---------|------------|------:|")
            for h in result.hotspots:
                lines.append(
                    f"| `{h['cycle']}` | {', '.join(h['modules'])} | "
                    f"{h['resonance']:.4f} | {h['tick']} |"
                )
        else:
            lines.append("_No se detectaron hotspots resonantes._")
        lines.append("")

        # Estrategia de refactor (espectro colapsado)
        lines.append("## Estrategia de refactor (espectro primary mode)\n")
        if result.refactor_strategy:
            lines.append("| Módulo | Valor orbital | Deuda real | Total |")
            lines.append("|--------|--------------:|-----------:|------:|")
            for s in result.refactor_strategy[:20]:
                lines.append(
                    f"| `{s['module']}` | {s['orbital_value']:.4f} | "
                    f"{s['real_debt']} | {s['total']} |"
                )
        else:
            lines.append("_Sin módulos con deuda real._")
        lines.append("")

        # Top tensiones
        lines.append("## Top 10 tensiones de deuda (TOR)\n")
        if result.top_tensions:
            lines.append("| Pareja | Tensión |")
            lines.append("|--------|--------:|")
            for t in result.top_tensions:
                lines.append(f"| {t['pair']} | {t['tension']:.4f} |")
        lines.append("")

        # Retroalimentación al baseline
        lines.append("## Retroalimentación orbital (ajuste de ω por módulo)\n")
        if result.retrofeedback:
            lines.append("| Módulo | ω sugerido |")
            lines.append("|--------|-----------:|")
            for mod, omega in sorted(result.retrofeedback.items(), key=lambda x: -x[1]):
                lines.append(f"| `{mod}` | {omega} |")
        lines.append("")

        # Notas
        lines.append("## Interpretación\n")
        lines.append(
            "- **Hotspots**: módulos con resonancia positiva en RCC. Refactorizarlos "
            "juntos tiene sinergia (deuda correlacionada).\n"
        )
        lines.append(
            "- **Estrategia**: orden de ataque sugerido por el espectro colapsado. "
            "El valor orbital refleja amplitud (deuda absoluta) y fase (proporción).\n"
        )
        lines.append(
            "- **Tensiones**: TOR alto entre dos módulos = deuda correlacionada. "
            "TOR negativo = deuda descompensada (uno tiene mucha, el otro poca).\n"
        )
        lines.append(
            "- **Retroalimentación**: ω sugerido para actualizar el baseline. "
            "Módulos con alta amplitud → ω bajo (refactor estable).\n"
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Reporte orbital escrito en %s", out_path)

    # ── Acceso a estado interno (para tests) ──────────────────

    @property
    def orbital_engine(self) -> OrbitalEngine:
        """Acceso al OrbitalEngine subyacente (para inspección/tests)."""
        return self._orbital

    @property
    def last_audit_summary(self) -> dict[str, Any] | None:
        """Último summary de auditoría clásica ejecutada."""
        return self._last_audit_summary
