"""
DDE v3 — DryRunSimulator (Etapa 12)

Simula la ejecución de un workflow sin ejecutar las herramientas reales.
Produce un reporte de qué haría cada paso, con datos simulados
y posibles problemas detectados.

Uso:
  - Previsualización antes de activar un workflow
  - Testing de workflows nuevos
  - Debug de configuraciones incorrectas

Determinista: mismo workflow + mismos datos → mismo resultado de simulación.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DryRunStep:
    """Resultado de simular un paso individual."""

    step_id: int
    tool: str
    action: str
    params: dict[str, Any]
    simulated_output: dict[str, Any]
    would_succeed: bool
    warnings: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class DryRunResult:
    """Resultado completo de la simulación."""

    workflow_name: str
    trigger_type: str
    trigger_config: dict[str, Any]
    steps: tuple[DryRunStep, ...]
    total_steps: int
    steps_that_would_succeed: int
    steps_that_would_fail: int
    warnings: tuple[str, ...]
    overall_feasible: bool
    summary: str


# ── Simuladores por tool/action ────────────────────────────

SIMULATED_OUTPUTS: dict[str, dict[str, dict]] = {
    "crm": {
        "create_lead": {
            "id": 999,
            "name": "[SIMULADO]",
            "email": "[SIMULADO]",
            "status": "created",
        },
        "update_lead": {
            "id": 999,
            "status": "updated",
        },
        "get_lead": {
            "id": 999,
            "name": "[SIMULADO]",
            "status": "found",
        },
        "advance_stage": {
            "id": 999,
            "stage": "contacted",
            "status": "advanced",
        },
    },
    "notification": {
        "send_email": {
            "status": "sent",
            "to": "[SIMULADO]",
            "message_id": "sim-001",
        },
        "send_notification": {
            "status": "sent",
            "channel": "[SIMULADO]",
        },
        "send_birthday_emails": {
            "status": "sent",
            "count": 0,
        },
    },
    "inventory": {
        "get_low_stock_products": {
            "count": 0,
            "products": [],
        },
        "update_stock": {
            "status": "updated",
            "new_stock": 0,
        },
    },
    "invoice": {
        "generate_pending": {
            "count": 0,
            "invoices": [],
        },
        "get_overdue_invoices": {
            "count": 0,
            "invoices": [],
        },
        "create_invoice": {
            "id": 999,
            "number": "SIM-001",
            "total": 0.0,
            "status": "created",
        },
    },
    "system": {
        "backup_database": {
            "status": "completed",
            "path": "/simulated/backup.db",
        },
    },
    "logic_gate": {
        "evaluate_rule": {
            "result": True,
            "rule": "[SIMULADO]",
        },
    },
}

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
}


class DryRunSimulator:
    """Simula ejecución de workflows sin ejecutar tools reales."""

    def simulate(self, workflow: dict[str, Any], context: dict[str, Any] | None = None) -> DryRunResult:
        """Simula la ejecución de un workflow.

        Args:
            workflow: Definición del workflow (dict con name, trigger_type, trigger_config, steps)
            context: Datos de contexto simulados (trigger_data, etc.)

        Returns:
            DryRunResult con el reporte de simulación
        """
        workflow_name = workflow.get("name", "Sin nombre")
        trigger_type = workflow.get("trigger_type", "manual")
        trigger_config = dict(workflow.get("trigger_config", {}))
        raw_steps = workflow.get("steps", [])

        all_warnings: list[str] = []
        sim_steps: list[DryRunStep] = []

        # Validar trigger
        trigger_warnings = self._validate_trigger(trigger_type, trigger_config)
        all_warnings.extend(trigger_warnings)

        # Simular cada paso
        for raw_step in raw_steps:
            step_id = raw_step.get("id", 0)
            tool = raw_step.get("tool", "")
            action = raw_step.get("action", "")
            params = dict(raw_step.get("params", {}))

            sim_step = self._simulate_step(step_id, tool, action, params)
            sim_steps.append(sim_step)
            all_warnings.extend(sim_step.warnings)

        total = len(sim_steps)
        success = sum(1 for s in sim_steps if s.would_succeed)
        fail = total - success
        feasible = fail == 0

        summary = self._build_summary(workflow_name, total, success, fail, feasible)

        return DryRunResult(
            workflow_name=workflow_name,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            steps=tuple(sim_steps),
            total_steps=total,
            steps_that_would_succeed=success,
            steps_that_would_fail=fail,
            warnings=tuple(all_warnings),
            overall_feasible=feasible,
            summary=summary,
        )

    def _simulate_step(
        self,
        step_id: int,
        tool: str,
        action: str,
        params: dict[str, Any],
    ) -> DryRunStep:
        """Simula un paso individual."""
        warnings: list[str] = []

        # Validar tool conocida
        if tool not in KNOWN_TOOLS:
            return DryRunStep(
                step_id=step_id,
                tool=tool,
                action=action,
                params=params,
                simulated_output={},
                would_succeed=False,
                warnings=(),
                error=f"Tool '{tool}' no reconocida",
            )

        # Buscar simulación
        tool_sims = SIMULATED_OUTPUTS.get(tool, {})
        sim_output = tool_sims.get(action)

        if sim_output is None:
            warnings.append(f"Paso {step_id}: acción '{action}' no tiene simulación conocida")
            sim_output = {"status": "simulated_no_data"}

        # Verificar variables sin resolver
        unresolved = self._check_unresolved_refs(params)
        if unresolved:
            warnings.append(f"Paso {step_id}: variables sin resolver: {', '.join(unresolved)}")

        return DryRunStep(
            step_id=step_id,
            tool=tool,
            action=action,
            params=params,
            simulated_output=dict(sim_output),
            would_succeed=True,
            warnings=tuple(warnings),
            error=None,
        )

    def _validate_trigger(self, trigger_type: str, config: dict[str, Any]) -> list[str]:
        """Valida la configuración del trigger."""
        warnings: list[str] = []

        if trigger_type == "schedule":
            cron = config.get("cron", "")
            if not cron:
                warnings.append("Trigger schedule sin expresión cron")
            elif not self._valid_cron(cron):
                warnings.append(f"Expresión cron inválida: '{cron}'")

        elif trigger_type == "event":
            event = config.get("event", "")
            if not event:
                warnings.append("Trigger event sin nombre de evento")

        elif trigger_type == "webhook":
            if not config.get("path") and not config.get("url"):
                warnings.append("Trigger webhook sin path configurado")

        return warnings

    def _valid_cron(self, expr: str) -> bool:
        """Valida que una expresión cron tenga 5 campos."""
        parts = expr.strip().split()
        return len(parts) == 5

    def _check_unresolved_refs(self, params: dict[str, Any]) -> list[str]:
        """Detecta variables $xxx sin resolver en params."""
        unresolved: list[str] = []
        for key, value in params.items():
            if isinstance(value, str):
                for prefix in ("$input.", "$output.", "$slot.", "$settings.", "$steps."):
                    if value.startswith(prefix):
                        unresolved.append(f"${key}={value}")
        return unresolved

    def _build_summary(
        self,
        name: str,
        total: int,
        success: int,
        fail: int,
        feasible: bool,
    ) -> str:
        """Construye un resumen legible."""
        if total == 0:
            return f"'{name}': sin pasos definidos."
        status = "✅ factible" if feasible else "❌ tiene problemas"
        return f"'{name}': {total} pasos simulados, {success} ok, {fail} fallarían. {status}."
