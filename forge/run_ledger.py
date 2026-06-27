"""
Run Ledger v1.0 — Zenic-Flujo Edition
======================================
Registro compacto que viaja con cada task del agente.
Cada acción debe tener rollback definido ANTES de ejecutarse.
Sin ledger completo → NO hay entrega.

Basado en: developersdigest "Permissions, Logs, Rollback for AI Coding Agents"

Uso:
    from forge import RunLedger
    ledger = RunLedger("/tmp/workdir")
    ledger.add_action("edit_file", "src/main.py", rollback="git checkout src/main.py")
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import NotRequired, TypedDict, cast


class LedgerAction(TypedDict):
    action_type: str
    permission: str
    target: str
    diff_summary: str
    before_sha: str
    after_sha: str
    rollback: str
    verified: bool
    timestamp: str
    rolled_back: NotRequired[bool]
    rollback_reason: NotRequired[str]


class Approval(TypedDict):
    phase: str
    approved_by: str
    timestamp: str
    notes: str


class GateProof(TypedDict):
    gate_name: str
    passed: bool
    evidence: str
    stack: str
    timestamp: str


class LedgerMetadata(TypedDict):
    hard_gates_passed: int
    soft_score: float
    total_files_changed: int
    rollbacks_executed: int
    canary_fixes_applied: int


class LedgerData(TypedDict, total=False):
    run_id: str
    spec: str
    created_at: str
    updated_at: str
    actions: list[LedgerAction]
    approvals: list[Approval]
    proof: list[GateProof]
    final_status: str
    metadata: LedgerMetadata
    completed_at: str
    rolled_back: bool
    rollback_reason: str


class LedgerSummary(TypedDict):
    run_id: str
    spec: str
    final_status: str
    total_actions: int
    verified_actions: int
    rolled_back: int
    hard_gates_passed: int
    soft_score: float
    files_changed: int
    canary_fixes: int
    approvals: int
    proof_count: int
    is_complete: bool


class RunLedger:
    """Run Ledger: permission → action → log → review → rollback."""

    def __init__(self, workdir: str | Path, run_id: str | None = None):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.workdir / "run_ledger.json"

        if run_id is None:
            ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
            run_id = f"zenic-fix-{ts}"

        if self.ledger_path.exists():
            self._load()
            if not self.verify_integrity():
                raise RuntimeError(
                    f"RUN LEDGER CORRUPTED: {self.ledger_path}. "
                    "HALT inmediato — el ledger está corrupto."
                )
        else:
            self.data: LedgerData = {
                "run_id": run_id,
                "spec": "",
                "created_at": datetime.now(tz=UTC).isoformat(),
                "updated_at": datetime.now(tz=UTC).isoformat(),
                "actions": [],
                "approvals": [],
                "proof": [],
                "final_status": "running",
                "metadata": {
                    "hard_gates_passed": 0,
                    "soft_score": 0.0,
                    "total_files_changed": 0,
                    "rollbacks_executed": 0,
                    "canary_fixes_applied": 0,
                },
            }
            self._save()

    # ── Spec ──────────────────────────────────────────────────────────

    def set_spec(self, spec: str) -> None:
        """Registra la SPEC original en el ledger."""
        self.data["spec"] = spec
        self._save()

    # ── Actions ───────────────────────────────────────────────────────

    def add_action(
        self,
        action_type: str,
        target: str,
        permission: str = "allow",
        diff_summary: str = "",
        before_sha: str = "",
        after_sha: str = "",
        rollback: str = "",
    ) -> LedgerAction:
        """Registra una acción del agente con su rollback.

        Args:
            action_type: edit_file | install_dep | run_test | git_commit | etc.
            target: archivo o comando afectado
            permission: allow | ask | deny
            diff_summary: resumen del cambio
            before_sha: git sha antes de la acción
            after_sha: git sha después de la acción
            rollback: cómo deshacer (git checkout | git revert | git stash pop)

        Returns:
            El dict de la acción creada

        Raises:
            ValueError: Si rollback está vacío y la acción es high-risk
        """
        if not rollback and action_type in ("edit_file", "git_commit"):
            raise ValueError(
                f"RUN LEDGER: rollback no definido para {action_type} en {target}. "
                "Si no puedes escribir el rollback, la acción es high-risk → NO ejecutar."
            )

        action = {
            "action_type": action_type,
            "permission": permission,
            "target": target,
            "diff_summary": diff_summary,
            "before_sha": before_sha,
            "after_sha": after_sha,
            "rollback": rollback,
            "verified": False,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        self.data["actions"].append(action)
        self.data["updated_at"] = datetime.now(tz=UTC).isoformat()

        if action_type in ("edit_file",):
            self.data["metadata"]["total_files_changed"] += 1

        self._save()
        return action

    def mark_verified(self, action_index: int) -> None:
        """Marca una acción como verificada."""
        if 0 <= action_index < len(self.data["actions"]):
            self.data["actions"][action_index]["verified"] = True
            self._save()

    def record_rollback(self, action_index: int, reason: str = "") -> None:
        """Registra que se ejecutó un rollback."""
        if 0 <= action_index < len(self.data["actions"]):
            self.data["actions"][action_index]["verified"] = False
            self.data["actions"][action_index]["rolled_back"] = True
            self.data["actions"][action_index]["rollback_reason"] = reason
            self.data["metadata"]["rollbacks_executed"] += 1
            self._save()

    def record_canary_fix(self, file_path: str) -> None:
        """Registra un canary fix aplicado."""
        self.data["metadata"]["canary_fixes_applied"] += 1
        self.data["updated_at"] = datetime.now(tz=UTC).isoformat()
        self._save()

    # ── Approvals ─────────────────────────────────────────────────────

    def add_approval(
        self, phase: str, approved_by: str = "auto", notes: str = ""
    ) -> None:
        """Registra una aprobación de fase.

        Args:
            phase: specify | plan | tasks | implement | verify | fix
            approved_by: human | auto
            notes: opcional
        """
        approval = {
            "phase": phase,
            "approved_by": approved_by,
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "notes": notes,
        }
        self.data["approvals"].append(approval)
        self._save()

    # ── Proof / Gates ─────────────────────────────────────────────────

    def add_gate_result(
        self,
        gate_name: str,
        passed: bool,
        evidence: str = "",
        stack: str = "python",
    ) -> None:
        """Registra el resultado de un gate.

        Args:
            gate_name: tests_pass | lint_clean | types_clean | etc.
            passed: True si pasó
            evidence: stdout resumen o error
            stack: python | typescript | ambos
        """
        result = {
            "gate_name": gate_name,
            "passed": passed,
            "evidence": evidence[:500],
            "stack": stack,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        self.data["proof"].append(result)

        if passed:
            hard_gates = {
                "tests_pass",
                "tests_deterministic",
                "no_security_issues",
                "no_broken_imports",
                "no_circular_imports",
                "integration_smoke",
            }
            if gate_name in hard_gates:
                self.data["metadata"]["hard_gates_passed"] = sum(
                    1
                    for g in self.data["proof"]
                    if g["gate_name"] in hard_gates and g["passed"]
                )

        self._save()

    def set_soft_score(self, score: float) -> None:
        """Registra el score ponderado de los soft goals (0-10)."""
        self.data["metadata"]["soft_score"] = round(score, 2)
        self._save()

    # ── High-risk check ──────────────────────────────────────────────

    def is_high_risk(self, action_index: int) -> bool:
        """Verifica si una acción es high-risk (sin rollback)."""
        if 0 <= action_index < len(self.data["actions"]):
            action = self.data["actions"][action_index]
            return not bool(action.get("rollback"))
        return True

    # ── Final status ──────────────────────────────────────────────────

    def complete(self, status: str = "pass") -> LedgerSummary:
        """Marca el ledger como completo.

        Args:
            status: pass | fail | halted

        Returns:
            Resumen del ledger
        """
        self.data["final_status"] = status
        self.data["completed_at"] = datetime.now(tz=UTC).isoformat()
        self._save()
        return self.summary()

    def summary(self) -> LedgerSummary:
        """Devuelve un resumen del ledger."""
        return {
            "run_id": self.data["run_id"],
            "spec": self.data["spec"][:100],
            "final_status": self.data["final_status"],
            "total_actions": len(self.data["actions"]),
            "verified_actions": sum(1 for a in self.data["actions"] if a["verified"]),
            "rolled_back": sum(
                1 for a in self.data["actions"] if a.get("rolled_back")
            ),
            "hard_gates_passed": self.data["metadata"]["hard_gates_passed"],
            "soft_score": self.data["metadata"]["soft_score"],
            "files_changed": self.data["metadata"]["total_files_changed"],
            "canary_fixes": self.data["metadata"]["canary_fixes_applied"],
            "approvals": len(self.data["approvals"]),
            "proof_count": len(self.data["proof"]),
            "is_complete": self.data["final_status"] != "running",
        }

    # ── Integrity check ───────────────────────────────────────────────

    def verify_integrity(self) -> bool:
        """Verifica que el ledger no esté corrupto.

        Returns:
            True si el ledger está íntegro, False si está corrupto → HALT
        """
        required_keys = {"run_id", "spec", "actions", "approvals", "proof", "final_status"}
        if not required_keys.issubset(self.data.keys()):
            return False

        for _, action in enumerate(self.data["actions"]):
            if action["action_type"] in ("edit_file", "git_commit") and not action.get("rollback"):
                return False

        return True

    # ── I/O privado ───────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            with open(self.ledger_path) as f:
                self.data = cast(LedgerData, json.load(f))
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"RUN LEDGER CORRUPTED: {self.ledger_path}. "
                f"JSON inválido: {e}. HALT inmediato."
            ) from e

    def _save(self) -> None:
        with open(self.ledger_path, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def __repr__(self) -> str:
        return (
            f"<RunLedger run_id={self.data['run_id']} "
            f"status={self.data['final_status']} "
            f"actions={len(self.data['actions'])}>"
        )
