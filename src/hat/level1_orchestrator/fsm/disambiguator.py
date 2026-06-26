"""
HAT-ORBITAL Nivel 0 — FSM ligera de desambiguación.

Cuando ORBITAL (RCC) devuelve top-3 dominios por resonancia y las diferencias
son pequeñas (< DISAMBIGUATION_THRESHOLD), esta FSM desambigua con reglas
explícitas. Si la diferencia es grande, ORBITAL decide solo (la FSM no se invoca).

Las 4 reglas, en orden de prioridad:
1. Clear winner: si top1 - top2 > threshold, ORBITAL decide solo → retorna top1.
2. Active domain: si Facts del Ledger indican un dominio activo y está en top2,
   priorizarlo (mantener contexto conversacional).
3. Keywords explícitas: si el input contiene keywords de un dominio presente en
   top2, ese dominio gana.
4. Clarify: si ninguna regla anterior resuelve, pedir aclaración al usuario.

Implementado en F0-D3 siguiendo HAT_ORBITAL_PLAN.md §2.3.
"""

from __future__ import annotations

from typing import Any, Final, Protocol

from src.core.logging import setup_logging

logger = setup_logging(__name__)

# Threshold por debajo del cual ORBITAL no es concluyente y se invoca la FSM.
# Valor 0.15 alineado con §2.3 del plan maestro (empírico, ajustable).
DISAMBIGUATION_THRESHOLD: Final[float] = 0.15

# Dominios canónicos de HAT-ORBITAL (M8: nuevos 3 dominios).
# Se mantienen los viejos por retrocompatibilidad con tests/sesiones existentes.
VALID_DOMAINS: Final[frozenset[str]] = frozenset({
    # M8 (actuales)
    "operaciones", "comunicaciones", "datos_auto",
    # Legacy (F0-F3)
    "research", "build", "operate",
})

# Resultado especial cuando ninguna regla resuelve y se debe pedir aclaración.
CLARIFY_DOMAIN: Final[str] = "clarify"

# Keywords explícitas por dominio (regla 3). Mínimo, legible, modificable.
DOMAIN_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    # M8: nuevos dominios
    "operaciones": (
        "cliente", "lead", "venta", "crm", "factura", "invoice",
        "cobro", "producto", "stock", "inventario", "listar",
        "crear lead", "crear factura", "pedido",
    ),
    "comunicaciones": (
        "email", "correo", "mensaje", "notificar", "notificación",
        "whatsapp", "slack", "telegram", "chat", "enviar",
    ),
    "datos_auto": (
        "código", "code", "python", "ejecutar", "script", "api",
        "consulta", "sql", "datos", "automatizar", "data",
        "función", "function",
    ),
    # Legacy (F0-F3) — se conservan para sesiones antiguas
    "build": (
        "código", "code", "deploy", "compilar", "test", "build",
        "función", "function", "clase", "class", "refactor",
        "crear", "generar", "implementar", "docker", "container",
    ),
    "research": (
        "buscar", "info", "investigar", "search", "find",
        "qué es", "que es", "documentación", "documentacion",
    ),
    "operate": (
        "monitor", "logs", "métricas", "metricas", "status",
        "incidente", "alerta", "estado", "salud",
    ),
}


class FactsProvider(Protocol):
    """Protocolo para obtener Facts del Ledger sin acoplamiento a LedgerRepository."""

    def get_fact(self, user_id: str, session_id: str, fact_key: str) -> dict[str, object] | None: ...


