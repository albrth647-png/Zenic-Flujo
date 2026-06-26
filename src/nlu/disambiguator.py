"""
DDE v3 — Disambiguator (Etapa 7)

Desempata intenciones cuando dos o más tienen scores cercanos (Δ < 0.1).
Decide si preguntar al usuario o elegir la mejor.

Determinista: mismo Δscore → misma decisión.
"""

from __future__ import annotations

from src.nlu.entities.base import IntentMatch

# Umbral: si la diferencia entre el mejor y segundo es menor a esto, hay ambigüedad
# Ajustado a 0.02 — con 30+ templates, los scores son bajos pero el ranking es correcto.
# La diferencia entre el intent correcto y el segundo suele ser >0.02.
AMBIGUITY_THRESHOLD = 0.02

# Umbral mínimo de score para aceptar una intención.
# Con 30+ templates, un solo match da ~3-5%. Bajar a 0.03 acepta esos casos.
MIN_ACCEPTANCE_THRESHOLD = 0.03

# Umbral para aceptar cuando hay múltiples candidatos cercanos.
# Con 30+ templates, múltiples candidatos es común. 0.10 es realista.
MULTI_CANDIDATE_THRESHOLD = 0.10


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
