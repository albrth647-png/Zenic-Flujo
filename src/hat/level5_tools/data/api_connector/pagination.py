"""
Pagination Collector — Recolección automática de datos paginados.
Sprint 5.2 del Roadmap Competitivo.
"""

from __future__ import annotations

from typing import ClassVar


class PaginationCollector:
    """
    Recolecta datos paginados automáticamente.

    Estrategias:
    - page: paginación clásica (?page=1&limit=10)
    - cursor: paginación por cursor (?cursor=abc123)
    - offset: paginación por offset (?offset=0&limit=10)

    Detecta automáticamente next_page/cursor/offset de la respuesta
    y continúa recolectando hasta max_pages o condición de parada.
    """

    NEXT_PAGE_KEYS: ClassVar[set[str]] = {"next_page", "nextPage", "next", "next_url", "nextUrl"}
    CURSOR_KEYS: ClassVar[set[str]] = {"cursor", "next_cursor", "nextCursor", "after", "page_token", "pageToken"}
    HAS_MORE_KEYS: ClassVar[set[str]] = {"has_more", "hasMore", "more"}
    TOTAL_KEYS: ClassVar[set[str]] = {"total", "total_count", "totalCount", "count", "total_items", "totalItems"}

    def __init__(self, max_pages: int = 10, max_total_items: int = 1000):
        self.max_pages = max_pages
        self.max_total_items = max_total_items

    def collect_page_based(self, url: str, params: dict, response: dict, pages_left: int) -> dict:
        if pages_left <= 0:
            return {"next_url": None, "next_params": None, "stop": True}
        current_page = int(params.get("page", 1))
        next_page = current_page + 1
        body = response.get("body", {})
        if isinstance(body, dict):
            for key in self.HAS_MORE_KEYS:
                if key in body and not body[key]:
                    return {"next_url": None, "next_params": None, "stop": True}
            limit = int(params.get("limit", params.get("per_page", 20)))
            for key in self.TOTAL_KEYS:
                total = body.get(key)
                if total is not None:
                    last_page = (int(total) + limit - 1) // limit
                    if current_page >= last_page:
                        return {"next_url": None, "next_params": None, "stop": True}
                    break
            for key in self.NEXT_PAGE_KEYS:
                np = body.get(key)
                if np is not None:
                    if np == current_page or np is False or np == "":
                        return {"next_url": None, "next_params": None, "stop": True}
                    break
        new_params = dict(params)
        new_params["page"] = next_page
        return {"next_url": url, "next_params": new_params, "stop": False}

    def collect_cursor_based(self, url: str, params: dict, response: dict, pages_left: int) -> dict:
        if pages_left <= 0:
            return {"next_url": None, "next_params": None, "stop": True}
        body = response.get("body", {})
        if not isinstance(body, dict):
            return {"next_url": None, "next_params": None, "stop": True}
        next_cursor = None
        for key in self.CURSOR_KEYS:
            cursor = body.get(key)
            if cursor is not None and cursor != "":
                next_cursor = cursor
                break
        if not next_cursor:
            for key in self.HAS_MORE_KEYS:
                if key in body and not body[key]:
                    return {"next_url": None, "next_params": None, "stop": True}
            return {"next_url": None, "next_params": None, "stop": True}
        new_params = dict(params)
        cursor_param = None
        for p in params:
            if p.lower() in {"cursor", "after", "page_token", "starting_after"}:
                cursor_param = p
                break
        if cursor_param:
            new_params[cursor_param] = next_cursor
        else:
            new_params["cursor"] = next_cursor
        return {"next_url": url, "next_params": new_params, "stop": False}

    def collect_offset_based(self, url: str, params: dict, response: dict, pages_left: int) -> dict:
        if pages_left <= 0:
            return {"next_url": None, "next_params": None, "stop": True}
        current_offset = int(params.get("offset", 0))
        limit = int(params.get("limit", 20))
        body = response.get("body", {})
        items = None
        if isinstance(body, list):
            items = body
        elif isinstance(body, dict):
            for key in ["data", "items", "results", "records", "results_list"]:
                val = body.get(key)
                if isinstance(val, list):
                    items = val
                    break
        if items is not None and len(items) < limit:
            return {"next_url": None, "next_params": None, "stop": True}
        if isinstance(body, dict):
            for key in self.TOTAL_KEYS:
                total = body.get(key)
                if total is not None:
                    if current_offset + limit >= int(total):
                        return {"next_url": None, "next_params": None, "stop": True}
                    break
        new_params = dict(params)
        new_params["offset"] = current_offset + limit
        return {"next_url": url, "next_params": new_params, "stop": False}
