#!/usr/bin/env python3
"""
fix_missing_any_import.py — Añade `from typing import Any` a archivos que lo usan pero no lo importan.

Esto es un parche para el codemod `auto-migrate-bare` que asumió que `Any` ya estaba
importado en los archivos donde parametrizaba `dict` → `dict[str, Any]`.

Estrategia:
  - Para cada archivo .py en src/ (excluyendo tests y core):
    - Parsea con AST.
    - Detecta si usa `Any` (como Name) pero no lo importa.
    - Si ya tiene `from typing import X, Y` (sin Any), añade Any a esa línea.
    - Si no tiene import de typing, añade `from typing import Any` después del último import.
  - Idempotente: si ya tiene el import, no hace nada.

Uso:
    python3 scripts/codemods/fix_missing_any_import.py --dry-run
    python3 scripts/codemods/fix_missing_any_import.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Escanear todo src/ excepto core (excluido del scope) y tests (auditados aparte)
SCAN_PATHS = ["src"]  # Se filtra core/tests dentro del loop
EXCLUDE_DIRS = {"core", "tests"}


def uses_any(source: str) -> bool:
    """True si el código usa `Any` como Name (no solo en strings/comments)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Any":
            return True
        # typing.Any
        if isinstance(node, ast.Attribute) and node.attr == "Any":
            return True
    return False


def imports_any(source: str) -> bool:
    """True si el código importa Any explícitamente."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                if alias.name == "Any":
                    return True
        # import typing (then uses typing.Any)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "typing":
                    return True
    return False


def fix_file(path: Path, *, dry_run: bool = False) -> bool:
    """Añade import de Any si es necesario. Retorna True si hubo cambios.

    Usa AST para identificar imports top-level (no dentro de funciones/clases)
    y localizar la posición correcta para insertar el nuevo import.
    """
    source = path.read_text(encoding="utf-8")
    if not uses_any(source) or imports_any(source):
        return False

    lines = source.splitlines(keepends=True)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    # Buscar imports top-level (directamente en tree.body, no anidados)
    last_top_import_line = 0  # 1-indexed
    typing_import_line = None  # 1-indexed
    typing_import_node = None

    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            typing_import_line = node.lineno
            typing_import_node = node
            last_top_import_line = max(last_top_import_line, node.end_lineno or node.lineno)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            last_top_import_line = max(last_top_import_line, node.end_lineno or node.lineno)

    if typing_import_line is not None and typing_import_node is not None:
        # Ya hay `from typing import X, Y` — añadir Any a esa línea
        # Caso simple: una sola línea
        if typing_import_node.lineno == typing_import_node.end_lineno:
            line_idx = typing_import_line - 1
            line = lines[line_idx]
            # Parsear los imports existentes
            # from typing import X, Y, Z
            match = re.match(r"^(from typing import )(.+?)(\s*(?:#.*)?)$", line.rstrip("\n"))
            if match:
                prefix, imports_part, suffix = match.groups()
                if "Any" not in imports_part:
                    new_imports = imports_part.rstrip(",") + ", Any"
                    new_line = prefix + new_imports + suffix + "\n"
                    lines[line_idx] = new_line
            else:
                # Formato no esperado, insertar nuevo import separado
                insert_idx = last_top_import_line  # 0-indexed = lineno
                lines.insert(insert_idx, "from typing import Any\n")
        else:
            # Multiline: from typing import (\n  X,\n  Y,\n)
            # Encontrar la línea con `)` y añadir Any antes
            for i in range(typing_import_line - 1, typing_import_node.end_lineno):
                if ")" in lines[i]:
                    # Insertar "    Any,\n" antes del )
                    indent = "    "
                    lines.insert(i, f"{indent}Any,\n")
                    break
    else:
        # No hay import de typing. Insertar `from typing import Any` después del último import top-level.
        insert_idx = last_top_import_line  # 0-indexed
        if insert_idx == 0:
            # No hay imports top-level. Buscar después del module docstring y comentarios.
            insert_idx = _find_insertion_point_after_docstring(tree, lines)
        lines.insert(insert_idx, "from typing import Any\n")

    new_source = "".join(lines)
    if new_source == source:
        return False

    # Validar que el resultado es sintácticamente válido antes de escribir
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        print(f"  [SKIP]  {path}: el fix produciría syntax error: {e}", file=sys.stderr)
        return False

    if not dry_run:
        path.write_text(new_source, encoding="utf-8")
    return True


def _find_insertion_point_after_docstring(tree: ast.Module, lines: list[str]) -> int:
    """Encuentra la posición para insertar un import cuando no hay imports top-level.

    Considera: module docstring, comentarios iniciales, y líneas vacías.
    Retorna índice 0-based.
    """
    insert_idx = 0
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            # Module docstring
            insert_idx = node.end_lineno or node.lineno
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            insert_idx = node.end_lineno or node.lineno
            break
        else:
            break
    return insert_idx


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or dry_run

    total_files = 0
    fixed = 0
    errors = 0

    for scan_path in SCAN_PATHS:
        root = PROJECT_ROOT / scan_path
        if not root.exists():
            continue
        for fpath in root.rglob("*.py"):
            if "__pycache__" in fpath.parts:
                continue
            # Excluir directorios prohibidos (core, tests)
            if any(part in EXCLUDE_DIRS for part in fpath.parts):
                continue
            total_files += 1
            try:
                changed = fix_file(fpath, dry_run=dry_run)
                if changed:
                    fixed += 1
                    status = "[DRY-RUN]" if dry_run else "[OK]    "
                    print(f"  {status} {fpath}")
            except Exception as e:
                errors += 1
                print(f"  [ERROR]  {fpath}: {e}", file=sys.stderr)

    print()
    print(f"Resumen: {fixed} archivos necesitan import de Any, {total_files} escaneados, {errors} errores")
    if dry_run and fixed > 0:
        print("(dry-run: no se escribieron cambios)")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
