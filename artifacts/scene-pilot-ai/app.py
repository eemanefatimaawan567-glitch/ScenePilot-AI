import os
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge


BASE_DIR = Path(__file__).resolve().parent
ALLOWED_EXTENSIONS = {"pdf", "txt"}
GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_MAX_ATTEMPTS = 3

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


def is_allowed_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


class GeminiAnalysisError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _request_gemini_json(gemini_request: urllib.request.Request, workflow_label: str):
    for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(gemini_request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 503} or attempt == GEMINI_MAX_ATTEMPTS:
                raise
            app.logger.warning(
                "Gemini %s transient HTTPError status=%s; retrying attempt %s/%s",
                workflow_label,
                exc.code,
                attempt + 1,
                GEMINI_MAX_ATTEMPTS,
            )
            time.sleep(2 ** (attempt - 1))


def _string_value(value, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    return str(value).strip() or fallback


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        _string_value(item)
        for item in value
        if _string_value(item)
    ]


def _normalize_characters(value) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    characters = []
    for item in value:
        if isinstance(item, dict):
            name = _string_value(
                item.get("name") or item.get("character"),
                "Unnamed character",
            )
            description = _string_value(
                item.get("description") or item.get("role"),
            )
        else:
            name = _string_value(item, "Unnamed character")
            description = ""
        characters.append({"name": name, "description": description})
    return characters


def _normalize_complexity(value) -> str:
    complexity = _string_value(value, "Medium").title()
    return complexity if complexity in {"Low", "Medium", "High"} else "Medium"


def _normalize_scene(scene, fallback_number: int) -> dict:
    if not isinstance(scene, dict):
        scene = {}

    try:
        number = int(scene.get("number", fallback_number))
    except (TypeError, ValueError):
        number = fallback_number

    int_ext = _string_value(
        scene.get("int_ext") or scene.get("intExt") or scene.get("setting"),
        "Not detected",
    ).upper()
    day_night = _string_value(
        scene.get("day_night") or scene.get("dayNight") or scene.get("time"),
        "Not detected",
    ).upper()

    return {
        "number": number,
        "int_ext": int_ext,
        "location": _string_value(scene.get("location"), "Not detected"),
        "day_night": day_night,
        "characters": _string_list(scene.get("characters")),
        "important_props": _string_list(
            scene.get("important_props") or scene.get("importantProps")
        ),
        "production_requirements": _string_list(
            scene.get("production_requirements")
            or scene.get("productionRequirements")
        ),
        "production_risks": _string_list(
            scene.get("production_risks") or scene.get("productionRisks")
        ),
        "complexity": _normalize_complexity(
            scene.get("estimated_complexity") or scene.get("complexity")
        ),
    }


def _normalize_agent_section(
    value,
    list_fields: list[str],
    summary_fallback: str,
) -> dict:
    raw_section = value if isinstance(value, dict) else {}
    normalized = {
        "summary": _string_value(
            raw_section.get("summary"),
            summary_fallback,
        ),
    }
    for field in list_fields:
        normalized[field] = _string_list(raw_section.get(field))
    return normalized


def _normalize_analysis(payload: dict) -> dict:
    raw_scenes = payload.get("scenes", [])
    scenes = [
        _normalize_scene(scene, index)
        for index, scene in enumerate(raw_scenes, start=1)
    ] if isinstance(raw_scenes, list) else []

    try:
        total_scenes = int(payload.get("total_scenes", len(scenes)))
    except (TypeError, ValueError):
        total_scenes = len(scenes)

    requirements = _string_list(
        payload.get("production_requirements")
        or payload.get("productionRequirements")
    )
    risks = _string_list(
        payload.get("production_risks") or payload.get("productionRisks")
    )

    for scene in scenes:
        for requirement in scene["production_requirements"]:
            if requirement not in requirements:
                requirements.append(requirement)
        for risk in scene["production_risks"]:
            if risk not in risks:
                risks.append(risk)

    return {
        "title": _string_value(payload.get("title"), "Untitled screenplay"),
        "genre": _string_value(payload.get("genre"), "Not detected"),
        "tone": _string_value(payload.get("tone"), "Not detected"),
        "logline": _string_value(payload.get("logline"), "Not detected"),
        "characters": _normalize_characters(payload.get("characters")),
        "total_scenes": max(total_scenes, len(scenes)),
        "scenes": scenes,
        "production_requirements": requirements,
        "production_risks": risks,
        "estimated_complexity": _normalize_complexity(
            payload.get("estimated_complexity") or payload.get("complexity")
        ),
        "director_agent": _normalize_agent_section(
            payload.get("director_agent"),
            ["production_priorities", "key_decisions"],
            "The Director Agent did not return a summary.",
        ),
        "continuity_agent": _normalize_agent_section(
            payload.get("continuity_agent"),
            ["continuity_risks", "affected_elements", "recommendations"],
            "The Continuity Agent did not return a summary.",
        ),
        "production_risk_agent": _normalize_agent_section(
            payload.get("production_risk_agent"),
            ["risks", "high_risk_scenes", "mitigations"],
            "The Production Risk Agent did not return a summary.",
        ),
        "scheduling_agent": _normalize_agent_section(
            payload.get("scheduling_agent"),
            ["shooting_order", "scheduling_rationale"],
            "The Scheduling Agent did not return a summary.",
        ),
        "director_decision": _normalize_agent_section(
            payload.get("director_decision"),
            ["final_priorities", "approved_shooting_strategy", "actions"],
            "The Director Decision did not return a summary.",
        ),
    }


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiAnalysisError(
            "Gemini returned an unreadable analysis. Please try the screenplay again.",
            502,
        ) from exc
    if not isinstance(parsed, dict):
        raise GeminiAnalysisError(
            "Gemini returned an unexpected analysis format.",
            502,
        )
    return _normalize_analysis(parsed)


