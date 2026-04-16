#!/bin/bash
#
# Bridget Voice Server — One-command setup
#
# Installs dependencies, starts the bridge server, creates a tunnel,
# and shows a QR code to connect from Bridget.
#
# Usage:
#   ./start.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8080}"
SERVER_PID=""
NGROK_PID=""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    if [ -n "$NGROK_PID" ]; then
        kill "$NGROK_PID" 2>/dev/null || true
    fi
    echo ""
    echo -e "${GREEN}✓ Bridget voice server stopped.${NC}"
}
trap cleanup EXIT

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✕${NC} $1"; exit 1; }

echo ""
echo -e "${BOLD}  Bridget Voice Server — Setup${NC}"
echo "  ─────────────────────────────────────"
echo ""

cd "$SCRIPT_DIR"

# --- Prerequisites ---

# Python 3
if command -v python3 &>/dev/null; then
    ok "Python $(python3 --version 2>&1 | cut -d' ' -f2)"
else
    fail "Python 3 not found. Install: brew install python3"
fi

# ffmpeg
if command -v ffmpeg &>/dev/null; then
    ok "ffmpeg"
else
    warn "ffmpeg not found. Installing..."
    if command -v brew &>/dev/null; then
        brew install ffmpeg 2>/dev/null
    fi
    if command -v ffmpeg &>/dev/null; then
        ok "ffmpeg installed"
    else
        fail "ffmpeg required by Whisper. Install: brew install ffmpeg"
    fi
fi

# pip deps
if python3 -c "import fastapi, whisper, edge_tts" 2>/dev/null; then
    ok "Python dependencies"
else
    echo "  Installing Python dependencies..."
    pip3 install -r requirements.txt --quiet 2>/dev/null
    if python3 -c "import fastapi, whisper, edge_tts" 2>/dev/null; then
        ok "Dependencies installed"
    else
        fail "pip install failed. Run: pip3 install -r requirements.txt"
    fi
fi

# ngrok
if command -v ngrok &>/dev/null; then
    ok "ngrok"
else
    warn "ngrok not found. Installing..."
    if command -v brew &>/dev/null; then
        brew install ngrok 2>/dev/null
    else
        curl -sL https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-arm64.zip -o /tmp/ngrok.zip
        unzip -o /tmp/ngrok.zip -d "$HOME/bin/" 2>/dev/null
        export PATH="$HOME/bin:$PATH"
    fi
    if command -v ngrok &>/dev/null; then
        ok "ngrok installed"
    else
        fail "ngrok install failed. Install: brew install ngrok"
    fi
fi

# --- .env check ---

if [ ! -f ".env" ]; then
    echo ""
    echo -e "  ${YELLOW}No .env file found.${NC} Let's create one."
    echo ""
    echo "  What's your agent's text API URL?"
    echo "  Examples:"
    echo "    Ollama:     http://localhost:11434/v1/chat/completions"
    echo "    LM Studio:  http://localhost:1234/v1/chat/completions"
    echo "    OpenAI:     https://api.openai.com/v1/chat/completions"
    echo ""
    read -p "  API URL: " AGENT_URL
    AGENT_URL=${AGENT_URL:-http://localhost:11434/v1/chat/completions}

    read -p "  Model name (e.g. llama3, gpt-4o): " AGENT_MODEL
    AGENT_MODEL=${AGENT_MODEL:-llama3}

    read -p "  API key (press Enter if none): " AGENT_KEY

    cat > .env <<ENVEOF
AGENT_BACKEND=openai_compatible
AGENT_API_URL=$AGENT_URL
AGENT_MODEL=$AGENT_MODEL
AGENT_API_KEY=$AGENT_KEY
HOST=0.0.0.0
PORT=$PORT
STT_PROVIDER=whisper_local
WHISPER_MODEL=base
TTS_PROVIDER=edge_tts
TTS_VOICE=en-US-AriaNeural
ENVEOF
    ok "Created .env"
else
    ok ".env configured"
fi

# --- Start server ---

echo ""
echo "  Starting voice server..."

# Kill any existing server on the port
kill "$(lsof -ti:$PORT)" 2>/dev/null || true
sleep 1

python3 server.py > /tmp/bridget-server.log 2>&1 &
SERVER_PID=$!

# Wait for health check
for i in $(seq 1 15); do
    sleep 1
    if curl -s "http://localhost:$PORT/health" >/dev/null 2>&1; then
        break
    fi
done

if curl -s "http://localhost:$PORT/health" >/dev/null 2>&1; then
    ok "Voice server running on port $PORT"
else
    echo ""
    echo "  Server failed to start. Logs:"
    tail -20 /tmp/bridget-server.log
    fail "Check the logs above"
fi

# --- Start ngrok + show QR ---

echo ""
echo "  Starting ngrok tunnel..."

killall ngrok 2>/dev/null || true
sleep 1

ngrok http "$PORT" --log=stdout > /tmp/bridget-ngrok.log 2>&1 &
NGROK_PID=$!

NGROK_URL=""
for i in $(seq 1 20); do
    sleep 1
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for t in data.get('tunnels', []):
        url = t.get('public_url', '')
        if url.startswith('https://'):
            print(url)
            break
except:
    pass
" 2>/dev/null)
    if [ -n "$NGROK_URL" ]; then
        break
    fi
done

if [ -z "$NGROK_URL" ]; then
    fail "ngrok failed to start. Run: ngrok config check"
fi

ok "Tunnel: $NGROK_URL"

ENDPOINT_URL="${NGROK_URL}/v1/audio/voice_chat"
DEEP_LINK="voicebridge://connect?url=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$ENDPOINT_URL', safe=''))")&channel=direct-api"

echo ""
echo -e "  ${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "  ${BOLD}║  Scan this QR code with your iPhone camera       ║${NC}"
echo -e "  ${BOLD}║  to connect Bridget automatically:               ║${NC}"
echo -e "  ${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

if command -v qrencode &>/dev/null; then
    qrencode -t ANSIUTF8 "$DEEP_LINK" 2>/dev/null | sed 's/^/  /'
elif python3 -c "import qrcode" 2>/dev/null; then
    python3 -c "
import qrcode
qr = qrcode.QRCode(box_size=1, border=1)
qr.add_data('$DEEP_LINK')
qr.make(fit=True)
qr.print_ascii(invert=True)
" 2>/dev/null | sed 's/^/  /'
else
    echo "  (Install qrencode for QR code: brew install qrencode)"
fi

echo ""
echo -e "  ${BOLD}Or paste this JSON in Bridget:${NC}"
echo ""
echo -e "  ${GREEN}{${NC}"
echo -e "  ${GREEN}  \"endpoint_url\": \"$ENDPOINT_URL\",${NC}"
echo -e "  ${GREEN}  \"api_key\": \"\",${NC}"
echo -e "  ${GREEN}  \"agent_name\": \"My Agent\"${NC}"
echo -e "  ${GREEN}}${NC}"
echo ""

if command -v pbcopy &>/dev/null; then
    echo -n "$ENDPOINT_URL" | pbcopy
    echo -e "  ${GREEN}✓ URL copied to clipboard${NC}"
fi

echo ""
echo "  ─────────────────────────────────────"
echo -e "  Server + tunnel running. ${YELLOW}Ctrl+C${NC} to stop."
echo -e "  First request will be slow (Whisper downloads model)."
echo ""

# Keep alive — wait for either process to exit
wait "$SERVER_PID" "$NGROK_PID" 2>/dev/null
