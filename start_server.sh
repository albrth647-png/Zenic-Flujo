#!/bin/bash
# M10: FastAPI v2 (port 8000) is launched automatically by src/main.py
# in a background thread. Flask (port 8080) runs in the main thread.
# Both ports must be exposed in Dockerfile.
#
# Note: this script is a lightweight dev launcher that bypasses main.py
# (it directly creates the Flask app). To get FastAPI v2 alongside Flask,
# invoke `python -m src.main` instead. See IMPLEMENTATION_PLAN.md M10.2.
export WFD_WEB_HOST=0.0.0.0
export WFD_WEB_PORT=5000
export WFD_WEBHOOK_PORT=5001
export PYTHONPATH=/home/z/my-project/Zenic-Flijo

cd /home/z/my-project/Zenic-Flijo

exec python -c "
import os, sys
os.environ['WFD_WEB_HOST'] = '0.0.0.0'
os.environ['WFD_WEB_PORT'] = '5000'
os.environ['WFD_WEBHOOK_PORT'] = '5001'
import webbrowser
webbrowser.open = lambda *a, **k: None
from src.web.app import create_app
app = create_app()
app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
"
