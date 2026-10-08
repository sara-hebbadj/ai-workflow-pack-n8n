# SOP: AI workflow pack (Lumi Skin operations)

**Version** 0.1 (draft, 8 October 2026) · **Owner** Operations lead · **Applies to** the four n8n workflows in this repo

## 1. Purpose

The four workflows sort enquiries, triage support tickets, produce the Monday operations report and turn supplier invoices into register rows. The AI reads text; code applies the rules; a person approves anything customer-facing.

## 2. Triggers and owners

| Workflow | Trigger | Business owner | Daily checker | Output |
|---|---|---|---|---|
| 01 Enquiry intake | Every inbound email (webhook) | Customer team lead | Customer agent on shift | Team sheet, approval queue, sent log |
| 02 Ticket triage | Every new ticket (webhook) | Support lead | Support agent on shift | Channel post; P1 escalation to on-call |
| 03 Weekly report | Monday 08:00 Dubai time (schedule) | Operations lead | Operations lead | Report email (MD/HTML) |
| 04 Invoices | File upload (webhook) | Finance lead | Accounts assistant | Invoice register, human-check queue |
| 00 Error logger | Any failed run | Automation owner (Sara) | Automation owner | `logs/errors.csv` |

## 3. The approval step (never skipped)

- **Enquiry replies:** every AI draft waits as `pending_approval`. The agent reads it, edits it if needed, and approves or rejects it through the approval link or the approval inbox. Nothing is sent before approval. Rejected drafts are logged as "not sent".
- **Human review queue** (`outputs/human_review_queue.csv`): work it at least twice a day. Each row names the workflow, the item and the reason, for example:
  - possible prompt injection;
  - low confidence;
  - failed schema check;
  - total does not equal net + VAT;
  - narrative held.
- **P1 tickets** are escalated automatically. The on-call person acknowledges them within 15 minutes.

## 4. Failure handling

1. **AI or API outage.** Each call is tried 3 times. After that the item is logged in `logs/errors.csv` and the sender gets HTTP 500. The item's duplicate key is released, so it is safe to re-send it once the service is back. Safety tickets are still escalated while the AI is down.
2. **Bad input** (missing body, unsupported file, corrupt PDF): the item is logged with step `check_input` or `extract_text`. Fix the source and re-send.
3. **Unexpected failure** (bug): the global error logger records the workflow, the node and the message. The automation owner investigates the same day.
4. **Daily check (automation owner, 5 minutes):**
   - New rows in `errors.csv`?
   - Review-queue size compared with yesterday?
   - Executions waiting for more than 24 hours?
5. **Escalate to the automation owner** if more than 5 errors arrive in an hour, the review queue doubles, or a report or reply looks wrong.

## 5. How to switch off

- **One workflow:** unpublish it in n8n. Its webhook returns 404 and senders fall back to the manual process (shared inbox, helpdesk, Excel register).
- **Everything:** stop n8n. No data is lost: inputs stay in their source systems, and the queues are files.
- **Model problem only:** change `model_cheap` / `model_main` in the workflow's Config node, or unpublish the workflow until fixed.

## 6. Changes and data

- Prompts and thresholds live in each workflow's **Config** node.
- Any change is tested with `python -m evals.run --target n8n --limit 10` before it is published, and logged in the repo history.
- Only business data goes to the model provider (OpenRouter). Payment card data and ID documents must never be sent through these workflows.
- The API key is stored only in n8n credentials.
