"""Tests para el API Connector Service."""
from unittest.mock import patch, MagicMock


class TestAPIConnectorService:
    """Tests para APIConnectorService."""

    def test_request_get_success(self):
        """Test: GET request exitoso retorna datos."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"id": 1, "name": "Test"}
        mock_response.elapsed.total_seconds.return_value = 0.5

        with patch("requests.request", return_value=mock_response) as mock_req:
            result = service.request(
                method="GET",
                url="https://api.example.com/users/1",
            )

        assert result["status_code"] == 200
        assert result["body"] == {"id": 1, "name": "Test"}
        assert result["duration_ms"] >= 0
        assert "content-type" in result["headers"]
        # requests.request usa keyword arguments (method=, url=)
        mock_req.assert_called_once_with(
            method="GET", url="https://api.example.com/users/1",
            headers=None, json=None, data=None, params=None,
            auth=None, timeout=30,
        )

    def test_request_post_with_body(self):
        """Test: POST request con body JSON."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_response.json.return_value = {"id": 42}
        mock_response.elapsed.total_seconds.return_value = 0.3

        with patch("requests.request", return_value=mock_response):
            result = service.request(
                method="POST",
                url="https://api.example.com/users",
                body={"name": "Juan", "email": "juan@test.com"},
                headers={"Authorization": "Bearer token123"},
            )

        assert result["status_code"] == 201
        assert result["body"] == {"id": 42}

    def test_request_with_bearer_auth(self):
        """Test: autenticación Bearer token."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.elapsed.total_seconds.return_value = 0.1

        with patch("requests.request", return_value=mock_response) as mock_req:
            service.request(
                method="GET",
                url="https://api.example.com/protected",
                auth_type="bearer",
                auth_credentials={"token": "abc123"},
            )

        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["headers"] == {"Authorization": "Bearer abc123"}

    def test_request_with_basic_auth(self):
        """Test: autenticación Basic Auth."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.elapsed.total_seconds.return_value = 0.1

        with patch("requests.request", return_value=mock_response) as mock_req:
            service.request(
                method="GET",
                url="https://api.example.com/protected",
                auth_type="basic",
                auth_credentials={"username": "admin", "password": "pass123"},
            )

        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["auth"] is not None

    def test_request_with_query_params(self):
        """Test: query parameters en la URL."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_response.elapsed.total_seconds.return_value = 0.2

        with patch("requests.request", return_value=mock_response) as mock_req:
            service.request(
                method="GET",
                url="https://api.example.com/search",
                params={"q": "test", "limit": 10},
            )

        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["params"] == {"q": "test", "limit": 10}

    def test_request_with_custom_headers(self):
        """Test: headers personalizados."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.elapsed.total_seconds.return_value = 0.1

        with patch("requests.request", return_value=mock_response) as mock_req:
            service.request(
                method="POST",
                url="https://api.example.com/data",
                headers={"X-Custom": "value123", "Accept": "application/json"},
                body={"key": "value"},
            )

        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["headers"]["X-Custom"] == "value123"
        assert call_kwargs["headers"]["Accept"] == "application/json"

    def test_request_timeout(self):
        """Test: timeout configurable."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.elapsed.total_seconds.return_value = 5.0

        with patch("requests.request", return_value=mock_response) as mock_req:
            service.request(
                method="GET",
                url="https://api.example.com/slow",
                timeout=60,
            )

        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["timeout"] == 60

    def test_request_connection_error(self):
        """Test: error de conexión retorna dict con error."""
        from src.tools.api_connector.service import APIConnectorService
        import requests
        service = APIConnectorService()

        with patch("requests.request", side_effect=requests.ConnectionError("Connection refused")):
            result = service.request(
                method="GET",
                url="https://api.example.com/nonexistent",
            )

        assert "error" in result
        assert "Connection refused" in result["error"]
        assert result["status_code"] == 0

    def test_request_timeout_error(self):
        """Test: timeout retorna dict con error."""
        from src.tools.api_connector.service import APIConnectorService
        import requests
        service = APIConnectorService()

        with patch("requests.request", side_effect=requests.Timeout("Request timed out")):
            result = service.request(
                method="GET",
                url="https://api.example.com/slow",
            )

        assert "error" in result
        assert "timed out" in result["error"].lower()

    def test_request_non_json_response(self):
        """Test: respuesta no-JSON retorna texto como body."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "Hello, world!"
        mock_response.elapsed.total_seconds.return_value = 0.1

        with patch("requests.request", return_value=mock_response):
            result = service.request(
                method="GET",
                url="https://api.example.com/text",
            )

        assert result["body"] == "Hello, world!"

    def test_request_400_error(self):
        """Test: error HTTP 400 retorna el body de error."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"error": "Bad request", "details": "email inválido"}
        mock_response.elapsed.total_seconds.return_value = 0.1

        with patch("requests.request", return_value=mock_response):
            result = service.request(
                method="POST",
                url="https://api.example.com/users",
                body={"email": "invalido"},
            )

        assert result["status_code"] == 400
        assert "Bad request" in str(result["body"])

    def test_validate_url_valid(self):
        """Test: validación de URLs válidas."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        assert service.validate_url("https://api.example.com/users") is True
        assert service.validate_url("http://localhost:3000/api") is True
        assert service.validate_url("https://jsonplaceholder.typicode.com/posts/1") is True

    def test_validate_url_invalid(self):
        """Test: validación rechaza URLs inválidas o peligrosas."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        assert service.validate_url("") is False
        assert service.validate_url("not-a-url") is False
        assert service.validate_url("ftp://files.example.com") is False
        assert service.validate_url("file:///etc/passwd") is False
        assert service.validate_url("javascript:alert(1)") is False

    def test_get_tool_definition(self):
        """Test: definición de la tool para el editor."""
        from src.tools.api_connector.service import APIConnectorService
        service = APIConnectorService()

        definition = service.get_tool_definition()
        assert definition["tool"] == "api_connector"
        assert "request" in definition["actions"]
        request_action = definition["actions"]["request"]
        params = {p["name"] for p in request_action["params"]}
        assert "method" in params
        assert "url" in params
        assert "body" in params
        assert "headers" in params
        assert "auth_type" in params
