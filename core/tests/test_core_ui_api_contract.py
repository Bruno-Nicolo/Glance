from __future__ import annotations

import tempfile
import asyncio
import json
import os
import socket
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import uvicorn
import websockets

from glance_core.server import RuntimeState, create_app


class CoreUiApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name) / "config.json"
        self.runtime_path = Path(self.temp_dir.name) / "runtime"
        self.runtime_path.mkdir()
        self.shutdown_requested = False
        self.previous_disable_helper = os.environ.get("GLANCE_DISABLE_HELPER")
        os.environ["GLANCE_DISABLE_HELPER"] = "1"
        self.addCleanup(self._restore_helper_environment)
        self.port = self._find_available_port()
        app = create_app(
            RuntimeState(
                token="test-token",
                port=self.port,
                config_path=self.config_path,
                runtime_path=self.runtime_path,
            ),
            shutdown_callback=self._mark_shutdown_requested,
        )
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="critical")
        )
        self.server_thread = threading.Thread(target=self.server.run, daemon=True)
        self.server_thread.start()
        self._wait_for_server()
        self.addCleanup(self._stop_server)
        self.headers = {"Authorization": "Bearer test-token"}

    def _mark_shutdown_requested(self) -> None:
        self.shutdown_requested = True

    def _restore_helper_environment(self) -> None:
        if self.previous_disable_helper is None:
            os.environ.pop("GLANCE_DISABLE_HELPER", None)
        else:
            os.environ["GLANCE_DISABLE_HELPER"] = self.previous_disable_helper

    def _stop_server(self) -> None:
        self.server.should_exit = True
        self.server_thread.join(timeout=2)

    def _wait_for_server(self) -> None:
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                self.get("/health")
                return
            except OSError:
                time.sleep(0.05)
        self.fail("Timed out waiting for test server")

    def _find_available_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def get(self, route: str) -> tuple[int, dict]:
        return self.request("GET", route)

    def post(self, route: str) -> tuple[int, dict]:
        return self.request("POST", route)

    def put(self, route: str, body: dict) -> tuple[int, dict]:
        return self.request("PUT", route, body)

    def request(self, method: str, route: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Authorization": "Bearer test-token"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            f"http://127.0.0.1:{self.port}{route}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_health_identifies_core_ui_contract(self) -> None:
        status_code, body = self.get("/health")

        self.assertEqual(status_code, 200)
        self.assertEqual(
            body,
            {
                "status": "ok",
                "contract": "core-ui",
                "contract_version": 1,
            },
        )

    def test_runtime_path_uses_private_permissions(self) -> None:
        mode = self.runtime_path.stat().st_mode & 0o777

        self.assertEqual(mode, 0o700)

    def test_status_shape_keeps_ui_out_of_runtime_critical_path(self) -> None:
        status_code, body = self.get("/status")

        self.assertEqual(status_code, 200)
        self.assertEqual(
            body,
            {
                "contract_version": 1,
                "core": {"state": "running", "pid": None},
                "helper": {"state": "not-started"},
                "camera": {"state": "stopped", "active": False},
                "tracking": {"state": "stopped", "input_enabled": False},
                "calibration": {"state": "missing", "profile_id": None},
                "ui": {"runtime_critical": False},
                "error": None,
            },
        )

    def test_settings_round_trip_persists_core_owned_config(self) -> None:
        update = {
            "tracking": {
                "pause_behavior": "privacy-low-power",
                "confidence_threshold": 0.74,
                "smoothing": 0.38,
            },
            "input": {"space_click_enabled": False},
            "debug": {"synthetic_gaze_enabled": False},
        }

        put_status, put_body = self.put("/settings", update)
        get_status, get_body = self.get("/settings")

        self.assertEqual(put_status, 200)
        self.assertEqual(get_status, 200)
        self.assertEqual(put_body, get_body)
        self.assertEqual(get_body["tracking"]["pause_behavior"], "privacy-low-power")
        self.assertEqual(get_body["tracking"]["confidence_threshold"], 0.74)
        self.assertEqual(get_body["input"]["space_click_enabled"], False)

    def test_settings_rejects_unknown_fields_with_structured_error(self) -> None:
        status_code, body = self.put("/settings", {"tracking": {"unknown": True}})

        self.assertEqual(status_code, 400)
        self.assertEqual(
            body,
            {
                "error": {
                    "code": "invalid_settings",
                    "message": "Unknown settings field: tracking.unknown",
                    "recoverable": True,
                },
            },
        )

    def test_settings_rejects_contract_version_updates(self) -> None:
        status_code, body = self.put("/settings", {"contract_version": 999})

        self.assertEqual(status_code, 400)
        self.assertEqual(body["error"]["code"], "invalid_settings")
        self.assertEqual(body["error"]["message"], "Unknown settings field: contract_version")

    def test_controls_start_and_stop_tracking_update_status(self) -> None:
        start_status, _start_body = self.post("/controls/start")
        _started_status_code, started_status = self.get("/status")
        stop_status, _stop_body = self.post("/controls/stop")
        _stopped_status_code, stopped_status = self.get("/status")

        self.assertEqual(start_status, 200)
        self.assertEqual(started_status["tracking"]["state"], "running")
        self.assertEqual(started_status["tracking"]["input_enabled"], True)
        self.assertEqual(stop_status, 200)
        self.assertEqual(stopped_status["tracking"]["state"], "stopped")
        self.assertEqual(stopped_status["tracking"]["input_enabled"], False)

    def test_shutdown_returns_explicit_full_shutdown_semantics(self) -> None:
        status_code, body = self.post("/shutdown")

        self.assertEqual(status_code, 202)
        self.assertEqual(
            body,
            {
                "status": "shutting-down",
                "scope": "full-runtime",
                "ui_should_exit": True,
            },
        )
        deadline = time.time() + 1
        while not self.shutdown_requested and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.shutdown_requested)

    def test_unauthorized_requests_return_structured_error(self) -> None:
        request = Request(f"http://127.0.0.1:{self.port}/status")
        try:
            with urlopen(request, timeout=2):
                self.fail("Expected unauthorized request to fail")
        except HTTPError as error:
            status_code = error.code
            body = json.loads(error.read().decode("utf-8"))

        self.assertEqual(status_code, 401)
        self.assertEqual(
            body,
            {
                "error": {
                    "code": "unauthorized",
                    "message": "Missing or invalid bearer token",
                    "recoverable": True,
                },
            },
        )

    def test_ui_websocket_receives_ready_status_and_change_events(self) -> None:
        async def receive_events() -> tuple[dict, dict, dict]:
            async with websockets.connect(
                f"ws://127.0.0.1:{self.port}/ui/events",
                additional_headers=self.headers,
                proxy=None,
            ) as websocket:
                ready = json.loads(await websocket.recv())
                status = json.loads(await websocket.recv())
                start_status, _start_body = self.post("/controls/start")
                changed = json.loads(await asyncio.wait_for(websocket.recv(), timeout=2))
                self.assertEqual(start_status, 200)
                return ready, status, changed

        ready, status, changed = asyncio.run(receive_events())

        self.assertEqual(ready["type"], "ui.ready")
        self.assertEqual(ready["contract_version"], 1)
        self.assertEqual(status["type"], "status.changed")
        self.assertEqual(status["status"]["tracking"]["state"], "stopped")
        self.assertEqual(changed["type"], "status.changed")
        self.assertEqual(changed["status"]["tracking"]["state"], "running")


if __name__ == "__main__":
    unittest.main()
