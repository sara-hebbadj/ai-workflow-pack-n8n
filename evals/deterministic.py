"""Checks that need no language model. These numbers are real and can be reported today.

    python -m evals.deterministic

Writes evals/deterministic/results.json and results.md. Where a rule exists twice (Python reference
and the JavaScript inside the n8n workflow), both are run and compared.
"""

import json
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from evals.js_bridge import node_available, run_code_node
from workflow_pack.baselines import enquiry_baseline, invoice_baseline, narrative_baseline, ticket_baseline
from workflow_pack.common import SeenStore, normalise_text
from workflow_pack.config import DATA_DIR, INVOICE_MIN_CONFIDENCE, MONEY_TOLERANCE
from workflow_pack.enquiry import looks_like_injection
from workflow_pack.invoice import FIELDS, decide, extract_text
from workflow_pack.report import check_narrative, compute_numbers, read_csv
from workflow_pack.triage import safety_match

OUT = Path(__file__).resolve().parent / "deterministic"


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def frac(correct: int, total: int) -> dict:
    return {"correct": correct, "total": total, "pct": round(100 * correct / total, 1) if total else None}


def same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(float(a) - float(b)) < 0.005
    return normalise_text(None if a is None else str(a)) == normalise_text(None if b is None else str(b))


# ------------------------------------------------------------------ invoices


def invoice_checks() -> dict:
    invoices = jsonl(DATA_DIR / "invoices" / "labels.jsonl")
    texts = {inv["id"]: extract_text(DATA_DIR / inv["input"]["file"]) for inv in invoices}
    extracted = sum(1 for inv in invoices if texts[inv["id"]].strip() and
                    (inv["label"]["invoice_number"] is None or inv["label"]["invoice_number"] in texts[inv["id"]]))  # fmt: skip

    def statuses(field_source) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            store = SeenStore(Path(tmp) / "state.sqlite")
            return [decide(field_source(inv), [], store)["status"] for inv in invoices]

    printed = lambda inv: {**{k: inv["label"][k] for k in FIELDS}, "confidence": 1.0}  # noqa: E731
    py_status = statuses(printed)
    expected = [inv["label"]["expected_status"] for inv in invoices]
    planted = [inv["label"]["issue"] != "none" for inv in invoices]
    result = {
        "text_extraction_ok (pypdf / utf-8)": frac(extracted, len(invoices)),
        "validator_on_perfect_fields: status == expected": frac(sum(a == b for a, b in zip(py_status, expected)), len(invoices)),
        "validator_on_perfect_fields: planted issues not booked": frac(
            sum(1 for s, p in zip(py_status, planted) if p and s != "accepted"), sum(planted)),
        "validator_on_perfect_fields: clean invoices booked": frac(
            sum(1 for s, p in zip(py_status, planted) if not p and s == "accepted"), len(planted) - sum(planted)),
    }  # fmt: skip

    baseline = {inv["id"]: invoice_baseline(texts[inv["id"]]) for inv in invoices}
    for field in FIELDS:
        result[f"regex_baseline_field: {field}"] = frac(
            sum(same(baseline[i["id"]][field], i["label"][field]) for i in invoices), len(invoices)
        )
    result["regex_baseline: all 8 fields correct"] = frac(
        sum(all(same(baseline[i["id"]][f], i["label"][f]) for f in FIELDS) for i in invoices), len(invoices))  # fmt: skip
    base_status = statuses(lambda inv: baseline[inv["id"]])
    result["regex_baseline: status == expected"] = frac(sum(a == b for a, b in zip(base_status, expected)), len(invoices))

    if node_available():  # the same rule, as written inside the n8n workflow
        static: dict = {}
        js_status = []
        config = [{"money_tolerance": MONEY_TOLERANCE, "invoice_min_confidence": INVOICE_MIN_CONFIDENCE}]
        for inv in invoices:
            item = {"file_name": inv["id"], "run_tag": "", "ai": printed(inv)}
            out = run_code_node("04_invoice_extraction.json", "Check totals & VAT (code)", [item], {"Config": config}, static)
            static = out["staticData"]
            js_status.append(out["output"][0]["status"])
        result["n8n JS validator: same status as Python"] = frac(sum(a == b for a, b in zip(js_status, py_status)), len(invoices))
    return result


# ------------------------------------------------------------------ weekly report


