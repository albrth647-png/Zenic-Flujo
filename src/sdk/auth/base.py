"""
Connector SDK — AuthProvider (Clase Base Abstracta)
====================================================

Define la interfaz comun que todos los proveedores de autenticacion
deben implementar para el sistema de conectores de Zenic-Flijo.

Cada proveedor maneja un tipo especifico de autenticacion y sabe
como aplicar sus credenciales a una peticion HTTP.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AuthProvider(ABC):
    """
    Clase base abstracta para proveedores de autenticacion.

    Define la interfaz comun que todos los proveedores de auth
    deben implementar. Cada proveedor maneja un tipo especifico
    de autenticacion y sabe como aplicar sus credenciales a
    una peticion HTTP.
    """

    @abstractmethod
    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Aplica las credenciales de autenticacion a una peticion.

        Modifica la peticion (headers, params, etc.) para incluir
        las credenciales apropiadas segun el tipo de autenticacion.

        Args:
            request: Diccionario con la peticion HTTP (debe tener al menos 'headers' y 'params')

        Retorna:
            Peticion modificada con las credenciales aplicadas
        """

    @abstractmethod
    def refresh(self) -> bool:
        """
        Renueva las credenciales de autenticacion.

        Implementa la logica de renovacion de credenciales
        cuando sea soportada (ej: OAuth2 token refresh).

        Retorna:
            True si la renovacion fue exitosa, False en caso contrario
        """

    @abstractmethod
    def is_expired(self) -> bool:
        """
        Verifica si las credenciales han expirado.

        Retorna:
            True si las credenciales expiraron o no son validas
        """

    @abstractmethod
    def validate(self) -> bool:
        """
        Valida que las credenciales sean correctas y esten completas.

        Verifica que todos los campos requeridos esten presentes
        y tengan valores validos. No verifica contra el servicio externo.

        Retorna:
            True si las credenciales son validas localmente
        """

    def get_auth_type(self) -> str:
        """
        Retorna el tipo de autenticacion como string.

        Retorna:
            Nombre del tipo de autenticacion (ej: 'api_key', 'basic', 'oauth2')
        """
        return self.__class__.__name__.replace("Auth", "").lower()

    def to_dict(self) -> dict[str, Any]:
        """
        Serializa la configuracion de auth a diccionario (sin secretos).

        Retorna:
            Diccionario con la configuracion de auth, excluyendo valores sensibles
        """
        return {
            "auth_type": self.get_auth_type(),
            "expired": self.is_expired(),
            "valid": self.validate(),
        }
