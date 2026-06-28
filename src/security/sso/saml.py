"""
SSO — SAML 2.0 Handler: metadata, login, callback, attribute extraction, conditions validation.
"""

from __future__ import annotations

import base64
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from typing import Any

from src.data.database_manager import DatabaseManager
from src.data.redis_service import RedisService
from src.security.sso.constants import SAML_NS, SSO_BASE_URL
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class SAMLHandler:
    """Maneja operaciones SAML 2.0: metadata, autenticacion y validacion."""

    def __init__(self, db: DatabaseManager, redis: RedisService):
        self._db = db
        self._redis = redis

    def generate_sp_metadata(self, config: dict[str, Any], provider_name: str) -> str:
        """Genera el metadata XML del Service Provider."""
        entity_id = config.get("entity_id", f"{SSO_BASE_URL}/api/v1/auth/saml/{provider_name}/callback")
        acs_url = config.get("acs_url", f"{SSO_BASE_URL}/api/v1/auth/saml/{provider_name}/callback")

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{entity_id}">
  <md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>
    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified</md:NameIDFormat>
    <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                 Location="{acs_url}"
                                 index="0" isDefault="true"/>
    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                            Location="{SSO_BASE_URL}/api/v1/auth/sso/logout"/>
  </md:SPSSODescriptor>
  <md:Organization>
    <md:OrganizationName xml:lang="en">Zenic-Flijo</md:OrganizationName>
    <md:OrganizationDisplayName xml:lang="en">Zenic-Flijo Workflow Platform</md:OrganizationDisplayName>
    <md:OrganizationURL xml:lang="en">{SSO_BASE_URL}</md:OrganizationURL>
  </md:Organization>
</md:EntityDescriptor>"""

    def initiate_login(self, config: dict[str, Any], provider_name: str) -> dict[str, Any]:
        """Inicia el flujo de login SAML generando un AuthnRequest."""
        idp_sso_url = config.get("idp_sso_url", "")
        if not idp_sso_url:
            return {"status": "error", "message": "IdP SSO URL no configurada"}

        request_id = f"id_{uuid.uuid4().hex}"
        issue_instant = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        entity_id = config.get("entity_id", f"{SSO_BASE_URL}/api/v1/auth/saml/{provider_name}/callback")
        acs_url = config.get("acs_url", f"{SSO_BASE_URL}/api/v1/auth/saml/{provider_name}/callback")

        authn_request = f"""<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                        xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                        ID="{request_id}"
                        Version="2.0"
                        IssueInstant="{issue_instant}"
                        AssertionConsumerServiceURL="{acs_url}"
                        Destination="{idp_sso_url}">
  <saml:Issuer>{entity_id}</saml:Issuer>
  <samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
                      AllowCreate="true"/>
</samlp:AuthnRequest>"""

        encoded_request = base64.b64encode(authn_request.encode("utf-8")).decode("ascii")
        redirect_url = f"{idp_sso_url}?SAMLRequest={urllib.parse.quote(encoded_request)}"

        self._redis.set_json(
            f"sso:saml:request:{request_id}",
            {"provider": provider_name, "created_at": time.time()},
            ttl=300,
        )

        logger.info(f"SSO SAML: Login iniciado para proveedor '{provider_name}' (request_id={request_id})")
        return {"status": "ok", "redirect_url": redirect_url, "request_id": request_id}

    def handle_callback(self, config: dict[str, Any], saml_response: str) -> dict[str, Any]:
        """Procesa la respuesta SAML del IdP."""
        try:
            decoded_xml = base64.b64decode(saml_response).decode("utf-8")
        except Exception as e:
            logger.error(f"SSO SAML: Error decodificando respuesta: {e}")
            return {"status": "error", "message": "Respuesta SAML invalida (decodificacion)"}

        try:
            root = ET.fromstring(decoded_xml)
            user_info = self._extract_attributes(root, config)
        except ET.ParseError as e:
            logger.error(f"SSO SAML: Error parseando XML: {e}")
            return {"status": "error", "message": "Respuesta SAML invalida (XML)"}

        if not user_info.get("external_id"):
            return {"status": "error", "message": "No se pudo identificar al usuario en la respuesta SAML"}

        validation = self._validate_conditions(root, config)
        if not validation["valid"]:
            return {"status": "error", "message": validation["message"]}

        return {"status": "ok", "user_info": user_info}

    def _extract_attributes(self, root: ET.Element, config: dict[str, Any]) -> dict[str, Any]:
        """Extrae atributos del usuario desde una asercion SAML."""
        user_info: dict[str, Any] = {}

        name_id_elements = root.findall(".//saml:NameID", SAML_NS)
        if name_id_elements:
            user_info["external_id"] = name_id_elements[0].text or ""
            user_info["name_id_format"] = name_id_elements[0].get("Format", "")

        attributes = root.findall(".//saml:Attribute", SAML_NS)
        for attr in attributes:
            attr_name = attr.get("Name", "")
            values = attr.findall("saml:AttributeValue", SAML_NS)
            if len(values) == 1:
                user_info[attr_name] = values[0].text or ""
            elif len(values) > 1:
                user_info[attr_name] = [v.text or "" for v in values]

        attr_map = config.get("attribute_map", {})
        mapped: dict[str, str] = {}
        for target_key, source_key in attr_map.items():
            if source_key in user_info:
                mapped[target_key] = user_info[source_key]

        if "email" not in mapped:
            mapped["email"] = (
                user_info.get("urn:oid:0.9.2342.19200300.100.1.3")
                or user_info.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress")
                or user_info.get("email") or user_info.get("Email") or ""
            )
        if "display_name" not in mapped:
            mapped["display_name"] = (
                user_info.get("urn:oid:2.16.840.1.113730.3.1.241")
                or user_info.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name")
                or user_info.get("displayName") or user_info.get("name") or ""
            )
        if "first_name" not in mapped:
            mapped["first_name"] = (
                user_info.get("urn:oid:2.5.4.42")
                or user_info.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname")
                or user_info.get("firstName") or ""
            )
        if "last_name" not in mapped:
            mapped["last_name"] = (
                user_info.get("urn:oid:2.5.4.4")
                or user_info.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname")
                or user_info.get("lastName") or ""
            )

        mapped["external_id"] = user_info.get("external_id", mapped.get("email", ""))
        return mapped

    def _validate_conditions(self, root: ET.Element, config: dict[str, Any]) -> dict[str, Any]:
        """Valida las condiciones de una asercion SAML."""
        conditions = root.findall(".//saml:Conditions", SAML_NS)
        if not conditions:
            return {"valid": True, "message": "Sin condiciones explicitas"}

        for condition in conditions:
            not_on_or_after = condition.get("NotOnOrAfter")
            if not_on_or_after:
                try:
                    from datetime import datetime
                    expiry = datetime.fromisoformat(not_on_or_after.replace("Z", "+00:00"))
                    if datetime.now(expiry.tzinfo) >= expiry:
                        return {"valid": False, "message": "Asercion SAML expirada"}
                except (ValueError, TypeError):
                    pass

            audiences = condition.findall(".//saml:Audience", SAML_NS)
            if audiences:
                entity_id = config.get("entity_id", "")
                valid_audience = any(aud.text == entity_id for aud in audiences if aud.text)
                if not valid_audience and entity_id:
                    return {"valid": False, "message": "Audience SAML no coincide con entity_id del SP"}

        return {"valid": True, "message": "Condiciones validas"}
