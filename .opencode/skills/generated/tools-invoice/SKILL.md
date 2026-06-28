---
name: tools-invoice
description: Invoice/fiscal tools - billing, AFIP, payment tracking, fiscal compliance
load: on-demand
tokens: ~160
---

# Tools Invoice

## Module: `src/tools/invoice/`
Invoice and fiscal management tools with AFIP Argentina integration.

### Key Features
- **Invoice Generation**: Facturación electrónica
- **AFIP Integration**: Electronic billing compliance
- **Payment Tracking**: Payment status and reconciliation
- **Fiscal Reports**: VAT, income tax reports
- **Credit/Debit Notes**: Notas de crédito/débito

### Usage
```python
from src.tools.invoice import InvoiceTool
inv = InvoiceTool()
invoice = inv.create_invoice(client_id=123, amount=50000)
```

### Key Files
- `src/tools/invoice/billing.py` - Billing core
- `src/tools/invoice/afip.py` - AFIP integration
- `src/tools/invoice/reports.py` - Fiscal reports
