import logging

import pytest

from app.llm.base import LLMError
from app.llm.circuit_breaker import CircuitBreaker
from app.llm.router import LLMRouter
from tests.fakes import ScriptedLLM

OUTAGE = LLMError("timeout", can_fall_back=True)
BAD_KEY = LLMError("HTTP 401", can_fall_back=False)


def make_router(anthropic_error=None, *, default="auto", configured=True, breaker=None):
    anthropic = ScriptedLLM("anthropic", "from claude", error=anthropic_error)
    ollama = ScriptedLLM("ollama", "from ollama")
    router = LLMRouter(
        anthropic, ollama, default=default, breaker=breaker, anthropic_configured=configured
    )
    return router, anthropic, ollama


def test_default_provider_is_used_when_none_is_requested():
    router, _, _ = make_router(default="ollama")

    assert router.generate("s", "u").provider == "ollama"


def test_requested_provider_overrides_the_default():
    router, _, _ = make_router(default="ollama")

    assert router.generate("s", "u", "anthropic").provider == "anthropic"


def test_explicit_anthropic_failure_is_not_hidden_by_a_fallback():
    router, _, ollama = make_router(OUTAGE)

    with pytest.raises(LLMError):
        router.generate("s", "u", "anthropic")
    assert ollama.calls == []


def test_auto_uses_anthropic_when_it_works():
    router, _, ollama = make_router()

    answer = router.generate("s", "u", "auto")

    assert (answer.text, answer.provider, answer.fell_back) == ("from claude", "anthropic", False)
    assert ollama.calls == []


def test_auto_falls_back_to_ollama_on_an_outage_and_logs_a_warning(caplog):
    router, _, _ = make_router(OUTAGE)

    with caplog.at_level(logging.WARNING):
        answer = router.generate("s", "u", "auto")

    assert (answer.text, answer.provider, answer.fell_back) == ("from ollama", "ollama", True)
    assert "llm.fallback from=anthropic to=ollama" in caplog.text


def test_auto_does_not_fall_back_on_errors_a_retry_would_not_fix():
    router, _, ollama = make_router(BAD_KEY)

    with pytest.raises(LLMError, match="401"):
        router.generate("s", "u", "auto")
    assert ollama.calls == []


def test_auto_goes_straight_to_ollama_without_an_api_key():
    router, anthropic, _ = make_router(configured=False)

    answer = router.generate("s", "u", "auto")

    assert answer.provider == "ollama"
    assert anthropic.calls == []


def test_auto_skips_anthropic_while_the_breaker_is_open():
    router, anthropic, ollama = make_router(OUTAGE)

    for _ in range(3):
        router.generate("s", "u", "auto")
    assert router.breaker.state == "open"
    router.generate("s", "u", "auto")

    assert len(anthropic.calls) == 3  # the 4th question didn't wait on Anthropic
    assert len(ollama.calls) == 4


def test_breaker_lets_anthropic_back_in_after_the_reset_period():
    clock = [0.0]
    breaker = CircuitBreaker(clock=lambda: clock[0])
    router, anthropic, _ = make_router(OUTAGE, breaker=breaker)
    for _ in range(3):
        router.generate("s", "u", "auto")

    anthropic.error = None  # Anthropic recovers
    clock[0] += 60

    assert router.generate("s", "u", "auto").provider == "anthropic"
    assert breaker.state == "closed"


def test_unknown_default_is_rejected():
    with pytest.raises(ValueError, match="gpt"):
        make_router(default="gpt")


# --- Ollama GPU between Anthropic and the CPU model -------------------------------------


def make_three(anthropic_error=None, gpu_error=None, *, configured=True):
    anthropic = ScriptedLLM("anthropic", "from claude", error=anthropic_error)
    gpu = ScriptedLLM("ollama_gpu", "from gpu", error=gpu_error)
    ollama = ScriptedLLM("ollama", "from ollama")
    router = LLMRouter(
        anthropic, ollama, default="auto", anthropic_configured=configured, ollama_gpu=gpu
    )
    return router, anthropic, gpu, ollama


def test_auto_falls_back_from_anthropic_to_the_gpu_model(caplog):
    router, _, _, ollama = make_three(OUTAGE)

    with caplog.at_level(logging.WARNING):
        answer = router.generate("s", "u")

    assert (answer.provider, answer.fell_back) == ("ollama_gpu", True)
    assert ollama.calls == []
    assert "llm.fallback from=anthropic to=ollama_gpu" in caplog.text


def test_auto_uses_the_gpu_model_first_without_an_api_key():
    router, anthropic, _, _ = make_three(configured=False)

    answer = router.generate("s", "u")

    assert (answer.provider, answer.fell_back) == ("ollama_gpu", False)
    assert anthropic.calls == []


def test_auto_falls_through_to_the_cpu_model_when_both_are_down(caplog):
    router, _, _, _ = make_three(OUTAGE, OUTAGE)

    with caplog.at_level(logging.WARNING):
        answer = router.generate("s", "u")

    assert (answer.provider, answer.fell_back) == ("ollama", True)
    assert "llm.fallback from=ollama_gpu to=ollama" in caplog.text


def test_the_gpu_model_has_its_own_circuit_breaker():
    router, _, gpu, ollama = make_three(gpu_error=OUTAGE, configured=False)

    for _ in range(4):
        router.generate("s", "u")

    assert router.gpu_breaker.state == "open"
    assert router.breaker.state == "closed"
    assert len(gpu.calls) == 3  # the 4th question went straight to the CPU model
    assert len(ollama.calls) == 4


def test_requesting_ollama_gpu_when_it_is_not_configured_fails_clearly():
    router, _, _ = make_router()

    with pytest.raises(LLMError, match="not configured"):
        router.generate("s", "u", "ollama_gpu")
