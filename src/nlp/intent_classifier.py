"""
Workflow Determinista — IntentClassifier
Clasificador determinista por keywords. NO usa AI. NO usa LLM.
"""
import re
from typing import Any

from src.nlp.bilingual_router import BilingualRouter
from src.nlp.templates import TEMPLATES
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class IntentClassifier:
    def __init__(self):
        self._router = BilingualRouter()

    def classify(self, text: str) -> list[dict]:
        normalized = self._normalize(text)
        lang = self._router.detect(text)
        intents = []

        for template in TEMPLATES:
            keywords = template.get(f"keywords_{lang}", template.get("keywords_es", []))
            score = 0
            for kw in keywords:
                if kw in normalized:
                    score += 2
                elif any(kw in word for word in normalized.split()):
                    score += 1

            if score > 0:
                intents.append({
                    "template_name": template["name"],
                    "confidence": min(1.0, score / (len(keywords) * 1.5)),
                    "description": template.get(f"description_{lang}", ""),
                    "trigger": template["trigger"],
                    "steps": template["steps"],
                    "score": score,
                })

        intents.sort(key=lambda x: x["score"], reverse=True)
        return intents[:5]

    def _normalize(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r'[áàäâ]', 'a', text)
        text = re.sub(r'[éèëê]', 'e', text)
        text = re.sub(r'[íìïî]', 'i', text)
        text = re.sub(r'[óòöô]', 'o', text)
        text = re.sub(r'[úùüû]', 'u', text)
        text = re.sub(r'[ñ]', 'n', text)
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
