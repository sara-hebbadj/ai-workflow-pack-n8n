"""Smoke test for the demo app in app/app.py (skipped without the [app] extra, as in CI).

Runs every tab's handler in demo mode (FakeClient: no network, no key) in a temporary session folder.
"""

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("gradio")
APP_PATH = Path(__file__).resolve().parents[1] / "app" / "app.py"


@pytest.fixture(scope="module")
def app():
    spec = importlib.util.spec_from_file_location("workflow_demo_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def demo_mode(app, monkeypatch):
    monkeypatch.setattr(app, "LIVE", False)
    return app


def test_app_builds(app):
    assert app.build() is not None


def test_enquiry_draft_waits_for_approval_then_mock_send(demo_mode):
    app = demo_mode
    session = app.new_session()
    first = next(c for c in app.enquiry_choices() if c.startswith("enq-001"))
    status, labels, draft_subject, _body, session, _review = app.run_enquiry(*app.load_enquiry(first), session)
    assert "waiting for approval" in status and draft_subject
    note, outbox, session = app.decide_enquiry("enq-001", draft_subject, True, session)
    assert "Approved" in note and outbox.iloc[-1]["status"] == "sent (mock)"
    again, *_ = app.run_enquiry(*app.load_enquiry(first), session)
    assert "Duplicate" in again


def test_ticket_safety_net_escalates(demo_mode):
    app = demo_mode
    status, result, _session, escalations = app.run_ticket(
        "t-demo", "Reaction", "My face is swelling after the serum, I went to hospital.", app.new_session()
    )
    assert json.loads(result)["escalate"] is True and "escalated" in status and len(escalations) == 1


def test_weekly_report_numbers_come_from_code(demo_mode):
    status, report, _session = demo_mode.run_report(demo_mode.WEEKS[0], demo_mode.new_session())
    assert "Weekly operations report" in report and ("Sent" in status or "Held" in status)


def test_invoice_with_planted_problem_is_not_booked(demo_mode):
    app = demo_mode
    bad = next(c for c in app.invoice_choices() if not c.endswith("expected: accepted"))
    status, _fields, _session, register, _review = app.run_invoice(bad, None, app.new_session())
    assert "Booked" not in status and register.iloc[-1]["status"] != "accepted"


def test_results_tables_read_the_saved_runs(app):
    assert len(app.metrics_table(app.MAIN_RUN)) > 10 and "openai" in app.run_caption(app.MAIN_RUN)
