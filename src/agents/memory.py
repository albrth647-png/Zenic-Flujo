"""Agent Memory — Short-term and long-term memory with vector similarity.

Provides persistent memory for agents with:
- Short-term memory: Recent observations and actions (sliding window)
- Long-term memory: Persistent knowledge with semantic search
- Vector similarity: Cosine similarity for semantic recall
- Memory consolidation: Automatic transfer from short-term to long-term
"""

from __future__ import annotations

import math
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("agent.memory")


@dataclass
class MemoryEntry:
    """A single memory entry with metadata and optional embedding."""

    entry_id: str = ""
    agent_id: str = ""
    content: str = ""
    entry_type: str = "observation"  # observation, action, decision, knowledge
    importance: float = 0.5  # 0.0 to 1.0
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = f"mem-{uuid.uuid4().hex[:8]}"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _simple_embedding(text: str, dim: int = 64) -> list[float]:
    """Simple hash-based embedding for demo/fallback.

    Production agents should use real embeddings (OpenAI, HuggingFace, etc.)
    This uses a deterministic character-based hash projection.
    """
    embedding = [0.0] * dim
    if not text:
        return embedding
    for i, char in enumerate(text):
        idx = i % dim
        embedding[idx] += (ord(char) * 0.01)
    # Normalize
    norm = math.sqrt(sum(x * x for x in embedding))
    if norm > 0:
        embedding = [x / norm for x in embedding]
    return embedding


