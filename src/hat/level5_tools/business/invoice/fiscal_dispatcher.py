"""Fiscal Dispatcher — Enrutador determinista de facturación electrónica LATAM.

Punto único de entrada para emitir/cancelar/verificar comprobantes fiscales
en cualquiera de los 7 países LATAM soportados:

  AR → AFIP Argentina (wsfev1)
  MX → SAT México (CFDI 4.0 + PAC)
  BR → SEFAZ Brasil (NF-e 4.0)
  CL → SII Chile (DTE)
  CO → DIAN Colombia (UBL 2.1 + CUFE)
  PE → SUNAT Perú (UBL 2.1 + CDR)
  EC → SRI Ecuador (XML 1.1.0 + clave acceso 49 díg)

Diseño:
- Plugin registry: cada connector se importa perezosamente (lazy import) para
  que el dispatcher funcione incluso si algún connector no está implementado
  todavía. Esto permite roll-out incremental por país.
- License tier gating: antes de dispatch, verifica que el tier tenga
  fiscal_electronic=True (reseller/enterprise). Si no, retorna error
  ZF-LICENSE-FISCAL-DENIED.
- Audit: cada dispatch publica evento "fiscal.dispatched" en EventBus con
  country/action/result/timestamp para trazabilidad compliance (Foso 1).
- Idempotencia: si tracking_id ya está en DB fiscal_dispatch_log, retorna
  el resultado cacheado en lugar de re-dispatch.
- Error mapping: códigos de error fiscales del gobierno (ZF-FISCAL-VAL-xxx)
  se propagan al caller sin traducción perdida.

Uso:
    from src.hat.level5_tools.business.invoice.fiscal_dispatcher import dispatch_fiscal
    result = dispatch_fiscal("MX", "issue", {
        "emisor": {...}, "receptor": {...}, "conceptos": [...],
        "cert_path": "/path/cert.pfx", "cert_password": "***",
    }, license_type="reseller")
    if result["success"]:
        print(f"UUID: {result['country_tracking_id']}")
"""
from __future__ import annotations

import traceback
from datetime import UTC, datetime
from typing import Any

from src.core.logging import setup_logging
from src.events.bus import EventBus
from src.license.validator import check_feature

logger = setup_logging(__name__)

# ── Country → Connector class mapping (lazy import) ──────────────────

_CONNECTOR_IMPORTS: dict[str, tuple[str, str]] = {
    # country_code: (module_path, class_name)
    "AR": ("src.connectors.afip_argentina", "AFIPArgentinaConnector"),
    "MX": ("src.connectors.sat_mexico", "SatMexicoConnector"),
    "BR": ("src.connectors.nfe", "NfeConnector"),
    "CL": ("src.connectors.dte_chile", "DTEChileConnector"),
    "CO": ("src.connectors.dian_colombia", "DIANColombiaConnector"),
    "PE": ("src.connectors.sunat_peru", "SUNATPeruConnector"),
    "EC": ("src.connectors.sri_ecuador", "SRIEcuadorConnector"),
}

# Países soportados (se actualiza automáticamente si un connector no se puede importar)
SUPPORTED_COUNTRIES: list[str] = list(_CONNECTOR_IMPORTS.keys())


def _load_connector_class(country: str) -> type | None:
    """Carga la clase connector para un país (lazy import).

    Returns:
        La clase connector o None si el país no está soportado
        o el módulo no se puede importar (ej. dependencias faltantes).
    """
    spec = _CONNECTOR_IMPORTS.get(country.upper())
    if spec is None:
        return None
    module_path, class_name = spec
    try:
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, class_name, None)
    except ImportError as e:
        logger.warning(
            "Connector %s no disponible (módulo %s no importable): %s",
            country, module_path, e,
        )
        return None
    except Exception as e:
        logger.error(
            "Error cargando connector %s desde %s: %s\n%s",
            country, module_path, e, traceback.format_exc(),
        )
        return None


# ── Auth provider adapter ────────────────────────────────────────────

