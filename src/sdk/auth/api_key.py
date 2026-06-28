"""
Connector SDK — APIKeyAuth
==========================

Autenticacion mediante API key via header o query parameter.
Soporta envio por header ('X-API-Key'), query parameter ('api_key'), o ambos.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.auth.base import AuthProvider

logger = setup_logging(__name__)


class APIKeyAuth(AuthProvider):
    """
    Autenticacion mediante API key via header o query parameter.

    Soporta dos modos de envio:
    - header: La API key se envia como header HTTP (default: 'X-API-Key')
    - query: La API key se envia como parametro de query (default: 'api_key')

    Args:
        api_key: Valor de la API key
        header_name: Nombre del header para enviar la key (default: 'X-API-Key')
        query_name: Nombre del param de query (default: 'api_key')
        location: Donde enviar la key: 'header', 'query', o 'both'
    """

    def __init__(
        self,
        api_key: str,
        header_name: str = "X-API-Key",
        query_name: str = "api_key",
        location: str = "header",
    ) -> None:
        self._api_key = api_key
        self._header_name = header_name
        self._query_name = query_name
        self._location = location

    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Aplica la API key a la peticion segun la ubicacion configurada.

        Args:
            request: Peticion HTTP con headers y params

        Retorna:
            Peticion con la API key aplicada
        """
        request.setdefault("headers", {})
        request.setdefault("params", {})

        if self._location in ("header", "both"):
            request["headers"][self._header_name] = self._api_key
        if self._location in ("query", "both"):
            request["params"][self._query_name] = self._api_key

        logger.debug(f"APIKeyAuth: key aplicada via {self._location}")
        return request

    def refresh(self) -> bool:
        """Las API keys estaticas no soportan renovacion automatica."""
        logger.debug("APIKeyAuth: renovacion no soportada para API keys estaticas")
        return False

    def is_expired(self) -> bool:
        """Las API keys estaticas no expiran (se asume validas hasta revocacion)."""
        return False

    def validate(self) -> bool:
        """Valida que la API key no este vacia."""
        return bool(self._api_key and self._api_key.strip())

    def to_dict(self) -> dict[str, Any]:
        """Serializa la config de API key (oculta el valor real)."""
        result = super().to_dict()
        result["header_name"] = self._header_name
        result["query_name"] = self._query_name
        result["location"] = self._location
        result["api_key_masked"] = f"{'*' * 8}{self._api_key[-4:]}" if len(self._api_key) > 4 else "****"
        return result
