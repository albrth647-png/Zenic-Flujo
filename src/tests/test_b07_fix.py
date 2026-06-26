"""
Test de verificacion para bug B-07 — GuardrailManager.check_prompt no valida PII.

Antes del fix: ``GuardrailManager.check_prompt(text)`` solo evaluaba la capa
``content`` (prompt injection, XSS, comandos peligrosos). La capa ``pii`` NO se
invocaba sobre el prompt, de modo que emails, telefonos, tarjetas y API keys
iban en claro al LLM externo.

Despues del fix:
- ``GuardrailManager.check_prompt`` invoca ``PIIGuardrails.check_text_for_pii``.
- ``GuardrailManager.check_prompt_pii(text) -> dict`` expone un contrato simple
  ``{"blocked": bool, "reason": str, "patterns": [...]}`` para callers que no
  quieran lidiar con ``CompositeGuardrailResult``.
- ``PIIGuardrails.check_text_for_pii(text)`` escanea texto libre reutilizando
  los patrones PII existentes y filtrando falsos positivos.
"""

from __future__ import annotations

from src.nlu.guardrails import GuardrailManager
from src.nlu.guardrails.pii import PIIGuardrails
from src.nlu.guardrails.result import GuardrailAction, RiskLevel


class TestBugB07PIIGuardrailsCheckTextForPII:
    """PIIGuardrails debe exponer un metodo para escanear texto libre."""

    def test_check_text_for_pii_blocks_email(self) -> None:
        """Un prompt con email debe resultar en WARN o BLOCK (riesgo LOW/MEDIUM)."""
        pii = PIIGuardrails(lang="es")
        result = pii.check_text_for_pii("mi email es juan@empresa.com")
        assert result.action in (GuardrailAction.WARN, GuardrailAction.BLOCK)
        assert result.details.get("reason") == "pii_detected"
        findings = result.details.get("findings", {})
        assert "email" in findings

    def test_check_text_for_pii_blocks_credit_card(self) -> None:
        """Un prompt con tarjeta de credito debe resultar en BLOCK (riesgo CRITICAL)."""
        pii = PIIGuardrails(lang="es")
        result = pii.check_text_for_pii("mi tarjeta es 4111222233334444")
        assert result.action == GuardrailAction.BLOCK
        assert result.risk == RiskLevel.CRITICAL
        findings = result.details.get("findings", {})
        assert "credit_card" in findings

    def test_check_text_for_pii_blocks_api_key(self) -> None:
        """Un prompt con api_key=... debe resultar en BLOCK (riesgo HIGH)."""
        pii = PIIGuardrails(lang="es")
        result = pii.check_text_for_pii('mi api_key="sk-AbCdEf1234567890XyZwVuTsRqPoNmLkJiHg"')
        assert result.action == GuardrailAction.BLOCK
        findings = result.details.get("findings", {})
        assert "api_key_like" in findings

    def test_check_text_for_pii_blocks_bearer_token(self) -> None:
        """Un prompt con Bearer token debe resultar en BLOCK (riesgo HIGH)."""
        pii = PIIGuardrails(lang="es")
        result = pii.check_text_for_pii("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
        assert result.action == GuardrailAction.BLOCK
        findings = result.details.get("findings", {})
        assert "bearer_token" in findings

    def test_check_text_for_pii_allows_clean_text(self) -> None:
        """Un prompt sin PII debe resultar en ALLOW."""
        pii = PIIGuardrails(lang="es")
        result = pii.check_text_for_pii("quiero registrar un nuevo cliente")
        assert result.action == GuardrailAction.ALLOW

    def test_check_text_for_pii_filters_known_false_positives(self) -> None:
        """Emails en dominios de ejemplo (test.com, example.com) deben filtrarse."""
        pii = PIIGuardrails(lang="es")
        # test.com y example.com estan en la lista de falsos positivos.
        result = pii.check_text_for_pii("contacta a test@test.com o admin@example.com")
        # Si solo hay falsos positivos, no debe bloquear.
        assert result.action == GuardrailAction.ALLOW


class TestBugB07GuardrailManagerCheckPrompt:
    """GuardrailManager.check_prompt debe incluir la capa PII."""

    def test_check_prompt_blocks_pii_email_and_credit_card(self) -> None:
        """Bug B-07: el caso del catalogo — email + tarjeta debe ser bloqueado."""
        mgr = GuardrailManager(lang="es")
        text = "mi email es juan@test.com y mi tarjeta es 4111222233334444"
        result = mgr.check_prompt(text)
        assert result.blocked, (
            "BUG B-07: check_prompt no bloqueo un prompt con email + tarjeta. "
            f"Action obtenida: {result.overall_action}"
        )

    def test_check_prompt_blocks_api_key(self) -> None:
        """Un prompt con API key debe ser bloqueado por la capa PII."""
        mgr = GuardrailManager(lang="es")
        text = 'usa esta api_key="sk-AbCdEf1234567890XyZwVuTsRqPoNmLkJiHg" para acceder'
        result = mgr.check_prompt(text)
        assert result.blocked
        # Y debe estar bloqueado por PII, no solo por content.
        assert "pii" in result.checks
        assert result.checks["pii"].action == GuardrailAction.BLOCK

    def test_check_prompt_allows_clean_prompt(self) -> None:
        """Un prompt sin PII ni contenido peligroso debe pasar."""
        mgr = GuardrailManager(lang="es")
        result = mgr.check_prompt("quiero registrar un nuevo cliente")
        assert not result.blocked
        assert result.overall_action in (GuardrailAction.ALLOW, GuardrailAction.WARN)

    def test_check_prompt_pii_dict_blocks_email(self) -> None:
        """El metodo de conveniencia check_prompt_pii debe retornar dict con blocked=True."""
        mgr = GuardrailManager(lang="es")
        result = mgr.check_prompt_pii("mi email es juan@empresa.com")
        assert isinstance(result, dict)
        assert result.get("blocked") is True
        assert result.get("reason") == "PII detectada"
        assert "email" in result.get("patterns", [])

    def test_check_prompt_pii_dict_blocks_credit_card(self) -> None:
        """check_prompt_pii debe bloquear tarjetas de credito."""
        mgr = GuardrailManager(lang="es")
        result = mgr.check_prompt_pii("mi tarjeta es 4111222233334444")
        assert result.get("blocked") is True
        assert "credit_card" in result.get("patterns", [])

    def test_check_prompt_pii_dict_allows_clean(self) -> None:
        """check_prompt_pii debe retornar blocked=False para prompts limpios."""
        mgr = GuardrailManager(lang="es")
        result = mgr.check_prompt_pii("quiero registrar un nuevo cliente")
        assert isinstance(result, dict)
        assert result == {"blocked": False}

    def test_check_prompt_pii_dict_blocks_api_key(self) -> None:
        """check_prompt_pii debe bloquear API keys en el prompt."""
        mgr = GuardrailManager(lang="es")
        result = mgr.check_prompt_pii('api_key="sk-AbCdEf1234567890XyZwVuTsRqPoNmLkJiHg"')
        assert result.get("blocked") is True
        assert "api_key_like" in result.get("patterns", [])


class TestBugB07CompositeWithPII:
    """Verifica que la capa PII se integra correctamente con _aggregate."""

    def test_pii_block_propagates_to_composite_blocked(self) -> None:
        """Si PII bloquea, el CompositeGuardrailResult.blocked debe ser True."""
        mgr = GuardrailManager(lang="es")
        # Solo PII (no hay patron de prompt injection ni XSS).
        result = mgr.check_prompt("mi tarjeta es 4111222233334444")
        assert result.blocked is True
        assert "pii" in result.checks
        assert result.checks["pii"].action == GuardrailAction.BLOCK
        # Y debe haber al menos un block en la lista.
        assert len(result.blocks) >= 1

    def test_pii_warn_does_not_force_block_when_content_allows(self) -> None:
        """Si PII solo advierte y content permite, el composite puede ser WARN.

        Esto protege el contrato: cuando la PII es de riesgo bajo (ej: un email
        suelto), el CompositeGuardrailResult puede quedar como WARN y el caller
        decide si enmascarar o continuar.
        """
        mgr = GuardrailManager(lang="es")
        # email@empresa.com NO esta en la lista de falsos positivos.
        result = mgr.check_prompt("mi email es juan@empresa.com")
        # Como minimo, el check de PII debe estar presente y ser WARN o BLOCK.
        assert "pii" in result.checks
        assert result.checks["pii"].action in (GuardrailAction.WARN, GuardrailAction.BLOCK)
