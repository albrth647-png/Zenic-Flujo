---
name: bpmn-designer
description: BPMN process modeling, builder, converter, parser, exporter
load: on-demand
tokens: ~140
---

# BPMN Designer

## Module: `src/bpmn/` (6 files)
BPMN 2.0 process modeling and conversion toolkit.

### Key Components
- **Builder**: Programmatic BPMN diagram construction
- **Converter**: BPMN to internal representation
- **Exporter**: Export to BPMN XML format
- **Parser**: Parse BPMN XML to models
- **Models**: BPMN data structures

### Usage
```python
from src.bpmn import BPMNBuilder
builder = BPMNBuilder()
builder.add_task("Send Invoice", type="service")
xml = builder.export()
```

### Key Files
- `src/bpmn/builder.py` - Diagram builder
- `src/bpmn/converter.py` - Format converter
- `src/bpmn/models.py` - Data models
