# bridget-voice-server

> **Using Claude Code?** You don't need this server. Use the [Bridget Channel Plugin](https://github.com/voicebridgeteam-max/Bridget/tree/main/BridgetChannel) instead — it connects directly to your Claude Code session with on-device STT/TTS, full project access, permission relay, and $0 cost.

Give any AI agent a voice. This open-source server sits between [Bridget](https://bridget.app) (the iOS voice app) and your agent's text API. It handles speech-to-text and text-to-speech so your agent doesn't have to.

```
You speak into Bridget
    ↓
Bridget sends audio here
    ↓
Whisper transcribes your voice → text
    ↓
Text sent to your agent's API → response
    ↓
Edge-TTS converts response → voice
    ↓
Bridget plays the reply
```

**Zero cost out of the box.** Local Whisper for STT, Edge-TTS for voice. No API keys required.

---

## Before You Start

You need two things:

### 1. ffmpeg (required by Whisper for audio decoding)
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Or download from https://ffmpeg.org/download.html
```
Verify: `ffmpeg -version`

### 2. A free ngrok account (for remote access)

1. Sign up at [ngrok.com/signup](https://dashboard.ngrok.com/signup) (free, 30 seconds)
2. Copy your authtoken from [your dashboard](https://dashboard.ngrok.com/get-started/your-authtoken)
3. Install ngrok: `brew install ngrok` or download from [ngrok.com/download](https://ngrok.com/download)
4. Authenticate: `ngrok config add-authtoken YOUR_TOKEN`

You only do these once.

> **Why ngrok?** Bridget runs on your iPhone. Your server runs on your computer. They're almost never on the same network (CarPlay, cellular, different WiFi). ngrok creates a public tunnel so your phone can reach your server from anywhere.

---

## Two Paths to Bridget Compatibility

**Path 1: Deploy this bridge server** — Your agent has a text API (Ollama, OpenAI, Claude Code CLI, etc.). Deploy this server alongside it. It wraps your text API with voice. See [Quickstart](#quickstart) below.

**Path 2: Build the endpoint natively** — Your agent already runs an HTTP server (Hermes, OpenClaw, custom FastAPI). Add the voice endpoint directly — better performance, no middleware. See [NATIVE_IMPLEMENTATION.md](NATIVE_IMPLEMENTATION.md) for the step-by-step guide.

Not sure which? If your agent can modify its own code and has an HTTP server, go native. Otherwise, deploy the bridge server.

---

## Quickstart

**One command** — installs everything, starts the server and ngrok, shows a QR code:

```bash
git clone https://github.com/voicebridgeteam-max/bridget-voice-server
cd bridget-voice-server
./start.sh
```

Scan the QR code with your iPhone camera to connect Bridget automatically.

<details>
<summary>Manual setup (if you prefer)</summary>

```bash
cp config.env.example .env
# Edit .env — set AGENT_API_URL to your agent's text API
pip install -r requirements.txt
python server.py
# In another terminal:
./connect.sh 8080   # starts ngrok + shows QR code
```
</details>

The server starts on `http://0.0.0.0:8080`. Bridget connects to `http://YOUR_IP:8080/v1/audio/voice_chat`.

> **First run:** Whisper downloads its model (~140MB for `base`). This only happens once.

---

## Backends

The server supports multiple ways to connect to your agent:

### OpenAI-compatible API (default)

Works with Ollama, LM Studio, OpenAI, Groq, vLLM, llama.cpp, or any endpoint that speaks the OpenAI chat format.

```env
AGENT_BACKEND=openai_compatible
AGENT_API_URL=http://localhost:11434/v1/chat/completions
AGENT_MODEL=llama3
```

### Claude Code CLI

For Claude Code users with OAuth or Max. No API key needed — uses your existing authenticated session.

```env
AGENT_BACKEND=claude_code
CLAUDE_CODE_PATH=claude
```

### Codex CLI

For OpenAI Codex users with an existing session.

```env
AGENT_BACKEND=codex
CODEX_PATH=codex
```

### Custom Command

Escape hatch for any agent with a CLI. Pipes text to stdin, reads response from stdout.

```env
AGENT_BACKEND=custom_command
AGENT_COMMAND=python my_agent.py
```

---

## If Your Agent Has Its Own Server

**You might not need this.** If your agent already runs an HTTP server (Hermes, OpenClaw, custom FastAPI), it can build the voice endpoint natively — better performance, no middleware.

Your agent needs to add one route: `POST /v1/audio/voice_chat`

- **[NATIVE_IMPLEMENTATION.md](NATIVE_IMPLEMENTATION.md)** — Step-by-step build guide with code examples and all known pitfalls. Start here.
- **[VOICE_ENDPOINT_SPEC.md](VOICE_ENDPOINT_SPEC.md)** — Protocol reference (request/response format).
- **[TESTING.md](TESTING.md)** — Curl commands to verify each stage before connecting Bridget.

---

## STT & TTS Providers

Defaults are free. Swap in cloud providers for better speed or quality.

### Speech-to-Text

| Provider | Config | Cost | Notes |
|----------|--------|------|-------|
| `whisper_local` | (default) | Free | Downloads model on first run |
| `openai` | `STT_API_KEY` required | $0.006/min | Fastest |
| `deepgram` | `STT_API_KEY` required | $0.0043/min | Fast, good quality |

### Text-to-Speech

| Provider | Config | Cost | Notes |
|----------|--------|------|-------|
| `edge_tts` | (default) | Free | Good quality, many voices |
| `openai` | `TTS_API_KEY` required | $0.015/1K chars | Fast, natural |
| `elevenlabs` | `TTS_API_KEY` required | $0.30/1K chars | Best quality |

---

## Configuration Reference

Copy `config.env.example` to `.env` and edit:

```env
# Agent connection
AGENT_BACKEND=openai_compatible    # openai_compatible, claude_code, codex, custom_command
AGENT_API_URL=http://localhost:11434/v1/chat/completions
AGENT_API_KEY=                     # Empty if not needed
AGENT_MODEL=llama3

# Server
HOST=0.0.0.0                      # 0.0.0.0 = accept connections from any device
PORT=8080
API_KEY=                           # Optional: require Bridget to send this key

# STT
STT_PROVIDER=whisper_local         # whisper_local, openai, deepgram
WHISPER_MODEL=base                 # tiny, base, small, medium, large

# TTS
TTS_PROVIDER=edge_tts              # edge_tts, openai, elevenlabs
TTS_VOICE=en-US-GuyNeural          # Edge-TTS voice name
```

See `config.env.example` for all options including cloud provider API keys.

---

## Examples

Pre-made configs in the `examples/` folder:

- [`ollama.env`](examples/ollama.env) — Ollama / LM Studio / local models
- [`openai.env`](examples/openai.env) — OpenAI API
- [`anthropic.env`](examples/anthropic.env) — Anthropic via LiteLLM or Claude Code
- [`claude-code.env`](examples/claude-code.env) — Claude Code CLI (OAuth, no API key)
- [`custom-command.env`](examples/custom-command.env) — Any CLI agent

Copy any example to `.env` and edit:
```bash
cp examples/ollama.env .env
```

---

## Connecting from Bridget

1. Start the server: `python server.py`
2. Start ngrok: `ngrok http 8080`
3. Copy the `https://...ngrok-free.app` URL from ngrok's output
4. Open Bridget on your iPhone
5. Tap **Direct API** → select your agent type → follow the setup
6. When asked for connection details, provide this JSON:

```json
{
  "endpoint_url": "https://YOUR-NGROK-URL.ngrok-free.app/v1/audio/voice_chat",
  "api_key": "",
  "agent_name": "My Agent"
}
```

7. Paste it into Bridget and tap **Connect**

> **Note:** The ngrok URL changes each time you restart it (free tier). Keep ngrok running. If your machine sleeps or the process dies, restart both the server and ngrok. Bridget handles ngrok's free-tier interstitial page automatically.

---

## Health Check

```bash
curl http://localhost:8080/health
# {"status": "ok", "server": "bridget-voice-server", "backend": "openai_compatible"}
```

---

## Troubleshooting

**"Transcription failed"**
- Whisper might not be installed. Run `pip install openai-whisper` and try again.
- If using a large model, ensure you have enough RAM.

**"Agent unreachable"**
- Check `AGENT_API_URL` in `.env`. Is the agent running?
- Test directly: `curl -X POST YOUR_AGENT_URL -H "Content-Type: application/json" -d '{"model":"llama3","messages":[{"role":"user","content":"hello"}]}'`

**Slow responses**
- Whisper `base` model is a good balance. `tiny` is faster but less accurate. `medium` and `large` are slower but better.
- Consider switching to cloud STT (`openai` or `deepgram`) for faster transcription.

**Can't connect from Bridget**
- Make sure `HOST=0.0.0.0` (not `127.0.0.1`)
- Check your firewall allows port 8080
- Verify with: `curl http://YOUR_IP:8080/health` from another device

---

## What is Bridget?

[Bridget](https://bridget.app) is a voice-first iOS app that lets you talk to your AI agent from anywhere — iPhone, CarPlay, Siri, widgets, Action Button. It records your voice, sends it to your agent, and plays back the reply. No typing, no screens.

Bridget is the voice interface. Your agent is the brain. This server is the bridge.

---

## License

MIT
