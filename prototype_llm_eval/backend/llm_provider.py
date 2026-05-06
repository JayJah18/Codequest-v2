from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any

import google.generativeai as genai
import requests
from google.api_core import exceptions as google_api_exceptions


GEMINI_API_KEY_MISSING_MSG = (
    "GEMINI_API_KEY is not set. This provider expects a Gemini API key (Google AI Studio / Gemini API key) for "
    "API-key auth with google.generativeai — not Vertex AI, not a service account, and not an empty value. "
    "For local demo without Gemini, set QUESTION_GENERATION_PROVIDER=llama (and run Ollama), or set "
    "MARKING_PROVIDER/FEEDBACK_PROVIDER=llama for marking/feedback."
)


class GeminiProviderAuthError(RuntimeError):
    """Raised when the Gemini provider cannot authenticate (missing or rejected API key)."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _gemini_auth_failure_user_message(exc: BaseException) -> str:
    return (
        "Gemini authentication failed. This code path uses Gemini API-key auth (google.generativeai + "
        "Generative Language API), not Vertex AI or service accounts. "
        "Likely causes: missing GEMINI_API_KEY, invalid or revoked key, or a Google Cloud API key whose restrictions "
        "block generativelanguage.googleapis.com (use an AI Studio key, or allow 'Generative Language API', or "
        "temporarily use 'Don't restrict key' for local testing). "
        "For a local demo without Gemini, set QUESTION_GENERATION_PROVIDER=llama (and MARKING_PROVIDER/FEEDBACK_PROVIDER "
        "if marking should also avoid Gemini). "
        f"Underlying error: {exc!s}"
    )


def _is_gemini_auth_related_google_error(exc: BaseException) -> bool:
    if isinstance(exc, google_api_exceptions.Unauthenticated):
        return True
    if isinstance(exc, google_api_exceptions.PermissionDenied):
        return True
    if isinstance(exc, google_api_exceptions.InvalidArgument):
        s = str(exc).lower()
        return (
            "api_key_invalid" in s
            or "api key not valid" in s
            or "invalid api key" in s
            or ("api key" in s and "invalid" in s)
        )
    return False


class LLMProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError

    def generate_json(self, prompt: str, system_prompt: str | None = None) -> dict[str, Any]:
        retries = int(os.getenv("LLM_JSON_RETRIES", "3"))
        last = ""
        for _ in range(max(1, retries)):
            raw = self.generate_text(prompt, system_prompt=system_prompt)
            last = raw
            try:
                return extract_json_object(raw)
            except json.JSONDecodeError:
                repaired = self.generate_text(
                    f"Fix this into valid JSON only. No prose.\n\n{raw}",
                    system_prompt="You are a strict JSON repair assistant.",
                )
                last = repaired
                try:
                    return extract_json_object(repaired)
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"Model did not return valid JSON. Last output: {last[:700]}")


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        if not (api_key or "").strip():
            raise GeminiProviderAuthError(GEMINI_API_KEY_MISSING_MSG, status_code=503)
        genai.configure(api_key=api_key.strip())
        self.model_name = model_name
        self._model = genai.GenerativeModel(model_name=model_name)

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        if system_prompt:
            prompt = f"{system_prompt}\n\nUser:\n{prompt}"
        try:
            response = self._model.generate_content(prompt)
        except google_api_exceptions.GoogleAPICallError as exc:
            if _is_gemini_auth_related_google_error(exc):
                raise GeminiProviderAuthError(_gemini_auth_failure_user_message(exc), status_code=502) from exc
            raise
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Gemini returned empty response.")
        return text.strip()


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model_name: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        merged = prompt if not system_prompt else f"{system_prompt}\n\nUser:\n{prompt}"
        payload = {"model": self.model_name, "prompt": merged, "stream": False}
        r = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=180)
        r.raise_for_status()
        return str(r.json().get("response", "")).strip()


class MistralProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "mistral-small-latest") -> None:
        self.api_key = api_key
        self.model_name = model_name

    def generate_text(self, prompt: str, system_prompt: str | None = None) -> str:
        if not self.api_key:
            # fallback to local mistral via Ollama
            base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            local_model = os.getenv("MISTRAL_OLLAMA_MODEL", "mistral")
            return OllamaProvider(base, local_model).generate_text(prompt, system_prompt=system_prompt)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.model_name, "messages": messages, "temperature": 0.2}
        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
        r.raise_for_status()
        data = r.json()
        return str(data["choices"][0]["message"]["content"]).strip()


def get_provider(name: str) -> LLMProvider:
    key = name.strip().lower()
    if key == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise GeminiProviderAuthError(GEMINI_API_KEY_MISSING_MSG, status_code=503)
        return GeminiProvider(
            api_key=api_key,
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        )
    if key == "llama":
        return OllamaProvider(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model_name=os.getenv("OLLAMA_MODEL", "llama3.1"),
        )
    if key == "mistral":
        return MistralProvider(
            api_key=os.getenv("MISTRAL_API_KEY", "").strip(),
            model_name=os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip(),
        )
    raise ValueError(f"Unknown provider name: {name}")


def get_configured_model_name(provider_name: str) -> str:
    key = provider_name.strip().lower()
    if key == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if key == "llama":
        return os.getenv("OLLAMA_MODEL", "llama3.1").strip()
    if key == "mistral":
        if os.getenv("MISTRAL_API_KEY", "").strip():
            return os.getenv("MISTRAL_MODEL", "mistral-small-latest").strip()
        return os.getenv("MISTRAL_OLLAMA_MODEL", "mistral").strip()
    return "unknown"


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    candidate = match.group(0) if match else stripped
    return json.loads(candidate)


def generate_json(prompt: str, provider_name: str, system_prompt: str | None = None) -> dict[str, Any]:
    return get_provider(provider_name).generate_json(prompt, system_prompt=system_prompt)


def generate_text(prompt: str, provider_name: str, system_prompt: str | None = None) -> str:
    text = get_provider(provider_name).generate_text(prompt, system_prompt=system_prompt)
    fence = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return fence.group(1).strip() if fence else text.strip()
