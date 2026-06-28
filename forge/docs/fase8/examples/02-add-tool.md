# Ejemplo 02: Añadir Tool N4 (Notificaciones Slack)

> **Tiempo estimado**: 45 minutos
> **Stack**: Python + TypeScript
> **Blast radius**: Medium (3 archivos nuevos + 2 modificados)

---

## 🎯 Objetivo

Añadir una nueva tool N4 (Level 4 Worker) para enviar notificaciones a Slack desde el HAT.

---

## Fase 1: SPECIFY

```bash
python -m forge ledger init .forge/add-slack-tool --run-id "feature-slack-notifications"
```

```python
from forge import RunLedger
ledger = RunLedger(".forge/add-slack-tool", run_id="feature-slack-notifications")
ledger.set_spec("""
Feature: Añadir SlackNotificationTool al HAT Level 4 Workers.

Requisitos:
- WHEN el specialist de comunicaciones recibe un subtask de notificación Slack,
  THE SYSTEM SHALL enviar el mensaje via Slack API.
- IF el canal no existe, THE SYSTEM SHALL devolver error con código 'channel_not_found'.
- WHILE el token de Slack sea válido, THE SYSTEM SHALL permitir múltiples envíos.

Criterio de salida:
- tests_pass: tests unitarios del worker pasan
- lint_clean: ruff clean
- types_clean: mypy clean en archivos nuevos
- no_security_issues: 0 HIGH (token via env, no hardcodeado)
""")
ledger.add_approval("specify", approved_by="human")
```

---

## Fase 2: PLAN

### Archivos a crear/modificar

| # | Acción | Archivo | Descripción |
|---|---|---|---|
| 1 | create_file | `src/hat/level4_workers/comunicaciones/slack/__init__.py` | Package init |
| 2 | create_file | `src/hat/level4_workers/comunicaciones/slack/worker.py` | SlackNotificationWorker |
| 3 | edit_file | `src/hat/level4_workers/comunicaciones/__init__.py` | Registrar worker |
| 4 | create_file | `src/tests/hat/hardened/test_slack_worker.py` | Tests unitarios |
| 5 | edit_file | `frontend/src/types/notifications.ts` | Añadir tipo SlackNotification |

```python
ledger.add_action(
    action_type="run_test",
    target="plan-detection",
    diff_summary="Stack: python+typescript, blast_radius: medium (3 nuevos + 2 editados)",
    rollback="",
)
ledger.add_approval("plan", approved_by="auto")
```

---

## Fase 3-4: TASKS + IMPLEMENT

### Task 1: Crear SlackNotificationWorker

```python
# src/hat/level4_workers/comunicaciones/slack/worker.py
from __future__ import annotations

import os
from typing import Any

import requests

from src.hat.level4_workers.base.tool_worker import ToolWorker
from src.hat.level4_workers.base.registry import register_worker


@register_worker("slack_notification")
class SlackNotificationWorker(ToolWorker):
    """Worker para enviar notificaciones a Slack via Web API."""

    @property
    def tool_name(self) -> str:
        return "slack_notification"

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        channel = params.get("channel", "#general")
        message = params.get("message", "")
        token = os.environ.get("SLACK_BOT_TOKEN")

        if not token:
            return {"status": "error", "error": "SLACK_BOT_TOKEN not set"}

        if not message:
            return {"status": "error", "error": "message is required"}

        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": channel, "text": message},
            timeout=30,
        )
        data = response.json()

        if not data.get("ok"):
            return {"status": "error", "error": data.get("error", "unknown")}

        return {"status": "ok", "channel": channel, "ts": data.get("ts")}
```

```python
ledger.add_action(
    action_type="create_file",
    target="src/hat/level4_workers/comunicaciones/slack/worker.py",
    diff_summary="Crear SlackNotificationWorker con execute() que envía a Slack API",
    before_sha="",
    after_sha="abc123",
    rollback="git rm src/hat/level4_workers/comunicaciones/slack/worker.py",
)
```

### Task 2: Crear `__init__.py`

```python
# src/hat/level4_workers/comunicaciones/slack/__init__.py
from src.hat.level4_workers.comunicaciones.slack.worker import SlackNotificationWorker

__all__ = ["SlackNotificationWorker"]
```

