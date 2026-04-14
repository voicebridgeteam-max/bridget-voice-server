"""
Backend: OpenAI-compatible API

Works with: OpenAI, Anthropic (via proxy), Groq, Ollama, LM Studio,
            llama.cpp, vLLM, or any endpoint that speaks the OpenAI chat format.
"""

import os
import requests

AGENT_API_URL = os.getenv("AGENT_API_URL", "http://localhost:11434/v1/chat/completions")
AGENT_API_KEY = os.getenv("AGENT_API_KEY", "")
AGENT_MODEL = os.getenv("AGENT_MODEL", "llama3")


def send_message(text: str, history: list[dict], system_prompt: str = "") -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)

    headers = {"Content-Type": "application/json"}
    if AGENT_API_KEY:
        headers["Authorization"] = f"Bearer {AGENT_API_KEY}"

    resp = requests.post(
        AGENT_API_URL,
        headers=headers,
        json={"model": AGENT_MODEL, "messages": messages},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    # Standard OpenAI format
    if "choices" in data:
        return data["choices"][0]["message"]["content"].strip()

    # Anthropic format (via compatible proxy)
    if "content" in data:
        content = data["content"]
        if isinstance(content, list):
            return content[0].get("text", "").strip()
        return str(content).strip()

    # Fallback: look for common keys
    for key in ("response", "text", "message", "output"):
        if key in data:
            return str(data[key]).strip()

    raise ValueError(f"Could not parse agent response: {list(data.keys())}")
