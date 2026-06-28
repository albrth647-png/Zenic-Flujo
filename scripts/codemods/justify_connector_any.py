#!/usr/bin/env python3
"""
justify_connector_any.py — Añade justificaciones `# legítimo:` a patrones de Any
que son legítimos en conectores de APIs externas según la skill any-best-practices §9.1.

Patrones justificados automáticamente:
  1. `def execute(self, action: str, params: dict[str, Any]) -> Any` — retorno dinámico de API
  2. `def __init__(self, **kwargs: Any)` — wrapper genérico (skill §1.2)
  3. `def _api(...) -> Any` o `def _signed_request(...) -> Any` — retorno HTTP raw
  4. `resp_body: Any` o `response: Any` — JSON decoded
  5. `def _<method>(self, p: dict[str, Any]) -> dict[str, Any]` — boundary de API (no toca, ya está bien)

NO aplica si la línea ya tiene justificación.

Uso:
    python3 scripts/codemods/justify_connector_any.py --dry-run
    python3 scripts/codemods/justify_connector_any.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCAN_PATH = PROJECT_ROOT / "src" / "connectors"

# Patrones legítimos y sus justificaciones
PATTERNS = [
    # execute() retorna JSON dinámico de API externa
    (
        re.compile(r"^(\s*def execute\(self,[^)]*\)\s*->\s*Any)(\s*:)\s*$"),
        "legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)",
    ),
    # __init__ con **kwargs: Any, **kw: Any, **args: Any, **config: Any (wrapper genérico)
    # Matchea **kwargs: Any en cualquier parte de la línea (ej: def __init__(self, **kwargs: Any) -> None:)
    (
        re.compile(r"^(.*\*\*(?:kwargs|kw|args|config)\s*:\s*Any.*)$"),
        "legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)",
    ),
    # _api, _signed_request, _request, _call, _azure_request → retorno HTTP raw
    # Caso 1: signatura completa en una línea con -> Any
    (
        re.compile(r"^(\s*def _(?:api|signed_request|azure_request|request|call|do_request)\([^)]*\)\s*->\s*Any)(\s*:)\s*$"),
        "legítimo: retorna respuesta HTTP raw de API externa (skill §9.1)",
    ),
    # Caso 2: signatura completa en una línea con -> dict[str, Any]
    (
        re.compile(r"^(\s*def _(?:api|signed_request|azure_request|request|call|do_request)\([^)]*\)\s*->\s*dict\[str,\s*Any\])(\s*:)\s*$"),
        "legítimo: retorna dict[str, Any] de API externa, value es JSON dinámico (skill §9.1)",
    ),
    # resp_body, response, raw_response: Any (JSON decoded)
    (
        re.compile(r"^(\s*(?:resp_body|response|raw_response|body|data)\s*:\s*Any)(\s*=|\s*$)"),
        "legítimo: JSON decoded de API externa, se valida al consumir (skill §9.1)",
    ),
    # result: Any = self._api(...) (asignación de retorno de API)
    (
        re.compile(r"^(\s*result\s*:\s*Any\s*=)\s*self\._api"),
        "legítimo: retorno de API externa, se valida al consumir (skill §9.1)",
    ),
    # parse_response, _parse, _extract → retorno dinámico
    (
        re.compile(r"^(\s*def _(?:parse|extract|transform)[^(]*\([^)]*\)\s*->\s*Any)(\s*:)\s*$"),
        "legítimo: parsea JSON dinámico de API externa (skill §9.1)",
    ),
]


def fix_file(path: Path, *, dry_run: bool = False) -> int:
    """Añade justificaciones a patrones legítimos. Retorna número de cambios."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    changes = 0

    for i, line in enumerate(lines):
        # Skip si ya tiene justificación
        if "# legítimo" in line or "# legitimo" in line:
            continue
        # Skip si la línea anterior ya tiene justificación (bloque)
        if i > 0 and ("# legítimo" in lines[i - 1] or "# legitimo" in lines[i - 1]):
            continue

        for pattern, justification in PATTERNS:
            match = pattern.match(line.rstrip("\n"))
            if match:
                # Obtener indentación
                indent = re.match(r"^(\s*)", line).group(1)
                # Insertar comentario en la línea anterior
                comment_line = f"{indent}# {justification}\n"
                lines.insert(i, comment_line)
                changes += 1
                break  # Solo aplicar un patrón por línea

    if changes == 0:
        return 0

    new_source = "".join(lines)
    if new_source == source:
        return 0

    if not dry_run:
        path.write_text(new_source, encoding="utf-8")
    return changes


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    total_files = 0
    files_changed = 0
    total_changes = 0

    for fpath in SCAN_PATH.rglob("*.py"):
        if "__pycache__" in fpath.parts:
            continue
        total_files += 1
        try:
            changes = fix_file(fpath, dry_run=dry_run)
            if changes > 0:
                files_changed += 1
                total_changes += changes
                status = "[DRY-RUN]" if dry_run else "[OK]    "
                print(f"  {status} {fpath} (+{changes} justificaciones)")
        except Exception as e:
            print(f"  [ERROR]  {fpath}: {e}", file=sys.stderr)

    print()
    print(f"Resumen: {total_changes} justificaciones en {files_changed} archivos de {total_files} escaneados")
    if dry_run and total_changes > 0:
        print("(dry-run: no se escribieron cambios)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
