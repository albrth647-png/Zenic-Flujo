"""
MercadoPago Connector — Pagos, preferencias, webhooks
===========================================================

Sprint 6 del Roadmap Competitivo.
Conector para MercadoPago API vía requests.
Requiere MP_ACCESS_TOKEN configurado en Settings.
Enfocado en Latinoamérica.
"""

from __future__ import annotations

import time

from src.core.logging import setup_logging
from typing import Any

logger = setup_logging(__name__)


class MercadoPagoService:
    """
    Conector MercadoPago.

    Proporciona:
    - create_preference: Crear preferencia de pago (checkout pro)
    - get_payment: Consultar estado de un pago
    - search_payments: Buscar pagos
    - create_customer: Crear customer (card tokens)
    - process_webhook: Procesar notificación webhook

    Uso en workflow:
    {
        "tool": "mercadopago",
        "action": "create_preference",
        "params": {
            "access_token": "$settings.mp_access_token",
            "items": [
                {"title": "Producto", "quantity": 1, "unit_price": 100.0}
            ]
        }
    }
    """

    API_BASE = "https://api.mercadopago.com"

    def create_preference(
        self,
        access_token: str = "",
        items: list[dict] | None = None,
        external_reference: str = "",
        back_urls: dict[str, Any] | None = None,
        auto_return: str = "approved",
        notification_url: str = "",
        payer: dict[str, Any] | None = None,
        expires: bool = False,
        expiration_date_from: str = "",
        expiration_date_to: str = "",
        timeout: int = 30,
    ) -> dict[str, Any]:
        """
        Crea una preferencia de pago (Checkout Pro).

        Args:
            access_token: Access Token de MercadoPago
            items: Lista de items [{title, quantity, unit_price, ...}]
            external_reference: Referencia externa (ID de tu sistema)
            back_urls: URLs de retorno {success, failure, pending}
            auto_return: 'approved' | 'all' | 'none'
            notification_url: URL de webhook para notificaciones
            payer: Datos del pagador {name, email, ...}
            expires: Si la preferencia expira
            expiration_date_from: Inicio de expiración (ISO 8601)
            expiration_date_to: Fin de expiración (ISO 8601)
            timeout: Timeout

        Returns:
            dict con {id, init_point, sandbox_init_point, items, ...}
        """
        if not access_token:
            return self._error("Access token de MercadoPago requerido")
        if not items:
            return self._error("Items requeridos")

        start_time = time.time()

        payload: dict[str, Any] = {"items": items, "auto_return": auto_return}

        if external_reference:
            payload["external_reference"] = external_reference
        if back_urls:
            payload["back_urls"] = back_urls
        if notification_url:
            payload["notification_url"] = notification_url
        if payer:
            payload["payer"] = payer
        if expires:
            payload["expires"] = True
            if expiration_date_from:
                payload["expiration_date_from"] = expiration_date_from
            if expiration_date_to:
                payload["expiration_date_to"] = expiration_date_to

        try:
            import requests

            resp = requests.post(
                f"{self.API_BASE}/checkout/preferences",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )

            if resp.status_code not in (200, 201):
                error_data = resp.json()
                msg = error_data.get("message", str(error_data))
                return self._error(f"MercadoPago error: {msg}")

            data = resp.json()
            return {
                "id": data["id"],
                "init_point": data.get("init_point", ""),
                "sandbox_init_point": data.get("sandbox_init_point", ""),
                "items": data.get("items", items),
                "external_reference": data.get("external_reference", ""),
                "collector_id": data.get("collector_id"),
                "client_id": data.get("client_id"),
                "expires": data.get("expires", False),
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"MercadoPago preference error: {e}")
            return self._error(str(e))

    def get_payment(self, access_token: str = "", payment_id: int = 0, timeout: int = 15) -> dict[str, Any]:
        """
        Consulta el estado de un pago.

        Args:
            access_token: Access Token
            payment_id: ID del pago

        Returns:
            dict con {id, status, status_detail, amount, payer, ...}
        """
        if not access_token:
            return self._error("Access token requerido")
        if not payment_id:
            return self._error("Payment ID requerido")

        try:
            import requests

            resp = requests.get(
                f"{self.API_BASE}/v1/payments/{payment_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=timeout,
            )

            if resp.status_code != 200:
                return self._error(f"Error: {resp.text}")

            p = resp.json()
            return {
                "id": p.get("id"),
                "status": p.get("status"),
                "status_detail": p.get("status_detail"),
                "amount": p.get("transaction_amount", 0),
                "currency": p.get("currency_id", "ARS"),  # Foso 3: fix currency dinámico (antes hardcoded ARS)
                "payer": {
                    "email": p.get("payer", {}).get("email", ""),
                    "name": p.get("payer", {}).get("first_name", ""),
                },
                "payment_method": p.get("payment_method_id", ""),
                "external_reference": p.get("external_reference", ""),
                "description": p.get("description", ""),
                "fee": p.get("transaction_details", {}).get("total_fee_amount", 0),
                "net_amount": p.get("transaction_details", {}).get("net_received_amount", 0),
                "created": p.get("date_created", ""),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"MercadoPago payment error: {e}")
            return self._error(str(e))

    def search_payments(
        self,
        access_token: str = "",
        status: str | None = None,
        external_reference: str | None = None,
        limit: int = 20,
        offset: int = 0,
        timeout: int = 15,
    ) -> dict[str, Any]:
        """
        Busca pagos en MercadoPago.

        Args:
            access_token: Access Token
            status: Filtrar por estado (approved, pending, rejected, etc.)
            external_reference: Filtrar por referencia externa
            limit: Resultados por página
            offset: Desplazamiento

        Returns:
            dict con {results: [{id, status, amount, ...}], total, count}
        """
        if not access_token:
            return self._error("Access token requerido")

        params: dict[str, Any] = {"limit": min(limit, 50), "offset": offset}
        if status:
            params["status"] = status
        if external_reference:
            params["external_reference"] = external_reference

        try:
            import requests

            resp = requests.get(
                f"{self.API_BASE}/v1/payments/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=timeout,
            )

            if resp.status_code != 200:
                return self._error(f"Error: {resp.text}")

            data = resp.json()
            results = data.get("results", [])
            payments = [
                {
                    "id": p.get("id"),
                    "status": p.get("status"),
                    "status_detail": p.get("status_detail"),
                    "amount": p.get("transaction_amount", 0),
                    "payer_email": p.get("payer", {}).get("email", ""),
                    "external_reference": p.get("external_reference", ""),
                    "created": p.get("date_created", ""),
                }
                for p in results
            ]

            return {
                "payments": payments,
                "count": len(payments),
                "total": data.get("paging", {}).get("total", 0),
                "offset": offset,
                "limit": limit,
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"MercadoPago search error: {e}")
            return self._error(str(e))

    def create_customer(
        self,
        access_token: str = "",
        email: str = "",
        name: str = "",
        identification: dict[str, Any] | None = None,
        timeout: int = 15,
    ) -> dict[str, Any]:
        """
        Crea un customer en MercadoPago (para guardar tarjetas).

        Args:
            access_token: Access Token
            email: Email del cliente
            name: Nombre del cliente
            identification: {type: "DNI", number: "12345678"}

        Returns:
            dict con {id, email, name}
        """
        if not access_token:
            return self._error("Access token requerido")
        if not email:
            return self._error("Email requerido")

        payload: dict[str, Any] = {"email": email}
        if name:
            payload["first_name"] = name
        if identification:
            payload["identification"] = identification

        try:
            import requests

            resp = requests.post(
                f"{self.API_BASE}/v1/customers",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )

            if resp.status_code not in (200, 201):
                error_data = resp.json()
                msg = error_data.get("message", str(error_data))
                return self._error(f"MercadoPago error: {msg}")

            c = resp.json()
            return {
                "id": c.get("id"),
                "email": c.get("email", ""),
                "name": c.get("first_name", ""),
                "identification": c.get("identification"),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"MercadoPago customer error: {e}")
            return self._error(str(e))

    def process_webhook(self, access_token: str = "", notification_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Procesa una notificación webhook de MercadoPago.

        Recibe el payload del webhook y consulta el estado actual
        del pago/orden para confirmar.

        Args:
            access_token: Access Token
            notification_data: Payload del webhook

        Returns:
            dict con {action, type, resource_id, status, payment_data}
        """
        if not notification_data:
            return self._error("Datos de notificación requeridos")

        action = notification_data.get("action", "")
        resource_type = notification_data.get("type", "")
        resource_id = notification_data.get("data", {}).get("id")

        if not resource_id:
            return self._error("ID de recurso no encontrado en webhook")

        # Si es pago, consultar estado
        if resource_type == "payment":
            payment_data = self.get_payment(
                access_token=access_token,
                payment_id=int(resource_id),
            )
            return {
                "action": action,
                "type": resource_type,
                "resource_id": resource_id,
                "status": "processed",
                "payment_data": payment_data,
            }

        return {
            "action": action,
            "type": resource_type,
            "resource_id": resource_id,
            "status": "acknowledged",
        }

    @staticmethod
    def _error(message: str) -> dict[str, Any]:
        return {"error": message, "status": "failed"}

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

    @staticmethod
    def get_tool_definition() -> dict[str, Any]:
        return {
            "tool": "mercadopago",
            "name": "MercadoPago",
            "description": "Pagos online para Latinoamérica",
            "actions": {
                "create_preference": {
                    "name": "Crear preferencia",
                    "description": "Crea link de pago Checkout Pro",
                    "params": [
                        {"name": "items", "type": "list", "required": True, "label": "Items"},
                        {"name": "external_reference", "type": "string", "default": "", "label": "Referencia externa"},
                        {"name": "notification_url", "type": "string", "default": "", "label": "URL de notificación"},
                    ],
                },
                "get_payment": {
                    "name": "Consultar pago",
                    "description": "Estado de un pago",
                    "params": [
                        {"name": "payment_id", "type": "number", "required": True, "label": "ID del pago"},
                    ],
                },
                "search_payments": {
                    "name": "Buscar pagos",
                    "params": [
                        {"name": "status", "type": "string", "default": "", "label": "Estado"},
                    ],
                },
            },
        }
