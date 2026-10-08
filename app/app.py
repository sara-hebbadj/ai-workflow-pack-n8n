"""Demo of the four workflows' logic (can run as a Hugging Face Space).

    pip install -e ".[app]"
    python app/app.py        then open http://127.0.0.1:7860

It runs the Python reference implementation (src/workflow_pack/), which applies the same rules as the n8n
Code nodes, on the sample inputs in data/. Each browser session gets its own temporary folder for the CSV
"sheets", queues, outbox and duplicate store, so visitors never see each other's runs.

- With OPENROUTER_API_KEY and MODEL_CHEAP set, the AI steps call that model (OpenRouter).
- Without them the app runs in demo mode: the AI steps are answered by the keyword baselines (FakeClient),
  not by a model. Every rule, check, queue and approval step is the same code in both modes.
n8n itself is not running here: the workflow JSON files can be downloaded from the last tab.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # works without installing (e.g. a Space)

import gradio as gr  # noqa: E402
import pandas as pd  # noqa: E402

from workflow_pack.common import SeenStore  # noqa: E402
from workflow_pack.config import DATA_DIR, REPO_ROOT, Paths, load_settings  # noqa: E402
from workflow_pack.enquiry import process_enquiry, record_decision  # noqa: E402
from workflow_pack.fake_llm import FakeClient  # noqa: E402
from workflow_pack.invoice import extract_text, process_invoice  # noqa: E402
from workflow_pack.llm import OpenRouterClient  # noqa: E402
from workflow_pack.report import process_week  # noqa: E402
from workflow_pack.triage import process_ticket  # noqa: E402

SETTINGS = load_settings()
LIVE = bool(SETTINGS.api_key and SETTINGS.model_cheap)
# One live client for the whole app, so its budget guard (MAX_COST_PER_RUN_USD, default US$3) covers every visitor.
LIVE_CLIENT = OpenRouterClient(SETTINGS, force_role="cheap") if LIVE else None
RUN_LIMIT = int(os.getenv("DEMO_MESSAGE_LIMIT", "20"))  # workflow runs per browser session
MAIN_RUN = REPO_ROOT / "evals" / "results" / "20261008T123216Z_python_cheap" / "summary.json"
N8N_RUN = REPO_ROOT / "evals" / "results" / "20261008T123530Z_n8n_cheap" / "summary.json"

MODE_NOTE = (
    f"**Live AI:** every AI step calls `{SETTINGS.model_cheap}` through OpenRouter ({RUN_LIMIT} workflow runs per session)."
    if LIVE
    else "**Demo mode — live AI is off; add OPENROUTER_API_KEY in Space settings to enable** (plus a `MODEL_CHEAP` "
    "variable). The AI steps are answered by simple keyword rules (`FakeClient`), not by a model, so labels and "
    "drafts are rough. Everything else is the real code: routing, safety net, schema checks, number checks, "
    "VAT checks, duplicate stop, review queue and approval."
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


ENQUIRIES = {row["id"]: row for row in read_jsonl(DATA_DIR / "enquiries.jsonl")}
TICKETS = {row["id"]: row for row in read_jsonl(DATA_DIR / "tickets.jsonl")}
WEEKS = [row["input"]["week_start"] for row in read_jsonl(DATA_DIR / "weekly_report" / "weeks.jsonl")]
INVOICES = {row["id"]: row for row in read_jsonl(DATA_DIR / "invoices" / "labels.jsonl")}


def enquiry_choices() -> list[str]:
    return [f"{key} · {row['input']['subject']}" for key, row in ENQUIRIES.items()]


def ticket_choices() -> list[str]:
    return [f"{key} · {row['input']['subject']}" for key, row in TICKETS.items()]


def invoice_choices() -> list[str]:
    return [
        f"{key} · {Path(row['input']['file']).name} · expected: {row['label']['expected_status']}"
        for key, row in INVOICES.items()
    ]


def key_of(choice: str) -> str:
    return choice.split(" · ", 1)[0]


# ---------- per-session workspace ----------


def new_session() -> dict:
    return {"folder": tempfile.mkdtemp(prefix="workflow-pack-"), "runs": 0}


def workspace(session: dict | None) -> tuple[dict, Paths, SeenStore]:
    session = session or new_session()
    folder = Path(session["folder"])
    paths = Paths(outputs=folder / "outputs", logs=folder / "logs")
    return session, paths, SeenStore(paths.state_db)


def client():
    return LIVE_CLIENT if LIVE else FakeClient()


def over_limit(session: dict) -> bool:
    if session["runs"] >= RUN_LIMIT:
        return True
    session["runs"] += 1
    return False


def sheet(paths: Paths, name: str) -> pd.DataFrame:
    path = paths.outputs / name
    if not path.exists():
        return pd.DataFrame()
    with path.open(encoding="utf-8", newline="") as handle:
        return pd.DataFrame(list(csv.DictReader(handle)))


def pretty(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1)


LIMIT_MESSAGE = f"Demo limit reached ({RUN_LIMIT} runs per session). Press 'New session' to start again."


# ---------- 1. enquiry intake ----------


def load_enquiry(choice: str):
    row = ENQUIRIES[key_of(choice)]["input"]
    return row["message_id"], row["from_name"], row["from_email"], row["subject"], row["body"]


def run_enquiry(message_id, from_name, from_email, subject, body, session):
    session, paths, store = workspace(session)
    if over_limit(session):
        return LIMIT_MESSAGE, "", "", "", session, sheet(paths, "human_review_queue.csv")
    enquiry = {
        "message_id": message_id,
        "from_name": from_name,
        "from_email": from_email,
        "subject": subject,
        "body": body,
        "received_at": "",
    }
    result = process_enquiry(enquiry, client(), store, paths)
    status = {
        "pending_approval": "**Draft waiting for approval.** Nothing is sent until a person approves it below.",
        "needs_review": f"**Sent to the human review queue:** {result.get('reason')}.",
        "archived_spam": "**Archived as spam:** no reply drafted.",
        "duplicate": "**Duplicate:** this message ID was already processed in this session (idempotency check).",
        "error": f"**Logged as an error** in logs/errors.csv: {result.get('reason')}.",
    }.get(result["status"], result["status"])
    shown = {
        k: result.get(k)
        for k in ("category", "team", "flag", "name", "company", "need", "urgency", "language", "confidence", "status", "reason")
        if k in result
    }
    label = ENQUIRIES.get(message_id, {}).get("label")
    if label:
        status += f"\n\nAnswer key for this sample: `{pretty(label)}`"
    return (
        status,
        pretty(shown),
        result.get("draft_subject", ""),
        result.get("draft_body", ""),
        session,
        sheet(paths, "human_review_queue.csv"),
    )


def decide_enquiry(message_id, subject, approved: bool, session):
    session, paths, _ = workspace(session)
    pending = sheet(paths, "enquiry_sheet.csv")
    if pending.empty or not ((pending["message_id"] == message_id) & (pending["status"] == "pending_approval")).any():
        return (
            "Run the workflow first: only a draft that is waiting for approval can be approved.",
            sheet(paths, "sent_emails.csv"),
            session,
        )
    record_decision(paths, message_id, "", subject, approved, "demo-reviewer")
    note = "Approved: the reply was 'sent' (mock outbox)." if approved else "Rejected: nothing was sent."
    return note, sheet(paths, "sent_emails.csv"), session


# ---------- 2. ticket triage ----------


def load_ticket(choice: str):
    row = TICKETS[key_of(choice)]["input"]
    return row["ticket_id"], row["subject"], row["body"]


def run_ticket(ticket_id, subject, body, session):
    session, paths, store = workspace(session)
    if over_limit(session):
        return LIMIT_MESSAGE, "", session, pd.DataFrame()
    base = TICKETS.get(ticket_id, {}).get("input", {"channel": "email", "customer_tier": "standard"})
    ticket = {**base, "ticket_id": ticket_id, "subject": subject, "body": body}
    result = process_ticket(ticket, client(), store, paths)
    if result["status"] == "duplicate":
        status = "**Duplicate:** this ticket ID was already triaged in this session (idempotency check)."
    elif result["status"] == "error":
        status = f"**Logged as an error:** {result.get('reason')}."
    else:
        status = (
            f"**{result['priority'] or 'No priority'} · {result['team']} · {result['status']}**"
            + (" · escalated to on-call now" if result.get("escalate") else "")
            + (f" ({result['reason']})" if result.get("reason") else "")
        )
    label = TICKETS.get(ticket_id, {}).get("label")
    if label:
        status += f"\n\nAnswer key for this sample: `{pretty(label)}`"
    return status, pretty(result), session, sheet(paths, "escalations.csv")


# ---------- 3. weekly report ----------


def run_report(week_start, session):
    session, paths, store = workspace(session)
    if over_limit(session):
        return LIMIT_MESSAGE, "", session
    result = process_week(week_start, client(), store, paths)
    if result["status"] in ("duplicate", "error"):
        return f"**{result['status'].capitalize()}:** {result.get('reason', 'this week was already reported')}", "", session
    report = (paths.outputs / "reports" / f"weekly_{week_start}.md").read_text(encoding="utf-8")
    status = (
        "**Sent (mock):** the narrative passed the number check; every number was filled in by code."
        if result["status"] == "sent"
        else f"**Held for review:** {result['reason']}"
    )
    return status, report, session


# ---------- 4. invoice extraction ----------


def preview_invoice(choice: str) -> str:
    path = DATA_DIR / INVOICES[key_of(choice)]["input"]["file"]
    return extract_text(path)[:2000]


def run_invoice(choice, upload, session):
    session, paths, store = workspace(session)
    if over_limit(session):
        return LIMIT_MESSAGE, "", session, pd.DataFrame(), pd.DataFrame()
    path = Path(upload) if upload else DATA_DIR / INVOICES[key_of(choice)]["input"]["file"]
    result = process_invoice(path, client(), store, paths)
    reasons = "; ".join(result.get("reasons", [])) or "all checks passed"
    status = {
        "accepted": "**Booked** in the invoice register",
        "needs_review": "**Sent to the human-check queue**",
        "duplicate": "**Duplicate: not booked again**",
        "error": "**Logged as an error**",
    }.get(result["status"], result["status"])
    status += f" ({reasons})."
    if not upload:
        status += f"\n\nAnswer key for this sample: `{pretty(INVOICES[key_of(choice)]['label'])}`"
    return (
        status,
        pretty(result.get("fields", {})),
        session,
        sheet(paths, "invoice_register.csv"),
        sheet(paths, "human_review_queue.csv"),
    )


# ---------- results and n8n ----------


def metrics_table(summary_path: Path) -> pd.DataFrame:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = []
    for workflow, data in summary["workflows"].items():
        for metric, value in data.get("metrics", {}).items():
            rows.append({"workflow": workflow, "metric": metric, "correct": value["correct"], "total": value["total"]})
        dup = data.get("duplicates_prevented")
        if dup:
            rows.append(
                {"workflow": workflow, "metric": "duplicates_prevented", "correct": dup["correct"], "total": dup["total"]}
            )
    return pd.DataFrame(rows)


def run_caption(summary_path: Path) -> str:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return (
        f"Run `{summary['run_id']}` · target **{summary['target']}** · model `{summary['model']}` · "
        f"cost US${summary.get('cost_usd', 0)}"
    )


def build() -> gr.Blocks:
    with gr.Blocks(title="AI workflow pack (n8n + AI)") as demo:
        session = gr.State(new_session)
        gr.Markdown(
            "# AI workflow pack (n8n + AI): the four workflows' logic\n"
            "Back-office work for **Lumi Skin**, a fictional skincare shop: enquiry intake with a draft that waits "
            "for approval, ticket triage with a safety net, a weekly report whose numbers come from code, and "
            "invoice extraction with VAT checks and a human-check queue. This page runs the **Python reference "
            "implementation** of the n8n workflows on the synthetic sample inputs. Run the same input twice to see "
            "the duplicate stop."
        )
        gr.Markdown(MODE_NOTE)
        gr.Button("New session (clear my sheets and queues)", size="sm").click(new_session, None, session)

        with gr.Tab("1. Enquiry intake"):
            pick = gr.Dropdown(enquiry_choices(), value=enquiry_choices()[0], label="Sample email")
            with gr.Row():
                message_id = gr.Textbox(label="Message ID")
                from_name = gr.Textbox(label="From name")
                from_email = gr.Textbox(label="From email")
            subject = gr.Textbox(label="Subject")
            body = gr.Textbox(label="Body (edit it, e.g. add 'ignore all previous instructions')", lines=6)
            run = gr.Button("Run the workflow", variant="primary")
            status = gr.Markdown()
            with gr.Row():
                ai_json = gr.Code(language="json", label="AI labels + routing by code")
                with gr.Column():
                    draft_subject = gr.Textbox(label="Draft subject (waits for approval)")
                    draft_body = gr.Textbox(label="Draft reply", lines=8)
            with gr.Row():
                approve = gr.Button("Approve and send (mock)")
                reject = gr.Button("Reject")
            decision = gr.Markdown()
            outbox = gr.Dataframe(label="Outbox (mock): sent_emails.csv", interactive=False, wrap=True)
            review = gr.Dataframe(label="Human review queue", interactive=False, wrap=True)
            fields = [message_id, from_name, from_email, subject, body]
            pick.change(load_enquiry, pick, fields)
            demo.load(load_enquiry, pick, fields)
            run.click(run_enquiry, [*fields, session], [status, ai_json, draft_subject, draft_body, session, review])
            approve.click(
                lambda m, s, st: decide_enquiry(m, s, True, st), [message_id, draft_subject, session], [decision, outbox, session]
            )
            reject.click(
                lambda m, s, st: decide_enquiry(m, s, False, st),
                [message_id, draft_subject, session],
                [decision, outbox, session],
            )

        with gr.Tab("2. Ticket triage"):
            t_pick = gr.Dropdown(ticket_choices(), value=ticket_choices()[0], label="Sample ticket")
            t_id = gr.Textbox(label="Ticket ID")
            t_subject = gr.Textbox(label="Subject")
            t_body = gr.Textbox(label="Body", lines=4)
            t_run = gr.Button("Run the workflow", variant="primary")
            t_status = gr.Markdown()
            t_json = gr.Code(language="json", label="Result (AI labels + rules in code)")
            t_escalations = gr.Dataframe(label="Escalations (P1, on-call)", interactive=False, wrap=True)
            t_fields = [t_id, t_subject, t_body]
            t_pick.change(load_ticket, t_pick, t_fields)
            demo.load(load_ticket, t_pick, t_fields)
            t_run.click(run_ticket, [*t_fields, session], [t_status, t_json, session, t_escalations])

        with gr.Tab("3. Weekly report"):
            gr.Markdown(
                "Code computes every number from the ticket and enquiry CSVs. The AI writes only the "
                "narrative, with placeholders such as `{sla_breaches}`; code fills in the values and holds "
                "the narrative back if the AI typed a number itself."
            )
            week = gr.Dropdown(WEEKS, value=WEEKS[0], label="Week starting (Monday)")
            w_run = gr.Button("Build the report", variant="primary")
            w_status = gr.Markdown()
            w_report = gr.Markdown()
            w_run.click(run_report, [week, session], [w_status, w_report, session])

        with gr.Tab("4. Invoice extraction"):
            gr.Markdown(
                "Code checks total = net + VAT, VAT = net x rate, a known VAT rate, no missing field and no duplicate. "
                "Planted problems to try: inv-009 (VAT mismatch), inv-033 (total mismatch), inv-012 (missing date). "
                "Run the same invoice twice to see the duplicate stop."
            )
            # inv-003: a clean invoice that the demo-mode keyword rules also read correctly
            i_pick = gr.Dropdown(invoice_choices(), value=invoice_choices()[2], label="Sample invoice")
            upload = gr.File(label="Or upload your own invoice (.pdf or .txt)", file_types=[".pdf", ".txt"], type="filepath")
            i_text = gr.Textbox(label="Text extracted from the sample file", lines=8)
            i_run = gr.Button("Run the workflow", variant="primary")
            i_status = gr.Markdown()
            i_fields = gr.Code(language="json", label="Extracted fields")
            register = gr.Dataframe(label="Invoice register", interactive=False, wrap=True)
            i_review = gr.Dataframe(label="Human-check queue", interactive=False, wrap=True)
            i_pick.change(preview_invoice, i_pick, i_text)
            demo.load(preview_invoice, i_pick, i_text)
            i_run.click(run_invoice, [i_pick, upload, session], [i_status, i_fields, session, register, i_review])

        with gr.Tab("Results and n8n"):
            gr.Markdown(
                "### Saved live evaluation (8 October 2026)\n"
                + run_caption(MAIN_RUN)
                + ": all 200 inputs through the Python reference."
            )
            gr.Dataframe(metrics_table(MAIN_RUN), interactive=False)
            gr.Markdown(run_caption(N8N_RUN) + ": the first 10 inputs of each workflow through real n8n 2.35.7.")
            gr.Dataframe(metrics_table(N8N_RUN), interactive=False)
            gr.Markdown("### n8n canvases (screenshots from the local n8n editor)")
            gr.Gallery(
                [str(p) for p in sorted((REPO_ROOT / "docs" / "screenshots").glob("*.png"))],
                columns=2,
                height="auto",
                label="n8n workflows",
            )
            gr.Markdown("### Download the n8n workflow JSON (import into n8n; no keys inside)")
            gr.File([str(p) for p in sorted((REPO_ROOT / "workflows").glob("*.json"))], label="Workflows", interactive=False)
    return demo


if __name__ == "__main__":
    build().launch()
