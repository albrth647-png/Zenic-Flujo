"""
Zenic CLI — Parser de argumentos
"""

from __future__ import annotations

import argparse

from src.cli.templates import VALID_AUTH_TYPES

CLI_VERSION = "1.0.0"


def build_parser() -> argparse.ArgumentParser:
    """
    Construye el parser de argumentos principal del CLI.

    Configura todos los subcomandos con sus argumentos y opciones.

    Retorna:
        ArgumentParser configurado con todos los subcomandos
    """
    parser = argparse.ArgumentParser(
        prog="zenic",
        description="Zenic CLI — Herramienta de desarrollo de conectores para Zenic-Flijo",
        epilog="Use 'zenic <comando> --help' para mas informacion sobre cada comando.",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {CLI_VERSION}",
    )

    subparsers = parser.add_subparsers(
        title="comandos",
        dest="command",
        help="Comando a ejecutar",
    )

    # ── init ───────────────────────────────────────────────────
    init_parser = subparsers.add_parser(
        "init",
        help="Crea el scaffolding de un nuevo conector",
        description="Genera la estructura de directorios y archivos boilerplate para un nuevo conector.",
    )
    init_parser.add_argument("name", help="Nombre del conector (snake_case, ej: mi_conector)")
    init_parser.add_argument("--category", default="general", help="Categoria del conector (default: general)")
    init_parser.add_argument("--auth-type", default="none", choices=VALID_AUTH_TYPES,
                             help="Tipo de autenticacion del conector (default: none)")

    # ── test ───────────────────────────────────────────────────
    test_parser = subparsers.add_parser(
        "test",
        help="Ejecuta un conector en entorno sandbox",
        description="Importa, instancia y ejecuta un conector en un entorno aislado capturando resultados y errores.",
    )
    test_parser.add_argument("connector_path", help="Ruta al directorio del conector")
    test_parser.add_argument("--action", default="ping", help="Accion a ejecutar (default: ping)")
    test_parser.add_argument("--input", default=None,
                             help="Parametros de entrada como JSON string o ruta a archivo JSON")

    # ── validate ───────────────────────────────────────────────
    validate_parser = subparsers.add_parser(
        "validate",
        help="Valida estructura y esquema del conector",
        description="Verifica que el conector cumpla con todos los requisitos: archivos, herencia, metodos, esquema y auth.",
    )
    validate_parser.add_argument("connector_path", help="Ruta al directorio del conector")

    # ── publish ────────────────────────────────────────────────
    publish_parser = subparsers.add_parser(
        "publish",
        help="Empaqueta y publica al marketplace",
        description="Valida, empaqueta como .zip y publica el conector al registro del marketplace.",
    )
    publish_parser.add_argument("connector_path", help="Ruta al directorio del conector")
    publish_parser.add_argument("--registry", default=None,
                                help="URL del registro del marketplace")

    # ── version ────────────────────────────────────────────────
    version_parser = subparsers.add_parser(
        "version",
        help="Gestiona la version del conector",
        description="Muestra o actualiza la version del conector siguiendo semver.",
    )
    version_parser.add_argument("connector_path", help="Ruta al directorio del conector")
    version_parser.add_argument("--bump", choices=["major", "minor", "patch"], default=None,
                                help="Incrementa la version (major|minor|patch)")

    # ── list ───────────────────────────────────────────────────
    subparsers.add_parser(
        "list",
        help="Lista todos los conectores registrados",
        description="Muestra una tabla con nombre, version, categoria y estado de cada conector registrado.",
    )

    # ── info ───────────────────────────────────────────────────
    info_parser = subparsers.add_parser(
        "info",
        help="Muestra informacion detallada del conector",
        description="Muestra metadata, acciones, requisitos de autenticacion y esquema del conector.",
    )
    info_parser.add_argument("connector_name", help="Nombre del conector")

    return parser
