#!/usr/bin/env python3
"""
run_codemod.py — Runner CLI para los codemods de migración `Any`.

Uso:
    # Listar codemods disponibles
    python3 scripts/codemods/run_codemod.py list

    # Aplicar un codemod a un archivo (dry-run)
    python3 scripts/codemods/run_codemod.py apply parametrize-bare-dict \\
        --file src/connectors/sendgrid.py --dry-run

    # Aplicar a un directorio completo
    python3 scripts/codemods/run_codemod.py apply auto-migrate-bare \\
        --path src/connectors --extensions .py

    # Aplicar a archivos modificados en git (vía pre-commit o manual)
    python3 scripts/codemods/run_codemod.py apply-to-git-changed parametrize-bare-dict

Workflow recomendado:
    1. Auditar antes:    python3 scripts/any_audit/any_audit.py run
    2. Dry-run codemod:  python3 scripts/codemods/run_codemod.py apply ... --dry-run
    3. Aplicar:          python3 scripts/codemods/run_codemod.py apply ... 
    4. Ver diff:         git diff
    5. Correr tests:     pytest src/tests/
    6. Auditar después:  python3 scripts/any_audit/any_audit.py run
    7. Commit:           git commit -m "refactor(any): parametrize bare dicts in connectors"

Diseño:
  - Determinístico: misma entrada → misma salida.
  - Reversible: git checkout restaura el estado anterior.
  - Idempotente: aplicar dos veces = aplicar una vez.
  - Sin dependencias externas más allá de libcst.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Asegurar que el directorio padre está en sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from any_codemods import list_codemods, transform_file  # noqa: E402


def cmd_list(_: argparse.Namespace) -> int:
    """Lista los codemods disponibles."""
    codemods = list_codemods()
    print("Codemods disponibles:")
    print()
    for name, cls in codemods.items():
        desc = (cls.DESCRIPTION or "").strip()
        print(f"  {name}")
        print(f"    {desc}")
        print()
    return 0


def _iter_python_files(path: Path) -> list[Path]:
    """Itera archivos .py en un path (archivo o directorio)."""
    if path.is_file():
        return [path] if path.suffix == ".py" else []
    if path.is_dir():
        return sorted(path.rglob("*.py"))
    return []


def cmd_apply(args: argparse.Namespace) -> int:
    """Aplica un codemod a un archivo o directorio."""
    codemods = list_codemods()
    if args.codemod not in codemods:
        print(f"❌ Codemod desconocido: {args.codemod}", file=sys.stderr)
        print(f"   Disponibles: {', '.join(codemods.keys())}", file=sys.stderr)
        return 2

    codemod_class = codemods[args.codemod]

    # Resolver archivos a procesar
    files: list[Path] = []
    if args.file:
        files.append(Path(args.file).resolve())
    elif args.path:
        target = Path(args.path).resolve()
        if not target.exists():
            print(f"❌ Path no existe: {target}", file=sys.stderr)
            return 2
        files = _iter_python_files(target)
    else:
        print("❌ Debes especificar --file o --path", file=sys.stderr)
        return 2

    if not files:
        print("⚠️  No se encontraron archivos para procesar.")
        return 0

    # Filtrar por extensiones
    if args.extensions:
        exts = tuple(args.extensions)
        files = [f for f in files if f.suffix in exts]

    # Excluir tests y core por defecto
    if not args.include_tests:
        files = [f for f in files if "tests" not in f.parts]
    if not args.include_core:
        files = [f for f in files if "src/core" not in str(f)]

    modified = 0
    unchanged = 0
    errors = 0

    for filepath in files:
        try:
            changed = transform_file(filepath, codemod_class, dry_run=args.dry_run)
            if changed:
                modified += 1
                status = "[DRY-RUN]" if args.dry_run else "[OK]    "
                print(f"  {status} {filepath}")
            else:
                unchanged += 1
                if args.verbose:
                    print(f"  [SKIP]   {filepath}")
        except Exception as e:
            errors += 1
            print(f"  [ERROR]  {filepath}: {e}", file=sys.stderr)

    print()
    print(f"Resumen: {modified} modificados, {unchanged} sin cambios, {errors} errores")
    if args.dry_run and modified > 0:
        print("(dry-run: no se escribieron cambios)")
    return 0 if errors == 0 else 1


def cmd_apply_to_git_changed(args: argparse.Namespace) -> int:
    """Aplica un codemod solo a archivos modificados en git (staged o modified)."""
    import subprocess

    codemods = list_codemods()
    if args.codemod not in codemods:
        print(f"❌ Codemod desconocido: {args.codemod}", file=sys.stderr)
        return 2

    codemod_class = codemods[args.codemod]

    # Obtener archivos modificados
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=AM", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        files_str = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Error ejecutando git: {e}", file=sys.stderr)
        return 2

    if not files_str:
        print("ℹ️  No hay archivos modificados.")
        return 0

    files = [Path(f) for f in files_str.split("\n") if f.endswith(".py")]
    if not files:
        print("ℹ️  No hay archivos .py modificados.")
        return 0

    modified = 0
    for filepath in files:
        if not filepath.exists():
            continue
        if "tests" in filepath.parts and not args.include_tests:
            continue
        if "src/core" in str(filepath) and not args.include_core:
            continue
        try:
            changed = transform_file(filepath, codemod_class, dry_run=args.dry_run)
            if changed:
                modified += 1
                status = "[DRY-RUN]" if args.dry_run else "[OK]    "
                print(f"  {status} {filepath}")
        except Exception as e:
            print(f"  [ERROR]  {filepath}: {e}", file=sys.stderr)

    print(f"\nResumen: {modified} archivos modificados de {len(files)} modificados en git.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="run_codemod",
        description="Runner para codemods de migración `Any` en Zenic-Flujo.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # list
    p_list = sub.add_parser("list", help="Lista codemods disponibles")
    p_list.set_defaults(func=cmd_list)

    # apply
    p_apply = sub.add_parser("apply", help="Aplica un codemod a archivos")
    p_apply.add_argument("codemod", help="Nombre del codemod (ver `list`)")
    p_apply.add_argument("--file", type=Path, help="Archivo individual")
    p_apply.add_argument("--path", type=Path, help="Directorio a escanear recursivamente")
    p_apply.add_argument(
        "--extensions", nargs="+", default=[".py"], help="Extensiones a incluir (default: .py)"
    )
    p_apply.add_argument("--dry-run", action="store_true", help="No escribir cambios, solo reportar")
    p_apply.add_argument("--verbose", action="store_true", help="Mostrar archivos sin cambios también")
    p_apply.add_argument("--include-tests", action="store_true", help="Incluir archivos en tests/")
    p_apply.add_argument("--include-core", action="store_true", help="Incluir src/core/ (peligroso)")
    p_apply.set_defaults(func=cmd_apply)

    # apply-to-git-changed
    p_git = sub.add_parser(
        "apply-to-git-changed", help="Aplica solo a archivos modificados en git"
    )
    p_git.add_argument("codemod", help="Nombre del codemod")
    p_git.add_argument("--dry-run", action="store_true")
    p_git.add_argument("--include-tests", action="store_true")
    p_git.add_argument("--include-core", action="store_true")
    p_git.set_defaults(func=cmd_apply_to_git_changed)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
