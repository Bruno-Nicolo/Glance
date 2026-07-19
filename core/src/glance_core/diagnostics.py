from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .helper_events import now_ms
from .ui_contract import CORE_UI_CONTRACT_VERSION

DiagnosticSeverity = Literal["debug", "info", "warning", "error"]
DiagnosticComponent = Literal[
    "core",
    "helper",
    "electron-main",
    "renderer",
    "camera",
    "calibration",
    "tracking",
]

DIAGNOSTIC_COMPONENTS = {
    "core",
    "helper",
    "electron-main",
    "renderer",
    "camera",
    "calibration",
    "tracking",
}
DIAGNOSTIC_SEVERITIES = {"debug", "info", "warning", "error"}


@dataclass(frozen=True, kw_only=True)
class DiagnosticLogEntry:
    timestamp_ms: int
    component: DiagnosticComponent
    severity: DiagnosticSeverity
    message: str
    details: dict[str, object] | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


class DiagnosticLogStore:
    def __init__(self, log_path: Path, max_entries: int = 500):
        self.log_path = log_path
        self.entries: deque[DiagnosticLogEntry] = deque(maxlen=max_entries)
        self.lock = threading.Lock()
        self.log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def record(
        self,
        component: DiagnosticComponent,
        severity: DiagnosticSeverity,
        message: str,
        details: dict[str, object] | None = None,
    ) -> DiagnosticLogEntry:
        entry = DiagnosticLogEntry(
            timestamp_ms=now_ms(),
            component=component,
            severity=severity,
            message=sanitize_log_message(message),
            details=sanitize_details(details),
        )
        with self.lock:
            self.entries.append(entry)
            with self.log_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(entry.to_json_dict(), sort_keys=True))
                file.write("\n")
        return entry

    def recent_entries(
        self,
        *,
        component: str | None = None,
        limit: int = 200,
    ) -> list[DiagnosticLogEntry]:
        bounded_limit = max(1, min(limit, 500))
        with self.lock:
            entries = list(self.entries)
        if component is not None:
            entries = [entry for entry in entries if entry.component == component]
        return entries[-bounded_limit:]

    def to_response(
        self,
        *,
        component: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
        return {
            "contract_version": CORE_UI_CONTRACT_VERSION,
            "entries": [
                entry.to_json_dict()
                for entry in self.recent_entries(component=component, limit=limit)
            ],
        }


def sanitize_log_message(message: str) -> str:
    return " ".join(message.split())[:2000]


def sanitize_details(details: dict[str, object] | None) -> dict[str, object] | None:
    if details is None:
        return None
    sanitized: dict[str, object] = {}
    for key, value in details.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_log_message(value)
        elif isinstance(value, int | float | bool) or value is None:
            sanitized[key] = value
        else:
            sanitized[key] = sanitize_log_message(str(value))
    return sanitized
