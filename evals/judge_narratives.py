"""LLM-judge check of the weekly-report narratives of a live run (an LLM's opinion, not a human review).

    python -m evals.judge_narratives evals/results/<run_id>

Code guarantees that every number in a sent report is a computed value (see check_narratives.py).
It does not check the words around the numbers ("Billing had the most tickets", "each received 13").
This script asks MODEL_JUDGE (a different model family from the one that wrote the narratives)
whether any statement in each sent headline + narrative is false or misleading given the numbers.

Reads <run>/report_narrative_check.jsonl (run check_narratives first) and writes
<run>/report_narrative_judge.jsonl, <run>/report_narrative_judge.json and <run>/judge_traces.jsonl.
"""

import json
import sys
from pathlib import Path

from workflow_pack.common import parse_json_object
from workflow_pack.config import load_settings
from workflow_pack.llm import OpenRouterClient

JUDGE_PROMPT = """You check a short weekly operations report against the numbers it was written from.
The numbers JSON is correct. The headline and narrative were written by another AI model, and code filled in every number.
List each statement in the headline or narrative that is false or misleading given the numbers, for example:
a wrong direction of change, a double negative such as "fell by -22.4%", a wrong comparison ("the most", "the largest",
"each received", "evenly spread"), or a number attached to the wrong metric. Ignore style and tone.
Return ONLY a JSON object: {"consistent": true or false, "problems": ["one short sentence per problem"]}."""


def judge_run(run_dir: Path) -> dict:
    settings = load_settings()
    client = OpenRouterClient(settings, trace_path=run_dir / "judge_traces.jsonl", force_role="judge")
    results = {json.loads(line)["id"]: json.loads(line)["result"] for line in (run_dir / "report_results.jsonl").open()}
    rows = []
    for line in (run_dir / "report_narrative_check.jsonl").read_text(encoding="utf-8").splitlines():
        check = json.loads(line)
        if check["status"] != "sent":
            continue
        week = check["week_start"]
        numbers = results[f"week-{week}"]["numbers"]
        user = json.dumps(
            {"numbers": numbers, "headline": check["final_headline"], "narrative": check["final_narrative"]}, ensure_ascii=False
        )
        reply = client.chat("judge_narrative", "judge", JUDGE_PROMPT, user, week)
        verdict = parse_json_object(reply.text) or {}
        rows.append({"week_start": week, "consistent": verdict.get("consistent"), "problems": verdict.get("problems", [])})
    totals = {
        "run": run_dir.name,
        "judge_model": settings.model_judge,
        "judged": len(rows),
        "judged_consistent": sum(1 for r in rows if r["consistent"] is True),
        "judged_inconsistent": sum(1 for r in rows if r["consistent"] is False),
        "unparsed": sum(1 for r in rows if r["consistent"] is None),
        "judge_cost_usd": round(client.total_cost_usd, 5),
        "note": "LLM-judge opinion, not a human review; one judge call per sent report, temperature 0",
    }
    with (run_dir / "report_narrative_judge.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (run_dir / "report_narrative_judge.json").write_text(json.dumps(totals, indent=2, ensure_ascii=False), encoding="utf-8")
    return totals


if __name__ == "__main__":
    print(json.dumps(judge_run(Path(sys.argv[1])), indent=2, ensure_ascii=False))
