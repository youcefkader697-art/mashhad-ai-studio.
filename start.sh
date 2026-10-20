#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if [ ! -f .env ]; then cp .env.example .env; fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
