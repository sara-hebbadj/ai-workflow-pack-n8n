"""Offline stand-in for the model, used by tests, `--dry-run` and the mock server for n8n.

Its answers come from the rule-based baselines, so dry-run numbers are NOT model results.
It can also simulate failures: `fail_ids` raise an API error on every try, `invalid_ids`
return text that is not JSON. That is how the error branch and the review queue are tested.
"""

import json
import re
from pathlib import Path

from workflow_pack.baselines import enquiry_baseline, invoice_baseline, narrative_baseline, ticket_baseline
from workflow_pack.llm import LLMReply, TransientLLMError, with_retries, write_trace

INVALID_TEXT = "Sorry, I cannot help with that."


def task_from_prompt(system_prompt: str) -> str:
    """Every prompt file starts with 'Task: <name>.'"""
    match = re.match(r"Task:\s*(\w+)", system_prompt)
    return match.group(1) if match else "unknown"


def item_id_from(payload: dict) -> str:
    """Find the input's id inside the user message (used by the mock server)."""
    email = payload.get("email") if isinstance(payload.get("email"), dict) else {}
    for key in ("message_id", "ticket_id", "week_start", "file_name"):
        if payload.get(key):
            return str(payload[key])
        if email.get(key):
            return str(email[key])
    return ""


def fake_reply(task: str, user_text: str) -> str:
    payload = json.loads(user_text)
    if task == "enquiry_classify":
        out = enquiry_baseline(payload)
    elif task == "enquiry_draft":
        name = payload["email"].get("from_name") or "there"
        out = {
            "reply_subject": f"Re: {payload['email'].get('subject', '')}"[:150],
            "reply_body": f"Hello {name},\n\nThank you for your message. Our team will get back to you shortly."
            "\n\nLumi Skin Customer Team",
        }
    elif task == "ticket_triage":
        out = ticket_baseline(payload)
    elif task == "report_narrative":
        out = narrative_baseline(payload)
    elif task == "invoice_extract":
        out = invoice_baseline(payload["text"])
    else:
        raise ValueError(f"unknown task {task}")
    return json.dumps(out, ensure_ascii=False)


class FakeClient:
    def __init__(self, fail_ids=(), invalid_ids=(), trace_path: Path | None = None):
        self.fail_ids, self.invalid_ids = set(fail_ids), set(invalid_ids)
        self.trace_path = trace_path
        self.calls: list[tuple[str, str]] = []

    def chat(self, task: str, model_role: str, system: str, user: str, item_id: str) -> LLMReply:
        def once() -> LLMReply:
            self.calls.append((task, item_id))
            if item_id in self.fail_ids:
                write_trace(
                    self.trace_path, {"task": task, "item_id": item_id, "model": "fake", "outcome": "simulated_api_error"}
                )
                raise TransientLLMError(f"simulated API failure for {item_id}")
            text = INVALID_TEXT if item_id in self.invalid_ids else fake_reply(task, user)
            write_trace(self.trace_path, {"task": task, "item_id": item_id, "model": "fake", "outcome": "ok"})
            return LLMReply(text=text, model="fake-baseline")

        return with_retries(once, sleep=lambda _seconds: None)  # same retry logic, no real waiting
