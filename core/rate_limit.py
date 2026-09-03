"""core/rate_limit.py — Per-session rate limiting for the Executo UI.

Enforces:
  - Max N runs per session  (EXECUTO_MAX_RUNS_PER_SESSION, default 10)
  - Cooldown between runs   (EXECUTO_COOLDOWN_SECONDS, default 30)

Usage in app.py:
    from core.rate_limit import RateLimiter
    limiter = RateLimiter()          # one instance shared across the app

    ok, msg = limiter.check()
    if not ok:
        # show msg to user, don't start a run
        ...
    else:
        limiter.record()             # call after check() passes, before the run
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


MAX_RUNS = _env_int("EXECUTO_MAX_RUNS_PER_SESSION", 10)
COOLDOWN = _env_int("EXECUTO_COOLDOWN_SECONDS", 30)


@dataclass
class RateLimiter:
    """Tracks runs for a single Gradio session (stateful, in-memory)."""

    max_runs: int = MAX_RUNS
    cooldown_seconds: int = COOLDOWN

    _run_count: int = field(default=0, init=False, repr=False)
    _last_run_at: float = field(default=0.0, init=False, repr=False)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def check(self) -> tuple[bool, str]:
        """Return (allowed, reason_message).

        Call this *before* starting a run.  If allowed is False, show the
        reason message to the user and abort.
        """
        now = time.monotonic()

        if self._run_count >= self.max_runs:
            return False, (
                f"⚠️ **Session limit reached** — you've run {self.max_runs} tasks "
                "this session. Refresh the page to start a new session."
            )

        elapsed = now - self._last_run_at
        if self._last_run_at > 0 and elapsed < self.cooldown_seconds:
            wait = int(self.cooldown_seconds - elapsed) + 1
            return False, (
                f"⏳ **Please wait {wait}s** before running another task "
                f"(cooldown: {self.cooldown_seconds}s between runs)."
            )

        return True, ""

    def record(self) -> None:
        """Record that a run has started.  Call immediately after check() passes."""
        self._run_count += 1
        self._last_run_at = time.monotonic()

    # ------------------------------------------------------------------ #
    # Convenience                                                          #
    # ------------------------------------------------------------------ #

    @property
    def runs_remaining(self) -> int:
        return max(0, self.max_runs - self._run_count)

    @property
    def seconds_until_ready(self) -> int:
        if self._last_run_at == 0:
            return 0
        elapsed = time.monotonic() - self._last_run_at
        remaining = self.cooldown_seconds - elapsed
        return max(0, int(remaining) + 1)

    @property
    def cooldown_remaining(self) -> float:
        """Un-rounded seconds left on the cooldown.

        `seconds_until_ready` rounds up for display; a live client-side
        countdown needs the real value to stay in step with the server.
        """
        if self._last_run_at == 0:
            return 0.0
        elapsed = time.monotonic() - self._last_run_at
        return max(0.0, self.cooldown_seconds - elapsed)

    def status_line(self) -> str:
        """Short status string suitable for a UI footer or tooltip."""
        remaining = self.runs_remaining
        wait = self.seconds_until_ready
        parts = [f"{remaining}/{self.max_runs} runs left this session"]
        if wait > 0:
            parts.append(f"ready in {wait}s")
        return " · ".join(parts)
