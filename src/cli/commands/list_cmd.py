"""
Zenic CLI — Comando: list
Lista todos los conectores registrados en el sistema.
"""

from __future__ import annotations

import argparse
from contextlib import suppress


def cmd_list(args: argparse.Namespace) -> int:
    """
    Lista todos los conectores registrados en el sistema.

    Muestra una tabla con el nombre, version, categoria y estado
    de cada conector registrado en ConnectorRegistry.

    Args:
        args: Argumentos parseados (no se usan argumentos adicionales)

    Retorna:
        0 siempre
    """
    from src.sdk.registry import ConnectorRegistry

    registry = ConnectorRegistry()

    if registry.count() == 0:
        with suppress(Exception):
            registry.auto_discover("src.connectors")
        with suppress(Exception):
            registry.auto_discover("src.tools.integrations")

    connectors = registry.list_all()

    if not connectors:
        print("No hay conectores registrados.")
        print()
        print("Para crear un nuevo conector:")
        print("  python -m src.cli.main init <nombre> --category <categoria> --auth-type <tipo>")
        return 0

    print(f"{'Nombre':<25} {'Version':<12} {'Categoria':<15} {'Estado'}")
    print("-" * 70)

    for conn in connectors:
        name = conn.get("name", "N/A")
        version = conn.get("version", "N/A")
        category = conn.get("category", "N/A")
        print(f"{name:<25} {version:<12} {category:<15} {'registrado'}")

    print()
    print(f"Total: {len(connectors)} conector(es)")

    return 0
