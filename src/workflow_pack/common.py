"""Small helpers shared by the four workflows: idempotency, CSV sinks, error log, JSON checks."""

import csv
import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

from workflow_pack.config import PROMPTS_DIR, SCHEMAS_DIR

ERROR_COLUMNS = ["timestamp", "workflow", "item_id", "step", "error_type", "message"]
REVIEW_COLUMNS = ["timestamp", "workflow", "item_id", "reason", "details"]
SENT_COLUMNS = ["timestamp", "workflow", "item_id", "to", "subject", "status", "detail"]  # mock email outbox


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------- idempotency ----------


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def idempotency_key(run_tag: str, *parts: str) -> str:
    """Same input -> same key. `run_tag` lets a test run use its own key space."""
    return sha256_text("|".join([run_tag or "", *parts]))


class SeenStore:
    """Remembers which keys were already processed (SQLite primary key = atomic check-and-set)."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, workflow TEXT, first_seen TEXT)")

    def claim(self, key: str, workflow: str) -> bool:
        """Return True the first time a key is seen, False for every repeat."""
        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO seen (key, workflow, first_seen) VALUES (?, ?, ?)", (key, workflow, now_iso())
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def is_seen(self, key: str) -> bool:
        return self.conn.execute("SELECT 1 FROM seen WHERE key = ?", (key,)).fetchone() is not None

    def release(self, key: str) -> None:
        """Forget a key after a failure, so the same input can be retried later."""
        self.conn.execute("DELETE FROM seen WHERE key = ?", (key,))
        self.conn.commit()


# ---------- CSV "sheets", queues and the error log ----------


def append_row(path: Path, row: dict, columns: list[str]) -> None:
    """Append one row to a CSV file, writing the header if the file is new."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        if is_new:
            writer.writeheader()
        writer.writerow({col: _cell(row.get(col)) for col in columns})


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def log_error(errors_csv: Path, workflow: str, item_id: str, step: str, error: Exception | str) -> None:
    error_type = type(error).__name__ if isinstance(error, Exception) else "Error"
    row = {
        "timestamp": now_iso(),
        "workflow": workflow,
        "item_id": item_id,
        "step": step,
        "error_type": error_type,
        "message": str(error)[:500],
    }
    append_row(errors_csv, row, ERROR_COLUMNS)


def send_to_review(review_csv: Path, workflow: str, item_id: str, reason: str, details: dict | None = None) -> None:
    row = {"timestamp": now_iso(), "workflow": workflow, "item_id": item_id, "reason": reason, "details": details}
    append_row(review_csv, row, REVIEW_COLUMNS)


# ---------- AI output checks ----------


def parse_json_object(text: str) -> dict | None:
    """Models sometimes wrap JSON in ``` fences or add a sentence. Take the outermost {...}."""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


@cache
def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def schema_errors(value: dict | None, schema_name: str) -> list[str]:
    """Empty list = valid. Anything invalid is sent to human review, never used blindly."""
    if value is None:
        return ["output is not a JSON object"]
    validator = Draft202012Validator(load_schema(schema_name))
    return [f"{'/'.join(map(str, e.path)) or '$'}: {e.message}" for e in validator.iter_errors(value)]


@cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def normalise_text(value: str | None) -> str:
    """Lower-case, trim and collapse spaces, for comparing names and companies."""
    return re.sub(r"\s+", " ", (value or "").strip().lower())
