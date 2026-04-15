"""
Backend: Claude Code CLI

For users running Claude Code with OAuth (Max subscription).
No API key needed — uses the existing authenticated session.
Uses --session-id and --resume for conversation memory across turns.
"""

import os
import subprocess

CLAUDE_CODE_PATH = os.getenv("CLAUDE_CODE_PATH", "claude")

# Context so Claude knows it's in a voice conversation, not a coding session
BASE_CONTEXT = """You are having a voice conversation through Bridget, a voice app. \
The user is speaking to you and will hear your reply read aloud. \
Respond naturally and conversationally. Keep replies concise — they'll be spoken, not read. \
Do NOT mention that you can't generate audio, create files, or access tools. \
Just respond to what the user said as a helpful voice assistant."""

# Track which sessions have been started
_started_sessions: set = set()


def send_message(text: str, history: list, system_prompt: str = "", session_id: str = "") -> str:
    context = BASE_CONTEXT
    if system_prompt:
        context = f"{BASE_CONTEXT}\n\nAdditional instruction: {system_prompt}"

    cmd = [CLAUDE_CODE_PATH, "--print"]

    if session_id and session_id in _started_sessions:
        # Resume existing session — Claude loads full conversation history
        cmd.extend(["--resume", session_id])
    elif session_id:
        # First message in this session — create with specific ID and system prompt
        cmd.extend(["--session-id", session_id])
        cmd.extend(["--system-prompt", context])
        _started_sessions.add(session_id)

    cmd.extend(["-p", text])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        error = result.stderr.strip() or "Claude Code returned non-zero exit code"
        raise RuntimeError(f"Claude Code error: {error}")

    response = result.stdout.strip()
    if not response:
        raise RuntimeError("Claude Code returned empty response")

    return response