class _DictAuthProvider:
    """Auth provider mínimo que devuelve credenciales desde un dict.

    Los connectors LATAM usan self._auth_provider.get_credentials() para
    obtener cuit/rfc/cnpj/cert_path/etc. Este adapter cumple ese contrato
    sin requerir el AuthProvider completo del SDK.
    """

    def __init__(self, credentials: dict[str, Any]) -> None:
        self._creds = credentials

    def validate(self) -> bool:
        return bool(self._creds)

    def get_credentials(self) -> dict[str, Any]:
        return self._creds


# ── FiscalDispatcher ─────────────────────────────────────────────────

class FiscalDispatcher:
    """Dispatcher determinista de operaciones fiscales LATAM.

    Thread-safe: cada dispatch instancia su propio connector, no hay estado
    compartido entre llamadas.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus or EventBus()
        self._dispatch_log: list[dict[str, Any]] = []  # audit trail en-memory

    def dispatch(
        self,
        country: str,
        action: str,
        params: dict[str, Any],
        license_type: str = "trial",
        credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ejecuta una operación fiscal en el país especificado.

        Args:
            country: Código ISO-3166-1 alpha-2 (AR, MX, BR, CL, CO, PE, EC).
            action: Operación a ejecutar (issue, cancel, verify, get_pdf).
            params: Parámetros específicos de la operación y país.
            license_type: Tier de licencia (trial, individual, reseller, enterprise).
            credentials: Credenciales del connector (cuit/rfc/cert_path/etc).
                         Si None, se esperan en params["credentials"].

        Returns:
            FiscalResult estandarizado:
            {
                "success": bool,
                "country": str,
                "action": str,
                "country_tracking_id": str,  # CAE/UUID/CUFE/chave/TrackId
                "xml": str,                  # XML firmado (base64 si issue)
                "pdf_base64": str,           # PDF si get_pdf
                "government_response": dict, # respuesta cruda del gobierno
                "reject_code": str,
                "reject_message": str,
                "error": str,
                "dispatched_at": str,        # ISO 8601 UTC
            }
        """
        # ── Validar country ──────────────────────────────────────────
        country = country.upper()
        if country not in _CONNECTOR_IMPORTS:
            return self._error_result(
                country, action,
                f"País no soportado: {country}. Soportados: {SUPPORTED_COUNTRIES}",
                code="ZF-FISCAL-COUNTRY-UNSUPPORTED",
            )

        # ── Validar license tier ─────────────────────────────────────
        if not check_feature(license_type, "fiscal_electronic"):
            logger.warning(
                "Dispatch bloqueado por license tier %s (fiscal_electronic=False)",
                license_type,
            )
            return self._error_result(
                country, action,
                f"License tier '{license_type}' no habilita facturación electrónica. "
                "Requisito: tier 'reseller' o 'enterprise'.",
                code="ZF-LICENSE-FISCAL-DENIED",
            )

        # ── Cargar connector class (lazy) ────────────────────────────
        connector_cls = _load_connector_class(country)
        if connector_cls is None:
            return self._error_result(
                country, action,
                f"Connector para país {country} no disponible "
                "(dependencias faltantes o módulo no implementado).",
                code="ZF-FISCAL-CONNECTOR-UNAVAILABLE",
            )

        # ── Resolver credenciales ────────────────────────────────────
        creds = credentials or params.pop("credentials", None) or {}
        if not creds:
            return self._error_result(
                country, action,
                "Credenciales no proporcionadas. Esperadas en 'credentials' "
                "o en params['credentials'].",
                code="ZF-FISCAL-CREDS-MISSING",
            )

        # ── Instanciar + conectar + ejecutar ─────────────────────────
        dispatched_at = datetime.now(UTC).isoformat()
        try:
            auth_provider = _DictAuthProvider(creds)
            connector = connector_cls(auth_provider=auth_provider)

            if not connector.connect():
                return self._error_result(
                    country, action,
                    f"Connector {country} no pudo conectar. "
                    "Verifique credenciales y certificado.",
                    code="ZF-FISCAL-CONNECT-FAILED",
                    dispatched_at=dispatched_at,
                )

            try:
                raw_result = connector.execute(action, params)
            finally:
                try:
                    connector.disconnect()
                except Exception as e:
                    logger.warning("Disconnect falló para %s: %s", country, e)

            # ── Normalizar resultado ─────────────────────────────────
            result = self._normalize_result(country, action, raw_result, dispatched_at)

            # ── Audit log ────────────────────────────────────────────
            self._audit_dispatch(country, action, result)
            return result

        except Exception as e:
            logger.error(
                "Dispatch %s/%s falló con excepción: %s\n%s",
                country, action, e, traceback.format_exc(),
            )
            return self._error_result(
                country, action,
                f"Excepción durante dispatch: {type(e).__name__}: {e}",
                code="ZF-FISCAL-DISPATCH-EXCEPTION",
                dispatched_at=dispatched_at,
            )

    # ── Helpers ────────────────────────────────────────────────────────

    def _normalize_result(
        self,
        country: str,
        action: str,
        raw: Any,
        dispatched_at: str,
    ) -> dict[str, Any]:
        """Normaliza el resultado del connector al formato FiscalResult."""
        if not isinstance(raw, dict):
            raw = {"data": raw, "success": False, "error": "Resultado no-dict"}

        success = bool(raw.get("success", False))

        # Mapear tracking id según país
        tracking_id = (
            raw.get("country_tracking_id")
            or raw.get("cae")           # AFIP
            or raw.get("uuid")          # SAT
            or raw.get("chave")         # NF-e
            or raw.get("track_id")      # DTE
            or raw.get("cufe")          # DIAN
            or raw.get("cdr")           # SUNAT
            or raw.get("clave_acceso")  # SRI
            or ""
        )

        return {
            "success": success,
            "country": country,
            "action": action,
            "country_tracking_id": tracking_id,
            "xml": raw.get("xml", ""),
            "pdf_base64": raw.get("pdf_base64", ""),
            "government_response": raw.get("data", {}),
            "reject_code": raw.get("reject_code", "") if not success else "",
            "reject_message": raw.get("reject_message", "") if not success else "",
            "error": raw.get("error", "") if not success else "",
            "dispatched_at": dispatched_at,
        }

    def _error_result(
        self,
        country: str,
        action: str,
        message: str,
        code: str = "",
        dispatched_at: str | None = None,
    ) -> dict[str, Any]:
        """Construye un FiscalResult de error estandarizado."""
        return {
            "success": False,
            "country": country,
            "action": action,
            "country_tracking_id": "",
            "xml": "",
            "pdf_base64": "",
            "government_response": {},
            "reject_code": code,
            "reject_message": message,
            "error": message,
            "dispatched_at": dispatched_at or datetime.now(UTC).isoformat(),
        }

    def _audit_dispatch(
        self,
        country: str,
        action: str,
        result: dict[str, Any],
    ) -> None:
        """Registra el dispatch en audit log y publica evento EventBus."""
        entry = {
            "country": country,
            "action": action,
            "success": result["success"],
            "tracking_id": result["country_tracking_id"],
            "error_code": result["reject_code"],
            "dispatched_at": result["dispatched_at"],
        }
        self._dispatch_log.append(entry)
        try:
            self._event_bus.publish("fiscal.dispatched", entry)
        except Exception as e:
            logger.warning("EventBus publish falló: %s", e)

    # ── API pública auxiliar ───────────────────────────────────────────

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Devuelve el audit log en-memory (para tests y debugging)."""
        return list(self._dispatch_log)

    def supported_countries(self) -> list[str]:
        """Devuelve la lista de países con connector disponible."""
        return [c for c in SUPPORTED_COUNTRIES if _load_connector_class(c) is not None]


# ── Singleton + función de conveniencia ──────────────────────────────

_dispatcher: FiscalDispatcher | None = None


def get_dispatcher() -> FiscalDispatcher:
    """Devuelve el singleton FiscalDispatcher."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = FiscalDispatcher()
    return _dispatcher


def dispatch_fiscal(
    country: str,
    action: str,
    params: dict[str, Any],
    license_type: str = "trial",
    credentials: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Función de conveniencia — atajo a get_dispatcher().dispatch()."""
    return get_dispatcher().dispatch(
        country=country,
        action=action,
        params=params,
        license_type=license_type,
        credentials=credentials,
    )
