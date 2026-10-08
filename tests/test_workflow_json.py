"""Checks on the exported n8n workflow JSON files themselves (no n8n needed)."""

import json
import re
import sys

import pytest

from workflow_pack.common import load_prompt
from workflow_pack.config import REPO_ROOT, WORKFLOWS_DIR

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import build_workflows  # noqa: E402

FILES = sorted(WORKFLOWS_DIR.glob("*.json"))
MAIN_FILES = [f for f in FILES if not f.name.startswith("00_")]
ALLOWED_TYPES = {
    f"n8n-nodes-base.{t}"
    for t in ["webhook", "scheduleTrigger", "errorTrigger", "set", "code", "crypto", "if", "httpRequest", "convertToFile",
              "readWriteFile", "extractFromFile", "respondToWebhook", "wait", "stickyNote"]
}  # fmt: skip


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def outputs_of(workflow, name, index):
    outputs = workflow["connections"].get(name, {}).get("main", [])
    return [c["node"] for c in outputs[index]] if len(outputs) > index else []


def test_there_are_four_workflows_plus_error_logger():
    assert [f.name for f in FILES] == [
        "00_error_logger.json", "01_enquiry_intake.json", "02_ticket_triage.json",
        "03_weekly_report.json", "04_invoice_extraction.json",
    ]  # fmt: skip


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_structure_is_valid(path):
    wf = load(path)
    names = [n["name"] for n in wf["nodes"]]
    assert len(names) == len(set(names)), "node names must be unique"
    for node in wf["nodes"]:
        assert node["type"] in ALLOWED_TYPES, node["type"]
    for source, outputs in wf["connections"].items():
        assert source in names
        for branch in outputs["main"]:
            for target in branch:
                assert target["node"] in names, f"{source} -> {target['node']}"
    targets = {t["node"] for o in wf["connections"].values() for b in o["main"] for t in b}
    for node in wf["nodes"]:  # every working node is reachable from something
        if not node["type"].endswith(("webhook", "Trigger", "trigger", "stickyNote")):
            assert node["name"] in targets, f"{node['name']} is not connected"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_no_secrets_in_workflow(path):
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"sk-[A-Za-z0-9_-]{16,}", text), "looks like an API key"
    assert "apiKey" not in text and "Authorization" not in text
    for node in load(path)["nodes"]:
        for credential in node.get("credentials", {}).values():
            assert set(credential) == {"id", "name"}, "credentials are referenced by name only"


@pytest.mark.parametrize("path", MAIN_FILES, ids=lambda p: p.stem)
def test_ai_calls_retry_and_have_an_error_branch(path):
    wf = load(path)
    ai_nodes = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"]
    assert ai_nodes
    for node in ai_nodes:
        assert node["retryOnFail"] is True and node["maxTries"] >= 3 and node["waitBetweenTries"] >= 1000
        assert node["onError"] == "continueErrorOutput"
        assert outputs_of(wf, node["name"], 1), f"{node['name']} error output is not connected"
        assert node["credentials"] == {"openAiApi": {"id": "openrouterCred01", "name": "OpenRouter (OpenAI-compatible)"}}
        assert node["parameters"]["authentication"] == "predefinedCredentialType"
        assert "llm_base_url" in node["parameters"]["url"]


@pytest.mark.parametrize("path", MAIN_FILES, ids=lambda p: p.stem)
def test_error_branch_writes_errors_csv_and_global_logger_is_set(path):
    wf = load(path)
    error_node = next(n for n in wf["nodes"] if n["name"] == "Error: log row")
    assert "logs/errors.csv" in error_node["parameters"]["jsCode"]
    writer = next(n for n in wf["nodes"] if n["name"] == "Error row: write")
    assert writer["parameters"]["options"]["append"] is True
    assert wf["settings"]["errorWorkflow"] == build_workflows.ERROR_WORKFLOW_ID


@pytest.mark.parametrize("path", MAIN_FILES, ids=lambda p: p.stem)
def test_every_workflow_checks_ai_json_and_duplicates(path):
    wf = load(path)
    codes = {n["name"]: n["parameters"].get("jsCode", "") for n in wf["nodes"]}
    assert "$getWorkflowStaticData" in codes["Seen before?"]
    assert any("schemaErrors" in code for code in codes.values()), "AI output must be schema-checked"
    for code in codes.values():
        assert not re.search(r"__[A-Z]+(:[\w.]+)?__", code), "unfilled placeholder"


def test_enquiry_reply_is_never_sent_before_approval():
    wf = load(WORKFLOWS_DIR / "01_enquiry_intake.json")
    assert outputs_of(wf, "Waiting for approval?", 0) == ["Wait for approval"]
    assert outputs_of(wf, "Wait for approval", 0) == ["Record decision"]
    record = next(n for n in wf["nodes"] if n["name"] == "Record decision")
    assert "query.decision === 'approve'" in record["parameters"]["jsCode"]


def test_webhook_paths_are_unique():
    paths = [n["parameters"]["path"] for f in FILES for n in load(f)["nodes"] if n["type"].endswith("webhook")]
    assert len(paths) == len(set(paths)) == 4


def test_config_has_placeholders_not_real_models_and_matches_prompt_files():
    wf = load(WORKFLOWS_DIR / "02_ticket_triage.json")
    config = {
        a["name"]: a["value"]
        for a in next(n for n in wf["nodes"] if n["name"] == "Config")["parameters"]["assignments"]["assignments"]
    }
    assert config["llm_base_url"] == "https://openrouter.ai/api/v1"
    assert config["model_cheap"].startswith("REPLACE_WITH_")
    assert config["prompt_triage"] == load_prompt("ticket_triage")


def test_committed_json_matches_the_generator():
    """If this fails, run `python scripts/build_workflows.py` (or delete this test if you now edit in the n8n UI)."""
    for file_name, builder in build_workflows.BUILDERS.items():
        assert builder() == load(WORKFLOWS_DIR / file_name), file_name
