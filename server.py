"""
bridget-voice-server — Give any AI agent a voice endpoint for Bridget.

Accepts audio from Bridget, transcribes it, forwards text to your agent's API,
generates a voice reply, and returns it. One file. Zero cost out of the box.

Usage:
    cp config.env.example .env   # configure your agent
    pip install -r requirements.txt
    python server.py
"""

import asyncio
import importlib
import io
import os
import tempfile
import time
import uuid
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse, Response
import uvicorn

load_dotenv()

# --- Config ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
API_KEY = os.getenv("API_KEY", "")  # Key Bridget must send (empty = no auth)
AGENT_BACKEND = os.getenv("AGENT_BACKEND", "openai_compatible")
STT_PROVIDER = os.getenv("STT_PROVIDER", "whisper_local")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge_tts")
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-GuyNeural")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
SESSION_TTL = int(os.getenv("SESSION_TTL", "3600"))  # seconds

# --- Session store ---
sessions: dict[str, dict] = {}  # session_id -> {"history": [...], "last_active": float}

app = FastAPI(title="bridget-voice-server")

# --- Lazy-loaded providers ---
_whisper_model = None
_backend = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model(WHISPER_MODEL)
    return _whisper_model


def get_backend():
    global _backend
    if _backend is None:
        mod = importlib.import_module(f"backends.{AGENT_BACKEND}")
        _backend = mod
    return _backend


# --- STT ---
def transcribe_whisper_local(audio_path: str) -> str:
    model = get_whisper_model()
    result = model.transcribe(audio_path)
    return result.get("text", "").strip()


async def transcribe_openai(audio_path: str) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("STT_API_KEY"))
    with open(audio_path, "rb") as f:
        result = await client.audio.transcriptions.create(model="whisper-1", file=f)
    return result.text.strip()


async def transcribe_deepgram(audio_path: str) -> str:
    import httpx
    api_key = os.getenv("STT_API_KEY")
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.deepgram.com/v1/listen?model=nova-2",
            headers={"Authorization": f"Token {api_key}", "Content-Type": "audio/ogg"},
            content=audio_bytes,
            timeout=30.0,
        )
        data = resp.json()
    return data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()


async def transcribe(audio_path: str) -> str:
    if STT_PROVIDER == "whisper_local":
        return await asyncio.to_thread(transcribe_whisper_local, audio_path)
    elif STT_PROVIDER == "openai":
        return await transcribe_openai(audio_path)
    elif STT_PROVIDER == "deepgram":
        return await transcribe_deepgram(audio_path)
    else:
        raise ValueError(f"Unknown STT provider: {STT_PROVIDER}")


# --- TTS ---
async def tts_edge(text: str) -> bytes:
    import edge_tts
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


async def tts_openai(text: str) -> bytes:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("TTS_API_KEY"))
    voice = os.getenv("TTS_OPENAI_VOICE", "alloy")
    response = await client.audio.speech.create(model="tts-1", voice=voice, input=text,
                                                 response_format="opus")
    return response.content


async def tts_elevenlabs(text: str) -> bytes:
    import httpx
    api_key = os.getenv("TTS_API_KEY")
    voice_id = os.getenv("TTS_ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_monolingual_v1",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            timeout=30.0,
        )
        return resp.content


async def text_to_speech(text: str) -> tuple[bytes, str]:
    """Returns (audio_bytes, media_type)."""
    if TTS_PROVIDER == "edge_tts":
        return await tts_edge(text), "audio/mpeg"  # Edge-TTS outputs MP3
    elif TTS_PROVIDER == "openai":
        return await tts_openai(text), "audio/ogg"  # OpenAI TTS with opus format
    elif TTS_PROVIDER == "elevenlabs":
        return await tts_elevenlabs(text), "audio/mpeg"  # ElevenLabs outputs MP3
    else:
        raise ValueError(f"Unknown TTS provider: {TTS_PROVIDER}")


# --- Session management ---
def get_session(session_id: str) -> list[dict]:
    now = time.time()
    # Clean expired sessions
    expired = [k for k, v in sessions.items() if now - v["last_active"] > SESSION_TTL]
    for k in expired:
        del sessions[k]
    # Get or create
    if session_id not in sessions:
        sessions[session_id] = {"history": [], "last_active": now}
    sessions[session_id]["last_active"] = now
    return sessions[session_id]["history"]


# --- Routes ---
@app.get("/health")
async def health():
    return {"status": "ok", "server": "bridget-voice-server", "backend": AGENT_BACKEND}


@app.post("/v1/audio/voice_chat")
async def voice_chat(
    audio: UploadFile = File(...),
    system_prompt: str = Form(default=""),
    session_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    # Auth check
    if API_KEY:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if token != API_KEY:
            return JSONResponse(status_code=401, content={"error": "Invalid API key"})

    # Session
    if not session_id:
        session_id = f"bridget-{uuid.uuid4()}"
    history = get_session(session_id)

    # Save audio to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    try:
        content = await audio.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()

        # 1. Transcribe
        try:
            input_text = await transcribe(tmp.name)
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": f"Transcription failed: {e}"})

        if not input_text:
            return JSONResponse(status_code=400, content={"error": "Transcription returned empty text"})

    finally:
        os.unlink(tmp.name)

    # 2. Send to agent
    history.append({"role": "user", "content": input_text})
    try:
        backend = get_backend()
        response_text = await asyncio.to_thread(
            backend.send_message, input_text, history, system_prompt
        )
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Agent error: {e}"})

    history.append({"role": "assistant", "content": response_text})

    # Sanitize header values — newlines in LLM output crash HTTP frameworks
    safe_input = input_text.replace("\n", " ").replace("\r", " ").replace("\0", "")
    safe_response = response_text.replace("\n", " ").replace("\r", " ").replace("\0", "")

    # 3. TTS
    try:
        audio_bytes, media_type = await text_to_speech(response_text)
    except Exception:
        # Fallback: return text if TTS fails
        return JSONResponse(
            content={"text": response_text},
            headers={"X-Transcript-Text": safe_input, "X-Response-Text": safe_response,
                     "X-Session-Id": session_id},
        )

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={
            "X-Transcript-Text": safe_input,
            "X-Response-Text": safe_response,
            "X-Session-Id": session_id,
        },
    )


if __name__ == "__main__":
    print(f"bridget-voice-server starting on {HOST}:{PORT}")
    print(f"  Backend: {AGENT_BACKEND}")
    print(f"  STT: {STT_PROVIDER} (model: {WHISPER_MODEL})")
    print(f"  TTS: {TTS_PROVIDER} (voice: {TTS_VOICE})")
    print(f"  Auth: {'required' if API_KEY else 'none'}")
    uvicorn.run(app, host=HOST, port=int(PORT))
