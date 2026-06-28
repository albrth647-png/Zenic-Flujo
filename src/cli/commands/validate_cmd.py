"""
Zenic CLI — Comando: validate
Valida la estructura y el esquema de un conector.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.cli.commands.helpers import _format_validation_report, _run_validation


def cmd_validate(args: argparse.Namespace) -> int:
    """
    Valida la estructura y el esquema de un conector.

    Realiza las siguientes verificaciones:
    1. Archivos requeridos existen (__init__.py, connector.py, schema.py)
    2. La clase principal hereda de BaseConnector
    3. Todos los metodos abstractos estan implementados
    4. El esquema cumple con ConnectorSchema
    5. Compatibilidad del proveedor de autenticacion
    6. Sintaxis Python valida (check con py_compile)

    Args:
        args: Argumentos parseados con 'connector_path'

    Retorna:
        0 si todas las validaciones pasan, 1 si alguna falla
    """
    connector_path = Path(args.connector_path)

    print("Validando conector...")
    print(f"  Ruta: {connector_path}")
    print()

    report = _run_validation(connector_path)
    print(_format_validation_report(report))

    return 0 if report["passed"] else 1
