"""The post-run narrative checker (evals/check_narratives.py). No model calls."""

from evals.check_narratives import direction_check, number_check

NUMBERS = {
    "week_start": "2025-11-03",
    "tickets_total": 30,
    "tickets_prev_week": 66,
    "tickets_change_pct": -54.5,
    "tickets_by_priority": {"P1": 2, "P2": 5},
    "negative_sentiment_pct": 31.0,
}


def test_number_check_accepts_only_computed_values():
    ok = number_check("We handled 30 tickets (66 last week); 2 P1 tickets; 31.0% negative.", NUMBERS)
    assert ok == {"numbers_in_text": 4, "numbers_not_in_computed": []}
    assert number_check("We handled 31 tickets.", NUMBERS)["numbers_not_in_computed"] == ["31"]


def test_direction_check_flags_wrong_direction_and_double_negative():
    assert direction_check("Tickets were down from 66 last week (-54.5%).", -54.5) == []
    assert direction_check("Ticket volume decreased -54.5% from 66 last week.", -54.5)[0].startswith("double negative")
    assert direction_check("Tickets rose -54.5% this week.", -54.5)[0].startswith("says up")
    assert direction_check("Tickets fell 12.0% this week.", 12.0)[0].startswith("says down")
    assert direction_check("No comparison this week.", None) == []
