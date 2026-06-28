---
name: connectors-integration
description: External API connectors - AFIP Argentina, MercadoLibre, and 65+ integrations
load: on-demand
tokens: ~180
---

# Connectors Integration

## Module: `src/connectors/` (65 files)
Integration layer connecting Zenic-Flujo with external services and APIs.

### Key Connectors
- **AFIP Argentina**: Argentine tax authority integration
- **MercadoLibre**: E-commerce platform
- **WhatsApp**: Messaging integration
- **Email/SMTP**: Email services
- **Payment Gateways**: Payment processing
- **Cloud APIs**: External cloud services

### Architecture
Each connector follows a standardized pattern:
- Auth handler (OAuth, API key, certificate)
- Request/response models
- Error handling with retry logic
- Rate limiting

### Key Files
- `src/connectors/afip_argentina/` - AFIP integration
- `src/connectors/mercadolibre/` - ML integration
- `src/connectors/base.py` - Base connector class
