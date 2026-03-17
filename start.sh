#!/usr/bin/env bash
# Electoral Roll OCR — Web UI launcher (Linux/macOS)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Load .env (TESSDATA_PREFIX for local tessdata) ──────────────────────────
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

# ── Add common Tesseract locations to path ──────────────────────────────────
for TESS_DIR in \
    "/usr/bin" \
    "/usr/local/bin" \
    "/opt/homebrew/bin"; do
    if [ -f "$TESS_DIR/tesseract" ]; then
        export PATH="$TESS_DIR:$PATH"
        break
    fi
done

# ── Check Python ────────────────────────────────────────────────────────────
PYTHON=$(which python3 2>/dev/null || which python 2>/dev/null)
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python not found. Install Python 3.10+ first."
    exit 1
fi
echo "[OK] Python: $($PYTHON --version)"

# ── Install web dependencies if missing ─────────────────────────────────────
if ! $PYTHON -c "import fastapi, uvicorn, aiofiles" 2>/dev/null; then
    echo "Installing web dependencies..."
    $PYTHON -m pip install fastapi uvicorn aiofiles psutil --quiet
fi

# ── Find free port ───────────────────────────────────────────────────────────
PORT=8000
for try_port in $(seq 8000 8009); do
    if ! lsof -i :"$try_port" &>/dev/null 2>&1; then
        PORT=$try_port
        break
    fi
done

echo ""
echo "  Electoral Roll OCR UI → http://localhost:$PORT"
echo "  Press Ctrl+C to stop"
echo ""

$PYTHON -m uvicorn web.app:app --host 127.0.0.1 --port "$PORT"
