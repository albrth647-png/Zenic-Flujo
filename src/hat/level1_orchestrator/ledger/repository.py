"""
HAT-ORBITAL Ledger Repository (M9 — v2.0)
==========================================

CRUD sobre las 3 tablas del Ledger HAT. Reusa DatabaseManager singleton
de Zenic-Flujo (no crea conexiones propias).

Tablas gestionadas (M9 — reducidas de 7 a 3):
  - hat_facts
  - hat_hypotheses
  - hat_progress     (ampliada — reemplaza hat_dispatch_registry, hat_plan,
                      hat_agent_cards y hat_sessions que se eliminaron)

Implementado en F0-D2; reducido en M9 siguiendo IMPLEMENTATION_PLAN.md §M9.
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict

from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging

logger = setup_logging(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


# ── TypedDicts (tipado concreto para las 3 tablas HAT) ──────────────


class FactRow(TypedDict):
    """Fila de la tabla hat_facts."""
    id: int
    user_id: str
    session_id: str
    fact_key: str
    # object: JSON decoded → dict/list/str/int/float/bool/None. Fuerza isinstance al consumir.
    fact_value: object
    confidence: float
    orbital_theta: float
    orbital_amplitude: float
    created_at: str
    updated_at: str


class HypothesisRow(TypedDict):
    """Fila de la tabla hat_hypotheses."""
    id: int
    user_id: str
    session_id: str
    hypothesis_key: str
    # object: JSON decoded → dict/list/str/int/float/bool/None.
    hypothesis_value: object
    confidence: float
    orbital_theta: float
    orbital_amplitude: float
    verified: bool
    verified_at: str | None
    promoted_to_fact: bool
    created_at: str


class ProgressRow(TypedDict):
    """Fila de la tabla hat_progress (ampliada).

    Incluye el alias ``result_cache`` que apunta a ``result_summary``
    para compatibilidad con capas anti-dup.
    """
    id: int
    user_id: str
    session_id: str
    dispatch_id: str
    domain: str
    status: str
    specialist: str | None
    worker: str | None
    # object: JSON decoded → dict/list/str/int/float/bool/None.
    result_summary: object
    result_cache: object    # Alias de compatibilidad
    orbital_resonance: float | None
    intent_hash: str | None
    ttl_expires_at: str | None
    subscriber_count: int
    created_at: str
    completed_at: str | None


class LedgerRepository:
    """CRUD sobre las 3 tablas HAT del Ledger (M9).

    Reusa el singleton DatabaseManager de ZF (sqlite3 + WAL + foreign_keys=ON).
    No crea conexiones propias; todos los métodos delegan a db.execute/fetchone/fetchall.
    """

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self._db = db if db is not None else DatabaseManager()
        self.ensure_schema()

    # ── Schema bootstrap ─────────────────────────────────────

    def ensure_schema(self) -> None:
        """Crea las 3 tablas HAT si no existen. Idempotente."""
        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        # executescript no está en DatabaseManager, usar cursor directo
        conn = self._db.get_connection()
        conn.executescript(sql)
        conn.commit()
        logger.debug("LedgerRepository: schema verificado (3 tablas HAT)")

    # ─────────────────────────────────────────────────────────
    # CRUD: hat_facts
    # ─────────────────────────────────────────────────────────

    def upsert_fact(
        self,
        user_id: str,
        session_id: str,
        fact_key: str,
        fact_value: object,
        confidence: float = 1.0,
        orbital_theta: float = 0.0,
        orbital_amplitude: float = 1.0,
    ) -> int:
        """Inserta o actualiza un fact. Retorna el id del registro."""
        # Fix F0-D2: SIEMPRE json.dumps para que _decode_fact (que siempre json.loads) sea simétrico.
        value_json = json.dumps(fact_value, ensure_ascii=False)
        cur = self._db.execute(
            """
            INSERT INTO hat_facts (user_id, session_id, fact_key, fact_value, confidence, orbital_theta, orbital_amplitude, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, session_id, fact_key) DO UPDATE SET
                fact_value = excluded.fact_value,
                confidence = excluded.confidence,
                orbital_theta = excluded.orbital_theta,
                orbital_amplitude = excluded.orbital_amplitude,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, session_id, fact_key, value_json, confidence, orbital_theta, orbital_amplitude),
        )
        return cur.lastrowid or 0

    def get_facts(self, user_id: str, session_id: str) -> list[FactRow]:
        """Retorna todos los facts de una sesión."""
        rows = self._db.fetchall(
            "SELECT * FROM hat_facts WHERE user_id = ? AND session_id = ? ORDER BY fact_key",
            (user_id, session_id),
        )
        return [self._decode_fact(r) for r in rows]

    def get_fact(self, user_id: str, session_id: str, fact_key: str) -> FactRow | None:
        row = self._db.fetchone(
            "SELECT * FROM hat_facts WHERE user_id = ? AND session_id = ? AND fact_key = ?",
            (user_id, session_id, fact_key),
        )
        return self._decode_fact(row) if row else None

    def delete_fact(self, user_id: str, session_id: str, fact_key: str) -> bool:
        """Elimina un fact. Retorna True si eliminó algo."""
        cur = self._db.execute(
            "DELETE FROM hat_facts WHERE user_id = ? AND session_id = ? AND fact_key = ?",
            (user_id, session_id, fact_key),
        )
        return cur.rowcount > 0

    @staticmethod
    def _decode_fact(row: dict[str, Any]) -> FactRow:
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "session_id": row["session_id"],
            "fact_key": row["fact_key"],
            "fact_value": json.loads(row["fact_value"]) if row["fact_value"] else None,
            "confidence": row["confidence"],
            "orbital_theta": row["orbital_theta"],
            "orbital_amplitude": row["orbital_amplitude"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ─────────────────────────────────────────────────────────
    # CRUD: hat_hypotheses
    # ─────────────────────────────────────────────────────────

    def upsert_hypothesis(
        self,
        user_id: str,
        session_id: str,
        hypothesis_key: str,
        hypothesis_value: object,
        confidence: float = 0.5,
        orbital_theta: float = 0.785,  # π/4
        orbital_amplitude: float = 0.5,
    ) -> int:
        # Fix F0-D2: SIEMPRE json.dumps (simetría con _decode_hypothesis).
        value_json = json.dumps(hypothesis_value, ensure_ascii=False)
        cur = self._db.execute(
            """
            INSERT INTO hat_hypotheses (user_id, session_id, hypothesis_key, hypothesis_value, confidence, orbital_theta, orbital_amplitude)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, session_id, hypothesis_key) DO UPDATE SET
                hypothesis_value = excluded.hypothesis_value,
                confidence = excluded.confidence,
                orbital_theta = excluded.orbital_theta,
                orbital_amplitude = excluded.orbital_amplitude
            """,
            (user_id, session_id, hypothesis_key, value_json, confidence, orbital_theta, orbital_amplitude),
        )
        return cur.lastrowid or 0

    def get_hypotheses(self, user_id: str, session_id: str, only_unverified: bool = False) -> list[HypothesisRow]:
        sql = "SELECT * FROM hat_hypotheses WHERE user_id = ? AND session_id = ?"
        params: list[Any] = [user_id, session_id]
        if only_unverified:
            sql += " AND verified = 0"
        sql += " ORDER BY hypothesis_key"
        rows = self._db.fetchall(sql, tuple(params))
        return [self._decode_hypothesis(r) for r in rows]

    def verify_hypothesis(
        self,
        user_id: str,
        session_id: str,
        hypothesis_key: str,
        promote_to_fact: bool = False,
    ) -> bool:
        """Marca una hipótesis como verificada. Opcionalmente la promueve a fact."""
        cur = self._db.execute(
            """
            UPDATE hat_hypotheses
            SET verified = 1, verified_at = CURRENT_TIMESTAMP, promoted_to_fact = ?
            WHERE user_id = ? AND session_id = ? AND hypothesis_key = ?
            """,
            (1 if promote_to_fact else 0, user_id, session_id, hypothesis_key),
        )
        if cur.rowcount == 0:
            return False
        if promote_to_fact:
            hyp = self.get_hypothesis(user_id, session_id, hypothesis_key)
            if hyp:
                # Promover: copiar a hat_facts con confidence=1.0, theta=0
                self.upsert_fact(
                    user_id, session_id, hypothesis_key,
                    hyp["hypothesis_value"],
                    confidence=1.0,
                    orbital_theta=0.0,
                    orbital_amplitude=1.0,
                )
        return True

    def get_hypothesis(self, user_id: str, session_id: str, hypothesis_key: str) -> HypothesisRow | None:
        row = self._db.fetchone(
            "SELECT * FROM hat_hypotheses WHERE user_id = ? AND session_id = ? AND hypothesis_key = ?",
            (user_id, session_id, hypothesis_key),
        )
        return self._decode_hypothesis(row) if row else None

    @staticmethod
    def _decode_hypothesis(row: dict[str, Any]) -> HypothesisRow:
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "session_id": row["session_id"],
            "hypothesis_key": row["hypothesis_key"],
            "hypothesis_value": json.loads(row["hypothesis_value"]) if row["hypothesis_value"] else None,
            "confidence": row["confidence"],
            "orbital_theta": row["orbital_theta"],
            "orbital_amplitude": row["orbital_amplitude"],
            "verified": bool(row["verified"]),
            "verified_at": row["verified_at"],
            "promoted_to_fact": bool(row["promoted_to_fact"]),
            "created_at": row["created_at"],
        }

    # ─────────────────────────────────────────────────────────
    # CRUD: hat_progress (ampliada — también reemplaza hat_dispatch_registry)
    # ─────────────────────────────────────────────────────────

    def record_progress(
        self,
        user_id: str,
        session_id: str,
        dispatch_id: str,
        domain: str,
        status: str,
        specialist: str | None = None,
        worker: str | None = None,
        result_summary: object = None,
        orbital_resonance: float | None = None,
        intent_hash: str | None = None,
        ttl_expires_at: str | None = None,
    ) -> int:
        """Persiste un dispatch en hat_progress. Idempotente por dispatch_id (UNIQUE).

        M9: ahora acepta intent_hash y ttl_expires_at para reemplazar
        hat_dispatch_registry. Si el dispatch_id ya existe, se hace upsert
        preservando intent_hash/ttl_expires_at ya almacenados.
        """
        summary_json = (
            json.dumps(result_summary, ensure_ascii=False)
            if result_summary is not None
            else None
        )
        completed_at = "CURRENT_TIMESTAMP" if status in ("completed", "failed") else None
        if completed_at:
            cur = self._db.execute(
                """
                INSERT INTO hat_progress (user_id, session_id, dispatch_id, domain, specialist, worker,
                                          status, result_summary, orbital_resonance, intent_hash,
                                          ttl_expires_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(dispatch_id) DO UPDATE SET
                    status = excluded.status,
                    specialist = COALESCE(excluded.specialist, hat_progress.specialist),
                    worker = COALESCE(excluded.worker, hat_progress.worker),
                    result_summary = excluded.result_summary,
                    orbital_resonance = excluded.orbital_resonance,
                    intent_hash = COALESCE(excluded.intent_hash, hat_progress.intent_hash),
                    ttl_expires_at = COALESCE(excluded.ttl_expires_at, hat_progress.ttl_expires_at),
                    completed_at = CURRENT_TIMESTAMP
                """,
                (user_id, session_id, dispatch_id, domain, specialist, worker, status,
                 summary_json, orbital_resonance, intent_hash, ttl_expires_at),
            )
        else:
            cur = self._db.execute(
                """
                INSERT INTO hat_progress (user_id, session_id, dispatch_id, domain, specialist, worker,
                                          status, result_summary, orbital_resonance, intent_hash,
                                          ttl_expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dispatch_id) DO UPDATE SET
                    status = excluded.status,
                    specialist = COALESCE(excluded.specialist, hat_progress.specialist),
                    worker = COALESCE(excluded.worker, hat_progress.worker),
                    result_summary = excluded.result_summary,
                    orbital_resonance = excluded.orbital_resonance,
                    intent_hash = COALESCE(excluded.intent_hash, hat_progress.intent_hash),
                    ttl_expires_at = COALESCE(excluded.ttl_expires_at, hat_progress.ttl_expires_at)
                """,
                (user_id, session_id, dispatch_id, domain, specialist, worker, status,
                 summary_json, orbital_resonance, intent_hash, ttl_expires_at),
            )
        return cur.lastrowid or 0

    def get_progress(self, user_id: str, session_id: str, limit: int = 50) -> list[ProgressRow]:
        rows = self._db.fetchall(
            "SELECT * FROM hat_progress WHERE user_id = ? AND session_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, session_id, limit),
        )
        result = []
        for r in rows:
            d = self._decode_dispatch(dict(r))
            result.append(d)
        return result

    # ─────────────────────────────────────────────────────────
    # Anti-doble-llamada — ahora sobre hat_progress (reemplaza hat_dispatch_registry)
    # ─────────────────────────────────────────────────────────

    def register_dispatch(
        self,
        intent_hash: str,
        user_id: str,
        session_id: str,
        domain: str,
        ttl_seconds: int = 5,
    ) -> tuple[int, bool]:
        """Registra un nuevo dispatch en hat_progress.

        M9: inserta en hat_progress con status='dispatched' y los campos
        intent_hash + ttl_expires_at (antes iba a hat_dispatch_registry).

        Returns:
            (id, was_created) — was_created=False si ya existía (capa 2 idempotency).
        """
        ttl_expires = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat(sep=" ")
        # dispatch_id = intent_hash (1:1 mapping; hat_progress.dispatch_id es UNIQUE)
        try:
            cur = self._db.execute(
                """
                INSERT INTO hat_progress (user_id, session_id, dispatch_id, domain, status,
                                          intent_hash, ttl_expires_at)
                VALUES (?, ?, ?, ?, 'dispatched', ?, ?)
                """,
                (user_id, session_id, intent_hash, domain, intent_hash, ttl_expires),
            )
            return cur.lastrowid or 0, True
        except Exception:
            # INSERT falla si el hash ya existe (UNIQUE constraint en dispatch_id)
            existing = self.get_dispatch(intent_hash)
            return (existing["id"] if existing else 0), False

    def get_dispatch(self, intent_hash: str) -> ProgressRow | None:
        """Consulta hat_progress por intent_hash (reemplaza query a hat_dispatch_registry).

        Mantiene compatibilidad con capas anti-dup que esperan campos
        'status' y 'result_cache' en el dict retornado.
        """
        row = self._db.fetchone(
            "SELECT * FROM hat_progress WHERE intent_hash = ?",
            (intent_hash,),
        )
        if not row:
            return None
        return self._decode_dispatch(dict(row))

    def get_dispatch_by_hash(self, intent_hash: str) -> ProgressRow | None:
        """Alias semántico de get_dispatch() — consulta hat_progress por intent_hash.

        Añadido en M9 para reemplazar conceptualmente al antiguo get_dispatch
        que consultaba hat_dispatch_registry.
        """
        return self.get_dispatch(intent_hash)

    def complete_dispatch(
        self,
        intent_hash: str,
        result: object,
        status: str = "completed",
    ) -> bool:
        """Marca un dispatch como completado/failed en hat_progress.

        M9: actualiza hat_progress SET status=?, result_summary=?, completed_at=NOW
        WHERE intent_hash=? (sin filtro de status previo — el dispatch puede
        estar en cualquier estado activo: dispatched|running).
        """
        # Fix F0-D2: SIEMPRE json.dumps (simetría con get_dispatch que siempre json.loads).
        result_json = json.dumps(result, ensure_ascii=False)
        cur = self._db.execute(
            """
            UPDATE hat_progress
            SET status = ?, result_summary = ?, completed_at = CURRENT_TIMESTAMP
            WHERE intent_hash = ?
            """,
            (status, result_json, intent_hash),
        )
        return cur.rowcount > 0

    def increment_subscriber(self, intent_hash: str) -> int:
        """Incrementa el contador de subscribers en hat_progress (capa 2 idempotency).

        M9: ahora opera sobre hat_progress.subscriber_count (antes era
        hat_dispatch_registry.subscriber_count).
        """
        cur = self._db.execute(
            "UPDATE hat_progress SET subscriber_count = subscriber_count + 1 WHERE intent_hash = ?",
            (intent_hash,),
        )
        if cur.rowcount == 0:
            return 0
        row = self._db.fetchone(
            "SELECT subscriber_count FROM hat_progress WHERE intent_hash = ?",
            (intent_hash,),
        )
        return row["subscriber_count"] if row else 0

    def get_recent_dispatches_by_hash(
        self, intent_hash: str, since_seconds: int = 5,
    ) -> list[ProgressRow]:
        """Capa 3 (TTL Freshness): despachos recientes con el mismo hash.

        M9: reemplaza get_recent_dispatches_by_session. Ahora filtra por
        intent_hash (más específico — no bloquea mensajes diferentes del
        mismo usuario en la ventana TTL).
        """
        cutoff = (datetime.now(UTC) - timedelta(seconds=since_seconds)).isoformat(sep=" ")
        rows = self._db.fetchall(
            """
            SELECT * FROM hat_progress
            WHERE intent_hash = ? AND created_at >= ?
            ORDER BY created_at DESC
            """,
            (intent_hash, cutoff),
        )
        return [self._decode_dispatch(dict(r)) for r in rows]

    @staticmethod
    def _decode_dispatch(row: dict[str, Any]) -> ProgressRow:
        """Normaliza un row de hat_progress para las capas anti-dup.

        Añade alias 'result_cache' (apuntando a result_summary) para que las
        capas anti-dup existentes (exact_match, idempotency, ttl_freshness)
        sigan funcionando sin cambios.
        """
        d = dict(row)
        if d.get("result_summary"):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                d["result_summary"] = json.loads(d["result_summary"])
        # Alias de compatibilidad con hat_dispatch_registry
        d["result_cache"] = d.get("result_summary")
        return d
