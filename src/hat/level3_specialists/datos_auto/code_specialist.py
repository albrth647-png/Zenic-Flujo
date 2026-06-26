"""
HAT NIVEL 3 — CodeSpecialist
=============================

UNA SOLA RESPONSABILIDAD: Código, lógica y automatización con IA.

Coordina los workers del Nivel 4 para las tools (Nivel 5):
- code_runner (CodeRunnerTool): run_python, validate
- logic_gate (LogicGateService): evaluate_rule, validate_expression, save_rule,
  get_rule, list_rules, delete_rule, evaluate_saved_rule
- autopilot (AutoPilotService): suggest_templates, get_quick_templates,
  create_from_template
- openai (OpenAIService): chat_completion, embeddings, list_models, moderate
- ollama (OllamaService): chat, generate, embeddings, list_models, pull_model

Routing por keywords:
- "código", "python", "script", "ejecutar", "función" → code_runner.run_python
- "regla", "condición", "if", "evaluar" → logic_gate.evaluate_rule
- "plantilla", "template" → autopilot.suggest_templates
- "openai", "gpt", "chatgpt" → openai.chat_completion
- "ollama", "llm local" → ollama.chat
- Default: code_runner.run_python
"""

from __future__ import annotations
from typing import Any

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, Subtask, SpecialistResult


class CodeSpecialist(SpecialistAgent):
    """Specialist con UNA responsabilidad: código y automatización (CodeRunner + LogicGate + Autopilot + OpenAI + Ollama)."""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        super().__init__(
            specialist_name="code",
            responsibility="codigo_automatizacion",
            tools=tools or {},
        )

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="code",
            agent_name="Code",
            domain="datos_auto",
            tier="specialist",
            capabilities=[
                # code_runner
                "run_python", "validate",
                # logic_gate
                "evaluate_rule", "validate_expression", "save_rule",
                "get_rule", "list_rules", "delete_rule", "evaluate_saved_rule",
                # autopilot
                "suggest_templates", "get_quick_templates", "create_from_template",
                # openai
                "chat_completion", "embeddings", "list_models", "moderate",
                # ollama
                "chat", "generate", "embeddings", "list_models", "pull_model",
            ],
            cost_per_call=0.0,
            avg_latency_ms=200,
            orbital_keywords=[
                "código", "codigo", "python", "script", "ejecutar", "función",
                "funcion", "programa", "código python", "run python",
                "regla", "condición", "condicion", "if", "evaluar", "lógica",
                "logica", "logic gate",
                "plantilla", "template", "autopilot",
                "openai", "gpt", "chatgpt", "llm", "ia", "ai",
                "ollama", "llm local", "modelo local",
                "automatizar", "automatización", "automatizacion",
            ],
            orbital_amplitude=1.5,
            orbital_velocity=0.05,
        )

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask."""
        desc = (subtask.get("description") or subtask.get("message") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        # --- OpenAI routing ---
        if any(kw in desc for kw in ["openai", "gpt", "chatgpt"]):
            if any(kw in desc for kw in ["embedding", "vector", "embed"]):
                return "openai", "embeddings", params
            if any(kw in desc for kw in ["modelos", "list models", "listar modelos"]):
                return "openai", "list_models", params
            if any(kw in desc for kw in ["moderar", "moderate", "moderación"]):
                return "openai", "moderate", params
            # Default openai: chat completion
            return "openai", "chat_completion", params

        # --- Ollama routing ---
        if any(kw in desc for kw in ["ollama", "llm local", "modelo local"]):
            if any(kw in desc for kw in ["generar", "generate", "completar"]):
                return "ollama", "generate", params
            if any(kw in desc for kw in ["embedding", "vector", "embed"]):
                return "ollama", "embeddings", params
            if any(kw in desc for kw in ["modelos", "list models", "listar modelos"]):
                return "ollama", "list_models", params
            if any(kw in desc for kw in ["pull", "descargar modelo", "instalar modelo"]):
                return "ollama", "pull_model", params
            # Default ollama: chat
            return "ollama", "chat", params

        # --- Autopilot routing ---
        if any(kw in desc for kw in ["plantilla", "template", "autopilot"]):
            if any(kw in desc for kw in ["crear plantilla", "create from template", "aplicar plantilla"]):
                return "autopilot", "create_from_template", params
            if any(kw in desc for kw in ["plantillas rápidas", "quick templates", "plantillas quick"]):
                return "autopilot", "get_quick_templates", params
            # Default autopilot: sugerir plantillas
            return "autopilot", "suggest_templates", params

        # --- LogicGate routing ---
        if any(kw in desc for kw in ["regla", "condición", "condicion", "evaluar", "logic gate", "lógica"]):
            if any(kw in desc for kw in ["validar expresión", "validate expression", "validar regla"]):
                return "logic_gate", "validate_expression", params
            if any(kw in desc for kw in ["guardar regla", "save rule", "crear regla"]):
                return "logic_gate", "save_rule", params
            if any(kw in desc for kw in ["listar reglas", "list rules", "ver reglas"]):
                return "logic_gate", "list_rules", params
            if any(kw in desc for kw in ["eliminar regla", "borrar regla", "delete rule"]):
                return "logic_gate", "delete_rule", params
            if any(kw in desc for kw in ["obtener regla", "get rule", "buscar regla"]):
                return "logic_gate", "get_rule", params
            # Default logic_gate: evaluar regla (incluye "if", "evaluar")
            return "logic_gate", "evaluate_rule", params

        # --- CodeRunner routing ---
        # (cubre: "código", "python", "script", "ejecutar", "función")
        if any(kw in desc for kw in ["validar código", "validate code", "revisar código"]):
            return "code_runner", "validate", params
        # Default code_runner: ejecutar python
        return "code_runner", "run_python", params

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
