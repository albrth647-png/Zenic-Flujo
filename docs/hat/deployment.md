# HAT-ORBITAL — Deployment Guide

## Prerrequisitos

- Python 3.12+
- SQLite 3.35+ (incluido en Python stdlib)
- Zenic-Flujo base instalado (`pip install -r requirements.txt`)
- Opcional: Redis (para hot cache en producción)
- Opcional: OpenTelemetry Collector (para tracing)

## Instalación

```bash
# Clonar repo
git clone https://github.com/albrth647-png/Zenic-Flujo.git
cd Zenic-Flujo

# Instalar dependencias
pip install -r requirements.txt

# Inicializar DB (crea las 7 tablas HAT automáticamente)
python -c "from src.hat.ledger.repository import LedgerRepository; LedgerRepository()"
```

## Configuración

### Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `WFD_SESSION_SECRET` | auto-generado | Flask session secret |
| `WFD_LICENSE_SECRET` | auto-generado | License signing secret |
| `WFD_API_V2_JWT_SECRET` | auto-generado | JWT signing |
| `WFD_API_V2_CORS_ORIGINS` | `""` | CORS origins comma-separated |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | none | OTel collector endpoint |

### Iniciar servidor

```bash
# Flask (UI + API v1)
python src/main.py

# O con FastAPI v2 (incluye HAT endpoints)
uvicorn src.api_v2.app:app --host 0.0.0.0 --port 8000
```

### Verificar

```bash
# Health check
curl http://localhost:8000/api/hat/health
# → {"status": "ok", "module": "hat", "version": "f0-d7"}

# Chat
curl -X POST http://localhost:8000/api/hat/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "session_id": "s1", "message": "buscar python"}'
```

## Docker

```bash
docker build -t zenic-flujo-hat .
docker run -p 8000:8000 zenic-flujo-hat
```

## Kubernetes (Helm)

```bash
cd deploy/helm/zenic-flujo-hat
helm install zenic-flujo .
```

Ver `deploy/helm/zenic-flujo-hat/values.yaml` para configuración.

## Benchmarks

```bash
# Benchmark HAT completo
python scripts/benchmark_hat.py --n 20

# Benchmark anti-dup
python scripts/benchmark_anti_dup.py --n 100
```

Resultados esperados:
- HAT p50: <5ms, p99: <10ms
- Anti-dup p50: <1ms, p99: <1ms
