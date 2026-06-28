"""
DDE v3 — Validator (Etapa 10)

Valida que un workflow compilado sea correcto antes de persistirlo.
Verifica tipos de trigger, referencias a slots, unicidad de IDs,
existencia de tools, y detecta ciclos.

Determinista: mismo workflow → mismos errores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Tools conocidas por el sistema
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

VALID_TRIGGER_TYPES = {"event", "schedule", "webhook", "manual"}

VALID_ACTIONS_BY_TOOL: dict[str, set[str]] = {
    "crm": {"create_lead", "update_lead", "get_lead", "list_leads"},
    "invoice": {"get_invoice", "get_overdue_invoices", "create_invoice", "send_invoice"},
    "inventory": {"get_low_stock_products", "get_product", "update_stock"},
    "notification": {"send_email", "send_notification", "send_birthday_emails", "send_sms", "send_whatsapp"},
    "system": {"backup_database", "run_script", "send_log"},
    "autopilot": {"execute", "analyze"},
    "logic_gate": {"evaluate", "compare"},
    "api_connector": {"get", "post", "put", "delete"},
    "data_keeper": {"save", "load", "delete"},
    "code_runner": {"run_python", "validate"},
    "gmail": {"send_email", "search_emails", "get_message", "list_labels"},
    "sheets": {"read_sheet", "write_sheet", "append_row", "update_cell", "create_spreadsheet"},
    "telegram": {"send_message", "send_photo", "get_updates", "get_chat"},
    "slack": {"send_message", "list_channels", "upload_file", "get_user_info"},
}


@dataclass(frozen=True)
class ValidationResult:
    """Resultado de la validación de un workflow."""

    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


class WorkflowValidator:
    """Valida definiciones de workflow compiladas."""

    def validate(self, workflow: dict[str, Any]) -> ValidationResult:
        """Valida un workflow completo.

        Args:
            workflow: Dict con keys (name, description, trigger_type,
                      trigger_config, steps)

        Returns:
            ValidationResult con errors y warnings
        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Validar estructura básica
        if not workflow:
            return ValidationResult(
                valid=False,
                errors=("Workflow vacío",),
                warnings=(),
            )

        if "name" not in workflow or not workflow.get("name"):
            errors.append("Falta el nombre del workflow")

        # 2. Validar trigger
        trigger_type = workflow.get("trigger_type", "")
        if not trigger_type:
            errors.append("Falta el tipo de trigger")
        elif trigger_type not in VALID_TRIGGER_TYPES:
            errors.append(f"Tipo de trigger inválido: '{trigger_type}'")

        trigger_config = workflow.get("trigger_config", {})
        if trigger_type == "event" and "event" not in trigger_config:
            errors.append("Trigger 'event' requiere config.event")
        if trigger_type == "schedule" and "cron" not in trigger_config:
            errors.append("Trigger 'schedule' requiere config.cron")

        # 3. Validar steps
        steps = workflow.get("steps", [])
        if not steps:
            warnings.append("El workflow no tiene pasos definidos")

        seen_ids: set[int] = set()
        for i, step in enumerate(steps):
            # Validar ID
            step_id = step.get("id", i + 1)
            if step_id in seen_ids:
                errors.append(f"ID duplicado: {step_id}")
            seen_ids.add(step_id)

            # Validar tool
            tool = step.get("tool", "")
            if not tool:
                errors.append(f"Paso {step_id}: falta 'tool'")
            elif tool not in KNOWN_TOOLS:
                warnings.append(f"Paso {step_id}: tool desconocida '{tool}'")

            # Validar action
            action = step.get("action", "")
            if not action:
                errors.append(f"Paso {step_id}: falta 'action'")
            elif tool in VALID_ACTIONS_BY_TOOL:
                valid_actions = VALID_ACTIONS_BY_TOOL[tool]
                if action not in valid_actions:
                    warnings.append(f"Paso {step_id}: action '{action}' no es estándar para '{tool}'")

            # Validar params
            params = step.get("params", {})
            if not isinstance(params, dict):
                errors.append(f"Paso {step_id}: 'params' debe ser un dict")

            # Detectar referencias $slot sin resolver
            self._check_unresolved_refs(params, f"Paso {step_id}", errors)

        # 4. Detectar ciclos en steps (auto-referencia)
        self._detect_cycles(steps, errors)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def _check_unresolved_refs(
        self,
        params: object,
        prefix: str,
        errors: list[str],
    ) -> None:
        """Busca referencias $slot.xxx sin resolver.

        Solo flaggea $slot.xxx como error porque son las unicas
        referencias de compile-time. $intent.xxx, $output.xxx y
        $input.xxx son referencias de runtime (se resuelven durante
        la ejecucion del workflow) y NO deben ser flaggeadas.
        """
        if isinstance(params, str):
            if "$slot." in params:
                errors.append(f"{prefix}: slot sin resolver: '{params}'")
        elif isinstance(params, dict):
            for key, value in params.items():
                self._check_unresolved_refs(value, f"{prefix}.{key}", errors)
        elif isinstance(params, list):
            for i, item in enumerate(params):
                self._check_unresolved_refs(item, f"{prefix}[{i}]", errors)

    def _detect_cycles(
        self,
        steps: list[dict[str, object]],
        errors: list[str],
    ) -> None:
        """Detecta ciclos simples en steps (auto-referencia)."""
        # Por ahora detectamos auto-referencias en params
        for step in steps:
            params = step.get("params", {})
            # Si un paso se referencia a sí mismo por ID
            step_id = step.get("id")
            if isinstance(params, dict):
                for value in params.values():
                    if isinstance(value, str) and f"$steps.{step_id}" in value:
                        errors.append(f"Paso {step_id}: auto-referencia detectada")

    def validate_slot_completeness(
        self,
        workflow: dict[str, Any],
        required_slots: tuple[str, ...],
    ) -> ValidationResult:
        """Valida que un workflow tenga todos los slots requeridos.

        Args:
            workflow: Dict del workflow compilado
            required_slots: Slots que deben estar resueltos

        Returns:
            ValidationResult
        """
        errors: list[str] = []
        if not workflow:
            return ValidationResult(valid=False, errors=("Workflow vacío",), warnings=())

        # Verificar que los slots requeridos no aparezcan como $slot.xxx
        params_str = str(workflow)
        for slot_name in required_slots:
            placeholder = f"$slot.{slot_name}"
            if placeholder in params_str:
                errors.append(f"Slot '{slot_name}' no resuelto (referencia '{placeholder}' no reemplazada)")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=(),
        )
