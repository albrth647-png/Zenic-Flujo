"""
DDE v3 — Guardrails: Deteccion de PII
======================================

Detecta y protege datos sensibles (PII/PHI) en workflows:
emails, telefonos, documentos, API keys, datos bancarios.
"""

from __future__ import annotations

import re
from typing import ClassVar

from src.nlu.guardrails.result import GuardrailResult, RiskLevel


class PIIGuardrails:
    """Detecta y protege datos sensibles (PII/PHI) en workflows.

    Detecta:
    - Correos electronicos
    - Telefonos
    - Numeros de documento (DNI, CUIT, RUT, SSN)
    - Direcciones IP
    - API keys y tokens
    - Datos bancarios (tarjetas de credito)
    """

    PII_PATTERNS: ClassVar[dict[str, re.Pattern]] = {
        "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
        "phone": re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}"),
        "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "ssn_like": re.compile(r"\b\d{3}[-]\d{2}[-]\d{4}\b"),
        "cuit_argentina": re.compile(r"\b(?:20|23|24|27|30|33|34)\d{8}\d{1}\b"),
        "rut_chile": re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}[-][\dkK]\b"),
        "dni_es": re.compile(r"\b\d{8}[A-Z]\b"),
        "api_key_like": re.compile(r"(?:api[_-]?key|apikey|secret[_-]?key|token)\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE),
        "bearer_token": re.compile(r"bearer\s+[a-zA-Z0-9._\-]+", re.IGNORECASE),
    }

    # Campos de workflow que tipicamente contienen PII
    PII_SENSITIVE_PARAMS: ClassVar[set[str]] = {
        "email", "to", "cc", "bcc", "phone", "telefono", "celular",
        "name", "nombre", "last_name", "apellido", "full_name",
        "address", "direccion", "domicilio",
        "dni", "cuit", "rut", "ssn", "tax_id",
        "password", "pass", "secret", "api_key", "token",
        "credit_card", "card_number", "cvv",
        "ip", "ip_address",
    }

    SENIORITY_THRESHOLDS: ClassVar[dict[str, int]] = {
        "email": 5,      # 5+ emails → medium risk
        "phone": 3,       # 3+ phones → medium risk
        "credit_card": 1, # 1 credit card → critical
        "ssn_like": 1,    # 1 SSN → critical
        "cuit_argentina": 5,  # 5+ CUIT → medium
    }

    def __init__(self, lang: str = "es"):
        self.lang = lang

    def check_workflow_for_pii(self, workflow: dict) -> GuardrailResult:
        """Escanea un workflow completo en busca de PII.

        Args:
            workflow: Definicion del workflow

        Returns:
            GuardrailResult con deteccion de PII
        """
        if not workflow:
            return GuardrailResult.allow(self._msg("Workflow vacio", "Empty workflow"))

        wf_str = str(workflow).lower()

        findings: dict[str, list[str]] = {}
        total_findings = 0

        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = pattern.findall(wf_str)
            if matches:
                clean_matches = self._filter_false_positives(pii_type, matches)
                if clean_matches:
                    findings[pii_type] = clean_matches[:5]  # Top 5
                    total_findings += len(clean_matches)

        if not findings:
            return GuardrailResult.allow(
                self._msg("Sin datos sensibles detectados", "No sensitive data detected"),
            )

        risk = self._assess_pii_risk(findings, total_findings)

        if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return GuardrailResult.block(
                self._msg(
                    f"Datos sensibles detectados ({total_findings} hallazgos): {', '.join(findings.keys())}",
                    f"Sensitive data detected ({total_findings} findings): {', '.join(findings.keys())}",
                ),
                risk,
                {"reason": "pii_detected", "findings": findings, "total": total_findings},
            )

        return GuardrailResult.warn(
            self._msg(
                f"Posibles datos personales detectados ({total_findings} hallazgos). Verificar antes de ejecutar.",
                f"Possible personal data detected ({total_findings} findings). Verify before execution.",
            ),
            risk,
            {"reason": "pii_detected", "findings": findings, "total": total_findings},
        )

    def check_params_for_pii(self, params: dict) -> GuardrailResult:
        """Escanea parametros especificos en busca de PII.

        Util para validar slots antes de compilar el workflow.
        """
        if not params:
            return GuardrailResult.allow()

        sensitive_found: list[dict[str, str]] = []
        for key, value in params.items():
            if key in self.PII_SENSITIVE_PARAMS and isinstance(value, str) and len(value) > 2:
                sensitive_found.append({"param": key, "value": value[:20]})

        if sensitive_found:
            return GuardrailResult.warn(
                self._msg(
                    f"Parametros con datos sensibles: {', '.join(p['param'] for p in sensitive_found)}",
                    f"Parameters with sensitive data: {', '.join(p['param'] for p in sensitive_found)}",
                ),
                RiskLevel.LOW,
                {"reason": "pii_in_params", "params": sensitive_found},
            )

        return GuardrailResult.allow()

    def check_text_for_pii(self, text: str) -> GuardrailResult:
        """Escanea un texto libre (prompt del usuario) en busca de PII.

        Fix B-07: el ``GuardrailManager.check_prompt`` necesita detectar PII
        en el prompt que el usuario envia al LLM. Antes de este metodo, la
        unica opcion era ``check_workflow_for_pii`` (que recibe un dict de
        workflow) o ``check_params_for_pii`` (que solo mira claves sensibles).
        Ninguno de los dos servia para escanear un prompt libre.

        Args:
            text: Texto del prompt del usuario (ej: "mi email es juan@test.com")

        Returns:
            GuardrailResult con la decision:
            - ``block`` si detecta PII de riesgo HIGH o CRITICAL (tarjetas,
              API keys, tokens bearer, documentos).
            - ``warn`` si detecta PII de riesgo LOW o MEDIUM (emails, telefonos
              puntuales) para que el caller decida si enmascarar o rechazar.
            - ``allow`` si no detecta PII.
        """
        if not text:
            return GuardrailResult.allow(
                self._msg("Texto vacio", "Empty text"),
            )

        findings: dict[str, list[str]] = {}
        total_findings = 0

        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                clean_matches = self._filter_false_positives(pii_type, matches)
                if clean_matches:
                    findings[pii_type] = clean_matches[:5]
                    total_findings += len(clean_matches)

        if not findings:
            return GuardrailResult.allow(
                self._msg("Sin datos sensibles detectados en el prompt", "No sensitive data detected in prompt"),
            )

        risk = self._assess_pii_risk(findings, total_findings)

        if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return GuardrailResult.block(
                self._msg(
                    f"PII detectada en el prompt ({total_findings} hallazgos): {', '.join(findings.keys())}",
                    f"PII detected in prompt ({total_findings} findings): {', '.join(findings.keys())}",
                ),
                risk,
                {"reason": "pii_detected", "findings": findings, "total": total_findings},
            )

        return GuardrailResult.warn(
            self._msg(
                f"Posible PII en el prompt ({total_findings} hallazgos). Verificar antes de enviar al LLM.",
                f"Possible PII in prompt ({total_findings} findings). Verify before sending to LLM.",
            ),
            risk,
            {"reason": "pii_detected", "findings": findings, "total": total_findings},
        )

    def _filter_false_positives(self, pii_type: str, matches: list[str]) -> list[str]:
        """Filtra falsos positivos conocidos por tipo de PII."""
        if pii_type == "ip_address":
            return [m for m in matches if not any(
                sub in m for sub in ["0.0.0.0", "127.0.0.1", "255.255.255.255", "1.1.1.1", "8.8.8.8"]
            )]
        if pii_type == "email":
            return [m for m in matches if not any(
                sub in m.lower() for sub in ["example.com", "test.com", "domain.com", "@corp.com"]
            )]
        if pii_type == "credit_card":
            return [m for m in matches if not any(
                sub in m.replace("-", "").replace(" ", "") for sub in ["4111111111111111", "4242424242424242"]
            )]
        return matches

    def _assess_pii_risk(self, findings: dict[str, list[str]], total: int) -> RiskLevel:
        """Determina el nivel de riesgo basado en hallazgos de PII."""
        for critical_type in ("credit_card", "ssn_like"):
            if critical_type in findings:
                return RiskLevel.CRITICAL

        for high_type in ("cuit_argentina", "rut_chile", "api_key_like", "bearer_token"):
            if high_type in findings:
                return RiskLevel.HIGH

        for medium_type, threshold in self.SENIORITY_THRESHOLDS.items():
            if medium_type in findings and len(findings[medium_type]) >= threshold:
                return RiskLevel.MEDIUM

        if total <= 3:
            return RiskLevel.LOW

        return RiskLevel.MEDIUM

    def mask_pii(self, text: str) -> str:
        """Enmascara datos PII en un texto (para logging seguro)."""
        for pii_type, pattern in self.PII_PATTERNS.items():
            if pii_type == "email":
                text = pattern.sub(lambda m: m.group()[0] + "***@" + m.group().split("@")[1], text)
            elif pii_type == "credit_card":
                text = pattern.sub("****-****-****-####", text)
            elif pii_type in ("phone", "ip_address"):
                text = pattern.sub("***", text)
            else:
                text = pattern.sub("***", text)
        return text

    def _msg(self, es: str, en: str) -> str:
        return es if self.lang == "es" else en
