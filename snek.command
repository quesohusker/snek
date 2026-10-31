#!/bin/sh
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  PY=""
  for c in python3.14 python3.13 python3.12 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
      PY="$c"
      break
    fi
  done
  if [ -z "$PY" ]; then
    echo "Snek needs Python 3.12 or newer. Get it at https://www.python.org/downloads/"
    exit 1
  fi
  echo "First run: installing Snek into .venv. This takes a minute."
  "$PY" -m venv .venv || exit 1
  .venv/bin/python -m pip install --quiet --upgrade pip || exit 1
  .venv/bin/python -m pip install --quiet -e . || exit 1
fi
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm install && npm run build) || exit 1
fi
exec .venv/bin/python -m snek "$@"
