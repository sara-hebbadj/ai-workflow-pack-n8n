"""Workflow 1: enquiry intake.

email -> AI classifies + extracts fields -> rules in code pick the team -> AI drafts a reply
-> the draft waits for a human to approve it. Nothing is ever sent automatically.
"""

import json
import re

from workflow_pack.common import (
    SENT_COLUMNS,
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

WORKFLOW = "enquiry_intake"
TEAM_BY_CATEGORY = {
    "sales": "Sales",
    "support": "Customer Support",
    "complaint": "Customer Care",
    "partnership": "Partnerships",
    "spam": "Spam archive",
}
SHEET_COLUMNS = [
    "timestamp",
    "message_id",
    "status",
    "reason",
    "category",
    "team",
    "flag",
    "name",
    "company",
    "need",
    "urgency",
    "language",
    "confidence",
    "draft_subject",
    "draft_body",
    "resume_url",
]  # fmt: skip  (resume_url is filled by n8n's Wait node; empty in the Python version)

# A cheap, deterministic tripwire. It does not replace the prompt rules; it makes sure a human
# sees any email that tries to give the AI orders.
INJECTION_PATTERNS = [
    r"ignore (all |the )?(previous|prior|above)? ?(instructions|rules)",
    r"ignore the rules",
    r"system (note|prompt)",
    r"admin mode",
    r"تجاهل (جميع |كل )?(التعليمات|القواعد)",
    r"ignorez (les|toutes les) instructions",
]


def looks_like_injection(text: str) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in INJECTION_PATTERNS)


def validate_input(enquiry: dict) -> None:
    """Reject inputs the workflow cannot handle. These go to the error log, not to the AI."""
    if not isinstance(enquiry, dict):
        raise ValueError("enquiry must be a JSON object")
    if not (enquiry.get("body") or "").strip():
        raise ValueError("missing email body")
    if "@" not in (enquiry.get("from_email") or ""):
        raise ValueError("missing or invalid from_email")


def user_message(enquiry: dict) -> str:
    keys = ["message_id", "from_name", "from_email", "subject", "body"]
    return json.dumps({k: enquiry.get(k, "") for k in keys}, ensure_ascii=False)


def route(ai: dict | None, injection: bool, threshold: float = CONFIDENCE_THRESHOLD) -> dict:
    """Deterministic routing. The AI only labels; code decides what happens next."""
    if ai is None:
        return {"status": "needs_review", "reason": "AI output failed the JSON schema check", "team": "Review queue"}
    team = TEAM_BY_CATEGORY[ai["category"]]
    flag = "manager_cc" if ai["category"] == "complaint" and ai["urgency"] == "high" else ""
    if injection:
        return {"status": "needs_review", "reason": "possible prompt injection", "team": team, "flag": flag}
    if ai["category"] == "spam":
        return {"status": "archived_spam", "reason": "spam: no reply drafted", "team": team, "flag": flag}
    if ai["confidence"] < threshold:
        return {"status": "needs_review", "reason": "low confidence", "team": team, "flag": flag}
    return {"status": "to_draft", "reason": "", "team": team, "flag": flag}


def process_enquiry(enquiry: dict, client: LLMClient, store, paths: Paths, run_tag: str = "") -> dict:
    item_id = str(enquiry.get("message_id") or "unknown") if isinstance(enquiry, dict) else "unknown"
    try:
        validate_input(enquiry)
    except ValueError as e:
        log_error(paths.errors_csv, WORKFLOW, item_id, "prepare_input", e)
        return {"message_id": item_id, "status": "error", "reason": str(e)}

    key_source = enquiry.get("message_id") or f"{enquiry['from_email']}|{enquiry.get('subject', '')}|{enquiry['body']}"
    key = idempotency_key(run_tag, key_source)
    if not store.claim(key, WORKFLOW):
        return {"message_id": item_id, "status": "duplicate"}

    injection = looks_like_injection(f"{enquiry.get('subject', '')}\n{enquiry['body']}")
    try:
        reply = client.chat("enquiry_classify", "cheap", load_prompt("enquiry_classify"), user_message(enquiry), item_id)
    except Exception as e:  # after retries: log, release the key so the email can be retried
        log_error(paths.errors_csv, WORKFLOW, item_id, "ai_classify", e)
        store.release(key)
        return {"message_id": item_id, "status": "error", "reason": f"AI call failed: {e}"}

    ai = parse_json_object(reply.text)
    errors = schema_errors(ai, "enquiry_classify")
    result = {"message_id": item_id, **(ai if not errors else {}), **route(None if errors else ai, injection)}

    if result["status"] == "to_draft":
        result.update(draft_reply(enquiry, result, client, paths, store, key))

    record(enquiry, result, paths, errors)
    return result


def draft_reply(enquiry: dict, result: dict, client: LLMClient, paths: Paths, store, key: str) -> dict:
    item_id = result["message_id"]
    payload = json.dumps({"category": result["category"], "email": json.loads(user_message(enquiry))}, ensure_ascii=False)
    try:
        reply = client.chat("enquiry_draft", "main", load_prompt("enquiry_draft"), payload, item_id)
    except Exception as e:
        log_error(paths.errors_csv, WORKFLOW, item_id, "ai_draft", e)
        store.release(key)
        return {"status": "error", "reason": f"AI draft failed: {e}"}
    draft = parse_json_object(reply.text)
    if schema_errors(draft, "enquiry_draft"):
        return {"status": "needs_review", "reason": "draft reply failed the JSON schema check"}
    return {
        "status": "pending_approval",
        "draft_subject": draft["reply_subject"],
        "draft_body": draft["reply_body"],
    }


def record(enquiry: dict, result: dict, paths: Paths, errors: list[str]) -> None:
    """Write the team sheet row; anything for a human also goes to the shared review queue."""
    if result["status"] == "error":
        return  # already in logs/errors.csv
    append_row(paths.outputs / "enquiry_sheet.csv", {"timestamp": now_iso(), **result}, SHEET_COLUMNS)
    if result["status"] == "needs_review":
        details = {"schema_errors": errors} if errors else {"category": result.get("category")}
        send_to_review(paths.outputs / "human_review_queue.csv", WORKFLOW, result["message_id"], result["reason"], details)


def record_decision(paths: Paths, message_id: str, to: str, subject: str, approved: bool, approver: str) -> dict:
    """Human approval step. Sending is mocked: we only append to sent_emails.csv."""
    row = {
        "timestamp": now_iso(),
        "workflow": WORKFLOW,
        "item_id": message_id,
        "to": to,
        "subject": subject,
        "status": "sent (mock)" if approved else "rejected - not sent",
        "detail": f"decided by {approver}",
    }
    append_row(paths.outputs / "sent_emails.csv", row, SENT_COLUMNS)
    return row
