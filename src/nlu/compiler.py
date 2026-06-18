"""
DDE v3 — WorkflowCompiler (Etapa 9)

Ensambla fragmentos de workflow en una definición completa.
Toma la intención ganadora + slots resueltos y produce un dict
compatible con WorkflowDefinition (src/workflow/repository.py).

Determinista: mismo intent + mismos slots + mismas entidades → mismo workflow.
"""

from __future__ import annotations

from src.nlu.entities.base import CompileResult, Entity, Slot
from src.nlu.fragments import get_fragments_by_intent
from src.nlu.templates import TEMPLATES

# Tools conocidas para validación suave
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

# Mapeo tipo trigger → trigger_type string
TRIGGER_TYPE_MAP = {
    "event": "event",
    "schedule": "schedule",
    "webhook": "webhook",
}

# Mapeo intent_name → event name real (para resolver $intent_event)
INTENT_EVENTS: dict[str, str] = {
    "registro_cliente": "crm.lead.created",
    "lead_avanzar_etapa": "crm.lead.stage_changed",
    "factura_vencida": "invoice.overdue",
    "producto_agotado": "inventory.stock_out",
    "archivo_nuevo": "file.created",
    # Nuevos intents v2.0
    "email_lead_nuevo": "crm.lead.created",
    "whatsapp_lead_nuevo": "crm.lead.created",
    "lead_cualificado_ventas": "crm.lead.stage_changed",
    "lead_perdido_analisis": "crm.lead.stage_changed",
    "email_pago_recibido": "payment.received",
    "factura_pagada_thankyou": "invoice.paid",
    "alerta_precio_cambio": "inventory.price_changed",
    "confirmacion_pedido": "order.created",
    "encuesta_satisfaccion": "crm.lead.stage_changed",
}


