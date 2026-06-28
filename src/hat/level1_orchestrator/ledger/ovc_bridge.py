"""
HAT-ORBITAL Nivel 0 — Bridge Ledger ↔ OVC (M9 — v2.0).

Sincroniza variables orbitales con el Ledger SQLite entre sesiones. Esto
resuelve el problema real de ORBITAL: el contexto del singleton OrbitalContext
se pierde entre sesiones (solo existe en memoria).

Flujo:
  Inicio de sesión:
    1. load_session(user_id, session_id) → carga Facts y Hypotheses del
       Ledger como variables OVC.
       M9: ya no carga Plan (tabla hat_plan eliminada) ni Agent Cards (las
       cards se publican en memoria por bootstrap.py vía publish_card()).
  Durante la sesión:
    - Cada tick ORBITAL puede mutar estas variables.
    - Nuevos Facts confirmados se añaden al OVC y se persisten.
  Cierre de sesión (o cada N ticks):
    - persist_session(user_id, session_id) → snapshot del OVC → Ledger.

Namespacing: cada variable OVC se crea con prefijo `hat_<session_id>__` para
aislar sesiones concurrentes (extensión del fix Sprint 1 bug #1 de ZF).

Implementado en F0-D4; simplificado en M9 siguiendo IMPLEMENTATION_PLAN.md §M9.
"""

from __future__ import annotations

import math
from typing import Final, Any

from src.core.logging import setup_logging
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
from src.orbital.context import OrbitalContext

logger = setup_logging(__name__)

# θ fija para Facts: 0 radianes (alta confianza, no orbitan).
FACT_THETA: Final[float] = 0.0

# θ fija para Hypotheses no verificadas: π/4 (confianza media).
HYPOTHESIS_THETA: Final[float] = math.pi / 4.0

# Velocidad orbital por defecto para variables cargadas desde el Ledger.
# Facts no orbitan (velocity=0); Hypotheses tienen drift lento.
FACT_VELOCITY: Final[float] = 0.0
HYPOTHESIS_VELOCITY: Final[float] = 0.05

# Grupos orbitales para clasificar variables en el OVC.
FACT_GROUP: Final[str] = "hat_facts"
HYPOTHESIS_GROUP: Final[str] = "hat_hypotheses"

# Prefijo para namespacing de variables por sesión.
SESSION_VAR_PREFIX: Final[str] = "hat_"


