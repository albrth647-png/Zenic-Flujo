---
name: events-system
description: Event bus, publish/subscribe, event handlers, async processing
load: on-demand
tokens: ~140
---

# Events System

## Module: `src/events/` (11 files)
Asynchronous event system for inter-module communication.

### Key Components
- **Event Bus**: Central event dispatcher
- **Pub/Sub**: Publish/subscribe pattern
- **Event Handlers**: Registered event processors
- **Async Queue**: Async event processing
- **Event Types**: Typed event definitions

### Events Flow
```
Producer → EventBus → Queue → Handlers → Actions
```

### Usage
```python
from src.events import EventBus
bus = EventBus()
bus.emit("invoice.created", invoice_id=123)
bus.subscribe("invoice.created", send_email_notification)
```

### Key Files
- `src/events/bus.py` - Event bus
- `src/events/handlers.py` - Event handlers
- `src/events/types.py` - Event types
