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
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, SpecialistResult, Subtask


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

    # Tabla de routing por tool: (keywords_tool, [(keywords_action, action_name)], default_action)
    # Refactorizado de CC=52 a CC≈8 usando dict dispatch (Forge Fase 1.4).
    _ROUTING_TABLE: tuple[tuple[
        tuple[str, ...],                                  # keywords que activan este tool
        list[tuple[tuple[str, ...], str]],                # (keywords de action, action_name)
        str,                                              # default action
        str,                                              # tool name
    ], ...] = (
        (
            ("postgres", "postgresql", "sql", "base datos", "base de datos", "consulta sql"),
            [
                (("listar tablas", "list tables", "ver tablas"), "list_tables"),
                (("esquema", "schema", "estructura tabla"), "get_schema"),
                (("insertar", "crear registro", "alta", "insert"), "insert"),
                (("actualizar", "modificar", "update"), "update"),
                (("ejecutar", "execute", "ddl", "alter", "create table"), "execute"),
            ],
            "query",
            "postgresql",
        ),
        (
            ("drive", "google drive", "subir archivo", "archivo drive"),
            [
                (("subir", "upload", "subir archivo"), "upload"),
                (("descargar", "download", "bajar archivo"), "download"),
                (("buscar", "search"), "search"),
                (("eliminar archivo", "borrar archivo", "delete"), "delete"),
                (("crear carpeta", "nueva carpeta", "create folder"), "create_folder"),
            ],
            "list_files",
            "drive",
        ),
        (
            ("sheets", "hoja cálculo", "hoja calculo", "google sheets", "spreadsheet"),
            [
                (("escribir", "write", "sobrescribir"), "write_sheet"),
                (("añadir fila", "agregar fila", "append", "append row"), "append_row"),
                (("celda", "update cell", "actualizar celda"), "update_cell"),
                (("crear hoja", "nueva hoja", "create spreadsheet"), "create_spreadsheet"),
            ],
            "read_sheet",
            "sheets",
        ),
        (
            ("colección", "coleccion", "collection", "data keeper"),
            [
                (("crear colección", "crear coleccion", "create collection", "nueva colección"), "create_collection"),
                (("insertar", "agregar registro", "alta registro", "insert"), "insert"),
                (("actualizar", "modificar", "update"), "update"),
                (("eliminar", "borrar", "delete"), "delete"),
                (("consultar", "buscar", "query", "filtrar"), "query"),
                (("info colección", "info coleccion", "información colección"), "get_collection_info"),
            ],
            "list_collections",
            "data_keeper",
        ),
    )

    def _match_action(self, desc: str, actions: list[tuple[tuple[str, ...], str]], default: str) -> str:
        """Devuelve la primera action cuyas keywords matcheen, sino default."""
        for keywords, action_name in actions:
            if any(kw in desc for kw in keywords):
                return action_name
        return default

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask.

        Implementación basada en tabla de routing (`_ROUTING_TABLE`) para
        mantener baja la complejidad ciclomática. Antes CC=52, ahora CC≈8.
        """
        desc = (subtask.get("description") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        for tool_keywords, actions, default_action, tool_name in self._ROUTING_TABLE:
            if any(kw in desc for kw in tool_keywords):
                action_name = self._match_action(desc, actions, default_action)
                return tool_name, action_name, params

        # Default seguro: listar colecciones en data_keeper
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
