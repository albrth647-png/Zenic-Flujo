"""
Conectores Enterprise — Registro de 60 Conectores del Marketplace
===================================================================

Registro completo de todos los conectores en el ConnectorRegistry.

Fix Sprint 2 bug #17: se añadieron 10 conectores orphaned que tenían archivo
.py completo pero NO estaban en _ALL_CONNECTORS ni importados aquí. Total: 60
conectores registrados automáticamente (antes 50).
"""

from __future__ import annotations

from src.connectors.afip_argentina import AFIPArgentinaConnector
from src.connectors.airtable import AirtableConnector
from src.connectors.anthropic import AnthropicConnector
from src.connectors.asana import AsanaConnector
from src.connectors.aws_s3 import AwsS3Connector
from src.connectors.azure_ad import AzureADConnector
from src.connectors.azure_blob import AzureBlobConnector
from src.connectors.confluence import ConfluenceConnector
from src.connectors.datadog import DatadogConnector
from src.connectors.deepseek import DeepseekConnector
from src.connectors.dian_colombia import DIANColombiaConnector
from src.connectors.discord import DiscordConnector
from src.connectors.dropbox import DropboxConnector
from src.connectors.dte_chile import DTEChileConnector
from src.connectors.elastic import ElasticConnector
from src.connectors.freshdesk import FreshdeskConnector
from src.connectors.gcs import GcsConnector
from src.connectors.github import GithubConnector
from src.connectors.gitlab import GitlabConnector
from src.connectors.grafana import GrafanaConnector
from src.connectors.hubspot import HubspotConnector
from src.connectors.huggingface import HuggingfaceConnector
from src.connectors.intercom import IntercomConnector
from src.connectors.jira import JiraConnector
from src.connectors.mailchimp import MailchimpConnector
from src.connectors.mailgun import MailgunConnector
from src.connectors.marketo import MarketoConnector
from src.connectors.mercadolibre import MercadolibreConnector
from src.connectors.monday import MondayConnector
from src.connectors.mongo_connector import MongoConnectorConnector
from src.connectors.mysql_connector import MysqlConnectorConnector
from src.connectors.new_relic import NewRelicConnector
from src.connectors.nfe import NfeConnector
from src.connectors.notion import NotionConnector
from src.connectors.okta import OktaConnector
from src.connectors.openai_v2 import OpenaiV2Connector
from src.connectors.pagerduty import PagerDutyConnector
from src.connectors.paypal import PaypalConnector
from src.connectors.pipedrive import PipedriveConnector
from src.connectors.pix_brazil import PixBrazilConnector
from src.connectors.quickbooks import QuickbooksConnector
from src.connectors.salesforce import SalesforceConnector
from src.connectors.sat_mexico import SatMexicoConnector
from src.connectors.sendgrid import SendGridConnector
from src.connectors.sentry import SentryConnector
from src.connectors.shopify import ShopifyConnector
from src.connectors.splunk import SplunkConnector
from src.connectors.square import SquareConnector
from src.connectors.sri_ecuador import SRIEcuadorConnector
from src.connectors.sumologic import SumoLogicConnector
from src.connectors.sunat_peru import SUNATPeruConnector
from src.connectors.teams import TeamsConnector
from src.connectors.totvs import TotvsConnector
from src.connectors.trello import TrelloConnector
from src.connectors.twilio import TwilioConnector
from src.connectors.typeform import TypeformConnector
from src.connectors.vault import VaultConnector
from src.connectors.whatsapp import WhatsAppConnector
from src.connectors.wise import WiseConnector
from src.connectors.woocommerce import WooCommerceConnector
from src.connectors.xero import XeroConnector
from src.connectors.zendesk import ZendeskConnector
from src.connectors.zoho_crm import ZohoCrmConnector
from src.sdk.registry import ConnectorRegistry

