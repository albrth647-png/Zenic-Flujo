"""
Zenic CLI — Comando: version
Gestiona la version de un conector siguiendo semver.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.cli.commands.helpers import _bump_version, _read_version, _update_version_in_files


def cmd_version(args: argparse.Namespace) -> int:
    """
    Gestiona la version de un conector siguiendo semver.

    Si se especifica --bump, incrementa la version segun el tipo:
    - major: Incrementa la version mayor (X.0.0) - cambios incompatibles
    - minor: Incrementa la version menor (0.X.0) - nueva funcionalidad compatible
    - patch: Incrementa la version de parche (0.0.X) - correcciones de bugs

    Si no se especifica --bump, muestra la version actual.

    Args:
        args: Argumentos parseados con 'connector_path', 'bump'

    Retorna:
        0 si la operacion fue exitosa, 1 si hubo errores
    """
    connector_path = Path(args.connector_path)
    bump_type = getattr(args, "bump", None)

    current_version = _read_version(connector_path)
    if current_version is None:
        print(f"Error: No se pudo determinar la version del conector en {connector_path}", file=sys.stderr)
        return 1

    if bump_type is None:
        print(f"Conector: {connector_path.name}")
        print(f"Version actual: {current_version}")
        return 0

    new_version = _bump_version(current_version, bump_type)
    if new_version is None:
        print(f"Error: No se pudo calcular la nueva version. Version actual: {current_version}", file=sys.stderr)
        return 1

    updated_files = _update_version_in_files(connector_path, current_version, new_version)

    print(f"Version actualizada: {current_version} -> {new_version}")
    print(f"Bump: {bump_type}")
    print()
    print("Archivos actualizados:")
    for filepath in updated_files:
        print(f"  - {filepath}")

    return 0
