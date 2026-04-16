#!/bin/bash
#
# Bridget Connect — ngrok tunnel + QR code for any agent
#
# Usage:
#   ./connect.sh 8080    # Agent on port 8080 (Hermes, bridge server)
#   ./connect.sh 3000    # Agent on port 3000
#
# Starts ngrok, generates a QR code that auto-connects Bridget,
# and copies the URL to your clipboard.
#

set -e

PORT="${1:-8080}"
NGROK_PID=""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

cleanup() {
    if [ -n "$NGROK_PID" ]; then
        kill "$NGROK_PID" 2>/dev/null || true
    fi
    echo ""
    echo -e "${GREEN}✓ Tunnel closed.${NC}"
}
trap cleanup EXIT

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✕${NC} $1"; exit 1; }

echo ""
echo -e "${BOLD}  Bridget Connect — Tunnel to port $PORT${NC}"
echo "  ─────────────────────────────────────"
echo ""

# --- Check ngrok ---

if ! command -v ngrok &>/dev/null; then
    fail "ngrok not found. Install: brew install ngrok"
fi
ok "ngrok"

# --- Verify agent is running ---

if curl -s "http://localhost:$PORT" >/dev/null 2>&1 || \
   curl -s "http://localhost:$PORT/health" >/dev/null 2>&1 || \
   curl -s "http://localhost:$PORT/ping" >/dev/null 2>&1; then
    ok "Agent responding on port $PORT"
else
    warn "Nothing detected on port $PORT — make sure your agent is running"
fi

# --- Start ngrok ---

echo ""
echo "  Starting ngrok tunnel to port $PORT..."

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

# --- Deep link ---

ENDPOINT_URL="${NGROK_URL}/v1/audio/voice_chat"
DEEP_LINK="voicebridge://connect?url=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$ENDPOINT_URL', safe=''))")&channel=direct-api"

# --- QR code ---

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
echo -e "  ${BOLD}Or paste this in Bridget's Magic Prompt:${NC}"
echo ""
echo -e "  ${GREEN}{${NC}"
echo -e "  ${GREEN}  \"endpoint_url\": \"$ENDPOINT_URL\",${NC}"
echo -e "  ${GREEN}  \"api_key\": \"\",${NC}"
echo -e "  ${GREEN}  \"agent_name\": \"My Agent\"${NC}"
echo -e "  ${GREEN}}${NC}"
echo ""

# Copy to clipboard
if command -v pbcopy &>/dev/null; then
    echo -n "$ENDPOINT_URL" | pbcopy
    echo -e "  ${GREEN}✓ URL copied to clipboard${NC}"
fi

echo ""
echo "  ─────────────────────────────────────"
echo -e "  Tunnel running. ${YELLOW}Ctrl+C${NC} to stop."
echo ""

# Keep alive
wait "$NGROK_PID" 2>/dev/null
