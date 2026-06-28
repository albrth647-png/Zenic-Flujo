"""HAT-ORBITAL Nivel 1 — Keyword Router (extraído de tick_router.py en M8).

Capa de routing por keywords explícitas + FSM de desambiguación.

Cuándo se invoca:
1. Después de ``OrbitalRouter.route()`` que retorna top-3 dominios por resonancia.
2. Si la diferencia ``top1 - top2`` es pequeña (< ``DISAMBIGUATION_THRESHOLD``),
   la FSM desambigua con reglas explícitas.
3. Si el mensaje contiene keywords explícitas de un dominio en top3, ese
   dominio gana directamente (M10.1 fix — override de la resonancia ORBITAL).

Las 4 reglas de la FSM (en orden de prioridad):
1. **Clear winner**: si ``top1 - top2 > threshold``, ORBITAL decide sola.
2. **Active domain**: si el Fact 'active_domain' del Ledger está en top2, priorizarlo.
3. **Keywords explícitas**: si el input contiene keywords de un dominio en top2, gana.
4. **Clarify**: si ninguna regla resuelve, pedir aclaración al usuario.

Diseño:
- Stateless (no mantiene estado entre calls).
- No conoce OrbitalContext ni Ledger — recibe ``active_domain`` como parámetro.
- Delega el matching de keywords a ``DOMAIN_KEYWORDS`` de ``fsm/disambiguator``.

Implementado en M8 siguiendo IMPLEMENTATION_PLAN.md §M8.
"""
from __future__ import annotations

from src.core.logging import setup_logging
from src.hat.level1_orchestrator.fsm.disambiguator import (
    CLARIFY_DOMAIN,
    DOMAIN_KEYWORDS,
    VALID_DOMAINS,
    fsm_disambiguate,
)

logger = setup_logging(__name__)


class KeywordRouter:
    """Router por keywords explícitas + FSM de desambiguación.

    Recibe el top-3 dominios de ``OrbitalRouter`` y decide el dominio
    ganador aplicando (en orden): keyword override → FSM.

    Attributes:
        _active_domain: Dominio activo del Ledger (Fact 'active_domain'),
            o None si no hay. Se pasa en el constructor para mantener
            la clase stateless entre calls.
    """

    def __init__(self, active_domain: str | None = None) -> None:
        """Inicializa el router con el dominio activo opcional.

        Args:
            active_domain: Dominio activo según Facts del Ledger. None si
                no hay Fact ``active_domain`` para la sesión.
        """
        self._active_domain = active_domain
        logger.info("KeywordRouter initialized with active_domain=%s", active_domain)

    # ── API pública ────────────────────────────────────────────────────

    def set_active_domain(self, domain: str | None) -> None:
        """Actualiza el dominio activo (tras cada dispatch exitoso)."""
        old = self._active_domain
        self._active_domain = domain
        logger.debug("Active domain changed: %s -> %s", old, domain)

    def disambiguate(
        self,
        top3: list[tuple[str, float]],
        message: str,
    ) -> str:
        """Aplica keyword override + FSM para elegir el dominio ganador.

        Flujo:
        1. Si ``top3`` está vacío → ``'clarify'``.
        2. Si el mensaje contiene keywords de un dominio en top3 → ese dominio
           (M10.1 override, no pasa por FSM).
        3. Sino, delega a ``fsm_disambiguate(top3, message, active_domain)``.

        Args:
            top3: Top-3 dominios por resonancia ORBITAL, ordenado desc.
                Debe tener al menos 1 elemento (si no, retorna 'clarify').
            message: Texto original del usuario. Se normaliza a minúsculas.

        Returns:
            Dominio ganador: ``'operaciones'`` | ``'comunicaciones'`` |
            ``'datos_auto'`` | ``'clarify'``. Nunca retorna None.
        """
        if not top3:
            logger.warning("disambiguate called with empty top3, returning clarify")
            return CLARIFY_DOMAIN

        logger.debug("disambiguate: top3=%s, message=%.80s", top3, message)

        keyword_domain = self.match_keyword_domain(message, top3)
        if keyword_domain is not None:
            logger.info("Keyword override: %s (message contained matching keywords)", keyword_domain)
            return keyword_domain

        result = fsm_disambiguate(top3, message, self._active_domain)
        logger.info("FSM decision: %s (top1=%s, active=%s)", result, top3[0][0] if top3 else '?', self._active_domain)
        return result

    @staticmethod
    def match_keyword_domain(
        message: str,
        top3: list[tuple[str, float]],
    ) -> str | None:
        """Retorna el dominio del top3 cuyas keywords aparecen en el mensaje.

        Solo considera dominios presentes en top3 (no todo el catálogo).
        Si múltiples dominios matchean, retorna el de mayor resonancia
        (i.e., el primero en el orden de top3).

        Args:
            message: Texto del usuario (case-insensitive).
            top3: Top-3 dominios por resonancia, ordenado desc.

        Returns:
            Nombre del dominio, o None si ningún keyword matchea.
            También retorna None si ``message`` no es string o está vacío.
        """
        if not isinstance(message, str) or not message:
            logger.debug("match_keyword_domain: invalid message type=%s", type(message).__name__)
            return None
        text_lower = message.lower()
        for domain, _score in top3:
            if domain not in VALID_DOMAINS:
                continue
            keywords = DOMAIN_KEYWORDS.get(domain, ())
            matching = [kw for kw in keywords if kw in text_lower]
            if matching:
                logger.debug("Keyword match for domain=%s: %s", domain, matching)
                return domain
        return None

    # ── Helpers de inspección ──────────────────────────────────────────

    @staticmethod
    def get_keywords_for_domain(domain: str) -> tuple[str, ...]:
        """Retorna las keywords configuradas para un dominio.

        Útil para tests y para depuración — permite ver qué keywords
        activan un dominio sin tener que importar ``DOMAIN_KEYWORDS``
        directamente.

        Args:
            domain: Nombre del dominio (ej: ``'operaciones'``).

        Returns:
            Tupla de keywords. Vacía si el dominio no está en
            ``DOMAIN_KEYWORDS``.
        """
        keywords = DOMAIN_KEYWORDS.get(domain, ())
        logger.debug("get_keywords_for_domain: domain=%s, count=%d", domain, len(keywords))
        return keywords

    @staticmethod
    def is_valid_domain(domain: str) -> bool:
        """Verifica si un dominio es canónico (está en ``VALID_DOMAINS``)."""
        result = domain in VALID_DOMAINS
        logger.debug("is_valid_domain: domain=%s -> %s", domain, result)
        return result

    # ── Representación ─────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<KeywordRouter active_domain={self._active_domain!r}>"
