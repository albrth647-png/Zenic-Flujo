"""HAT-ORBITAL Nivel 1 — Facts Manager (capa de negocio sobre el Ledger).

Separa la lógica de negocio de Facts/Hypotheses de la capa de persistencia
(`LedgerRepository`). El repositorio sabe SQL; este módulo sabe reglas de
negocio: promoción de hipótesis a facts, normalización de confianza, firma
de tipos, validación de invariantes.

Reglas implementadas:
- Un Fact tiene ``confidence`` en [0, 1] y ``orbital_theta`` = 0 (no orbita).
- Una Hypothesis no verificada tiene ``confidence`` en [0, 1) y theta = π/4.
- Al verificar una hypothesis con ``promote_to_fact=True``, la confidence
  se fuerza a 1.0 y ``orbital_theta`` se resetea a 0.0 (pasa a ser Fact).
- ``set_active_domain`` es un atajo para upsert_fact con fact_key
  ``"active_domain"`` y confidence 1.0 — usado por el HATRouter.
- ``active_domain_or_none`` lee ese Fact de forma defensiva (None si falta
  o si el valor no es string).

Implementado en M8 (extrae lógica que vivía inline en repository.py).
"""
from __future__ import annotations

import math
from typing import Any

from src.core.logging import setup_logging
from src.hat.level1_orchestrator.ledger.repository import FactRow, HypothesisRow, LedgerRepository

logger = setup_logging(__name__)

# ── Constantes orbitales ────────────────────────────────────────────────
# Facts: θ=0 (alta confianza, no orbitan). Hypotheses: θ=π/4 (media).
FACT_THETA: float = 0.0
HYPOTHESIS_THETA: float = math.pi / 4.0
FACT_AMPLITUDE: float = 1.0
HYPOTHESIS_AMPLITUDE: float = 0.5

# Confidence bounds.
CONFIDENCE_MIN: float = 0.0
CONFIDENCE_MAX: float = 1.0

# Fact key canónico para el dominio activo de la sesión.
ACTIVE_DOMAIN_FACT_KEY: str = "active_domain"


