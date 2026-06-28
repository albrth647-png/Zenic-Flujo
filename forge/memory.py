"""
Persistent Memory v1.0 — Zenic-Flujo Edition
=============================================
Memoria cross-session para agentes de IA.
Guarda reflexiones verbales que sobreviven entre sesiones.
Antes de CRITIQUE, inyecta top-5 reflexiones más relevantes vía Jaccard similarity.

Basado en: Reflexion (NeurIPS 2023), Engram (Gentleman Programming)

Uso:
    from forge import PersistentMemory
    mem = PersistentMemory("/tmp/workdir")
    mem.add_reflection("iter-1", "Resumen", "Reflexion verbal...", score=8.0)
    similares = mem.find_similar("error de import", top_n=5)
"""

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast


class Reflection(TypedDict):
    iteration_id: str
    timestamp: str
    summary: str
    verbal_reflection: str
    score: float
    root_cause: str
    files_affected: list[str]
    key_learnings: list[str]


class MemoryData(TypedDict, total=False):
    version: str
    reflections: list[Reflection]
    created_at: str


class MemoryStats(TypedDict, total=False):
    total_reflections: int
    avg_score: float
    top_root_causes: list[tuple[str, int]]
    top_files: list[tuple[str, int]]


class PersistentMemory:
    """Memoria persistente cross-session con búsqueda por similitud."""

    def __init__(self, workdir: str | Path):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.memory_path = self.workdir / "memory.json"

        if self.memory_path.exists():
            self._load()
        else:
            self.data: MemoryData = {
                "version": "1.0",
                "reflections": [],
                "created_at": datetime.now(tz=UTC).isoformat(),
            }
            self._save()

    # ── Reflections ───────────────────────────────────────────────────

    def add_reflection(
        self,
        iteration_id: str,
        summary: str,
        verbal_reflection: str,
        score: float = 0.0,
        root_cause: str = "",
        files_affected: list[str] | None = None,
        key_learnings: list[str] | None = None,
    ) -> Reflection:
        reflection: Reflection = {
            "iteration_id": iteration_id,
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "summary": summary[:500],
            "verbal_reflection": verbal_reflection,
            "score": score,
            "root_cause": root_cause,
            "files_affected": files_affected or [],
            "key_learnings": (key_learnings or [])[:5],
        }
        self.data["reflections"].append(reflection)
        self._save()
        return reflection

    # ── Jaccard Similarity Search ─────────────────────────────────────

    def _extract_keywords(self, text: str) -> set[str]:
        words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text.lower())
        stopwords = {
            "the", "and", "for", "are", "but", "not", "you", "all",
            "can", "had", "her", "was", "one", "our", "out", "has",
            "have", "been", "some", "than", "that", "this", "very",
            "with", "from", "they", "will", "what", "when", "where",
            "which", "while", "would", "could", "should", "their",
            "there", "these", "about", "after", "also", "into",
            "other", "over", "such", "them", "then", "each",
        }
        return {w for w in words if w not in stopwords and len(w) > 2}

    def _jaccard_similarity(self, keywords1: set[str], keywords2: set[str]) -> float:
        if not keywords1 or not keywords2:
            return 0.0
        intersection = keywords1 & keywords2
        union = keywords1 | keywords2
        return len(intersection) / len(union)

    def find_similar(self, query: str, top_n: int = 5) -> list[Reflection]:
        if not self.data["reflections"]:
            return []

        query_keywords = self._extract_keywords(query)
        scored: list[tuple[float, Reflection]] = []
        for ref in self.data["reflections"]:
            ref_text = (
                ref.get("summary", "")
                + " " + ref.get("verbal_reflection", "")
                + " " + ref.get("root_cause", "")
                + " " + " ".join(ref.get("key_learnings", []))
            )
            ref_keywords = self._extract_keywords(ref_text)
            similarity = self._jaccard_similarity(query_keywords, ref_keywords)
            scored.append((similarity, ref))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ref for score, ref in scored[:top_n] if score > 0.0]

    # ── Stats ─────────────────────────────────────────────────────────

    def stats(self) -> MemoryStats:
        reflections = self.data["reflections"]
        if not reflections:
            return MemoryStats(total_reflections=0)
        return MemoryStats(
            total_reflections=len(reflections),
            avg_score=sum(r["score"] for r in reflections) / len(reflections),
            top_root_causes=self._top_items(
                [r["root_cause"] for r in reflections if r["root_cause"]]
            ),
            top_files=self._top_items([
                f for r in reflections for f in r.get("files_affected", [])
            ]),
        )

    @staticmethod
    def _top_items(items: list[str], n: int = 5) -> list[tuple[str, int]]:
        return Counter(items).most_common(n)

    def get_all_reflections(self) -> list[Reflection]:
        return self.data["reflections"]

    # ── I/O privado ───────────────────────────────────────────────────

    def _load(self) -> None:
        with open(self.memory_path) as f:
            self.data = cast(MemoryData, json.load(f))

    def _save(self) -> None:
        with open(self.memory_path, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def __repr__(self) -> str:
        return f"<PersistentMemory reflections={len(self.data['reflections'])} path={self.memory_path}>"
