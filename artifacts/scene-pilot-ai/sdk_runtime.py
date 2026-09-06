"""ScenePilot runtime adapter using the official Google Gen AI SDK.

The original Flask application keeps its existing prompts, response normalization,
and routes in app.py. This module replaces only the Gemini transport layer so
runtime model calls go through the accepted google-genai SDK.
"""

import json
import os
import time

from google import genai
from google.genai import types

import app as scenepilot


def _sdk_request_gemini_json(gemini_request, workflow_label: str):
    """Execute the existing Gemini request through google-genai instead of urllib."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise scenepilot.GeminiAnalysisError(
            "Gemini is not configured yet. Add GEMINI_API_KEY in Replit Secrets.",
            503,
        )

    try:
        request_payload = json.loads((gemini_request.data or b"{}").decode("utf-8"))
        prompt = request_payload["contents"][0]["parts"][0]["text"]
        generation_config = request_payload.get("generationConfig", {})
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise scenepilot.GeminiAnalysisError(
            "ScenePilot could not prepare the Gemini request.", 500
        ) from exc

    client = genai.Client(api_key=api_key)
    last_error = None

    for attempt in range(1, scenepilot.GEMINI_MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=scenepilot.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=generation_config.get("temperature", 0.2),
                    response_mime_type=generation_config.get(
                        "responseMimeType", "application/json"
                    ),
                ),
            )

            response_text = getattr(response, "text", None)
            if not response_text:
                raise scenepilot.GeminiAnalysisError(
                    f"Gemini returned no usable {workflow_label}. Please try again.",
                    502,
                )

            # app.py already knows how to parse the REST-shaped response below.
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": response_text}]
                        }
                    }
                ]
            }

        except scenepilot.GeminiAnalysisError:
            raise
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            transient = any(
                token in message
                for token in ("429", "503", "resource exhausted", "unavailable")
            )

            if transient and attempt < scenepilot.GEMINI_MAX_ATTEMPTS:
                scenepilot.app.logger.warning(
                    "Gemini %s transient SDK error; retrying attempt %s/%s",
                    workflow_label,
                    attempt + 1,
                    scenepilot.GEMINI_MAX_ATTEMPTS,
                )
                time.sleep(2 ** (attempt - 1))
                continue

            if any(
                token in message
                for token in ("401", "403", "api key", "permission", "unauthorized")
            ):
                raise scenepilot.GeminiAnalysisError(
                    "Gemini credentials were rejected. Check GEMINI_API_KEY in Replit Secrets.",
                    503,
                ) from exc

            if transient:
                raise scenepilot.GeminiAnalysisError(
                    "Gemini is temporarily busy. Please try again in a moment.",
                    503,
                ) from exc

            if "404" in message or "not found" in message:
                raise scenepilot.GeminiAnalysisError(
                    "The configured Gemini analysis model is unavailable. Please check the Gemini setup.",
                    503,
                ) from exc

            raise scenepilot.GeminiAnalysisError(
                f"Gemini could not complete the {workflow_label} right now. Please try again.",
                502,
            ) from exc

    raise scenepilot.GeminiAnalysisError(
        f"Gemini could not complete the {workflow_label} right now. Please try again.",
        502,
    ) from last_error


# Replace the legacy transport before any /analyze or /replan request is handled.
scenepilot._request_gemini_json = _sdk_request_gemini_json


if __name__ == "__main__":
    scenepilot.app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5001")),
        debug=False,
    )
