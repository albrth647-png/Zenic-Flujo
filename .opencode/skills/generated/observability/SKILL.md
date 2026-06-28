---
name: observability
description: Monitoring, logging, metrics, telemetry, alerting
load: on-demand
tokens: ~130
---

# Observability

## Module: `src/observability/` (4 files)
System observability with monitoring, logging, and metrics.

### Key Features
- **Structured Logging**: JSON-formatted logs
- **Metrics Collection**: Performance metrics
- **Health Checks**: System health endpoints
- **Telemetry**: Request tracing
- **Alerting**: Configurable alert rules

### Usage
```python
from src.observability import Monitor
monitor = Monitor()
monitor.track_request(duration=0.342, endpoint="/api/v2/invoices")
monitor.alert_if_slow(threshold=1.0)
```

### Key Files
- `src/observability/monitor.py` - Monitoring core
- `src/observability/logger.py` - Logging config
- `src/observability/metrics.py` - Metrics
