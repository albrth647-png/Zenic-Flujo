"""src.core.utils.binaries — Resolucion segura de paths de binarios.

Mitigacion del hallazgo Bandit B607 (Starting a process with a partial
executable path). Split de ``src/utils/helpers.py`` (M1.4).
"""

from __future__ import annotations

import shutil


# Caché de paths resueltos para no llamar shutil.which() en cada invocation.
_RESOLVED_BIN_CACHE: dict[str, str | None] = {}


def resolve_binary(name: str, *, allow_none: bool = False) -> str | None:
    """Resuelve un binario a su path absoluto usando shutil.which().

    MITIGACIÓN de B607 (Bandit): Starting a process with a partial executable path.
    Permite a un atacante que controla la variable de entorno PATH ejecutar un
    binario malicioso en lugar del binario legítimo. Esta función resuelve
    el nombre del binario a un path absoluto UNA SOLA VEZ y lo cachea.

    Args:
        name: Nombre del binario (ej. 'python', 'ruff', 'ollama').
        allow_none: Si True, retorna None cuando el binario no está en PATH
                    en vez de lanzar FileNotFoundError.

    Returns:
        Path absoluto al binario, o None si allow_none=True y no se encontró.

    Raises:
        FileNotFoundError: Si el binario no está en PATH y allow_none=False.
    """
    if name in _RESOLVED_BIN_CACHE:
        path = _RESOLVED_BIN_CACHE[name]
    else:
        path = shutil.which(name)
        _RESOLVED_BIN_CACHE[name] = path

    if path is None:
        if allow_none:
            return None
        raise FileNotFoundError(
            f"Binario '{name}' no encontrado en PATH. Instálelo o verifique su configuración."
        )
    return path


__all__ = ["resolve_binary", "_RESOLVED_BIN_CACHE"]