class WorkflowCompiler:
    """Compila fragmentos + slots en una definición de workflow."""

    def compile(
        self,
        intent_name: str,
        slots: tuple[Slot, ...],
        entities: tuple[Entity, ...],
        lang: str = "es",
    ) -> CompileResult:
        """Compila un workflow desde intención y slots.

        Args:
            intent_name: Nombre de la intención ganadora
            slots: Slots llenados (con valores o vacíos)
            entities: Entidades extraídas (contexto adicional)
            lang: Idioma para descripciones

        Returns:
            CompileResult con workflow, explanation y status
        """
        # 1. Buscar template metadata
        template = self._find_template(intent_name)
        if template is None:
            return CompileResult(
                workflow={},
                explanation="",
                missing_slots=(),
                status="unknown",
            )

        # 2. Obtener fragmentos para esta intención
        fragments = get_fragments_by_intent(intent_name)

        # 3. Separar triggers y steps
        trigger_fragments = [f for f in fragments if f.kind == "trigger"]
        step_fragments = [f for f in fragments if f.kind == "step"]

        # 4. Construir slot lookup
        slot_map: dict[str, object] = {}
        for s in slots:
            if s.filled and s.value is not None:
                slot_map[s.name] = s.value

        # 5. Verificar slots requeridos faltantes
        required_slot_names: set[str] = set()
        for f in fragments:
            required_slot_names.update(f.requires_slots)
        missing = tuple(name for name in required_slot_names if name not in slot_map or slot_map[name] is None)
        if missing:
            return CompileResult(
                workflow={},
                explanation="",
                missing_slots=missing,
                status="needs_clarification",
            )

        # 6. Construir trigger
        trigger_type = "manual"
        trigger_config: dict[str, object] = {}

        if trigger_fragments:
            best_trigger = trigger_fragments[0]
            trigger_type = TRIGGER_TYPE_MAP.get(best_trigger.produces.get("type", ""), "manual")
            trigger_config = dict(best_trigger.produces.get("config", {}))
            # Resolver $slot.xxx y $intent_event en trigger config
            trigger_config = self._resolve_slots(trigger_config, slot_map)
            trigger_config = self._resolve_intent_refs(trigger_config, intent_name)

        # 7. Construir steps desde fragmentos
        steps: list[dict[str, object]] = []
        for idx, frag in enumerate(step_fragments, start=1):
            produces = dict(frag.produces)
            step: dict[str, object] = {
                "id": idx,
                "tool": produces.get("tool", ""),
                "action": produces.get("action", ""),
                "params": self._resolve_slots(
                    dict(produces.get("params", {})),
                    slot_map,
                ),
            }
            steps.append(step)

        # 8. Fallback: si no hay fragmentos, usar template directamente
        if not steps:
            trigger_config_raw = template.get("trigger", {})
            trigger_type = trigger_config_raw.get("type", "manual")
            trigger_config = dict(trigger_config_raw.get("config", {}))
            trigger_config = self._resolve_slots(trigger_config, slot_map)
            trigger_config = self._resolve_intent_refs(trigger_config, intent_name)

            raw_steps = template.get("steps", [])
            for raw_step in raw_steps:
                step = dict(raw_step)
                step["params"] = self._resolve_slots(
                    dict(step.get("params", {})),
                    slot_map,
                )
                steps.append(step)

        # 9. Construir descripción
        description_key = f"description_{lang}" if lang in ("es", "en") else "description_es"
        description = template.get(description_key, template.get("description_es", ""))

        # 10. Armar workflow dict
        workflow: dict[str, object] = {
            "name": template.get("label", intent_name),
            "description": description,
            "trigger_type": trigger_type,
            "trigger_config": trigger_config,
            "steps": steps,
        }

        # 11. Generar explicación
        explanation = self._generate_explanation(template, trigger_type, trigger_config, steps, slot_map, lang)

        return CompileResult(
            workflow=workflow,
            explanation=explanation,
            missing_slots=(),
            status="ready",
        )

    def _find_template(self, intent_name: str) -> dict | None:
        """Busca el template por nombre de intención."""
        for t in TEMPLATES:
            if t["name"] == intent_name:
                return t
        return None

    def _resolve_slots(
        self,
        target: dict[str, object],
        slot_map: dict[str, object],
    ) -> dict[str, object]:
        """Resuelve referencias $slot.xxx en un dict.

        Reemplaza strings que contienen $slot.xxx con el valor del slot.
        También resuelve $settings.xxx usando defaults conocidos.
        Si no encuentra el slot, deja el placeholder intacto.
        """
        settings_defaults: dict[str, str] = {
            "admin_email": "admin@corp.com",
            "admin_phone": "+1234567890",
            "telegram_chat_id": "",
            "shopify_url": "",
        }

        def _resolve_string(s: str) -> str:
            """Resuelve $slot.x y $settings.x recursivamente en un string."""
            if "$slot." in s:
                slot_name = s.replace("$slot.", "").strip()
                slot_value = slot_map.get(slot_name, s)
                if isinstance(slot_value, str) and "$settings." in slot_value:
                    setting_name = slot_value.replace("$settings.", "").strip()
                    return settings_defaults.get(setting_name, slot_value)
                if isinstance(slot_value, str):
                    return slot_value
                return str(slot_value)
            if "$settings." in s:
                setting_name = s.replace("$settings.", "").strip()
                return settings_defaults.get(setting_name, s)
            return s

        resolved: dict[str, object] = {}
        for key, value in target.items():
            if isinstance(value, str) and ("$slot." in value or "$settings." in value):
                resolved[key] = _resolve_string(value)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_slots(value, slot_map)
            elif isinstance(value, list):
                resolved[key] = [self._resolve_slots(v, slot_map) if isinstance(v, dict) else v for v in value]
            else:
                resolved[key] = value
        return resolved

    def _resolve_intent_refs(
        self,
        target: dict[str, object],
        intent_name: str,
    ) -> dict[str, object]:
        """Resuelve referencias $intent_event en un dict."""
        event_name = INTENT_EVENTS.get(intent_name, "")
        resolved: dict[str, object] = {}
        for key, value in target.items():
            if isinstance(value, str) and "$intent_event" in value:
                resolved[key] = event_name or value
            elif isinstance(value, dict):
                resolved[key] = self._resolve_intent_refs(value, intent_name)
            elif isinstance(value, list):
                resolved[key] = [self._resolve_intent_refs(v, intent_name) if isinstance(v, dict) else v for v in value]
            else:
                resolved[key] = value
        return resolved

    def _generate_explanation(
        self,
        template: dict,
        trigger_type: str,
        trigger_config: dict[str, object],
        steps: list[dict[str, object]],
        slot_map: dict[str, object],
        lang: str,
    ) -> str:
        """Genera explicación en lenguaje natural del workflow compilado."""
        parts: list[str] = []

        # Descripción del trigger
        trigger_explanations = {
            "event": "Cuando ocurra el evento",
            "schedule": "Se ejecutará automáticamente según el horario programado",
            "webhook": "Cuando se reciba un webhook externo",
            "manual": "Se ejecutará manualmente",
        }
        trigger_text = trigger_explanations.get(trigger_type, "Se ejecutará")
        if trigger_type == "schedule" and "cron" in trigger_config:
            trigger_text = f"Se ejecutará con la frecuencia: {trigger_config['cron']}"
        elif trigger_type == "event":
            event_name = trigger_config.get("event", "")
            if event_name:
                trigger_text = f"Cuando ocurra el evento '{event_name}'"

        parts.append(trigger_text)

        # Steps
        for step in steps:
            tool = step.get("tool", "")
            action = step.get("action", "")
            params = step.get("params", {})

            step_text = self._describe_step(tool, action, params, lang)
            parts.append(step_text)

        return ". ".join(parts) + "."

    def _describe_step(
        self,
        tool: str,
        action: str,
        params: dict[str, object],
        lang: str,
    ) -> str:
        """Describe un paso individual en lenguaje natural."""
        # Acciones conocidas con descripciones en español
        action_descriptions_es: dict[str, str] = {
            "create_lead": "registrar lead en CRM",
            "send_email": "enviar correo",
            "send_notification": "enviar notificación",
            "send_birthday_emails": "enviar correos de cumpleaños",
            "get_low_stock_products": "consultar productos con stock bajo",
            "get_overdue_invoices": "consultar facturas vencidas",
            "get_invoice": "consultar factura",
            "backup_database": "hacer backup de base de datos",
        }
        action_descriptions_en: dict[str, str] = {
            "create_lead": "create lead in CRM",
            "send_email": "send email",
            "send_notification": "send notification",
            "send_birthday_emails": "send birthday emails",
            "get_low_stock_products": "get low stock products",
            "get_overdue_invoices": "get overdue invoices",
            "get_invoice": "get invoice",
            "backup_database": "back up database",
        }

        descriptions = action_descriptions_es if lang == "es" else action_descriptions_en
        base = descriptions.get(action, f"{tool}/{action}")

        # Agregar detalles de params relevantes
        extra: list[str] = []
        to_val = params.get("to")
        if to_val:
            extra.append(f"a {to_val}")
        subject_val = params.get("subject")
        if subject_val:
            extra.append(f"asunto: {subject_val}")

        if extra:
            return f"{base} ({', '.join(extra)})"
        return base
