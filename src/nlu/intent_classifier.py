"""
DDE v3 — IntentClassifier (Etapa 5)

Clasificador de intenciones determinista basado en TF-IDF ligero + bonus keywords.
Usa los lemas del Tokenizer (Etapa 2) en vez de substring matching.

Mejoras vs. v1 (src/nlp/intent_classifier.py):
- Usa tokens con lemas → tolera conjugaciones y plurales
- TF-IDF ligero en vez de substring matching
- Score normalizado 0.0–1.0 comparable entre intenciones
- Trazabilidad: cada match guarda la evidencia
"""
from __future__ import annotations
import math
from collections import Counter
from src.nlu.entities.base import Token, IntentMatch


class IntentClassifier:
    """Clasificador TF-IDF determinista.

    Usa TF-IDF vectorial ligero con IDF precalculado.
    Cada intención es un vector de {lemma: idf_weight}.
    """

    def __init__(self):
        self._idf_vectors: dict[str, dict[str, float]] = {}
        self._build_idf_vectors()

    # ── Construcción de vectores IDF ─────────────────────

    def _build_idf_vectors(self) -> None:
        """Construye vectores IDF para cada intención desde TEMPLATES.

        Normaliza las keywords (NFKD) para que coincidan con los lemas
        del tokenizer, que también normaliza por NFKD.
        """
        from src.nlu.templates import TEMPLATES
        from src.nlu.normalizer import normalize

        # Colección de todos los documentos (lemas de keywords)
        all_terms: dict[str, set[str]] = {}

        for template in TEMPLATES:
            name = template["name"]
            keywords_es = template.get("keywords_es", [])
            keywords_en = template.get("keywords_en", [])
            # Normalizar keywords (NFKD) para que matcheen con tokens normalizados
            all_keywords = keywords_es + keywords_en
            normalized_keywords = set()
            for kw in all_keywords:
                norm_kw = normalize(kw, "es")
                normalized_keywords.add(norm_kw)
            all_terms[name] = normalized_keywords

        # Número total de intenciones (para IDF)
        n_intents = len(all_terms)

        for intent_name, terms in all_terms.items():
            vector: dict[str, float] = {}
            for term in terms:
                # IDF: cuántas intenciones contienen este término
                df = sum(1 for t in all_terms.values() if term in t)
                idf = math.log((n_intents + 1) / (df + 1)) + 1
                vector[term] = idf
            self._idf_vectors[intent_name] = vector

    # ── Clasificación principal ──────────────────────────

    def classify(
        self,
        tokens: list[Token],
        lang: str = "es",
        threshold: float = 0.0,
    ) -> tuple[IntentMatch, ...]:
        """Clasifica los tokens contra todas las intenciones.

        Args:
            tokens: Lista de tokens (con lemas) del tokenizer
            lang: Idioma detectado
            threshold: Umbral mínimo de score para incluir

        Returns:
            Tupla de IntentMatch ordenados por score descendente
        """
        if not tokens:
            return ()

        lemmas = [t.lemma for t in tokens]
        tf = Counter(lemmas)

        scored: list[tuple[float, str, list[str]]] = []

        for intent_name, idf_vector in self._idf_vectors.items():
            score = 0.0
            evidence: list[str] = []

            for lemma, freq in tf.items():
                if lemma in idf_vector:
                    tf_weight = 1 + math.log(freq) if freq > 1 else 1.0
                    idf_weight = idf_vector[lemma]
                    score += tf_weight * idf_weight
                    evidence.append(lemma)

            # Normalizar por máximo posible
            max_possible = sum(idf_vector.values())
            if max_possible > 0:
                normalized = min(1.0, score / max_possible)
            else:
                normalized = 0.0

            if normalized >= threshold:
                scored.append((normalized, intent_name, evidence))

        # Ordenar por score descendente
        scored.sort(key=lambda x: x[0], reverse=True)

        results = tuple(
            IntentMatch(intent=name, score=round(s, 4), evidence=ev)
            for s, name, ev in scored
        )

        return results

    # ── Helper: clasificar desde texto sin procesar ──────

    def classify_text(
        self,
        text: str,
        lang: str | None = None,
        threshold: float = 0.0,
    ) -> tuple[IntentMatch, ...]:
        """Clasifica texto sin procesar (usa pipeline interno).

        Args:
            text: Texto en lenguaje natural
            lang: Idioma (auto-detect si None)
            threshold: Umbral mínimo de score

        Returns:
            Tupla de IntentMatch ordenados por score
        """
        from src.nlu.normalizer import normalize
        from src.nlu.tokenizer import tokenize
        from src.nlu.language_router import LanguageRouter

        normalized = normalize(text)
        if lang is None:
            lang = LanguageRouter().detect(text)
        tokens = tokenize(normalized, lang)
        return self.classify(tokens, lang, threshold)
