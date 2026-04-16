# Build a Voice Endpoint for Bridget (Native Implementation)

If your agent already runs an HTTP server (FastAPI, aiohttp, Flask, Express), you can add the voice endpoint directly. No bridge server needed.

This guide walks you through building it step by step. Each step has a verification command. **Do not skip the verifications** — finding bugs one at a time after a full deployment wastes hours. We learned this the hard way.

If you just want to deploy the bridge server instead, see the [README](README.md).

---

## Prerequisites

Before you start, verify you have:

- [ ] **ffmpeg** installed — Whisper requires it for audio decoding. Install: `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Linux). Verify: `ffmpeg -version`. **This is the #1 missing dependency.**
- [ ] An HTTP server framework (FastAPI, aiohttp, Flask, etc.)
- [ ] An STT engine (Whisper, Deepgram, etc.) — test it: can you transcribe an audio file?
- [ ] A TTS engine (Edge-TTS, ElevenLabs, OpenAI TTS, etc.) — test it: can you generate audio from text?
- [ ] Your AI agent/LLM callable from code — test it: can you get a text response from a prompt?
- [ ] **ngrok** installed and authenticated — for remote access from Bridget. See [README](README.md#before-you-start).

If any of these don't work yet, fix them first. The voice endpoint chains all four together.

---

## Step 1: Add the Route Skeleton

Add a POST route at `/v1/audio/voice_chat` that accepts multipart form data.

```python
from fastapi import FastAPI, File, Form, UploadFile, Header
from fastapi.responses import Response, JSONResponse

app = FastAPI()

@app.post("/v1/audio/voice_chat")
async def voice_chat(
    audio: UploadFile = File(...),
    system_prompt: str = Form(default=""),
    session_id: str = Form(default=""),
    authorization: str | None = Header(default=None),
):
    return JSONResponse({"status": "ok", "message": "Route works"})
```

**Server binding — this is critical:**
- Host MUST be `0.0.0.0`, not `127.0.0.1` or `localhost`
- If your phone and server are on different networks (which is the normal case — CarPlay, cellular), you'll need ngrok or a public IP

If you use Hermes/OpenClaw: host and port in `config.yaml` are **silently ignored** by the config parser. Set them in your `.env` file:
```
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8080
```

**Verify:**
```bash
curl -X POST http://localhost:8080/v1/audio/voice_chat \
  -F "audio=@test.ogg" -w "\nStatus: %{http_code}\n"
# Expected: Status: 200
```

If you get `404`: wrong path. If you get `Connection refused`: server isn't running or wrong port.

---

## Step 2: Add Transcription (STT)

Save the uploaded audio to a temp file, transcribe it, return the text.

```python
import asyncio
import tempfile
import os

@app.post("/v1/audio/voice_chat")
async def voice_chat(
    audio: UploadFile = File(...),
    system_prompt: str = Form(default=""),
    session_id: str = Form(default=""),
    authorization: str | None = Header(default=None),
):
    # Save audio to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    try:
        content = await audio.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()

        # Transcribe — MUST use asyncio.to_thread for sync STT calls
        try:
            text = await asyncio.to_thread(transcribe_audio, tmp.name)
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": f"Transcription failed: {e}"})

        if not text:
            return JSONResponse(status_code=400, content={"error": "Empty transcription"})

        return JSONResponse({"transcript": text})
    finally:
        os.unlink(tmp.name)
```

**WARNING — asyncio.to_thread is mandatory:**
Whisper and most STT engines are synchronous CPU-heavy operations. If you call them directly in an async handler, they block the entire event loop. The server hangs. Bridget times out after 180 seconds. You'll see no error — just silence.

Always wrap sync calls:
```python
# WRONG — blocks event loop:
text = transcribe_audio(path)

# RIGHT — runs in thread pool:
text = await asyncio.to_thread(transcribe_audio, path)
```

**WARNING — imports must be at module level:**
Don't import inside a `try` or `finally` block and use outside it. Run `python -c "from your_module import *"` to catch import errors before restarting your server.

**Verify:**
```bash
curl -X POST http://localhost:8080/v1/audio/voice_chat \
  -F "audio=@test.ogg" -w "\nStatus: %{http_code}\n"
# Expected: Status: 200, body: {"transcript": "..."}
```

If you get `400 Transcription failed`: your STT isn't working. Test it independently.

---

## Step 3: Add Agent Execution

Pass the transcribed text to your agent/LLM. Get a text response.

```python
        # After transcription succeeds:

        # Load session history (BOTH load AND save must be wired up)
        history = load_session_history(session_id)  # Your session DB
        history.append({"role": "user", "content": text})

        # Call your agent — wrap in asyncio.to_thread if synchronous
        response_text = await asyncio.to_thread(
            run_agent, text, history, system_prompt
        )

        # Handle None responses
        response_text = response_text or ""

        history.append({"role": "assistant", "content": response_text})
        save_session_history(session_id, history)  # Persist for next turn

        return JSONResponse({"response": response_text})
