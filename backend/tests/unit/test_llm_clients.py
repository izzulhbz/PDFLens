import json

import anthropic
import httpx
import pytest

from app.llm.anthropic_client import AnthropicClient
from app.llm.base import LLMError
from app.llm.ollama_client import OllamaClient
from tests.fakes import FakeAnthropicSDK, anthropic_status_error, anthropic_timeout

# --- AnthropicClient ----------------------------------------------------------------------


def test_anthropic_sends_model_system_prompt_and_question():
    sdk = FakeAnthropicSDK(text="  Answer [p. 2]  ")
    client = AnthropicClient("sk-test", "claude-haiku-5-5", sdk_client=sdk)

    answer = client.generate("SYSTEM", "USER")

    assert answer == "Answer [p. 2]"
    [call] = sdk.create_calls
    assert call["model"] == "claude-haiku-5-5"
    assert call["system"] == "SYSTEM"
    assert call["messages"] == [{"role": "user", "content": "USER"}]


def test_anthropic_client_disables_sdk_retries_and_sets_the_timeout():
    client = AnthropicClient("sk-test", "claude-haiku-5-5", timeout_seconds=10)

    sdk = client._client
    assert sdk.max_retries == 0
    assert sdk.timeout == 10


@pytest.mark.parametrize(
    ("error", "can_fall_back"),
    [
        (anthropic_timeout(), True),
        (anthropic_status_error(500), True),
        (anthropic_status_error(529), True),  # overloaded
        (anthropic_status_error(429), True),  # rate limited
        (anthropic_status_error(401), False),  # bad API key: retrying won't help
        (anthropic_status_error(400), False),  # bad request: our bug
    ],
)
def test_anthropic_errors_say_whether_to_fall_back(error, can_fall_back):
    client = AnthropicClient("sk-test", "m", sdk_client=FakeAnthropicSDK(error=error))

    with pytest.raises(LLMError) as raised:
        client.generate("s", "u")

    assert raised.value.can_fall_back is can_fall_back


def test_anthropic_without_key_is_unavailable_and_never_calls_the_api():
    sdk = FakeAnthropicSDK()
    client = AnthropicClient("", "m", sdk_client=sdk)

    assert client.availability() == (False, "No API key configured")
    with pytest.raises(LLMError):
        client.generate("s", "u")
    assert sdk.create_calls == [] and sdk.list_calls == 0


def test_anthropic_availability_is_cached():
    sdk = FakeAnthropicSDK()
    client = AnthropicClient("sk-test", "m", sdk_client=sdk)

    assert client.availability() == (True, "Reachable")
    assert client.availability() == (True, "Reachable")

    assert sdk.list_calls == 1


def test_anthropic_rejected_key_is_reported():
    sdk = FakeAnthropicSDK()
    sdk.list_error = anthropic_status_error(401)

    assert AnthropicClient("sk-bad", "m", sdk_client=sdk).availability() == (
        False,
        "API key rejected",
    )


def test_anthropic_outage_is_reported_as_unreachable():
    sdk = FakeAnthropicSDK()
    sdk.list_error = anthropic_timeout()

    assert AnthropicClient("sk-test", "m", sdk_client=sdk).availability()[0] is False
    assert isinstance(sdk.list_error, anthropic.APIConnectionError)


# --- OllamaClient ------------------------------------------------------------------------


def ollama(handler) -> httpx.Client:
    return httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(handler))


def test_ollama_sends_system_and_user_messages_with_temperature_zero():
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": " Hi [p. 1] "}}
        )

    answer = OllamaClient(ollama(handler), "llama3.2").generate("SYSTEM", "USER")

    assert answer == "Hi [p. 1]"
    assert sent[0]["model"] == "llama3.2"
    assert sent[0]["stream"] is False
    assert sent[0]["options"] == {"temperature": 0}
    assert sent[0]["messages"] == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "USER"},
    ]


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(200, text="nope"), httpx.Response(200, json={})],
)
def test_ollama_bad_responses_raise_llm_error(response):
    with pytest.raises(LLMError):
        OllamaClient(ollama(lambda request: response), "llama3.2").generate("s", "u")


def test_ollama_availability_needs_the_chat_model_pulled():
    def tags(models):
        return lambda request: httpx.Response(200, json={"models": [{"name": m} for m in models]})

    assert OllamaClient(ollama(tags(["llama3.2:latest"])), "llama3.2").availability()[0] is True
    assert OllamaClient(ollama(tags(["llama3.2:1b"])), "llama3.2").availability() == (
        False,
        "Model llama3.2 not pulled",
    )
