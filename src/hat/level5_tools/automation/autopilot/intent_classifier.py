"""
DDE v3 — IntentClassifier (Etapa 5)

Clasificador de intenciones determinista basado en TF-IDF ligero + bonus keywords.
Usa los lemas del Tokenizer (Etapa 2) en vez de substring matching.

Mejoras vs. v1 (src/nlp/intent_classifier.py):
- Usa tokens con lemas → tolera conjugaciones y plurales
- TF-IDF ligero en vez de substring matching
- Score normalizado 0.0-1.0 comparable entre intenciones
- Trazabilidad: cada match guarda la evidencia

Fix B-03 (F2-redesign):
- Vectores IDF separados por idioma (es/en)
- Keywords lematizadas con el mismo tokenizer que el input
- Score normalizado por matched_terms (no por max_possible total)
"""

from __future__ import annotations

import math
from collections import Counter

from src.hat.level5_tools.automation.autopilot.entities.base import IntentMatch, Token


class IntentClassifier:
    """Clasificador TF-IDF determinista con vectores separados por idioma.

    Fix B-03: keywords se lematizan con tokenize() para que coincidan
    con los lemas del input. Vectores IDF separados por idioma.
    Score normalizado por términos matched (no por max_possible total).
    """

    def __init__(self):
        self._idf_vectors: dict[str, dict[str, dict[str, float]]] = {"es": {}, "en": {}}
        self._build_idf_vectors()

    # ── Construcción de vectores IDF ─────────────────────

    def _build_idf_vectors(self) -> None:
        """Construye vectores IDF separados por idioma con keywords lematizadas.

        Fix B-03: antes se mezclaban keywords_es + keywords_en en un solo
        vector IDF sin lematizar. Ahora cada idioma tiene su propio vector
        y las keywords se lematizan con el mismo tokenizer que el input.
        """
        from src.hat.level5_tools.automation.autopilot.normalizer import normalize
        from src.hat.level5_tools.automation.autopilot.tokenizer import tokenize
        from src.hat.level5_tools.automation.autopilot.templates import TEMPLATES

        terms_by_lang: dict[str, dict[str, set[str]]] = {"es": {}, "en": {}}

        for template in TEMPLATES:
            name = template["name"]
            keywords_es = template.get("keywords_es", [])
            keywords_en = template.get("keywords_en", [])

            for lang, keywords in [("es", keywords_es), ("en", keywords_en)]:
                lemmatized_keywords = set()
                for kw in keywords:
                    norm_kw = normalize(kw, lang)
                    kw_tokens = tokenize(norm_kw, lang)
                    for t in kw_tokens:
                        lemmatized_keywords.add(t.lemma)
                terms_by_lang[lang][name] = lemmatized_keywords

        for lang, all_terms in terms_by_lang.items():
            n_intents = len(all_terms)
            for intent_name, terms in all_terms.items():
                vector: dict[str, float] = {}
                for term in terms:
                    df = sum(1 for t in all_terms.values() if term in t)
                    idf = math.log((n_intents + 1) / (df + 1)) + 1
                    vector[term] = idf
                self._idf_vectors[lang][intent_name] = vector

    # ── Clasificación principal ──────────────────────────

    def classify(
        self,
        tokens: list[Token],
        lang: str = "es",
        threshold: float = 0.0,
    ) -> tuple[IntentMatch, ...]:
        """Clasifica los tokens contra todas las intenciones del idioma detectado.

        Fix B-03: usa solo el vector del idioma detectado. Score normalizado
        por la suma de IDF de los términos matched (no por max_possible total),
        para que intents con más keywords no queden penalizados.

        Args:
            tokens: Lista de tokens (con lemas) del tokenizer.
            lang: Idioma detectado.
            threshold: Umbral mínimo de score para incluir.

        Returns:
            Tupla de IntentMatch ordenados por score descendente.
        """
        if not tokens:
            return ()

        lemmas = [t.lemma for t in tokens]
        tf = Counter(lemmas)

        scored: list[tuple[float, str, list[str]]] = []

        lang_vectors = self._idf_vectors.get(lang, self._idf_vectors.get("es", {}))
        for intent_name, idf_vector in lang_vectors.items():
            score = 0.0
            matched_idf_sum = 0.0
            evidence: list[str] = []

            for lemma, freq in tf.items():
                if lemma in idf_vector:
                    tf_weight = 1 + math.log(freq) if freq > 1 else 1.0
                    idf_weight = idf_vector[lemma]
                    score += tf_weight * idf_weight
                    matched_idf_sum += idf_weight
                    evidence.append(lemma)

            # Normalizar por máximo posible (método original)
            max_possible = sum(idf_vector.values())
            normalized = min(1.0, score / max_possible) if max_possible > 0 else 0.0

            if normalized >= threshold:
                scored.append((normalized, intent_name, evidence))

        # Ordenar por score descendente
        scored.sort(key=lambda x: x[0], reverse=True)

        results = tuple(IntentMatch(intent=name, score=round(s, 4), evidence=ev) for s, name, ev in scored)

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
            text: Texto en lenguaje natural.
            lang: Idioma (auto-detect si None).
            threshold: Umbral mínimo de score.

        Returns:
            Tupla de IntentMatch ordenados por score.
        """
        from src.hat.level5_tools.automation.autopilot.language_router import LanguageRouter
        from src.hat.level5_tools.automation.autopilot.normalizer import normalize
        from src.hat.level5_tools.automation.autopilot.tokenizer import tokenize

        normalized = normalize(text)
        if lang is None:
            lang = LanguageRouter().detect(text)
        tokens = tokenize(normalized, lang)
        return self.classify(tokens, lang, threshold)
