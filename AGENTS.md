# Notes for coding agents (this repo)

Read `README.md` first. The shared rules for all of Sara's portfolio projects are in `../../AGENTS.md`: secrets, honesty, publishing only with Sara's OK.

## Where things live

- `workflows/*.json` are **generated**. Edit the sources, then run `python scripts/build_workflows.py`:
  - JavaScript: `workflows/code/` (`// @include x.js` pulls in `workflows/code/lib/x.js`);
  - prompts: `prompts/`;
  - schemas: `schemas/`;
  - rule tables: Python constants. `__CONST:module.NAME__` in the JS is replaced with the JSON of that constant.
- `tests/test_workflow_json.py::test_committed_json_matches_the_generator` fails if you forget to rebuild. If Sara starts editing in the n8n UI instead, export over the JSON and delete that one test.
- The Python reference in `src/workflow_pack/` must make the same decisions as the JavaScript. `tests/test_js_parity.py` checks this; it needs Node.js and is skipped without it.

## Rules

- Never put a key in a workflow, test or file. n8n uses the credential named `OpenRouter (OpenAI-compatible)`, referenced by name and id only. Python reads `OPENROUTER_API_KEY` from `Portfolio Projects/.env`.
- Tests never touch the network: use `FakeClient` or monkeypatch the SDK.
- Any LLM number in the README must come from `python -m evals.run` (not `--dry-run`) with the model ID, the date and the denominator. Dry-run and mock-server outputs go to `evals/dry_run/` and are never results.
- Keep the JavaScript compatible with n8n's Code node: `runOnceForAllItems` mode, `$input`, `$('Node')`, `$getWorkflowStaticData`, `$execution`; no `require`.
- Every workflow follows the same shape: Config → check input → Seen before? → AI call (3 tries, error output) → schema check → rules → output rows → respond, plus the error branch. Keep it that way so Sara can explain one pattern.

## Useful commands

```bash
python scripts/build_workflows.py                  # regenerate workflows/*.json
python -m evals.deterministic                      # model-free checks (real numbers)
python -m evals.run --dry-run                      # full pipeline, fake model
python scripts/mock_llm_server.py --port 8765      # OpenAI-compatible mock for n8n
python -m evals.run --target n8n --dry-run         # n8n end to end against the mock
python -m evals.compare_runs <python_run> <n8n_run>
```

Tested with n8n 2.35.7 on Node 22.22; n8n 2.37+ needs Node 24.