def fsm_disambiguate(
    top3_resonances: list[tuple[str, float]],
    user_input: str,
    active_domain: str | None = None,
) -> str:
    """Desambigua entre top-3 dominios cuando ORBITAL no es concluyente.

    Args:
        top3_resonances: Lista de tuplas (domain, resonance) ordenada desc por
            resonance. Debe tener al menos 1 elemento, idealmente 3.
            El caller es responsable de pasar la lista ordenada desc — no se
            re-ordena internamente.
        user_input: Texto original del usuario. Se normaliza a minúsculas.
            None y strings vacíos se tratan como sin keywords.
        active_domain: Dominio activo según Facts del Ledger. None si no hay
            Fact `active_domain` para la sesión.

    Returns:
        Dominio ganador: 'research' | 'build' | 'operate' | 'clarify'.
        Nunca retorna None. Retorna 'clarify' cuando ninguna regla resuelve
        o cuando los argumentos son inválidos (defensive).

    Raises:
        ValueError: Si `top3_resonances` está vacío.
        TypeError: Si `top3_resonances` contiene scores no numéricos.
    """
    if not top3_resonances:
        raise ValueError("top3_resonances no puede estar vacío")

    _validate_scores(top3_resonances)

    top1_domain, top1_score = top3_resonances[0]
    top2_domain, top2_score = _extract_top2(top3_resonances)

    logger.debug(
        "fsm_disambiguate: top1=%s (%.3f), top2=%s (%.3f), diff=%.3f, threshold=%.2f",
        top1_domain, top1_score, top2_domain, top2_score,
        top1_score - top2_score, DISAMBIGUATION_THRESHOLD,
    )

    if _is_clear_winner(top1_score, top2_score):
        result = _sanitize_domain(top1_domain)
        logger.info("Clear winner: %s (diff=%.3f > threshold=%.2f)", result, top1_score - top2_score, DISAMBIGUATION_THRESHOLD)
        return result

    top2_set = {top1_domain, top2_domain} - {None}

    active_result = _try_active_domain(active_domain, top2_set)
    if active_result is not None:
        logger.info("Active domain priority: %s", active_result)
        return active_result

    safe_input = user_input if isinstance(user_input, str) else ""
    keyword_result = _try_keywords(safe_input, top1_domain, top2_domain)
    if keyword_result is not None:
        logger.info("Keyword match resolved: %s", keyword_result)
        return keyword_result

    logger.info("No rule resolved -> clarify")
    return CLARIFY_DOMAIN


def _validate_scores(top3: list[tuple[str, float]]) -> None:
    """Valida que todos los scores sean numéricos (int/float, no bool).

    Raises:
        TypeError: Si algún score no es numérico.
    """
    for i, item in enumerate(top3):
        if len(item) < 2:
            raise TypeError(f"top3[{i}] no tiene score: {item!r}")
        score = item[1]
        # bool es subclase de int — lo excluimos explícitamente
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise TypeError(
                f"top3[{i}] score debe ser numérico, no {type(score).__name__}: {score!r}"
            )


def _extract_top2(top3: list[tuple[str, float]]) -> tuple[str | None, float]:
    """Extrae (domain, score) del segundo elemento, o (None, 0.0) si no existe."""
    if len(top3) > 1:
        return top3[1]
    return None, 0.0


def _is_clear_winner(top1_score: float, top2_score: float) -> bool:
    """Determina si top1 es claro ganador (diferencia > threshold estricto)."""
    return (top1_score - top2_score) > DISAMBIGUATION_THRESHOLD


def _try_active_domain(
    active_domain: str | None, top2_set: set[str | None],
) -> str | None:
    """Aplica regla 2: si active_domain está en top2 y es válido, gana.

    Returns:
        El dominio si aplica, None si no aplica.
    """
    if active_domain is None:
        return None
    if active_domain not in top2_set:
        return None
    if active_domain not in VALID_DOMAINS:
        return None
    return active_domain


def _try_keywords(
    user_input: str, top1_domain: str, top2_domain: str | None,
) -> str | None:
    """Aplica regla 3: si el input menciona keywords de un dominio en top2, gana.

    Returns:
        El dominio si aplica, None si no aplica.
    """
    text_lower = user_input.lower()
    for domain in (top1_domain, top2_domain):
        if domain is None or domain not in VALID_DOMAINS:
            continue
        keywords = DOMAIN_KEYWORDS.get(domain, ())
        if any(kw in text_lower for kw in keywords):
            return domain
    return None


def _sanitize_domain(domain: str) -> str:
    """Valida que un dominio sea uno de los canónicos; si no, retorna 'clarify'.

    Defensive: nunca propaga dominios inválidos al resto del sistema.

    Args:
        domain: Dominio retornado por ORBITAL o por las reglas previas.

    Returns:
        El dominio si es válido, 'clarify' en caso contrario.
    """
    if domain in VALID_DOMAINS:
        return domain
    return CLARIFY_DOMAIN
