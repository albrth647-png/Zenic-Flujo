"""
Tests para Sprint 6 del Roadmap Competitivo.
Cubre: OpenAI, Ollama, PostgreSQL, Google Drive, Stripe, MercadoPago.
Todos los tests usan mocks para no hacer llamadas reales a APIs.
"""

from unittest.mock import MagicMock, patch

from src.tools.integrations.drive_service import DriveService
from src.tools.integrations.mercadopago_service import MercadoPagoService
from src.tools.integrations.ollama_service import OllamaService
from src.tools.integrations.openai_service import OpenAIService
from src.tools.integrations.postgresql_service import PostgreSQLService
from src.tools.integrations.stripe_service import StripeService

# ===================================================================
# OpenAI
# ===================================================================


class TestOpenAIService:
    """Tests para OpenAI connector."""

    def test_chat_no_api_key(self):
        """Chat sin API key retorna error."""
        svc = OpenAIService(api_key="")
        result = svc.chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert result["status"] == "failed"
        assert "no configurada" in result.get("error", "")

    @patch("requests.post")
    def test_chat_completion(self, mock_post):
        """Chat completion exitosa."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello!", "role": "assistant"}, "finish_reason": "stop"}],
            "model": "gpt-4o-mini",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_post.return_value = mock_response

        svc = OpenAIService(api_key="sk-test123")
        result = svc.chat_completion(messages=[{"role": "user", "content": "Say hello"}])
        assert result["content"] == "Hello!"
        assert result["model"] == "gpt-4o-mini"
        assert result["usage"]["total_tokens"] == 15

    @patch("requests.post")
    def test_chat_api_error(self, mock_post):
        """Chat con error de API."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": {"message": "Invalid request"}}
        mock_post.return_value = mock_response

        svc = OpenAIService(api_key="sk-test123")
        result = svc.chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert result["status"] == "failed"

    @patch("requests.post")
    def test_embeddings(self, mock_post):
        """Embeddings exitoso."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
            "model": "text-embedding-3-small",
            "usage": {"prompt_tokens": 5, "total_tokens": 5},
        }
        mock_post.return_value = mock_response

        svc = OpenAIService(api_key="sk-test123")
        result = svc.embeddings("test text")
        assert len(result["embeddings"]) == 1
        assert result["dimension"] == 3

    @patch("requests.get")
    def test_list_models(self, mock_get):
        """Listar modelos."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4o", "created": 123, "owned_by": "openai"},
                {"id": "gpt-4o-mini", "created": 456, "owned_by": "openai"},
            ]
        }
        mock_get.return_value = mock_response

        svc = OpenAIService(api_key="sk-test123")
        result = svc.list_models()
        assert result["count"] == 2

    def test_get_tool_definition(self):
        """Definición de tool."""
        definition = OpenAIService.get_tool_definition()
        assert definition["tool"] == "openai"
        assert "chat_completion" in definition["actions"]
        assert "embeddings" in definition["actions"]


# ===================================================================
# Ollama
# ===================================================================


