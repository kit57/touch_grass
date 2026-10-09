import os
from pathlib import Path


def _load_env(path=".env"):
    """Read KEY=value lines from .env. Variables already set in the environment win."""
    file = Path(path)
    if not file.exists():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#") and value.strip():
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env()
