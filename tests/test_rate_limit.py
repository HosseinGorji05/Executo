"""Tests for core.rate_limit."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from core.rate_limit import RateLimiter


class TestRateLimiter(unittest.TestCase):
    def test_allows_first_run(self) -> None:
        limiter = RateLimiter(max_runs=3, cooldown_seconds=30)
        ok, msg = limiter.check()
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_session_limit_blocks_after_max_runs(self) -> None:
        limiter = RateLimiter(max_runs=2, cooldown_seconds=0)
        limiter.record()
        limiter.record()
        ok, msg = limiter.check()
        self.assertFalse(ok)
        self.assertIn("Session limit reached", msg)

    @patch("core.rate_limit.time.monotonic")
    def test_cooldown_blocks_rapid_reruns(self, mock_mono: MagicMock) -> None:
        mock_mono.side_effect = [100.0, 100.0, 110.0]
        limiter = RateLimiter(max_runs=10, cooldown_seconds=30)
        limiter.record()
        ok, msg = limiter.check()
        self.assertFalse(ok)
        self.assertIn("Please wait", msg)

    @patch("core.rate_limit.time.monotonic")
    def test_runs_remaining_and_status_line(self, mock_mono: MagicMock) -> None:
        mock_mono.return_value = 200.0
        limiter = RateLimiter(max_runs=5, cooldown_seconds=30)
        limiter.record()
        self.assertEqual(limiter.runs_remaining, 4)
        self.assertIn("4/5 runs left", limiter.status_line())


if __name__ == "__main__":
    unittest.main()
