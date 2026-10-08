"""Evaluation runner: 50 labelled inputs per workflow, scored against the labels.

    python -m evals.run --model cheap --limit 10        # live model through the Python reference (needs a key)
    python -m evals.run --model mixed                   # cheap model for reading, main model for drafts/narratives
    python -m evals.run --dry-run                       # fake model, proves the pipeline; NOT real results
    python -m evals.run --target n8n --dry-run          # post to the n8n webhooks (n8n pointed at the mock model)
    python -m evals.run --target n8n --model cheap      # post to n8n wired to OpenRouter (real results)

Real runs write to evals/results/<run_id>/, dry runs to evals/dry_run/<run_id>/ so they can never be mixed up.
"""

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from workflow_pack.common import SeenStore, normalise_text
from workflow_pack.config import DATA_DIR, REPO_ROOT, Paths, load_settings
from workflow_pack.enquiry import process_enquiry, record_decision
from workflow_pack.fake_llm import FakeClient
from workflow_pack.invoice import FIELDS as INVOICE_FIELDS
from workflow_pack.invoice import process_invoice
from workflow_pack.llm import OpenRouterClient
from workflow_pack.report import process_week
from workflow_pack.triage import process_ticket

EVALS = Path(__file__).resolve().parent
DATASETS = {
    "enquiry": DATA_DIR / "enquiries.jsonl",
    "triage": DATA_DIR / "tickets.jsonl",
    "report": DATA_DIR / "weekly_report" / "weeks.jsonl",
    "invoice": DATA_DIR / "invoices" / "labels.jsonl",
}
WEBHOOKS = {"enquiry": "enquiry", "triage": "ticket", "report": "weekly-report", "invoice": "invoice"}
# Dry runs inject one API failure and one non-JSON answer per workflow to exercise the error branch and review queue.
DRY_RUN_FAULTS = {
    "fail": {"enq-050", "t-050", "2026-09-14", "inv-050.txt"},
    "invalid": {"enq-049", "t-049", "2026-09-07", "inv-047.txt"},
}


def load(workflow: str, limit: int | None) -> list[dict]:
    rows = [json.loads(line) for line in DATASETS[workflow].read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:limit] if limit else rows


# ------------------------------------------------------------------ running one input


class PythonTarget:
    """Runs the Python reference implementation in-process, with its own outputs folder per run."""

    def __init__(self, client, run_dir: Path, run_tag: str):
        self.client, self.run_tag = client, run_tag
        self.paths = Paths(outputs=run_dir / "outputs", logs=run_dir / "logs")
        self.store = SeenStore(run_dir / "state.sqlite")

    def run(self, workflow: str, item: dict) -> dict:
        args = (self.client, self.store, self.paths, self.run_tag)
        if workflow == "enquiry":
            return process_enquiry(item["input"], *args)
        if workflow == "triage":
            return process_ticket(item["input"], *args)
        if workflow == "report":
            return process_week(item["input"]["week_start"], self.client, self.store, self.paths, DATA_DIR, self.run_tag)
        return process_invoice(DATA_DIR / item["input"]["file"], *args)

    def approve(self, result: dict, item: dict) -> bool:
        record_decision(
            self.paths, result["message_id"], item["input"]["from_email"], result.get("draft_subject", ""), True, "eval"
        )
        return result["message_id"] in (self.paths.outputs / "sent_emails.csv").read_text(encoding="utf-8")


class N8nTarget:
    """Posts each input to the workflow's production webhook and reads the JSON answer."""

    def __init__(self, base_url: str, run_tag: str):
        self.base_url, self.run_tag = base_url.rstrip("/"), run_tag
        self.http = httpx.Client(timeout=120)

    def run(self, workflow: str, item: dict) -> dict:
        url = f"{self.base_url}/webhook/{WEBHOOKS[workflow]}"
        if workflow == "invoice":
            path = DATA_DIR / item["input"]["file"]
            response = self.http.post(url, files={"file": (path.name, path.read_bytes())}, data={"run_tag": self.run_tag})
        elif workflow == "report":
            response = self.http.post(url, json={"week_start": item["input"]["week_start"], "run_tag": self.run_tag})
        else:
            response = self.http.post(url, json={**item["input"], "run_tag": self.run_tag})
        try:
            result = response.json()
        except ValueError:
            result = {"status": "error", "reason": f"HTTP {response.status_code}: {response.text[:200]}"}
        if workflow == "triage" and "escalated" in result:
            result["escalate"] = result.pop("escalated")
        return result

    def approve(self, result: dict, item: dict) -> bool:
        response = self.http.get(result["approve_url"] + "&approver=eval")
        return response.status_code == 200


