"""Build the n8n workflow JSON files in workflows/ from readable sources.

    python scripts/build_workflows.py

Sources: the JavaScript for each Code node (workflows/code/), the prompts (prompts/), the JSON
schemas (schemas/) and the rule tables in the Python package (for example the safety keywords).
Pulling the rule tables from Python means the n8n workflows and the Python reference cannot drift.

If you edit a workflow in the n8n editor instead, export it over the JSON file; the tests check the
JSON files themselves, however they were produced.
"""

import importlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from n8n_nodes import (  # noqa: E402
    Flow,
    append_to_file,
    code,
    config,
    error_trigger,
    extract,
    hash_file,
    hash_text,
    if_true,
    llm_call,
    read_file,
    respond,
    schedule,
    sticky,
    text_to_file,
    wait_for_webhook,
    webhook,
    write_file,
)

from workflow_pack.common import load_prompt, load_schema  # noqa: E402
from workflow_pack.config import CONFIDENCE_THRESHOLD, INVOICE_MIN_CONFIDENCE, MONEY_TOLERANCE  # noqa: E402

CODE_DIR = REPO / "workflows" / "code"
OUT_DIR = REPO / "workflows"
ERROR_WORKFLOW_ID = "wfErrorLogger001"
DEFAULTS = {
    "llm_base_url": "https://openrouter.ai/api/v1",
    "model_cheap": "REPLACE_WITH_MODEL_CHEAP",
    "model_main": "REPLACE_WITH_MODEL_MAIN",
    "base_dir": "/home/node/ai-workflow-pack-n8n",
}
DX, ERR_Y = 230, 420  # layout: distance between nodes, height of the error branch


def js(relative_path: str, **replacements: str) -> str:
    """Load a Code node script, inline its @include files and fill the placeholders."""
    text = (CODE_DIR / relative_path).read_text(encoding="utf-8")
    text = re.sub(
        r"^// @include (\S+)\n", lambda m: (CODE_DIR / "lib" / m.group(1)).read_text(encoding="utf-8"), text, flags=re.M
    )
    text = re.sub(r"__CONST:([\w.]+)__", lambda m: json.dumps(python_constant(m.group(1)), ensure_ascii=False), text)
    text = re.sub(r"__SCHEMA:(\w+)__", lambda m: json.dumps(load_schema(m.group(1)), ensure_ascii=False), text)
    for key, value in replacements.items():
        text = text.replace(f"__{key}__", value)
    leftover = re.findall(r"__[A-Z_]+(?::[\w.]+)?__", text)
    if leftover:
        raise ValueError(f"{relative_path}: unfilled placeholders {leftover}")
    return text


def python_constant(dotted: str):
    module, name = dotted.rsplit(".", 1)
    return getattr(importlib.import_module(module), name)


def settings(flow: Flow) -> dict:
    data = flow.to_json()
    data["settings"]["errorWorkflow"] = ERROR_WORKFLOW_ID  # uncaught failures go to 00_error_logger
    return data


def add_writer(f: Flow, prefix: str, rows_node: str, x: int, y: int, append: bool = True) -> tuple[str, str]:
    """Code node items {target_path, line} -> text file -> append to the path in each item."""
    to_file = f.add(text_to_file(f"{prefix} to file", "line" if append else "content"), x, y)
    path = f"={{{{ $('{rows_node}').item.json.target_path }}}}"
    writer = f.add((append_to_file if append else write_file)(f"{prefix}: write", path), x + DX, y)
    f.chain(rows_node, to_file, writer)
    return to_file, writer


def add_error_branch(f: Flow, workflow: str, id_field: str, id_fallback: str, x: int) -> str:
    """Shared error branch: errors.csv row -> write -> respond 500. Returns the entry node name."""
    script = js("shared/error_row.js", ERROR_COLUMNS=json.dumps(python_constant("workflow_pack.common.ERROR_COLUMNS")),
                WORKFLOW=workflow, KEY_NODE="Seen before?", ID_FIELD=id_field, ID_FALLBACK=id_fallback)  # fmt: skip
    entry = f.add(code("Error: log row", script, catch_errors=False), x, ERR_Y)
    _, writer = add_writer(f, "Error row", entry, x + DX, ERR_Y)
    reply = f.add(respond("Respond: error", "={{ $('Error: log row').first().json.response }}", 500), x + 3 * DX, ERR_Y)
    f.connect(writer, reply)
    f.add(sticky("Note: errors", "## Error branch\nAPI failures (after 3 tries), bad input and broken files land here: "
                 "one row in `logs/errors.csv`, the idempotency key is released so the input can be retried, "
                 "and the caller gets HTTP 500.", 420, 160, 3), x, ERR_Y + 150)  # fmt: skip
    return entry


