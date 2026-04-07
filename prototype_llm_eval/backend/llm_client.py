from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def load_prompt_template(prompt_filename: str) -> str:
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / prompt_filename).read_text(encoding="utf-8")


def generate_json_with_ollama(prompt: str) -> dict[str, Any]:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=90)
    response.raise_for_status()
    body = response.json()
    raw = body.get("response", "{}").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama returned invalid JSON: {raw}") from exc
