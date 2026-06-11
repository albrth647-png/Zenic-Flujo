"""
DDE v3 — Explainer (Etapa 11)

Traduce un workflow compilado a una explicación en lenguaje natural.
Usa los templates de descripción + descripciones de acciones.

Determinista: mismo workflow → misma explicación.
"""

from __future__ import annotations

from src.nlu.entities.base import CompileResult
from src.nlu.templates import TEMPLATES


def explain_intent(intent_name: str, lang: str = "es") -> str:
    """Genera una explicación corta de una intención.

    Args:
        intent_name: Nombre de la intención
        lang: Idioma ('es' o 'en')

    Returns:
        Frase explicativa en lenguaje natural
    """
    templates_map = {t["name"]: t for t in TEMPLATES}
    template = templates_map.get(intent_name)

    if not template:
        return intent_name if lang != "es" else f"Intención: {intent_name}"

    return template.get(
        f"description_{lang}",
        template.get("description_es", intent_name),
    )


class Explainer:
    """Genera explicaciones en lenguaje natural de workflows."""

    def explain(
        self,
        compile_result: CompileResult,
        lang: str = "es",
    ) -> str:
        """Genera explicación legible de un CompileResult.

        Args:
            compile_result: Resultado de la compilación
            lang: Idioma ('es' o 'en')

        Returns:
            Texto explicativo en lenguaje natural
        """
        if compile_result.status == "unknown":
            if lang == "es":
                return "No se pudo determinar la intención del mensaje."
            return "Could not determine the intent of the message."

        if compile_result.status == "needs_clarification":
            missing = compile_result.missing_slots
            if lang == "es":
                slot_names_es = {
                    "nombre": "nombre del cliente",
                    "email_destino": "correo electrónico",
                    "email_cliente": "correo del cliente",
                    "telefono": "teléfono",
                    "url_webhook": "URL del webhook",
                    "frecuencia": "frecuencia",
                    "email_admin": "correo del administrador",
                    "umbral_stock": "umbral de stock",
                    "carpeta": "carpeta",
                }
                labels = [slot_names_es.get(s, s) for s in missing]
                return (
                    f"Falta información obligatoria: {', '.join(labels)}. Por favor, proporciona los datos faltantes."
                )
            return f"Missing required information: {', '.join(missing)}. Please provide the missing data."

        if compile_result.status == "ambiguous":
            if lang == "es":
                return "Hay varias posibles interpretaciones. Por favor, sé más específico."
            return "There are several possible interpretations. Please be more specific."

        # Status: ready — explicar el workflow
        if compile_result.explanation:
            return compile_result.explanation

        workflow = compile_result.workflow
        if not workflow:
            if lang == "es":
                return "Workflow vacío."
            return "Empty workflow."

        return self._explain_workflow(workflow, lang)

    def _explain_workflow(self, workflow: dict, lang: str) -> str:
        """Genera explicación detallada de un workflow."""
        parts: list[str] = []

        name = workflow.get("name", "")
        trigger_type = workflow.get("trigger_type", "manual")
        trigger_config = workflow.get("trigger_config", {})
        steps = workflow.get("steps", [])

        # Título
        if name:
            if lang == "es":
                parts.append(f"Workflow: {name}")
            else:
                parts.append(f"Workflow: {name}")

        # Trigger
        if lang == "es":
            trigger_texts = {
                "event": "Disparador: evento",
                "schedule": "Disparador: programación",
                "webhook": "Disparador: webhook externo",
                "manual": "Disparador: manual",
            }
        else:
            trigger_texts = {
                "event": "Trigger: event",
                "schedule": "Trigger: schedule",
                "webhook": "Trigger: external webhook",
                "manual": "Trigger: manual",
            }

        trigger_line = trigger_texts.get(trigger_type, f"Trigger: {trigger_type}")
        if trigger_type == "event" and "event" in trigger_config:
            trigger_line += f" '{trigger_config['event']}'"
        elif trigger_type == "schedule" and "cron" in trigger_config:
            trigger_line += f" ({trigger_config['cron']})"
        parts.append(trigger_line)

        # Steps
        if steps:
            if lang == "es":
                parts.append("Pasos:")
            else:
                parts.append("Steps:")
            for step in steps:
                step_id = step.get("id", "")
                tool = step.get("tool", "")
                action = step.get("action", "")
                params = step.get("params", {})

                action_descriptions_es = {
                    "create_lead": "Registrar lead en CRM",
                    "send_email": "Enviar correo",
                    "send_notification": "Enviar notificación",
                    "send_birthday_emails": "Enviar correos de cumpleaños",
                    "get_low_stock_products": "Consultar productos con stock bajo",
                    "get_overdue_invoices": "Consultar facturas vencidas",
                    "get_invoice": "Consultar factura",
                    "backup_database": "Hacer backup de BD",
                }
                action_descriptions_en = {
                    "create_lead": "Create lead in CRM",
                    "send_email": "Send email",
                    "send_notification": "Send notification",
                    "send_birthday_emails": "Send birthday emails",
                    "get_low_stock_products": "Get low stock products",
                    "get_overdue_invoices": "Get overdue invoices",
                    "get_invoice": "Get invoice",
                    "backup_database": "Back up database",
                }

                descs = action_descriptions_es if lang == "es" else action_descriptions_en
                action_desc = descs.get(action, f"{tool}/{action}")

                # Agregar detalles de params
                param_details = []
                for pkey, pval in params.items():
                    if pval and pval != "":
                        param_details.append(f"{pkey}={pval}")
                param_str = f" ({', '.join(param_details)})" if param_details else ""

                parts.append(f"  {step_id}. {action_desc}{param_str}")

        return "\n".join(parts)