def seen_before(binary_source: str = "undefined") -> dict:
    return code("Seen before?", js("shared/seen_before.js", BINARY_SOURCE=binary_source), catch_errors=False)


def check_ai_output(schema: str, request_node: str) -> dict:
    script = js(
        "shared/check_ai_output.js", SCHEMA=json.dumps(load_schema(schema), ensure_ascii=False), REQUEST_NODE=request_node
    )
    return code("Check AI output (schema)", script, catch_errors=False)


# ------------------------------------------------------------------ 00 error logger


def build_error_logger() -> dict:
    f = Flow("00 Error logger (global)", ERROR_WORKFLOW_ID)
    f.add(error_trigger("When any workflow fails"), 0, 0)
    f.add(config("Config", {"base_dir": DEFAULTS["base_dir"]}), DX, 0)
    f.add(code("Build error row", js("error_logger/build_error_row.js"), catch_errors=False), 2 * DX, 0)
    f.chain("When any workflow fails", "Config", "Build error row")
    add_writer(f, "Error row", "Build error row", 3 * DX, 0)
    f.add(sticky("Note", "## Global error logger\nSet as the *Error Workflow* of the other four. Catches failures "
                 "that no error branch handled and appends them to `logs/errors.csv`.", 420, 140, 3), 0, 180)  # fmt: skip
    return f.to_json()


# ------------------------------------------------------------------ 01 enquiry intake


def build_enquiry() -> dict:
    f = Flow("01 Enquiry intake (AI + human approval)", "wfEnquiryIntake1")
    f.add(webhook("Webhook: new enquiry", "enquiry"), 0, 0)
    settings_ = {
        **DEFAULTS,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "prompt_classify": load_prompt("enquiry_classify"),
        "prompt_draft": load_prompt("enquiry_draft"),
    }
    f.add(config("Config", settings_), DX, 0)
    f.add(code("Check input", js("enquiry/check_input.js")), 2 * DX, 0)
    f.add(hash_text("Make idempotency key", "={{ $json.dedupe_text }}", "dedupe_key"), 3 * DX, 0)
    f.add(seen_before(), 4 * DX, 0)
    f.add(if_true("Duplicate?", "={{ $json.is_duplicate }}"), 5 * DX, 0)
    f.add(respond("Respond: duplicate", "={{ { status: 'duplicate', message_id: $json.message_id } }}"), 6 * DX, -200)
    f.add(code("Build AI request", js("enquiry/build_classify_request.js"), catch_errors=False), 6 * DX, 0)
    f.add(llm_call("AI: classify + extract"), 7 * DX, 0)
    f.add(check_ai_output("enquiry_classify", "Build AI request"), 8 * DX, 0)
    f.add(code("Route (business rules)", js("enquiry/route.js"), catch_errors=False), 9 * DX, 0)
    f.add(if_true("Draft a reply?", "={{ $json.status === 'to_draft' }}"), 10 * DX, 0)
    f.add(code("Build draft request", js("enquiry/build_draft_request.js"), catch_errors=False), 11 * DX, -200)
    f.add(llm_call("AI: draft reply"), 12 * DX, -200)
    f.add(code("Check draft", js("enquiry/check_draft.js"), catch_errors=False), 13 * DX, -200)
    f.add(code("Build output rows", js("enquiry/build_output_rows.js"), catch_errors=False), 14 * DX, 0)
    _, writer = add_writer(f, "Row", "Build output rows", 15 * DX, 0)
    f.add(respond("Respond: result", "={{ $('Build output rows').first().json.response }}"), 17 * DX, 0)
    awaiting = if_true("Waiting for approval?", "={{ $('Build output rows').first().json.status === 'pending_approval' }}")
    f.add({**awaiting, "executeOnce": True}, 18 * DX, 0)
    f.add(wait_for_webhook("Wait for approval"), 19 * DX, -200)
    f.add(code("Record decision", js("enquiry/record_decision.js"), catch_errors=False), 20 * DX, -200)
    add_writer(f, "Decision", "Record decision", 21 * DX, -200)

    f.chain("Webhook: new enquiry", "Config", "Check input", "Make idempotency key", "Seen before?", "Duplicate?")
    f.connect("Duplicate?", "Respond: duplicate", 0)
    f.connect("Duplicate?", "Build AI request", 1)
    f.chain("Build AI request", "AI: classify + extract", "Check AI output (schema)", "Route (business rules)", "Draft a reply?")
    f.connect("Draft a reply?", "Build draft request", 0)
    f.connect("Draft a reply?", "Build output rows", 1)
    f.chain("Build draft request", "AI: draft reply", "Check draft", "Build output rows")
    f.chain(writer, "Respond: result", "Waiting for approval?")
    f.connect("Waiting for approval?", "Wait for approval", 0)
    f.connect("Wait for approval", "Record decision")

    error = add_error_branch(f, "enquiry_intake", "message_id", "$('Webhook: new enquiry').first().json.body.message_id", 2 * DX)
    for source in ("Check input", "AI: classify + extract", "AI: draft reply"):
        f.connect(source, error, 1)
    f.add(sticky("Note: flow", "## Enquiry intake\nEmail in → AI labels it (category + fields) → **code** checks the JSON "
                 "and routes it → AI drafts a reply → the draft waits for a person. Nothing is sent until someone "
                 "opens the approval link (`?decision=approve`). Sending is mocked to `outputs/sent_emails.csv`.",
                 520, 180, 5), 0, -330)  # fmt: skip
    return settings(f)


