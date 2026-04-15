"""
Backend: OpenAI Codex CLI

For users running Codex with an existing authenticated session.
"""

import os
import subprocess


CODEX_PATH = os.getenv("CODEX_PATH", "codex")


BASE_CONTEXT = """You are having a voice conversation through Bridget, a voice app. \
The user is speaking to you and will hear your reply read aloud. \
Respond naturally and conversationally. Keep replies concise — they'll be spoken, not read. \
Do NOT mention that you can't generate audio, create files, or access tools. \
Just respond to what the user said as a helpful voice assistant."""


def send_message(text: str, history: list, system_prompt: str = "", session_id: str = "") -> str:
    context = BASE_CONTEXT
    if system_prompt:
        context = f"{BASE_CONTEXT}\n\nAdditional instruction: {system_prompt}"

    prompt = f"{context}\n\nUser said: {text}"

    result = subprocess.run(
        [CODEX_PATH, "--quiet", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        error = result.stderr.strip() or "Codex returned non-zero exit code"
        raise RuntimeError(f"Codex error: {error}")

    response = result.stdout.strip()
    if not response:
        raise RuntimeError("Codex returned empty response")

    return response
