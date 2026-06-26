"""NIVEL 3 — Base compartida de specialists.

Contiene:
- AgentCard (dataclass que declara capacidades)
- CardPublisherMixin (publica cards al OVC + DB)
- SpecialistAgent (ABC base para los 9 specialists concretos)
"""
from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.card_publisher import CardPublisherMixin
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent

__all__ = ["AgentCard", "CardPublisherMixin", "SpecialistAgent"]
