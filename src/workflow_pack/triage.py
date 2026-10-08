"""Workflow 2: ticket triage.

ticket -> AI sets priority, sentiment, team and a summary -> code applies a safety net
-> every ticket is posted to the team "channel"; P1 tickets are escalated immediately.
"""

import json
import re

from workflow_pack.common import (
    append_row,
    idempotency_key,
    load_prompt,
    log_error,
    now_iso,
    parse_json_object,
    schema_errors,
    send_to_review,
)
from workflow_pack.config import CONFIDENCE_THRESHOLD, Paths
from workflow_pack.llm import LLMClient

WORKFLOW = "ticket_triage"
CHANNEL_COLUMNS = ["timestamp", "ticket_id", "status", "priority", "team", "sentiment", "summary", "reason"]
ESCALATION_COLUMNS = ["timestamp", "ticket_id", "priority", "team", "message"]

# Safety net: if any of these appear, the ticket is P1 whatever the AI said.
# High precision on purpose (safety, security, fraud, legal); the AI handles the nuance.
SAFETY_PATTERNS = [
    r"allerg", r"swelling", r"hospital", r"bleed", r"chemical burn", r"poison",
    r"brûlure", r"saigne",
    r"حساسية", r"مستشفى", r"شربت", r"حرق",
    r"hacked", r"اختراق", r"fraud", r"احتيال", r"lawyer", r"legal action",
    r"حماية المستهلك", r"other customers'? (names|data)",
]  # fmt: skip


def safety_match(text: str) -> str:
    """Return the first safety keyword found, or '' if none."""
    for pattern in SAFETY_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return ""


def validate_input(ticket: dict) -> None:
    if not isinstance(ticket, dict):
        raise ValueError("ticket must be a JSON object")
    if not ticket.get("ticket_id"):
        raise ValueError("missing ticket_id")
    if not (ticket.get("body") or "").strip():
        raise ValueError("missing ticket body")


def user_message(ticket: dict) -> str:
    keys = ["ticket_id", "channel", "customer_tier", "subject", "body"]
    return json.dumps({k: ticket.get(k, "") for k in keys}, ensure_ascii=False)


def apply_rules(ai: dict | None, safety_keyword: str, subject: str, threshold: float = CONFIDENCE_THRESHOLD) -> dict:
    """Code decides the final priority and whether to escalate."""
    if safety_keyword:
        # Escalate even if the AI output was broken: a safety ticket must never wait in a queue.
        return {
            "status": "escalated",
            "priority": "P1",
            "team": ai["team"] if ai else "Product",
            "sentiment": ai["sentiment"] if ai else "negative",
            "summary": ai["summary"] if ai else subject,
            "reason": f"safety net matched '{safety_keyword}'",
            "escalate": True,
        }
    if ai is None:
        return {
            "status": "needs_review", "priority": "", "team": "Triage queue", "sentiment": "",
            "summary": subject, "reason": "AI output failed the JSON schema check", "escalate": False,
        }  # fmt: skip
    if ai["priority"] == "P1":
        return {**_ai_fields(ai), "status": "escalated", "reason": "AI set P1", "escalate": True}
    if ai["confidence"] < threshold:
        return {**_ai_fields(ai), "status": "needs_review", "reason": "low confidence", "escalate": False}
    return {**_ai_fields(ai), "status": "routed", "reason": "", "escalate": False}


def _ai_fields(ai: dict) -> dict:
    return {k: ai[k] for k in ("priority", "team", "sentiment", "summary")}


def process_ticket(ticket: dict, client: LLMClient, store, paths: Paths, run_tag: str = "") -> dict:
    item_id = str(ticket.get("ticket_id") or "unknown") if isinstance(ticket, dict) else "unknown"
    try:
        validate_input(ticket)
    except ValueError as e:
        log_error(paths.errors_csv, WORKFLOW, item_id, "prepare_input", e)
        return {"ticket_id": item_id, "status": "error", "reason": str(e)}

    key = idempotency_key(run_tag, item_id)
    if not store.claim(key, WORKFLOW):
        return {"ticket_id": item_id, "status": "duplicate"}

    safety_keyword = safety_match(f"{ticket.get('subject', '')}\n{ticket['body']}")
    try:
        reply = client.chat("ticket_triage", "cheap", load_prompt("ticket_triage"), user_message(ticket), item_id)
    except Exception as e:
        log_error(paths.errors_csv, WORKFLOW, item_id, "ai_triage", e)
        store.release(key)
        if safety_keyword:  # the AI is down but this may be a safety case: escalate anyway
            result = {"ticket_id": item_id, **apply_rules(None, safety_keyword, ticket.get("subject", ""))}
            record(result, paths, [])
            return result
        return {"ticket_id": item_id, "status": "error", "reason": f"AI call failed: {e}"}

    ai = parse_json_object(reply.text)
    errors = schema_errors(ai, "ticket_triage")
    result = {"ticket_id": item_id, **apply_rules(None if errors else ai, safety_keyword, ticket.get("subject", ""))}
    record(result, paths, errors)
    return result


def record(result: dict, paths: Paths, errors: list[str]) -> None:
    """Escalate first (P1), then post to the channel, then queue for a human if needed."""
    ticket_id = result["ticket_id"]
    if result["escalate"]:
        message = f"@on-call P1 ticket {ticket_id} for {result['team']}: {result['summary']}"
        row = {"timestamp": now_iso(), "ticket_id": ticket_id, "priority": "P1", "team": result["team"], "message": message}
        append_row(paths.outputs / "escalations.csv", row, ESCALATION_COLUMNS)
    append_row(paths.outputs / "channel_posts.csv", {"timestamp": now_iso(), **result}, CHANNEL_COLUMNS)
    if result["status"] == "needs_review":
        send_to_review(paths.outputs / "human_review_queue.csv", WORKFLOW, ticket_id, result["reason"], {"schema_errors": errors})
