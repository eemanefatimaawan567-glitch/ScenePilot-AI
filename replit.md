# ScenePilot AI

ScenePilot AI is a cinematic Flask homepage for screenplay intake and future production analysis.

## Run & Operate

- `python artifacts/scene-pilot-ai/app.py` — run the Flask homepage locally
- `pnpm --filter @workspace/api-server run dev` — run the shared API server when backend routes are needed
- `pnpm run typecheck` — full typecheck across the workspace packages
- `python -m compileall artifacts/scene-pilot-ai` — check the Flask source compiles

## Stack

- Flask 3.1+, Python 3.13
- pnpm workspaces are retained for the shared Replit project services
- Screenplay Analysis uses Google's Gemini REST API through the `GEMINI_API_KEY` secret.

## Where things live

- `artifacts/scene-pilot-ai/app.py` — Flask application, TXT upload validation, and Gemini analysis endpoint
- `artifacts/scene-pilot-ai/templates/index.html` — homepage markup and required product copy
- `artifacts/scene-pilot-ai/static/styles.css` — dark film-studio visual system and responsive layout
- `artifacts/scene-pilot-ai/static/app.js` — local file selection, drag-and-drop, analysis request, and report rendering
- `artifacts/scene-pilot-ai/requirements.txt` — Python runtime dependency

## Architecture decisions

- Gemini is prompted for a fixed JSON contract and the Flask layer normalizes missing or alternate field spellings before returning it to the browser.
- Screenplays are validated in the browser and Flask route by extension, with a 25 MB request limit.
- The app uses the artifact's managed Flask workflow and the `PORT` environment variable.

## Product

Users can open a production-desk homepage, choose or drag in a PDF/TXT screenplay, and analyze TXT screenplays through Gemini. Production Analysis fills Story Signal, Scene Architecture, Production Pressure, and an expanded scene report.

## User preferences

- Keep the product focused on professional, dark cinematic film-studio presentation.
- Keep `GEMINI_API_KEY` in Replit Secrets; never hard-code or expose it.

## Gotchas

- The ScenePilot AI web workflow runs `python app.py` from the artifact directory, so commands in the artifact workflow must remain relative to that working directory.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
