# Bridget Voice Endpoint Specification

This is the protocol that Bridget (the iOS app) speaks. If you're building a native voice endpoint into your agent, implement this spec. If you're using `bridget-voice-server`, it already implements this — you don't need to do anything.

---

## Endpoint

```
POST /v1/audio/voice_chat
```

## Request

**Headers:**
- `Authorization: Bearer {api_key}` (omit if no auth required)
- `Content-Type: multipart/form-data`

**Form fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio` | file | Yes | OGG/Opus encoded audio (filename: `voice.ogg`, MIME: `audio/ogg; codecs=opus`) |
| `system_prompt` | string | No | Response preference instruction (e.g., "Always respond with voice") |
| `session_id` | string | No | Conversation session ID for continuity (format: `bridget-{UUID}`). Create a new one if not provided. |

## Response — Primary (audio)

```
HTTP 200
Content-Type: audio/ogg
X-Transcript-Text: "What the user said"
X-Response-Text: "What the agent replied"
X-Session-Id: "bridget-550e8400-..."
Body: raw OGG/Opus audio bytes
```

## Response — Fallback (text, if TTS fails)

```
HTTP 200
Content-Type: application/json
X-Transcript-Text: "What the user said"
X-Response-Text: "What the agent replied"
X-Session-Id: "bridget-550e8400-..."
Body: {"text": "Agent's text response"}
```

Bridget handles both. Audio is played directly. Text is read aloud via on-device TTS.

## Response — Bridget also accepts these formats

Bridget's parser is lenient. These all work:

| Content-Type | Body | Behavior |
|-------------|------|----------|
| `audio/*` or `*ogg*` | Raw audio bytes | Plays directly |
| `application/json` | `{"text": "..."}` | Reads aloud |
| `application/json` | `{"response": "..."}` | Reads aloud |
| `application/json` | `{"message": "..."}` | Reads aloud |
| `application/json` | `{"choices": [{"message": {"content": "..."}}]}` | OpenAI format, reads aloud |
| `application/json` | `{"audio_url": "https://..."}` | Downloads and plays |
| `text/plain` | Raw text | Reads aloud |

## Errors

| Code | Body | Meaning |
|------|------|---------|
| 400 | `{"error": "Transcription failed"}` | Couldn't understand the audio |
| 401 | `{"error": "Invalid API key"}` | Wrong or missing API key |
| 502 | `{"error": "Agent unreachable"}` | Backend agent didn't respond |

## Connection Test

Bridget tests the endpoint by sending a minimal silent audio file (20ms of silence encoded as OGG/Opus). A successful response (any 200) confirms the full pipeline works.

## Common Pitfalls (from real-world testing)

These bugs were discovered during live integration testing. If you're building the endpoint natively, watch for every one of these.

### Async event loop blocking (critical)

STT (Whisper) and TTS are heavy CPU operations. If you call them synchronously inside an async handler (FastAPI, aiohttp), they block the entire event loop and the server hangs forever. Bridget times out after 180 seconds.

**Fix:** Wrap all synchronous calls in `asyncio.to_thread()`:
```python
text = await asyncio.to_thread(transcribe_audio, audio_path)
audio = await asyncio.to_thread(text_to_speech, response_text)
```

### Model parameter must be explicit

Don't create your LLM agent without specifying a model. Sending `model: ""` to the API returns HTTP 400. Always pass the model name explicitly.

### Check your tool signatures

Your STT and TTS tools have specific function signatures. Don't guess — check them. Common mistake: calling `tts(text, output_format="ogg")` when the function expects `tts(text, output_path="/tmp/out.ogg")`.

### Parse tool output formats

Internal tools often return JSON strings, not Python dicts. If your TTS tool returns `'{"path": "/tmp/audio.ogg"}'`, you need `json.loads()` before calling `.get()` on it.

### Test each stage independently

Before testing the full pipeline, verify each stage works on its own:
1. Can you transcribe an OGG file? (STT)
2. Can you get a text response from your LLM? (Agent)
3. Can you generate an audio file from text? (TTS)

If any stage fails, the endpoint will fail. Debug them separately.

### Server binding and network access

- **Host must be `0.0.0.0`**, not `127.0.0.1` or `localhost`. Otherwise only the local machine can connect.
- **Firewall:** macOS blocks incoming connections by default. Allow your Python process or disable the firewall.
- **Remote access:** If Bridget isn't on the same network (which is the common case — CarPlay, cellular), use `ngrok http 8080` or deploy to a VPS with a public IP.
- **Full restart required** after config changes. Don't just reload — kill the old process and start fresh.

## Notes

- **Timeout:** Bridget waits up to 180 seconds for a response. The STT → LLM → TTS pipeline can be slow.
- **Audio format:** Bridget always sends OGG/Opus at 48kHz mono. Your STT must handle this format.
- **Session continuity:** If you return `X-Session-Id`, Bridget uses it on subsequent requests. This lets the agent maintain conversation history.
- **System prompt:** This is the user's response preference, not a personality prompt. Common values: "Always respond with a voice message, never text." or empty (let agent decide).
