# Bridget Voice Endpoint Specification

This is the protocol that Bridget (the iOS app) speaks. It's a reference for what to send and what to expect back.

- **Building this natively?** See [NATIVE_IMPLEMENTATION.md](NATIVE_IMPLEMENTATION.md) for a step-by-step build guide with all known pitfalls baked in.
- **Using the bridge server?** It already implements this protocol. You don't need to do anything.

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
Content-Type: audio/mpeg (or audio/ogg — match your TTS output format)
X-Transcript-Text: "What the user said"
X-Response-Text: "What the agent replied"
X-Session-Id: "bridget-550e8400-..."
Body: raw audio bytes
```

## Response — Fallback (text, if TTS fails)

```
HTTP 200
Content-Type: application/json
{"text": "Agent's text response"}
```

Bridget handles both. Audio is played directly. Text is read aloud via on-device TTS.

## Response — Bridget also accepts these formats

Bridget's parser is lenient. These all work:

| Content-Type | Body | Behavior |
|-------------|------|----------|
| `audio/*` | Raw audio bytes | Plays directly |
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

## Notes

- **Timeout:** Bridget waits up to 180 seconds for a response. The STT → LLM → TTS pipeline can be slow.
- **Audio format:** Bridget always sends OGG/Opus at 48kHz mono. Your STT must handle this format.
- **Content-Type:** Must match the actual audio format your TTS produces. MP3 → `audio/mpeg`. OGG → `audio/ogg`.
- **Header values:** Sanitize `X-Transcript-Text` and `X-Response-Text` — replace newlines with spaces. Multi-line LLM output in headers crashes most HTTP frameworks.
- **Session continuity:** If you return `X-Session-Id`, Bridget uses it on subsequent requests for conversation history.
- **System prompt:** This is the user's response preference, not a personality prompt. Common values: "Always respond with a voice message, never text." or empty (let agent decide).
- **Testing:** See [TESTING.md](TESTING.md) for curl commands to verify your endpoint.