```

**WARNING — model parameter must be explicit:**
Don't create your agent without specifying a model name. Sending `model: ""` returns HTTP 400 from the LLM API.

**WARNING — handle None responses:**
`result.get("final_response", "")` returns `None` when the key exists with value None (common in error paths). Use:
```python
response_text = (result.get("final_response") or "")
```

**WARNING — load your agent's identity:**
Don't use flags like `skip_context_files=True` or `skip_memory=True`. These strip your agent's personality. It will respond as a generic base model instead of itself. Voice requests should load the same identity as other channels.

**WARNING — session management is two-part:**
1. **Load** history for the session_id before calling the agent
2. **Save** new messages after the agent responds

A common bug: the framework auto-saves (e.g., `persist_session=True`) but the handler doesn't pass the DB instance to the agent constructor. The save method silently no-ops. History loads fine, but new turns vanish.

**WARNING — check attribute and method names:**
Python silently ignores wrong attribute assignments. If you write `agent.system_prompt_override = "..."` but the actual attribute is `ephemeral_system_prompt`, nothing errors — it just doesn't work. Verify against the actual class API.

**Verify:**
```bash
curl -X POST http://localhost:8080/v1/audio/voice_chat \
  -F "audio=@test.ogg" -w "\nStatus: %{http_code}\n"
# Expected: Status: 200, body: {"response": "agent's text reply"}
```

---

## Step 4: Add TTS and Return Audio

Convert the response text to audio. Return it with the correct headers.

```python
        # After getting response_text:

        # TTS — MUST use asyncio.to_thread for sync TTS calls
        tmp_out = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        try:
            await asyncio.to_thread(
                text_to_speech, response_text, tmp_out.name
            )
            with open(tmp_out.name, "rb") as f:
                audio_bytes = f.read()
        finally:
            os.unlink(tmp_out.name)  # Clean up BOTH temp files

        # Detect actual format and set correct Content-Type
        content_type = detect_content_type(tmp_out.name)

        # Sanitize header values — newlines and non-Latin-1 chars crash HTTP frameworks
        safe_transcript = text.replace("\n", " ").replace("\r", " ").replace("\0", "")
        safe_transcript = safe_transcript.encode("latin-1", errors="replace").decode("latin-1")
        safe_response = response_text.replace("\n", " ").replace("\r", " ").replace("\0", "")
        safe_response = safe_response.encode("latin-1", errors="replace").decode("latin-1")

        return Response(
            content=audio_bytes,
            media_type=content_type,
            headers={
                "X-Transcript-Text": safe_transcript,
                "X-Response-Text": safe_response,
                "X-Session-Id": session_id,
            },
        )
```

**WARNING — Content-Type must match actual bytes:**
If your TTS outputs MP3, return `audio/mpeg`. If it outputs OGG, return `audio/ogg`. A mismatch causes playback failures in Bridget — it falls back to reading text aloud.

**WARNING — sanitize response headers (two issues):**
LLM responses contain newlines AND non-ASCII characters (em dashes —, smart quotes, emoji). Both crash HTTP headers:
1. Newlines (`\n`, `\r`) are rejected as potential header injection
2. Non-Latin-1 characters (anything outside 0-255) crash Starlette/uvicorn silently

```python
def safe_header(s: str) -> str:
    s = s.replace("\n", " ").replace("\r", " ").replace("\0", "")
    return s.encode("latin-1", errors="replace").decode("latin-1")
```

**WARNING — check your TTS function's actual signature:**
Don't guess the arguments. If the function expects `tts(text, output_path)`, don't call `tts(text, output_format="ogg")`. Wrong keyword arguments cause TypeErrors.

**WARNING — parse tool outputs:**
If your TTS tool returns a JSON string (common in agent frameworks), parse it before calling `.get()`:
```python
import json
result = json.loads(tts_tool(text))  # String → dict
path = result.get("path")
```

**WARNING — clean up ALL temp files:**
Create temp files for both input (STT) and output (TTS). Clean up both in `finally` blocks. Missed temp files leak to disk on every request.

**TTS fallback — if TTS fails, return text:**
```python
        except Exception:
            return JSONResponse(
                content={"text": response_text},
                headers={...}
            )
```
Bridget reads text aloud as a fallback if it doesn't receive audio.

**Verify:**
```bash
curl -X POST http://localhost:8080/v1/audio/voice_chat \
  -F "audio=@test.ogg" -o response.mp3 -D - -w "\nStatus: %{http_code}\n"
# Expected: Status: 200, Content-Type: audio/mpeg, audio file saved
# Play it: afplay response.mp3 (macOS) or ffplay response.mp3
```

Check the response headers — you should see `x-transcript-text`, `x-response-text`, and `x-session-id`.

---

## Step 5: Add Auth (Optional)

If you want to require an API key:

```python
    # At the top of the handler:
    if REQUIRED_API_KEY:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if token != REQUIRED_API_KEY:
            return JSONResponse(status_code=401, content={"error": "Invalid API key"})
