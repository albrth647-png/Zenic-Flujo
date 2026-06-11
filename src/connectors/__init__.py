"""
Conectores Enterprise — Registro de los 35 Conectores del Marketplace
========================================================================

Este modulo importa y registra todos los conectores enterprise
en el ConnectorRegistry del SDK de Zenic-Flijo.

Categorias:
    - Communication (5): Twilio, SendGrid, Discord, Teams, Intercom
    - Cloud Storage (4): AWS S3, GCS, Azure Blob, Dropbox
    - CRM & Sales (4): HubSpot, Salesforce, Pipedrive, Zoho CRM
    - Finance & Payments (4): PayPal, Square, Wise, QuickBooks
    - Databases (3): MySQL, MongoDB, Elasticsearch
    - Project Management (3): Jira, Asana, Notion
    - LATAM (4): MercadoLibre, SAT Mexico, Pix Brazil, RUV Chile
    - AI & Data (4): OpenAI v2, Anthropic, HuggingFace, DeepSeek
    - DevOps & Monitoring (4): GitHub, GitLab, Sentry, Datadog
"""

from __future__ import annotations

from src.sdk.registry import ConnectorRegistry

# Communication
from src.connectors.twilio import TwilioConnector
from src.connectors.sendgrid import SendGridConnector
from src.connectors.discord import DiscordConnector
from src.connectors.teams import TeamsConnector
from src.connectors.intercom import IntercomConnector

# Cloud Storage
from src.connectors.aws_s3 import AwsS3Connector
from src.connectors.gcs import GcsConnector
from src.connectors.azure_blob import AzureBlobConnector
from src.connectors.dropbox import DropboxConnector

# CRM & Sales
from src.connectors.hubspot import HubspotConnector
from src.connectors.salesforce import SalesforceConnector
from src.connectors.pipedrive import PipedriveConnector
from src.connectors.zoho_crm import ZohoCrmConnector

# Finance & Payments
from src.connectors.paypal import PaypalConnector
from src.connectors.square import SquareConnector
from src.connectors.wise import WiseConnector
from src.connectors.quickbooks import QuickbooksConnector

# Databases
from src.connectors.mysql_connector import MysqlConnectorConnector
from src.connectors.mongo_connector import MongoConnectorConnector
from src.connectors.elastic import ElasticConnector

# Project Management
from src.connectors.jira import JiraConnector
from src.connectors.asana import AsanaConnector
from src.connectors.notion import NotionConnector

# LATAM
from src.connectors.mercadolibre import MercadolibreConnector
from src.connectors.sat_mexico import SatMexicoConnector
from src.connectors.pix_brazil import PixBrazilConnector
from src.connectors.ruv import RuvConnector

# AI & Data
from src.connectors.openai_v2 import OpenaiV2Connector
from src.connectors.anthropic import AnthropicConnector
from src.connectors.huggingface import HuggingfaceConnector
from src.connectors.deepseek import DeepseekConnector

# DevOps & Monitoring
from src.connectors.github import GithubConnector
from src.connectors.gitlab import GitlabConnector
from src.connectors.sentry import SentryConnector
from src.connectors.datadog import DatadogConnector

# Registrar todos los conectores en el ConnectorRegistry
_ALL_CONNECTORS: list[type] = [
    # Communication
    TwilioConnector,
    SendGridConnector,
    DiscordConnector,
    TeamsConnector,
    IntercomConnector,
    # Cloud Storage
    AwsS3Connector,
    GcsConnector,
    AzureBlobConnector,
    DropboxConnector,
    # CRM & Sales
    HubspotConnector,
    SalesforceConnector,
    PipedriveConnector,
    ZohoCrmConnector,
    # Finance & Payments
    PaypalConnector,
    SquareConnector,
    WiseConnector,
    QuickbooksConnector,
    # Databases
    MysqlConnectorConnector,
    MongoConnectorConnector,
    ElasticConnector,
    # Project Management
    JiraConnector,
    AsanaConnector,
    NotionConnector,
    # LATAM
    MercadolibreConnector,
    SatMexicoConnector,
    PixBrazilConnector,
    RuvConnector,
    # AI & Data
    OpenaiV2Connector,
    AnthropicConnector,
    HuggingfaceConnector,
    DeepseekConnector,
    # DevOps & Monitoring
    GithubConnector,
    GitlabConnector,
    SentryConnector,
    DatadogConnector,
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
    "AnthropicConnector",
    "AsanaConnector",
    "AwsS3Connector",
    "AzureBlobConnector",
    "DatadogConnector",
    "DeepseekConnector",
    "DiscordConnector",
    "DropboxConnector",
    "ElasticConnector",
    "GithubConnector",
    "GitlabConnector",
    "GcsConnector",
    "HuggingfaceConnector",
    "HubspotConnector",
    "IntercomConnector",
    "JiraConnector",
    "MercadolibreConnector",
    "MongoConnectorConnector",
    "MysqlConnectorConnector",
    "NotionConnector",
    "OpenaiV2Connector",
    "PaypalConnector",
    "PipedriveConnector",
    "PixBrazilConnector",
    "QuickbooksConnector",
    "RuvConnector",
    "SatMexicoConnector",
    "SalesforceConnector",
    "SendGridConnector",
    "SentryConnector",
    "SquareConnector",
    "TeamsConnector",
    "TwilioConnector",
    "WiseConnector",
    "ZohoCrmConnector",
    "register_all_connectors",
]
