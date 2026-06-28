"""HAT NIVEL 2 — DatosAutoSupervisor (M8: routing real por keywords).

Sub-orquestador de datos + automatización. NO conoce a Operaciones ni Comunicaciones.

Coordina specialists (Nivel 3):
- DataSpecialist (DataKeeper + Sheets + Drive + PostgreSQL)
- ApiSpecialist (ApiConnector)
- CodeSpecialist (CodeRunner + LogicGate + Autopilot + OpenAI + Ollama)

Routing por keywords (case-insensitive):
- "data", "sheets", "drive", "postgres", "sql" → DataSpecialist
- "api", "http", "endpoint", "webhook" → ApiSpecialist
- "codigo", "code", "python", "openai", "ollama", "funcion" → CodeSpecialist

Si ningún keyword matchea, usa el primer specialist disponible (fallback graceful).

Implementación completa en M8.
"""
from __future__ import annotations

from typing import ClassVar

from src.core.logging import get_logger
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
from src.hat.level2_supervisors.base_router import SpecialistRouter

logger = get_logger("hat.level2.datos_auto")


class DatosAutoSupervisor(SpecialistRouter):
    """Sub-orquestador de datos y automatización con routing real por keywords.

    Hereda de :class:`SpecialistRouter` que implementa el routing genérico.
    Esta clase solo define el ``_keyword_map`` específico del dominio.
    """

    domain = "datos_auto"

    # Mapeo keyword → specialist_name.
    # Orden: keywords más específicas primero para evitar substrings.
    _KEYWORD_MAP: ClassVar[dict[str, str]] = {
        # === API (ApiConnector) — específicas primero ===
        "api": "api",
        "http": "api",
        "endpoint": "api",
        "webhook": "api",
        "rest": "api",
        # === Code (CodeRunner + LogicGate + Autopilot + OpenAI + Ollama) ===
        "openai": "code",
        "ollama": "code",
        "python": "code",
        "codigo": "code",
        "code": "code",
        "funcion": "code",
        "function": "code",
        "script": "code",
        "automatizar": "code",
        # === Data (DataKeeper + Sheets + Drive + PostgreSQL) ===
        "postgres": "data",
        "postgresql": "data",
        "sheets": "data",
        "drive": "data",
        "data": "data",
        "datos": "data",
        "sql": "data",

        # === CONECTORES EXTERNOS (Phase 4) ===
        "github": "code",
        "gitlab": "code",
        "jira": "api",
        "asana": "api",
        "trello": "api",
        "monday": "api",
        "notion": "data",
        "confluence": "data",
        "airtable": "data",
        "aws": "data",
        "azure": "data",
        "gcs": "data",
        "dropbox": "data",
        "datadog": "data",
        "grafana": "data",
        "sentry": "data",
        "pagerduty": "data",
        "anthropic": "code",
        "deepseek": "code",
        "huggingface": "code",
        "vault": "data",
        "okta": "data",
        "splunk": "data",
        "elastic": "data",
    }

    def __init__(
        self,
        specialists: dict | None = None,
        ledger: LedgerRepository | None = None,
    ) -> None:
        """Inicializa el supervisor de datos y automatización.

        Args:
            specialists: Dict con keys 'data', 'api', 'code' (o subset).
            ledger: LedgerRepository opcional (no usado en routing).
        """
        super().__init__(specialists=specialists, ledger=ledger)
        self._keyword_map = dict(self._KEYWORD_MAP)
        logger.info(
            "DatosAutoSupervisor inicializado con %d specialists, %d keywords",
            len(self._specialists), len(self._keyword_map),
        )
