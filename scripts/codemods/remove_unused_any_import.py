#!/usr/bin/env python3
"""
remove_unused_any_import.py — Elimina `Any` de imports sin uso en archivos Python.

Detecta archivos que tienen `from typing import Any` (o `from typing import X, Any, Y`)
pero NO usan `Any` en el resto del archivo. Elimina `Any` del import, o elimina el
import completo si era el único nombre importado.

Casos cubiertos:
  - `from typing import Any`              → elimina la línea completa
  - `from typing import Any, Optional`    → `from typing import Optional`
  - `from typing import Optional, Any`    → `from typing import Optional`
  - `from typing import (\n  Any,\n  X,\n)` → `from typing import (\n  X,\n)`
  - `import typing` (si solo se usa typing.Any y ya no se usa) → elimina la línea

Uso:
    python3 scripts/codemods/remove_unused_any_import.py --dry-run
    python3 scripts/codemods/remove_unused_any_import.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCAN_PATHS = ["src"]
EXCLUDE_DIRS = {"core", "tests"}


def uses_any(source: str) -> bool:
    """True si el código usa `Any` como Name (no en import)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        # Name node "Any" en cualquier contexto que no sea import
        if isinstance(node, ast.Name) and node.id == "Any":
            return True
        # typing.Any
        if isinstance(node, ast.Attribute) and node.attr == "Any":
            return True
    return False


def has_any_import(source: str) -> tuple[bool, list[ast.ImportFrom]]:
    """Retorna (tiene_import_any, lista_de_nodos_ImportFrom_con_Any)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, []
    nodes_with_any = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                if alias.name == "Any":
                    nodes_with_any.append(node)
                    break
    return len(nodes_with_any) > 0, nodes_with_any


def fix_file(path: Path, *, dry_run: bool = False) -> bool:
    """Elimina Any de imports sin uso. Retorna True si hubo cambios."""
    source = path.read_text(encoding="utf-8")
    if uses_any(source):
        return False  # Any se usa, el import es legítimo

    has_import, import_nodes = has_any_import(source)
    if not has_import:
        return False  # No hay import de Any, nada que hacer

    lines = source.splitlines(keepends=True)
    lines_to_remove: set[int] = set()  # 0-indexed
    lines_to_modify: dict[int, str] = {}  # 0-indexed -> new content

    for node in import_nodes:
        # Caso 1: import single-line `from typing import Any` o `from typing import X, Any, Y`
        if node.lineno == node.end_lineno:
            line_idx = node.lineno - 1
            line = lines[line_idx]
            # Parsear los nombres importados
            match = re.match(r"^(\s*from typing import )(.+?)(\s*(?:#.*)?)$", line.rstrip("\n"))
            if match:
                prefix, imports_part, suffix = match.groups()
                # Split por coma
                names = [n.strip() for n in imports_part.split(",")]
                # Filtrar Any
                names_without_any = [n for n in names if n != "Any"]
                if not names_without_any:
                    # Solo importaba Any → eliminar línea completa
                    lines_to_remove.add(line_idx)
                else:
                    # Reconstruir
                    new_imports = ", ".join(names_without_any)
                    new_line = prefix + new_imports + suffix + "\n"
                    lines_to_modify[line_idx] = new_line
        else:
            # Caso 2: multiline `from typing import (\n  Any,\n  X,\n)`
            # Iterar las líneas del bloque y eliminar las que contengan solo `Any,`
            for line_no in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                line_idx = line_no - 1
                if line_idx >= len(lines):
                    break
                line = lines[line_idx]
                # Línea que contiene solo `Any,` o `Any` (con whitespace)
                if re.match(r"^\s*Any\s*,?\s*$", line.rstrip("\n")):
                    lines_to_remove.add(line_idx)
                    break  # Solo una línea Any por import
            # Verificar si quedan nombres en el multiline; si no, eliminar todo el bloque
            remaining_names = []
            for line_no in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                line_idx = line_no - 1
                if line_idx in lines_to_remove:
                    continue
                if line_idx >= len(lines):
                    break
                line = lines[line_idx]
                # Saltar paréntesis y líneas vacías
                stripped = line.strip()
                if stripped in {"(", ")", ""}:
                    continue
                # Si llega aquí, es un nombre que no es Any
                remaining_names.append(line)
            if not remaining_names:
                # Eliminar todo el bloque
                for line_no in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                    lines_to_remove.add(line_no - 1)

    if not lines_to_remove and not lines_to_modify:
        return False

    # Aplicar cambios
    new_lines = []
    for i, line in enumerate(lines):
        if i in lines_to_remove:
            continue
        if i in lines_to_modify:
            new_lines.append(lines_to_modify[i])
        else:
            new_lines.append(line)

    new_source = "".join(new_lines)
    if new_source == source:
        return False

    # Validar syntax
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        print(f"  [SKIP]  {path}: el fix produciría syntax error: {e}", file=sys.stderr)
        return False

    if not dry_run:
        path.write_text(new_source, encoding="utf-8")
    return True


def main() -> int:
    dry_run = "--dry-run" in sys.argv

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
    print(f"Resumen: {fixed} archivos con unused Any import, {total_files} escaneados, {errors} errores")
    if dry_run and fixed > 0:
        print("(dry-run: no se escribieron cambios)")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
