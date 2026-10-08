"""Workflow 3: weekly AI report.

Code computes every number from the CSVs. The AI only writes the narrative, and code then
checks that every number in the narrative exists in the computed numbers.
"""

import csv
import html
import json
import re
from datetime import date, timedelta
from pathlib import Path

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
from workflow_pack.config import DATA_DIR, Paths
from workflow_pack.llm import LLMClient

WORKFLOW = "weekly_report"
PRIORITIES = ["P1", "P2", "P3", "P4"]
TEAMS = ["Technical", "Billing", "Delivery", "Product", "Account"]
CATEGORIES = ["sales", "support", "complaint", "partnership", "spam"]
SLA_MINUTES = {"P1": 60, "P2": 240, "P3": 1440, "P4": 2880}  # first-response targets


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------- rounding: integer maths so Python and the n8n JavaScript give identical results ----------


def pct(part: int, whole: int) -> float:
    """Percentage with one decimal, rounding halves up."""
    if whole == 0:
        return 0.0
    return ((2000 * part + whole) // (2 * whole)) / 10


def avg1(total: int, count: int) -> float:
    """Average with one decimal, rounding halves up."""
    if count == 0:
        return 0.0
    return ((20 * total + count) // (2 * count)) / 10


def change_pct(current: int, previous: int) -> float | None:
    if previous == 0:
        return None
    sign = -1 if current < previous else 1
    return sign * pct(abs(current - previous), previous)


# ---------- the numbers ----------


def week_window(week_start: str) -> tuple[str, str]:
    start = date.fromisoformat(week_start)
    if start.weekday() != 0:
        raise ValueError(f"week_start {week_start} is not a Monday")
    return start.isoformat(), (start + timedelta(days=6)).isoformat()


def in_week(timestamp: str, start: str, end: str) -> bool:
    # Timestamps are stored in Dubai local time (+04:00), so the first 10 characters are the local date.
    return start <= timestamp[:10] <= end


def compute_numbers(tickets: list[dict], enquiries: list[dict], week_start: str) -> dict:
    start, end = week_window(week_start)
    prev_start, prev_end = week_window((date.fromisoformat(start) - timedelta(days=7)).isoformat())
    week = [t for t in tickets if in_week(t["created_at"], start, end)]
    prev_count = sum(1 for t in tickets if in_week(t["created_at"], prev_start, prev_end))
    week_enq = [e for e in enquiries if in_week(e["received_at"], start, end)]
    minutes = [int(t["first_response_minutes"]) for t in week]
    breaches = sum(1 for t in week if int(t["first_response_minutes"]) > SLA_MINUTES[t["priority"]])
    negatives = sum(1 for t in week if t["sentiment"] == "negative")
    spam = sum(1 for e in week_enq if e["category"] == "spam")
    return {
        "week_start": start,
        "week_end": end,
        "tickets_total": len(week),
        "tickets_prev_week": prev_count,
        "tickets_change_pct": change_pct(len(week), prev_count),
        "tickets_by_priority": {p: sum(1 for t in week if t["priority"] == p) for p in PRIORITIES},
        "tickets_by_team": {team: sum(1 for t in week if t["team"] == team) for team in TEAMS},
        "negative_sentiment_pct": pct(negatives, len(week)),
        "avg_first_response_minutes": avg1(sum(minutes), len(minutes)),
        "sla_breaches": breaches,
        "enquiries_total": len(week_enq),
        "enquiries_by_category": {c: sum(1 for e in week_enq if e["category"] == c) for c in CATEGORIES},
        "spam_pct": pct(spam, len(week_enq)),
    }


# ---------- checking the AI narrative ----------
# The AI never types a number. It writes placeholders such as {tickets_total} or {tickets_by_priority.P1}
# and code fills them in. Any digit the AI typed itself (other than the labels P1-P4) means review.

PLACEHOLDER = re.compile(r"\{([a-z_]+(?:\.[A-Za-z0-9]+)?)\}")
PRIORITY_LABEL = re.compile(r"\bP[1-4]\b")
DIGITS = re.compile(r"[0-9]+")


def format_value(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def lookup(numbers: dict, path: str):
    """'tickets_by_priority.P1' -> numbers['tickets_by_priority']['P1']; KeyError if unknown."""
    value = numbers
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(path)
        value = value[part]
    if isinstance(value, dict):
        raise KeyError(path)
    return value


def check_narrative(text: str, numbers: dict) -> tuple[str, list[str]]:
    """Return (text with placeholders filled, problems). No problems = safe to send."""
    problems = []
    for path in PLACEHOLDER.findall(text):
        try:
            lookup(numbers, path)
        except KeyError:
            problems.append(f"unknown placeholder {{{path}}}")
    typed = DIGITS.findall(PRIORITY_LABEL.sub(" ", PLACEHOLDER.sub(" ", text)))
    if typed:
        problems.append(f"AI typed numbers itself: {', '.join(typed)}")
    if problems:
        return text, problems
    return PLACEHOLDER.sub(lambda m: format_value(lookup(numbers, m.group(1))), text), []


# ---------- rendering the "email" ----------


def numbers_table(numbers: dict) -> list[tuple[str, str]]:
    change = numbers["tickets_change_pct"]
    rows = [
        ("Tickets this week", str(numbers["tickets_total"])),
        ("Tickets last week", str(numbers["tickets_prev_week"])),
        ("Change vs last week (%)", "n/a" if change is None else f"{change:.1f}"),
    ]
    rows += [(f"{p} tickets", str(n)) for p, n in numbers["tickets_by_priority"].items()]
    rows += [
        ("SLA breaches (first response)", str(numbers["sla_breaches"])),
        ("Negative sentiment (%)", f"{numbers['negative_sentiment_pct']:.1f}"),
        ("Average first response (minutes)", f"{numbers['avg_first_response_minutes']:.1f}"),
        ("Enquiries this week", str(numbers["enquiries_total"])),
        ("Spam enquiries (%)", f"{numbers['spam_pct']:.1f}"),
    ]
    return rows


def render_markdown(numbers: dict, headline: str, narrative: str) -> str:
    lines = [f"# Weekly operations report: {numbers['week_start']} to {numbers['week_end']}", "", f"**{headline}**", ""]
    lines += ["| Metric | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in numbers_table(numbers)]
    lines += ["", "## Narrative (AI-written, numbers checked by code)", "", narrative.strip(), ""]
    return "\n".join(lines)


def render_html(numbers: dict, headline: str, narrative: str) -> str:
    rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>" for k, v in numbers_table(numbers))
    bullets = "".join(f"<li>{html.escape(line.lstrip('-* ').strip())}</li>" for line in narrative.splitlines() if line.strip())
    return (
        f"<h1>Weekly operations report: {numbers['week_start']} to {numbers['week_end']}</h1>"
        f"<p><strong>{html.escape(headline)}</strong></p><table>{rows}</table><ul>{bullets}</ul>"
    )


# ---------- the workflow ----------

WITHHELD = "_Narrative withheld: it failed the checks (schema, placeholders or typed numbers). A human must review it._"


def process_week(week_start: str, client: LLMClient, store, paths: Paths, data_dir: Path = DATA_DIR, run_tag: str = "") -> dict:
    try:
        week_window(week_start)  # must be a Monday in YYYY-MM-DD format
    except (TypeError, ValueError) as e:
        log_error(paths.errors_csv, WORKFLOW, str(week_start), "check_input", e)
        return {"week_start": week_start, "status": "error", "reason": str(e)}

    key = idempotency_key(run_tag, week_start)
    if not store.claim(key, WORKFLOW):
        return {"week_start": week_start, "status": "duplicate"}

    try:
        tickets = read_csv(data_dir / "weekly_report" / "tickets.csv")
        enquiries = read_csv(data_dir / "weekly_report" / "enquiries.csv")
        numbers = compute_numbers(tickets, enquiries, week_start)
    except (OSError, KeyError) as e:
        log_error(paths.errors_csv, WORKFLOW, week_start, "read_data", e)
        store.release(key)
        return {"week_start": week_start, "status": "error", "reason": str(e)}

    try:
        user = json.dumps(numbers, ensure_ascii=False)
        reply = client.chat("report_narrative", "main", load_prompt("report_narrative"), user, week_start)
    except Exception as e:
        log_error(paths.errors_csv, WORKFLOW, week_start, "ai_narrative", e)
        store.release(key)
        return {"week_start": week_start, "status": "error", "reason": f"AI call failed: {e}"}

    ai = parse_json_object(reply.text)
    errors = schema_errors(ai, "report_narrative")
    problems = ["AI output failed the JSON schema check"] if errors else []
    if not errors:
        headline, problems_h = check_narrative(ai["headline"], numbers)
        narrative, problems_n = check_narrative(ai["narrative"], numbers)
        problems = problems_h + problems_n
    ok = not problems
    if not ok:
        headline, narrative = "Weekly numbers (narrative held for review)", WITHHELD
    result = {
        "week_start": week_start,
        "status": "sent" if ok else "needs_review",
        "reason": "; ".join(problems),
        "numbers": numbers,
    }
    save_report(result, headline, narrative, paths)
    return result


def save_report(result: dict, headline: str, narrative: str, paths: Paths) -> None:
    numbers, week = result["numbers"], result["week_start"]
    report_dir = paths.outputs / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    md_path = report_dir / f"weekly_{week}.md"
    md_path.write_text(render_markdown(numbers, headline, narrative), encoding="utf-8")
    (report_dir / f"weekly_{week}.html").write_text(render_html(numbers, headline, narrative), encoding="utf-8")
    status = "sent (mock)" if result["status"] == "sent" else "held for review"
    row = {
        "timestamp": now_iso(), "workflow": WORKFLOW, "item_id": week, "to": "ops-managers@example.com",
        "subject": f"Weekly operations report {week}", "status": status, "detail": md_path.name,
    }  # fmt: skip
    append_row(paths.outputs / "sent_emails.csv", row, SENT_COLUMNS)
    if result["status"] == "needs_review":
        send_to_review(paths.outputs / "human_review_queue.csv", WORKFLOW, week, result["reason"])
