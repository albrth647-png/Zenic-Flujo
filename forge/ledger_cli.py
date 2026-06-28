"""
Forge Ledger CLI — Subcomando `forge ledger`
============================================
Operaciones de gestión de RunLedger desde CLI.

Comandos:
  init [path]              Inicializa ledger vacío desde template canónico
  verify [path]            Verifica integridad del ledger
  show [path]              Muestra resumen del ledger
  list [path]              Lista ledgers encontrados en .forge/*/

Uso:
  python -m forge ledger init .forge/phase5
  python -m forge ledger verify .forge/phase4/run_ledger.json
  python -m forge ledger show .forge/phase1/run_ledger.json
  python -m forge ledger list .
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TypedDict

from forge import RunLedger
from forge.run_ledger import LedgerData, LedgerSummary


class LedgerVerifyResult(TypedDict):
    """Resultado de verificar un ledger."""

    path: str
    valid: bool
    error: str
    actions_count: int
    hard_gates_passed: int
    soft_score: float
    final_status: str


class LedgerListEntry(TypedDict):
    """Entrada en el listado de ledgers."""

    path: str
    run_id: str
    final_status: str
    actions_count: int
    hard_gates_passed: int
    soft_score: float


# ── Init ─────────────────────────────────────────────────────────────


def init_ledger(target_dir: Path, run_id: str | None = None) -> Path:
    """Inicializa un ledger vacío en target_dir.

    Args:
        target_dir: Directorio donde crear el ledger (.forge/<phase>/)
        run_id: ID opcional del run. Si None, se auto-genera.

    Returns:
        Path al ledger creado.

    Raises:
        FileExistsError: Si ya existe un ledger en target_dir.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = target_dir / "run_ledger.json"
    if ledger_path.exists():
        raise FileExistsError(f"Ledger already exists: {ledger_path}")

    RunLedger(target_dir, run_id=run_id)
    return ledger_path


# ── Verify ───────────────────────────────────────────────────────────

# Keys requeridas en todo ledger íntegro
_REQUIRED_KEYS = {"run_id", "spec", "actions", "approvals", "proof", "final_status"}

# Tipos de acción que requieren rollback obligatorio
_HIGH_RISK_ACTIONS = {"edit_file", "git_commit"}


def _check_integrity(data: dict[str, object]) -> tuple[bool, str]:
    """Verifica integridad de un dict de ledger sin instanciar RunLedger.

    Args:
        data: Dict con el contenido del ledger (parseado de JSON).

    Returns:
        Tupla (válido, error). Si válido=False, error contiene el mensaje.
    """
    if not _REQUIRED_KEYS.issubset(data.keys()):
        missing = _REQUIRED_KEYS - data.keys()
        return False, f"Missing required keys: {missing}"

    actions = data.get("actions", [])
    if not isinstance(actions, list):
        return False, "actions is not a list"

    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            return False, f"action[{i}] is not a dict"
        action_type = action.get("action_type", "")
        rollback = action.get("rollback", "")
        if action_type in _HIGH_RISK_ACTIONS and not rollback:
            return (
                False,
                f"action[{i}] ({action_type}) missing required rollback",
            )

    return True, ""


