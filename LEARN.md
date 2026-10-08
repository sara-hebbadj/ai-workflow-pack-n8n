# LEARN: walkthrough, interview questions and live exercises

## 10-minute walkthrough script

1. **(1 min) The problem.** "Lumi Skin is a fictional mid-size retailer. By my estimate from stated assumptions (`docs/hours_saved.md`, not measured), its operations team spends about 43 hours a week on four jobs: the inbox, tickets, the Monday report and invoices. I automated them with n8n and an AI model, and code makes sure the AI cannot send, miscount or double-book anything."
2. **(2 min) The shared pattern.** Open `docs/screenshots/02_ticket_triage.png` and point at each step:
   - Trigger, then Config (model, prompts and thresholds in one place);
   - Check input;
   - Seen before? (idempotency);
   - AI call (3 tries);
   - schema check;
   - rules in code;
   - write rows and respond.

   Then show the red error branch: "Every failure ends here: one row in `logs/errors.csv`, the duplicate key is released, the caller gets HTTP 500."
3. **(2 min) Enquiry intake and human approval.**
   - Run the curl from `docs/n8n_setup.md`, show the `approve_url`, open it, and show the line in `sent_emails.csv`.
   - "Nothing is sent before a person clicks approve."
   - Show enquiry `enq-009` (a prompt injection), which lands in the review queue.
4. **(1.5 min) Ticket triage safety net.**
   - Post `t-001` (an allergic reaction): it is escalated as P1 by the safety net, even with the mock model set to fail (`--fail-ids t-001`).
   - "Health, security, fraud and legal keywords always win over the AI."
5. **(1.5 min) Weekly report.**
   - Open `outputs/reports/weekly_2026-03-02.md`.
   - "Every number comes from code. The AI writes `{sla_breaches}`, not 3. If it types a digit, the narrative is held."
   - Show `evals/deterministic/results.md`: 1200/1200 numbers, and 50/50 bad narratives caught.
6. **(1 min) Invoices.**
   - Upload `inv-033.pdf` (planted wrong total). It goes to the human-check queue with the reason.
   - Upload `inv-040.txt` twice: the second upload is a duplicate.
7. **(1 min) Evidence and honesty.**
   - 200/200 n8n decisions are identical to the Python reference.
   - Live model (`openai/gpt-6-luna`, 8 October 2026): invoices 50/50 with all fields correct against 19/50 for the regex baseline; enquiry category 50/50; ticket priority 48/50.
   - The hours saved are an estimate with its assumptions shown.

## 10 interview questions with short answers

1. **Which steps did you keep deterministic, and why?**
   - Routing, escalation, every report number, totals/VAT checks, duplicates and sending all stay in code or with a person.
   - They must be predictable, auditable and cheap to verify. The AI only reads messy text and writes wording.
2. **How do you stop duplicate records or emails?**
   - An idempotency key per input: message ID, ticket ID, week, or the SHA-256 of the file.
   - The key is stored in n8n static data and checked before any AI call. Invoices also get a business key (supplier + invoice number).
   - Replies only go out after approval, and the approval resumes one specific execution.
3. **What happens when the model API is down?**
   - 3 tries, 2 seconds apart, then the error output: a row in `errors.csv`, HTTP 500, and the key released so a retry works.
   - P1 safety tickets are escalated anyway.
4. **How do you know the AI output is usable?** Every reply is parsed and checked against a JSON Schema (`schemas/`). Invalid output never flows on; it goes to the human review queue.
5. **How did you test n8n workflows without a key?**
   - Three ways:
     - I ran the Code-node JavaScript from the exported JSON with Node.js and compared it with a Python reference;
     - I ran the real n8n 2.35.7 against a mock OpenAI-compatible server on 200 inputs (200/200 identical decisions);
     - I injected failures and invalid answers.
   - A real model was then run (8 October 2026, by the coding agent) on all 200 inputs through the Python reference and on 40 inputs through n8n (35/40 identical decisions; the 5 differences were the model's own answers).
6. **How do you defend against prompt injection?**
   - The prompts treat the email as data.
   - A deterministic tripwire holds suspicious emails for a person.
   - The AI has no tools and cannot send anything.
   - It flagged 3/3 injections with 0/47 false alarms on the test set, a small sample.
7. **Why placeholders in the report narrative?**
   - My first check, "every number in the text exists in the data", caught only 17/50 narratives with a wrong number, because the wrong value often matched another count.
   - With placeholders the AI never types a number, and the same test catches 50/50.
   - Placeholders guarantee the numbers, not the words: the first live run wrote "fell by -54.5%" in 21 of 22 weeks with fewer tickets. The check now also holds that wording.
8. **How would you roll this out to a 50-person team?**
   - Pilot one workflow with one team.
   - Use the SOP (owners, approval step, switch-off) and the one-page training.
   - Hold a daily 5-minute check of the error log and review queue, and a weekly review of corrections, which feed new test cases.
   - Widen only when the measured review rate and error rate are acceptable.
9. **How would you measure the real hours saved?** A 2-week time-and-motion sample before go-live; then n8n execution data, approval timestamps and review-queue sizes after go-live; compare median minutes per item, including the owner's maintenance time. The current sheet is an estimate.
10. **What would you change for production?**
    - A database instead of static data for keys (no race conditions).
    - Real Sheets, Slack and Gmail nodes instead of CSV files.
    - OCR for scanned PDFs.
    - Calibrated confidence, from accuracy against labels per confidence band.
    - Alerting on the error log.

## 3 "change it live" exercises

1. **Add a team.** Add `"wholesale": "Wholesale desk"` as a category:
   - in `TEAM_BY_CATEGORY` (`src/workflow_pack/enquiry.py`);
   - in the enum in `schemas/enquiry_classify.schema.json`;
   - in the category list in `prompts/enquiry_classify.md`.

   Run `python scripts/build_workflows.py` and `pytest`. Show that the JSON test and the JavaScript parity test still pass.
2. **Make invoices stricter.** Change `INVOICE_MIN_CONFIDENCE` from 0.8 to 0.9 in `src/workflow_pack/config.py`; the build script copies it into the n8n Config node. Rebuild, and show how the human-review rate changes in `python -m evals.run --dry-run --workflow invoice`.
3. **Add a safety keyword.** Add `r"\bswollen\b"` to `SAFETY_PATTERNS` in `triage.py`, then:
   - rebuild;
   - write a test ticket "My lips are swollen" and show that it is escalated as P1 in both Python (`pytest -k safety`) and the n8n JavaScript (`tests/test_js_parity.py`).