# ------------------------------------------------------------------ 02 ticket triage


def build_triage() -> dict:
    f = Flow("02 Ticket triage (P1-P4 + escalation)", "wfTicketTriage01")
    f.add(webhook("Webhook: new ticket", "ticket"), 0, 0)
    settings_ = {**DEFAULTS, "confidence_threshold": CONFIDENCE_THRESHOLD, "prompt_triage": load_prompt("ticket_triage")}
    f.add(config("Config", settings_), DX, 0)
    f.add(code("Check input", js("triage/check_input.js")), 2 * DX, 0)
    f.add(seen_before(), 3 * DX, 0)
    f.add(if_true("Duplicate?", "={{ $json.is_duplicate }}"), 4 * DX, 0)
    f.add(respond("Respond: duplicate", "={{ { status: 'duplicate', ticket_id: $json.ticket_id } }}"), 5 * DX, -200)
    f.add(code("Build AI request", js("triage/build_ai_request.js"), catch_errors=False), 5 * DX, 0)
    f.add(llm_call("AI: triage"), 6 * DX, 0)
    f.add(check_ai_output("ticket_triage", "Build AI request"), 7 * DX, 0)
    f.add(if_true("Safety case?", "={{ $('Check input').first().json.safety_keyword !== '' }}"), 7 * DX, 200)
    f.add(code("Apply rules", js("triage/apply_rules.js"), catch_errors=False), 8 * DX, 0)
    f.add(if_true("P1? escalate now", "={{ $json.escalate }}"), 9 * DX, 0)
    f.add(code("Escalation alert", js("triage/escalation_alert.js"), catch_errors=False), 10 * DX, -200)
    _, alert_writer = add_writer(f, "Alert", "Escalation alert", 11 * DX, -200)
    f.add(code("Build output rows", js("triage/build_output_rows.js"), catch_errors=False), 13 * DX, 0)
    _, writer = add_writer(f, "Row", "Build output rows", 14 * DX, 0)
    f.add(respond("Respond: result", "={{ $('Build output rows').first().json.response }}"), 16 * DX, 0)

    f.chain("Webhook: new ticket", "Config", "Check input", "Seen before?", "Duplicate?")
    f.connect("Duplicate?", "Respond: duplicate", 0)
    f.connect("Duplicate?", "Build AI request", 1)
    f.chain("Build AI request", "AI: triage", "Check AI output (schema)", "Apply rules", "P1? escalate now")
    f.connect("AI: triage", "Safety case?", 1)  # AI failed: still escalate safety tickets
    f.connect("Safety case?", "Apply rules", 0)
    f.connect("P1? escalate now", "Escalation alert", 0)
    f.connect("P1? escalate now", "Build output rows", 1)
    f.connect(alert_writer, "Build output rows")
    f.connect(writer, "Respond: result")

    error = add_error_branch(f, "ticket_triage", "ticket_id", "$('Webhook: new ticket').first().json.body.ticket_id", 2 * DX)
    f.connect("Check input", error, 1)
    f.connect("Safety case?", error, 1)
    f.add(sticky("Note: flow", "## Ticket triage\nAI sets priority, sentiment, team and a summary. **Code** applies a "
                 "safety net (allergy, burns, hacking, fraud, legal threats → always P1), escalates P1 immediately "
                 "and posts every ticket to the channel (mock: `outputs/channel_posts.csv`). If the AI is down, "
                 "safety tickets are still escalated.", 520, 190, 5), 0, -340)  # fmt: skip
    return settings(f)


