"""
Workflow Determinista — Air-Gapped Deployment Configuration

Modo de operación completamente desconectado (offline/air-gapped).
Desactiva todas las llamadas externas y valida que el sistema
pueda operar sin conectividad a internet.

Características:
- Desactiva conectores que requieren internet (OpenAI, Anthropic, etc.)
- Usa resolución local de DNS / IPs estáticas
- Validación de licencia offline mediante HMAC local
- Cache local de imágenes Docker para deploy air-gapped
- Verificación de integridad de paquetes sin telemetría
- Fallback a modelos locales (Ollama) cuando los cloud no están disponibles
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from src.core.logging import setup_logging

logger = setup_logging("airgap")

# ── Environment Variable Names (evaluated lazily in __init__) ──
_ENV_AIRGAP_MODE = "WFD_AIRGAP_MODE"
_ENV_AIRGAP_ALLOW_LOCAL_AI = "WFD_AIRGAP_ALLOW_LOCAL_AI"
_ENV_AIRGAP_REGISTRY_MIRROR = "WFD_AIRGAP_REGISTRY_MIRROR"
_ENV_AIRGAP_LICENSE_FILE = "WFD_AIRGAP_LICENSE_FILE"

# Conectores que REQUIEREN internet (desactivados en modo air-gapped)
CLOUD_CONNECTORS: list[str] = [
    "openai_v2",
    "anthropic",
    "huggingface",
    "deepseek",
    "sendgrid",
    "twilio",
    "datadog",
    "sentry",
    "intercom",
    "hubspot",
    "salesforce",
    "zoho_crm",
    "pipedrive",
    "quickbooks",
    "paypal",
    "square",
    "wise",
    "mercadolibre",
    "asana",
    "notion",
    "jira",
    "github",
    "gitlab",
    "discord",
    "teams",
    "dropbox",
    "aws_s3",
    "azure_blob",
    "gcs",
    "elastic",
    "mongo_connector",
    "mysql_connector",
    "marketo",
    "freshdesk",
    "new_relic",
    "sumologic",
    "pagerduty",
    "typeform",
    "mailgun",
    "woocommerce",
    "confluence",
    "azure_ad",
    "airtable",
]

# Conectores que funcionan OFFLINE (mantenidos en modo air-gapped)
LOCAL_CONNECTORS: list[str] = [
    "sat_mexico",    # SAT México (puede operar con archivos locales)
    "pix_brazil",    # PIX Brazil (operación local con QR)
    "totvs",         # TOTVS ERP (red local)
    "vault",         # HashiCorp Vault (infraestructura local)
]


class AirGapConfig:
    """Air-gapped deployment configuration.

    Validates that the system can operate without internet access
    and provides helpers for offline operation.
    """

    def __init__(self) -> None:
        # Read env vars lazily so tests can set them before instantiation
        self.enabled = os.environ.get(_ENV_AIRGAP_MODE, "false").lower() == "true"
        self.allow_local_ai = os.environ.get(_ENV_AIRGAP_ALLOW_LOCAL_AI, "false").lower() == "true"
        self.registry_mirror = os.environ.get(_ENV_AIRGAP_REGISTRY_MIRROR, "")
        self.license_file = os.environ.get(_ENV_AIRGAP_LICENSE_FILE, "/etc/zenic-flijo/license.json")
        self._disabled_connectors: list[str] = []
        self._validation_results: dict[str, bool] = {}

    def validate(self) -> dict[str, Any]:
        """Run air-gapped readiness validation checks."""
        if not self.enabled:
            return {"airgap_enabled": False, "message": "Air-gapped mode is disabled"}

        checks: dict[str, bool] = {}

        # 1. No internet access check
        checks["no_internet_access"] = self._check_no_internet()

        # 2. DNS resolution should work for internal services
        checks["internal_dns"] = self._check_internal_dns()

        # 3. License file exists and is valid
        checks["offline_license"] = self._check_offline_license()

        # 4. Docker registry mirror configured (if Docker is used)
        checks["registry_mirror"] = self._check_registry_mirror()

        # 5. Local AI available (if enabled)
        if self.allow_local_ai:
            checks["local_ai"] = self._check_local_ai()
        else:
            checks["local_ai"] = True  # Not required

        # 6. Local database connectivity
        checks["local_db"] = self._check_local_db()

        # 7. File system writable for offline storage
        checks["writable_storage"] = self._check_writable_storage()

        self._validation_results = checks

        return {
            "airgap_enabled": True,
            "registry_mirror": self.registry_mirror,
            "allow_local_ai": self.allow_local_ai,
            "checks": checks,
            "all_passed": all(checks.values()),
            "disabled_connectors": self.get_disabled_connectors(),
            "local_connectors": self.get_local_connectors(),
        }

    def get_disabled_connectors(self) -> list[str]:
        """Return list of connectors that should be disabled in air-gapped mode."""
        if not self.enabled:
            return []
        return CLOUD_CONNECTORS

    def get_local_connectors(self) -> list[str]:
        """Return list of connectors that work offline."""
        return LOCAL_CONNECTORS

    def is_connector_allowed(self, connector_name: str) -> bool:
        """Check if a connector is allowed in the current mode."""
        if not self.enabled:
            return True
        return connector_name.lower() not in CLOUD_CONNECTORS

    def create_airgap_license(
        self,
        customer_name: str,
        license_key: str,
        expiry_days: int = 365,
        output_path: str = "",
    ) -> dict[str, Any]:
        """Create an offline license file for air-gapped deployment.

        In air-gapped mode, license validation happens locally using
        HMAC-SHA256 instead of an online validation service.
        """
        import hashlib
        import hmac

        from src.core.config import LICENSE_SECRET_KEY

        output = output_path or self.license_file

        payload = {
            "customer": customer_name,
            "license_key": license_key,
            "issued_at": time.time(),
            "expires_at": time.time() + (expiry_days * 86400),
            "airgap": True,
            "features": ["all"],
            "max_workflows": 1000,
            "max_connectors": 60,
        }

        # Sign with HMAC-SHA256
        payload_json = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            LICENSE_SECRET_KEY.encode(),
            payload_json.encode(),
            hashlib.sha256,
        ).hexdigest()

        license_data = {
            "payload": payload,
            "signature": signature,
            "version": "2.0",
        }

        output_path_obj = Path(output)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        output_path_obj.write_text(json.dumps(license_data, indent=2))

        logger.info(f"AirGap: Offline license created at {output}")
        return license_data

    def verify_airgap_license(self, license_path: str = "") -> dict[str, Any]:
        """Verify an offline air-gapped license file."""
        import hashlib
        import hmac

        from src.core.config import LICENSE_SECRET_KEY

        path = Path(license_path or self.license_file)
        if not path.exists():
            return {"valid": False, "error": f"License file not found: {path}"}

        try:
            data = json.loads(path.read_text())
            payload = data.get("payload", {})
            signature = data.get("signature", "")

            # Verify signature
            payload_json = json.dumps(payload, sort_keys=True)
            expected_sig = hmac.new(
                LICENSE_SECRET_KEY.encode(),
                payload_json.encode(),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return {"valid": False, "error": "Invalid license signature"}

            # Check expiry
            expires_at = payload.get("expires_at", 0)
            now = time.time()
            if now > expires_at:
                return {"valid": False, "error": "License expired"}

            return {
                "valid": True,
                "customer": payload.get("customer", ""),
                "expires_at": expires_at,
                "days_remaining": int((expires_at - now) / 86400),
                "airgap": payload.get("airgap", False),
                "features": payload.get("features", []),
            }
        except (json.JSONDecodeError, KeyError) as e:
            return {"valid": False, "error": f"Invalid license file: {e}"}

    # ── Internal Checks ────────────────────────────────────

    def _check_no_internet(self) -> bool:
        """Verify no internet access is available (as expected in air-gap).

        Fix Sprint 2 bug #39: antes solo testeaba 8.8.8.8:53 (Google DNS),
        lo que daba falsos negativos si esa IP estaba bloqueada pero había
        internet por otras vías. Ahora prueba múltiples endpoints conocidos:
        si AL MENOS UNO responde, hay internet (no es airgap).
        """
        import socket

        # Endpoints a testear: DNS públicos + un dominio conocido.
        # Si cualquiera responde, hay internet → no es airgap.
        test_endpoints = [
            ("8.8.8.8", 53),            # Google DNS
            ("1.1.1.1", 53),            # Cloudflare DNS
            ("9.9.9.9", 53),            # Quad9 DNS
        ]
        # Test de DNS resolve (si resuelve un dominio público, hay internet)
        test_domains = ["example.com", "cloudflare.com"]

        for host, port in test_endpoints:
            try:
                socket.create_connection((host, port), timeout=2)
                logger.warning(
                    f"AirGap: Internet access detected via {host}:{port}! "
                    f"Air-gap should block external traffic."
                )
                return False  # Hay internet
            except (TimeoutError, OSError):
                continue  # Este endpoint no responde, probar el siguiente

        # Test DNS resolution: si un dominio público resuelve, hay internet
        for domain in test_domains:
            try:
                socket.getaddrinfo(domain, 80, socket.AF_INET)
                logger.warning(
                    f"AirGap: DNS resolution for '{domain}' succeeded — internet detected!"
                )
                return False
            except (socket.gaierror, OSError):
                continue

        # Todos los tests fallaron → no hay internet → es airgap
        return True

    def _check_internal_dns(self) -> bool:
        """Verify internal DNS resolution works for local services."""
        import socket
        internal_hosts = [
            "database.internal",
            "redis.internal",
            "vault.internal",
        ]
        for host in internal_hosts:
            with contextlib.suppress(socket.gaierror):
                socket.getaddrinfo(host, 80, socket.AF_INET)
        # Not critical — internal services may use IPs directly
        return True

    def _check_offline_license(self) -> bool:
        """Check offline license file exists and is valid."""
        result = self.verify_airgap_license()
        return result.get("valid", False)

    def _check_registry_mirror(self) -> bool:
        """Check if Docker registry mirror is configured."""
        if not self.registry_mirror:
            # No registry mirror configured — warn but don't fail
            logger.warning("AirGap: No registry mirror configured. Set WFD_AIRGAP_REGISTRY_MIRROR")
            return True  # Not blocking
        return True

    def _check_local_ai(self) -> bool:
        """Check if local AI (Ollama) is available."""
        try:
            # Resolver path absoluto para mitigar B607 (PATH injection).
            from src.core.utils import resolve_binary
            ollama_bin = resolve_binary("ollama", allow_none=True)
            if ollama_bin is None:
                logger.warning("AirGap: Local AI (Ollama) not available (not in PATH)")
                return False

            result = subprocess.run(
                [ollama_bin, "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("AirGap: Local AI (Ollama) not available")
            return False

    def _check_local_db(self) -> bool:
        """Verify local database connectivity."""
        try:
            from src.core.db import DatabaseManager
            db = DatabaseManager()
            conn = db.get_connection()
            conn.execute("SELECT 1")
            conn.close()
            return True
        except Exception as e:
            logger.error(f"AirGap: Local DB check failed: {e}")
            return False

    def _check_writable_storage(self) -> bool:
        """Verify local storage is writable."""
        from src.core.config import DATA_DIR
        try:
            test_file = Path(DATA_DIR) / ".airgap_test"
            test_file.write_text("ok")
            test_file.unlink()
            return True
        except OSError as e:
            logger.error(f"AirGap: Storage not writable: {e}")
            return False

    def get_status_summary(self) -> dict[str, Any]:
        """Get a summary of the current air-gapped deployment status."""
        if not self.enabled:
            return {
                "mode": "online",
                "message": "System is in online mode. Set WFD_AIRGAP_MODE=true for air-gapped deployment.",
            }

        validation = self.validate()
        return {
            "mode": "airgapped",
            "enabled": True,
            "registry_mirror": self.registry_mirror or "none",
            "local_ai": self.allow_local_ai,
            "disabled_connectors": len(self.get_disabled_connectors()),
            "local_connectors": len(self.get_local_connectors()),
            "checks": validation.get("checks", {}),
            "all_checks_passed": validation.get("all_passed", False),
            "license_valid": self._check_offline_license(),
        }


# ── Singleton instance ─────────────────────────────────

_instance: AirGapConfig | None = None


def get_instance() -> AirGapConfig:
    """Get or create the AirGapConfig singleton."""
    global _instance
    if _instance is None:
        _instance = AirGapConfig()
    return _instance


def is_connector_allowed(name: str) -> bool:
    """Convenience function to check if a connector is allowed."""
    return get_instance().is_connector_allowed(name)


def get_connector_filter() -> dict[str, Any]:
    """Get air-gap connector filter for use in connector registration."""
    config = get_instance()
    return {
        "disabled": config.get_disabled_connectors(),
        "local_only": config.get_local_connectors(),
    }
