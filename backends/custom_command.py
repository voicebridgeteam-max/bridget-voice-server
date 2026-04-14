"""
Backend: Custom Command

Escape hatch for any agent with a CLI. Pipes transcribed text to stdin,
reads response from stdout. Works with anything.

Set AGENT_COMMAND in .env to your agent's command.
Example: AGENT_COMMAND=python my_agent.py
"""

import os
import subprocess


AGENT_COMMAND = os.getenv("AGENT_COMMAND", "")


def send_message(text: str, history: list[dict], system_prompt: str = "") -> str:
    if not AGENT_COMMAND:
        raise RuntimeError("AGENT_COMMAND not set in .env")

    prompt = text
    if system_prompt:
        prompt = f"{system_prompt}\n\n{text}"

    result = subprocess.run(
        AGENT_COMMAND,
        shell=True,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        error = result.stderr.strip() or "Command returned non-zero exit code"
        raise RuntimeError(f"Command error: {error}")

    response = result.stdout.strip()
    if not response:
        raise RuntimeError("Command returned empty response")

    return response