### Task 3: Registrar worker en `comunicaciones/__init__.py`

```python
# Añadir import al final del __init__.py existente
from src.hat.level4_workers.comunicaciones.slack import SlackNotificationWorker  # noqa: F401
```

### Task 4: Tests unitarios

```python
# src/tests/hat/hardened/test_slack_worker.py
from unittest.mock import patch, MagicMock

from src.hat.level4_workers.comunicaciones.slack.worker import SlackNotificationWorker


class TestSlackNotificationWorker:
    def test_execute_sends_message(self):
        worker = SlackNotificationWorker()
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test"}), \
             patch("requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"ok": True, "ts": "1234567890.123"}
            result = worker.execute({"channel": "#general", "message": "Hello"})
            assert result["status"] == "ok"
            assert result["ts"] == "1234567890.123"

    def test_execute_without_token_returns_error(self):
        worker = SlackNotificationWorker()
        with patch.dict("os.environ", {}, clear=True):
            result = worker.execute({"channel": "#general", "message": "Hello"})
            assert result["status"] == "error"
            assert "SLACK_BOT_TOKEN" in result["error"]

    def test_execute_without_message_returns_error(self):
        worker = SlackNotificationWorker()
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test"}):
            result = worker.execute({"channel": "#general", "message": ""})
            assert result["status"] == "error"
            assert "message" in result["error"]

    def test_execute_slack_api_error(self):
        worker = SlackNotificationWorker()
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test"}), \
             patch("requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"ok": False, "error": "channel_not_found"}
            result = worker.execute({"channel": "#invalid", "message": "Hello"})
            assert result["status"] == "error"
            assert result["error"] == "channel_not_found"
```

### Task 5: Añadir tipo TypeScript

```typescript
// frontend/src/types/notifications.ts — añadir al final
export interface SlackNotification {
  channel: string
  message: string
  ts?: string
}
```

```python
ledger.add_approval("implement", approved_by="auto", notes="5 tasks implementadas")
```

---

## Fase 5: VERIFY

```bash
# Ejecutar tests del nuevo worker
python -m pytest src/tests/hat/hardened/test_slack_worker.py -v

# Ejecutar gates sobre el módulo afectado
python -m forge check-module src/hat/level4_workers/comunicaciones/slack/

# Verificar TypeScript
cd frontend && npx tsc --noEmit -p tsconfig.app.json && cd ..
```

```python
ledger.add_gate_result("tests_pass", passed=True, evidence="4 tests passed")
ledger.add_gate_result("lint_clean", passed=True, evidence="ruff: 0 issues")
ledger.add_gate_result("no_security_issues", passed=True, evidence="0 HIGH (token via env)")
ledger.add_approval("verify", approved_by="auto")
```

---

## Fase 8: FINAL_VERIFY + Entrega

```python
ledger.set_soft_score(9.0)
summary = ledger.complete(status="pass")
```

```bash
python -m forge ledger verify .forge/add-slack-tool/run_ledger.json
git add -A
git commit -m "feat: add SlackNotificationTool to HAT Level 4 (ledger: .forge/add-slack-tool)"
git push origin feature/slack-notifications
```

---

## 📊 Resultado

| Métrica | Valor |
|---|---|
| Tiempo total | 35 min |
| Archivos nuevos | 3 |
| Archivos modificados | 2 |
| Tests añadidos | 4 |
| Gates PASS | 6/6 hard |
| Score | 9.0/10 |
| Security | Token via `os.environ` (no hardcodeado) ✅ |

---

## 🎓 Lección registrada en memoria

```python
mem.add_reflection(
    iteration_id="add-slack-tool",
    summary="Añadido SlackNotificationWorker al HAT Level 4",
    verbal_reflection="Patrón: crear worker en src/hat/level4_workers/<domain>/<tool>/worker.py...",
    score=9.0,
    key_learnings=[
        "Workers Level 4 heredan de ToolWorker y se registran via @register_worker decorator",
        "Token de API siempre via os.environ, nunca hardcodeado (security gate)",
        "Tests con patch.dict('os.environ', ...) para mock de env vars",
        "Requests.post con timeout=30 para evitar hangs en API externa",
    ],
)
```
