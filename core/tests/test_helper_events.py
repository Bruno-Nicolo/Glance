from __future__ import annotations

import unittest

from glance_core.helper_events import (
    HELPER_EVENT_VERSION,
    HELPER_STALE_SAMPLE_MS,
    HELPER_TARGET_FPS,
    CoreReadyEvent,
    CursorPoint,
    DisplayBounds,
    GazeSampleEvent,
    HelperInputEvent,
    HelperPermissionEvent,
    SyntheticGazePath,
    TrackingStatusEvent,
)


class HelperEventContractTests(unittest.TestCase):
    def test_core_ready_payload_contains_contract_metadata(self) -> None:
        payload = CoreReadyEvent(sent_at_ms=1000, sequence=0).to_json_dict()

        self.assertEqual(payload["type"], "core.ready")
        self.assertEqual(payload["version"], HELPER_EVENT_VERSION)
        self.assertEqual(payload["min_version"], HELPER_EVENT_VERSION)
        self.assertEqual(payload["target_fps"], HELPER_TARGET_FPS)
        self.assertEqual(payload["stale_sample_ms"], HELPER_STALE_SAMPLE_MS)

    def test_gaze_sample_payload_uses_top_left_display_coordinates(self) -> None:
        event = GazeSampleEvent(
            sent_at_ms=1033,
            sequence=3,
            sample_at_ms=1029,
            x=320.5,
            y=180.25,
            display=DisplayBounds(
                id="main",
                x=0,
                y=0,
                width=1440,
                height=900,
                scale=2,
            ),
            confidence=0.92,
            status="valid",
            source="synthetic",
        )

        payload = event.to_json_dict()

        self.assertEqual(payload["type"], "gaze.sample")
        self.assertEqual(payload["display"]["coordinate_space"], "display-logical-top-left")
        self.assertEqual(payload["x"], 320.5)
        self.assertEqual(payload["y"], 180.25)
        self.assertEqual(payload["confidence"], 0.92)
        self.assertEqual(payload["source"], "synthetic")

    def test_tracking_status_payload_allows_paused_overlay_state(self) -> None:
        payload = TrackingStatusEvent(
            sent_at_ms=1100,
            sequence=4,
            tracking="paused",
            overlay="frozen",
            reason="esc-held",
        ).to_json_dict()

        self.assertEqual(payload["type"], "tracking.status")
        self.assertEqual(payload["tracking"], "paused")
        self.assertEqual(payload["overlay"], "frozen")
        self.assertEqual(payload["reason"], "esc-held")

    def test_helper_input_payload_reports_space_click_at_cursor_without_key_history(self) -> None:
        display = DisplayBounds(
            id="main",
            x=0,
            y=0,
            width=1440,
            height=900,
            scale=2,
        )

        payload = HelperInputEvent(
            sent_at_ms=1200,
            sequence=5,
            action="space-click",
            cursor=CursorPoint(x=512.5, y=384.25, display=display),
        ).to_json_dict()

        self.assertEqual(payload["type"], "helper.input")
        self.assertEqual(payload["action"], "space-click")
        self.assertEqual(payload["cursor"]["x"], 512.5)
        self.assertEqual(payload["cursor"]["display"]["coordinate_space"], "display-logical-top-left")
        self.assertNotIn("key_code", payload)
        self.assertNotIn("history", payload)

    def test_helper_input_payload_reports_suppressed_actions_without_cursor(self) -> None:
        payload = HelperInputEvent(
            sent_at_ms=1233,
            sequence=6,
            action="space-click",
            suppressed_reason="permission-denied",
        ).to_json_dict()

        self.assertEqual(payload["type"], "helper.input")
        self.assertEqual(payload["action"], "space-click")
        self.assertEqual(payload["cursor"], None)
        self.assertEqual(payload["suppressed_reason"], "permission-denied")

    def test_helper_permission_payload_identifies_recoverable_missing_permissions(self) -> None:
        payload = HelperPermissionEvent(
            sent_at_ms=1266,
            sequence=7,
            permission="accessibility",
            state="denied",
            required_for=["space-click"],
        ).to_json_dict()

        self.assertEqual(payload["type"], "helper.permission")
        self.assertEqual(payload["permission"], "accessibility")
        self.assertEqual(payload["state"], "denied")
        self.assertEqual(payload["required_for"], ["space-click"])
        self.assertEqual(payload["recoverable"], True)

    def test_synthetic_gaze_path_emits_valid_looping_screen_samples(self) -> None:
        display = DisplayBounds(
            id="main",
            x=0,
            y=0,
            width=1000,
            height=500,
            scale=2,
        )
        path = SyntheticGazePath(display=display, frames_per_loop=4)

        right = path.sample(sequence=0, sent_at_ms=2000).to_json_dict()
        bottom = path.sample(sequence=1, sent_at_ms=2033).to_json_dict()
        left = path.sample(sequence=2, sent_at_ms=2066).to_json_dict()
        top = path.sample(sequence=3, sent_at_ms=2099).to_json_dict()

        self.assertEqual(right["type"], "gaze.sample")
        self.assertEqual(right["sample_at_ms"], 2000)
        self.assertEqual(right["confidence"], 1.0)
        self.assertEqual(right["status"], "valid")
        self.assertEqual(right["source"], "synthetic")
        self.assertEqual(right["display"]["coordinate_space"], "display-logical-top-left")
        self.assertEqual(right["x"], 820.0)
        self.assertEqual(right["y"], 250.0)
        self.assertAlmostEqual(bottom["x"], 500.0)
        self.assertEqual(bottom["y"], 390.0)
        self.assertEqual(left["x"], 180.0)
        self.assertAlmostEqual(left["y"], 250.0)
        self.assertAlmostEqual(top["x"], 500.0)
        self.assertEqual(top["y"], 110.0)


if __name__ == "__main__":
    unittest.main()
