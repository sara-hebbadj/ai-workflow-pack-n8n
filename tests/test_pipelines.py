"""End-to-end runs of the Python reference with the fake model (no network)."""

import csv
from pathlib import Path

from workflow_pack.config import DATA_DIR
from workflow_pack.enquiry import process_enquiry, record_decision
from workflow_pack.fake_llm import FakeClient
from workflow_pack.invoice import process_invoice
from workflow_pack.report import process_week
from workflow_pack.triage import process_ticket


def rows(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []


def by_id(items, item_id):
    return next(i["input"] for i in items if i["id"] == item_id)


def test_enquiry_goes_to_approval_and_duplicate_is_blocked(enquiries, paths, store):
    email = by_id(enquiries, "enq-001")
    result = process_enquiry(email, FakeClient(), store, paths)
    assert result["status"] == "pending_approval" and result["team"] == "Sales" and result["draft_body"]
    assert process_enquiry(email, FakeClient(), store, paths)["status"] == "duplicate"
    assert len(rows(paths.outputs / "enquiry_sheet.csv")) == 1
    assert not (paths.outputs / "sent_emails.csv").exists(), "nothing is sent before approval"
    record_decision(paths, "enq-001", email["from_email"], result["draft_subject"], approved=True, approver="sara")
    assert rows(paths.outputs / "sent_emails.csv")[0]["status"] == "sent (mock)"


def test_prompt_injection_is_held_for_a_person(enquiries, paths, store):
    result = process_enquiry(by_id(enquiries, "enq-009"), FakeClient(), store, paths)
    assert result["status"] == "needs_review" and result["reason"] == "possible prompt injection"
    assert rows(paths.outputs / "human_review_queue.csv")[0]["item_id"] == "enq-009"


def test_api_failure_is_logged_and_can_be_retried(enquiries, paths, store):
    email = by_id(enquiries, "enq-002")
    failing = FakeClient(fail_ids={"enq-002"})
    assert process_enquiry(email, failing, store, paths)["status"] == "error"
    assert len(failing.calls) == 3, "three tries before giving up"
    assert rows(paths.errors_csv)[0]["step"] == "ai_classify"
    assert process_enquiry(email, FakeClient(), store, paths)["status"] == "pending_approval", "key was released"


def test_invalid_ai_output_goes_to_review(enquiries, paths, store):
    result = process_enquiry(by_id(enquiries, "enq-003"), FakeClient(invalid_ids={"enq-003"}), store, paths)
    assert result["status"] == "needs_review" and "schema" in result["reason"]


def test_bad_input_is_logged_not_sent_to_ai(paths, store):
    client = FakeClient()
    assert (
        process_enquiry({"message_id": "x", "from_email": "a@example.com", "body": " "}, client, store, paths)["status"]
        == "error"
    )
    assert client.calls == [] and rows(paths.errors_csv)[0]["step"] == "prepare_input"


def test_p1_ticket_is_escalated_even_when_the_ai_is_down(tickets, paths, store):
    result = process_ticket(by_id(tickets, "t-001"), FakeClient(fail_ids={"t-001"}), store, paths)
    assert result["status"] == "escalated" and result["priority"] == "P1"
    assert rows(paths.outputs / "escalations.csv")[0]["ticket_id"] == "t-001"
    assert rows(paths.errors_csv)[0]["item_id"] == "t-001"


def test_routine_ticket_is_posted_to_channel(tickets, paths, store):
    result = process_ticket(by_id(tickets, "t-025"), FakeClient(), store, paths)
    assert result["status"] == "routed" and not result["escalate"]
    assert rows(paths.outputs / "channel_posts.csv")[0]["ticket_id"] == "t-025"
    assert process_ticket(by_id(tickets, "t-025"), FakeClient(), store, paths)["status"] == "duplicate"


def test_weekly_report_is_rendered_and_mock_sent(paths, store):
    result = process_week("2026-03-02", FakeClient(), store, paths)
    assert result["status"] == "sent" and result["numbers"]["tickets_total"] == 38
    report = (paths.outputs / "reports" / "weekly_2026-03-02.md").read_text(encoding="utf-8")
    assert "| Tickets this week | 38 |" in report and "{" not in report
    assert rows(paths.outputs / "sent_emails.csv")[0]["status"] == "sent (mock)"
    assert process_week("2026-03-02", FakeClient(), store, paths)["status"] == "duplicate"


def test_weekly_report_holds_a_bad_narrative(paths, store):
    result = process_week("2026-03-09", FakeClient(invalid_ids={"2026-03-09"}), store, paths)
    assert result["status"] == "needs_review"
    assert "held for review" in rows(paths.outputs / "sent_emails.csv")[0]["status"]


def test_invoice_with_wrong_total_goes_to_review(paths, store):
    result = process_invoice(DATA_DIR / "invoices" / "files" / "inv-033.pdf", FakeClient(), store, paths)
    assert result["status"] == "needs_review" and "total does not equal net + VAT" in result["reasons"]


def test_invoice_duplicates_by_file_and_by_supplier_number(paths, store, tmp_path):
    original = DATA_DIR / "invoices" / "files" / "inv-040.txt"
    assert process_invoice(original, FakeClient(), store, paths)["status"] == "accepted"
    assert process_invoice(original, FakeClient(), store, paths)["status"] == "duplicate"
    resent = tmp_path / "resent.txt"
    resent.write_text(original.read_text(encoding="utf-8") + "\nresent\n", encoding="utf-8")
    result = process_invoice(resent, FakeClient(), store, paths)
    assert result["status"] == "duplicate" and result["reasons"] == ["invoice number already booked for this supplier"]


def test_unsupported_file_is_an_error(paths, store, tmp_path):
    bad = tmp_path / "x.csv"
    bad.write_text("a,b\n")
    assert process_invoice(bad, FakeClient(), store, paths)["status"] == "error"
    assert rows(paths.errors_csv)[0]["step"] == "check_input"