# ------------------------------------------------------------------ 03 weekly report


def build_report() -> dict:
    f = Flow("03 Weekly AI report (numbers in code)", "wfWeeklyReport01")
    f.add(schedule("Every Monday 08:00", "0 8 * * 1"), 0, -100)
    f.add(webhook("Webhook: run report", "weekly-report"), 0, 100)
    f.add(config("Config", {**DEFAULTS, "prompt_narrative": load_prompt("report_narrative")}), DX, 0)
    f.add(code("Pick week", js("report/pick_week.js")), 2 * DX, 0)
    f.add(seen_before(), 3 * DX, 0)
    f.add(if_true("Duplicate?", "={{ $json.is_duplicate }}"), 4 * DX, 0)
    f.add(respond("Respond: duplicate", "={{ { status: 'duplicate', week_start: $json.week_start } }}"), 5 * DX, -200)
    data = "={{ $('Config').first().json.base_dir }}/data/weekly_report"
    f.add({**read_file("Read tickets CSV", data + "/tickets.csv"), "onError": "continueErrorOutput"}, 5 * DX, 0)
    f.add(extract("Parse tickets CSV", "csv"), 6 * DX, 0)
    f.add({**read_file("Read enquiries CSV", data + "/enquiries.csv"), "onError": "continueErrorOutput"}, 7 * DX, 0)
    f.add(extract("Parse enquiries CSV", "csv"), 8 * DX, 0)
    f.add(code("Compute numbers (code)", js("report/compute_numbers.js"), catch_errors=False), 9 * DX, 0)
    f.add(llm_call("AI: write narrative"), 10 * DX, 0)
    f.add(code("Check AI output (schema)", js("shared/check_ai_output.js", SCHEMA=json.dumps(load_schema("report_narrative")),
               REQUEST_NODE="Compute numbers (code)"), catch_errors=False), 11 * DX, 0)  # fmt: skip
    f.add(code("Check narrative", js("report/check_narrative.js"), catch_errors=False), 12 * DX, 0)
    f.add(code("Build report", js("report/build_report.js"), catch_errors=False), 13 * DX, 0)
    _, report_writer = add_writer(f, "Report", "Build report", 14 * DX, 0, append=False)
    f.add({**code("Build output rows", js("report/build_output_rows.js"), catch_errors=False), "executeOnce": True}, 16 * DX, 0)
    _, writer = add_writer(f, "Row", "Build output rows", 17 * DX, 0)
    f.add({**if_true("Started by webhook?", "={{ $('Pick week').first().json.from_webhook }}"), "executeOnce": True}, 19 * DX, 0)
    f.add(respond("Respond: result", "={{ $('Build output rows').first().json.response }}"), 20 * DX, 0)

    f.connect("Every Monday 08:00", "Config")
    f.chain("Webhook: run report", "Config", "Pick week", "Seen before?", "Duplicate?")
    f.connect("Duplicate?", "Respond: duplicate", 0)
    f.connect("Duplicate?", "Read tickets CSV", 1)
    f.chain("Read tickets CSV", "Parse tickets CSV", "Read enquiries CSV", "Parse enquiries CSV", "Compute numbers (code)")
    f.chain("Compute numbers (code)", "AI: write narrative", "Check AI output (schema)", "Check narrative", "Build report")
    f.chain(report_writer, "Build output rows")
    f.chain(writer, "Started by webhook?")
    f.connect("Started by webhook?", "Respond: result", 0)

    error = add_error_branch(f, "weekly_report", "week_start", "$('Webhook: run report').first().json.body.week_start", 2 * DX)
    for source in ("Pick week", "Read tickets CSV", "Read enquiries CSV", "AI: write narrative"):
        f.connect(source, error, 1)
    f.add(sticky("Note: flow", "## Weekly AI report\nEvery number is computed in **code** from the CSVs. The AI only writes "
                 "the narrative, then code checks that every number it mentions exists in the computed data. "
                 "If not, the numbers go out and the narrative is held for review. The email is mocked as "
                 "`outputs/reports/weekly_<date>.md/.html` + a line in `outputs/sent_emails.csv`.", 560, 200, 5),
          0, -380)  # fmt: skip
    return settings(f)


# ------------------------------------------------------------------ 04 invoice extraction