class TestOllamaService:
    """Tests para Ollama connector."""

    @patch("requests.post")
    def test_chat(self, mock_post):
        """Chat con Ollama."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "llama3.2",
            "message": {"content": "Hello from local LLM!", "role": "assistant"},
            "total_duration": 1000000,
            "eval_count": 50,
            "done": True,
        }
        mock_post.return_value = mock_response

        svc = OllamaService(base_url="http://localhost:11434")
        result = svc.chat(messages=[{"role": "user", "content": "Hi"}])
        assert result["content"] == "Hello from local LLM!"
        assert result["model"] == "llama3.2"

    @patch("requests.post")
    def test_generate(self, mock_post):
        """Generate texto."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "llama3.2",
            "response": "Generated text",
            "total_duration": 500000,
            "eval_count": 25,
            "done": True,
        }
        mock_post.return_value = mock_response

        svc = OllamaService(base_url="http://localhost:11434")
        result = svc.generate(prompt="Write something")
        assert result["response"] == "Generated text"

    @patch("requests.post")
    def test_embeddings(self, mock_post):
        """Embeddings Ollama."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.5, 0.5, 0.5]}
        mock_post.return_value = mock_response

        svc = OllamaService(base_url="http://localhost:11434")
        result = svc.embeddings("test")
        assert result["count"] == 1
        assert result["dimension"] == 3

    @patch("requests.get")
    def test_list_models(self, mock_get):
        """Listar modelos instalados."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2:latest", "modified_at": "2024-01-01", "size": 1000},
                {"name": "mistral:latest", "modified_at": "2024-01-02", "size": 2000},
            ]
        }
        mock_get.return_value = mock_response

        svc = OllamaService()
        result = svc.list_models()
        assert result["count"] == 2

    @patch("requests.post")
    def test_connection_error(self, mock_post):
        """Error de conexión."""
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError()

        svc = OllamaService(base_url="http://localhost:11434")
        result = svc.generate(prompt="test")
        assert result["status"] == "failed"
        assert "conectar" in result.get("error", "")

    @patch("requests.post")
    def test_pull_model(self, mock_post):
        """Descargar modelo."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        svc = OllamaService()
        result = svc.pull_model("llama3.2")
        assert result["status"] == "downloaded"

    def test_get_health(self):
        """Health check sin conexión real."""
        result = OllamaService.get_health(base_url="http://localhost:11434")
        assert "status" in result


# ===================================================================
# PostgreSQL
# ===================================================================


class TestPostgreSQLService:
    """Tests para PostgreSQL connector."""

    def test_query_no_connection(self):
        """Query sin connection string."""
        svc = PostgreSQLService()
        result = svc.query("SELECT 1")
        assert result["status"] == "failed"

    def test_execute_no_connection(self):
        """Execute sin connection string."""
        svc = PostgreSQLService()
        result = svc.execute("CREATE TABLE test (id int)")
        assert result["status"] == "failed"

    def test_insert_no_data(self):
        """Insert sin datos."""
        svc = PostgreSQLService()
        result = svc.insert("users", {}, connection_string="pg://localhost")
        assert result["status"] == "failed"

    def test_update_no_data(self):
        """Update sin datos."""
        svc = PostgreSQLService()
        result = svc.update("users", {}, where="1=1", connection_string="pg://localhost")
        assert result["status"] == "failed"

    def test_serialize_datetime(self):
        """Serialización de datetime."""
        from datetime import datetime

        result = PostgreSQLService._serialize(datetime(2024, 1, 1, 12, 0))
        assert "2024" in result

    def test_serialize_bytes(self):
        """Serialización de bytes."""
        result = PostgreSQLService._serialize(b"hello")
        assert result == "hello"

    def test_get_tool_definition(self):
        """Definición de tool."""
        definition = PostgreSQLService.get_tool_definition()
        assert definition["tool"] == "postgresql"
        assert "query" in definition["actions"]
        assert "insert" in definition["actions"]


# ===================================================================
# Google Drive
# ===================================================================


class TestDriveService:
    """Tests para Google Drive connector."""

    def test_list_no_token(self):
        """List sin token."""
        svc = DriveService()
        result = svc.list_files()
        assert result["status"] == "failed"

    def test_upload_no_token(self):
        """Upload sin token."""
        svc = DriveService()
        result = svc.upload(file_name="test.txt", content_base64="aGVsbG8=")
        assert result["status"] == "failed"

    def test_upload_no_filename(self):
        """Upload sin nombre."""
        svc = DriveService()
        result = svc.upload(access_token="tok", file_name="", content_base64="aGVsbG8=")
        assert result["status"] == "failed"

    def test_download_no_token(self):
        """Download sin token."""
        svc = DriveService()
        result = svc.download(file_id="abc123")
        assert result["status"] == "failed"

    def test_delete_no_token(self):
        """Delete sin token."""
        svc = DriveService()
        result = svc.delete(file_id="abc123")
        assert result["status"] == "failed"

    def test_search_no_query(self):
        """Search sin query."""
        svc = DriveService()
        result = svc.search(access_token="tok", query="")
        assert result["status"] == "failed"

    def test_create_folder_no_token(self):
        """Crear folder sin token."""
        svc = DriveService()
        result = svc.create_folder(folder_name="test")
        assert result["status"] == "failed"

    @patch("requests.get")
    def test_list_files_success(self, mock_get):
        """Listar archivos exitoso."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "files": [
                {
                    "id": "1",
                    "name": "doc.txt",
                    "mimeType": "text/plain",
                    "size": "100",
                    "createdTime": "2024-01-01",
                    "modifiedTime": "2024-01-02",
                    "webViewLink": "https://drive.google.com/file/d/1",
                }
            ]
        }
        mock_get.return_value = mock_response

        svc = DriveService()
        result = svc.list_files(access_token="tok", folder_id="root")
        assert result["count"] == 1
        assert result["files"][0]["name"] == "doc.txt"


