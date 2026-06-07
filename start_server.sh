#!/bin/bash
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
