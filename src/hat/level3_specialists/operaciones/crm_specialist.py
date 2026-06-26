"""
HAT NIVEL 3 — CrmSpecialist
============================

UNA SOLA RESPONSABILIDAD: Gestión de clientes/leads.

Coordina los workers del Nivel 4 para la tool CRM (Nivel 5):
- create_lead, update_lead, get_lead, list_leads, delete_lead
- advance_stage, close_won, close_lost, get_stats

Routing por keywords:
- "crear", "nuevo", "alta" → create_lead
- "listar", "mostrar", "ver" → list_leads
- "avanzar", "siguiente" → advance_stage
- "ganado", "won", "éxito" → close_won
- "perdido", "lost" → close_lost
- "estadísticas", "stats" → get_stats
"""

from __future__ import annotations
from typing import Any

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, Subtask, SpecialistResult


class CrmSpecialist(SpecialistAgent):
    """Specialist con UNA responsabilidad: gestión de clientes/leads."""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        super().__init__(
            specialist_name="crm",
            responsibility="gestion_clientes_leads",
            tools=tools or {},
        )

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="crm",
            agent_name="CRM",
            domain="operaciones",
            tier="specialist",
            capabilities=["create_lead", "update_lead", "get_lead", "list_leads",
                         "delete_lead", "advance_stage", "close_won", "close_lost", "get_stats"],
            cost_per_call=0.0,
            avg_latency_ms=50,
            orbital_keywords=["cliente", "lead", "venta", "oportunidad", "negocio", "contacto", "crm"],
            orbital_amplitude=1.5,
            orbital_velocity=0.05,
        )

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask."""
        desc = (subtask.get("description") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        if any(kw in desc for kw in ["crear", "nuevo", "alta", "registrar"]):
            return "crm", "create_lead", params
        if any(kw in desc for kw in ["listar", "mostrar", "ver"]):
            return "crm", "list_leads", params
        if any(kw in desc for kw in ["avanzar", "siguiente etapa"]):
            return "crm", "advance_stage", params
        if any(kw in desc for kw in ["ganado", "won", "éxito", "cerrado ganado"]):
            return "crm", "close_won", params
        if any(kw in desc for kw in ["perdido", "lost", "cerrado perdido"]):
            return "crm", "close_lost", params
        if any(kw in desc for kw in ["estadística", "stats", "resumen", "dashboard"]):
            return "crm", "get_stats", params
        if any(kw in desc for kw in ["eliminar", "borrar", "delete"]):
            return "crm", "delete_lead", params
        if any(kw in desc for kw in ["actualizar", "modificar", "update"]):
            return "crm", "update_lead", params
        if any(kw in desc for kw in ["obtener", "buscar", "get"]):
            return "crm", "get_lead", params

        # Default seguro: listar
        return "crm", "list_leads", params

    def handle(self, subtask: Subtask) -> SpecialistResult:
        """Ejecuta el specialist: route → invoke tool → return result."""
        import time
        start = time.monotonic()

        tool_name, action_name, params = self.route_action(subtask)
        tool = self._tools.get(tool_name)

        if tool is None:
            return SpecialistResult(
                status="failed",
                error=f"tool '{tool_name}' not available",
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            method = getattr(tool, action_name)
            result = method(**params) if params else method()
            return SpecialistResult(
                status="completed",
                action=action_name,
                result=result,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:
            return SpecialistResult(
                status="failed",
                error=str(exc),
                action=action_name,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
