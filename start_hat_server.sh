#!/usr/bin/env bash
# M10: Script de lanzamiento para Flask (8080) + FastAPI (8000) en producción.
#
# Uso:
#   bash start_hat_server.sh
#
# Flask sirve la Web UI en http://localhost:8080
# FastAPI sirve la API v2 + HAT en http://localhost:8000

set -e

echo "=== Zenic-Flujo HAT Server ==="
echo "Flask Web UI:  http://localhost:8080"
echo "FastAPI v2:    http://localhost:8000"
echo "HAT Chat API:  http://localhost:8000/api/hat/chat"
echo "Health:        http://localhost:8000/api/hat/health"
echo "Metrics:       http://localhost:8080/metrics"
echo

# Lanzar FastAPI en background
python3 -m uvicorn src.api_v2.app:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info &
FASTAPI_PID=$!
echo "FastAPI started (PID: $FASTAPI_PID) on port 8000"

# Lanzar Flask en foreground
python3 src/main.py &
FLASK_PID=$!
echo "Flask started (PID: $FLASK_PID) on port 8080"

# Manejar señales para cerrar ambos
trap "kill $FASTAPI_PID $FLASK_PID 2>/dev/null; exit" INT TERM

# Esperar
wait
