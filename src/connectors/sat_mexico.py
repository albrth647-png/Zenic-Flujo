"""
Conector SAT Mexico — Facturacion CFDI via SAT
===================================================

Permite generar, timbrar, cancelar y consultar facturas
CFDI conforme a los requisitos del SAT Mexico.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class SatMexicoConnector(BaseConnector):
    """Conector para SAT Mexico: facturacion CFDI, timbrado y cancelacion."""

    name = "sat_mexico"
    version = "1.0.0"
    description = "Genera, timbra y consulta facturas CFDI del SAT Mexico"
    category = "latam"
    icon = "file-text"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.sat.gob.mx/v1"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con el PAC (Proveedor Autorizado de Certificacion)."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("SatMexicoConnector: credenciales PAC no configuradas")
            return False
        try:
            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )
            # SAT PAC uses API key + Basic auth with pac_user/pac_password
            creds = self._auth_provider.get_credentials()
            pac_user = creds.get("pac_user", "")
            pac_password = creds.get("pac_password", "")
            rfc = creds.get("rfc", "")
            if pac_user and pac_password:
                self._http.set_auth("Basic", username=pac_user, password=pac_password)
            if rfc:
                self._http.set_header("X-RFC", rfc)

            # Validate connection by checking service status
            resp = self._http.get("/status")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", "Credenciales PAC configuradas")
                return True
            # If status endpoint is not available, still consider connected
            # (some PACs don't have a status endpoint)
            self._connected = True
            self._log_operation("connect", "Credenciales PAC configuradas (sin verificacion de estado)")
            return True
        except HTTPClientError as e:
            # Even if status check fails, set up the client for later use
            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )
            creds = self._auth_provider.get_credentials()
            pac_user = creds.get("pac_user", "")
            pac_password = creds.get("pac_password", "")
            rfc = creds.get("rfc", "")
            if pac_user and pac_password:
                self._http.set_auth("Basic", username=pac_user, password=pac_password)
            if rfc:
                self._http.set_header("X-RFC", rfc)
            self._connected = True
            self._log_operation("connect", f"Credenciales PAC configuradas (status check fallo: {e})")
            return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector SAT Mexico.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "generate_cfdi": self._generate_cfdi,
            "stamp_cfdi": self._stamp_cfdi,
            "cancel_cfdi": self._cancel_cfdi,
            "get_cfdi": self._get_cfdi,
            "get_cfdi_pdf": self._get_cfdi_pdf,
            "verify_cfdi": self._verify_cfdi,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales del PAC esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con el PAC."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _generate_cfdi(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera un CFDI (Comprobante Fiscal Digital por Internet).

        Args:
            params: Debe contener 'receptor', 'conceptos', 'forma_pago',
                    'metodo_pago', 'uso_cfdi'
        """
        receptor = params.get("receptor", {})
        conceptos = params.get("conceptos", [])
        if not receptor or not conceptos:
            return {"success": False, "error": "Parametros requeridos: receptor, conceptos"}
        self._log_operation("generate_cfdi", f"receptor_rfc={receptor.get('rfc', 'N/A')}")

        payload: dict[str, Any] = {
            "receptor": receptor,
            "conceptos": conceptos,
            "forma_pago": params.get("forma_pago", ""),
            "metodo_pago": params.get("metodo_pago", ""),
            "uso_cfdi": params.get("uso_cfdi", ""),
        }
        if params.get("emisor"):
            payload["emisor"] = params["emisor"]
        if params.get("serie"):
            payload["serie"] = params["serie"]
        if params.get("folio"):
            payload["folio"] = params["folio"]
        if params.get("condiciones_de_pago"):
            payload["condiciones_de_pago"] = params["condiciones_de_pago"]

        try:
            resp = self._http.post("/cfdi/generate", json=payload)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "uuid": data.get("uuid", ""),
                    "xml": data.get("xml", ""),
                    "estado": data.get("estado", "generado"),
                    "total": data.get("total", 0.0),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _stamp_cfdi(self, params: dict[str, Any]) -> dict[str, Any]:
        """Timbra un CFDI generado previamente.

        Args:
            params: Debe contener 'xml' (XML del CFDI a timbrar)
        """
        xml = params.get("xml", "")
        if not xml:
            return {"success": False, "error": "Parametro requerido: xml"}
        self._log_operation("stamp_cfdi")

        payload: dict[str, Any] = {"xml": xml}

        try:
            resp = self._http.post("/cfdi/stamp", json=payload)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "uuid": data.get("uuid", ""),
                    "xml_timbrado": data.get("xml_timbrado", data.get("xml", "")),
                    "fecha_timbrado": data.get("fecha_timbrado", ""),
                    "estado": data.get("estado", "timbrado"),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _cancel_cfdi(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cancela un CFDI timbrado.

        Args:
            params: Debe contener 'uuid' y 'motivo'
                    (01=Comprobante emitido con errores,
                     02=Comprobante emitido sin relacion,
                     03=No se llevo a cabo la operacion,
                     04=Operacion nominativa relacionada en factura global)
        """
        uuid_val = params.get("uuid", "")
        motivo = params.get("motivo", "")
        if not uuid_val or not motivo:
            return {"success": False, "error": "Parametros requeridos: uuid, motivo"}
        self._log_operation("cancel_cfdi", f"uuid={uuid_val}")

        payload: dict[str, Any] = {"uuid": uuid_val, "motivo": motivo}
        if params.get("folio_sustitucion"):
            payload["folio_sustitucion"] = params["folio_sustitucion"]

        try:
            resp = self._http.post(f"/cfdi/{uuid_val}/cancel", json=payload)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "uuid": uuid_val,
                    "estado": data.get("estado", "cancelado"),
                    "fecha_cancelacion": data.get("fecha_cancelacion", ""),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_cfdi(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un CFDI por su UUID.

        Args:
            params: Debe contener 'uuid'
        """
        uuid_val = params.get("uuid", "")
        if not uuid_val:
            return {"success": False, "error": "Parametro requerido: uuid"}
        self._log_operation("get_cfdi", f"uuid={uuid_val}")

        try:
            resp = self._http.get(f"/cfdi/{uuid_val}")
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "uuid": uuid_val,
                    "estado": data.get("estado", "vigente"),
                    "xml": data.get("xml", ""),
                    "fecha": data.get("fecha", ""),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_cfdi_pdf(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene la representacion impresa (PDF) de un CFDI.

        Args:
            params: Debe contener 'uuid'
        """
        uuid_val = params.get("uuid", "")
        if not uuid_val:
            return {"success": False, "error": "Parametro requerido: uuid"}
        self._log_operation("get_cfdi_pdf", f"uuid={uuid_val}")

        try:
            resp = self._http.get(
                f"/cfdi/{uuid_val}/pdf",
                headers={"Accept": "application/pdf"},
            )
            if resp.ok:
                data = resp.json() if resp.json() else {}
                # PDF may be returned as base64 in a JSON wrapper or as raw bytes
                pdf_base64 = data.get("pdf_base64", "") if isinstance(data, dict) else ""
                if not pdf_base64 and resp.raw:
                    import base64
                    pdf_base64 = base64.b64encode(resp.raw).decode("utf-8")
                return {
                    "success": True,
                    "uuid": uuid_val,
                    "pdf_base64": pdf_base64,
                    "content_type": "application/pdf",
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _verify_cfdi(self, params: dict[str, Any]) -> dict[str, Any]:
        """Verifica la validez de un CFDI en el portal del SAT.

        Args:
            params: Debe contener 'uuid', 'rfc_emisor', 'rfc_receptor' y 'total'
        """
        uuid_val = params.get("uuid", "")
        rfc_emisor = params.get("rfc_emisor", "")
        rfc_receptor = params.get("rfc_receptor", "")
        if not uuid_val or not rfc_emisor or not rfc_receptor:
            return {"success": False, "error": "Parametros requeridos: uuid, rfc_emisor, rfc_receptor"}
        self._log_operation("verify_cfdi", f"uuid={uuid_val}")

        query_params: dict[str, Any] = {
            "uuid": uuid_val,
            "rfc_emisor": rfc_emisor,
            "rfc_receptor": rfc_receptor,
        }
        if params.get("total"):
            query_params["total"] = params["total"]

        try:
            resp = self._http.get("/cfdi/verify", params=query_params)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "uuid": uuid_val,
                    "estado": data.get("estado", "Vigente"),
                    "es_cancelable": data.get("es_cancelable", "No cancelable"),
                    "estatus_cancelacion": data.get("estatus_cancelacion", ""),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}


SAT_MEXICO_SCHEMA = ConnectorSchema(
    name="sat_mexico",
    version="1.0.0",
    description="Genera, timbra y consulta facturas CFDI del SAT Mexico",
    category="latam",
    icon="file-text",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="generate_cfdi", description="Genera un CFDI", category="write"),
        ActionDefinition(name="stamp_cfdi", description="Timbra un CFDI", category="write"),
        ActionDefinition(name="cancel_cfdi", description="Cancela un CFDI", category="write"),
        ActionDefinition(name="get_cfdi", description="Obtiene un CFDI", category="read"),
        ActionDefinition(name="get_cfdi_pdf", description="Obtiene PDF del CFDI", category="read"),
        ActionDefinition(name="verify_cfdi", description="Verifica validez del CFDI", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["pac_user", "pac_password", "rfc"], description="Credenciales PAC + RFC emisor")
    ],
)
