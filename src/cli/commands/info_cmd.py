"""
Zenic CLI — Comando: info
Muestra informacion detallada de un conector.
"""

from __future__ import annotations

import argparse
from contextlib import suppress


def cmd_info(args: argparse.Namespace) -> int:
    """
    Muestra informacion detallada de un conector.

    Busca el conector por nombre en el registro y muestra:
    - Metadata (nombre, version, descripcion, categoria, autor)
    - Acciones disponibles
    - Requisitos de autenticacion
    - Esquema del conector

    Args:
        args: Argumentos parseados con 'connector_name'

    Retorna:
        0 si se encontro el conector, 1 si no existe
    """
    from src.sdk.registry import ConnectorRegistry

    connector_name = args.connector_name
    registry = ConnectorRegistry()

    if registry.count() == 0:
        with suppress(Exception):
            registry.auto_discover("src.connectors")
        with suppress(Exception):
            registry.auto_discover("src.tools.integrations")

    metadata = registry.get_metadata(connector_name)
    connector_class = registry.get(connector_name)

    if metadata is None or connector_class is None:
        print(f"Conector '{connector_name}' no encontrado.")
        print()
        print("Conectores disponibles:")
        for name in registry.list_names():
            print(f"  - {name}")
        return 1

    print("=" * 60)
    print(f"  INFORMACION DEL CONECTOR: {connector_name}")
    print("=" * 60)
    print()

    print("  Metadata:")
    print(f"    Nombre:        {metadata.get('name', connector_name)}")
    print(f"    Version:       {metadata.get('version', 'N/A')}")
    print(f"    Descripcion:   {metadata.get('description', 'Sin descripcion')}")
    print(f"    Categoria:     {metadata.get('category', 'general')}")
    print(f"    Icono:         {metadata.get('icon', 'plug')}")
    print(f"    Autor:         {metadata.get('author', 'Desconocido')}")
    print(f"    Registrado:    {metadata.get('registered_at', 'N/A')}")
    print()

    try:
        from unittest.mock import patch
        with patch("src.sdk.base.RedisService"), patch("src.sdk.base.TelemetryService"):
            instance = connector_class()

        actions = instance.get_action_names()
        print("  Acciones disponibles:")
        if actions:
            for action in actions:
                print(f"    - {action}")
        else:
            print("    (Sin acciones definidas)")
        print()

        status = instance.get_status()
        has_auth = status.get("has_auth", False)
        auth_type = status.get("auth_type", "none")
        print("  Autenticacion:")
        print(f"    Requiere auth: {'Si' if has_auth else 'No'}")
        print(f"    Tipo:          {auth_type or 'N/A'}")
        print()

        schema = instance.get_schema()
        if schema:
            print("  Esquema:")
            print(f"    Nombre:           {schema.name}")
            print(f"    Version:          {schema.version}")
            print(f"    Acciones:         {len(schema.actions)}")
            print(f"    Requisitos auth:  {len(schema.auth_requirements)}")
            print(f"    Tags:             {', '.join(schema.tags) if schema.tags else 'Ninguno'}")
            if schema.auth_requirements:
                print()
                print("    Detalles de autenticacion:")
                for req in schema.auth_requirements:
                    required = ", ".join(req.required_fields) if req.required_fields else "Ninguno"
                    optional = ", ".join(req.optional_fields) if req.optional_fields else "Ninguno"
                    print(f"      - Tipo: {req.auth_type}")
                    print(f"        Campos requeridos: {required}")
                    print(f"        Campos opcionales: {optional}")
                    if req.description:
                        print(f"        Descripcion: {req.description}")
        else:
            print("  Esquema: No definido")

    except Exception as exc:
        print(f"  (No se pudo obtener informacion detallada: {exc})")

    print()
    print("=" * 60)

    return 0
