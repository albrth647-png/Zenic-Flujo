"""
DDE v3 — SynonymLearner (Etapa 13)

Aprende sinónimos del usuario para mejorar la clasificación NLU.
Almacena pares de sinónimos en la tabla nlp_synonyms de SQLite.

Flujo:
  1. Usuario dice: "cuando 'facturar' = crear factura"
  2. SynonymLearner guarda: {word: "facturar", synonym_of: "factura", intent: "factura_automatica"}
  3. En clasificación futura, "facturar" matchea como "factura"

Determinista: mismos sinónimos → misma clasificación.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Synonym:
    """Un sinónimo aprendido."""
    word: str           # la palabra nueva
    synonym_of: str     # la palabra original que ya funciona
    intent: str         # a qué intención pertenece
    confidence: float   # 0.0–1.0, cuántas veces se usó


class SynonymLearner:
    """Aprende y almacena sinónimos para mejorar la clasificación."""

    def __init__(self, db=None):
        """
        Args:
            db: DatabaseManager instance (None = usa in-memory dict)
        """
        self._db = db
        self._memory: dict[str, list[dict]] = {}  # fallback in-memory

    def learn(self, word: str, synonym_of: str, intent: str) -> Synonym:
        """Aprende un nuevo sinónimo.

        Args:
            word: La palabra nueva que el usuario quiere que se entienda
            synonym_of: La palabra original que ya tiene keyword en el template
            intent: La intención a la que pertenece

        Returns:
            Synonym creado
        """
        word = word.strip().lower()
        synonym_of = synonym_of.strip().lower()
        intent = intent.strip().lower()

        if self._db:
            self._db_learn(word, synonym_of, intent)
        else:
            self._memory_learn(word, synonym_of, intent)

        return Synonym(
            word=word,
            synonym_of=synonym_of,
            intent=intent,
            confidence=1.0,
        )

    def get_synonyms(self, intent: str | None = None) -> list[Synonym]:
        """Obtiene sinónimos, opcionalmente filtrados por intención.

        Args:
            intent: Si se provee, solo retorna sinónimos de esa intención

        Returns:
            Lista de sinónimos
        """
        if self._db:
            return self._db_get_synonyms(intent)
        return self._memory_get_synonyms(intent)

    def get_keywords_for_intent(self, intent: str) -> list[str]:
        """Retorna todas las palabras (originales + sinónimos) para una intención.

        Args:
            intent: Nombre de la intención

        Returns:
            Lista de keywords/lemas
        """
        synonyms = self.get_synonyms(intent)
        return [s.word for s in synonyms]

    def remove_synonym(self, word: str, intent: str) -> bool:
        """Elimina un sinónimo.

        Args:
            word: Palabra a eliminar
            intent: Intención de la que se elimina

        Returns:
            True si se eliminó, False si no existía
        """
        word = word.strip().lower()
        intent = intent.strip().lower()

        if self._db:
            return self._db_remove(word, intent)
        return self._memory_remove(word, intent)

    def import_bulk(self, synonyms: list[dict]) -> int:
        """Importa múltiples sinónimos de una vez.

        Args:
            synonyms: Lista de dicts con keys 'word', 'synonym_of', 'intent'

        Returns:
            Cantidad importada
        """
        count = 0
        for s in synonyms:
            if all(k in s for k in ("word", "synonym_of", "intent")):
                self.learn(s["word"], s["synonym_of"], s["intent"])
                count += 1
        return count

    # ── In-memory implementation ────────────────────────────

    def _memory_learn(self, word: str, synonym_of: str, intent: str) -> None:
        if intent not in self._memory:
            self._memory[intent] = []
        # Evitar duplicados
        for existing in self._memory[intent]:
            if existing["word"] == word:
                return
        self._memory[intent].append({
            "word": word,
            "synonym_of": synonym_of,
            "intent": intent,
        })

    def _memory_get_synonyms(self, intent: str | None) -> list[Synonym]:
        results: list[Synonym] = []
        intents_to_scan = [intent] if intent else list(self._memory.keys())
        for intent_key in intents_to_scan:
            for entry in self._memory.get(intent_key, []):
                results.append(Synonym(
                    word=entry["word"],
                    synonym_of=entry["synonym_of"],
                    intent=entry["intent"],
                    confidence=1.0,
                ))
        return results

    def _memory_remove(self, word: str, intent: str) -> bool:
        entries = self._memory.get(intent, [])
        before = len(entries)
        self._memory[intent] = [e for e in entries if e["word"] != word]
        return len(self._memory[intent]) < before

    # ── DB implementation ───────────────────────────────────

    def _db_learn(self, word: str, synonym_of: str, intent: str) -> None:
        """Guarda sinónimo en la DB."""
        self._db.execute(
            """INSERT OR REPLACE INTO nlp_synonyms (word, synonym_of, intent, usage_count)
               VALUES (?, ?, ?, 1)""",
            (word, synonym_of, intent),
        )
        self._db.commit()

    def _db_get_synonyms(self, intent: str | None) -> list[Synonym]:
        """Lee sinónimos de la DB."""
        if intent:
            rows = self._db.fetchall(
                "SELECT word, synonym_of, intent, usage_count FROM nlp_synonyms WHERE intent = ?",
                (intent,),
            )
        else:
            rows = self._db.fetchall(
                "SELECT word, synonym_of, intent, usage_count FROM nlp_synonyms",
            )
        return [
            Synonym(
                word=r["word"],
                synonym_of=r["synonym_of"],
                intent=r["intent"],
                confidence=min(r.get("usage_count", 1) / 10.0, 1.0),
            )
            for r in rows
        ]

    def _db_remove(self, word: str, intent: str) -> bool:
        """Elimina un sinónimo de la DB."""
        cursor = self._db.execute(
            "DELETE FROM nlp_synonyms WHERE word = ? AND intent = ?",
            (word, intent),
        )
        self._db.commit()
        return cursor.rowcount > 0
