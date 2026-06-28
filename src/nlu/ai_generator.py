"""
Workflow Determinista — AI Workflow Generator (Sprint 5)

Genera definiciones de workflow a partir de texto libre usando un LLM.
La EJECUCIÓN sigue siendo 100% determinista — la IA solo genera el JSON.

Flujo:
1. Usuario escribe texto libre
2. Guardrails: ContentGuardrails verifica el prompt
3. LLM genera JSON de workflow
4. WorkflowValidator valida el JSON generado
5. Guardrails: ExecutionGuardrails + PIIGuardrails verifican el workflow
6. Si es válido → retorna workflow listo
7. Si es inválido → fallback al compilador determinista

Soporta: Ollama (local), OpenAI, Anthropic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.core.logging import setup_logging
from src.nlu.ai_config import AIProvider, ProviderConfig, get_ai_config
from src.nlu.guardrails import (
    ContentGuardrails,
    ExecutionGuardrails,
    GuardrailAction,
    GuardrailResult,
    PIIGuardrails,
)
from typing import Any

logger = setup_logging(__name__)

# Tools conocidas (debe coincidir con src/nlu/compiler.py)
KNOWN_TOOLS = {
    "crm",
    "invoice",
    "inventory",
    "notification",
    "system",
    "autopilot",
    "logic_gate",
    "api_connector",
    "data_keeper",
    "code_runner",
    "gmail",
    "sheets",
    "telegram",
    "slack",
}

# Prompt template para generar workflows con guardrails integrados
SYSTEM_PROMPT = """Eres un generador de workflows de automatización de negocios.

Dado un texto del usuario, genera UN workflow en formato JSON.

HERRAMIENTAS DISPONIBLES:
- crm: create_lead, list_leads, update_lead
- notification: send_email, send_whatsapp, send_notification
- invoice: create_invoice, list_invoices, get_overdue_invoices
- inventory: add_product, update_stock, get_low_stock_products
- api_connector: request (GET/POST/PUT/DELETE)
- data_keeper: save, load, delete
- system: backup_database, get_setting
- code_runner: run_python, validate
- gmail: send_email, search_emails, get_message, list_labels
- sheets: read_sheet, write_sheet, append_row
- slack: send_message, list_channels, get_user_info
- telegram: send_message, send_photo

REGLAS DE SEGURIDAD:
1. NUNCA generes workflows que ejecuten comandos inseguros (rm -rf, drop table, etc.)
2. NUNCA generes workflows que soliciten contraseñas, API keys o datos sensibles como parámetros
3. NUNCA generes bucles infinitos (while true, loop forever)
4. Máximo 50 pasos por workflow
5. No generes más de 10 ramas fork paralelas

FORMATO DEL WORKFLOW:
1. Cada paso debe tener: id (int), tool (string), action (string), params (dict)
2. El trigger_type debe ser: "manual", "schedule", "event", o "webhook"
3. Si el usuario menciona un tiempo/cron, usa trigger_type "schedule"
4. Si el usuario menciona un evento (cuando llegue un email, cuando se cree un lead), usa "event"
5. Si no hay trigger claro, usa "manual"
6. Usa $input.xxx para variables de entrada del usuario
7. Usa $output.stepN.xxx para datos de pasos anteriores

RESPONDE SOLO CON EL JSON DEL WORKFLOW, sin texto adicional.

