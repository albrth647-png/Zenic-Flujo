"""HAT Level 5 — Conectores externos registrados como tools de HAT.

Registra los 61 conectores de src/connectors/ como ToolRegistration
entries en el _REGISTRY de HAT Level 5. Esto permite que HAT
rutee mensajes a los conectores via Supervisor → Specialist → Worker.

Los conectores usan src.sdk.BaseConnector — no son tools nativas de Level 5,
pero ToolRegistration las instancia igual via importlib.

Clasificación por dominio:
- operaciones (20): CRM, payments, e-commerce, ERP, fiscal
- comunicaciones (11): email, chat, messaging, helpdesk
- datos_auto (30): devops, monitoring, storage, AI, project management

Total: 61 conectores + 19 tools nativas = 80 tools en HAT.
"""
from __future__ import annotations

# Cada entrada es: (name, domain, category, import_path, class_name, requires_event_bus)
CONNECTORS_REGISTRY: list[tuple[str, str, str, str, str, bool]] = [
    # === OPERACIONES (20 conectores) ===
    # CRM / Sales
    ("salesforce", "operaciones", "business",
     "src.connectors.salesforce", "SalesforceConnector", False),
    ("hubspot", "operaciones", "business",
     "src.connectors.hubspot", "HubspotConnector", False),
    ("pipedrive", "operaciones", "business",
     "src.connectors.pipedrive", "PipedriveConnector", False),
    ("zoho_crm", "operaciones", "business",
     "src.connectors.zoho_crm", "ZohoCrmConnector", False),
    ("marketo", "operaciones", "business",
     "src.connectors.marketo", "MarketoConnector", False),
    # E-commerce
    ("shopify", "operaciones", "business",
     "src.connectors.shopify", "ShopifyConnector", False),
    ("woocommerce", "operaciones", "business",
     "src.connectors.woocommerce", "WooCommerceConnector", False),
    ("mercadolibre", "operaciones", "business",
     "src.connectors.mercadolibre", "MercadolibreConnector", False),
    # Payments
    ("paypal", "operaciones", "payments",
     "src.connectors.paypal", "PaypalConnector", False),
    ("wise", "operaciones", "payments",
     "src.connectors.wise", "WiseConnector", False),
    ("square", "operaciones", "payments",
     "src.connectors.square", "SquareConnector", False),
    # Accounting / ERP
    ("quickbooks", "operaciones", "business",
     "src.connectors.quickbooks", "QuickbooksConnector", False),
    ("xero", "operaciones", "business",
     "src.connectors.xero", "XeroConnector", False),
    ("totvs", "operaciones", "business",
     "src.connectors.totvs", "TotvsConnector", False),
    # Fiscal / Tax (LatAm)
    ("afip_argentina", "operaciones", "business",
     "src.connectors.afip_argentina", "AFIPArgentinaConnector", False),
    ("dte_chile", "operaciones", "business",
     "src.connectors.dte_chile", "DTEChileConnector", False),
    ("nfe", "operaciones", "business",
     "src.connectors.nfe", "NfeConnector", False),
    ("pix_brazil", "operaciones", "payments",
     "src.connectors.pix_brazil", "PixBrazilConnector", False),
    ("sat_mexico", "operaciones", "business",
     "src.connectors.sat_mexico", "SatMexicoConnector", False),
    # Identity
    ("azure_ad", "operaciones", "business",
     "src.connectors.azure_ad", "AzureADConnector", False),

    # === COMUNICACIONES (11 conectores) ===
    # Email
    ("mailgun", "comunicaciones", "communications",
     "src.connectors.mailgun", "MailgunConnector", False),
    ("sendgrid", "comunicaciones", "communications",
     "src.connectors.sendgrid", "SendGridConnector", False),
    ("mailchimp", "comunicaciones", "communications",
     "src.connectors.mailchimp", "MailchimpConnector", False),
    # Chat / Messaging
    ("discord", "comunicaciones", "communications",
     "src.connectors.discord", "DiscordConnector", False),
    ("twilio", "comunicaciones", "communications",
     "src.connectors.twilio", "TwilioConnector", False),
    ("whatsapp", "comunicaciones", "communications",
     "src.connectors.whatsapp", "WhatsAppConnector", False),
    ("teams", "comunicaciones", "communications",
     "src.connectors.teams", "TeamsConnector", False),
    # Helpdesk / Forms
    ("freshdesk", "comunicaciones", "communications",
     "src.connectors.freshdesk", "FreshdeskConnector", False),
    ("intercom", "comunicaciones", "communications",
     "src.connectors.intercom", "IntercomConnector", False),
    ("zendesk", "comunicaciones", "communications",
     "src.connectors.zendesk", "ZendeskConnector", False),
    ("typeform", "comunicaciones", "communications",
     "src.connectors.typeform", "TypeformConnector", False),

    # === DATOS_AUTO (30 conectores) ===
    # AI / LLM
    ("anthropic", "datos_auto", "automation",
     "src.connectors.anthropic", "AnthropicConnector", False),
    ("deepseek", "datos_auto", "automation",
     "src.connectors.deepseek", "DeepseekConnector", False),
    ("huggingface", "datos_auto", "automation",
     "src.connectors.huggingface", "HuggingfaceConnector", False),
    ("openai_v2", "datos_auto", "automation",
     "src.connectors.openai_v2", "OpenaiV2Connector", False),
    # Storage / Cloud
    ("aws_s3", "datos_auto", "data",
     "src.connectors.aws_s3", "AwsS3Connector", False),
    ("azure_blob", "datos_auto", "data",
     "src.connectors.azure_blob", "AzureBlobConnector", False),
    ("gcs", "datos_auto", "data",
     "src.connectors.gcs", "GcsConnector", False),
    ("dropbox", "datos_auto", "data",
     "src.connectors.dropbox", "DropboxConnector", False),
    # Databases
    ("mongo_connector", "datos_auto", "data",
     "src.connectors.mongo_connector", "MongoConnectorConnector", False),
    ("mysql_connector", "datos_auto", "data",
     "src.connectors.mysql_connector", "MysqlConnectorConnector", False),
    ("elastic", "datos_auto", "data",
     "src.connectors.elastic", "ElasticConnector", False),
    # Monitoring / DevOps
    ("datadog", "datos_auto", "data",
     "src.connectors.datadog", "DatadogConnector", False),
    ("new_relic", "datos_auto", "data",
     "src.connectors.new_relic", "NewRelicConnector", False),
    ("grafana", "datos_auto", "data",
     "src.connectors.grafana", "GrafanaConnector", False),
    ("splunk", "datos_auto", "data",
     "src.connectors.splunk", "SplunkConnector", False),
    ("sumologic", "datos_auto", "data",
     "src.connectors.sumologic", "SumoLogicConnector", False),
    ("sentry", "datos_auto", "data",
     "src.connectors.sentry", "SentryConnector", False),
    ("pagerduty", "datos_auto", "data",
     "src.connectors.pagerduty", "PagerDutyConnector", False),
    # Dev / Collaboration
    ("github", "datos_auto", "data",
     "src.connectors.github", "GithubConnector", False),
    ("gitlab", "datos_auto", "data",
     "src.connectors.gitlab", "GitlabConnector", False),
    ("jira", "datos_auto", "data",
     "src.connectors.jira", "JiraConnector", False),
    ("confluence", "datos_auto", "data",
     "src.connectors.confluence", "ConfluenceConnector", False),
    ("notion", "datos_auto", "data",
     "src.connectors.notion", "NotionConnector", False),
    ("asana", "datos_auto", "data",
     "src.connectors.asana", "AsanaConnector", False),
    ("trello", "datos_auto", "data",
     "src.connectors.trello", "TrelloConnector", False),
    ("monday", "datos_auto", "data",
     "src.connectors.monday", "MondayConnector", False),
    ("airtable", "datos_auto", "data",
     "src.connectors.airtable", "AirtableConnector", False),
    # Security
    ("okta", "datos_auto", "data",
     "src.connectors.okta", "OktaConnector", False),
    ("vault", "datos_auto", "data",
     "src.connectors.vault", "VaultConnector", False),
    # RuvConnector removido en Fase 2B (no es facturación electrónica).
]
