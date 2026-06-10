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

from src.orbital.ovc import OVC
from src.orbital.tor import TOR
from src.orbital.rcc import RCC
from src.orbital.cod import COD
from src.orbital.espectro import EspectroOrbital
from src.orbital.engine import OrbitalEngine
from src.utils.logger import setup_logging

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

    _instance: "OrbitalContext | None" = None
    _lock = threading.RLock()

    def __new__(cls) -> "OrbitalContext":
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

    def get_snapshot(self) -> dict:
        """Retorna un snapshot completo del estado orbital compartido."""
        return {
            "ovc_variables": self._ovc.variable_count,
            "ovc_phases": self._ovc.get_phase_snapshot(),
            "ovc_values": self._ovc.get_value_snapshot(),
            "tor_matrix_size": len(self._tor.calculate_matrix()) if self._ovc.variable_count >= 2 else 0,
            "rcc_cycles": len(self._rcc._cycles) if hasattr(self._rcc, '_cycles') else 0,
            "engine_tick": self._engine.tick,
        }

    def status_summary(self) -> str:
        """Retorna un resumen del estado orbital compartido."""
        lines = ["=" * 50]
        lines.append("ORBITAL CONTEXT — Estado Compartido")
        lines.append("=" * 50)
        lines.append(f"  Variables orbitales: {self._ovc.variable_count}")
        lines.append(f"  Engine tick: {self._engine.tick}")
        lines.append(f"  RCC ciclos: {len(self._rcc._cycles) if hasattr(self._rcc, '_cycles') else 0}")
        if self._ovc.variable_count > 0:
            lines.append(self._ovc.status_summary())
        lines.append("=" * 50)
        return "\n".join(lines)

    # ── Reset para testing ─────────────────────────────────────

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (para tests)."""
        cls._instance = None

    def __repr__(self) -> str:
        return f"OrbitalContext(vars={self._ovc.variable_count}, tick={self._engine.tick})"
