"""
ORBITAL — Contexto Compartido (OrbitalContext)
================================================

Singleton que provee una unica instancia de OVC, TOR, RCC, COD y
EspectroOrbital compartida entre TODOS los componentes del sistema.

PROBLEMA que resuelve:
- Cada componente (WorkflowEngine, StepExecutor, ConditionEvaluator,
  BranchHandler, LoopHandler, ErrorHandler, EventBus) creaba su propio
  OVC independiente → variables orbitales aisladas → sin retroalimentacion
  real entre componentes.

SOLUCION:
- OrbitalContext es un singleton que contiene una unica instancia de cada
  pilar orbital. Todos los componentes lo usan, asi las variables orbitales
  se comparten y la retroalimentacion fluye entre todos los componentes.

Paradigma: CIRCULAR — Lo que un componente retroalimenta, otro lo recibe.
"""

from __future__ import annotations

import threading
from typing import Any

from src.core.logging import setup_logging
from src.orbital.cod import COD
from src.orbital.engine import OrbitalEngine
from src.orbital.espectro import EspectroOrbital
from src.orbital.ovc import OVC
from src.orbital.rcc import RCC
from src.orbital.tor import TOR

logger = setup_logging(__name__)


class OrbitalContext:
    """
    Contexto Orbital Compartido — Singleton.

    Provee una unica instancia de cada pilar ORBITAL compartida
    entre todos los componentes del sistema determinista.

    Uso:
        ctx = OrbitalContext()
        ovc = ctx.ovc      # OVC compartido
        tor = ctx.tor      # TOR compartido
        rcc = ctx.rcc      # RCC compartido
        cod = ctx.cod      # COD compartido
        espectro = ctx.espectro  # Espectro compartido

    Ciclo ORBITAL compartido:
    OVC → TOR → RCC → COD → Espectro → Retro → OVC → ...
    Todo lo que un componente hace en el OVC, todos los demas lo ven.
    """

    _instance: OrbitalContext | None = None
    _lock = threading.RLock()

    def __new__(cls) -> OrbitalContext:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        with self._lock:
            if hasattr(self, "_initialized") and self._initialized:
                return
            self._initialized = True

            # ── 5 Pilares ORBITALES (compartidos) ───────────
            # Se crean primero las instancias, luego se pasan al Engine
            # para que TODOS compartan el MISMO OVC.
            self._ovc = OVC()
            self._tor = TOR(self._ovc)
            self._rcc = RCC(self._ovc, self._tor)
            self._cod = COD(self._ovc, self._tor, self._rcc)
            self._espectro = EspectroOrbital(self._ovc, self._tor, self._rcc, self._cod)
            # Engine recibe las MISMAS instancias — garantiza id(ctx.ovc) == id(ctx.engine._ovc)
            self._engine = OrbitalEngine(
                ovc=self._ovc,
                tor=self._tor,
                rcc=self._rcc,
                cod=self._cod,
                espectro=self._espectro,
            )

            logger.info("OrbitalContext: Inicializado — OVC compartido activo (engine sincronizado)")

    # ── Propiedades de acceso a los 5 pilares ──────────────────

    @property
    def ovc(self) -> OVC:
        """OVC compartido — Variables orbitales unificadas."""
        return self._ovc

    @property
    def tor(self) -> TOR:
        """TOR compartido — Tensiones sobre el OVC unificado."""
        return self._tor

    @property
    def rcc(self) -> RCC:
        """RCC compartido — Resonancia sobre el OVC unificado."""
        return self._rcc

    @property
    def cod(self) -> COD:
        """COD compartido — Colapso sobre el OVC unificado."""
        return self._cod

    @property
    def espectro(self) -> EspectroOrbital:
        """EspectroOrbital compartido — Espectro sobre el OVC unificado."""
        return self._espectro

    @property
    def engine(self) -> OrbitalEngine:
        """OrbitalEngine compartido — Motor completo."""
        return self._engine

    # ── Ciclo Orbital Completo ─────────────────────────────────

    def run_tick(self, dt: float = 1.0, retrofeed_damping: float = 0.3) -> object:
        """
        Ejecuta un ciclo orbital completo compartido.

        OVC → TOR → RCC → COD → Espectro → Retro → OVC

        Todos los componentes ven los cambios inmediatamente.
        """

        result = self._engine.run_tick(dt=dt, retrofeed_damping=retrofeed_damping)

        logger.info(
            f"OrbitalContext.tick: tick={result.tick} "
            f"vars={len(result.variables)} "
            f"TOR={len(result.tor_results)} "
            f"RCC={len(result.rcc_results)}"
        )

        return result

    # ── Consultas ──────────────────────────────────────────────

    def get_snapshot(self) -> dict[str, Any]:
        """Retorna un snapshot completo del estado orbital compartido."""
        # Fix Sprint 2 bug #13: usar métodos públicos en vez de atributos privados.
        rcc_cycle_count = (
            self._rcc.get_cycle_count() if hasattr(self._rcc, "get_cycle_count")
            else len(self._rcc._cycles)  # fallback
        )
        return {
            "ovc_variables": self._ovc.variable_count,
            "ovc_phases": self._ovc.get_phase_snapshot(),
            "ovc_values": self._ovc.get_value_snapshot(),
            "tor_matrix_size": len(self._tor.calculate_matrix()) if self._ovc.variable_count >= 2 else 0,
            "rcc_cycles": rcc_cycle_count,
            "engine_tick": self._engine.tick,
        }

    def status_summary(self) -> str:
        """Retorna un resumen del estado orbital compartido."""
        # Fix Sprint 2 bug #13: usar métodos públicos en vez de atributos privados.
        rcc_cycle_count = (
            self._rcc.get_cycle_count() if hasattr(self._rcc, "get_cycle_count")
            else len(self._rcc._cycles)  # fallback
        )
        lines = ["=" * 50]
        lines.append("ORBITAL CONTEXT — Estado Compartido")
        lines.append("=" * 50)
        lines.append(f"  Variables orbitales: {self._ovc.variable_count}")
        lines.append(f"  Engine tick: {self._engine.tick}")
        lines.append(f"  RCC ciclos: {rcc_cycle_count}")
        if self._ovc.variable_count > 0:
            lines.append(self._ovc.status_summary())
        lines.append("=" * 50)
        return "\n".join(lines)

    # ── Reset para testing ─────────────────────────────────────

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (para tests)."""
        cls._instance = None

    # ── Reset por workflow (fix Sprint 1 bugs #1 + #2) ─────────

    # Prefijo usado para namespacing de variables orbitales por workflow.
    # Formato: "wf_<execution_id>__<step_var_name>"
    # Esto permite que dos workflows concurrentes no contaminen sus variables
    # en el singleton compartido OVC.
    WORKFLOW_VAR_PREFIX = "wf_"

    @staticmethod
    def make_workflow_var_prefix(execution_id: str) -> str:
        """Genera el prefijo de namespace para variables de un workflow."""
        # Sanitizar execution_id para que sea válido como prefix de nombre
        safe_id = "".join(c if c.isalnum() else "_" for c in str(execution_id))
        return f"{OrbitalContext.WORKFLOW_VAR_PREFIX}{safe_id}__"

    def clear_workflow_variables(self, execution_id: str) -> int:
        """
        Elimina TODAS las variables orbitales asociadas a un execution_id.

        Esto resuelve el bug #1 del Sprint 1 (OrbitalContext singleton
        contaminable entre requests): al final de cada WorkflowEngine.execute(),
        se llama a este método para limpiar las variables orbitales del workflow
        que terminó, evitando que se acumulen y contaminen el siguiente.

        TAMBIÉN limpia los ciclos RCC registrados con el nombre workflow_cycle
        de ese execution_id (bug #3 — ciclos fantasma).

        Args:
            execution_id: ID de ejecución del workflow a limpiar.

        Returns:
            Número total de variables eliminadas.
        """
        prefix = self.make_workflow_var_prefix(execution_id)

        # Limpiar variables del OVC por prefijo (eficiente)
        removed = 0
        if hasattr(self._ovc, "delete_variables_by_prefix"):
            removed = self._ovc.delete_variables_by_prefix(prefix)
        else:
            # Fallback: iterar y eliminar una por una
            var_names = list(self._ovc.get_variable_names())
            for name in var_names:
                if name.startswith(prefix) and hasattr(self._ovc, "delete_variable"):
                    self._ovc.delete_variable(name)
                    removed += 1

        # Limpiar ciclo fantasma workflow_cycle_<exec_id> si existe
        cycle_name = f"workflow_cycle_{execution_id}"
        if hasattr(self._rcc, "remove_cycles_by_name"):
            self._rcc.remove_cycles_by_name(cycle_name)

        # Limpiar cache TOR para que no queden entradas stale
        if hasattr(self._tor, "clear_cache"):
            self._tor.clear_cache()

        if removed > 0:
            logger.info(
                f"OrbitalContext: {removed} variables orbitales limpiadas "
                f"para execution_id={execution_id}"
            )
        return removed

    def __repr__(self) -> str:
        return f"OrbitalContext(vars={self._ovc.variable_count}, tick={self._engine.tick})"
