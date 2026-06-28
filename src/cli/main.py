"""
Zenic CLI — Punto de Entrada Principal
========================================

Interfaz de linea de comandos para el desarrollo de conectores Zenic-Flijo.

Uso:
    python -m src.cli.main init <name> [--category ...] [--auth-type ...]
    python -m src.cli.main test <path> [--action ...] [--input ...]
    python -m src.cli.main validate <path>
    python -m src.cli.main publish <path> [--registry ...]
    python -m src.cli.main version <path> [--bump major|minor|patch]
    python -m src.cli.main list
    python -m src.cli.main info <name>
"""

from __future__ import annotations

import sys

from src.cli.commands import COMMAND_MAP, build_parser
from src.core.logging import setup_logging

logger = setup_logging(__name__)

CLI_VERSION = "1.0.0"


def main(argv: list[str] | None = None) -> int:
    """
    Punto de entrada principal del CLI.

    Parsea los argumentos de linea de comandos y despacha al
    subcomando correspondiente usando COMMAND_MAP.

    Args:
        argv: Lista de argumentos (default: sys.argv[1:])

    Retorna:
        Codigo de salida (0 = exito, 1 = error)
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    handler = COMMAND_MAP.get(args.command)
    if handler is None:
        print(f"Error: Comando desconocido '{args.command}'", file=sys.stderr)
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\nOperacion cancelada por el usuario", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error inesperado: {exc}", file=sys.stderr)
        logger.error(f"Error en comando '{args.command}': {exc}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
