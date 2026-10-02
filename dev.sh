#!/usr/bin/env bash
# Starts the upstream (:8081), the backend (:8000) and the frontend (:4000). Ctrl+C stops all three.
# MySQL must already be running (e.g. DBngin) with a `project_editor` database.
# --stable turns the upstream's flakiness (slow GETs, 504s) off.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" == "--stable" ]]; then
  export UPSTREAM_SLOW_RATE=0 UPSTREAM_TIMEOUT_RATE=0
fi

run() {
  local name=$1; shift
  ("$@" 2>&1 | sed -u "s/^/[$name] /") &
}

trap 'kill 0' EXIT
run upstream bash -c "cd upstream && uv run upstream"
run backend bash -c "cd backend && uv run uvicorn app.main:app --reload --port 8000"
run frontend bash -c "cd frontend && npm run dev"
wait
