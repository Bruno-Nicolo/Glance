from __future__ import annotations

import os
from pathlib import Path


def application_support_dir() -> Path:
    base = Path.home() / "Library" / "Application Support" / "Glance"
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    return base


def runtime_dir() -> Path:
    path = application_support_dir() / "runtime"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path
