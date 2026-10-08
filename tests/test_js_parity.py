"""The JavaScript inside the n8n workflows must make the same decisions as the Python reference.

Runs the Code nodes straight from the exported workflow JSON with Node.js (skipped if Node is missing).
"""

import json

import pytest

from evals.js_bridge import node_available, run_code_node
from workflow_pack.baselines import enquiry_baseline, ticket_baseline
from workflow_pack.common import schema_errors
from workflow_pack.config import CONFIDENCE_THRESHOLD, DATA_DIR
from workflow_pack.enquiry import looks_like_injection, route
from workflow_pack.report import check_narrative, compute_numbers, read_csv
from workflow_pack.triage import apply_rules, safety_match

pytestmark = pytest.mark.skipif(not node_available(), reason="Node.js is not installed")
CONFIG = [{"confidence_threshold": CONFIDENCE_THRESHOLD}]


def ai_reply(obj) -> dict:
    content = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return {"choices": [{"message": {"content": content}}]}


@pytest.mark.parametrize(
    "candidate",
    [
        {"priority": "P2", "sentiment": "negative", "team": "Billing", "summary": "x", "confidence": 0.8},
        {"priority": "P5", "sentiment": "negative", "team": "Billing", "summary": "x", "confidence": 0.8},
        {"priority": "P2", "sentiment": "angry", "team": "Billing", "summary": "x", "confidence": 0.8},
        {"priority": "P2", "sentiment": "negative", "team": "Billing", "summary": "x", "confidence": 1.5},
        {"priority": "P2", "sentiment": "negative", "team": "Billing", "summary": "x"},
        {"priority": "P2", "sentiment": "negative", "team": "Billing", "summary": "x", "confidence": 0.8, "note": "extra"},
        "not json at all",
    ],
)
def test_schema_check_agrees_with_jsonschema(candidate):
    out = run_code_node(
        "02_ticket_triage.json", "Check AI output (schema)", [ai_reply(candidate)], {"Build AI request": [{"ticket_id": "t"}]}
    )
    js_valid = out["output"][0]["ai"] is not None
    py_valid = not schema_errors(candidate if isinstance(candidate, dict) else None, "ticket_triage")
    assert js_valid == py_valid


def test_enquiry_routing_matches_python(enquiries):
    for e in enquiries[::2]:
        ai = enquiry_baseline(e["input"])
        for variant in (ai, {**ai, "confidence": 0.3}, None):
            injection = looks_like_injection(e["input"]["subject"] + "\n" + e["input"]["body"])
            item = {"ai": variant, "injection_suspected": injection}
            out = run_code_node("01_enquiry_intake.json", "Route (business rules)", [item], {"Config": CONFIG})["output"][0]
            expected = route(variant, injection)
            assert {k: out.get(k) for k in expected} == expected, e["id"]


def test_ticket_rules_match_python(tickets):
    for t in tickets[::3]:
        ticket = t["input"]
        keyword = safety_match(ticket["subject"] + "\n" + ticket["body"])
        checked = {"ticket_id": ticket["ticket_id"], "ticket": ticket, "safety_keyword": keyword, "dedupe_text": "x"}
        ai = ticket_baseline(ticket)
        out = run_code_node("02_ticket_triage.json", "Apply rules", [{"ai": ai, "schema_errors": []}],
                            {"Config": CONFIG, "Check input": [checked]})["output"][0]  # fmt: skip
        expected = apply_rules(ai, keyword, ticket["subject"])
        assert {k: out[k] for k in expected} == expected, t["id"]


def test_safety_keywords_match_python(tickets):
    for t in tickets:
        out = run_code_node("02_ticket_triage.json", "Check input", [], {"Webhook: new ticket": [{"body": t["input"]}]})
        assert out["output"][0]["safety_keyword"] == safety_match(t["input"]["subject"] + "\n" + t["input"]["body"]), t["id"]


def test_report_numbers_and_narrative_check_match_python():
    tickets = read_csv(DATA_DIR / "weekly_report" / "tickets.csv")
    enquiries = read_csv(DATA_DIR / "weekly_report" / "enquiries.csv")
    nodes = {"Config": [{"model_main": "m", "prompt_narrative": "p"}], "Seen before?": [{"week_start": "2026-03-02"}],
             "Parse tickets CSV": tickets, "Parse enquiries CSV": enquiries}  # fmt: skip
    numbers = run_code_node("03_weekly_report.json", "Compute numbers (code)", [{}], nodes)["output"][0]["numbers"]
    assert numbers == compute_numbers(tickets, enquiries, "2026-03-02")
    for narrative in ["- {tickets_total} tickets, {tickets_change_pct}% change, {avg_first_response_minutes} min", "- 39 tickets",
                      "- {refund_total} refunds", "- P1 count is {tickets_by_priority.P1}",
                      "- Tickets fell by {tickets_change_pct}%", "- Tickets rose {tickets_change_pct}%",
                      "- Down from last week ({tickets_change_pct}%)"]:  # fmt: skip
        ai = {"headline": "Weekly summary", "narrative": narrative}
        out = run_code_node("03_weekly_report.json", "Check narrative", [{"ai": ai, "numbers": numbers}])["output"][0]
        text, problems = check_narrative(narrative, numbers)
        assert (out["status"] == "sent") == (not problems)
        assert out["reason"] == "; ".join(problems)
        if not problems:
            assert out["narrative"] == text
