from app.llm.circuit_breaker import CircuitBreaker


class Clock:
    """A clock the test moves by hand, so nothing has to sleep."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_breaker() -> tuple[CircuitBreaker, Clock]:
    clock = Clock()
    return CircuitBreaker(failure_threshold=3, reset_after_seconds=60, clock=clock), clock


def test_starts_closed_and_allows_requests():
    breaker, _ = make_breaker()

    assert breaker.state == "closed"
    assert breaker.allow_request()


def test_opens_after_three_consecutive_failures():
    breaker, _ = make_breaker()

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "closed"
    breaker.record_failure()

    assert breaker.state == "open"
    assert not breaker.allow_request()


def test_a_success_resets_the_failure_count():
    breaker, _ = make_breaker()
    breaker.record_failure()
    breaker.record_failure()

    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()

    assert breaker.state == "closed"


def test_after_60_seconds_exactly_one_trial_request_is_allowed():
    breaker, clock = make_breaker()
    for _ in range(3):
        breaker.record_failure()

    clock.now += 59
    assert not breaker.allow_request()
    clock.now += 1

    assert breaker.state == "half-open"
    assert breaker.allow_request()
    assert not breaker.allow_request()  # a second caller must wait for the trial


def test_successful_trial_closes_the_breaker():
    breaker, clock = make_breaker()
    for _ in range(3):
        breaker.record_failure()
    clock.now += 60
    breaker.allow_request()

    breaker.record_success()

    assert breaker.state == "closed"


def test_failed_trial_reopens_for_another_60_seconds():
    breaker, clock = make_breaker()
    for _ in range(3):
        breaker.record_failure()
    clock.now += 60
    breaker.allow_request()

    breaker.record_failure()

    assert breaker.state == "open"
    clock.now += 59
    assert not breaker.allow_request()
    clock.now += 1
    assert breaker.allow_request()
