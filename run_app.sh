#!/bin/bash

# ─────────────────────────────────────────────────────────────────────────────
#  run_app.sh — Launch the Personalised Kids Books Streamlit App
# ─────────────────────────────────────────────────────────────────────────────

# Navigate to project directory
cd "$(dirname "$0")"

echo "🚀 Starting Kids Books App..."
echo "📂 Working directory: $(pwd)"
echo ""

# Run the Streamlit app
streamlit run app.py
