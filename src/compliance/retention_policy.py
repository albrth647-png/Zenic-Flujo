"""Políticas de retención de evidencia por jurisdicción LATAM.

Foso 1 — Compliance Reproducible Banca LATAM.

Reguladores y requerimientos de retención (años):

    País       Regulador   Bank/Fin  Healthcare  PII
    ----------------------------------------------------
    México     CNBV        10        10          5
    Brasil     BACEN       10        10          5
    Argentina  BCRA/CNV    10        10          5
    Colombia   SFC         5         10          5
    Chile      CMF         5         10          5
    Perú       SBS         10        10          5
    Ecuador    SBS         7         10          5
    Uruguay    BCU         10        10          5
    Paraguay   BCP         5         10          5
    Bolivia    ASFI        10        10          5

Las políticas se aplican al purgar audit_log_chain y orbital_executions:
cualquier entry con antiguedad > retention_days NO se elimina, sino que
se archiva (move-to-cold-storage) o se mantiene en sitio.

Uso:
    from src.compliance.retention_policy import get_retention_days, should_purge
    days = get_retention_days("MX", "banking")  # → 3650
    should = should_purge(entry_timestamp, country="MX", data_type="banking")
"""
from __future__ import annotations

import time
from typing import Any

# Retención en días por (país, tipo_de_dato).
# Tipo: banking | healthcare | pii | general
# Basado en regulaciones LATAM vigentes a junio 2026.
RETENTION_DAYS: dict[tuple[str, str], int] = {
    # México — CNBV (banca) / INAI (PII)
    ("MX", "banking"): 365 * 10,
    ("MX", "healthcare"): 365 * 10,
    ("MX", "pii"): 365 * 5,
    ("MX", "general"): 365 * 5,
    # Brasil — BACEN (banca) / ANPD (PII, LGPD)
    ("BR", "banking"): 365 * 10,
    ("BR", "healthcare"): 365 * 10,
    ("BR", "pii"): 365 * 5,
    ("BR", "general"): 365 * 5,
    # Argentina — BCRA (banca) / CNV (financiero) / AAIP (PII)
    ("AR", "banking"): 365 * 10,
    ("AR", "healthcare"): 365 * 10,
    ("AR", "pii"): 365 * 5,
    ("AR", "general"): 365 * 5,
    # Colombia — SFC (financiero) / SIC (PII)
    ("CO", "banking"): 365 * 5,
    ("CO", "healthcare"): 365 * 10,
    ("CO", "pii"): 365 * 5,
    ("CO", "general"): 365 * 5,
    # Chile — CMF (banca) / SAG (salud)
    ("CL", "banking"): 365 * 5,
    ("CL", "healthcare"): 365 * 10,
    ("CL", "pii"): 365 * 5,
    ("CL", "general"): 365 * 5,
    # Perú — SBS (banca) / INDECOPI (PII)
    ("PE", "banking"): 365 * 10,
    ("PE", "healthcare"): 365 * 10,
    ("PE", "pii"): 365 * 5,
    ("PE", "general"): 365 * 5,
    # Ecuador — SBS (banca) / SPD (PII)
    ("EC", "banking"): 365 * 7,
    ("EC", "healthcare"): 365 * 10,
    ("EC", "pii"): 365 * 5,
    ("EC", "general"): 365 * 5,
    # Uruguay — BCU
    ("UY", "banking"): 365 * 10,
    ("UY", "healthcare"): 365 * 10,
    ("UY", "pii"): 365 * 5,
    ("UY", "general"): 365 * 5,
    # Paraguay — BCP
    ("PY", "banking"): 365 * 5,
    ("PY", "healthcare"): 365 * 10,
    ("PY", "pii"): 365 * 5,
    ("PY", "general"): 365 * 5,
    # Bolivia — ASFI
    ("BO", "banking"): 365 * 10,
    ("BO", "healthcare"): 365 * 10,
    ("BO", "pii"): 365 * 5,
    ("BO", "general"): 365 * 5,
}

# Default fallback (5 años, conservador) si país no está listado.
DEFAULT_RETENTION_DAYS = 365 * 5

# Regulador oficial por país (para reportes regulatorios).
REGULATOR_BY_COUNTRY: dict[str, str] = {
    "MX": "CNBV",
    "BR": "BACEN",
    "AR": "BCRA",
    "CO": "SFC",
    "CL": "CMF",
    "PE": "SBS",
    "EC": "SBS",
    "UY": "BCU",
    "PY": "BCP",
    "BO": "ASFI",
}


def get_retention_days(country_code: str, data_type: str = "banking") -> int:
    """Retorna los días de retención obligatoria para un país y tipo de dato.

    Args:
        country_code: ISO 3166-1 alpha-2 (MX, BR, AR, CO, CL, PE, EC, UY, PY, BO).
        data_type: Tipo de dato (banking, healthcare, pii, general).

    Returns:
        Días de retención. Default 5 años (1825) si país no está listado.
    """
    return RETENTION_DAYS.get(
        (country_code.upper(), data_type.lower()),
        DEFAULT_RETENTION_DAYS,
    )


def get_regulator_name(country_code: str) -> str:
    """Retorna el nombre del regulador financiero de un país LATAM."""
    return REGULATOR_BY_COUNTRY.get(country_code.upper(), "Desconocido")


def should_purge(
    entry_timestamp: float,
    country_code: str = "MX",
    data_type: str = "banking",
    now: float | None = None,
) -> bool:
    """Determina si un entry puede ser purgado/archivado según la política.

    Un entry puede purgarse cuando su antiguedad excede el período de retención
    obligatorio del país. Antes de eso, debe conservarse in situ para auditoría.

    Args:
        entry_timestamp: Unix timestamp del entry.
        country_code: ISO 3166-1 alpha-2.
        data_type: Tipo de dato.
        now: Timestamp de referencia (default: time.time()).

    Returns:
        True si el entry puede purgarse (retención cumplida), False si debe
        conservarse.
    """
    if now is None:
        now = time.time()
    age_days = (now - entry_timestamp) / 86400
    retention_days = get_retention_days(country_code, data_type)
    return age_days > retention_days


def list_retention_policies() -> list[dict[str, Any]]:
    """Lista todas las políticas de retención como dicts ordenados.

    Útil para exponer vía API /api/v2/compliance/retention-policies.
    """
    policies: list[dict[str, Any]] = []
    for (country, data_type), days in sorted(RETENTION_DAYS.items()):
        policies.append(
            {
                "country": country,
                "regulator": get_regulator_name(country),
                "data_type": data_type,
                "retention_days": days,
                "retention_years": round(days / 365, 1),
            }
        )
    return policies
