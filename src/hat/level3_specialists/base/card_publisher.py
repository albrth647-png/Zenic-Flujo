"""
HAT-ORBITAL Nivel 2-3 — Card Publisher Mixin (M9 — v2.0).

Mixin que añade a cualquier BaseAgent la capacidad de publicar su AgentCard
como variable OVC para resonancia RCC.

M9: la tabla hat_agent_cards fue eliminada (cards se generan fresh en cada
startup). publish_card() ahora solo inyecta en OVC (no persiste en DB).

Uso:
    class MySpecialist(BaseAgent, CardPublisherMixin):
        def get_card(self) -> AgentCard:
            return AgentCard(agent_id="my_specialist", ...)

    agent = MySpecialist(config)
    agent.publish_card()  # inyecta en OVC (no DB post-M9)

Implementado en F0-D6; simplificado en M9 siguiendo IMPLEMENTATION_PLAN.md §M9.
"""

from __future__ import annotations

import hashlib

from src.core.logging import setup_logging
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
from src.hat.level3_specialists.base.cards import AgentCard
from src.orbital.context import OrbitalContext
from src.orbital.models import TWO_PI

logger = setup_logging(__name__)

# Prefijo para variables OVC de Agent Cards.
_CARD_VAR_PREFIX = "card_"


class CardPublisherMixin:
    """Mixin para publicar AgentCards en OVC.

    M9: ya NO persiste en DB (tabla hat_agent_cards eliminada). Las cards
    se generan fresh en cada startup y solo viven en memoria (OVC).

    Debe combinarse con BaseAgent (que provee `self.config` y `self.agent_id`).
    La subclase debe implementar get_card() -> AgentCard.
    """

    def get_card(self) -> AgentCard:
        """Retorna la AgentCard que describe a este agente.

        Subclases deben sobreescribir este método.
        """
        raise NotImplementedError(
            f"{type(self).__name__} debe implementar get_card() -> AgentCard"
        )

    def publish_card(
        self,
        _repo: LedgerRepository | None = None,  # compat, no usado (M9 eliminó persistencia)
        ctx: OrbitalContext | None = None,
    ) -> AgentCard:
        """Publica la AgentCard en OVC (memoria).

        M9: ya NO persiste en hat_agent_cards (tabla eliminada). Las cards
        solo se inyectan como variables OVC para resonancia RCC.

        Idempotente: si la variable OVC ya existe, se skip (no duplica).

        Args:
            _repo: LedgerRepository. Mantenido por compat — ya no se usa para
                persistir cards, pero algunas subclases podrían seguir pasándolo.
            ctx: OrbitalContext. None → usa el singleton existente.

        Returns:
            La AgentCard publicada (la misma que retorna get_card()).
        """
        card = self.get_card()
        context = ctx if ctx is not None else OrbitalContext()  # type: ignore[no-untyped-call]

        # M9: paso 1 (persistir a DB) eliminado — hat_agent_cards ya no existe.

        # 2. Inyectar como variable OVC
        self._inject_card_to_ovc(card, context)

        logger.info(
            "CardPublisher: card %s publicada en OVC (domain=%s, tier=%s, %d keywords)",
            card.agent_id, card.domain, card.tier, len(card.orbital_keywords),
        )
        return card

    @staticmethod
    def _inject_card_to_ovc(card: AgentCard, ctx: OrbitalContext) -> None:
        """Inyecta la AgentCard como variable OVC. Idempotente."""
        var_name = f"{_CARD_VAR_PREFIX}{card.agent_id}"
        theta = CardPublisherMixin._deterministic_theta(card.orbital_keywords)
        try:
            ctx.ovc.create_variable(
                name=var_name,
                theta=theta,
                amplitude=card.orbital_amplitude,
                velocity=card.orbital_velocity,
                orbit_group=f"hat_cards_{card.domain}",
                metadata=card.to_ovc_metadata(),
            )
        except ValueError:
            # Variable ya existe (idempotente) — skip silencioso.
            logger.debug(
                "CardPublisher: variable OVC %s ya existe — skip", var_name
            )

    @staticmethod
    def _deterministic_theta(keywords: list[str]) -> float:
        """Genera una fase θ determinista a partir de keywords (hash MD5).

        Args:
            keywords: Lista de keywords (ej: ["buscar", "info"]).

        Returns:
            θ en [0, 2π) derivada deterministamente. Misma lista → misma θ.
        """
        joined = "|".join(keywords)
        hash_val = int(
            hashlib.md5(joined.encode(), usedforsecurity=False).hexdigest()[:8], 16
        )
        return (hash_val % 10000) / 10000.0 * TWO_PI

    @staticmethod
    def make_card_var_name(agent_id: str) -> str:
        """Genera el nombre canónico de la variable OVC para una card.

        Args:
            agent_id: ID del agente.

        Returns:
            Nombre en formato "card_<agent_id>".
        """
        return f"{_CARD_VAR_PREFIX}{agent_id}"
