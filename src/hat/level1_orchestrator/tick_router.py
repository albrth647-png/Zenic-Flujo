"""
HAT-ORBITAL Nivel 0 — Tick Router.

Corazón del Nivel 0. Orquesta el flujo end-to-end HAT-ORBITAL:
1. Recibe input del usuario
2. Calcula intent_hash (anti-doble-llamada capa 1+2)
3. Carga sesión del Ledger vía OVCLedgerBridge.load_session()
4. Inyecta user_intent como variable OVC + crea ciclo routing_cycle
5. Ejecuta run_tick() → RCC detecta resonancia con Agent Cards
6. Llama fsm_disambiguate() si diferencia top1-top2 < 0.15
7. Despacha a DomainSupervisor.handle() del dominio ganador
8. Consolidación + persist_session() al Ledger
9. Síntesis de respuesta al usuario

Implementado en F0-D7 siguiendo HAT_ORBITAL_PLAN.md §2.4.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, TypedDict

from src.core.logging import setup_logging
from src.hat.level1_orchestrator.fsm.disambiguator import CLARIFY_DOMAIN
from src.hat.level1_orchestrator.intent.hasher import compute_intent_hash
from src.hat.level1_orchestrator.ledger.ovc_bridge import OVCLedgerBridge
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
from src.hat.level1_orchestrator.response_synthesizer import DispatchResult, ResponseSynthesizer
from src.hat.level1_orchestrator.routing import KeywordRouter, OrbitalRouter
from src.orbital.context import OrbitalContext

logger = setup_logging(__name__)

# Threshold para invocar FSM de desambiguación (mantenido para compatibilidad).
_DISAMBIGUATION_THRESHOLD = 0.15


class Subtask(TypedDict):
    """Subtarea enviada del HATRouter (L1) al supervisor (L2).

    Construido en ``HATRouter.handle()``, consumido por ``SpecialistRouter.handle()``
    y ``SpecialistAgent.route_action()`` / ``handle()``.
    """
    dispatch_id: str
    user_id: str
    session_id: str
    description: str
    parent_intent: str | None
    params: dict[str, Any]
    orbital_resonance: float


class SupervisorResult(TypedDict, total=False):
    """Resultado devuelto por el supervisor (L2) tras procesar un subtask.

    Los campos varían según ``status``:
    - ``'completed'``: tiene ``result``, ``specialists_used``, ``duration_ms``
    - ``'failed'``: tiene ``error``, ``domain``
    - ``'clarify'``: tiene ``result.clarify_message``
    """
    status: str
    # legítimo: resultado dinámico de dispatch HAT, tipo depende del especialista
    result: Any
    error: str
    domain: str
    specialists_used: list[str]
    duration_ms: int


def _get_supervisor_classes() -> dict[str, type]:
    """Retorna mapeo domain → supervisor class (solo fallback)."""
    return {}


class HATRouter:
    """Orquestador principal del Nivel 0 HAT-ORBITAL.

    Coordina Ledger, OrbitalContext, FSM de desambiguación y DomainSupervisors.
    Thread-unsafe: cada request debe crear su propio HATRouter o serializar accesos.
    """

    def __init__(
        self,
        ledger: LedgerRepository | None = None,
        ctx: OrbitalContext | None = None,
        bridge: OVCLedgerBridge | None = None,
        supervisors: dict[str, Any] | None = None,
    ) -> None:
        """Inicializa el router con dependencias inyectadas.

        Args:
            ledger: LedgerRepository. None → crea uno nuevo.
            ctx: OrbitalContext. None → usa singleton.
            bridge: OVCLedgerBridge. None → crea uno con ledger+ctx.
            supervisors: dict domain→supervisor instance. None → vacío {}.
        """
        self._ledger = ledger if ledger is not None else LedgerRepository()
        self._ctx = ctx if ctx is not None else OrbitalContext()  # type: ignore[no-untyped-call]
        self._bridge = bridge if bridge is not None else OVCLedgerBridge(
            repo=self._ledger, ctx=self._ctx,
        )
        # Supervisores del Nivel 2 inyectados por bootstrap.py.
        self._supervisors = supervisors if supervisors is not None else {}
        # Routers extraídos en M8 (routing orbital + keyword override).
        self._orbital_router = OrbitalRouter(ctx=self._ctx)
        self._keyword_router = KeywordRouter()
        # Session ID actual para namespacing OVC (seteado en handle()).
        self._current_session_id: str = "default"
        # Sintetizador de respuestas (extraído para SRP).
        self._synthesizer = ResponseSynthesizer()

    def handle(
        self,
        user_id: str,
        session_id: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> DispatchResult:
        """Procesa un mensaje del usuario end-to-end y retorna la respuesta.

        Flujo:
        1. Calcular intent_hash
        2. Registrar dispatch (anti-doble capa 2)
        3. Cargar sesión del Ledger
        4. Ruteo por resonancia ORBITAL
        5. Despachar al supervisor del dominio ganador
        6. Consolidar + persistir
        7. Sintetizar respuesta

        Args:
            user_id: ID del usuario.
            session_id: ID de la sesión.
            message: Texto del usuario.
            context: Contexto adicional opcional (params, etc.).

        Returns:
            DispatchResult con respuesta sintetizada.
        """
        start = time.monotonic()
        dispatch_id = f"disp_{uuid.uuid4().hex[:12]}"
        intent_hash = compute_intent_hash(user_id, session_id, message, context)
        params = context or {}

        # M8: establecer session_id en los routers extraídos.
        self._set_current_session(session_id)

        # FIX CRÍTICO M8: cargar sesión ANTES de ruteo orbital.
        self._bridge.load_session(user_id, session_id)

        # M8: ruteo delegado a OrbitalRouter + KeywordRouter.
        top3 = self._orbital_router.route(message)
        active_domain = self._get_active_domain(user_id, session_id)
        self._keyword_router.set_active_domain(active_domain)
        domain = self._keyword_router.disambiguate(top3, message)

        anti_dup_result = self._run_anti_dup_cascade(
            intent_hash, user_id, session_id, message, domain,
        )
        if anti_dup_result["duplicate"]:
            return self._synthesizer.build_anti_dup_response(
                anti_dup_result, dispatch_id, domain, start,
            )

        # 2. Registrar dispatch (anti-doble capa 2 idempotency)
        self._ledger.register_dispatch(
            intent_hash=intent_hash,
            user_id=user_id,
            session_id=session_id,
            domain=domain,
        )

        # 3. Despachar al supervisor
        subtask: Subtask = {
            "dispatch_id": dispatch_id,
            "user_id": user_id,
            "session_id": session_id,
            "description": message,
            "parent_intent": message,
            "params": {**params, "query": message},
            "orbital_resonance": top3[0][1] if top3 else 0.0,
        }

        if domain == CLARIFY_DOMAIN:
            supervisor_result = self._synthesizer.build_clarify_response(message)
        else:
            supervisor_result = self._dispatch_to_supervisor(domain, subtask)

        # 5. Consolidar
        resonance = top3[0][1] if top3 else 0.0
        self._ledger.complete_dispatch(intent_hash, supervisor_result, status="completed")

        # 6. Persistir sesión al Ledger
        self._bridge.persist_session(user_id, session_id)

        # 7. Sintetizar respuesta
        duration_ms = int((time.monotonic() - start) * 1000)
        return self._synthesizer.synthesize(
            dispatch_id=dispatch_id, domain=domain,
            supervisor_result=supervisor_result, resonance=resonance,
            duration_ms=duration_ms, anti_dup_layer="none",
        )

    def _run_anti_dup_cascade(
        self,
        intent_hash: str,
        user_id: str,
        session_id: str,
        message: str,
        domain: str,
    ) -> dict[str, Any]:
        """Ejecuta el cascade anti-doble-llamada de 5 capas.

        Args:
            intent_hash: Hash del intent.
            user_id: ID del usuario.
            session_id: ID de la sesión.
            message: Texto del usuario.
            domain: Dominio destino.

        Returns:
            Resultado del cascade con duplicate/action/layer_hit.
        """
        from src.hat.level1_orchestrator.anti_duplication.cascade import AntiDuplicationCascade

        cascade = AntiDuplicationCascade(repo=self._ledger)
        return cascade.check(
            intent_hash=intent_hash,
            user_id=user_id,
            session_id=session_id,
            message=message,
            domain=domain if domain != CLARIFY_DOMAIN else "clarify",
        )

    def _set_current_session(self, session_id: str) -> None:
        """Establece el session_id en ambos routers extraídos (M8).

        Delega a ``OrbitalRouter.set_session()``. El KeywordRouter es stateless
        respecto a la sesión (no namespacing), solo se le pasa active_domain.
        """
        self._current_session_id = session_id
        self._orbital_router.set_session(session_id)

    def _route_by_orbital(self, message: str) -> list[tuple[str, float]]:
        """Delegado a ``OrbitalRouter.route()`` (M8).

        Mantenido como wrapper fino para compatibilidad con tests existentes
        que llaman ``hat_router._route_by_orbital()`` directamente.
        """
        return self._orbital_router.route(message)

    def _disambiguate(
        self,
        top3: list[tuple[str, float]],
        message: str,
        active_domain: str | None,
    ) -> str:
        """Delegado a ``KeywordRouter.disambiguate()`` (M8).

        Mantenido como wrapper fino para compatibilidad con tests existentes.
        """
        self._keyword_router.set_active_domain(active_domain)
        return self._keyword_router.disambiguate(top3, message)

    def _dispatch_to_supervisor(
        self, domain: str, subtask: Subtask,
    ) -> SupervisorResult:
        """Despacha la subtarea al supervisor del dominio ganador.

        Args:
            domain: Dominio ganador ('operaciones', 'comunicaciones', 'datos_auto').
            subtask: Subtarea a procesar.

        Returns:
            dict con status, result, specialists_used, duration_ms.
        """
        supervisor = self._supervisors.get(domain)
        if supervisor is None:
            return {
                "status": "failed",
                "result": None,
                "error": f"no supervisor for domain {domain!r}",
                "specialists_used": [],
                "duration_ms": 0,
            }
        result: dict[str, Any] = supervisor.handle(subtask)
        return result

    def _get_active_domain(self, user_id: str, session_id: str) -> str | None:
        """Obtiene el dominio activo del Ledger (Fact 'active_domain').

        Args:
            user_id: ID del usuario.
            session_id: ID de la sesión.

        Returns:
            Dominio activo o None si no hay Fact.
        """
        fact = self._ledger.get_fact(user_id, session_id, "active_domain")
        if fact is None:
            return None
        value = fact.get("fact_value")
        if isinstance(value, str):
            return value
        return None
