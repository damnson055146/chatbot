from __future__ import annotations

import argparse
import secrets
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
FRONTEND_ROOT = REPO_ROOT / "frontend"
DEFAULT_FRONTEND_ENV = FRONTEND_ROOT / ".env"
FRONTEND_ENV_EXAMPLE = FRONTEND_ROOT / ".env.example"


def _load_env_lines(env_path: Path, fallback: Path | None = None) -> List[str]:
    if env_path.exists():
        return env_path.read_text(encoding="utf-8").splitlines()
    if fallback and fallback.exists():
        return fallback.read_text(encoding="utf-8").splitlines()
    return []


def _upsert_env(lines: List[str], key: str, value: str) -> List[str]:
    key_found = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        candidate = line.split("=", 1)[0].strip()
        if candidate == key:
            lines[idx] = f"{key}={value}"
            key_found = True
            break
    if not key_found:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}={value}")
    return lines


def _write_env(env_path: Path, lines: List[str]) -> None:
    if lines:
        content = "\n".join(lines) + "\n"
    else:
        content = ""
    env_path.write_text(content, encoding="utf-8")


def _generate_token(byte_length: int) -> str:
    return secrets.token_urlsafe(byte_length)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update API_AUTH_TOKEN in .env")
    parser.add_argument(
        "--token",
        help="Explicit token to write. If omitted, a secure random token is generated.",
        default=None,
    )
    parser.add_argument(
        "--bytes",
        type=int,
        default=24,
        help="Byte length fed to secrets.token_urlsafe when generating (default: 24).",
    )
    parser.add_argument(
        "--env-path",
        type=Path,
        default=DEFAULT_ENV,
        help="Path to the .env file (default: repository .env).",
    )
    parser.add_argument(
        "--frontend-env",
        type=Path,
        default=DEFAULT_FRONTEND_ENV,
        help="Path to frontend .env for syncing VITE_API_KEY (default: frontend/.env).",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Do not update the frontend env file even if --frontend-env is provided.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = args.token or _generate_token(args.bytes)
    env_path: Path = args.env_path
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = _load_env_lines(env_path, ENV_EXAMPLE)
    updated = _upsert_env(lines, "API_AUTH_TOKEN", token)
    _write_env(env_path, updated)
    print(f"[INFO] API_AUTH_TOKEN written to {env_path}")
    print(f"[INFO] Use this value for requests and frontend env: {token}")

    if not args.skip_frontend and args.frontend_env:
        frontend_lines = _load_env_lines(args.frontend_env, FRONTEND_ENV_EXAMPLE)
        updated_frontend = _upsert_env(frontend_lines, "VITE_API_KEY", token)
        _write_env(args.frontend_env, updated_frontend)
        print(f"[INFO] VITE_API_KEY synced to {args.frontend_env}")


if __name__ == "__main__":
    main()
