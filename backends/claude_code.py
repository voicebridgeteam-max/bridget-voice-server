"""
Backend: Claude Code CLI

For users running Claude Code with OAuth (Max subscription).
No API key needed — uses the existing authenticated session.
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


def send_message(text: str, history: list[dict], system_prompt: str = "") -> str:
    context = BASE_CONTEXT
    if system_prompt:
        context = f"{BASE_CONTEXT}\n\nAdditional instruction: {system_prompt}"

    prompt = f"{context}\n\nUser said: {text}"

    result = subprocess.run(
        [CLAUDE_CODE_PATH, "--print", "-p", prompt],
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
