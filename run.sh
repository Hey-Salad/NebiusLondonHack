#!/usr/bin/env bash
# Salad Scout - one-command local run.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "→ creating virtualenv"
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

if [ ! -f .env ]; then
  echo "→ no .env found, copying .env.example (add your keys, then re-run)"
  cp .env.example .env
fi

PORT="${PORT:-8000}"
echo "→ Salad Scout on http://localhost:${PORT}"
exec .venv/bin/uvicorn app.main:app --reload --port "${PORT}"
