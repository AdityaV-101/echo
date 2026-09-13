#!/usr/bin/env bash
# Starts the Echo backend (FastAPI/uvicorn) and frontend (Vite) together.
#
# Usage:
#   ./run.sh                  # stub scorer (fast, fake results, no ffmpeg/model needed)
#   USE_REAL_SCORER=1 ./run.sh   # real wav2vec2 phoneme scorer (needs ffmpeg + espeak-ng, see SETUP_NOTES.md)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d venv ]; then
  echo "Python virtual environment not found. Run:"
  echo "  python3 -m venv venv"
  echo "  source venv/bin/activate"
  echo "  pip install -r backend/requirements.txt"
  exit 1
fi

if [ ! -d frontend/node_modules ]; then
  echo "Frontend dependencies not installed. Run: cd frontend && npm install"
  exit 1
fi

cleanup() {
  echo "Stopping Echo..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

source venv/bin/activate
(cd backend && uvicorn main:app --port 8000) &
BACKEND_PID=$!

(cd frontend && npm run dev) &
FRONTEND_PID=$!

echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "Press Ctrl+C to stop both."

wait
