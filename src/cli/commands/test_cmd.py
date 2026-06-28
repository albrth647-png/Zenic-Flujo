"""
Zenic CLI — Comando: test
Ejecuta un conector en un entorno sandbox aislado.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cli.commands.helpers import _load_connector, _parse_input
from src.cli.sandbox import SandboxExecutor


def cmd_test(args: argparse.Namespace) -> int:
    """
    Ejecuta un conector en un entorno sandbox aislado.

    Importa e instancia el conector desde la ruta especificada,
    ejecuta el ciclo de vida completo (connect -> execute -> disconnect)
    y muestra los resultados con tiempos y errores.

    Args:
        args: Argumentos parseados con 'connector_path', 'action', 'input'

    Retorna:
        0 si la ejecucion fue exitosa, 1 si hubo errores
    """
    connector_path = Path(args.connector_path)
    action = getattr(args, "action", "ping") or "ping"
    input_data = getattr(args, "input", None)
    params = _parse_input(input_data)

    connector = _load_connector(connector_path)
    if connector is None:
        return 1

    print(f"Ejecutando conector '{connector.name}' en sandbox...")
    print(f"  Accion:  {action}")
    print(f"  Params:  {json.dumps(params, default=str, ensure_ascii=False)}")
    print()

    executor = SandboxExecutor(timeout=30, capture_output=True, mock_infra=True)
    result = executor.run(connector, action=action, params=params)
    print(result.format_report())

    return 0 if result.success else 1
