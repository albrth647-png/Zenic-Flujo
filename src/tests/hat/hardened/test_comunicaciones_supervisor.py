"""Tests para ComunicacionesSupervisor — routing real por keywords.

Cubre:
- Routing a EmailSpecialist (email, correo, gmail, smtp).
- Routing a ChatSpecialist (whatsapp, slack, telegram, chat).
- Routing a NotificationSpecialist (notificar, notificacion, cumpleanos).
- Fallback al primer specialist cuando no hay keyword match.
- Case-insensitive matching.
- Respuestas de error cuando faltan specialists.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.hat.level2_supervisors.comunicaciones.supervisor import ComunicacionesSupervisor


@pytest.fixture
def mock_specialists() -> dict[str, MagicMock]:
    """3 specialists mockeados: notification, email, chat."""
    return {
        "notification": MagicMock(),
        "email": MagicMock(),
        "chat": MagicMock(),
    }


@pytest.fixture
def supervisor(mock_specialists: dict[str, MagicMock]) -> ComunicacionesSupervisor:
    """ComunicacionesSupervisor con 3 specialists."""
    return ComunicacionesSupervisor(specialists=mock_specialists)


class TestRoutingToEmail:
    """Mensajes con keywords de Email rutean a EmailSpecialist."""

    @pytest.mark.parametrize("message", [
        "enviar email al cliente",
        "revisar correo electrónico",
        "configurar cuenta gmail",
        "probar conexión smtp",
    ])
    def test_email_keywords_route_to_email(
        self, supervisor: ComunicacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
        message: str,
    ) -> None:
        """Cada keyword de Email rutea al EmailSpecialist."""
        mock_specialists["email"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": message})
        mock_specialists["email"].handle.assert_called_once()
        assert result["status"] == "completed"
        assert result["specialists_used"] == ["email"]


class TestRoutingToChat:
    """Mensajes con keywords de Chat rutean a ChatSpecialist."""

    @pytest.mark.parametrize("message", [
        "enviar mensaje por whatsapp",
        "publicar en slack",
        "enviar por telegram",
        "iniciar chat con cliente",
    ])
    def test_chat_keywords_route_to_chat(
        self, supervisor: ComunicacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
        message: str,
    ) -> None:
        """Cada keyword de Chat rutea al ChatSpecialist."""
        mock_specialists["chat"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": message})
        mock_specialists["chat"].handle.assert_called_once()
        assert result["status"] == "completed"
        assert result["specialists_used"] == ["chat"]


class TestRoutingToNotification:
    """Mensajes con keywords de Notification rutean a NotificationSpecialist."""

    @pytest.mark.parametrize("message", [
        "notificar al equipo",
        "enviar notificacion masiva",
        "send notification to user",
        "recordatorio de cumpleanos",
        "enviar saludo de cumpleaños",
        "birthday campaign",
    ])
    def test_notification_keywords_route_to_notification(
        self, supervisor: ComunicacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
        message: str,
    ) -> None:
        """Cada keyword de Notification rutea al NotificationSpecialist."""
        mock_specialists["notification"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": message})
        mock_specialists["notification"].handle.assert_called_once()
        assert result["status"] == "completed"
        assert result["specialists_used"] == ["notification"]


class TestCaseInsensitive:
    """El matching de keywords es case-insensitive."""

    def test_uppercase_keywords_match(
        self, supervisor: ComunicacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Keywords en mayúsculas funcionan."""
        mock_specialists["email"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": "ENVIAR EMAIL AHORA"})
        mock_specialists["email"].handle.assert_called_once()
        assert result is not None


class TestFallback:
    """Fallback cuando no hay keyword match."""

    def test_fallback_to_first_specialist(
        self, supervisor: ComunicacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Sin keyword match → primer specialist (notification por inserción)."""
        mock_specialists["notification"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": "xyz qwerty unknown"})
        mock_specialists["notification"].handle.assert_called_once()
        assert result["specialists_used"] == ["notification"]


class TestErrors:
    """Manejo de errores."""

    def test_no_specialists_returns_failed(self) -> None:
        """Sin specialists → respuesta failed."""
        sup = ComunicacionesSupervisor(specialists=None)
        result = sup.handle({"description": "enviar email"})
        assert result["status"] == "failed"
        assert result["domain"] == "comunicaciones"
        assert "no specialists" in result["error"]

    def test_partial_specialists_set(
        self, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Si solo hay email y chat, routing a notification falla graceful."""
        partial = {
            "email": mock_specialists["email"],
            "chat": mock_specialists["chat"],
        }
        sup = ComunicacionesSupervisor(specialists=partial)
        result = sup.handle({"description": "notificar al equipo"})
        assert result["status"] == "failed"
        assert "notification" in result["error"]


class TestDomainAttribute:
    """El atributo domain está correctamente definido."""

    def test_domain_is_comunicaciones(
        self, supervisor: ComunicacionesSupervisor,
    ) -> None:
        """domain = 'comunicaciones'."""
        assert supervisor.domain == "comunicaciones"

    def test_keyword_map_is_populated(
        self, supervisor: ComunicacionesSupervisor,
    ) -> None:
        """_keyword_map tiene entradas para los 3 specialists."""
        assert len(supervisor._keyword_map) > 0
        specialists_in_map = set(supervisor._keyword_map.values())
        assert "email" in specialists_in_map
        assert "chat" in specialists_in_map
        assert "notification" in specialists_in_map


class TestRepr:
    """Representación string."""

    def test_repr_includes_domain(
        self, supervisor: ComunicacionesSupervisor,
    ) -> None:
        """__repr__ incluye 'comunicaciones' y los specialists."""
        r = repr(supervisor)
        assert "ComunicacionesSupervisor" in r
        assert "comunicaciones" in r
        assert "email" in r
