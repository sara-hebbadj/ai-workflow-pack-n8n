"""The model client: retries, budget, tracing. The OpenAI SDK call is replaced by a stub (no network)."""

import json
from types import SimpleNamespace

import pytest

from workflow_pack.config import Settings
from workflow_pack.fake_llm import FakeClient, fake_reply, task_from_prompt
from workflow_pack.llm import BudgetExceeded, LLMReply, OpenRouterClient, TransientLLMError, make_client, with_retries

SETTINGS = Settings(api_key="test-key", base_url="http://localhost:9/v1", model_main="m", model_cheap="c", model_judge="j")


def test_retries_back_off_exponentially_then_succeed():
    waits, attempts = [], []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise TransientLLMError("503")
        return LLMReply(text="{}", model="x")

    assert with_retries(flaky, sleep=waits.append).text == "{}"
    assert waits == [1.0, 2.0]


def test_retries_give_up_after_three_tries():
    def always_down():
        raise TransientLLMError("down")

    with pytest.raises(TransientLLMError):
        with_retries(always_down, sleep=lambda _: None)


def test_missing_key_fails_clearly():
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterClient(Settings("", "u", "m", "c", "j"))


def stub_response(text: str, cost: float = 0.0012):
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, cost=cost)
    return SimpleNamespace(model="c", usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_openrouter_client_traces_usage_and_cost(tmp_path, monkeypatch):
    trace = tmp_path / "traces.jsonl"
    client = OpenRouterClient(SETTINGS, trace_path=trace)
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return stub_response('{"ok": true}')

    monkeypatch.setattr(client.client.chat.completions, "create", create)
    reply = client.chat("ticket_triage", "cheap", "system", "user", "t-1")
    assert reply.text == '{"ok": true}' and reply.cost_usd == 0.0012
    assert seen["model"] == "c" and seen["temperature"] == 0 and seen["response_format"] == {"type": "json_object"}
    record = json.loads(trace.read_text().splitlines()[0])
    assert record["item_id"] == "t-1" and record["outcome"] == "ok" and record["prompt_tokens"] == 10


def test_force_role_sends_every_call_to_one_model(monkeypatch):
    models = []

    def create(**kwargs):
        models.append(kwargs["model"])
        return stub_response("{}")

    for force_role, expected in ((None, ["c", "m"]), ("cheap", ["c", "c"]), ("main", ["m", "m"])):
        client = OpenRouterClient(SETTINGS, force_role=force_role)
        monkeypatch.setattr(client.client.chat.completions, "create", create)
        client.chat("ticket_triage", "cheap", "s", "u", "1")
        client.chat("report_narrative", "main", "s", "u", "2")
        assert models[-2:] == expected


def test_budget_guard_stops_the_run(monkeypatch):
    client = OpenRouterClient(SETTINGS, max_cost_usd=0.001)
    monkeypatch.setattr(client.client.chat.completions, "create", lambda **_: stub_response("{}", cost=0.002))
    client.chat("t", "cheap", "s", "u", "1")
    with pytest.raises(BudgetExceeded):
        client.chat("t", "cheap", "s", "u", "2")


def test_make_client_dry_run_is_offline():
    assert isinstance(make_client(True, SETTINGS), FakeClient)


def test_fake_model_reads_the_task_from_the_prompt():
    assert task_from_prompt("Task: invoice_extract.\nYou read...") == "invoice_extract"
    reply = json.loads(fake_reply("ticket_triage", json.dumps({"ticket_id": "t", "subject": "Thanks!", "body": "Loved it"})))
    assert reply["priority"] == "P4" and reply["sentiment"] == "positive"
