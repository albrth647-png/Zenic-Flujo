#!/usr/bin/env python3
r"""
Pre-commit hook: verifica integridad de RunLedger
===================================================
Verifica que todos los archivos run_ledger.json en .forge/*/ sean íntegros
(keys requeridas, rollback en acciones high-risk, JSON válido).

Uso en .pre-commit-config.yaml:
  - repo: local
    hooks:
      - id: forge-ledger-verify
        name: Forge Ledger Verify
        entry: python3 scripts/hooks/pre_commit_ledger.py
        language: system
        files: r'\.forge/.*run_ledger\.json$'
        pass_filenames: false

O como hook standalone (sin pre-commit framework):
  python3 scripts/hooks/pre_commit_ledger.py [--strict]

Exit codes:
  0 — Todos los ledgers válidos
  1 — Al menos un ledger inválido (bloquea commit)
"""
# ruff: noqa: E402 — sys.path manipulation required before forge import
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Añadir el directorio del proyecto al path para importar forge
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from forge.ledger_cli import list_ledgers, verify_ledger


def main(argv: list[str] | None = None) -> int:
    """Entry point del pre-commit hook.

    Args:
        argv: Argumentos CLI (default: sys.argv[1:]).

    Returns:
        0 si todos los ledgers son válidos, 1 si hay al menos uno inválido.
    """
    parser = argparse.ArgumentParser(
        description="Verifica integridad de RunLedger antes del commit",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Directorio raíz del proyecto (default: .)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Modo estricto: requiere al menos 1 ledger válido",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    entries = list_ledgers(project_root)

    if not entries:
        if args.strict:
            print("❌ No ledgers found in .forge/ (strict mode requires at least 1)")
            return 1
        print("[INFO] No ledgers found in .forge/ - skipping")
        return 0

    print(f"🔍 Verifying {len(entries)} ledger(s)...")
    all_valid = True
    for entry in entries:
        ledger_path = project_root / entry["path"]
        result = verify_ledger(ledger_path)
        if result["valid"]:
            print(f"  ✅ {entry['path']} (actions={result['actions_count']}, status={result['final_status']})")
        else:
            print(f"  ❌ {entry['path']}: {result['error']}")
            all_valid = False

    if all_valid:
        print(f"✅ All {len(entries)} ledger(s) valid — commit allowed")
        return 0
    print("❌ Some ledgers invalid — commit blocked", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