# ===================================================================
# Stripe
# ===================================================================


class TestStripeService:
    """Tests para Stripe connector."""

    def test_payment_intent_no_key(self):
        """PI sin key."""
        svc = StripeService()
        result = svc.create_payment_intent(amount=1000)
        assert result["status"] == "failed"

    def test_payment_intent_zero_amount(self):
        """PI con amount 0."""
        svc = StripeService()
        result = svc.create_payment_intent(secret_key="sk_test", amount=0)
        assert result["status"] == "failed"

    @patch("requests.post")
    def test_create_payment_intent(self, mock_post):
        """Crear PI exitoso."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "pi_123",
            "amount": 5000,
            "currency": "usd",
            "status": "requires_payment_method",
            "client_secret": "secret_abc",
        }
        mock_post.return_value = mock_response

        svc = StripeService()
        result = svc.create_payment_intent(secret_key="sk_test", amount=5000)
        assert result["id"] == "pi_123"
        assert result["status"] == "requires_payment_method"

    @patch("requests.post")
    def test_create_customer(self, mock_post):
        """Crear customer."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "cus_123",
            "email": "test@test.com",
            "name": "Test",
            "created": 1700000000,
        }
        mock_post.return_value = mock_response

        svc = StripeService()
        result = svc.create_customer(secret_key="sk_test", email="test@test.com")
        assert result["id"] == "cus_123"

    @patch("requests.get")
    def test_list_customers(self, mock_get):
        """Listar customers."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "cus_1", "email": "a@a.com", "name": "A", "created": 100}]}
        mock_get.return_value = mock_response

        svc = StripeService()
        result = svc.list_customers(secret_key="sk_test")
        assert result["count"] == 1

    @patch("requests.post")
    def test_create_subscription(self, mock_post):
        """Crear suscripción."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "sub_123",
            "status": "active",
            "customer": "cus_123",
            "current_period_start": 100,
            "current_period_end": 200,
        }
        mock_post.return_value = mock_response

        svc = StripeService()
        result = svc.create_subscription(secret_key="sk_test", customer_id="cus_123", price_id="price_123")
        assert result["id"] == "sub_123"
        assert result["status"] == "active"

    @patch("requests.get")
    def test_list_invoices(self, mock_get):
        """Listar facturas."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "in_1",
                    "number": "INV-001",
                    "amount_due": 5000,
                    "currency": "usd",
                    "status": "paid",
                    "paid": True,
                }
            ]
        }
        mock_get.return_value = mock_response

        svc = StripeService()
        result = svc.list_invoices(secret_key="sk_test")
        assert result["count"] == 1

    @patch("requests.post")
    @patch("requests.post")
    @patch("requests.post")
    def test_create_payment_link(self, mock_pl, mock_price, mock_product):
        """Crear payment link."""
        mock_product.return_value = MagicMock(status_code=200, json=lambda: {"id": "prod_123"})
        mock_price.return_value = MagicMock(status_code=200, json=lambda: {"id": "price_123"})
        mock_pl.return_value = MagicMock(
            status_code=200, json=lambda: {"id": "pl_123", "url": "https://buy.stripe.com/test"}
        )

        svc = StripeService()
        result = svc.create_payment_link(secret_key="sk_test", amount=1000)
        assert "url" in result


# ===================================================================
# MercadoPago
# ===================================================================


class TestMercadoPagoService:
    """Tests para MercadoPago connector."""

    def test_create_preference_no_token(self):
        """Preferencia sin token."""
        svc = MercadoPagoService()
        result = svc.create_preference(items=[{"title": "test", "quantity": 1, "unit_price": 100}])
        assert result["status"] == "failed"

    def test_create_preference_no_items(self):
        """Preferencia sin items."""
        svc = MercadoPagoService()
        result = svc.create_preference(access_token="tok")
        assert result["status"] == "failed"

    @patch("requests.post")
    def test_create_preference_success(self, mock_post):
        """Crear preferencia exitosa."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "12345",
            "init_point": "https://mercadopago.com/checkout/12345",
            "sandbox_init_point": "https://sandbox.mercadopago.com/checkout/12345",
            "items": [{"title": "test", "quantity": 1, "unit_price": 100}],
            "external_reference": "ref123",
            "collector_id": 123456,
        }
        mock_post.return_value = mock_response

        svc = MercadoPagoService()
        result = svc.create_preference(
            access_token="tok",
            items=[{"title": "Producto", "quantity": 1, "unit_price": 100.0}],
            external_reference="order_123",
        )
        assert result["id"] == "12345"
        assert "init_point" in result

    @patch("requests.get")
    def test_get_payment(self, mock_get):
        """Consultar pago."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "status": "approved",
            "status_detail": "accredited",
            "transaction_amount": 100.0,
            "payer": {"email": "test@test.com", "first_name": "Juan"},
            "payment_method_id": "visa",
            "external_reference": "order_123",
        }
        mock_get.return_value = mock_response

        svc = MercadoPagoService()
        result = svc.get_payment(access_token="tok", payment_id=12345)
        assert result["status"] == "approved"
        assert result["amount"] == 100.0

    @patch("requests.get")
    def test_search_payments(self, mock_get):
        """Buscar pagos."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 1,
                    "status": "approved",
                    "transaction_amount": 100.0,
                    "payer": {"email": "a@a.com"},
                    "external_reference": "ref1",
                    "date_created": "2024-01-01",
                }
            ],
            "paging": {"total": 1},
        }
        mock_get.return_value = mock_response

        svc = MercadoPagoService()
        result = svc.search_payments(access_token="tok")
        assert result["count"] == 1

    @patch("requests.post")
    def test_create_customer(self, mock_post):
        """Crear customer."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "12345",
            "email": "test@test.com",
            "first_name": "Juan",
        }
        mock_post.return_value = mock_response

        svc = MercadoPagoService()
        result = svc.create_customer(access_token="tok", email="test@test.com")
        assert result["id"] == "12345"

    def test_process_webhook_no_data(self):
        """Webhook sin datos."""
        svc = MercadoPagoService()
        result = svc.process_webhook()
        assert result["status"] == "failed"

    def test_process_webhook_acknowledged(self):
        """Webhook sin payment type."""
        svc = MercadoPagoService()
        result = svc.process_webhook(
            access_token="tok",
            notification_data={
                "action": "created",
                "type": "merchant_order",
                "data": {"id": "order_123"},
            },
        )
        assert result["status"] == "acknowledged"


# ===================================================================
# Tool definitions
# ===================================================================


class TestToolDefinitions:
    """Tests para definiciones de herramientas."""

    def test_openai_definition(self):
        d = OpenAIService.get_tool_definition()
        assert d["tool"] == "openai"

    def test_ollama_definition(self):
        d = OllamaService.get_tool_definition()
        assert d["tool"] == "ollama"

    def test_postgresql_definition(self):
        d = PostgreSQLService.get_tool_definition()
        assert d["tool"] == "postgresql"

    def test_drive_definition(self):
        d = DriveService.get_tool_definition()
        assert d["tool"] == "drive"

    def test_stripe_definition(self):
        d = StripeService.get_tool_definition()
        assert d["tool"] == "stripe"

    def test_mercadopago_definition(self):
        d = MercadoPagoService.get_tool_definition()
        assert d["tool"] == "mercadopago"
