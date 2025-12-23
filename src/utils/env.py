from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"


@lru_cache(maxsize=1)
def load_env_file(dotenv_path: str | Path | None = None) -> bool:
    """Load environment variables from a .env file exactly once per process."""

    path: Path | None
    if dotenv_path is None:
        candidate = DEFAULT_ENV_PATH
        path = candidate if candidate.exists() else None
    else:
        path = Path(dotenv_path)
    return load_dotenv(dotenv_path=path, override=False)
