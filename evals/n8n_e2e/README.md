# n8n end-to-end run (8 October 2026), mock model, NOT model results

**What ran:**

- n8n 2.35.7 (npm), self-hosted on the build machine (Node.js 22.22.0, SQLite, `N8N_RESTRICT_FILE_ACCESS_TO` set to this repo);
- the five workflows from `workflows/`, prepared with `scripts/prepare_workflows.py --llm-base-url http://127.0.0.1:8765/v1`;
- the AI nodes using an OpenAI-type credential named `OpenRouter (OpenAI-compatible)` with a dummy key, pointed at `scripts/mock_llm_server.py`. The mock answers with the rule-based baselines.

The mock was started with injected faults:
`--fail-ids enq-050,t-050,2026-09-14,inv-050.txt` (HTTP 500 on every try) and
`--invalid-ids enq-049,t-049,2026-09-07,inv-047.txt` (answers that are not JSON).

**Commands:**

```bash
python -m evals.run --target n8n --dry-run          # -> evals/dry_run/20261008T120522Z_n8n_dryrun/
python -m evals.run --dry-run                       # Python reference, same fake answers -> evals/dry_run/20261008T120520Z_python_dryrun/
python -m evals.compare_runs evals/dry_run/20261008T120520Z_python_dryrun evals/dry_run/20261008T120522Z_n8n_dryrun
```

**Results:**

- **200/200 inputs got identical decisions** in n8n and in the Python reference (`../dry_run/parity_python_vs_n8n.json`):
  - status, category, team, fields, priority, escalation, report numbers, invoice fields and reasons all match;
  - the rendered weekly report (Markdown and HTML) is byte-identical for the week checked (2026-03-02).
- For each workflow:
  - 5/5 re-sent inputs returned `duplicate`;
  - the injected API failure was retried 3 times and then logged;
  - the injected invalid answer went to the review queue.
- Approval: opening the `approve_url` of a pending draft resumed the waiting execution and wrote `sent (mock)` to `sent_emails.csv`. The approval inbox app (`app/approval_inbox.py`) was also tested against this n8n and resumed `enq-002`.

**Files in this folder** (copied from `outputs/` and `logs/` after the runs; they include the smoke tests and all four evaluation passes run against n8n that day):

- `errors.csv` has these rows:
  - the 4 injected API failures, once per evaluation pass (4 passes, so 16 rows);
  - the edge cases: empty email body, missing ticket id, non-Monday week, `.csv` upload, corrupt PDF;
  - one row from the **global error-logger workflow**, written when a deliberately buggy test workflow ("Test uncaught error") failed in a Code node. A second row from that test came from a configuration mistake in the test workflow itself (no Respond node).
- `human_review_queue.csv`, `escalations.csv` and `sent_emails.csv` show what staff would see.

**What this does and does not show.** It shows that the n8n wiring, error branches, idempotency, approval step and code checks behave as designed. It says nothing about how accurate a real model is: that needs `python -m evals.run --target n8n --model cheap` with a real key.
