"""Make import-ready copies of the workflows and create the empty CSV "sheets".

    python scripts/prepare_workflows.py                       # models from Portfolio Projects/.env
    python scripts/prepare_workflows.py --base-dir /home/node/ai-workflow-pack-n8n   # for Docker

Writes build/n8n/*.json (git-ignored) with the Config nodes filled in:
model IDs (MODEL_CHEAP / MODEL_MAIN), the OpenRouter base URL and the folder n8n reads and writes.
The API key is NEVER written anywhere: you add it once in n8n as a credential named
"OpenRouter (OpenAI-compatible)" (type OpenAI, base URL https://openrouter.ai/api/v1).
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from workflow_pack.common import ERROR_COLUMNS, REVIEW_COLUMNS, SENT_COLUMNS  # noqa: E402
from workflow_pack.config import load_settings  # noqa: E402
from workflow_pack.enquiry import SHEET_COLUMNS  # noqa: E402
from workflow_pack.invoice import REGISTER_COLUMNS  # noqa: E402
from workflow_pack.triage import CHANNEL_COLUMNS, ESCALATION_COLUMNS  # noqa: E402

CSV_HEADERS = {
    "logs/errors.csv": ERROR_COLUMNS,
    "outputs/human_review_queue.csv": REVIEW_COLUMNS,
    "outputs/sent_emails.csv": SENT_COLUMNS,
    "outputs/enquiry_sheet.csv": SHEET_COLUMNS,
    "outputs/channel_posts.csv": CHANNEL_COLUMNS,
    "outputs/escalations.csv": ESCALATION_COLUMNS,
    "outputs/invoice_register.csv": REGISTER_COLUMNS,
}


def fill_config(workflow: dict, values: dict) -> dict:
    for node in workflow["nodes"]:
        if node["name"] == "Config":
            for assignment in node["parameters"]["assignments"]["assignments"]:
                if assignment["name"] in values and values[assignment["name"]]:
                    assignment["value"] = values[assignment["name"]]
    return workflow


def create_csv_headers(base_dir: Path) -> None:
    """n8n only appends lines, so each CSV needs its header row before the first run."""
    (base_dir / "outputs" / "reports").mkdir(parents=True, exist_ok=True)
    for relative, columns in CSV_HEADERS.items():
        path = base_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.stat().st_size == 0:
            path.write_text(",".join(columns) + "\n", encoding="utf-8")


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-dir", default=str(REPO), help="this repo's path as n8n sees it")
    parser.add_argument("--llm-base-url", default=settings.base_url)
    parser.add_argument("--model-cheap", default=settings.model_cheap)
    parser.add_argument("--model-main", default=settings.model_main)
    parser.add_argument("--out", default=str(REPO / "build" / "n8n"))
    args = parser.parse_args()

    values = {
        "base_dir": args.base_dir,
        "llm_base_url": args.llm_base_url,
        "model_cheap": args.model_cheap,
        "model_main": args.model_main,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    workflows = []
    for path in sorted((REPO / "workflows").glob("*.json")):
        workflow = fill_config(json.loads(path.read_text(encoding="utf-8")), values)
        (out / path.name).write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8")
        workflows.append(workflow)
    (out / "all_workflows.json").write_text(json.dumps(workflows, ensure_ascii=False), encoding="utf-8")
    create_csv_headers(REPO)
    missing = [k for k in ("model_cheap", "model_main") if not values[k]]
    print(f"wrote {len(workflows)} workflows to {out}")
    if missing:
        print(f"note: {missing} not set in .env - the Config nodes keep the REPLACE_WITH_... placeholders")
    print("next: n8n import:workflow --input=build/n8n/all_workflows.json  (or import each file in the n8n editor)")


if __name__ == "__main__":
    main()