def report_checks() -> dict:
    weeks = jsonl(DATA_DIR / "weekly_report" / "weeks.jsonl")
    tickets = read_csv(DATA_DIR / "weekly_report" / "tickets.csv")
    enquiries = read_csv(DATA_DIR / "weekly_report" / "enquiries.csv")

    def leaf_checks(numbers: dict, truth: dict) -> tuple[int, int]:
        pairs = [(numbers[k].get(s), v[s]) if isinstance(v, dict) else (numbers.get(k), v) for k, v in truth.items()
                 for s in (v if isinstance(v, dict) else [None])]  # fmt: skip
        return sum(a == b for a, b in pairs), len(pairs)

    passed = total = faithful = caught_typed = caught_unknown = 0
    py_numbers = {}
    for week in weeks:
        numbers = compute_numbers(tickets, enquiries, week["input"]["week_start"])
        py_numbers[week["id"]] = numbers
        ok, n = leaf_checks(numbers, week["label"])
        passed, total = passed + ok, total + n
        narrative = narrative_baseline(numbers)["narrative"]
        faithful += not check_narrative(narrative, numbers)[1]
        # Two kinds of bad narrative: the AI typed a (wrong) number itself, or it invented a metric.
        typed = narrative.replace("{sla_breaches}", str(numbers["sla_breaches"] + 1))
        caught_typed += bool(check_narrative(typed, numbers)[1])
        invented = narrative.replace("{sla_breaches}", "{refund_total}")
        caught_unknown += bool(check_narrative(invented, numbers)[1])
    result = {
        "python numbers == generator truth (leaf checks)": frac(passed, total),
        "narrative check: placeholder narratives accepted": frac(faithful, len(weeks)),
        "narrative check: a typed wrong number caught": frac(caught_typed, len(weeks)),
        "narrative check: an invented metric caught": frac(caught_unknown, len(weeks)),
    }
    if node_available():
        js_passed = js_total = same_as_py = 0
        ticket_items, enquiry_items = tickets, enquiries
        for week in weeks:
            nodes = {
                "Config": [{"model_main": "x", "prompt_narrative": "x"}],
                "Seen before?": [{"week_start": week["input"]["week_start"]}],
                "Parse tickets CSV": ticket_items,
                "Parse enquiries CSV": enquiry_items,
            }
            out = run_code_node("03_weekly_report.json", "Compute numbers (code)", [{}], nodes)
            js_numbers = out["output"][0]["numbers"]
            ok, n = leaf_checks(js_numbers, week["label"])
            js_passed, js_total = js_passed + ok, js_total + n
            same_as_py += js_numbers == py_numbers[week["id"]]
        result["n8n JS numbers == generator truth (leaf checks)"] = frac(js_passed, js_total)
        result["n8n JS numbers identical to Python (weeks)"] = frac(same_as_py, len(weeks))
    return result


# ------------------------------------------------------------------ keyword baselines and tripwires


def enquiry_checks() -> dict:
    rows = jsonl(DATA_DIR / "enquiries.jsonl")
    predictions = [(enquiry_baseline(r["input"]), r["label"]) for r in rows]
    non_spam = [(p, label) for p, label in predictions if label["category"] != "spam"]
    result = {"keyword_baseline: category": frac(sum(p["category"] == label["category"] for p, label in predictions), len(rows))}
    for field in ("name", "company", "urgency", "language"):
        result[f"keyword_baseline: {field} (non-spam)"] = frac(
            sum(same(p[field], label[field]) for p, label in non_spam), len(non_spam)
        )
    injected = [looks_like_injection(f"{r['input']['subject']}\n{r['input']['body']}") for r in rows]
    truth = [r["label"]["injection"] for r in rows]
    result["injection tripwire: injections flagged"] = frac(sum(i and t for i, t in zip(injected, truth)), sum(truth))
    result["injection tripwire: clean emails not flagged"] = frac(
        sum(not i and not t for i, t in zip(injected, truth)), len(truth) - sum(truth)
    )
    result["label distribution"] = dict(Counter(r["label"]["category"] for r in rows))
    return result


def ticket_checks() -> dict:
    rows = jsonl(DATA_DIR / "tickets.jsonl")
    predictions = [(ticket_baseline(r["input"]), r["label"]) for r in rows]
    result = {
        f"keyword_baseline: {k}": frac(sum(p[k] == label[k] for p, label in predictions), len(rows))
        for k in ("priority", "sentiment", "team")
    }
    p1 = [r for r in rows if r["label"]["priority"] == "P1"]
    other = [r for r in rows if r["label"]["priority"] != "P1"]
    hit = lambda r: bool(safety_match(f"{r['input']['subject']}\n{r['input']['body']}"))  # noqa: E731
    result["safety net alone: true P1 caught"] = frac(sum(hit(r) for r in p1), len(p1))
    result["safety net alone: non-P1 not flagged"] = frac(sum(not hit(r) for r in other), len(other))
    result["label distribution"] = dict(Counter(r["label"]["priority"] for r in rows))
    return result


def to_markdown(results: dict) -> str:
    lines = [f"# Deterministic checks (no language model) - {results['date']}", "", f"Command: `{results['command']}`", ""]
    for section, checks in results["checks"].items():
        lines += [f"## {section}", "", "| Check | Result |", "|---|---|"]
        for name, value in checks.items():
            shown = (
                f"{value['correct']}/{value['total']} ({value['pct']}%)"
                if isinstance(value, dict) and "correct" in value
                else json.dumps(value)
            )
            lines.append(f"| {name} | {shown} |")
        lines.append("")
    lines.append("Caveat: the keyword baselines and the test labels were written by the same author (a coding agent), "
                 "so baseline scores on this set are optimistic. They are a sanity floor, not a fair benchmark.")  # fmt: skip
    return "\n".join(lines) + "\n"


def main() -> None:
    results = {
        "date": datetime.now(UTC).date().isoformat(),
        "command": "python -m evals.deterministic",
        "node_js_checks": node_available(),
        "checks": {
            "invoices": invoice_checks(),
            "weekly_report": report_checks(),
            "enquiries": enquiry_checks(),
            "tickets": ticket_checks(),
        },
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "results.md").write_text(to_markdown(results), encoding="utf-8")
    print(to_markdown(results))


if __name__ == "__main__":
    main()
