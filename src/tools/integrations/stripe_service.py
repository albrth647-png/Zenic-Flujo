"""
Stripe Connector — Pagos, clientes, suscripciones
======================================================

Sprint 6 del Roadmap Competitivo.
Conector para Stripe API vía requests.
Requiere STRIPE_SECRET_KEY configurada en Settings.
"""

from __future__ import annotations

import base64
import time

from src.utils.logger import setup_logging
from typing import Any

logger = setup_logging(__name__)


class StripeService:
    """
    Conector Stripe.

    Proporciona:
    - create_payment_intent: Crear intención de pago
    - create_customer: Crear cliente
    - list_customers: Listar clientes
    - create_subscription: Crear suscripción
    - list_invoices: Listar facturas
    - create_payment_link: Crear link de pago
    - retrieve_payment_intent: Consultar estado de pago

    Uso en workflow:
    {
        "tool": "stripe",
        "action": "create_payment_intent",
        "params": {
            "secret_key": "$settings.stripe_secret_key",
            "amount": 5000,
            "currency": "usd"
        }
    }
    """

    API_BASE = "https://api.stripe.com/v1"

    @staticmethod
    def _auth_header(secret_key: str) -> dict[str, Any]:
        """Genera header de autenticación Basic con la secret key."""
        encoded = base64.b64encode(f"{secret_key}:".encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    def create_payment_intent(
        self,
        secret_key: str = "",
        amount: int = 0,
        currency: str = "usd",
        customer_id: str | None = None,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """
        Crea una intención de pago.

        Args:
            secret_key: Stripe Secret Key
            amount: Monto en centavos (5000 = $50.00)
            currency: Moneda (usd, mxn, eur, etc.)
            customer_id: ID de cliente existente (opcional)
            description: Descripción del pago
            metadata: Metadatos adicionales
            timeout: Timeout

        Returns:
            dict con {id, amount, currency, status, client_secret, ...}
        """
        if not secret_key:
            return self._error("Stripe secret key requerida")
        if amount <= 0:
            return self._error("Amount debe ser > 0")

        start_time = time.time()

        data = {
            "amount": amount,
            "currency": currency,
            "description": description or "",
        }
        if customer_id:
            data["customer"] = customer_id
        if metadata:
            data["metadata"] = metadata

        try:
            import requests

            resp = requests.post(
                f"{self.API_BASE}/payment_intents",
                headers=self._auth_header(secret_key),
                data=data,
                timeout=timeout,
            )

            if resp.status_code != 200:
                error_body = resp.json()
                return self._error(error_body.get("error", {}).get("message", str(resp.text)))

            pi = resp.json()
            return {
                "id": pi["id"],
                "amount": pi["amount"],
                "currency": pi["currency"],
                "status": pi["status"],
                "client_secret": pi.get("client_secret", ""),
                "customer_id": pi.get("customer"),
                "description": pi.get("description", ""),
                "created": pi.get("created", 0),
                "payment_method": pi.get("payment_method"),
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"Stripe PI error: {e}")
            return self._error(str(e))

    def retrieve_payment_intent(self, secret_key: str = "", payment_intent_id: str = "", timeout: int = 15) -> dict[str, Any]:
        """
        Consulta el estado de una intención de pago.

        Args:
            secret_key: Stripe Secret Key
            payment_intent_id: ID del PaymentIntent

        Returns:
            dict con estado actual del pago
        """
        if not secret_key:
            return self._error("Stripe secret key requerida")
        if not payment_intent_id:
            return self._error("PaymentIntent ID requerido")

        try:
            import requests

            resp = requests.get(
                f"{self.API_BASE}/payment_intents/{payment_intent_id}",
                headers=self._auth_header(secret_key),
                timeout=timeout,
            )

            if resp.status_code != 200:
                return self._error(f"Error: {resp.text}")

            pi = resp.json()
            return {
                "id": pi["id"],
                "amount": pi["amount"],
                "currency": pi["currency"],
                "status": pi["status"],
                "customer_id": pi.get("customer"),
                "description": pi.get("description", ""),
                "payment_method": pi.get("payment_method"),
                "charges": pi.get("charges", {}).get("data", []),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            return self._error(str(e))

    def create_customer(
        self,
        secret_key: str = "",
        email: str = "",
        name: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
        timeout: int = 15,
    ) -> dict[str, Any]:
        """
        Crea un cliente en Stripe.

        Args:
            secret_key: Stripe Secret Key
            email: Email del cliente
            name: Nombre del cliente
            description: Descripción
            metadata: Metadatos

        Returns:
            dict con {id, email, name, created}
        """
        if not secret_key:
            return self._error("Stripe secret key requerida")
        if not email and not name:
            return self._error("Email o name requerido")

        data = {}
        if email:
            data["email"] = email
        if name:
            data["name"] = name
        if description:
            data["description"] = description
        if metadata:
            data["metadata"] = metadata

        try:
            import requests

            resp = requests.post(
                f"{self.API_BASE}/customers",
                headers=self._auth_header(secret_key),
                data=data,
                timeout=timeout,
            )

            if resp.status_code != 200:
                error_body = resp.json()
                return self._error(error_body.get("error", {}).get("message", str(resp.text)))

            c = resp.json()
            return {
                "id": c["id"],
                "email": c.get("email", ""),
                "name": c.get("name", ""),
                "description": c.get("description", ""),
                "created": c.get("created", 0),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"Stripe customer error: {e}")
            return self._error(str(e))

    def list_customers(
        self, secret_key: str = "", limit: int = 10, email: str | None = None, timeout: int = 15
    ) -> dict[str, Any]:
        """
        Lista clientes en Stripe.

        Args:
            secret_key: Stripe Secret Key
            limit: Máximo de resultados
            email: Filtrar por email

        Returns:
            dict con {customers: [{id, email, name, created}], count}
        """
        if not secret_key:
            return self._error("Stripe secret key requerida")

        params = {"limit": min(limit, 100)}
        if email:
            params["email"] = email

        try:
            import requests

            resp = requests.get(
                f"{self.API_BASE}/customers",
                headers=self._auth_header(secret_key),
                params=params,
                timeout=timeout,
            )

            if resp.status_code != 200:
                return self._error(f"Error: {resp.text}")

            data = resp.json()
            customers = [
                {
                    "id": c["id"],
                    "email": c.get("email", ""),
                    "name": c.get("name", ""),
                    "created": c.get("created", 0),
                }
                for c in data.get("data", [])
            ]
            return {"customers": customers, "count": len(customers)}

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"Stripe list customers error: {e}")
            return self._error(str(e))

    def create_subscription(
        self,
        secret_key: str = "",
        customer_id: str = "",
        price_id: str = "",
        trial_days: int = 0,
        metadata: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """
        Crea una suscripción para un cliente.

        Args:
            secret_key: Stripe Secret Key
            customer_id: ID del cliente
            price_id: ID del price en Stripe
            trial_days: Días de prueba gratis
            metadata: Metadatos

        Returns:
            dict con {id, status, current_period_start, current_period_end}
        """
        if not secret_key:
            return self._error("Stripe secret key requerida")
        if not customer_id:
            return self._error("Customer ID requerido")
        if not price_id:
            return self._error("Price ID requerido")

        data = {
            "customer": customer_id,
            "items[0][price]": price_id,
        }
        if trial_days > 0:
            data["trial_period_days"] = trial_days
        if metadata:
            for k, v in metadata.items():
                data[f"metadata[{k}]"] = v

        try:
            import requests

            resp = requests.post(
                f"{self.API_BASE}/subscriptions",
                headers=self._auth_header(secret_key),
                data=data,
                timeout=timeout,
            )

            if resp.status_code != 200:
                error_body = resp.json()
                return self._error(error_body.get("error", {}).get("message", str(resp.text)))

            s = resp.json()
            return {
                "id": s["id"],
                "status": s["status"],
                "customer_id": s.get("customer"),
                "current_period_start": s.get("current_period_start", 0),
                "current_period_end": s.get("current_period_end", 0),
                "plan": s.get("plan", {}),
                "created": s.get("created", 0),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"Stripe subscription error: {e}")
            return self._error(str(e))

    def list_invoices(
        self, secret_key: str = "", customer_id: str | None = None, limit: int = 10, timeout: int = 15
    ) -> dict[str, Any]:
        """
        Lista facturas de Stripe.

        Args:
            secret_key: Stripe Secret Key
            customer_id: Filtrar por cliente
            limit: Máximo de resultados

        Returns:
            dict con {invoices: [{id, number, amount, status, ...}], count}
        """
        if not secret_key:
            return self._error("Stripe secret key requerida")

        params = {"limit": min(limit, 100)}
        if customer_id:
            params["customer"] = customer_id

        try:
            import requests

            resp = requests.get(
                f"{self.API_BASE}/invoices",
                headers=self._auth_header(secret_key),
                params=params,
                timeout=timeout,
            )

            if resp.status_code != 200:
                return self._error(f"Error: {resp.text}")

            data = resp.json()
            invoices = [
                {
                    "id": inv["id"],
                    "number": inv.get("number", ""),
                    "amount": inv.get("amount_due", 0),
                    "currency": inv.get("currency", ""),
                    "status": inv.get("status", ""),
                    "customer_id": inv.get("customer"),
                    "created": inv.get("created", 0),
                    "paid": inv.get("paid", False),
                    "pdf_url": inv.get("invoice_pdf", ""),
                }
                for inv in data.get("data", [])
            ]
            return {"invoices": invoices, "count": len(invoices)}

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"Stripe invoices error: {e}")
            return self._error(str(e))

    def create_payment_link(
        self,
        secret_key: str = "",
        amount: int = 0,
        currency: str = "usd",
        description: str = "",
        quantity: int = 1,
        metadata: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """
        Crea un link de pago (vía price + payment link).

        Args:
            secret_key: Stripe Secret Key
            amount: Monto en centavos
            currency: Moneda
            description: Descripción
            quantity: Cantidad
            metadata: Metadatos

        Returns:
            dict con {id, url, status}
        """
        if not secret_key:
            return self._error("Stripe secret key requerida")
        if amount <= 0:
            return self._error("Amount debe ser > 0")

        start_time = time.time()

        try:
            import requests

            # 1. Crear product temporal
            product_resp = requests.post(
                f"{self.API_BASE}/products",
                headers=self._auth_header(secret_key),
                data={
                    "name": description or f"Pago de {amount} {currency}",
                },
                timeout=timeout,
            )
            if product_resp.status_code != 200:
                return self._error(f"Error creating product: {product_resp.text}")
            product = product_resp.json()
            product_id = product["id"]

            # 2. Crear price
            price_resp = requests.post(
                f"{self.API_BASE}/prices",
                headers=self._auth_header(secret_key),
                data={
                    "product": product_id,
                    "unit_amount": str(amount),
                    "currency": currency,
                },
                timeout=timeout,
            )
            if price_resp.status_code != 200:
                return self._error(f"Error creating price: {price_resp.text}")
            price = price_resp.json()
            price_id = price["id"]

            # 3. Crear payment link
            pl_data = {
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": quantity,
            }
            if metadata:
                for k, v in metadata.items():
                    pl_data[f"metadata[{k}]"] = v

            pl_resp = requests.post(
                f"{self.API_BASE}/payment_links",
                headers=self._auth_header(secret_key),
                data=pl_data,
                timeout=timeout,
            )

            if pl_resp.status_code != 200:
                return self._error(f"Error creating payment link: {pl_resp.text}")

            payment_link = pl_resp.json()
            return {
                "id": payment_link["id"],
                "url": payment_link.get("url", ""),
                "status": "active",
                "amount": amount,
                "currency": currency,
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"Stripe payment link error: {e}")
            return self._error(str(e))

    @staticmethod
    def _error(message: str) -> dict[str, Any]:
        return {"error": message, "status": "failed"}

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

    @staticmethod
    def get_tool_definition() -> dict[str, Any]:
        return {
            "tool": "stripe",
            "name": "Stripe",
            "description": "Pagos, clientes y suscripciones con Stripe",
            "actions": {
                "create_payment_intent": {
                    "name": "Crear pago",
                    "params": [
                        {"name": "amount", "type": "number", "required": True, "label": "Monto (centavos)"},
                        {"name": "currency", "type": "string", "default": "usd", "label": "Moneda"},
                    ],
                },
                "list_customers": {
                    "name": "Listar clientes",
                    "params": [
                        {"name": "limit", "type": "number", "default": 10, "label": "Límite"},
                    ],
                },
                "create_subscription": {
                    "name": "Crear suscripción",
                    "params": [
                        {"name": "customer_id", "type": "string", "required": True, "label": "Cliente ID"},
                        {"name": "price_id", "type": "string", "required": True, "label": "Price ID"},
                    ],
                },
            },
        }
