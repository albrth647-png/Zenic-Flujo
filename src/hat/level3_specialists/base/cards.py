"""
HAT-ORBITAL Nivel 2-3 — Agent Cards.

Declaración de capacidades de un agente. Las Agent Cards son usadas por el
Nivel 0 (OrbitalEngine) para calcular resonancia RCC entre el input del usuario
y los agentes disponibles, y así decidir ruteo sin LLM.

Cada agente (supervisor/specialist/worker) publica una AgentCard al iniciar,
que se persiste en hat_agent_cards y se inyecta como variable OVC con θ
derivada deterministamente de sus keywords.

Implementado en F0-D6 siguiendo HAT_ORBITAL_PLAN.md §5.2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentCard:
    """Declaración de capacidades de un agente, usada para resonancia RCC.

    Attributes:
        agent_id: Identificador único del agente (ej: "web_researcher").
        agent_name: Nombre humano legible (ej: "Web Researcher").
        domain: Dominio al que pertenece ("research" | "build" | "operate").
        tier: Nivel jerárquico ("supervisor" | "specialist" | "worker").
        capabilities: Lista de capacidades declaradas (ej: ["web_search"]).
        cost_per_call: Coste estimado por invocación en USD.
        avg_latency_ms: Latencia media esperada en milisegundos.
        orbital_keywords: Keywords para resonancia RCC (ej: ["buscar", "info"]).
        orbital_amplitude: Peso en resonancia (>1 = más influencia).
        orbital_velocity: Velocidad orbital del agente en rad/tick.
    """

    agent_id: str
    agent_name: str
    domain: str
    tier: str
    capabilities: list[str] = field(default_factory=list)
    cost_per_call: float = 0.0
    avg_latency_ms: int = 0
    orbital_keywords: list[str] = field(default_factory=list)
    orbital_amplitude: float = 1.0
    orbital_velocity: float = 0.1

    def to_db_row(self) -> dict[str, object]:
        """Convierte la card a un dict listo para upsert_agent_card.

        Returns:
            Dict con las 10 columnas de hat_agent_cards (sin id, created_at, last_seen
            que los gestiona el repositorio).
        """
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "domain": self.domain,
            "tier": self.tier,
            "capabilities": json.dumps(self.capabilities, ensure_ascii=False),
            "cost_per_call": self.cost_per_call,
            "avg_latency_ms": self.avg_latency_ms,
            "orbital_keywords": json.dumps(self.orbital_keywords, ensure_ascii=False),
            "orbital_amplitude": self.orbital_amplitude,
            "orbital_velocity": self.orbital_velocity,
        }

    def to_ovc_metadata(self) -> dict[str, object]:
        """Metadatos para la variable OVC creada al publicar la card.

        Returns:
            Dict con type, agent_id, domain, tier, capabilities — listo para
            asignar a VariableOrbital.metadata.
        """
        return {
            "type": "agent_card",
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "domain": self.domain,
            "tier": self.tier,
            "capabilities": self.capabilities,
            "cost_per_call": self.cost_per_call,
            "avg_latency_ms": self.avg_latency_ms,
        }

    def __repr__(self) -> str:
        """Repr compacto que NO incluye capabilities completas (puede ser largo)."""
        return (
            f"AgentCard(agent_id={self.agent_id!r}, "
            f"domain={self.domain!r}, tier={self.tier!r}, "
            f"keywords={len(self.orbital_keywords)})"
        )