def verify_ledger(ledger_path: Path) -> LedgerVerifyResult:
    """Verifica la integridad de un ledger.

    Args:
        ledger_path: Path al archivo run_ledger.json.

    Returns:
        LedgerVerifyResult con detalles de la verificación.
    """
    if not ledger_path.exists():
        return LedgerVerifyResult(
            path=str(ledger_path),
            valid=False,
            error=f"File not found: {ledger_path}",
            actions_count=0,
            hard_gates_passed=0,
            soft_score=0.0,
            final_status="unknown",
        )

    try:
        with open(ledger_path) as f:
            data: dict[str, object] = json.load(f)
    except json.JSONDecodeError as e:
        return LedgerVerifyResult(
            path=str(ledger_path),
            valid=False,
            error=f"JSON decode error: {e}",
            actions_count=0,
            hard_gates_passed=0,
            soft_score=0.0,
            final_status="corrupted",
        )

    is_valid, error = _check_integrity(data)
    if not is_valid:
        actions = data.get("actions", [])
        return LedgerVerifyResult(
            path=str(ledger_path),
            valid=False,
            error=error,
            actions_count=len(actions) if isinstance(actions, list) else 0,
            hard_gates_passed=_get_nested_int(data, "metadata", "hard_gates_passed"),
            soft_score=_get_nested_float(data, "metadata", "soft_score"),
            final_status=str(data.get("final_status", "unknown")),
        )

    actions = data.get("actions", [])
    return LedgerVerifyResult(
        path=str(ledger_path),
        valid=True,
        error="",
        actions_count=len(actions) if isinstance(actions, list) else 0,
        hard_gates_passed=_get_nested_int(data, "metadata", "hard_gates_passed"),
        soft_score=_get_nested_float(data, "metadata", "soft_score"),
        final_status=str(data.get("final_status", "unknown")),
    )


def _get_nested_int(data: dict[str, object], *keys: str) -> int:
    """Obtiene un int anidado de forma segura."""
    current: object = data
    for key in keys:
        if not isinstance(current, dict):
            return 0
        current = current.get(key, 0)
    return int(current) if isinstance(current, (int, float)) else 0


def _get_nested_float(data: dict[str, object], *keys: str) -> float:
    """Obtiene un float anidado de forma segura."""
    current: object = data
    for key in keys:
        if not isinstance(current, dict):
            return 0.0
        current = current.get(key, 0.0)
    return float(current) if isinstance(current, (int, float)) else 0.0


# ── Show ─────────────────────────────────────────────────────────────


def show_ledger(ledger_path: Path) -> LedgerSummary | None:
    """Muestra el resumen de un ledger.

    Args:
        ledger_path: Path al archivo run_ledger.json.

    Returns:
        LedgerSummary o None si el ledger no existe o está corrupto.
    """
    if not ledger_path.exists():
        return None

    try:
        ledger = RunLedger(ledger_path.parent, run_id="show-only")
        with open(ledger_path) as f:
            data = json.load(f)
        ledger.data = data
        return ledger.summary()
    except (json.JSONDecodeError, RuntimeError):
        return None


# ── List ─────────────────────────────────────────────────────────────


def list_ledgers(project_root: Path) -> list[LedgerListEntry]:
    """Lista todos los ledgers encontrados en .forge/*/ del proyecto.

    Args:
        project_root: Directorio raíz del proyecto.

    Returns:
        Lista de LedgerListEntry con metadatos de cada ledger, ordenados por path.
    """
    forge_dir = project_root / ".forge"
    if not forge_dir.exists():
        return []

    entries: list[LedgerListEntry] = []
    for ledger_path in sorted(forge_dir.rglob("run_ledger.json")):
        result = verify_ledger(ledger_path)
        if not result["valid"]:
            continue
        try:
            with open(ledger_path) as f:
                data: LedgerData = json.load(f)
            entries.append(LedgerListEntry(
                path=str(ledger_path.relative_to(project_root)),
                run_id=str(data.get("run_id", "?")),
                final_status=str(data.get("final_status", "unknown")),
                actions_count=result["actions_count"],
                hard_gates_passed=result["hard_gates_passed"],
                soft_score=result["soft_score"],
            ))
        except (json.JSONDecodeError, KeyError):
            continue
    return entries


# ── CLI handlers ─────────────────────────────────────────────────────


def cmd_ledger_init(args: argparse.Namespace) -> int:
    """Handler para `forge ledger init`."""
    target = Path(args.path).resolve()
    run_id: str | None = getattr(args, "run_id", None)
    try:
        ledger_path = init_ledger(target, run_id=run_id)
        print(f"✅ Ledger initialized: {ledger_path}")
        return 0
    except FileExistsError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