class OVCLedgerBridge:
    """Sincroniza variables orbitales con el Ledger SQLite entre sesiones.

    Attributes:
        _repo: LedgerRepository para CRUD sobre las 3 tablas HAT (M9).
        _ctx: OrbitalContext singleton (OVC + TOR + RCC + COD + Espectro).

    Usage:
        bridge = OVCLedgerBridge()
        bridge.load_session(user_id, session_id)  # al iniciar sesión
        # ... ticks orbitales, llamadas a supervisors, etc. ...
        bridge.persist_session(user_id, session_id)  # al cerrar sesión
    """

    def __init__(
        self,
        repo: LedgerRepository | None = None,
        ctx: OrbitalContext | None = None,
    ) -> None:
        """Inicializa el bridge con dependencias inyectadas.

        Args:
            repo: LedgerRepository. Si None, crea uno nuevo (usa DatabaseManager singleton).
            ctx: OrbitalContext. Si None, usa el singleton existente.
        """
        self._repo = repo if repo is not None else LedgerRepository()
        self._ctx = ctx if ctx is not None else OrbitalContext()  # type: ignore[no-untyped-call]

    # ─────────────────────────────────────────────────────────
    # load_session
    # ─────────────────────────────────────────────────────────

    def load_session(self, user_id: str, session_id: str) -> dict[str, int]:
        """Carga Facts y Hypotheses del Ledger como variables OVC.

        M9: ya no carga Plan (tabla hat_plan eliminada) ni Agent Cards (las
        cards se publican en memoria por bootstrap.py vía specialist.publish_card()).

        Idempotente: si las variables ya existen para esta sesión, se limpian
        primero (vía delete_variables_by_prefix) y se recargan.

        Args:
            user_id: ID del usuario.
            session_id: ID de la sesión (usado para namespacing de variables OVC).

        Returns:
            Dict con conteos: {"facts": N, "hypotheses": N, "plan_steps": 0, "cards": 0}.
        """
        prefix = self._make_session_prefix(session_id)
        self._ctx.ovc.delete_variables_by_prefix(prefix)

        facts_count = self._load_facts(user_id, session_id, prefix)
        hypotheses_count = self._load_hypotheses(user_id, session_id, prefix)
        # M9: No load plan (eliminated), no load agent_cards (published in memory by bootstrap)
        counts = {"facts": facts_count, "hypotheses": hypotheses_count, "plan_steps": 0, "cards": 0}
        logger.info(
            f"OVCLedgerBridge.load_session: {session_id} cargó "
            f"{facts_count}F + {hypotheses_count}H"
        )
        return counts

    def _load_facts(self, user_id: str, session_id: str, prefix: str) -> int:
        """Carga Facts como variables OVC con θ=0 (alta confianza, no orbitan)."""
        facts = self._repo.get_facts(user_id, session_id)
        for fact in facts:
            var_name = f"{prefix}fact_{fact['fact_key']}"
            try:
                self._ctx.ovc.create_variable(
                    name=var_name,
                    theta=fact.get("orbital_theta", FACT_THETA),
                    amplitude=fact.get("orbital_amplitude", 1.0),
                    velocity=FACT_VELOCITY,
                    orbit_group=FACT_GROUP,
                    metadata={
                        "type": "fact",
                        "key": fact["fact_key"],
                        "value": fact["fact_value"],
                        "confidence": fact["confidence"],
                    },
                )
            except ValueError:
                # Variable ya existe (raro tras delete_variables_by_prefix) — skip.
                continue
        return len(facts)

    def _load_hypotheses(self, user_id: str, session_id: str, prefix: str) -> int:
        """Carga Hypotheses no verificadas como variables OVC con θ=π/4.

        Si la hypothesis tiene orbital_theta != 0 almacenado (mutada en sesión
        previa), se usa ese valor. Si es 0 (default del schema), se aplica
        HYPOTHESIS_THETA = π/4 (confianza media para hipótesis no verificadas).
        """
        hypotheses = self._repo.get_hypotheses(user_id, session_id, only_unverified=True)
        for hyp in hypotheses:
            var_name = f"{prefix}hyp_{hyp['hypothesis_key']}"
            # El schema.sql usa DEFAULT 0.785 (truncado) — distinguir "default"
            # de "valor real mutado". Si el valor está cerca del default del
            # schema (0.785), aplicamos HYPOTHESIS_THETA exacta.
            stored_theta = hyp.get("orbital_theta", 0.0)
            theta = HYPOTHESIS_THETA if abs(stored_theta - 0.785) < 0.001 or stored_theta == 0.0 else stored_theta
            try:
                self._ctx.ovc.create_variable(
                    name=var_name,
                    theta=theta,
                    amplitude=hyp.get("orbital_amplitude", 0.5),
                    velocity=HYPOTHESIS_VELOCITY,
                    orbit_group=HYPOTHESIS_GROUP,
                    metadata={
                        "type": "hypothesis",
                        "key": hyp["hypothesis_key"],
                        "value": hyp["hypothesis_value"],
                        "confidence": hyp["confidence"],
                    },
                )
            except ValueError:
                continue
        return len(hypotheses)

    # ─────────────────────────────────────────────────────────
    # persist_session
    # ─────────────────────────────────────────────────────────

    def persist_session(self, user_id: str, session_id: str) -> dict[str, int]:
        """Snapshot del OVC → persiste Facts y Hypotheses al Ledger.

        Solo persiste variables creadas por load_session (prefix `hat_<session>__`).
        Variables de otras sesiones o del motor ZF no se tocan.

        Args:
            user_id: ID del usuario.
            session_id: ID de la sesión cuyas variables se persisten.

        Returns:
            Dict con conteos: {"facts_persisted": N, "hypotheses_persisted": N}.
        """
        prefix = self._make_session_prefix(session_id)
        all_vars = self._ctx.ovc.get_all_variables()

        facts_count = 0
        hypotheses_count = 0
        for name, var in all_vars.items():
            if not name.startswith(prefix):
                continue
            metadata = var.metadata or {}
            fact_persisted, hyp_persisted = self._persist_variable(
                user_id, session_id, metadata, var
            )
            facts_count += fact_persisted
            hypotheses_count += hyp_persisted

        counts = {
            "facts_persisted": facts_count,
            "hypotheses_persisted": hypotheses_count,
        }
        logger.info(
            f"OVCLedgerBridge.persist_session: {session_id} guardó "
            f"{facts_count}F + {hypotheses_count}H"
        )
        return counts

    def _persist_variable(
        self,
        user_id: str,
        session_id: str,
        metadata: dict[str, Any],
        var: object,
    ) -> tuple[int, int]:
        """Persiste una variable OVC al Ledger según su tipo.

        Returns:
            Tupla (facts_persisted, hypotheses_persisted) — (1,0), (0,1) o (0,0).
        """
        var_type = metadata.get("type")
        if var_type == "fact":
            self._repo.upsert_fact(
                user_id, session_id,
                fact_key=metadata["key"],
                fact_value=metadata["value"],
                confidence=metadata.get("confidence", 1.0),
                orbital_theta=var.theta,
                orbital_amplitude=var.amplitude,
            )
            return 1, 0
        if var_type == "hypothesis":
            self._repo.upsert_hypothesis(
                user_id, session_id,
                hypothesis_key=metadata["key"],
                hypothesis_value=metadata["value"],
                confidence=metadata.get("confidence", 0.5),
                orbital_theta=var.theta,
                orbital_amplitude=var.amplitude,
            )
            return 0, 1
        return 0, 0

    # ─────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _make_session_prefix(session_id: str) -> str:
        """Genera el prefijo de namespacing para variables de una sesión.

        Args:
            session_id: ID de la sesión. Se sanitiza (no alfanuméricos → '_').

        Returns:
            Prefijo string en formato 'hat_<sanitized_session_id>__'.
        """
        safe_id = "".join(c if c.isalnum() else "_" for c in str(session_id))
        return f"{SESSION_VAR_PREFIX}{safe_id}__"
