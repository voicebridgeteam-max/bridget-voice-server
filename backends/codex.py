"""
Backend: OpenAI Codex CLI

For users running Codex with an existing authenticated session.
"""

import os
import subprocess


CODEX_PATH = os.getenv("CODEX_PATH", "codex")


def send_message(text: str, history: list[dict], system_prompt: str = "") -> str:
    prompt = text
    if system_prompt:
        prompt = f"{system_prompt}\n\n{text}"

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
