#!/usr/bin/env bash

set -Eeuo pipefail

# Resolve project root (directory of this script)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Optional: virtualenv location (defaults to ./unisolar_env)
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/unisolar_env}"

# Activate virtual environment if present
if [[ -d "$VENV_DIR" && -f "$VENV_DIR/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
fi

# Development defaults (can be overridden via env vars)
export FLASK_ENV="${FLASK_ENV:-development}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5001}"

# Prefer run_app.py which configures logging and debug correctly
if [[ -f "$PROJECT_ROOT/run_app.py" ]]; then
  exec python "$PROJECT_ROOT/run_app.py" --debug --host "$HOST" --port "$PORT" "$@"
else
  # Fallback to flask run if run_app.py is missing
  export FLASK_APP="${FLASK_APP:-app.py}"
  exec flask run --host "$HOST" --port "$PORT" "$@"
fi


