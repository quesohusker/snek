#!/bin/zsh
cd "$(dirname "$0")"
if [ ! -d frontend/dist ]; then
  (cd frontend && npm install && npm run build) || exit 1
fi
exec .venv/bin/python -m snek
