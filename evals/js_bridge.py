"""Run a Code node's JavaScript (from the exported n8n workflow JSON) with Node.js, outside n8n."""

import json
import shutil
import subprocess

from workflow_pack.config import REPO_ROOT, WORKFLOWS_DIR

HARNESS = REPO_ROOT / "scripts" / "run_code_node.js"


def node_available() -> bool:
    return shutil.which("node") is not None


def run_code_node(workflow_file: str, node_name: str, input_items: list[dict], nodes: dict | None = None,
                  static_data: dict | None = None) -> dict:  # fmt: skip
    """Returns {"output": [...], "staticData": {...}} or {"error": "..."}."""
    context = {"input": input_items, "nodes": nodes or {}, "staticData": static_data or {}}
    completed = subprocess.run(
        ["node", str(HARNESS), str(WORKFLOWS_DIR / workflow_file), node_name],
        input=json.dumps(context, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=60,
    )
    return json.loads(completed.stdout)
