"""
Metricas de Auth/Security — login attempts, API keys, RBAC checks.

Responsabilidad:
- ``record_login_attempt``: contador por method+status + contador de
  fallos por method.
- ``record_api_key_created``: contador por user_id.
- ``record_rbac_check``: contador por permission+granted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class AuthMetricsMixin:
    """Metricas de seguridad y autenticacion."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_login_attempt(
        self,
        username: str = "",
        status: str = "success",
        method: str = "password",
    ) -> None:
        """
        Registra un intento de inicio de sesion.

        Args:
            username: Nombre de usuario (anonimizado)
            status: Estado (success, failed)
            method: Metodo de autenticacion (password, mfa, sso, api_key)
        """
        self._metrics.increment_counter(
            "security_login_attempts_total",
            labels={"method": method, "status": status},
        )
        if status == "failed":
            self._metrics.increment_counter(
                "security_login_failures_total",
                labels={"method": method},
            )

    def record_api_key_created(self, user_id: str = "") -> None:
        """
        Registra la creacion de una API key.

        Args:
            user_id: ID del usuario
        """
        self._metrics.increment_counter(
            "security_api_keys_created_total",
            labels={"user_id": user_id},
        )

    def record_rbac_check(self, permission: str, granted: bool) -> None:
        """
        Registra una verificacion de permisos RBAC.

        Args:
            permission: Permiso verificado
            granted: Si fue concedido
        """
        self._metrics.increment_counter(
            "security_rbac_checks_total",
            labels={"permission": permission, "granted": str(granted)},
        )
