"""
DDE v3 — Guardrails: Filtro de Contenido
==========================================

Filtra contenido peligroso en prompts de usuario y respuestas de IA:
prompt injection, comandos peligrosos, SQL injection, XSS,
contenido prohibido y token overflow.
"""

from __future__ import annotations

import re
from typing import ClassVar

from src.nlu.guardrails.result import GuardrailResult, RiskLevel


class ContentGuardrails:
    """Filtra contenido peligroso en prompts de usuario y respuestas de IA.

    Detecta:
    - Prompt injection (intentos de override del system prompt)
    - Comandos de sistema peligrosos (rm -rf, drop table, etc.)
    - SQL injection en parametros
    - Cross-site scripting (XSS)
    - Contenido prohibido (instrucciones ilegales, violencia)
    - Token overflow (prompts excesivamente largos)
    """

    # Patrones de prompt injection (ES/EN)
    PROMPT_INJECTION_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"ignora\s+las?\s+instruccion(?:es)?\s+anteriores", re.IGNORECASE),
        re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?", re.IGNORECASE),
        re.compile(r"olvid(?:a|e)\s+tod(?:o|as?)\s+lo\s+(?:que\s+)?te\s+(?:dije|dijeron|he dicho)", re.IGNORECASE),
        re.compile(r"forget\s+(?:all\s+)?(?:your\s+)?(?:previous\s+)?instructions?", re.IGNORECASE),
        re.compile(r"eres?\s+un?\s+(?:asistente|sistema|ai)\s+(?:libre|sin\s+restriccion(?:es)?)", re.IGNORECASE),
        re.compile(r"you\s+are\s+(?:a\s+)?(?:free|unrestricted|unbounded)\s+(?:assistant|ai|system)", re.IGNORECASE),
        re.compile(r"act\s+(?:as\s+)?(?:if|like)\s+(?:you\s+are|a)\s+(?:free|unrestricted|dan)", re.IGNORECASE),
        re.compile(r"eres\s+(?:un?\s+)?(?:dan|free|unrestricted)", re.IGNORECASE),
        re.compile(r"no\s+(?:hay|tienes?)\s+(?:reglas?|limites?|restriccion(?:es)?)", re.IGNORECASE),
        re.compile(r"(?:there\s+are|you\s+have)\s+no\s+(?:rules?|limits?|restrictions?)", re.IGNORECASE),
        re.compile(r"bypass|jailbreak|jail.?break", re.IGNORECASE),
        re.compile(r"a partir de ahora|from now on\s+you\s+(?:are|will)", re.IGNORECASE),
        re.compile(r"system\s*(?:prompt|instruction|message)s?\s*[:=]", re.IGNORECASE),
    ]

    # Patrones de comandos peligrosos
    DANGEROUS_COMMANDS: ClassVar[list[re.Pattern]] = [
        re.compile(r"\brm\s+(?:-rf|\-r\s+\-f)\s+[/~]", re.IGNORECASE),
        re.compile(r"\b(drop|truncate)\s+(table|database|schema)", re.IGNORECASE),
        re.compile(r"\bshutdown\s+(?:now|-h|-r)", re.IGNORECASE),
        re.compile(r"\bmkfs\.", re.IGNORECASE),
        re.compile(r"\bdd\s+if=", re.IGNORECASE),
        re.compile(r"\b(?:wget|curl)\s+(?:-O\s+)?https?://.*\|\s*(?:bash|sh|python)", re.IGNORECASE),
        re.compile(r"\bchmod\s+777\s+/", re.IGNORECASE),
    ]

    # Patrones XSS
    XSS_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
        re.compile(r"javascript\s*:", re.IGNORECASE),
        re.compile(r"on\w+\s*=\s*['\"][^'\"]*['\"]", re.IGNORECASE),
        re.compile(r"<iframe\b", re.IGNORECASE),
        re.compile(r"document\.(?:cookie|write|location)", re.IGNORECASE),
    ]

    # Palabras clave de contenido prohibido
    PROHIBITED_CONTENT: ClassVar[list[re.Pattern]] = [
        re.compile(r"(?:instruccion(?:es)?|c[óo]digo)\s+(?:para\s+)?(?:crear|hacer|fabricar)\s+(?:armas?|explosivos?|drogas?|venenos?)", re.IGNORECASE),
        re.compile(r"(?:how\s+to\s+)?(?:make|create|build|synthesize)\s+(?:weapons?|explosives?|drugs?|poisons?|malware)", re.IGNORECASE),
        re.compile(r"(?:ataque|hack(?:ing|ear)?)\s+(?:inform[áa]tico|de\s+seguridad|bancari)", re.IGNORECASE),
        re.compile(r"(?:hack|crack|phish)\s+(?:bank|account|system|password)", re.IGNORECASE),
    ]

    MAX_PROMPT_LENGTH: ClassVar[int] = 10000
    MAX_PROMPT_TOKENS: ClassVar[int] = 4000  # ~3000 palabras

    def __init__(self, lang: str = "es"):
        self.lang = lang

    def check_prompt(self, text: str) -> GuardrailResult:
        """Evalua el prompt del usuario contra todas las reglas de contenido.

        Args:
            text: Texto del prompt del usuario

        Returns:
            GuardrailResult con la decision
        """
        if not text or not text.strip():
            return GuardrailResult.block(
                self._msg("El prompt esta vacio", "Empty prompt"),
                RiskLevel.MEDIUM,
                {"reason": "empty_prompt"},
            )

        # 1. Verificar longitud
        if len(text) > self.MAX_PROMPT_LENGTH:
            return GuardrailResult.block(
                self._msg(
                    f"Prompt demasiado largo ({len(text)} caracteres, maximo {self.MAX_PROMPT_LENGTH})",
                    f"Prompt too long ({len(text)} chars, max {self.MAX_PROMPT_LENGTH})",
                ),
                RiskLevel.MEDIUM,
                {"reason": "prompt_too_long", "length": len(text), "max": self.MAX_PROMPT_LENGTH},
            )

        # 2. Token overflow aproximado
        approx_tokens = len(text.split())
        if approx_tokens > self.MAX_PROMPT_TOKENS:
            return GuardrailResult.warn(
                self._msg(
                    f"Prompt extenso (~{approx_tokens} tokens). Puede exceder limites del modelo.",
                    f"Long prompt (~{approx_tokens} tokens). May exceed model limits.",
                ),
                RiskLevel.LOW,
                {"reason": "large_prompt", "approx_tokens": approx_tokens},
            )

        # 3. Prompt injection
        for pattern in self.PROMPT_INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                return GuardrailResult.block(
                    self._msg(
                        f"Posible intento de prompt injection detectado: '{match.group()}'",
                        f"Possible prompt injection detected: '{match.group()}'",
                    ),
                    RiskLevel.CRITICAL,
                    {"reason": "prompt_injection", "match": match.group(), "pattern": pattern.pattern},
                )

        # 4. Comandos peligrosos
        for pattern in self.DANGEROUS_COMMANDS:
            match = pattern.search(text)
            if match:
                return GuardrailResult.block(
                    self._msg(
                        f"Comando peligroso detectado: '{match.group()}'",
                        f"Dangerous command detected: '{match.group()}'",
                    ),
                    RiskLevel.CRITICAL,
                    {"reason": "dangerous_command", "match": match.group()},
                )

        # 5. XSS
        for pattern in self.XSS_PATTERNS:
            match = pattern.search(text)
            if match:
                return GuardrailResult.block(
                    self._msg(
                        f"Posible XSS detectado: '{match.group()[:50]}'",
                        f"Possible XSS detected: '{match.group()[:50]}'",
                    ),
                    RiskLevel.HIGH,
                    {"reason": "xss", "match": match.group()[:50]},
                )

        # 6. Contenido prohibido
        for pattern in self.PROHIBITED_CONTENT:
            match = pattern.search(text)
            if match:
                return GuardrailResult.block(
                    self._msg(
                        "Contenido no permitido detectado",
                        "Prohibited content detected",
                    ),
                    RiskLevel.CRITICAL,
                    {"reason": "prohibited_content", "match": match.group()},
                )

        return GuardrailResult.allow(
            self._msg("Prompt verificado — sin contenido peligroso", "Prompt verified — no harmful content detected"),
        )

    def check_ai_response(self, response: str) -> GuardrailResult:
        """Evalua la respuesta generada por IA contra reglas de contenido.

        Args:
            response: Texto generado por el LLM

        Returns:
            GuardrailResult con la decision
        """
        if not response:
            return GuardrailResult.warn(
                self._msg("Respuesta IA vacia", "Empty AI response"),
                RiskLevel.LOW,
                {"reason": "empty_response"},
            )

        injection_indicators = [
            "i'm free now",
            "no restrictions",
            "without rules",
            "sin restricciones",
            "sin reglas",
            "soy libre",
            "puedo hacer cualquier cosa",
            "i can do anything",
        ]
        for indicator in injection_indicators:
            if indicator in response.lower():
                return GuardrailResult.block(
                    self._msg(
                        "La respuesta IA contiene indicadores de jailbreak",
                        "AI response contains jailbreak indicators",
                    ),
                    RiskLevel.CRITICAL,
                    {"reason": "ai_jailbreak_response", "indicator": indicator},
                )

        return GuardrailResult.allow(
            self._msg("Respuesta IA verificada", "AI response verified"),
        )

    def _msg(self, es: str, en: str) -> str:
        return es if self.lang == "es" else en
