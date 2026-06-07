"""
Workflow Determinista — EntityExtractor
Extrae entidades del texto usando patrones regex.
"""
import re
from typing import Any


class EntityExtractor:
    PATTERNS = {
        "email": r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b',
        "phone": r'\b[\+]?[\d\s\-\(\)]{7,15}\b',
        "number": r'\b\d+\b',
        "date": r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b',
        "time": r'\b(\d{1,2}:\d{2}(\s?[ap]m)?)\b',
        "url": r'\bhttps?://[^\s]+\b',
        "currency": r'\$\s?\d+[\.,]?\d*\b',
    }

    def extract(self, text: str) -> dict[str, list[str]]:
        entities = {}
        for entity_type, pattern in self.PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                entities[entity_type] = list(set(m.strip() for m in matches))
        return entities

    def extract_trigger_type(self, text: str) -> tuple[str, dict]:
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
