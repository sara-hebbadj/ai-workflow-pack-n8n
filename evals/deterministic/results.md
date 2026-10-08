# Deterministic checks (no language model) - 2026-10-08

Command: `python -m evals.deterministic`

## invoices

| Check | Result |
|---|---|
| text_extraction_ok (pypdf / utf-8) | 50/50 (100.0%) |
| validator_on_perfect_fields: status == expected | 50/50 (100.0%) |
| validator_on_perfect_fields: planted issues not booked | 14/14 (100.0%) |
| validator_on_perfect_fields: clean invoices booked | 36/36 (100.0%) |
| regex_baseline_field: supplier_name | 50/50 (100.0%) |
| regex_baseline_field: invoice_number | 20/50 (40.0%) |
| regex_baseline_field: invoice_date | 19/50 (38.0%) |
| regex_baseline_field: currency | 50/50 (100.0%) |
| regex_baseline_field: net_amount | 19/50 (38.0%) |
| regex_baseline_field: vat_rate | 19/50 (38.0%) |
| regex_baseline_field: vat_amount | 19/50 (38.0%) |
| regex_baseline_field: total_amount | 19/50 (38.0%) |
| regex_baseline: all 8 fields correct | 19/50 (38.0%) |
| regex_baseline: status == expected | 25/50 (50.0%) |
| n8n JS validator: same status as Python | 50/50 (100.0%) |

## weekly_report

| Check | Result |
|---|---|
| python numbers == generator truth (leaf checks) | 1200/1200 (100.0%) |
| narrative check: placeholder narratives accepted | 50/50 (100.0%) |
| narrative check: a typed wrong number caught | 50/50 (100.0%) |
| narrative check: an invented metric caught | 50/50 (100.0%) |
| n8n JS numbers == generator truth (leaf checks) | 1200/1200 (100.0%) |
| n8n JS numbers identical to Python (weeks) | 50/50 (100.0%) |

## enquiries

| Check | Result |
|---|---|
| keyword_baseline: category | 45/50 (90.0%) |
| keyword_baseline: name (non-spam) | 38/40 (95.0%) |
| keyword_baseline: company (non-spam) | 36/40 (90.0%) |
| keyword_baseline: urgency (non-spam) | 32/40 (80.0%) |
| keyword_baseline: language (non-spam) | 40/40 (100.0%) |
| injection tripwire: injections flagged | 3/3 (100.0%) |
| injection tripwire: clean emails not flagged | 47/47 (100.0%) |
| label distribution | {"sales": 12, "support": 10, "complaint": 10, "partnership": 8, "spam": 10} |

## tickets

| Check | Result |
|---|---|
| keyword_baseline: priority | 49/50 (98.0%) |
| keyword_baseline: sentiment | 50/50 (100.0%) |
| keyword_baseline: team | 46/50 (92.0%) |
| safety net alone: true P1 caught | 7/8 (87.5%) |
| safety net alone: non-P1 not flagged | 42/42 (100.0%) |
| label distribution | {"P1": 8, "P2": 12, "P3": 20, "P4": 10} |

Caveat: the keyword baselines and the test labels were written by the same author (a coding agent), so baseline scores on this set are optimistic. They are a sanity floor, not a fair benchmark.
