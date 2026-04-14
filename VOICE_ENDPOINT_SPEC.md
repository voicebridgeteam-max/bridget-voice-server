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

### Handle None responses from your agent

`result.get("final_response", "")` returns `None` when the key exists but the value is None — which happens in many error paths. This breaks TTS and sends `{"text": null}` to Bridget. Use `(result.get("final_response") or "")` to coalesce None to empty string.

### Check attribute/method names against your framework's actual API

Don't guess. If you think the attribute is `system_prompt_override`, verify it exists. A wrong attribute name silently does nothing in Python — no error, just ignored. Read the class source or docs.

### Clean up ALL temp files

The handler creates temp files for both input audio (STT) and output audio (TTS). Clean up both in a `finally` block. A missed temp file leaks to disk on every request.

### Verify imports at module level

Don't import inside a `try` or `finally` block and use it outside that scope. Run `python -c "from your_module import *"` to catch import errors without restarting the server. Import bugs caused 3 unnecessary restarts during our testing.

### Do a full trace before first deployment

Read the entire handler top to bottom. Trace every variable, every import, every function call. The "fix one bug → restart → find next bug" loop caused 6+ restarts over 30 minutes during our first integration. A single careful read-through catches them all. Only restart when you're confident the whole handler runs clean.

### Test each stage independently

Before testing the full pipeline, verify each stage works on its own:
1. Can you transcribe an OGG file? (STT)
2. Can you get a text response from your LLM? (Agent)
3. Can you generate an audio file from text? (TTS)

If any stage fails, the endpoint will fail. Debug them separately.

### Content-Type header must match actual audio bytes

If your TTS outputs MP3, return `Content-Type: audio/mpeg`, not `audio/ogg`. Bridget detects audio from the Content-Type header — a mismatch can cause playback to fail and fall back to reading text aloud. Detect the actual format from the file extension or magic bytes and set the header accordingly.

### Server binding and network access

- **Host must be `0.0.0.0`**, not `127.0.0.1` or `localhost`. Otherwise only the local machine can connect.
- **Firewall:** macOS blocks incoming connections by default. Allow your Python process or disable the firewall.
- **Remote access:** If Bridget isn't on the same network (which is the common case — CarPlay, cellular), use `ngrok http 8080` or deploy to a VPS with a public IP.
- **Full restart required** after config changes. Don't just reload — kill the old process and start fresh.

### ngrok tunnel goes stale after server restart

When you restart your server, ngrok's tunnel to the port goes stale (ERR_NGROK_3004). You must restart ngrok after restarting the server. For production, use a proper reverse proxy (nginx, caddy) or ngrok's paid tier with auto-reconnect.

### Sanitize response header values

`X-Transcript-Text` and `X-Response-Text` contain raw LLM text, which can include newlines (`\n`, `\r`) in multi-paragraph responses. Most HTTP frameworks (aiohttp, uvicorn) reject headers with newlines as a security measure (header injection). Replace newlines and null bytes with spaces before setting headers:

```python
safe_text = response_text.replace("\n", " ").replace("\r", " ").replace("\0", "")
```

Short single-line responses work fine. Multi-paragraph responses crash the server without this fix.

## Notes

- **Timeout:** Bridget waits up to 180 seconds for a response. The STT → LLM → TTS pipeline can be slow.
- **Audio format:** Bridget always sends OGG/Opus at 48kHz mono. Your STT must handle this format.
- **Session continuity:** If you return `X-Session-Id`, Bridget uses it on subsequent requests. This lets the agent maintain conversation history.
- **System prompt:** This is the user's response preference, not a personality prompt. Common values: "Always respond with a voice message, never text." or empty (let agent decide).