def build_invoice() -> dict:
    f = Flow("04 Invoice or PDF to data (totals checked in code)", "wfInvoiceExtract")
    f.add(webhook("Webhook: invoice file", "invoice"), 0, 0)
    f.add(config("Config", {**DEFAULTS, "invoice_min_confidence": INVOICE_MIN_CONFIDENCE, "money_tolerance": MONEY_TOLERANCE,
                            "prompt_extract": load_prompt("invoice_extract")}), DX, 0)  # fmt: skip
    f.add(code("Check file", js("invoice/check_file.js")), 2 * DX, 0)
    f.add(hash_file("Hash file (SHA-256)", "file", "file_hash"), 3 * DX, 0)
    key_expr = "`${item.run_tag}|file|${item.file_hash}`"
    f.add(code("Seen before?", js("shared/seen_before.js", BINARY_SOURCE="$('Check file').first().binary").replace(
        "item.dedupe_key || item.dedupe_text", key_expr), catch_errors=False), 4 * DX, 0)  # fmt: skip
    f.add(if_true("Duplicate?", "={{ $json.is_duplicate }}"), 5 * DX, 0)
    duplicate_body = "={{ { status: 'duplicate', file_name: $json.file_name, reasons: ['same file already processed'] } }}"
    f.add(respond("Respond: duplicate", duplicate_body), 6 * DX, -250)
    f.add(if_true("PDF?", "={{ $json.is_pdf }}"), 6 * DX, 0)
    f.add({**extract("Extract PDF text", "pdf", "file"), "onError": "continueErrorOutput"}, 7 * DX, -100)
    f.add({**extract("Extract text file", "text", "file", destinationKey="text"), "onError": "continueErrorOutput"}, 7 * DX, 100)
    f.add(code("Build AI request", js("invoice/build_ai_request.js"), catch_errors=False), 8 * DX, 0)
    f.add(if_true("Text found?", "={{ $json.has_text }}"), 9 * DX, 0)
    f.add(llm_call("AI: extract fields"), 10 * DX, -100)
    f.add(check_ai_output("invoice_extract", "Build AI request"), 11 * DX, -100)
    f.add(code("Check totals & VAT (code)", js("invoice/check_totals.js"), catch_errors=False), 12 * DX, -100)
    f.add(code("Build output rows", js("invoice/build_output_rows.js"), catch_errors=False), 13 * DX, 0)
    _, writer = add_writer(f, "Row", "Build output rows", 14 * DX, 0)
    f.add(respond("Respond: result", "={{ $('Build output rows').first().json.response }}"), 16 * DX, 0)

    f.chain("Webhook: invoice file", "Config", "Check file", "Hash file (SHA-256)", "Seen before?", "Duplicate?")
    f.connect("Duplicate?", "Respond: duplicate", 0)
    f.connect("Duplicate?", "PDF?", 1)
    f.connect("PDF?", "Extract PDF text", 0)
    f.connect("PDF?", "Extract text file", 1)
    f.connect("Extract PDF text", "Build AI request")
    f.connect("Extract text file", "Build AI request")
    f.connect("Build AI request", "Text found?")
    f.connect("Text found?", "AI: extract fields", 0)
    f.connect("Text found?", "Build output rows", 1)
    f.chain("AI: extract fields", "Check AI output (schema)", "Check totals & VAT (code)", "Build output rows")
    f.connect(writer, "Respond: result")

    error = add_error_branch(
        f, "invoice_extraction", "file_name", "$('Webhook: invoice file').first().binary.file.fileName", 2 * DX
    )
    for source in ("Check file", "Extract PDF text", "Extract text file", "AI: extract fields"):
        f.connect(source, error, 1)
    f.add(sticky("Note: flow", "## Invoice or PDF to data\nUpload a PDF or .txt (multipart field `file`). The AI reads the "
                 "fields; **code** checks total = net + VAT, VAT = net × rate, known VAT rates, missing fields and "
                 "duplicates (same supplier + number). Clean invoices go to `outputs/invoice_register.csv`; anything "
                 "doubtful goes to the human-check queue.", 560, 190, 5), 0, -360)  # fmt: skip
    return settings(f)


BUILDERS = {
    "00_error_logger.json": build_error_logger,
    "01_enquiry_intake.json": build_enquiry,
    "02_ticket_triage.json": build_triage,
    "03_weekly_report.json": build_report,
    "04_invoice_extraction.json": build_invoice,
}


def main() -> None:
    for file_name, builder in BUILDERS.items():
        path = OUT_DIR / file_name
        path.write_text(json.dumps(builder(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote", path.relative_to(REPO))


if __name__ == "__main__":
    main()
