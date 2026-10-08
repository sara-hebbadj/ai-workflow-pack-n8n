"""Approval inbox: the human step of the enquiry workflow, as a small web page.

    pip install -e ".[app]"
    python app/approval_inbox.py          # opens http://127.0.0.1:7860

Reads the CSV "sheets" the workflows write (outputs/). For drafts created by n8n, Approve/Reject
opens the Wait node's resume link, so n8n records the decision. For drafts created by the Python
reference (no resume link), the decision is written directly to outputs/sent_emails.csv.
Sending is always mocked.
"""

import csv
from pathlib import Path

import gradio as gr
import httpx

from workflow_pack.config import default_paths
from workflow_pack.enquiry import record_decision

PATHS = default_paths()
SHEET = PATHS.outputs / "enquiry_sheet.csv"
REVIEW = PATHS.outputs / "human_review_queue.csv"
SENT = PATHS.outputs / "sent_emails.csv"


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def pending() -> list[dict]:
    """Drafts waiting for a decision (latest row per message, minus those already decided)."""
    decided = {r["item_id"] for r in read_rows(SENT) if r["workflow"] == "enquiry_intake"}
    latest = {r["message_id"]: r for r in read_rows(SHEET) if r["status"] == "pending_approval"}
    return [r for message_id, r in latest.items() if message_id not in decided]


def tables():
    drafts = [[r["message_id"], r["team"], r["category"], r["name"], r["draft_subject"], r["draft_body"]] for r in pending()]
    review = [[r["workflow"], r["item_id"], r["reason"]] for r in read_rows(REVIEW)]
    choices = [d[0] for d in drafts]
    return drafts, review, gr.update(choices=choices, value=choices[0] if choices else None)


def decide(message_id: str, approver: str, approved: bool):
    row = next((r for r in pending() if r["message_id"] == message_id), None)
    if row is None:
        return ("Nothing selected.", *tables())
    if row.get("resume_url"):  # created by n8n: let the waiting workflow record the decision
        decision = "approve" if approved else "reject"
        separator = "&" if "?" in row["resume_url"] else "?"
        httpx.get(f"{row['resume_url']}{separator}decision={decision}&approver={approver or 'unknown'}", timeout=30)
    else:
        record_decision(PATHS, message_id, "", row["draft_subject"], approved, approver or "unknown")
    return (f"{message_id}: {'approved (mock send)' if approved else 'rejected'}", *tables())


with gr.Blocks(title="Approval inbox") as demo:
    gr.Markdown("## Approval inbox\nAI drafts wait here. Nothing is sent until a person approves it.")
    drafts = gr.Dataframe(headers=["message_id", "team", "category", "name", "subject", "draft"], wrap=True, label="Drafts")
    with gr.Row():
        selected = gr.Dropdown(label="Draft", choices=[])
        approver = gr.Textbox(label="Your name", value="")
        approve, reject = gr.Button("Approve", variant="primary"), gr.Button("Reject")
    status = gr.Markdown()
    review = gr.Dataframe(headers=["workflow", "item_id", "reason"], label="Human review queue (all workflows)")
    outputs = [status, drafts, review, selected]
    approve.click(lambda m, a: decide(m, a, True), [selected, approver], outputs)
    reject.click(lambda m, a: decide(m, a, False), [selected, approver], outputs)
    demo.load(lambda: ("", *tables()), None, outputs)

if __name__ == "__main__":
    demo.launch()
