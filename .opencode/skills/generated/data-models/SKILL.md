---
name: data-models
description: Data models, schemas, Pydantic validation, ORM definitions
load: on-demand
tokens: ~130
---

# Data Models

## Module: `src/data/` + `src/schemas/` (12 files)
Data layer with models, schemas, and validation.

### Key Components
- **Data Models**: Pydantic/SQLAlchemy models
- **Schemas**: API request/response schemas
- **Validation**: Input validation rules
- **Migrations**: Database schema migrations
- **Serializers**: Model serialization/deserialization

### Usage
```python
from src.data.models import Invoice
from src.schemas.invoice import InvoiceSchema
invoice = InvoiceSchema(**data)
validated = invoice.validate()
```

### Key Files
- `src/data/models.py` - Core data models
- `src/schemas/` - API schemas
- `src/data/validators.py` - Validation logic