FORMATO:
{
    "name": "nombre_del_workflow",
    "description": "descripción corta",
    "trigger_type": "manual",
    "trigger_config": {},
    "steps": [
        {"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "$input.name"}}
    ]
}"""


@dataclass
class AIGenerationResult:
    """Resultado de la generación IA de un workflow."""

    workflow: dict[str, Any]
    provider: str
    model: str
    explanation: str
    validated: bool
    validation_errors: list[str]
    fallback_used: bool
    raw_response: str = ""
    guardrails_result: GuardrailResult | None = None  # Fase 3


class WorkflowAIGenerator:
    """
    Genera workflows a partir de texto libre usando un LLM.

    La generación es complementaria al compilador determinista:
    - Si el compilador determinista funciona → usarlo (preferido)
    - Si el usuario pide "usar IA" explícitamente → usar este generador
    - Si el compilador falla → fallback a este generador
    """

    def __init__(self):
        self._config = get_ai_config()
        # ── Fase 3: Guardrails ───────────────────────────
        self._content_guardrails = ContentGuardrails()
        self._execution_guardrails = ExecutionGuardrails()
        self._pii_guardrails = PIIGuardrails()

    def generate(
        self,
        text: str,
        lang: str = "es",
        enable_guardrails: bool = True,
    ) -> AIGenerationResult:
        """
        Genera un workflow desde texto libre usando el proveedor IA activo.

        Fase 3: Integra guardrails de contenido antes del LLM
        y guardrails de ejecución/PII después de generar.

        Args:
            text: Texto libre del usuario
            lang: Idioma para la explicación
            enable_guardrails: Si aplicar guardrails

        Returns:
            AIGenerationResult con el workflow y metadata
        """
        # ── 0. ContentGuardrails sobre el prompt ──────────
        if enable_guardrails:
            content_check = self._content_guardrails.check_prompt(text)
            if content_check.action == GuardrailAction.BLOCK:
                return AIGenerationResult(
                    workflow={},
                    provider="guardrails",
                    model="",
                    explanation=content_check.message,
                    validated=False,
                    validation_errors=[f"Content blocked: {content_check.message}"],
                    fallback_used=False,
                    guardrails_result=content_check,
                )

        if not self._config.is_ai_available():
            return AIGenerationResult(
                workflow={},
                provider="none",
                model="",
                explanation="No hay proveedor de IA configurado. Activa Ollama, OpenAI o Anthropic en Configuración.",
                validated=False,
                validation_errors=["No AI provider configured"],
                fallback_used=False,
            )

        provider_config = self._config.get_active_config()
        if not provider_config:
            return AIGenerationResult(
                workflow={},
                provider="none",
                model="",
                explanation="Proveedor IA no disponible.",
                validated=False,
                validation_errors=["Provider config is None"],
                fallback_used=False,
            )

        try:
            # 1. Llamar al LLM
            raw_response = self._call_llm(text, provider_config, lang)

            # 2. Parsear respuesta
            workflow = self._parse_workflow(raw_response)

            if not workflow:
                return AIGenerationResult(
                    workflow={},
                    provider=provider_config.provider.value,
                    model=provider_config.model,
                    explanation="El LLM no pudo generar un workflow válido.",
                    validated=False,
                    validation_errors=["Failed to parse LLM response as workflow JSON"],
                    fallback_used=False,
                    raw_response=raw_response,
                )

            # 3. Validar workflow (estructural)
            validation_errors = self._validate_workflow(workflow)

            if validation_errors:
                logger.warning(f"Workflow generado tiene errores: {validation_errors}")
                return AIGenerationResult(
                    workflow=workflow,
                    provider=provider_config.provider.value,
                    model=provider_config.model,
                    explanation="Workflow generado pero con errores de validación.",
                    validated=False,
                    validation_errors=validation_errors,
                    fallback_used=False,
                    raw_response=raw_response,
                )

            # ── 4. ExecutionGuardrails + PIIGuardrails ────
            if enable_guardrails:
                exec_check = self._execution_guardrails.check_workflow_definition(workflow)
                if exec_check.action == GuardrailAction.BLOCK:
                    return AIGenerationResult(
                        workflow=workflow,
                        provider=provider_config.provider.value,
                        model=provider_config.model,
                        explanation=exec_check.message,
                        validated=False,
                        validation_errors=[f"Execution blocked: {exec_check.message}"],
                        fallback_used=False,
                        raw_response=raw_response,
                        guardrails_result=exec_check,
                    )

                pii_check = self._pii_guardrails.check_workflow_for_pii(workflow)
                if pii_check.action == GuardrailAction.BLOCK:
                    return AIGenerationResult(
                        workflow=workflow,
                        provider=provider_config.provider.value,
                        model=provider_config.model,
                        explanation=pii_check.message,
                        validated=False,
                        validation_errors=[f"PII blocked: {pii_check.message}"],
                        fallback_used=False,
                        raw_response=raw_response,
                        guardrails_result=pii_check,
                    )

            # 5. Workflow válido (pasó validación + guardrails)
            explanation = self._generate_explanation(workflow, lang)
            return AIGenerationResult(
                workflow=workflow,
                provider=provider_config.provider.value,
                model=provider_config.model,
                explanation=explanation,
                validated=True,
                validation_errors=[],
                fallback_used=False,
                raw_response=raw_response,
            )

        except Exception as e:
            logger.error(f"Error en AI Generator: {e}")
            return AIGenerationResult(
                workflow={},
                provider=provider_config.provider.value,
                model=provider_config.model,
                explanation=f"Error generando workflow con IA: {e}",
                validated=False,
                validation_errors=[str(e)],
                fallback_used=False,
            )

    def _call_llm(self, text: str, config: ProviderConfig, lang: str) -> str:
        """Llama al LLM según el proveedor configurado."""
        user_prompt = f"Genera un workflow para: {text}" if lang == "es" else f"Generate a workflow for: {text}"

        if config.provider == AIProvider.OLLAMA:
            return self._call_ollama(user_prompt, config)
        elif config.provider == AIProvider.OPENAI:
            return self._call_openai(user_prompt, config)
        elif config.provider == AIProvider.ANTHROPIC:
            return self._call_anthropic(user_prompt, config)
        else:
            raise ValueError(f"Proveedor no soportado: {config.provider}")

    def _call_ollama(self, prompt: str, config: ProviderConfig) -> str:
        """Llama a Ollama API local."""
        import requests

        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
        }

        resp = requests.post(
            f"{config.base_url}/api/chat",
            json=payload,
            timeout=config.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

    def _call_openai(self, prompt: str, config: ProviderConfig) -> str:
        """Llama a OpenAI API."""
        import requests

        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
        }

        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=config.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _call_anthropic(self, prompt: str, config: ProviderConfig) -> str:
        """Llama a Anthropic API."""
        import requests

        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=config.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]

    @staticmethod
    def _parse_workflow(raw: str) -> dict[str, Any] | None:
        """Parsea la respuesta del LLM como workflow JSON."""
        try:
            # Buscar JSON en la respuesta
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                return None

            json_str = raw[start : end + 1]
            parsed = json.loads(json_str)

            if not isinstance(parsed, dict):
                return None

            # Verificar campos mínimos requeridos
            required = {"name", "trigger_type", "steps"}
            if not required.issubset(parsed.keys()):
                return None

            if not isinstance(parsed["steps"], list):
                return None

            return parsed

        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Error parseando workflow del LLM: {e}")
            return None

    @staticmethod
    def _validate_workflow(workflow: dict[str, Any]) -> list[str]:
        """Valida que el workflow generado tenga tools y actions válidas."""
        errors = []

        # Validar name
        if not workflow.get("name"):
            errors.append("Falta 'name' en el workflow")

        # Validar trigger_type
        valid_triggers = {"manual", "schedule", "event", "webhook"}
        if workflow.get("trigger_type") not in valid_triggers:
            errors.append(f"trigger_type inválido: {workflow.get('trigger_type')}")

        # Validar steps
        steps = workflow.get("steps", [])
        if not steps:
            errors.append("El workflow no tiene pasos")

        for i, step in enumerate(steps):
            step_id = step.get("id", i + 1)
            tool = step.get("tool", "")
            action = step.get("action", "")

            if tool not in KNOWN_TOOLS:
                errors.append(f"Paso {step_id}: tool '{tool}' no existe. Disponibles: {', '.join(sorted(KNOWN_TOOLS))}")

            if not action:
                errors.append(f"Paso {step_id}: falta 'action'")

            if not isinstance(step.get("params", {}), dict):
                errors.append(f"Paso {step_id}: 'params' debe ser un dict")

        return errors

    def _generate_explanation(self, workflow: dict[str, Any], lang: str) -> str:
        """Genera explicación del workflow generado por IA."""
        name = workflow.get("name", "Sin nombre")
        trigger = workflow.get("trigger_type", "manual")
        steps = workflow.get("steps", [])

        trigger_text = {
            "manual": "Se ejecutará manualmente",
            "schedule": "Se ejecutará automáticamente",
            "event": "Se activará con un evento",
            "webhook": "Se activará con un webhook externo",
        }.get(trigger, "Se ejecutará")

        parts = [f"Workflow '{name}': {trigger_text}"]

        for step in steps:
            tool = step.get("tool", "?")
            action = step.get("action", "?")
            parts.append(f"  → {tool}.{action}")

        return ". ".join(parts) + "."


# ── Función de conveniencia ──────────────────────────────


def generate_workflow_from_text(text: str, lang: str = "es") -> AIGenerationResult:
    """Función rápida para generar un workflow con IA desde texto libre.

    Args:
        text: Descripción del workflow que el usuario quiere
        lang: Idioma (es/en)

    Returns:
        AIGenerationResult con el workflow y metadata
    """
    generator = WorkflowAIGenerator()
    return generator.generate(text, lang)
