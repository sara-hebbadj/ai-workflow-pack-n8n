# Build notes (8 October 2026)

Observations made by the coding agent while building and testing the first version. These are a log of what happened, not results of the current code; re-run the current checks with `python -m evals.deterministic`.

1. **Invoice set too easy (observed and fixed).**
   - The first generator printed every invoice in one fixed layout per language (English, French, Arabic).
   - `python -m evals.deterministic` then showed the regex baseline reading all 8 fields correctly on 50/50 invoices.
   - The generator now rotates 2–3 label layouts per language. Rerun on the same day: 19/50 fully correct, 25/50 routed correctly.
   - The baseline rules were not edited after the change.
2. **Narrative number check too weak (observed and fixed).**
   - The first check accepted a narrative if every number it contained appeared somewhere in the computed numbers.
   - In a test that added 1 to the SLA-breach count in 50 template narratives, it caught only 17/50: the wrong value often equalled another count, such as a team's ticket count.
   - The AI now writes placeholders (`{sla_breaches}`) that code fills in, and any digit it types is rejected. The same kind of test now catches 50/50, plus 50/50 invented placeholders.
3. **n8n behaviours found by running n8n 2.35.7 locally.**
   - "Convert to File" outputs items with empty JSON, so the write node reads the target path from the previous node through paired items.
   - The Crypto node (hash of a binary file) drops the binary, so the file is re-attached from "Check file".
   - n8n 2.x needs `N8N_RESTRICT_FILE_ACCESS_TO` to allow file reads and writes outside `~/.n8n-files`.
   - n8n 2.37+ requires Node 24. The build machine had Node 22.22, so 2.35.7 was used.
   - `$execution.resumeUrl` includes a `signature` query parameter, so the approval link adds `&decision=approve`.
4. **Retry vs duplicate.** If the idempotency key were kept after a failed AI call, the retry would be rejected as a duplicate. The error branch now deletes the key. Tests: `test_api_failure_is_logged_and_can_be_retried` (Python); in n8n, see `workflows/code/shared/error_row.js`.
5. **Mock server restart.** One n8n dry run showed 0/50 narratives accepted, because the mock model process was still running the old (digit-typing) template. After a restart: 48/50. The other 2 were the injected failure and the injected invalid answer. The stale run was deleted.
