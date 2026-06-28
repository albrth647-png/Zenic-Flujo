"""
Code-Forge CLI v1.0
===================
Entry point for `python -m forge <command>`.

Commands:
  init            Inicializa ledger en directorio actual
  verify          Corre 12 gates sobre el proyecto
  check-module    Gates sobre un módulo específico
  report          Genera reporte de estado
  self-test       Ejecuta auto-test de gates en directorio temporal
  ledger          Gestión de RunLedger (init, verify, show, list)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path


def cmd_init(args: argparse.Namespace) -> int:
    """Inicializa ledger vacío en el directorio actual."""
    from forge import RunLedger

    target = Path(args.dir).resolve()
    RunLedger(target)
    ledger_path = target / "run_ledger.json"
    print(f"Ledger initialized at {ledger_path}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Corre todos los gates sobre el proyecto."""
    from forge import GateRunner

    root = Path(args.dir).resolve()
    runner = GateRunner(root)
    exclude = set(runner.EXPENSIVE_GATES) if args.quick else set()
    report = runner.run_all(exclude=exclude)
    runner.print_report()
    return 0 if report["overall"]["passed"] else 1


def cmd_check_module(args: argparse.Namespace) -> int:
    """Corre gates sobre un módulo específico."""
    from forge import GateRunner

    root = Path(args.dir).resolve()
    module_path = Path(args.module)
    if not module_path.exists():
        print(f"Module not found: {module_path}", file=sys.stderr)
        return 1

    runner = GateRunner(root)
    py_files = list(module_path.rglob("*.py"))
    ts_files = list(module_path.rglob("*.ts")) + list(module_path.rglob("*.tsx"))
    stacks: list[str] = []
    if py_files:
        stacks.append("python")
    if ts_files:
        stacks.append("typescript")
    if not stacks:
        print(f"No Python or TypeScript files found in {module_path}", file=sys.stderr)
        return 1

    report = runner.run_all(stacks=stacks, exclude=set(runner.EXPENSIVE_GATES))
    runner.print_report()
    return 0 if report["overall"]["passed"] else 1


def cmd_report(args: argparse.Namespace) -> int:
    """Genera reporte de estado del proyecto."""
    from forge import GateRunner

    root = Path(args.dir).resolve()
    runner = GateRunner(root)
    exclude = set(runner.EXPENSIVE_GATES) if args.quick else set()
    report = runner.run_all(exclude=exclude)
    runner.print_report()
    print()
    print("  Summary:")
    print(f"    Hard gates: {report['hard_gates']['count']}")
    print(f"    Soft score: {report['soft_goals']['score']:.1f}/{report['soft_goals']['threshold']}")
    print(f"    Overall:    {'PASS' if report['overall']['passed'] else 'FAIL'}")
    return 0 if report["overall"]["passed"] else 1


def cmd_self_test(args: argparse.Namespace) -> int:
    """Ejecuta self-test en directorio temporal."""
    from forge.gates import self_test

    report = self_test()
    return 0 if report["overall"]["passed"] else 1


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Genera dashboard HTML con score por módulo y tendencias."""
    from forge.dashboard import DashboardGenerator

    root = Path(args.dir).resolve()
    gen = DashboardGenerator(root)
    html = gen.generate()
    output = Path(args.output) if args.output else root / "reports" / "dashboard.html"
    saved = gen.save(html, output)
    print(f"✅ Dashboard generated: {saved}")
    print(f"   Open with: file://{saved.resolve()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m forge",
        description="Code-Forge v1.0 — Framework de ingeniería para agentes de IA",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Inicializa ledger en directorio")
    p_init.add_argument("--dir", default=".", help="Directorio del proyecto")

    p_verify = sub.add_parser("verify", help="Corre 12 gates sobre el proyecto")
    p_verify.add_argument("--dir", default=".", help="Directorio del proyecto")
    p_verify.add_argument("--quick", action="store_true", help="Skip expensive gates (mutation, coverage)")

    p_module = sub.add_parser("check-module", help="Gates sobre un módulo específico")
    p_module.add_argument("module", help="Ruta del módulo (ej: src/hat/)")
    p_module.add_argument("--dir", default=".", help="Directorio del proyecto")

    p_report = sub.add_parser("report", help="Genera reporte de estado")
    p_report.add_argument("--dir", default=".", help="Directorio del proyecto")
    p_report.add_argument("--quick", action="store_true", help="Skip expensive gates")

    sub.add_parser("self-test", help="Ejecuta auto-test de gates en directorio temporal")

    # Fase 7.3b: Subcomando dashboard
    p_dashboard = sub.add_parser("dashboard", help="Genera dashboard HTML con score por módulo")
    p_dashboard.add_argument("--dir", default=".", help="Directorio del proyecto")
    p_dashboard.add_argument("--output", default=None, help="Path de salida (default: reports/dashboard.html)")

    # Fase 4.3c: Subcomando ledger
    from forge.ledger_cli import add_ledger_subparser
    add_ledger_subparser(sub)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Si el comando tiene un handler asignado via set_defaults(func=...)
    # (caso del subcomando ledger), usarlo directamente
    if hasattr(args, "func"):
        handler: Callable[[argparse.Namespace], int] = args.func
        return handler(args)

    dispatch: dict[str, Callable[[argparse.Namespace], int]] = {
        "init": cmd_init,
        "verify": cmd_verify,
        "check-module": cmd_check_module,
        "report": cmd_report,
        "self-test": cmd_self_test,
        "dashboard": cmd_dashboard,
    }

    dispatched = dispatch.get(args.command)
    if dispatched:
        return dispatched(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
