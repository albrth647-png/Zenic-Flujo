"""
Metricas de Compliance — verificaciones de auditoria y reportes.

Responsabilidad:
- ``record_compliance_audit_check``: contador por framework+status + contador
  de violaciones por framework+control si status=fail.
- ``record_compliance_report_generated``: contador por framework+type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class ComplianceMetricsMixin:
    """Metricas de compliance (SOC2, GDPR, HIPAA, etc.)."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_compliance_audit_check(
        self,
        framework: str,
        control: str,
        status: str,
    ) -> None:
        """
        Registra una verificacion de auditoria de compliance.

        Args:
            framework: Framework (SOC2, GDPR, HIPAA)
            control: Control verificado
            status: Estado (pass, fail, warning)
        """
        self._metrics.increment_counter(
            "compliance_audit_checks_total",
            labels={"framework": framework, "status": status},
        )
        if status == "fail":
            self._metrics.increment_counter(
                "compliance_violations_total",
                labels={"framework": framework, "control": control},
            )

    def record_compliance_report_generated(
        self,
        framework: str,
        report_type: str,
    ) -> None:
        """
        Registra la generacion de un reporte de compliance.

        Args:
            framework: Framework (SOC2, GDPR, HIPAA)
            report_type: Tipo de reporte
        """
        self._metrics.increment_counter(
            "compliance_reports_generated_total",
            labels={"framework": framework, "type": report_type},
        )
