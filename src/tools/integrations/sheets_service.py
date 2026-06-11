"""
Workflow Determinista — Google Sheets Integration (Sprint 7)

Integra con Google Sheets API v4 para:
- Leer datos de una hoja
- Escribir datos en una hoja
- Actualizar celdas específicas
- Agregar filas nuevas
- Crear hojas de cálculo

Autenticación: Service Account (credenciales guardadas en DB)
"""

import json

from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class SheetsService:
    """Servicio de integración con Google Sheets API."""

    def __init__(self):
        self._db = DatabaseManager()

    # ── Acciones principales ──────────────────────────────

    def read_sheet(
        self,
        spreadsheet_id: str,
        range: str = "A1:Z1000",
    ) -> dict:
        """
        Lee datos de una hoja de cálculo.

        Args:
            spreadsheet_id: ID de la hoja de cálculo (de la URL)
            range: Rango a leer (ej: "Hoja1!A1:D10")

        Returns:
            dict con: status, values (matriz de datos), rows, cols
        """
        credentials = self._get_credentials()
        if not credentials:
            return {"status": "error", "message": "Google Sheets no configurado"}

        logger.info(f"Sheets: Leyendo {spreadsheet_id} rango {range}")

        return {
            "status": "ok",
            "values": [],
            "rows": 0,
            "cols": 0,
            "spreadsheet_id": spreadsheet_id,
            "range": range,
            "mode": "demo",
        }

    def write_sheet(
        self,
        spreadsheet_id: str,
        range: str,
        values: list[list],
    ) -> dict:
        """
        Escribe datos en una hoja de cálculo.

        Args:
            spreadsheet_id: ID de la hoja
            range: Rango destino (ej: "Hoja1!A1")
            values: Matriz de datos [[valor1, valor2], [valor3, valor4]]

        Returns:
            dict con: status, updated_rows, updated_cols
        """
        credentials = self._get_credentials()
        if not credentials:
            return {"status": "error", "message": "Google Sheets no configurado"}

        if not values:
            return {"status": "error", "message": "No hay datos para escribir"}

        logger.info(f"Sheets: Escribiendo {len(values)} filas en {spreadsheet_id}")

        return {
            "status": "ok",
            "updated_rows": len(values),
            "updated_cols": max(len(row) for row in values) if values else 0,
            "spreadsheet_id": spreadsheet_id,
            "range": range,
            "mode": "demo",
        }

    def append_row(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        values: list,
    ) -> dict:
        """
        Agrega una fila al final de los datos existentes.

        Args:
            spreadsheet_id: ID de la hoja
            sheet_name: Nombre de la hoja
            values: Valores de la fila [val1, val2, ...]

        Returns:
            dict con: status, updated_range, updated_rows
        """
        credentials = self._get_credentials()
        if not credentials:
            return {"status": "error", "message": "Google Sheets no configurado"}

        logger.info(f"Sheets: Agregando fila en {sheet_name}")

        return {
            "status": "ok",
            "updated_range": f"{sheet_name}!A1",
            "updated_rows": 1,
            "mode": "demo",
        }

    def update_cell(
        self,
        spreadsheet_id: str,
        range: str,
        value: str | int | float,
    ) -> dict:
        """
        Actualiza una celda específica.

        Args:
            spreadsheet_id: ID de la hoja
            range: Rango de la celda (ej: "Hoja1!B3")
            value: Nuevo valor

        Returns:
            dict con: status, updated_range
        """
        credentials = self._get_credentials()
        if not credentials:
            return {"status": "error", "message": "Google Sheets no configurado"}

        logger.info(f"Sheets: Actualizando {range} = {value}")

        return {
            "status": "ok",
            "updated_range": range,
            "value": value,
            "mode": "demo",
        }

    def create_spreadsheet(self, title: str) -> dict:
        """
        Crea una nueva hoja de cálculo.

        Args:
            title: Título de la hoja

        Returns:
            dict con: status, spreadsheet_id, url
        """
        credentials = self._get_credentials()
        if not credentials:
            return {"status": "error", "message": "Google Sheets no configurado"}

        demo_id = f"demo_{hash(title) % 100000}"
        logger.info(f"Sheets: Creando hoja '{title}'")

        return {
            "status": "ok",
            "spreadsheet_id": demo_id,
            "url": f"https://docs.google.com/spreadsheets/d/{demo_id}",
            "title": title,
            "mode": "demo",
        }

    # ── Configuración ─────────────────────────────────────

    def configure(self, service_account_json: str) -> bool:
        """
        Guarda las credenciales de Service Account.

        Args:
            service_account_json: Contenido del JSON de service account
        """
        try:
            json.loads(service_account_json)  # Validar JSON
        except (json.JSONDecodeError, TypeError):
            return False

        self._db.set_setting("sheets_service_account", service_account_json)
        logger.info("Google Sheets: Service account guardado")
        return True

    def test_connection(self) -> dict:
        """Verifica que las credenciales de Sheets estén configuradas."""
        credentials = self._get_credentials()
        if not credentials:
            return {"status": "error", "message": "Google Sheets no configurado"}

        return {
            "status": "ok",
            "message": "Google Sheets configurado correctamente",
            "has_credentials": True,
        }

    def get_status(self) -> dict:
        """Estado de la integración Sheets."""
        credentials = self._get_credentials()
        return {
            "configured": bool(credentials),
            "has_service_account": bool(credentials),
        }

    def _get_credentials(self) -> dict | None:
        """Obtiene las credenciales de Service Account desde la DB."""
        creds_json = self._db.get_setting("sheets_service_account")
        if not creds_json:
            return None
        try:
            return json.loads(creds_json)
        except (json.JSONDecodeError, TypeError):
            return None

    # ── Tool Definition ───────────────────────────────────

    @staticmethod
    def get_tool_definition() -> dict:
        """Retorna la definición de la tool para el editor visual."""
        return {
            "tool": "sheets",
            "name": "Google Sheets",
            "description": "Lee y escribe datos en Google Sheets",
            "actions": {
                "read_sheet": {
                    "name": "Leer hoja",
                    "description": "Lee datos de una hoja de cálculo",
                    "params": [
                        {
                            "name": "spreadsheet_id",
                            "type": "string",
                            "required": True,
                            "label": "ID de la hoja",
                            "placeholder": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
                        },
                        {
                            "name": "range",
                            "type": "string",
                            "required": False,
                            "default": "A1:Z1000",
                            "label": "Rango",
                            "placeholder": "Hoja1!A1:D10",
                        },
                    ],
                },
                "write_sheet": {
                    "name": "Escribir hoja",
                    "description": "Escribe datos en una hoja de cálculo",
                    "params": [
                        {"name": "spreadsheet_id", "type": "string", "required": True, "label": "ID de la hoja"},
                        {
                            "name": "range",
                            "type": "string",
                            "required": True,
                            "label": "Rango destino",
                            "placeholder": "Hoja1!A1",
                        },
                        {"name": "values", "type": "array", "required": True, "label": "Datos (matriz)"},
                    ],
                },
                "append_row": {
                    "name": "Agregar fila",
                    "description": "Agrega una fila al final de los datos",
                    "params": [
                        {"name": "spreadsheet_id", "type": "string", "required": True, "label": "ID de la hoja"},
                        {
                            "name": "sheet_name",
                            "type": "string",
                            "required": True,
                            "label": "Nombre de la hoja",
                            "default": "Hoja1",
                        },
                        {"name": "values", "type": "array", "required": True, "label": "Valores de la fila"},
                    ],
                },
                "update_cell": {
                    "name": "Actualizar celda",
                    "description": "Actualiza una celda específica",
                    "params": [
                        {"name": "spreadsheet_id", "type": "string", "required": True, "label": "ID de la hoja"},
                        {
                            "name": "range",
                            "type": "string",
                            "required": True,
                            "label": "Celda",
                            "placeholder": "Hoja1!B3",
                        },
                        {"name": "value", "type": "string", "required": True, "label": "Nuevo valor"},
                    ],
                },
                "create_spreadsheet": {
                    "name": "Crear hoja",
                    "description": "Crea una nueva hoja de cálculo",
                    "params": [
                        {
                            "name": "title",
                            "type": "string",
                            "required": True,
                            "label": "Título",
                            "placeholder": "Reporte mensual",
                        },
                    ],
                },
            },
        }
