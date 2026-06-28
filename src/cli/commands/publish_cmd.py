"""
Zenic CLI — Comando: publish
Empaqueta y publica un conector al marketplace.
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import suppress
from pathlib import Path

from src.cli.commands.helpers import _format_validation_report, _package_connector, _run_validation, _upload_connector


def cmd_publish(args: argparse.Namespace) -> int:
    """
    Empaqueta y publica un conector al marketplace.

    El proceso realiza los siguientes pasos:
    1. Valida el conector (ejecuta validate internamente)
    2. Empaqueta el conector como archivo .zip con manifest.json
    3. Sube al registro del marketplace (HTTP POST con API key)
    4. Muestra el estado de la publicacion

    Args:
        args: Argumentos parseados con 'connector_path', 'registry'

    Retorna:
        0 si la publicacion fue exitosa, 1 si hubo errores
    """
    connector_path = Path(args.connector_path)
    registry_url = getattr(args, "registry", None) or "https://marketplace.zenic-flijo.io/api/v1/connectors"

    print("Publicando conector...")
    print(f"  Ruta:     {connector_path}")
    print(f"  Registro: {registry_url}")
    print()

    # Paso 1: Validar
    print("Paso 1/3: Validando conector...")
    validation = _run_validation(connector_path)
    if not validation["passed"]:
        print("  Validacion FALLIDA. Corrija los errores antes de publicar.", file=sys.stderr)
        print()
        print(_format_validation_report(validation))
        return 1
    print(f"  Validacion OK ({validation['passed_checks']}/{validation['total_checks']} checks)")
    print()

    # Paso 2: Empaquetar
    print("Paso 2/3: Empaquetando conector...")
    zip_path = _package_connector(connector_path)
    if zip_path is None:
        print("  Error: No se pudo empaquetar el conector", file=sys.stderr)
        return 1
    zip_size_kb = os.path.getsize(zip_path) / 1024
    print(f"  Paquete creado: {zip_path} ({zip_size_kb:.1f} KB)")
    print()

    # Paso 3: Subir
    print("Paso 3/3: Subiendo al marketplace...")
    success = _upload_connector(zip_path, registry_url)
    if success:
        print("  Publicacion exitosa!")
    else:
        print("  Error: No se pudo subir al marketplace", file=sys.stderr)
        print("  Nota: Verifique su ZENIC_API_KEY y la conectividad al registro")
        return 1

    with suppress(OSError):
        os.remove(zip_path)

    return 0
