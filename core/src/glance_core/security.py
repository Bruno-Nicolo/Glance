from __future__ import annotations

import secrets
from pathlib import Path


def load_or_create_token(token_path: Path) -> str:
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()

    token = secrets.token_urlsafe(48)
    token_path.write_text(token, encoding="utf-8")
    token_path.chmod(0o600)
    return token


def is_authorized(authorization: str | None, token: str) -> bool:
    return authorization == f"Bearer {token}"
