"""
DDE v3 — Disambiguator (Etapa 7)

Desempata intenciones cuando dos o más tienen scores cercanos (Δ < 0.1).
Decide si preguntar al usuario o elegir la mejor.

Determinista: mismo Δscore → misma decisión.
"""

from __future__ import annotations

from src.nlu.entities.base import IntentMatch

# Umbral: si la diferencia entre el mejor y segundo es menor a esto, hay ambigüedad
# Ajustado a 0.05 (era 0.1) — el TF-IDF del IntentClassifier normaliza por el total
# de keywords del template (típicamente 7-10), así que un solo match da ~10-15%.
# Con 0.1 de threshold, casi todo queda como ambiguo. 0.05 es más realista.
AMBIGUITY_THRESHOLD = 0.05

# Umbral mínimo de score para aceptar una intención (era 0.2).
# El TF-IDF normalizado rara vez supera 0.15 con 1-2 matches de keywords.
# Bajar a 0.05 permite detectar intenciones con evidencia parcial.
MIN_ACCEPTANCE_THRESHOLD = 0.05

# Umbral para aceptar cuando hay múltiples candidatos cercanos (era 0.5).
# Prácticamente inalcanzable con la normalización actual. 0.15 es realista.
MULTI_CANDIDATE_THRESHOLD = 0.15


class Disambiguator:
    """Resuelve ambigüedad entre intenciones."""

    def resolve(
        self,
        intents: tuple[IntentMatch, ...],
    ) -> tuple[IntentMatch | None, bool, tuple[str, ...]]:
        """Resuelve la mejor intención.

        Args:
            intents: Intenciones ordenadas por score descendente

        Returns:
            (best_intent, is_ambiguous, candidates):
            - best_intent: La intención ganadora (o None si no hay)
            - is_ambiguous: True si hay que preguntar al usuario
            - candidates: Tupla de nombres de intenciones candidatas
        """
        if not intents:
            return None, False, ()

        best = intents[0]
        candidates = [best]

        for intent in intents[1:]:
            delta = best.score - intent.score
            if delta < AMBIGUITY_THRESHOLD:
                candidates.append(intent)
            else:
                break

        if len(candidates) > 1 and best.score < MULTI_CANDIDATE_THRESHOLD:
            # Scores bajos + múltiples candidatos → preguntar
            return best, True, tuple(c.intent for c in candidates)

        if best.score < MIN_ACCEPTANCE_THRESHOLD:
            # Score muy bajo → preguntar
            return best, True, (best.intent,)

        return best, False, (best.intent,)