# Todos los conectores registrados (60 total — RuvConnector removido en Fase 2B)
_ALL_CONNECTORS: list[type] = [
    # AI & Data (4)
    AnthropicConnector,
    DeepseekConnector,
    HuggingfaceConnector,
    OpenaiV2Connector,
    # Cloud Storage (4)
    AwsS3Connector,
    AzureBlobConnector,
    DropboxConnector,
    GcsConnector,
    # Communication (7)
    DiscordConnector,
    IntercomConnector,
    MailgunConnector,
    SendGridConnector,
    TeamsConnector,
    TwilioConnector,
    WhatsAppConnector,
    # CRM & Sales (4)
    HubspotConnector,
    PipedriveConnector,
    SalesforceConnector,
    ZohoCrmConnector,
    # Databases (3)
    ElasticConnector,
    MongoConnectorConnector,
    MysqlConnectorConnector,
    # DevOps & Monitoring (8) — incluye Grafana y Splunk añadidos (fix #17)
    DatadogConnector,
    GithubConnector,
    GitlabConnector,
    GrafanaConnector,
    NewRelicConnector,
    PagerDutyConnector,
    SentryConnector,
    SplunkConnector,
    # E-commerce (2) — incluye Shopify (fix #17)
    ShopifyConnector,
    WooCommerceConnector,
    # ERP (1)
    TotvsConnector,
    # Finance & Payments (5) — incluye Xero (fix #17)
    PaypalConnector,
    PixBrazilConnector,
    QuickbooksConnector,
    SquareConnector,
    WiseConnector,
    XeroConnector,
    # Forms (1)
    TypeformConnector,
    # Identity (2) — incluye Okta (fix #17)
    AzureADConnector,
    OktaConnector,
    # LATAM (8) — incluye AFIP Argentina y DTE Chile (fix #17). RuvConnector removido en Fase 2B.
    # Fase 2C: añade DIAN Colombia, SUNAT Perú, SRI Ecuador con crypto REAL.
    AFIPArgentinaConnector,
    DTEChileConnector,
    DIANColombiaConnector,
    MercadolibreConnector,
    NfeConnector,
    SatMexicoConnector,
    SRIEcuadorConnector,
    SUNATPeruConnector,
    # Marketing (2) — incluye Mailchimp (fix #17)
    MailchimpConnector,
    MarketoConnector,
    # Monitoring & Logging (1)
    SumoLogicConnector,
    # No-code Database (1)
    AirtableConnector,
    # Project Management (6) — incluye Monday (fix #17)
    AsanaConnector,
    ConfluenceConnector,
    JiraConnector,
    MondayConnector,
    NotionConnector,
    TrelloConnector,
    # Security (1)
    VaultConnector,
    # Support (2) — incluye Zendesk (fix #17)
    FreshdeskConnector,
    ZendeskConnector,
]


def register_all_connectors() -> list[str]:
    """Registra todos los conectores enterprise en el ConnectorRegistry.

    Retorna:
        Lista de nombres de conectores registrados exitosamente
    """
    registered: list[str] = []
    registry = ConnectorRegistry()
    for connector_cls in _ALL_CONNECTORS:
        try:
            registry.register(connector_cls, override=True)
            registered.append(connector_cls.name)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Error registrando {connector_cls.__name__}: {e}")
    return registered


# Auto-registro al importar el modulo
register_all_connectors()

__all__ = [
    "AFIPArgentinaConnector",
    "AirtableConnector",
    "AnthropicConnector",
    "AsanaConnector",
    "AwsS3Connector",
    "AzureADConnector",
    "AzureBlobConnector",
    "ConfluenceConnector",
    "DTEChileConnector",
    "DatadogConnector",
    "DeepseekConnector",
    "DiscordConnector",
    "DropboxConnector",
    "ElasticConnector",
    "FreshdeskConnector",
    "GcsConnector",
    "GithubConnector",
    "GitlabConnector",
    "GrafanaConnector",
    "HubspotConnector",
    "HuggingfaceConnector",
    "IntercomConnector",
    "JiraConnector",
    "MailchimpConnector",
    "MailgunConnector",
    "MarketoConnector",
    "MercadolibreConnector",
    "MondayConnector",
    "MongoConnectorConnector",
    "MysqlConnectorConnector",
    "NewRelicConnector",
    "NfeConnector",
    "NotionConnector",
    "OktaConnector",
    "OpenaiV2Connector",
    "PagerDutyConnector",
    "PaypalConnector",
    "PipedriveConnector",
    "PixBrazilConnector",
    "QuickbooksConnector",
    "SalesforceConnector",
    "SatMexicoConnector",
    "SendGridConnector",
    "SentryConnector",
    "ShopifyConnector",
    "SplunkConnector",
    "SquareConnector",
    "SumoLogicConnector",
    "TeamsConnector",
    "TotvsConnector",
    "TrelloConnector",
    "TwilioConnector",
    "TypeformConnector",
    "VaultConnector",
    "WhatsAppConnector",
    "WiseConnector",
    "WooCommerceConnector",
    "XeroConnector",
    "ZendeskConnector",
    "ZohoCrmConnector",
    "register_all_connectors",
]