class FactsManager:
    """Capa de negocio sobre ``LedgerRepository`` para Facts y Hypotheses.

    No toca SQL directamente. Delega CRUD al repositorio y añade reglas:

    - Validación de confidence en [0, 1].
    - Forzado de θ=0 / amplitude=1 al verificar una hypothesis.
    - Atajos para ``active_domain`` (fact_key canónico del HATRouter).

    Attributes:
        _repo: Repositorio subyacente (CRUD sobre SQLite).
    """

    def __init__(self, repo: LedgerRepository | None = None) -> None:
        self._repo = repo if repo is not None else LedgerRepository()
        logger.debug("FactsManager initialized with repo=%s", type(self._repo).__name__)

    # ── Facts ──────────────────────────────────────────────────────────

    def upsert_fact(
        self,
        user_id: str,
        session_id: str,
        fact_key: str,
        # legítimo: valor JSON del fact/hypothesis, dinámico por diseño
        fact_value: Any,
        confidence: float = 1.0,
        orbital_theta: float = FACT_THETA,
        orbital_amplitude: float = FACT_AMPLITUDE,
    ) -> int:
        """Inserta o actualiza un Fact, validando confidence en [0, 1].

        Args:
            user_id: ID del usuario.
            session_id: ID de la sesión.
            fact_key: Clave del Fact (ej: ``"active_domain"``).
            fact_value: Valor JSON-serializable.
            confidence: Confianza en [0, 1] (default 1.0).
            orbital_theta: Fase orbital en radianes (default 0.0 — no orbita).
            orbital_amplitude: Amplitud orbital (default 1.0).

        Returns:
            ID del registro insertado/actualizado.

        Raises:
            ValueError: Si ``confidence`` está fuera de [0, 1].
        """
        confidence = self._validate_confidence(confidence)
        result_id = self._repo.upsert_fact(
            user_id=user_id,
            session_id=session_id,
            fact_key=fact_key,
            fact_value=fact_value,
            confidence=confidence,
            orbital_theta=orbital_theta,
            orbital_amplitude=orbital_amplitude,
        )
        logger.debug("upsert_fact: user=%s, session=%s, key=%s, value=%s, confidence=%.2f -> id=%d",
                      user_id, session_id, fact_key, fact_value, confidence, result_id)
        return result_id

    def get_fact(
        self,
        user_id: str,
        session_id: str,
        fact_key: str,
    ) -> FactRow | None:
        """Retorna un Fact por clave, o None si no existe."""
        return self._repo.get_fact(user_id, session_id, fact_key)

    def get_facts(
        self,
        user_id: str,
        session_id: str,
    ) -> list[FactRow]:
        """Retorna todos los Facts de una sesión, ordenados por clave."""
        return self._repo.get_facts(user_id, session_id)

    def delete_fact(
        self,
        user_id: str,
        session_id: str,
        fact_key: str,
    ) -> bool:
        """Elimina un Fact. Retorna True si eliminó algo."""
        return self._repo.delete_fact(user_id, session_id, fact_key)

    # ── Hypotheses ─────────────────────────────────────────────────────

    def upsert_hypothesis(
        self,
        user_id: str,
        session_id: str,
        hypothesis_key: str,
        # legítimo: valor JSON del fact/hypothesis, dinámico por diseño
        hypothesis_value: Any,
        confidence: float = 0.5,
        orbital_theta: float = HYPOTHESIS_THETA,
        orbital_amplitude: float = HYPOTHESIS_AMPLITUDE,
    ) -> int:
        """Inserta o actualiza una Hypothesis, validando confidence en [0, 1).

        Una hypothesis no verificada debe tener ``confidence`` < 1.0; si se
        pasa 1.0 se clamp a 0.99 (forzar verificación explícita para llegar
        a 1.0).
        """
        confidence = self._validate_confidence(confidence)
        if confidence >= CONFIDENCE_MAX:
            confidence = 0.99
        return self._repo.upsert_hypothesis(
            user_id=user_id,
            session_id=session_id,
            hypothesis_key=hypothesis_key,
            hypothesis_value=hypothesis_value,
            confidence=confidence,
            orbital_theta=orbital_theta,
            orbital_amplitude=orbital_amplitude,
        )

    def get_hypothesis(
        self,
        user_id: str,
        session_id: str,
        hypothesis_key: str,
    ) -> HypothesisRow | None:
        """Retorna una Hypothesis por clave, o None si no existe."""
        return self._repo.get_hypothesis(user_id, session_id, hypothesis_key)

    def get_hypotheses(
        self,
        user_id: str,
        session_id: str,
        only_unverified: bool = False,
    ) -> list[HypothesisRow]:
        """Retorna todas las Hypotheses de la sesión."""
        return self._repo.get_hypotheses(
            user_id, session_id, only_unverified=only_unverified,
        )

    def verify_hypothesis(
        self,
        user_id: str,
        session_id: str,
        hypothesis_key: str,
        promote_to_fact: bool = False,
    ) -> bool:
        """Verifica una Hypothesis. Si ``promote_to_fact``, la copia a Facts.

        El repositorio ya implementa la promoción — este método añade
        validación: si la hypothesis no existe, retorna False sin lanzar.
        """
        hyp = self._repo.get_hypothesis(user_id, session_id, hypothesis_key)
        if hyp is None:
            return False
        result = self._repo.verify_hypothesis(
            user_id=user_id,
            session_id=session_id,
            hypothesis_key=hypothesis_key,
            promote_to_fact=promote_to_fact,
        )
        logger.info("verify_hypothesis: user=%s, session=%s, key=%s, promote=%s -> %s",
                     user_id, session_id, hypothesis_key, promote_to_fact, result)
        return result

    # ── Atajos de dominio activo ───────────────────────────────────────

    def set_active_domain(
        self,
        user_id: str,
        session_id: str,
        domain: str,
    ) -> int:
        """Atajo para upsert_fact con fact_key='active_domain', confidence=1.0.

        Usado por HATRouter para persistir el dominio ganador de un dispatch
        y permitir que el siguiente dispatch lo priorice si hay ambigüedad.

        Args:
            user_id: ID del usuario.
            session_id: ID de la sesión.
            domain: Nombre del dominio ganador (ej: ``"operaciones"``).

        Returns:
            ID del registro insertado/actualizado.
        """
        result_id = self.upsert_fact(
            user_id=user_id,
            session_id=session_id,
            fact_key=ACTIVE_DOMAIN_FACT_KEY,
            fact_value=domain,
            confidence=1.0,
            orbital_theta=FACT_THETA,
            orbital_amplitude=FACT_AMPLITUDE,
        )
        logger.info("Active domain set: user=%s, session=%s, domain=%s (id=%d)",
                     user_id, session_id, domain, result_id)
        return result_id

    def get_active_domain(
        self,
        user_id: str,
        session_id: str,
    ) -> str | None:
        """Retorna el dominio activo de la sesión, o None si no hay.

        Defensivo: si el Fact no existe, retorna None. Si existe pero el
        valor no es string, retorna None (no propaga tipos inválidos).
        """
        fact = self.get_fact(user_id, session_id, ACTIVE_DOMAIN_FACT_KEY)
        if fact is None:
            return None
        value = fact.get("fact_value")
        if isinstance(value, str):
            return value
        return None

    def clear_active_domain(
        self,
        user_id: str,
        session_id: str,
    ) -> bool:
        """Elimina el Fact 'active_domain' de la sesión.

        Útil para tests y para resetear el contexto conversacional cuando
        el usuario cambia explícitamente de tema.

        Returns:
            True si el Fact existía y fue eliminado, False si no existía.
        """
        result = self.delete_fact(user_id, session_id, ACTIVE_DOMAIN_FACT_KEY)
        if result:
            logger.info("Active domain cleared for user=%s, session=%s", user_id, session_id)
        else:
            logger.debug("No active domain to clear for user=%s, session=%s", user_id, session_id)
        return result

    # ── Validación interna ─────────────────────────────────────────────

    @staticmethod
    def _validate_confidence(confidence: float) -> float:
        """Clamp confidence al rango [0, 1].

        Raises:
            TypeError: Si ``confidence`` no es numérico (bool excluido).
        """
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            type_name = type(confidence).__name__
            raise TypeError(
                f"confidence debe ser numérico, no {type_name}: {confidence!r}",
            )
        if confidence < CONFIDENCE_MIN:
            return CONFIDENCE_MIN
        if confidence > CONFIDENCE_MAX:
            return CONFIDENCE_MAX
        return float(confidence)

    # ── Representación ─────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<FactsManager repo={type(self._repo).__name__}>"
