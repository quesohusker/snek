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
if ! .venv/bin/python -m snek --check quick >/dev/null 2>&1; then
  echo "Snek needs to add or update some packages. They go into .venv. Your own Python is not changed."
  .venv/bin/python -m pip install --quiet --upgrade -e . || exit 1
  if ! .venv/bin/python -m snek --check; then
    echo "Snek could not finish setting up. The list above shows what is wrong."
    echo "If it does not clear, delete the .venv folder and start Snek again."
    exit 1
  fi
fi
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm ci --ignore-scripts && npm run build) || exit 1
fi
exec .venv/bin/python -m snek "$@"
