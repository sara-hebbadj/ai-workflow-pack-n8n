"""A tiny OpenAI-compatible server for testing the n8n workflows without a real model or key.

    python scripts/mock_llm_server.py --port 8765 --fail-ids enq-050,t-050 --invalid-ids enq-049

Point the workflows' Config node at http://localhost:8765/v1 (scripts/prepare_workflows.py does this
with --llm-base-url). Answers come from the rule-based baselines, so results are NOT model results.
`--fail-ids` always answer HTTP 500 (to exercise retries + the error branch); `--invalid-ids` answer
with text that is not JSON (to exercise the schema check + human review).
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from workflow_pack.fake_llm import INVALID_TEXT, fake_reply, item_id_from, task_from_prompt


def make_handler(fail_ids: set[str], invalid_ids: set[str], log_file: str):
    def log(entry: dict) -> None:
        if log_file:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 (name required by http.server)
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            messages = body.get("messages", [])
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            user = next((m["content"] for m in messages if m["role"] == "user"), "{}")
            task, item_id = task_from_prompt(system), item_id_from(json.loads(user))
            authorised = self.headers.get("Authorization", "").startswith("Bearer ")
            log({"task": task, "item_id": item_id, "model": body.get("model"), "auth_header": authorised})
            if item_id in fail_ids:
                return self._send(500, {"error": {"message": f"simulated upstream error for {item_id}"}})
            content = INVALID_TEXT if item_id in invalid_ids else fake_reply(task, user)
            self._send(200, {
                "id": "mock-1", "object": "chat.completion", "model": body.get("model", "mock"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0},
            })  # fmt: skip

        def _send(self, status: int, payload: dict):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # keep the console quiet
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--fail-ids", default="")
    parser.add_argument("--invalid-ids", default="")
    parser.add_argument("--log-file", default="")
    args = parser.parse_args()
    split = lambda s: {x for x in s.split(",") if x}  # noqa: E731
    handler = make_handler(split(args.fail_ids), split(args.invalid_ids), args.log_file)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"mock LLM listening on http://127.0.0.1:{args.port}/v1", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
