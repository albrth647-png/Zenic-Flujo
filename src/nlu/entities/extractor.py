"""
DDE v3 — EntityExtractor (Etapa 4)

Extrae entidades del texto usando patrones regex deterministas.
Retorna tuple[Entity, ...] con tipo y valor normalizado.

Cada extractor es independiente y testeable por separado.
"""
from __future__ import annotations
import re
from src.nlu.entities.base import Entity


class EntityExtractor:
    """Extractor de entidades determinista por regex.

    Cada extractor interno retorna listas de Entity que se
    combinan al final. Los solapamientos se resuelven por
    prioridad fija + score.
    """

    # ── Patrones por tipo ─────────────────────────────────
    EMAIL_RE = re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b', re.IGNORECASE)
    PHONE_RE = re.compile(r'\b[\+]?\d[\d\s\-\(\)]{6,14}\b')
    NUMBER_RE = re.compile(r'\b\d+\b')
    DATE_RE = re.compile(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b')
    TIME_RE = re.compile(r'\b(\d{1,2}:\d{2}(?:\s?[ap]m)?)\b', re.IGNORECASE)
    URL_RE = re.compile(r'\bhttps?://[^\s]+\b', re.IGNORECASE)
    CURRENCY_RE = re.compile(r'\$\s?\d+[\.,]?\d*\b')

    def extract_all(self, text: str) -> tuple[Entity, ...]:
        """Extrae TODAS las entidades del texto.

        Args:
            text: Texto original (sin normalizar, para spans correctos)

        Returns:
            Tupla de Entity extraídas, ordenadas por posición de aparición
        """
        entities: list[Entity] = []

        # Orden: extractores específicos (alta confianza) ANTES que genéricos (baja confianza)
        # para evitar que números sueltos solapen fechas, horas, monedas o emails
        entities.extend(self._extract_email(text))       # score 1.0
        entities.extend(self._extract_url(text))          # score 1.0
        entities.extend(self._extract_date(text))         # score 0.9
        entities.extend(self._extract_time(text))         # score 0.9
        entities.extend(self._extract_currency(text))     # score 0.9
        entities.extend(self._extract_phone(text))        # score 0.9
        entities.extend(self._extract_number(text))       # score 0.6 (genérico, último)

        # Ordenar por posición de aparición
        entities.sort(key=lambda e: e.span[0])

        # Resolver solapamientos: el de mayor score se queda
        entities = self._resolve_overlaps(entities)

        return tuple(entities)

    def extract_trigger_type(self, text: str) -> tuple[str, dict]:
        """Detecta el tipo de trigger del workflow.

        Args:
            text: Texto en lenguaje natural

        Returns:
            (tipo_trigger, config) donde tipo es 'event'|'schedule'|'webhook'|'file'|'manual'
        """
        text_lower = text.lower()
        if any(w in text_lower for w in ["cuando", "when", "si", "if", "cada vez"]):
            return "event", {}
        if any(w in text_lower for w in ["cada", "every", "diario", "daily", "semanal", "weekly", "cron"]):
            return "schedule", {"cron": "0 9 * * *"}
        if any(w in text_lower for w in ["webhook", "http", "api"]):
            return "webhook", {}
        if any(w in text_lower for w in ["archivo", "file", "carpeta", "folder"]):
            return "file", {}
        return "manual", {}

    # ── Extractores individuales ──────────────────────────

    def _extract_email(self, text: str) -> list[Entity]:
        entities = []
        for match in self.EMAIL_RE.finditer(text):
            entities.append(Entity(
                type="email",
                value=match.group(),
                raw=match.group(),
                span=(match.start(), match.end()),
                score=1.0,
            ))
        return entities

    def _extract_phone(self, text: str) -> list[Entity]:
        entities = []
        for match in self.PHONE_RE.finditer(text):
            raw = match.group().strip()
            # Filtro: ignorar números muy cortos o que parezcan años
            digits = re.sub(r'\D', '', raw)
            if len(digits) < 7 or len(digits) > 15:
                continue
            entities.append(Entity(
                type="phone",
                value=digits,
                raw=raw,
                span=(match.start(), match.end()),
                score=0.9,
            ))
        return entities

    def _extract_number(self, text: str) -> list[Entity]:
        entities = []
        for match in self.NUMBER_RE.finditer(text):
            raw = match.group()
            # Ignorar si ya fue cubierto por otro extractor (ej: fecha, hora)
            entities.append(Entity(
                type="number",
                value=int(raw),
                raw=raw,
                span=(match.start(), match.end()),
                score=0.6,
            ))
        return entities

    def _extract_date(self, text: str) -> list[Entity]:
        entities = []
        for match in self.DATE_RE.finditer(text):
            entities.append(Entity(
                type="date",
                value=match.group(),
                raw=match.group(),
                span=(match.start(), match.end()),
                score=0.9,
            ))
        return entities

    def _extract_time(self, text: str) -> list[Entity]:
        entities = []
        for match in self.TIME_RE.finditer(text):
            entities.append(Entity(
                type="time",
                value=match.group(),
                raw=match.group(),
                span=(match.start(), match.end()),
                score=0.9,
            ))
        return entities

    def _extract_url(self, text: str) -> list[Entity]:
        entities = []
        for match in self.URL_RE.finditer(text):
            entities.append(Entity(
                type="url",
                value=match.group(),
                raw=match.group(),
                span=(match.start(), match.end()),
                score=1.0,
            ))
        return entities

    def _extract_currency(self, text: str) -> list[Entity]:
        entities = []
        for match in self.CURRENCY_RE.finditer(text):
            raw = match.group()
            try:
                value = float(re.sub(r'[^\d.]', '', raw))
            except ValueError:
                continue
            entities.append(Entity(
                type="money",
                value=value,
                raw=raw,
                span=(match.start(), match.end()),
                score=0.9,
            ))
        return entities

    PHONE_RE = re.compile(r'\b[\+]?\d[\d\s\-\(\)]{6,14}\b')

    def _resolve_overlaps(self, entities: list[Entity]) -> list[Entity]:
        """Resuelve solapamientos: el de mayor score se queda.

        Ordena por score descendente + posición, para que entidades
        más específicas (con score más alto) sobrevivan al solapamiento.
        """
        if not entities:
            return []

        # Ordenar por score descendente, luego por posición izquierda
        sorted_entities = sorted(entities, key=lambda e: (-e.score, e.span[0]))

        resolved: list[Entity] = []
        occupied: set[tuple[int, int]] = set()

        for ent in sorted_entities:
            span = ent.span
            overlaps = False
            for (start, end) in occupied:
                if not (span[1] <= start or span[0] >= end):
                    overlaps = True
                    break

            if not overlaps:
                resolved.append(ent)
                occupied.add(span)

        # Reordenar por posición de aparición para salida consistente
        resolved.sort(key=lambda e: e.span[0])
        return resolved
