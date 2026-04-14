"""
Backend: Claude Code CLI

For users running Claude Code with OAuth (Max subscription).
No API key needed — uses the existing authenticated session.
"""

import os
import subprocess


CLAUDE_CODE_PATH = os.getenv("CLAUDE_CODE_PATH", "claude")


def send_message(text: str, history: list[dict], system_prompt: str = "") -> str:
    prompt = text
    if system_prompt:
        prompt = f"{system_prompt}\n\n{text}"

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
