"""A circuit breaker for the Anthropic API in "auto" mode.

When Anthropic is down, every question would otherwise wait for the full
10-second timeout before falling back to Ollama. After 3 failures in a row
the breaker "opens" and auto mode skips Anthropic entirely for 60 seconds.
After that, one request is let through as a trial ("half-open"): success
closes the breaker again, failure re-opens it for another 60 seconds.

    closed --3 failures--> open --60 s--> half-open --success--> closed
                                              |--failure--> open

State is in memory and protected by a lock, because gunicorn serves
requests on several threads. The clock is injectable so tests don't sleep.
"""

import threading
import time
from collections.abc import Callable


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        reset_after_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._reset_after = reset_after_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._trial_in_progress = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state()

    def allow_request(self) -> bool:
        with self._lock:
            state = self._state()
            if state == "closed":
                return True
            if state == "half-open" and not self._trial_in_progress:
                self._trial_in_progress = True  # exactly one trial request
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None
            self._trial_in_progress = False

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            self._trial_in_progress = False
            if self._opened_at is not None or self._consecutive_failures >= self._threshold:
                self._opened_at = self._clock()  # (re)open

    def _state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at < self._reset_after:
            return "open"
        return "half-open"
