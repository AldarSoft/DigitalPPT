from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def load_env_file(path: str | Path) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        cleaned = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), cleaned)


def env(key: str, default: Any = None, cast: type = str) -> Any:
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {key}")

    if cast is bool:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if cast is int:
        return int(value)
    if cast is list:
        return [item.strip() for item in str(value).split(",") if item.strip()]
    return cast(value) if cast is not str else value