def _normalize_recovery(payload: dict) -> dict:
    director_agent = payload.get("director_agent")
    continuity_agent = payload.get("continuity_agent")
    production_risk_agent = payload.get("production_risk_agent")
    scheduling_agent = payload.get("scheduling_agent")
    recovery_plan = payload.get("recovery_plan")

    return {
        "disruption_summary": _string_value(
            payload.get("disruption_summary"),
            "Production disruption received.",
        ),
        "affected_scenes": _string_list(payload.get("affected_scenes")),
        "director_agent": {
            "decision": _string_value(
                director_agent.get("decision")
                if isinstance(director_agent, dict)
                else None,
                "No director decision returned.",
            ),
            "priorities": _string_list(
                director_agent.get("priorities")
                if isinstance(director_agent, dict)
                else None
            ),
        },
        "continuity_agent": {
            "issues": _string_list(
                continuity_agent.get("issues")
                if isinstance(continuity_agent, dict)
                else None
            ),
            "recommendations": _string_list(
                continuity_agent.get("recommendations")
                if isinstance(continuity_agent, dict)
                else None
            ),
        },
        "production_risk_agent": {
            "new_risks": _string_list(
                production_risk_agent.get("new_risks")
                if isinstance(production_risk_agent, dict)
                else None
            ),
            "mitigations": _string_list(
                production_risk_agent.get("mitigations")
                if isinstance(production_risk_agent, dict)
                else None
            ),
        },
        "scheduling_agent": {
            "revised_shooting_order": _string_list(
                scheduling_agent.get("revised_shooting_order")
                if isinstance(scheduling_agent, dict)
                else None
            ),
            "rationale": _string_value(
                scheduling_agent.get("rationale")
                if isinstance(scheduling_agent, dict)
                else None,
                "No scheduling rationale returned.",
            ),
        },
        "recovery_plan": {
            "final_decision": _string_value(
                recovery_plan.get("final_decision")
                if isinstance(recovery_plan, dict)
                else None,
                "No final recovery decision returned.",
            ),
            "actions": _string_list(
                recovery_plan.get("actions")
                if isinstance(recovery_plan, dict)
                else None
            ),
        },
    }


def _extract_recovery_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiAnalysisError(
            "Gemini returned an unreadable recovery plan. Please try again.",
            502,
        ) from exc
    if not isinstance(parsed, dict):
        raise GeminiAnalysisError(
            "Gemini returned an unexpected recovery format.",
            502,
        )
    return _normalize_recovery(parsed)


