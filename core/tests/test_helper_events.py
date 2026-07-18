from __future__ import annotations

import unittest

from glance_core.helper_events import (
    HELPER_EVENT_VERSION,
    HELPER_STALE_SAMPLE_MS,
    HELPER_TARGET_FPS,
    CoreReadyEvent,
    DisplayBounds,
    GazeSampleEvent,
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


if __name__ == "__main__":
    unittest.main()
