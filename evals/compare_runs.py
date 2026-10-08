"""Compare two runs item by item (for example the Python reference vs the n8n workflows).

    python -m evals.compare_runs evals/dry_run/<python_run> evals/dry_run/<n8n_run>

With the same (fake) model answers, both implementations should make identical decisions.
"""

import json
import sys
from pathlib import Path

KEYS = {
    "enquiry": ["status", "category", "team", "name", "company", "urgency", "language"],
    "triage": ["status", "priority", "team", "sentiment", "escalate"],
    "report": ["status", "reason", "numbers"],
    "invoice": ["status", "reasons", "fields"],
}


def load(run_dir: Path, workflow: str) -> dict:
    path = run_dir / f"{workflow}_results.jsonl"
    return {r["id"]: r["result"] for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def comparable(result: dict, key: str):
    value = result.get(key)
    if key == "fields" and value:
        return {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in value.items()}
    if key == "status" and value == "error":
        return "error"
    return value


def compare(a_dir: Path, b_dir: Path) -> dict:
    report = {}
    for workflow, keys in KEYS.items():
        a, b = load(a_dir, workflow), load(b_dir, workflow)
        mismatches = []
        for item_id in a:
            fields = ["status"] if a[item_id].get("status") == "error" else keys
            diff = [k for k in fields if comparable(a[item_id], k) != comparable(b.get(item_id, {}), k)]
            if diff:
                mismatches.append({"id": item_id, "fields": diff})
        report[workflow] = {"identical": len(a) - len(mismatches), "total": len(a), "mismatches": mismatches}
    return report


if __name__ == "__main__":
    result = compare(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(result, indent=2, ensure_ascii=False))
