"""Workflow 4: invoice or PDF to data.

file -> text extraction -> AI extracts the fields -> code checks totals and VAT
-> clean invoices go to the register; anything doubtful goes to a human-check queue.
"""

import json
from pathlib import Path

from pypdf import PdfReader

from workflow_pack.common import (
    append_row,
    idempotency_key,
    load_prompt,
    log_error,
    normalise_text,
    now_iso,
    parse_json_object,
    schema_errors,
    send_to_review,
    sha256_bytes,
)
from workflow_pack.config import INVOICE_MIN_CONFIDENCE, MONEY_TOLERANCE, Paths
from workflow_pack.llm import LLMClient

WORKFLOW = "invoice_extraction"
FIELDS = ["supplier_name", "invoice_number", "invoice_date", "currency", "net_amount", "vat_rate", "vat_amount", "total_amount"]
REGISTER_COLUMNS = ["timestamp", "file_name", "status", "reasons", *FIELDS, "confidence"]
# VAT rates we expect per currency (UAE 5%, UK 20%, France 20/10/5.5%). Anything else is checked by a person.
KNOWN_VAT_RATES = {"AED": [5.0, 0.0], "GBP": [20.0, 5.0, 0.0], "EUR": [20.0, 10.0, 5.5, 0.0], "USD": [0.0]}


SUPPORTED = (".pdf", ".txt")


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8")


def validate_fields(fields: dict) -> list[str]:
    """The money checks. An empty list means the invoice adds up."""
    issues = [f"missing {name}" for name in FIELDS if fields.get(name) in (None, "")]
    net, vat, total, rate = (fields.get(k) for k in ("net_amount", "vat_amount", "total_amount", "vat_rate"))
    tolerance = MONEY_TOLERANCE + 1e-9  # tiny extra margin for floating-point noise
    if None not in (net, vat, total) and abs(net + vat - total) > tolerance:
        issues.append("total does not equal net + VAT")
    if None not in (net, vat, rate) and abs(net * rate / 100 - vat) > tolerance:
        issues.append("VAT amount does not equal net x rate")
    currency = fields.get("currency")
    if rate is not None and currency in KNOWN_VAT_RATES and float(rate) not in KNOWN_VAT_RATES[currency]:
        issues.append(f"unusual VAT rate {rate}% for {currency}")
    return issues


def business_key(fields: dict, run_tag: str = "") -> str | None:
    """Same supplier + same invoice number = same invoice, even if the file is different."""
    supplier, number = normalise_text(fields.get("supplier_name")), normalise_text(fields.get("invoice_number"))
    if not supplier or not number:
        return None
    return idempotency_key(run_tag, "invoice", supplier, number)


def decide(fields: dict | None, errors: list[str], store, run_tag: str = "") -> dict:
    """Code decides: accepted (booked), duplicate, or needs_review (human-check queue)."""
    if errors:
        return {"status": "needs_review", "reasons": ["AI output failed the JSON schema check"]}
    issues = validate_fields(fields)
    if fields["confidence"] < INVOICE_MIN_CONFIDENCE:
        issues.append("low confidence")
    key = business_key(fields, run_tag)
    if key and store.is_seen(key):
        return {"status": "duplicate", "reasons": ["invoice number already booked for this supplier"]}
    if issues:
        return {"status": "needs_review", "reasons": issues}
    store.claim(key, WORKFLOW)  # only booked invoices are remembered
    return {"status": "accepted", "reasons": []}


def process_invoice(path: Path, client: LLMClient, store, paths: Paths, run_tag: str = "") -> dict:
    file_name = path.name
    try:
        if path.suffix.lower() not in SUPPORTED:
            raise ValueError(f"unsupported file type {path.suffix}")
        file_key = idempotency_key(run_tag, "file", sha256_bytes(path.read_bytes()))
    except (OSError, ValueError) as e:
        log_error(paths.errors_csv, WORKFLOW, file_name, "check_input", e)
        return {"file_name": file_name, "status": "error", "reasons": [str(e)]}
    if not store.claim(file_key, WORKFLOW):
        return {"file_name": file_name, "status": "duplicate", "reasons": ["same file already processed"]}
    try:
        text = extract_text(path)
    except Exception as e:  # e.g. a corrupt PDF
        log_error(paths.errors_csv, WORKFLOW, file_name, "extract_text", e)
        store.release(file_key)
        return {"file_name": file_name, "status": "error", "reasons": [f"text extraction failed: {e}"]}

    if not text.strip():
        result = {"file_name": file_name, "status": "needs_review", "reasons": ["no text found (scanned image? needs OCR)"]}
        record(result, {}, paths)
        return result

    try:
        user = json.dumps({"file_name": file_name, "text": text}, ensure_ascii=False)
        reply = client.chat("invoice_extract", "cheap", load_prompt("invoice_extract"), user, file_name)
    except Exception as e:
        log_error(paths.errors_csv, WORKFLOW, file_name, "ai_extract", e)
        store.release(file_key)
        return {"file_name": file_name, "status": "error", "reasons": [f"AI call failed: {e}"]}

    fields = parse_json_object(reply.text)
    errors = schema_errors(fields, "invoice_extract")
    result = {"file_name": file_name, **decide(None if errors else fields, errors, store, run_tag)}
    result["fields"] = {} if errors else {k: fields[k] for k in [*FIELDS, "confidence"]}
    record(result, result["fields"], paths)
    return result


def record(result: dict, fields: dict, paths: Paths) -> None:
    row = {"timestamp": now_iso(), **fields, **result, "reasons": "; ".join(result["reasons"])}
    append_row(paths.outputs / "invoice_register.csv", row, REGISTER_COLUMNS)
    if result["status"] == "needs_review":
        send_to_review(paths.outputs / "human_review_queue.csv", WORKFLOW, result["file_name"], row["reasons"], fields)
