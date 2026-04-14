# Testing Your Voice Endpoint

Run these tests before connecting Bridget. Each test verifies one stage of the pipeline. If any stage fails, fix it before moving on.

---

## 1. Generate Test Audio

You need a test OGG/Opus file. Any of these methods work:

**Option A — ffmpeg (recommended):**
```bash
ffmpeg -f lavfi -i anullsrc=r=48000:cl=mono -t 1 -c:a libopus test.ogg
```
This creates 1 second of silence in the exact format Bridget sends.

**Option B — Record with your mic:**
```bash
ffmpeg -f avfoundation -i ":0" -t 3 -c:a libopus -ar 48000 -ac 1 test.ogg
```
Records 3 seconds from your default mic (macOS). On Linux, replace `-f avfoundation -i ":0"` with `-f pulse -i default`.

**Option C — Use any existing OGG file.** Whisper handles most audio formats.

---

## 2. Health Check

```bash
curl http://localhost:8080/health
```

**Expected:**
```json
{"status": "ok", "server": "bridget-voice-server", "backend": "openai_compatible"}
```

**If this fails:** The server isn't running. Check `python server.py` output for errors.

---

## 3. Full Pipeline Test

```bash
curl -X POST http://localhost:8080/v1/audio/voice_chat \
  -F "audio=@test.ogg" \
  -F "system_prompt=Reply briefly." \
  -F "session_id=test-session-1" \
  -o response.mp3 \
  -D response_headers.txt \
  -w "\nHTTP Status: %{http_code}\nTime: %{time_total}s\n"
```

**Expected output:**
```
HTTP Status: 200
Time: 8.234s
```

**Check the headers:**
```bash
cat response_headers.txt
```

You should see:
```
HTTP/1.1 200 OK
content-type: audio/mpeg
x-transcript-text: (what you said in the audio)
x-response-text: (what the agent replied)
x-session-id: test-session-1
```

**Play the response:**
```bash
ffplay response.mp3    # or: afplay response.mp3 (macOS)
```

You should hear the agent's voice reply.

---

## 4. Test Session Continuity

Send two requests with the same session_id:

**Request 1:**
```bash
curl -X POST http://localhost:8080/v1/audio/voice_chat \
  -F "audio=@test.ogg" \
  -F "system_prompt=My name is Jack. Remember this." \
  -F "session_id=test-session-2" \
  -o /dev/null -w "Status: %{http_code}\n"
```

**Request 2:**
```bash
curl -X POST http://localhost:8080/v1/audio/voice_chat \
  -F "audio=@test.ogg" \
  -F "system_prompt=What is my name?" \
  -F "session_id=test-session-2" \
  -D - -o /dev/null 2>/dev/null | grep x-response-text
```

The `x-response-text` header should mention "Jack." If it doesn't, session history isn't being loaded or saved correctly.

---

## 5. Test from Another Device

From your phone or another computer on the same network:

```bash
curl http://YOUR_MAC_IP:8080/health
```

**If this fails but localhost works:**
- Host is bound to `127.0.0.1` instead of `0.0.0.0` — check your `.env`
- Firewall is blocking port 8080 — allow Python or disable firewall
- Devices are on different networks

**If using ngrok:**
```bash
ngrok http 8080
# Then test with the ngrok URL:
curl https://your-ngrok-url.ngrok-free.app/health
```

---

## 6. Test with Bridget's Connection Test

Bridget tests the endpoint by sending 20ms of silence. Simulate this:

```bash
# Generate minimal silent audio (like Bridget does)
ffmpeg -f lavfi -i anullsrc=r=48000:cl=mono -t 0.02 -c:a libopus silent.ogg 2>/dev/null

curl -X POST http://localhost:8080/v1/audio/voice_chat \
  -F "audio=@silent.ogg" \
  -F "system_prompt=This is a connection test from Bridget. Reply with any short message to confirm." \
  -w "\nStatus: %{http_code}\n" -o /dev/null
```

Any 200 response means the connection test will pass in Bridget.

---

## Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Connection refused` | Server not running | Start with `python server.py` |
| `404 Not Found` | Wrong URL path | Use `/v1/audio/voice_chat` |
| `405 Method Not Allowed` | Used GET instead of POST | Use `-X POST` |
| `400 Transcription failed` | Whisper can't process the audio | Check Whisper is installed, audio is valid OGG |
| `502 Agent error` | Backend can't reach your agent | Check `AGENT_API_URL` in `.env`, verify agent is running |
| `401 Invalid API key` | API_KEY set but not sent | Add `-H "Authorization: Bearer YOUR_KEY"` |
| Hangs forever | Sync calls blocking event loop | Wrap STT/TTS in `asyncio.to_thread()` |
| Response is JSON, not audio | TTS failed, fell back to text | Check TTS is configured, test TTS independently |
| Headers have `null` values | Agent returned None | Use `(result.get("key") or "")` |