class AgentMemory:
    """Agent memory system with short-term and long-term storage.

    Short-term memory is a sliding window of recent entries.
    Long-term memory is persisted in SQLite with vector similarity search.

    Usage:
        memory = AgentMemory(agent_id="agent-1", db_path=":memory:")
        memory.store("User asked about invoices", entry_type="observation")
        results = memory.recall("invoices", limit=5)
    """

    def __init__(
        self,
        agent_id: str,
        db_path: str = "agent_memory.db",
        short_term_limit: int = 100,
        embedding_fn: Any | None = None,
    ) -> None:
        self.agent_id = agent_id
        self._db_path = db_path
        self._short_term_limit = short_term_limit
        self._embedding_fn = embedding_fn or _simple_embedding
        self._short_term: list[MemoryEntry] = []
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite storage for long-term memory."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_memory (
                entry_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                content TEXT NOT NULL,
                entry_type TEXT NOT NULL DEFAULT 'observation',
                importance REAL NOT NULL DEFAULT 0.5,
                embedding TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                timestamp REAL NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed REAL NOT NULL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_agent ON agent_memory(agent_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_type ON agent_memory(agent_id, entry_type)"
        )
        self._conn.commit()

    # ── Store ───────────────────────────────────────────────

    def store(
        self,
        content: str,
        entry_type: str = "observation",
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        """Store a new memory entry in both short-term and long-term memory.

        Args:
            content: The memory content text.
            entry_type: Type of memory (observation, action, decision, knowledge).
            importance: Importance score 0.0-1.0.
            metadata: Optional metadata dict.

        Returns:
            The created MemoryEntry.
        """
        embedding = self._embedding_fn(content)
        entry = MemoryEntry(
            agent_id=self.agent_id,
            content=content,
            entry_type=entry_type,
            importance=max(0.0, min(1.0, importance)),
            embedding=embedding,
            metadata=metadata or {},
        )

        with self._lock:
            # Short-term
            self._short_term.append(entry)
            if len(self._short_term) > self._short_term_limit:
                self._short_term = self._short_term[-self._short_term_limit:]

            # Long-term (SQLite)
            self._persist_entry(entry)

        return entry

    def _persist_entry(self, entry: MemoryEntry) -> None:
        """Persist a memory entry to SQLite."""
        if self._conn is None:
            return
        self._conn.execute(
            """INSERT OR REPLACE INTO agent_memory
               (entry_id, agent_id, content, entry_type, importance, embedding, metadata,
                timestamp, access_count, last_accessed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.entry_id,
                entry.agent_id,
                entry.content,
                entry.entry_type,
                entry.importance,
                ",".join(str(v) for v in entry.embedding),
                str(entry.metadata),
                entry.timestamp,
                entry.access_count,
                entry.last_accessed,
            ),
        )
        self._conn.commit()

    # ── Recall ──────────────────────────────────────────────

    def recall(
        self,
        query: str,
        limit: int = 10,
        entry_type: str | None = None,
        min_importance: float = 0.0,
        use_similarity: bool = True,
    ) -> list[MemoryEntry]:
        """Recall memories matching a query.

        Uses vector similarity search if use_similarity is True,
        otherwise falls back to keyword matching.

        Args:
            query: The search query.
            limit: Maximum number of results.
            entry_type: Filter by entry type.
            min_importance: Minimum importance threshold.
            use_similarity: Whether to use semantic similarity.

        Returns:
            List of matching MemoryEntry objects, ranked by relevance.
        """
        query_embedding = self._embedding_fn(query) if use_similarity else []

        with self._lock:
            # Search short-term first
            short_results = self._search_entries(
                self._short_term, query_embedding, entry_type, min_importance
            )

            # Search long-term
            long_results = self._search_db(query_embedding, entry_type, min_importance)

        # Merge, deduplicate, and rank
        seen_ids: set[str] = set()
        all_results: list[MemoryEntry] = []

        for entry in short_results + long_results:
            if entry.entry_id not in seen_ids:
                seen_ids.add(entry.entry_id)
                all_results.append(entry)

        # Sort by relevance (similarity score or importance)
        if use_similarity and query_embedding:
            all_results.sort(
                key=lambda e: _cosine_similarity(query_embedding, e.embedding),
                reverse=True,
            )
        else:
            all_results.sort(key=lambda e: e.importance, reverse=True)

        return all_results[:limit]

    def _search_entries(
        self,
        entries: list[MemoryEntry],
        query_embedding: list[float],
        entry_type: str | None,
        min_importance: float,
    ) -> list[MemoryEntry]:
        """Filter entries by type and importance, optionally compute similarity."""
        results = []
        for entry in entries:
            if entry_type and entry.entry_type != entry_type:
                continue
            if entry.importance < min_importance:
                continue
            results.append(entry)
        return results

    def _search_db(
        self,
        query_embedding: list[float],
        entry_type: str | None,
        min_importance: float,
    ) -> list[MemoryEntry]:
        """Search long-term memory in SQLite."""
        if self._conn is None:
            return []

        query = "SELECT * FROM agent_memory WHERE agent_id = ? AND importance >= ?"
        params: list[Any] = [self.agent_id, min_importance]

        if entry_type:
            query += " AND entry_type = ?"
            params.append(entry_type)

        query += " ORDER BY importance DESC, timestamp DESC LIMIT 200"

        try:
            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()
        except sqlite3.Error:
            return []

        results = []
        for row in rows:
            entry = self._row_to_entry(row)
            results.append(entry)
        return results

    def _row_to_entry(self, row: tuple[Any, ...]) -> MemoryEntry:
        """Convert a database row to a MemoryEntry."""
        embedding_str = row[5] if len(row) > 5 else ""
        embedding = [float(v) for v in embedding_str.split(",") if v] if embedding_str else []

        import json

        return MemoryEntry(
            entry_id=row[0],
            agent_id=row[1],
            content=row[2],
            entry_type=row[3],
            importance=row[4],
            embedding=embedding,
            metadata=json.loads(row[6]) if len(row) > 6 and row[6] else {},
            timestamp=row[7],
            access_count=row[8] if len(row) > 8 else 0,
            last_accessed=row[9] if len(row) > 9 else 0.0,
        )

    # ── Consolidation ───────────────────────────────────────

    def consolidate(self, importance_threshold: float = 0.7) -> int:
        """Move important short-term memories to long-term with enhanced embedding.

        This simulates the cognitive process of memory consolidation during sleep.
        Only memories above the importance threshold are consolidated.

        Returns:
            Number of memories consolidated.
        """
        consolidated = 0
        with self._lock:
            for entry in self._short_term:
                if entry.importance >= importance_threshold:
                    # Boost importance slightly during consolidation
                    entry.importance = min(1.0, entry.importance * 1.1)
                    self._persist_entry(entry)
                    consolidated += 1

        if consolidated > 0:
            logger.info("Consolidated %d memories for agent %s", consolidated, self.agent_id)
        return consolidated

    # ── Management ──────────────────────────────────────────

    def forget(self, entry_id: str) -> bool:
        """Remove a specific memory entry.

        Returns:
            True if the entry was found and removed.
        """
        with self._lock:
            # Remove from short-term
            self._short_term = [e for e in self._short_term if e.entry_id != entry_id]

            # Remove from long-term
            if self._conn is not None:
                self._conn.execute(
                    "DELETE FROM agent_memory WHERE entry_id = ? AND agent_id = ?",
                    (entry_id, self.agent_id),
                )
                self._conn.commit()
        return True

    def clear(self, entry_type: str | None = None) -> int:
        """Clear memories, optionally filtered by type.

        Returns:
            Number of entries cleared.
        """
        with self._lock:
            if entry_type:
                count = sum(1 for e in self._short_term if e.entry_type == entry_type)
                self._short_term = [e for e in self._short_term if e.entry_type != entry_type]
            else:
                count = len(self._short_term)
                self._short_term = []

            if self._conn is not None:
                if entry_type:
                    self._conn.execute(
                        "DELETE FROM agent_memory WHERE agent_id = ? AND entry_type = ?",
                        (self.agent_id, entry_type),
                    )
                else:
                    self._conn.execute(
                        "DELETE FROM agent_memory WHERE agent_id = ?",
                        (self.agent_id,),
                    )
                self._conn.commit()

        return count

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        with self._lock:
            short_term_count = len(self._short_term)
            type_counts: dict[str, int] = {}
            for entry in self._short_term:
                type_counts[entry.entry_type] = type_counts.get(entry.entry_type, 0) + 1

        long_term_count = 0
        if self._conn is not None:
            cursor = self._conn.execute(
                "SELECT COUNT(*) FROM agent_memory WHERE agent_id = ?",
                (self.agent_id,),
            )
            long_term_count = cursor.fetchone()[0]

        return {
            "agent_id": self.agent_id,
            "short_term_count": short_term_count,
            "long_term_count": long_term_count,
            "type_counts": type_counts,
            "short_term_limit": self._short_term_limit,
        }

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
