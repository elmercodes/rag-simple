#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load backend env if present.
if [ -f "${ROOT_DIR}/apps/backend/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${ROOT_DIR}/apps/backend/.env"
  set +a
fi

backend() {
  cd "${ROOT_DIR}"
  PYTHONPATH="${ROOT_DIR}/apps" python -m uvicorn backend.main:app --reload --port 8000
}

frontend() {
  cd "${ROOT_DIR}/apps/frontend"
  npm run dev
}

cleanup() {
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID"
  fi
}
trap cleanup EXIT INT TERM

backend &
BACKEND_PID=$!
frontend
