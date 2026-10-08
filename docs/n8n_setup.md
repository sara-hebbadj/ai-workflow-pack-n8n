# Running the workflows in n8n

Tested on 8 October 2026 with **n8n 2.35.7** on Node.js 22.22. That was the newest n8n release that supports Node 22; n8n 2.37 and later need Node 24. Use Docker, or install Node 24 and use a newer n8n. The JSON uses only core nodes, so newer 2.x versions should import it, but that has not been tested.

## 1. Prepare the files

```bash
python scripts/prepare_workflows.py                                         # n8n started with npx from this folder
python scripts/prepare_workflows.py --base-dir /home/node/ai-workflow-pack-n8n   # n8n in Docker (see step 2)
```

This writes `build/n8n/*.json` (git-ignored) with each workflow's **Config** node filled in:

- `model_cheap` / `model_main` come from `MODEL_CHEAP` / `MODEL_MAIN` in `Portfolio Projects/.env`;
- `llm_base_url` is the OpenRouter base URL;
- `base_dir` is the folder where n8n reads `data/` and writes `outputs/` and `logs/`.

It also creates the CSV files with their header rows, because n8n only appends lines. **The API key is never written to any file.**

## 2. Start n8n

Docker:

```bash
docker run -it --rm -p 5678:5678 \
  -v "$PWD:/home/node/ai-workflow-pack-n8n" \
  -e N8N_RESTRICT_FILE_ACCESS_TO=/home/node/ai-workflow-pack-n8n \
  -e GENERIC_TIMEZONE=Asia/Dubai \
  docker.n8n.io/n8nio/n8n:2.35.7
```

Without Docker (Node 22.22+):

```bash
N8N_RESTRICT_FILE_ACCESS_TO="$PWD" GENERIC_TIMEZONE=Asia/Dubai npx n8n@2.35.7
```

`N8N_RESTRICT_FILE_ACCESS_TO` lets the "Read/Write Files from Disk" nodes use this folder and nothing else. Open http://localhost:5678 and create the local owner account. It stays on your machine; no n8n cloud account is needed.

## 3. Add the model credential (once)

In n8n, go to **Credentials → Add credential → OpenAI** and enter:

- **Name:** `OpenRouter (OpenAI-compatible)`. Use exactly this name; the workflows refer to it.
- **API Key:** your OpenRouter key.
- **Base URL:** `https://openrouter.ai/api/v1`.

## 4. Import and publish

Import the workflows in one of two ways:

- **Editor:** go to **Workflows → Import from file** and import the five files in `build/n8n/`, starting with `00_error_logger.json`.
- **CLI:** run `n8n import:workflow --input=build/n8n/all_workflows.json` while n8n is stopped.

After importing:

1. Open each AI node (5 in total) and select the `OpenRouter (OpenAI-compatible)` credential if n8n shows a warning. Imported workflows refer to the credential by name; your new credential has a different ID, so n8n may ask once.
2. **Publish** each workflow. The error logger is already set as each workflow's *Error Workflow*, in **Settings → Error workflow**.

## 5. Try it

```bash
curl -X POST localhost:5678/webhook/enquiry -H 'Content-Type: application/json' \
  -d '{"message_id":"demo-1","from_email":"layla@example.com","from_name":"Layla","subject":"Bulk order","body":"Hi, I want 30 serums for my spa. Price?"}'
curl -X POST localhost:5678/webhook/ticket -H 'Content-Type: application/json' \
  -d '{"ticket_id":"demo-t1","subject":"Rash","body":"I had an allergic reaction to the serum"}'
curl -X POST localhost:5678/webhook/weekly-report -H 'Content-Type: application/json' -d '{"week_start":"2026-03-02"}'
curl -X POST localhost:5678/webhook/invoice -F "file=@data/invoices/files/inv-001.pdf"
```

- The enquiry response contains an `approve_url`. Open it, adding `&approver=YourName`, to approve the draft. You can also use the approval inbox: `python app/approval_inbox.py`.
- To run the whole evaluation against n8n, use `python -m evals.run --target n8n --model cheap`.

## Without an API key (mock model)

```bash
python scripts/mock_llm_server.py --port 8765 --fail-ids enq-050 --invalid-ids enq-049
python scripts/prepare_workflows.py --llm-base-url http://127.0.0.1:8765/v1 --model-cheap mock --model-main mock
```

Then follow steps 2–4, using any text as the API key. The mock answers with the rule-based baselines. Use it to check the wiring, error branches, duplicates and the approval step; the numbers it produces are **not** model results. Run the evaluation with `python -m evals.run --target n8n --dry-run`.

## How to switch a workflow off

Unpublish the workflow in the editor, or toggle its webhook off. Webhooks then return 404, so callers can see the workflow is off; nothing is silently dropped. Waiting approvals stay in **Executions** until they are resumed or deleted. More detail is in [SOP.md](SOP.md).