def cmd_ledger_verify(args: argparse.Namespace) -> int:
    """Handler para `forge ledger verify`."""
    ledger_path = Path(args.path).resolve()
    result = verify_ledger(ledger_path)

    if result["valid"]:
        print(f"✅ Ledger valid: {result['path']}")
        print(f"   Actions: {result['actions_count']}")
        print(f"   Hard gates passed: {result['hard_gates_passed']}")
        print(f"   Soft score: {result['soft_score']:.2f}/10")
        print(f"   Final status: {result['final_status']}")
        return 0
    print(f"❌ Ledger INVALID: {result['path']}", file=sys.stderr)
    print(f"   Error: {result['error']}", file=sys.stderr)
    return 1


def cmd_ledger_show(args: argparse.Namespace) -> int:
    """Handler para `forge ledger show`."""
    ledger_path = Path(args.path).resolve()
    summary = show_ledger(ledger_path)

    if summary is None:
        print(f"❌ Cannot read ledger: {ledger_path}", file=sys.stderr)
        return 1

    print(f"📋 Ledger Summary: {ledger_path}")
    print(f"   Run ID:          {summary['run_id']}")
    print(f"   Spec:            {summary['spec']}")
    print(f"   Final status:    {summary['final_status']}")
    print(f"   Total actions:   {summary['total_actions']}")
    print(f"   Verified:        {summary['verified_actions']}")
    print(f"   Rolled back:     {summary['rolled_back']}")
    print(f"   Hard gates:      {summary['hard_gates_passed']}")
    print(f"   Soft score:      {summary['soft_score']:.2f}/10")
    print(f"   Files changed:   {summary['files_changed']}")
    print(f"   Canary fixes:    {summary['canary_fixes']}")
    print(f"   Approvals:       {summary['approvals']}")
    print(f"   Proof count:     {summary['proof_count']}")
    print(f"   Is complete:     {summary['is_complete']}")
    return 0


def cmd_ledger_list(args: argparse.Namespace) -> int:
    """Handler para `forge ledger list`."""
    project_root = Path(args.path).resolve()
    entries = list_ledgers(project_root)

    if not entries:
        print(f"No ledgers found in {project_root}/.forge/")
        return 0

    print(f"📂 Ledgers in {project_root}/.forge/ ({len(entries)} found):")
    print()
    print(f"  {'PATH':<40} {'STATUS':<10} {'ACTIONS':<10} {'HARD':<6} {'SOFT':<8}")
    print(f"  {'─' * 40} {'─' * 10} {'─' * 10} {'─' * 6} {'─' * 8}")
    for e in entries:
        print(
            f"  {e['path']:<40} {e['final_status']:<10} "
            f"{e['actions_count']:<10} {e['hard_gates_passed']:<6} "
            f"{e['soft_score']:<8.2f}"
        )
    return 0


def add_ledger_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Añade el subparser `ledger` al parser principal.

    Args:
        subparsers: Subparsers del parser principal de forge CLI.
    """
    p_ledger = subparsers.add_parser(
        "ledger",
        help="Gestión de RunLedger (init, verify, show, list)",
    )
    ledger_sub = p_ledger.add_subparsers(dest="ledger_command", required=True)

    p_init = ledger_sub.add_parser("init", help="Inicializa ledger vacío")
    p_init.add_argument("path", help="Directorio donde crear el ledger (ej: .forge/phase5)")
    p_init.add_argument("--run-id", default=None, help="ID del run (auto-generado si se omite)")
    p_init.set_defaults(func=cmd_ledger_init)

    p_verify = ledger_sub.add_parser("verify", help="Verifica integridad del ledger")
    p_verify.add_argument("path", help="Path al archivo run_ledger.json")
    p_verify.set_defaults(func=cmd_ledger_verify)

    p_show = ledger_sub.add_parser("show", help="Muestra resumen del ledger")
    p_show.add_argument("path", help="Path al archivo run_ledger.json")
    p_show.set_defaults(func=cmd_ledger_show)

    p_list = ledger_sub.add_parser("list", help="Lista ledgers en .forge/*/ del proyecto")
    p_list.add_argument("path", default=".", nargs="?", help="Directorio raíz del proyecto (default: .)")
    p_list.set_defaults(func=cmd_ledger_list)
