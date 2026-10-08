"""Small builders for n8n workflow JSON (used by build_workflows.py).

Each function returns one node as a dict, in the format n8n exports. Keeping the builders
here means every AI call gets the same retry settings and credential reference.
"""

import uuid

CREDENTIAL_REF = {"openAiApi": {"id": "openrouterCred01", "name": "OpenRouter (OpenAI-compatible)"}}  # name only, never a key
NAMESPACE = uuid.UUID("6f1c2a5e-1d0b-4c39-9a51-0e8f3b7d2c10")


def stable_id(*parts: str) -> str:
    """Deterministic ids so re-running the generator gives an identical file."""
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


class Flow:
    def __init__(self, name: str, workflow_id: str):
        self.name, self.workflow_id = name, workflow_id
        self.nodes: list[dict] = []
        self.connections: dict = {}

    def add(self, node: dict, x: int, y: int) -> str:
        node.setdefault("id", stable_id(self.name, node["name"]))
        node["position"] = [x, y]
        self.nodes.append(node)
        return node["name"]

    def connect(self, source: str, target: str, output: int = 0) -> None:
        outputs = self.connections.setdefault(source, {"main": []})["main"]
        while len(outputs) <= output:
            outputs.append([])
        outputs[output].append({"node": target, "type": "main", "index": 0})

    def chain(self, *names: str) -> None:
        for a, b in zip(names, names[1:]):
            self.connect(a, b)

    def to_json(self) -> dict:
        return {
            "id": self.workflow_id,
            "name": self.name,
            "nodes": self.nodes,
            "connections": self.connections,
            "settings": {
                "executionOrder": "v1",
                "timezone": "Asia/Dubai",
                "saveDataErrorExecution": "all",
                "saveDataSuccessExecution": "all",
                "saveManualExecutions": True,
            },  # fmt: skip
            "pinData": {},
            "active": False,
            "tags": [],
            "meta": {"templateCredsSetupCompleted": False},
        }


def node(name: str, node_type: str, version: float, parameters: dict, **extra) -> dict:
    return {"name": name, "type": f"n8n-nodes-base.{node_type}", "typeVersion": version, "parameters": parameters, **extra}


def webhook(name: str, path: str) -> dict:
    params = {"httpMethod": "POST", "path": path, "responseMode": "responseNode", "options": {}}
    return node(name, "webhook", 2.1, params, webhookId=stable_id("webhook", path))


def schedule(name: str, cron: str) -> dict:
    return node(name, "scheduleTrigger", 1.2, {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}})


def config(name: str, fields: dict) -> dict:
    """A Set node holding settings, prompts and thresholds. Other fields pass through unchanged."""
    assignments = []
    for key, value in fields.items():
        kind = "number" if isinstance(value, (int, float)) and not isinstance(value, bool) else "string"
        assignments.append({"id": stable_id(name, key), "name": key, "value": value, "type": kind})
    return node(name, "set", 3.4, {"assignments": {"assignments": assignments}, "includeOtherFields": True, "options": {}})


def code(name: str, js: str, catch_errors: bool = True) -> dict:
    extra = {"onError": "continueErrorOutput"} if catch_errors else {}
    return node(name, "code", 2, {"jsCode": js}, **extra)


def hash_text(name: str, value_expr: str, out_field: str) -> dict:
    return node(name, "crypto", 2, {"action": "hash", "type": "SHA256", "value": value_expr, "dataPropertyName": out_field})


def hash_file(name: str, binary_field: str, out_field: str) -> dict:
    params = {
        "action": "hash",
        "binaryData": True,
        "binaryPropertyName": binary_field,
        "type": "SHA256",
        "dataPropertyName": out_field,
    }
    return node(name, "crypto", 2, params)


def if_true(name: str, bool_expr: str) -> dict:
    """IF node: output 0 when the expression is true, output 1 when false."""
    condition = {
        "id": stable_id(name, "condition"),
        "leftValue": bool_expr,
        "rightValue": "",
        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
    }
    params = {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                       "conditions": [condition], "combinator": "and"},
        "looseTypeValidation": True,
        "options": {},
    }  # fmt: skip
    return node(name, "if", 2.2, params)


def llm_call(name: str) -> dict:
    """POST to the OpenAI-compatible endpoint. The body is built by the previous Code node.

    3 tries, 2 s apart; after that the item leaves through the error output (index 1).
    """
    params = {
        "method": "POST",
        "url": "={{ $('Config').first().json.llm_base_url }}/chat/completions",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "openAiApi",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify($json.llm_request) }}",
        "options": {"timeout": 60000},
    }
    return node(name, "httpRequest", 4.2, params, credentials=CREDENTIAL_REF, retryOnFail=True, maxTries=3,
                waitBetweenTries=2000, onError="continueErrorOutput")  # fmt: skip


def text_to_file(name: str, field: str = "line") -> dict:
    return node(name, "convertToFile", 1.1, {"operation": "toText", "sourceProperty": field, "options": {}})


def append_to_file(name: str, path_expr: str) -> dict:
    return node(name, "readWriteFile", 1.1, {"operation": "write", "fileName": path_expr, "options": {"append": True}})


def write_file(name: str, path_expr: str) -> dict:
    return node(name, "readWriteFile", 1.1, {"operation": "write", "fileName": path_expr, "options": {}})


def read_file(name: str, path_expr: str) -> dict:
    return node(name, "readWriteFile", 1.1, {"fileSelector": path_expr, "options": {}}, executeOnce=True)


def extract(name: str, operation: str, binary_field: str = "data", **params) -> dict:
    return node(
        name, "extractFromFile", 1.1, {"operation": operation, "binaryPropertyName": binary_field, **params, "options": {}}
    )


def respond(name: str, body_expr: str, status_expr: str | int = 200) -> dict:
    params = {"respondWith": "json", "responseBody": body_expr, "options": {"responseCode": status_expr}}
    return node(name, "respondToWebhook", 1.5, params)


def wait_for_webhook(name: str) -> dict:
    return node(name, "wait", 1.1, {"resume": "webhook", "httpMethod": "GET", "options": {}}, webhookId=stable_id("wait", name))


def error_trigger(name: str) -> dict:
    return node(name, "errorTrigger", 1, {})


def sticky(name: str, content: str, width: int = 360, height: int = 220, color: int = 7) -> dict:
    return node(name, "stickyNote", 1, {"content": content, "width": width, "height": height, "color": color})