def analyze_with_gemini(screenplay_text: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiAnalysisError(
            "Gemini is not configured yet. Add GEMINI_API_KEY in Replit Secrets.",
            503,
        )

    prompt = f"""You are a coordinated film production team. Analyze the screenplay below and return ONLY valid JSON.
Do not wrap the JSON in markdown fences. Do not omit fields; use an empty array or "Not detected" when needed.
Simulate the Director, Continuity, Production Risk, and Scheduling Agents inside this single response.
Do not make separate model calls. Each agent should analyze the same screenplay independently, then the
director_decision should combine their recommendations into one practical production direction.

Return exactly this shape:
{{
  "title": "string",
  "genre": "string",
  "tone": "string",
  "logline": "string",
  "characters": [{{"name": "string", "description": "string"}}],
  "total_scenes": 0,
  "scenes": [
    {{
      "number": 1,
      "int_ext": "INT, EXT, or INT/EXT",
      "location": "string",
      "day_night": "DAY, NIGHT, or other screenplay time marker",
      "characters": ["string"],
      "important_props": ["string"],
      "production_requirements": ["string"],
      "production_risks": ["string"],
      "complexity": "Low, Medium, or High"
    }}
  ],
  "production_requirements": ["string"],
  "production_risks": ["string"],
  "estimated_complexity": "Low, Medium, or High",
  "director_agent": {{
    "summary": "string",
    "production_priorities": ["string"],
    "key_decisions": ["string"]
  }},
  "continuity_agent": {{
    "summary": "string",
    "continuity_risks": ["string"],
    "affected_elements": ["character, prop, wardrobe, location, or timeline issue"],
    "recommendations": ["string"]
  }},
  "production_risk_agent": {{
    "summary": "string",
    "risks": ["string"],
    "high_risk_scenes": ["scene number and reason"],
    "mitigations": ["string"]
  }},
  "scheduling_agent": {{
    "summary": "string",
    "shooting_order": ["scene number or grouped scene order"],
    "scheduling_rationale": ["string"]
  }},
  "director_decision": {{
    "summary": "string",
    "final_priorities": ["string"],
    "approved_shooting_strategy": ["string"],
    "actions": ["string"]
  }}
}}

Be specific and production-minded. Identify practical requirements such as vehicles, stunts, weapons,
special effects, animals, crowds, period details, specialty locations, night work, and weather.
For continuity, check character states, props, wardrobe, locations, and timeline progression.
For scheduling, recommend an efficient order based on location, DAY/NIGHT, and production complexity.

SCREENPLAY:
{screenplay_text}
"""

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?"
        f"{urllib.parse.urlencode({'key': api_key})}"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    request_body = json.dumps(body).encode("utf-8")
    gemini_request = urllib.request.Request(
        endpoint,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        response_payload = _request_gemini_json(gemini_request, "screenplay analysis")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore").lower()
        safe_error_body = error_body.replace(api_key, "[REDACTED]") if api_key else error_body
        safe_error_body = re.sub(
            r'(?i)([?&]key=|["\']?(?:api[_-]?key|key)["\']?\s*[:=]\s*)[^&,"\'}\s]+',
            r"\1[REDACTED]",
            safe_error_body,
        )[:4000]
        app.logger.error(
            "Gemini upstream HTTPError status=%s body=%s",
            exc.code,
            safe_error_body,
        )
        if exc.code in {401, 403} or "api key" in error_body or "permission" in error_body:
            raise GeminiAnalysisError(
                "Gemini credentials were rejected. Check GEMINI_API_KEY in Replit Secrets.",
                503,
            ) from exc
        if exc.code in {429, 503}:
            raise GeminiAnalysisError(
                "Gemini is temporarily busy. Please try again in a moment.",
                503,
            ) from exc
        if exc.code == 400:
            raise GeminiAnalysisError(
                "Gemini rejected the screenplay analysis request. Please try a readable TXT file again.",
                502,
            ) from exc
        if exc.code == 404:
            raise GeminiAnalysisError(
                "The configured Gemini analysis model is unavailable. Please check the Gemini setup.",
                503,
            ) from exc
        raise GeminiAnalysisError(
            "Gemini could not analyze this screenplay right now. Please try again.",
            502,
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeminiAnalysisError(
            "Gemini is unavailable right now. Check the connection and try again.",
            503,
        ) from exc

    try:
        candidate = response_payload["candidates"][0]
        response_text = "".join(
            part.get("text", "")
            for part in candidate["content"]["parts"]
            if isinstance(part, dict)
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiAnalysisError(
            "Gemini returned no usable screenplay analysis. Please try again.",
            502,
        ) from exc

    return _extract_json(response_text)


def replan_with_gemini(analysis: dict, disruption: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiAnalysisError(
            "Gemini is not configured yet. Add GEMINI_API_KEY in Replit Secrets.",
            503,
        )

    analysis_context = json.dumps(analysis, ensure_ascii=False)
    prompt = f"""You are a coordinated film production recovery team.
Use the existing screenplay analysis and the filmmaker's production disruption below.
Return ONLY valid JSON. Do not wrap the JSON in markdown fences. Do not omit fields;
use an empty array or "Not detected" when needed.

Director Agent: decide the overall response and rank the most important priorities.
Continuity Agent: identify consequences for character, prop, wardrobe, location, and timeline continuity.
Production Risk Agent: identify new expensive, difficult, dangerous, or logistical risks and mitigations.
Scheduling Agent: create a revised shooting order using location, DAY/NIGHT, and complexity.
Then produce a final recovery_plan that combines the recommendations.
Run all roles inside this single response and do not make separate model calls.

Return exactly this shape:
{{
  "disruption_summary": "string",
  "affected_scenes": ["scene number and reason"],
  "director_agent": {{
    "decision": "string",
    "priorities": ["string"]
  }},
  "continuity_agent": {{
    "issues": ["string"],
    "recommendations": ["string"]
  }},
  "production_risk_agent": {{
    "new_risks": ["string"],
    "mitigations": ["string"]
  }},
  "scheduling_agent": {{
    "revised_shooting_order": ["scene number or grouped scene order"],
    "rationale": "string"
  }},
  "recovery_plan": {{
    "final_decision": "string",
    "actions": ["string"]
  }}
}}

EXISTING SCREENPLAY ANALYSIS:
{analysis_context}

FILMMAKER PRODUCTION DISRUPTION:
{disruption}
"""

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?"
        f"{urllib.parse.urlencode({'key': api_key})}"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    gemini_request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        response_payload = _request_gemini_json(gemini_request, "production recovery")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore").lower()
        safe_error_body = error_body.replace(api_key, "[REDACTED]") if api_key else error_body
        safe_error_body = re.sub(
            r'(?i)([?&]key=|["\']?(?:api[_-]?key|key)["\']?\s*[:=]\s*)[^&,"\'}\s]+',
            r"\1[REDACTED]",
            safe_error_body,
        )[:4000]
        app.logger.error(
            "Gemini recovery upstream HTTPError status=%s body=%s",
            exc.code,
            safe_error_body,
        )
        if exc.code in {401, 403} or "api key" in error_body or "permission" in error_body:
            raise GeminiAnalysisError(
                "Gemini credentials were rejected. Check GEMINI_API_KEY in Replit Secrets.",
                503,
            ) from exc
        if exc.code in {429, 503}:
            raise GeminiAnalysisError(
                "Gemini is temporarily busy. Please try again in a moment.",
                503,
            ) from exc
        if exc.code == 400:
            raise GeminiAnalysisError(
                "Gemini rejected the production recovery request. Please revise the disruption and try again.",
                502,
            ) from exc
        if exc.code == 404:
            raise GeminiAnalysisError(
                "The configured Gemini analysis model is unavailable. Please check the Gemini setup.",
                503,
            ) from exc
        raise GeminiAnalysisError(
            "Gemini could not create a recovery plan right now. Please try again.",
            502,
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeminiAnalysisError(
            "Gemini is unavailable right now. Check the connection and try again.",
            503,
        ) from exc

    try:
        candidate = response_payload["candidates"][0]
        response_text = "".join(
            part.get("text", "")
            for part in candidate["content"]["parts"]
            if isinstance(part, dict)
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiAnalysisError(
            "Gemini returned no usable recovery plan. Please try again.",
            502,
        ) from exc

    return _extract_recovery_json(response_text)


@app.route("/", methods=["GET", "POST"])
def home():
    selected_file = None
    upload_error = None

    if request.method == "POST":
        screenplay = request.files.get("screenplay")
        if screenplay and screenplay.filename:
            if is_allowed_file(screenplay.filename):
                selected_file = screenplay.filename
            else:
                upload_error = "Please choose a PDF or TXT screenplay."
        else:
            upload_error = "Choose a screenplay before continuing."

    return render_template(
        "index.html",
        selected_file=selected_file,
        upload_error=upload_error,
    )


@app.post("/analyze")
def analyze_screenplay():
    screenplay = request.files.get("screenplay")
    if not screenplay or not screenplay.filename:
        return jsonify({"error": "Choose a screenplay before analyzing it."}), 400

    if not screenplay.filename.lower().endswith(".txt"):
        return jsonify(
            {"error": "Screenplay Analysis currently supports TXT files only."}
        ), 400

    try:
        screenplay_text = screenplay.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify(
            {"error": "This TXT screenplay is not encoded as readable UTF-8 text."}
        ), 400

    if not screenplay_text.strip():
        return jsonify({"error": "The screenplay file is empty."}), 400

    try:
        analysis = analyze_with_gemini(screenplay_text)
    except GeminiAnalysisError as exc:
        return jsonify({"error": str(exc)}), exc.status_code

    return jsonify(analysis)


@app.post("/replan")
def replan_production():
    payload = request.get_json(silent=True) or {}
    disruption = _string_value(payload.get("disruption"))
    analysis = payload.get("analysis")

    if not disruption:
        return jsonify({"error": "Describe the production disruption before replanning."}), 400
    if not isinstance(analysis, dict):
        return jsonify({"error": "Analyze a screenplay before replanning production."}), 400

    try:
        recovery = replan_with_gemini(analysis, disruption)
    except GeminiAnalysisError as exc:
        return jsonify({"error": str(exc)}), exc.status_code

    return jsonify(recovery)


@app.errorhandler(RequestEntityTooLarge)
def handle_large_upload(_error):
    return jsonify(
        {"error": "This screenplay is larger than the 25 MB workspace limit."}
    ), 413


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5001")),
        debug=False,
    )