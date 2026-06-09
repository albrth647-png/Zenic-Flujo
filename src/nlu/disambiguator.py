"""
DDE v3 — Disambiguator (Etapa 7)

Desempata intenciones cuando dos o más tienen scores cercanos (Δ < 0.1).
Decide si preguntar al usuario o elegir la mejor.

Determinista: mismo Δscore → misma decisión.
"""
from __future__ import annotations
from src.nlu.entities.base import IntentMatch


# Umbral: si la diferencia entre el mejor y segundo es menor a esto, hay ambigüedad
AMBIGUITY_THRESHOLD = 0.1


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

        if len(candidates) > 1 and best.score < 0.5:
            # Scores bajos + múltiples candidatos → preguntar
            return best, True, tuple(c.intent for c in candidates)

        if best.score < 0.2:
            # Score muy bajo → preguntar
            return best, True, (best.intent,)

        return best, False, (best.intent,)
