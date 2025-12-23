# Scripts

## `run_dev.bat`

- Purpose: bootstrap the local dev environment and launch backend (`python -m src.cli --config configs/dev.yaml serve --reload`) plus frontend (`npm run dev`).
- Usage: double-click the file in Explorer or run `scripts\run_dev.bat` from `cmd`.
- Behavior:
  - Creates `.venv` if missing and installs Python dependencies via `pip install -r requirements.txt`.
  - Runs `python scripts/set_api_token.py` so `.env` and `frontend/.env` share the same `API_AUTH_TOKEN` / `VITE_API_KEY`.
  - Runs backend in a dedicated terminal with the virtual environment activated.
  - Installs frontend dependencies on first run (`frontend\node_modules` check) and opens another terminal for `npm run dev`.
- Requirements: Python (for `venv`/`pip`) and Node.js + npm must be available on `PATH`.
- Shutdown: close the spawned backend/frontend terminals to stop the services.

## `set_api_token.py`

- Purpose: generate (or set) `API_AUTH_TOKEN` inside `.env`, ensuring the backend and frontend share the same secret.
- Usage: `python scripts/set_api_token.py` (optionally pass `--token <value>` to use your own string).
- Behavior:
  - Copies `.env.example` as the base if `.env` does not exist yet.
  - Generates a secure random token via `secrets.token_urlsafe` when `--token` is omitted.
  - Upserts the `API_AUTH_TOKEN` line and prints the value so it can be used by clients or `frontend/.env` (`VITE_API_KEY`).
- Options: `--bytes` controls the entropy when auto-generating; `--env-path` lets you target a different `.env` file.
