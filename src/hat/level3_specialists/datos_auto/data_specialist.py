"""
HAT NIVEL 3 — DataSpecialist
=============================

UNA SOLA RESPONSABILIDAD: Datos persistentes (colecciones + hojas + archivos + SQL).

Coordina los workers del Nivel 4 para las tools (Nivel 5):
- data_keeper (DataKeeperService): create_collection, insert, query, update, delete,
  list_collections, get_collection_info
- sheets (SheetsService): read_sheet, write_sheet, append_row, update_cell,
  create_spreadsheet
- drive (DriveService): upload, download, list_files, search, delete, create_folder
- postgresql (PostgreSQLService): query, insert, update, execute, list_tables,
  get_schema

Routing por keywords:
- "colección", "collection", "data keeper" → data_keeper actions
- "sheets", "hoja cálculo" → sheets actions
- "drive", "google drive", "subir archivo" → drive actions
- "postgres", "sql", "base datos", "consulta sql" → postgresql actions
- Default: data_keeper.list_collections
"""

from __future__ import annotations
from typing import Any

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, Subtask, SpecialistResult


class DataSpecialist(SpecialistAgent):
    """Specialist con UNA responsabilidad: datos (DataKeeper + Sheets + Drive + PostgreSQL)."""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        super().__init__(
            specialist_name="data",
            responsibility="datos_persistentes",
            tools=tools or {},
        )

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="data",
            agent_name="Data",
            domain="datos_auto",
            tier="specialist",
            capabilities=[
                # data_keeper
                "create_collection", "insert", "query", "update", "delete",
                "list_collections", "get_collection_info",
                # sheets
                "read_sheet", "write_sheet", "append_row", "update_cell",
                "create_spreadsheet",
                # drive
                "upload", "download", "list_files", "search", "delete",
                "create_folder",
                # postgresql
                "query", "insert", "update", "execute", "list_tables", "get_schema",
            ],
            cost_per_call=0.0,
            avg_latency_ms=80,
            orbital_keywords=[
                "dato", "datos", "colección", "coleccion", "collection",
                "data keeper", "sheets", "hoja cálculo", "hoja calculo",
                "drive", "google drive", "subir archivo", "archivo",
                "postgres", "postgresql", "sql", "base datos", "consulta sql",
                "tabla", "registro", "almacenar",
            ],
            orbital_amplitude=1.5,
            orbital_velocity=0.05,
        )

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask."""
        desc = (subtask.get("description") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        # --- PostgreSQL routing ---
        if any(kw in desc for kw in ["postgres", "postgresql", "sql", "base datos", "base de datos", "consulta sql"]):
            if any(kw in desc for kw in ["listar tablas", "list tables", "ver tablas"]):
                return "postgresql", "list_tables", params
            if any(kw in desc for kw in ["esquema", "schema", "estructura tabla"]):
                return "postgresql", "get_schema", params
            if any(kw in desc for kw in ["insertar", "crear registro", "alta", "insert"]):
                return "postgresql", "insert", params
            if any(kw in desc for kw in ["actualizar", "modificar", "update"]):
                return "postgresql", "update", params
            if any(kw in desc for kw in ["ejecutar", "execute", "ddl", "alter", "create table"]):
                return "postgresql", "execute", params
            # Default postgresql: query
            return "postgresql", "query", params

        # --- Drive routing ---
        if any(kw in desc for kw in ["drive", "google drive", "subir archivo", "archivo drive"]):
            if any(kw in desc for kw in ["subir", "upload", "subir archivo"]):
                return "drive", "upload", params
            if any(kw in desc for kw in ["descargar", "download", "bajar archivo"]):
                return "drive", "download", params
            if any(kw in desc for kw in ["buscar", "search"]):
                return "drive", "search", params
            if any(kw in desc for kw in ["eliminar archivo", "borrar archivo", "delete"]):
                return "drive", "delete", params
            if any(kw in desc for kw in ["crear carpeta", "nueva carpeta", "create folder"]):
                return "drive", "create_folder", params
            # Default drive: listar archivos
            return "drive", "list_files", params

        # --- Sheets routing ---
        if any(kw in desc for kw in ["sheets", "hoja cálculo", "hoja calculo", "google sheets", "spreadsheet"]):
            if any(kw in desc for kw in ["escribir", "write", "sobrescribir"]):
                return "sheets", "write_sheet", params
            if any(kw in desc for kw in ["añadir fila", "agregar fila", "append", "append row"]):
                return "sheets", "append_row", params
            if any(kw in desc for kw in ["celda", "update cell", "actualizar celda"]):
                return "sheets", "update_cell", params
            if any(kw in desc for kw in ["crear hoja", "nueva hoja", "create spreadsheet"]):
                return "sheets", "create_spreadsheet", params
            # Default sheets: leer
            return "sheets", "read_sheet", params

        # --- DataKeeper routing ---
        if any(kw in desc for kw in ["colección", "coleccion", "collection", "data keeper"]):
            if any(kw in desc for kw in ["crear colección", "crear coleccion", "create collection", "nueva colección"]):
                return "data_keeper", "create_collection", params
            if any(kw in desc for kw in ["insertar", "agregar registro", "alta registro", "insert"]):
                return "data_keeper", "insert", params
            if any(kw in desc for kw in ["actualizar", "modificar", "update"]):
                return "data_keeper", "update", params
            if any(kw in desc for kw in ["eliminar", "borrar", "delete"]):
                return "data_keeper", "delete", params
            if any(kw in desc for kw in ["consultar", "buscar", "query", "filtrar"]):
                return "data_keeper", "query", params
            if any(kw in desc for kw in ["info colección", "info coleccion", "información colección"]):
                return "data_keeper", "get_collection_info", params
            # Default data_keeper: listar colecciones
            return "data_keeper", "list_collections", params

        # --- Default seguro: listar colecciones ---
        return "data_keeper", "list_collections", params

    def handle(self, subtask: Subtask) -> SpecialistResult:
        """Ejecuta el specialist: route → invoke tool → return result."""
        import time
        start = time.monotonic()

        tool_name, action_name, params = self.route_action(subtask)
        tool = self._tools.get(tool_name)

        if tool is None:
            return SpecialistResult(
                status="failed",
                error=f"tool '{tool_name}' not available",
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            method = getattr(tool, action_name)
            result = method(**params) if params else method()
            return SpecialistResult(
                status="completed",
                action=action_name,
                result=result,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:
            return SpecialistResult(
                status="failed",
                error=str(exc),
                action=action_name,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