# ------------------------------------------------------------------ scoring


def same(predicted, expected) -> bool:
    if isinstance(expected, float) or isinstance(predicted, float):
        return predicted is not None and expected is not None and abs(float(predicted) - float(expected)) < 0.005
    return normalise_text(None if predicted is None else str(predicted)) == normalise_text(
        None if expected is None else str(expected)
    )


def score_item(workflow: str, result: dict, label: dict) -> dict:
    """Per-item correctness flags (None = not applicable)."""
    status = result.get("status")
    if workflow == "enquiry":
        scored = status not in ("error", "duplicate") and "category" in result
        row = {"category_ok": scored and result["category"] == label["category"]}
        for field in ("name", "company", "urgency", "language"):
            row[f"{field}_ok"] = (scored and same(result.get(field), label[field])) if label["category"] != "spam" else None
        row["injection_held"] = status in ("needs_review", "archived_spam") if label["injection"] else None
        return row
    if workflow == "triage":
        return {
            "priority_ok": result.get("priority") == label["priority"],
            "sentiment_ok": result.get("sentiment") == label["sentiment"],
            "team_ok": result.get("team") == label["team"],
            "p1_escalated": bool(result.get("escalate")) if label["priority"] == "P1" else None,
            "non_p1_not_escalated": not result.get("escalate") if label["priority"] != "P1" else None,
        }
    if workflow == "report":
        numbers = result.get("numbers")
        if not numbers:  # error before a report was produced: nothing to check
            return {"number_checks": 0, "number_checks_passed": 0, "narrative_ok": False}
        checks = [(k, sub) for k, v in label.items() for sub in (v if isinstance(v, dict) else [None])]
        passed = sum(1 for k, sub in checks if _report_value(numbers, k, sub) == _report_value(label, k, sub))
        return {"number_checks": len(checks), "number_checks_passed": passed, "narrative_ok": status == "sent"}
    fields = result.get("fields") or {}
    row = {f"{f}_ok": same(fields.get(f), label[f]) if fields else False for f in INVOICE_FIELDS}
    row["all_fields_ok"] = all(row[f"{f}_ok"] for f in INVOICE_FIELDS)
    row["status_ok"] = status == label["expected_status"]
    return row


def _report_value(source: dict, key: str, sub):
    value = source.get(key)
    return value.get(sub) if isinstance(value, dict) and sub is not None else value


def rate(rows: list[dict], key: str) -> dict:
    values = [r[key] for r in rows if r.get(key) is not None]
    return {"correct": sum(bool(v) for v in values), "total": len(values)}


def summarise(workflow: str, rows: list[dict], duplicates: dict, approval: dict | None) -> dict:
    statuses = {}
    for r in rows:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    summary = {
        "n": len(rows),
        "statuses": statuses,
        "errors_logged": statuses.get("error", 0),
        "duplicates_prevented": duplicates,
    }
    keys = {
        "enquiry": ["category_ok", "name_ok", "company_ok", "urgency_ok", "language_ok", "injection_held"],
        "triage": ["priority_ok", "sentiment_ok", "team_ok", "p1_escalated", "non_p1_not_escalated"],
        "report": ["narrative_ok"],
        "invoice": [f"{f}_ok" for f in INVOICE_FIELDS] + ["all_fields_ok", "status_ok"],
    }[workflow]
    summary["metrics"] = {k: rate(rows, k) for k in keys}
    if workflow == "report":
        summary["metrics"]["number_checks"] = {
            "correct": sum(r["number_checks_passed"] for r in rows), "total": sum(r["number_checks"] for r in rows)}  # fmt: skip
    if workflow == "invoice":
        summary["human_review_rate"] = {"count": statuses.get("needs_review", 0), "total": len(rows)}
        summary["metrics"]["planted_issue_not_booked"] = rate(rows, "issue_caught")
    if workflow == "enquiry":
        summary["sent_without_approval"] = sum(1 for r in rows if str(r["status"]).startswith("sent"))
        summary["approval_flow"] = approval
    return summary


