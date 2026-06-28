"""
Zenic CLI — Comando: init
Crea el scaffolding de un nuevo conector con plantillas.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from src.cli.commands.helpers import CONNECTORS_BASE_DIR
from src.cli.templates import (
    VALID_AUTH_TYPES,
    generate_connector_code,
    generate_init_code,
    generate_manifest,
    generate_schema_code,
    generate_test_code,
)


def cmd_init(args: argparse.Namespace) -> int:
    """
    Crea el scaffolding de un nuevo conector con plantillas segun tipo de autenticacion.

    Genera la estructura de directorios completa:
    - connector_name/__init__.py
    - connector_name/connector.py
    - connector_name/schema.py
    - connector_name/tests/test_connector.py
    - connector_name/manifest.json

    Args:
        args: Argumentos parseados con 'name', 'category', 'auth_type'

    Retorna:
        0 si el scaffolding fue exitoso, 1 si hubo error
    """
    name = args.name
    category = getattr(args, "category", "general") or "general"
    auth_type = getattr(args, "auth_type", "none") or "none"

    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        print(f"Error: El nombre '{name}' no es valido. Use solo minusculas, numeros y guiones bajos.", file=sys.stderr)
        return 1

    if auth_type not in VALID_AUTH_TYPES:
        print(f"Error: Tipo de autenticacion '{auth_type}' no valido. Opciones: {', '.join(VALID_AUTH_TYPES)}", file=sys.stderr)
        return 1

    base_dir = Path(CONNECTORS_BASE_DIR) / name
    tests_dir = base_dir / "tests"

    if base_dir.exists():
        print(f"Error: El conector '{name}' ya existe en {base_dir}", file=sys.stderr)
        return 1

    tests_dir.mkdir(parents=True, exist_ok=True)

    files_to_create = {
        base_dir / "__init__.py": generate_init_code(name),
        base_dir / "connector.py": generate_connector_code(name, category, auth_type),
        base_dir / "schema.py": generate_schema_code(name),
        tests_dir / "__init__.py": "",
        tests_dir / "test_connector.py": generate_test_code(name),
        base_dir / "manifest.json": generate_manifest(name, "1.0.0", category, ""),
    }

    created_files: list[str] = []
    for filepath, content in files_to_create.items():
        filepath.write_text(content, encoding="utf-8")
        created_files.append(str(filepath))

    print(f"Conector '{name}' creado exitosamente!")
    print(f"  Categoria:    {category}")
    print(f"  Auth type:    {auth_type}")
    print(f"  Directorio:   {base_dir}")
    print()
    print("Archivos generados:")
    for filepath in sorted(created_files):
        print(f"  - {filepath}")
    print()
    print("Proximos pasos:")
    print(f"  1. Implemente la logica en {base_dir / 'connector.py'}")
    print(f"  2. Defina esquemas en {base_dir / 'schema.py'}")
    print(f"  3. Pruebe con: zenic test {base_dir}")
    print(f"  4. Valide con: zenic validate {base_dir}")

    return 0
