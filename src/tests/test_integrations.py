"""
Tests para Integraciones (Sprint 7).
Tests mockeados para Gmail, Sheets, Telegram, Slack.
"""
from unittest.mock import patch, MagicMock
from src.tools.integrations.gmail_service import GmailService
from src.tools.integrations.sheets_service import SheetsService
from src.tools.integrations.telegram_service import TelegramService
from src.tools.integrations.slack_service import SlackService
from src.tools.integrations.gmail_service import GmailService
from src.tools.integrations.sheets_service import SheetsService
from src.tools.integrations.telegram_service import TelegramService
from src.tools.integrations.slack_service import SlackService


# ═══════════════════════════════════════════════════════════════
# GMAIL
# ═══════════════════════════════════════════════════════════════

class TestGmailService:
    """Tests para GmailService."""

    def _make_service(self):
        from src.tools.integrations.gmail_service import GmailService
        with patch("src.tools.integrations.gmail_service.DatabaseManager"):
            return GmailService()

    def test_not_configured(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = None
        result = svc.send_email(to="a@b.com", subject="Test", body="Hi")
        assert result["status"] == "error"
        assert "configurado" in result["message"].lower()

    def test_send_email(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"client_id":"x","client_secret":"y","refresh_token":"z"}'
        result = svc.send_email(to="test@example.com", subject="Hola", body="Mundo")
        assert result["status"] == "sent"
        assert "test@example.com" in result["to"]
        assert result["mode"] == "demo"

    def test_send_email_html(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"client_id":"x","client_secret":"y","refresh_token":"z"}'
        result = svc.send_email(to="a@b.com", subject="HTML", body="<h1>Hola</h1>", html=True)
        assert result["status"] == "sent"

    def test_search_emails(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"client_id":"x","client_secret":"y","refresh_token":"z"}'
        result = svc.search_emails(query="from:admin@test.com", max_results=5)
        assert result["status"] == "ok"
        assert result["query"] == "from:admin@test.com"

    def test_get_message(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"client_id":"x","client_secret":"y","refresh_token":"z"}'
        result = svc.get_message(message_id="msg123")
        assert result["status"] == "ok"
        assert result["message"]["id"] == "msg123"

    def test_list_labels(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"client_id":"x","client_secret":"y","refresh_token":"z"}'
        result = svc.list_labels()
        assert result["status"] == "ok"
        assert "INBOX" in result["labels"]

    def test_configure(self):
        svc = self._make_service()
        result = svc.configure("client_id", "secret", "refresh_token")
        assert result is True
        svc._db.set_setting.assert_called_once()

    def test_get_status(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = None
        status = svc.get_status()
        assert status["configured"] is False

    def test_tool_definition(self):
        defn = GmailService.get_tool_definition()
        assert defn["tool"] == "gmail"
        assert "send_email" in defn["actions"]
        assert "search_emails" in defn["actions"]


# ═══════════════════════════════════════════════════════════════
# GOOGLE SHEETS
# ═══════════════════════════════════════════════════════════════

class TestSheetsService:
    """Tests para SheetsService."""

    def _make_service(self):
        from src.tools.integrations.sheets_service import SheetsService
        with patch("src.tools.integrations.sheets_service.DatabaseManager"):
            return SheetsService()

    def test_not_configured(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = None
        result = svc.read_sheet(spreadsheet_id="abc123")
        assert result["status"] == "error"

    def test_read_sheet(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"project_id":"x","private_key":"y"}'
        result = svc.read_sheet(spreadsheet_id="sheet1", range="A1:D10")
        assert result["status"] == "ok"
        assert result["spreadsheet_id"] == "sheet1"

    def test_write_sheet(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"project_id":"x","private_key":"y"}'
        result = svc.write_sheet(
            spreadsheet_id="sheet1",
            range="A1",
            values=[["Name", "Email"], ["Test", "test@test.com"]],
        )
        assert result["status"] == "ok"
        assert result["updated_rows"] == 2

    def test_write_sheet_empty(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"project_id":"x","private_key":"y"}'
        result = svc.write_sheet(spreadsheet_id="sheet1", range="A1", values=[])
        assert result["status"] == "error"

    def test_append_row(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"project_id":"x","private_key":"y"}'
        result = svc.append_row("sheet1", "Hoja1", ["Juan", "juan@test.com"])
        assert result["status"] == "ok"
        assert result["updated_rows"] == 1

    def test_update_cell(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"project_id":"x","private_key":"y"}'
        result = svc.update_cell("sheet1", "Hoja1!B3", "nuevo valor")
        assert result["status"] == "ok"

    def test_create_spreadsheet(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = '{"project_id":"x","private_key":"y"}'
        result = svc.create_spreadsheet("Reporte mensual")
        assert result["status"] == "ok"
        assert "url" in result

    def test_configure_invalid_json(self):
        svc = self._make_service()
        result = svc.configure("not valid json {{{")
        assert result is False

    def test_tool_definition(self):
        defn = SheetsService.get_tool_definition()
        assert defn["tool"] == "sheets"
        assert "read_sheet" in defn["actions"]
        assert "write_sheet" in defn["actions"]


# ═══════════════════════════════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════════════════════════════

class TestTelegramService:
    """Tests para TelegramService."""

    def _make_service(self):
        from src.tools.integrations.telegram_service import TelegramService
        with patch("src.tools.integrations.telegram_service.DatabaseManager"):
            return TelegramService()

    def test_not_configured(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = None
        result = svc.send_message(chat_id="123", text="Hola")
        assert result["status"] == "error"
        assert "configurado" in result["message"].lower()

    def test_send_message_empty(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = "bot_token_123"
        result = svc.send_message(chat_id="123", text="")
        assert result["status"] == "error"

    @patch("src.tools.integrations.telegram_service.requests")
    def test_send_message_success(self, mock_requests):
        svc = self._make_service()
        svc._db.get_setting.return_value = "bot_token_123"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 42}}
        mock_requests.post.return_value = mock_resp
        result = svc.send_message(chat_id="123", text="Hola mundo")
        assert result["status"] == "sent"
        assert result["message_id"] == 42

    @patch("src.tools.integrations.telegram_service.requests")
    def test_send_message_api_error(self, mock_requests):
        svc = self._make_service()
        svc._db.get_setting.return_value = "bot_token_123"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "description": "Bad Request"}
        mock_requests.post.return_value = mock_resp
        result = svc.send_message(chat_id="123", text="Hola")
        assert result["status"] == "failed"
        assert "Bad Request" in result["error"]

    @patch("src.tools.integrations.telegram_service.requests")
    def test_send_photo(self, mock_requests):
        svc = self._make_service()
        svc._db.get_setting.return_value = "bot_token_123"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 100}}
        mock_requests.post.return_value = mock_resp
        result = svc.send_photo(chat_id="123", photo="https://example.com/img.png", caption="Foto")
        assert result["status"] == "sent"

    @patch("src.tools.integrations.telegram_service.requests")
    def test_get_updates(self, mock_requests):
        svc = self._make_service()
        svc._db.get_setting.return_value = "bot_token_123"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": [{"update_id": 1}]}
        mock_requests.get.return_value = mock_resp
        result = svc.get_updates(offset=0)
        assert result["status"] == "ok"
        assert result["count"] == 1

    def test_configure(self):
        svc = self._make_service()
        result = svc.configure("my_bot_token")
        assert result is True
        svc._db.set_setting.assert_called_once_with("telegram_bot_token", "my_bot_token")

    def test_get_status(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = None
        status = svc.get_status()
        assert status["configured"] is False

    def test_tool_definition(self):
        defn = TelegramService.get_tool_definition()
        assert defn["tool"] == "telegram"
        assert "send_message" in defn["actions"]
        assert "send_photo" in defn["actions"]


# ═══════════════════════════════════════════════════════════════
# SLACK
# ═══════════════════════════════════════════════════════════════

class TestSlackService:
    """Tests para SlackService."""

    def _make_service(self):
        from src.tools.integrations.slack_service import SlackService
        with patch("src.tools.integrations.slack_service.DatabaseManager"):
            return SlackService()

    def test_not_configured(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = None
        result = svc.send_message(channel="#test", text="Hola")
        assert result["status"] == "error"
        assert "configurado" in result["message"].lower()

    def test_send_message_empty(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = "xoxb-token"
        result = svc.send_message(channel="#test", text="")
        assert result["status"] == "error"

    @patch("src.tools.integrations.slack_service.requests")
    def test_send_message_success(self, mock_requests):
        svc = self._make_service()
        svc._db.get_setting.return_value = "xoxb-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        mock_requests.post.return_value = mock_resp
        result = svc.send_message(channel="#general", text="Hola Slack")
        assert result["status"] == "sent"
        assert result["message_id"] == "1234567890.123456"

    @patch("src.tools.integrations.slack_service.requests")
    def test_send_message_with_thread(self, mock_requests):
        svc = self._make_service()
        svc._db.get_setting.return_value = "xoxb-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "ts": "999.999"}
        mock_requests.post.return_value = mock_resp
        result = svc.send_message(channel="#general", text="Reply", thread_ts="111.111")
        assert result["status"] == "sent"

    @patch("src.tools.integrations.slack_service.requests")
    def test_send_message_api_error(self, mock_requests):
        svc = self._make_service()
        svc._db.get_setting.return_value = "xoxb-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "error": "channel_not_found"}
        mock_requests.post.return_value = mock_resp
        result = svc.send_message(channel="#bad", text="Test")
        assert result["status"] == "failed"
        assert "channel_not_found" in result["error"]

    @patch("src.tools.integrations.slack_service.requests")
    def test_list_channels(self, mock_requests):
        svc = self._make_service()
        svc._db.get_setting.return_value = "xoxb-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "channels": [{"id": "C001", "name": "general"}, {"id": "C002", "name": "random"}],
        }
        mock_requests.get.return_value = mock_resp
        result = svc.list_channels()
        assert result["status"] == "ok"
        assert result["count"] == 2
        assert result["channels"][0]["name"] == "general"

    @patch("src.tools.integrations.slack_service.requests")
    def test_get_user_info(self, mock_requests):
        svc = self._make_service()
        svc._db.get_setting.return_value = "xoxb-token"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "user": {"id": "U001", "name": "testuser", "real_name": "Test User",
                     "profile": {"email": "test@slack.com"}},
        }
        mock_requests.get.return_value = mock_resp
        result = svc.get_user_info("U001")
        assert result["status"] == "ok"
        assert result["user"]["email"] == "test@slack.com"

    def test_configure(self):
        svc = self._make_service()
        result = svc.configure("xoxb-my-token")
        assert result is True
        svc._db.set_setting.assert_called_once_with("slack_bot_token", "xoxb-my-token")

    def test_get_status(self):
        svc = self._make_service()
        svc._db.get_setting.return_value = None
        status = svc.get_status()
        assert status["configured"] is False

    def test_tool_definition(self):
        defn = SlackService.get_tool_definition()
        assert defn["tool"] == "slack"
        assert "send_message" in defn["actions"]
        assert "list_channels" in defn["actions"]
        assert "upload_file" in defn["actions"]
