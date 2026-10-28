#!/bin/sh
set -eu
# Executar da raiz do pacote. Um processo porque sessões e HITL são efêmeros.
exec python -m uvicorn api:app --app-dir test-ui --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
