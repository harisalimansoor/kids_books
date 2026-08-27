#!/usr/bin/env bash
# Start the Streamlit workbook app.
# Backend already runs the kitchen face pipeline on Generate:
#   YuNet paste → AI blend (adult, then child) → object-count lock → degreen
#
# Usage (from repo root):
#   ./scripts/run_workbook.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
elif [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]] && [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' .env | grep -v '^#' || true)
  set +a
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "⚠️  OPENROUTER_API_KEY missing — add it to .env (needed for AI face blend)."
fi

echo "▶ Streamlit workbook → kitchen face pipeline on Generate"
exec streamlit run new_pipeline/newapp.py
