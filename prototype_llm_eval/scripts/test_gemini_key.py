"""
Test GEMINI_API_KEY + GEMINI_MODEL using the same Gemini provider path as the app (get_provider('gemini')).

Run from repository root:
  python prototype_llm_eval/scripts/test_gemini_key.py

Or on Windows after loading local.env in the shell:
  . .\\prototype_llm_eval\\scripts\\load_local_env.ps1
  python prototype_llm_eval/scripts/test_gemini_key.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_ROOT = Path(__file__).resolve().parents[1]


def _load_local_env_file() -> None:
    path = _EVAL_ROOT / "local.env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().strip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not name:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[name] = value


def main() -> int:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    _load_local_env_file()

    from prototype_llm_eval.backend.llm_provider import GeminiProviderAuthError, get_provider

    key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    print(f"Configured model: {model}")
    print(f"GEMINI_API_KEY present: {bool(key)}")
    if key:
        print(f"GEMINI_API_KEY length: {len(key)} (typical AI Studio keys are ~39 chars, prefix AIzaSy)")

    try:
        provider = get_provider("gemini")
        text = provider.generate_text("Reply with exactly the single word OK and nothing else.")
        snippet = (text or "").strip()[:120]
        print("Result: Gemini API key appears valid — model returned:", snippet or "(empty)")
        return 0
    except GeminiProviderAuthError as exc:
        print("Result: Gemini auth failed - likely wrong/missing key type or invalid key for this SDK path.")
        print(f"Detail: {exc}")
        print(
            "Hint: This project uses API-key auth (google.generativeai / Generative Language API), "
            "not Vertex AI. Prefer a key from Google AI Studio. If you use a Cloud Console key, allow "
            "'Generative Language API' or use 'Don't restrict key' for local testing. "
            "For demos without Gemini: QUESTION_GENERATION_PROVIDER=llama in local.env."
        )
        return 1
    except Exception as exc:  # noqa: BLE001 — diagnostic script
        print("Result: Unexpected error during Gemini test call.")
        print(f"Detail: {exc!r}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