```

Bridget sends `Authorization: Bearer {key}` if the user entered a key.

---

## Step 6: Network Access

Your endpoint must be reachable from Bridget (an iPhone, usually on a different network).

**Local network (same WiFi):**
1. Bind to `0.0.0.0` (not `127.0.0.1`)
2. Find your IP: `ifconfig en0 | grep "inet "` (macOS) or `hostname -I` (Linux)
3. Test from phone: open `http://YOUR_IP:8080/health` in Safari
4. If blocked: check your firewall settings. Allow Python or your server process.

**Remote access (different network, CarPlay, cellular):**

Use the `connect.sh` script from this repo — it starts ngrok and shows a QR code that auto-connects Bridget:

```bash
# Clone this repo if you haven't:
git clone https://github.com/voicebridgeteam-max/bridget-voice-server
# Run connect.sh with your agent's port:
./bridget-voice-server/connect.sh 8080
```

The QR code encodes a deep link — scan it with your iPhone camera and Bridget opens and connects automatically. The script also copies the URL to your clipboard.

**Or manually:** `ngrok http 8080` and paste the URL in Bridget.

**ngrok gotcha:** When you restart your server, the ngrok tunnel goes stale. Restart ngrok too.

---

## Step 7: Full Pipeline Test

See [TESTING.md](TESTING.md) for complete test commands including session continuity, remote access, and Bridget's connection test simulation.

Quick smoke test:
```bash
curl -X POST http://localhost:8080/v1/audio/voice_chat \
  -F "audio=@test.ogg" \
  -F "session_id=smoke-test" \
  -o response.mp3 -D - -w "\nStatus: %{http_code}\nTime: %{time_total}s\n"
```

If you get `200` with audio bytes and valid headers, you're ready to connect from Bridget.

---

## Complete Reference Implementation

Here's a minimal correct handler (~50 lines) with all pitfalls addressed:

```python
import asyncio, json, os, tempfile, uuid
from fastapi import FastAPI, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse, Response

app = FastAPI()
sessions = {}  # session_id -> [{"role": "user/assistant", "content": "..."}]

@app.post("/v1/audio/voice_chat")
async def voice_chat(
    audio: UploadFile = File(...),
    system_prompt: str = Form(default=""),
    session_id: str = Form(default=""),
    authorization: str | None = Header(default=None),
):
    if not session_id:
        session_id = f"bridget-{uuid.uuid4()}"

    # 1. Save and transcribe
    tmp_in = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    try:
        tmp_in.write(await audio.read())
        tmp_in.close()
        text = await asyncio.to_thread(your_stt_function, tmp_in.name)
        if not text:
            return JSONResponse(status_code=400, content={"error": "Empty transcription"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"STT failed: {e}"})
    finally:
        os.unlink(tmp_in.name)

    # 2. Run agent with session history
    history = sessions.get(session_id, [])
    history.append({"role": "user", "content": text})
    try:
        response_text = await asyncio.to_thread(your_agent_function, text, history, system_prompt)
        response_text = response_text or ""
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Agent error: {e}"})
    history.append({"role": "assistant", "content": response_text})
    sessions[session_id] = history

    # 3. TTS
    safe_in = text.replace("\n", " ").replace("\r", " ").replace("\0", "")
    safe_out = response_text.replace("\n", " ").replace("\r", " ").replace("\0", "")
    headers = {"X-Transcript-Text": safe_in, "X-Response-Text": safe_out, "X-Session-Id": session_id}

    tmp_out = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    try:
        await asyncio.to_thread(your_tts_function, response_text, tmp_out.name)
        with open(tmp_out.name, "rb") as f:
            audio_bytes = f.read()
        return Response(content=audio_bytes, media_type="audio/mpeg", headers=headers)
    except Exception:
        return JSONResponse(content={"text": response_text}, headers=headers)
    finally:
        os.unlink(tmp_out.name)
```

Replace `your_stt_function`, `your_agent_function`, and `your_tts_function` with your actual implementations. The structure handles all 21 known pitfalls.

---

## Before You Deploy Checklist

Read the entire handler top to bottom. Trace every variable, every import, every function call. The "fix one bug → restart → find next bug" loop wastes 30+ minutes. One careful read catches them all.

- [ ] All sync calls wrapped in `asyncio.to_thread()`
- [ ] All imports at module level (not inside try/finally)
- [ ] Model parameter explicitly set
- [ ] None responses handled with `(x or "")`
- [ ] Agent identity/context files loaded (no skip flags)
- [ ] Session history: both load AND save wired up
- [ ] Correct attribute/method names (verified against actual API)
- [ ] TTS function signature matches your actual tool
- [ ] Tool outputs parsed (JSON strings → dicts)
- [ ] Content-Type matches actual audio format
- [ ] Response headers sanitized (no newlines, no non-Latin-1 characters)
- [ ] All temp files cleaned up in finally blocks
- [ ] Host bound to `0.0.0.0`
- [ ] Server fully restarted (not just reloaded)
- [ ] Dry import test: `python -c "from your_module import *"`
