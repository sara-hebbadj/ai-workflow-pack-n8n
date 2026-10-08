"""Check the weekly-report narratives of a live run. No model calls.

    python -m evals.check_narratives evals/results/<run_id>

For each week of the run it reads the AI's raw answer (traces.jsonl), the code's decision
(report_results.jsonl) and the final report (outputs/reports/weekly_<week>.md), then checks:

1. Number consistency: every number in the final headline and narrative equals one of the week's
   computed values. This should hold by construction (code fills the placeholders); here it is verified
   on the text a manager would read.
2. Direction of the week-on-week change (keyword check): a "rose / up / increase" word next to a
   negative change, or a "fell / down / decrease" word next to a positive one, is a wrong direction.
   A "fell" word directly followed by the negative value ("decreased -54.5%") is flagged as a double negative.
   This is a simple keyword heuristic, not a full reading of the text.

Writes <run>/report_narrative_check.jsonl (one row per week, with the raw and final text) and
<run>/report_narrative_check.json (totals).
"""

import json
import re
import sys
from pathlib import Path

from workflow_pack.report import format_value

DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
PRIORITY_LABEL = re.compile(r"\bP[1-4]\b")
UP = r"\b(?:rose|rise|rising|up|increase[sd]?|increasing|grew|growth|higher|jump(?:ed)?|climb(?:ed)?)\b"
DOWN = r"\b(?:fell|fall|falling|down|decrease[sd]?|decreasing|drop(?:ped)?|declined?|lower|shr[ai]nk|eased)\b"
UP_WORDS, DOWN_WORDS = re.compile(UP, re.I), re.compile(DOWN, re.I)


def leaf_values(numbers: dict) -> set[str]:
    values = set()
    for value in numbers.values():
        for leaf in value.values() if isinstance(value, dict) else [value]:
            values.add(format_value(leaf))
    return values


def final_text(report_md: str) -> tuple[str, str]:
    """(headline, narrative) as written in the rendered Markdown report."""
    lines = report_md.splitlines()
    headline = lines[2].strip("* ") if len(lines) > 2 else ""
    narrative = report_md.split("## Narrative (AI-written, numbers checked by code)", 1)[-1].strip()
    return headline, narrative


def number_check(text: str, numbers: dict) -> dict:
    allowed = leaf_values(numbers)
    dates = DATE.findall(text)
    found = NUMBER.findall(PRIORITY_LABEL.sub(" ", DATE.sub(" ", text)))
    wrong = [n for n in found if n not in allowed] + [d for d in dates if d not in allowed]
    return {"numbers_in_text": len(found) + len(dates), "numbers_not_in_computed": wrong}


def direction_check(text: str, change) -> list[str]:
    """Keyword check around each place the change percentage appears."""
    if change is None:
        return []
    value = format_value(change)
    problems = []
    for sentence in re.split(r"(?<=[.;])\s+|\n", text):
        if value not in NUMBER.findall(sentence):
            continue
        up, down = bool(UP_WORDS.search(sentence)), bool(DOWN_WORDS.search(sentence))
        if change < 0 and up and not down:
            problems.append(f"says up, change is {value}%: {sentence.strip()}")
        elif change > 0 and down and not up:
            problems.append(f"says down, change is {value}%: {sentence.strip()}")
        elif change < 0 and re.search(rf"{DOWN}\W+(?:by\W+)?{re.escape(value)}", sentence, re.I):
            problems.append(f"double negative: {sentence.strip()}")
    return problems


def check_run(run_dir: Path) -> dict:
    raw_text = {}
    for line in (run_dir / "traces.jsonl").read_text(encoding="utf-8").splitlines():
        trace = json.loads(line)
        if trace["task"] == "report_narrative" and trace.get("outcome") == "ok":
            raw_text[trace["item_id"]] = trace.get("text", "")
    rows = []
    for line in (run_dir / "report_results.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        result = record["result"]
        week, numbers = result["week_start"], result.get("numbers")
        row = {"week_start": week, "status": result["status"], "reason": result.get("reason", ""), "ai_raw": raw_text.get(week)}
        report = run_dir / "outputs" / "reports" / f"weekly_{week}.md"
        if result["status"] == "sent" and numbers and report.exists():
            headline, narrative = final_text(report.read_text(encoding="utf-8"))
            text = f"{headline}\n{narrative}"
            row.update({"final_headline": headline, "final_narrative": narrative, **number_check(text, numbers)})
            row["direction_problems"] = direction_check(text, numbers["tickets_change_pct"])
        rows.append(row)
    sent = [r for r in rows if r["status"] == "sent"]
    totals = {
        "run": run_dir.name,
        "weeks": len(rows),
        "sent": len(sent),
        "held_for_review": sum(1 for r in rows if r["status"] == "needs_review"),
        "errors": sum(1 for r in rows if r["status"] == "error"),
        "numbers_in_sent_text": sum(r["numbers_in_text"] for r in sent),
        "numbers_not_in_computed": sum(len(r["numbers_not_in_computed"]) for r in sent),
        "sent_with_number_problem": sum(1 for r in sent if r["numbers_not_in_computed"]),
        "sent_with_direction_problem": sum(1 for r in sent if r["direction_problems"]),
        "held_reasons": [r["reason"] for r in rows if r["status"] == "needs_review"],
        "method": "regex over the final Markdown; direction = keyword heuristic, not a human or LLM reading",
    }
    with (run_dir / "report_narrative_check.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (run_dir / "report_narrative_check.json").write_text(json.dumps(totals, indent=2, ensure_ascii=False), encoding="utf-8")
    return totals


if __name__ == "__main__":
    print(json.dumps(check_run(Path(sys.argv[1])), indent=2, ensure_ascii=False))