# ------------------------------------------------------------------ main


def run_workflow(target, workflow: str, limit: int | None) -> tuple[list[dict], dict]:
    items = load(workflow, limit)
    rows, raw = [], []
    for item in items:
        result = target.run(workflow, item)
        raw.append({"id": item["id"], "result": result, "label": item["label"]})
        row = {"id": item["id"], "status": result.get("status"), **score_item(workflow, result, item["label"])}
        if workflow == "invoice":
            row["issue_caught"] = (
                result.get("status") in ("needs_review", "duplicate") if item["label"]["issue"] != "none" else None
            )
        rows.append(row)
    # Idempotency: send the first few inputs again; every one must come back as "duplicate".
    again = [target.run(workflow, item) for item in items[: min(5, len(items))]]
    duplicates = {"correct": sum(1 for r in again if r.get("status") == "duplicate"), "total": len(again)}
    approval = None
    if workflow == "enquiry":
        pending = [
            (r["result"], next(i for i in items if i["id"] == r["id"]))
            for r in raw
            if r["result"].get("status") == "pending_approval"
        ]
        approval = {"approved_and_logged": target.approve(*pending[0]) if pending else None}
    return rows, {"raw": raw, "summary": summarise(workflow, rows, duplicates, approval)}


def write_outputs(run_dir: Path, workflow: str, rows: list[dict], details: dict) -> None:
    with (run_dir / f"{workflow}_items.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with (run_dir / f"{workflow}_results.jsonl").open("w", encoding="utf-8") as f:
        for record in details["raw"]:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workflow", choices=["all", *DATASETS], default="all")
    parser.add_argument(
        "--model",
        choices=["cheap", "main", "mixed"],
        default="cheap",
        help="python target: cheap/main = every AI call uses MODEL_CHEAP/MODEL_MAIN; mixed = cheap for reading tasks, "
        "main for drafts and narratives (as in the n8n Config node). n8n target: label only (set models in n8n)",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="fake model; outputs go to evals/dry_run/ and are NOT results")
    parser.add_argument("--target", choices=["python", "n8n"], default="python")
    parser.add_argument("--n8n-url", default="http://localhost:5678")
    args = parser.parse_args()

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}_{args.target}_{'dryrun' if args.dry_run else args.model}"
    run_dir = EVALS / ("dry_run" if args.dry_run else "results") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    settings = load_settings()

    if args.target == "n8n":
        target = N8nTarget(args.n8n_url, run_tag=run_id)
        model = "n8n Config node (mock server)" if args.dry_run else f"n8n Config node ({args.model})"
    else:
        trace = run_dir / "traces.jsonl"
        if args.dry_run:
            client = FakeClient(DRY_RUN_FAULTS["fail"], DRY_RUN_FAULTS["invalid"], trace_path=trace)
            model = "fake-baseline (dry run)"
        else:
            force_role = None if args.model == "mixed" else args.model
            client = OpenRouterClient(settings, trace_path=trace, force_role=force_role)
            model = (
                f"main={settings.model_main} cheap={settings.model_cheap} (per task)"
                if force_role is None
                else f"{settings.model_for(force_role)} (every call)"
            )
        target = PythonTarget(client, run_dir, run_tag=run_id)

    workflows = list(DATASETS) if args.workflow == "all" else [args.workflow]
    summary = {
        "run_id": run_id,
        "date": stamp[:8],
        "target": args.target,
        "model": model,
        "dry_run": args.dry_run,
        "workflows": {},
    }
    for workflow in workflows:
        rows, details = run_workflow(target, workflow, args.limit)
        write_outputs(run_dir, workflow, rows, details)
        summary["workflows"][workflow] = details["summary"]
        print(workflow, json.dumps(details["summary"]["metrics"]))
    if hasattr(target, "client") and hasattr(target.client, "total_cost_usd"):
        summary["cost_usd"] = round(target.client.total_cost_usd, 4)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", run_dir.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
