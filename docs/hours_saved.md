# Hours-saved estimate

> **These are estimates built from assumptions, not measured results.** No real team used these workflows. Every input below is an assumption; change it to your own numbers. The sheet is [`hours_saved.csv`](hours_saved.csv), which opens in Excel or Google Sheets.

## Formula

For each workflow:

- manual hours per week = weekly volume × manual minutes per item ÷ 60;
- after-automation hours per week = weekly volume × after minutes per item ÷ 60;
- hours saved per week = manual hours − after hours.

The "after" minutes are **not zero**. They include reading AI output, approving drafts and working the human-review queue. A separate row counts the new work the automation creates: 2 hours a week for the owner to watch the error log and maintain prompts and tests.

## Assumptions (all to be replaced with real observations)

| Workflow | Volume / week | Manual min / item | After min / item | Where the "after" time goes |
|---|---|---|---|---|
| Enquiry intake | 150 | 6.0 | 2.0 | Check fields, read/edit/approve every draft |
| Ticket triage | 300 | 3.0 | 0.8 | 0.5 min spot check + about 10% re-triaged by hand |
| Weekly report | 1 | 180 | 20 | Read the report; write commentary if the narrative is held |
| Invoices | 120 | 5.0 | 2.2 | 70% accepted × 1 min + 30% human-check queue × 5 min |
| Running the automation | n/a | 0 | 120 | Owner monitoring and maintenance |

**Estimated result:** 43.0 hours a week by hand, against 15.7 hours with the automation. That is about **27 hours a week saved**, or roughly 0.7 of a full-time person.

## What the estimate is most sensitive to

- **The invoice human-check rate.** With no layout knowledge, the regex baseline sent 25/50 test invoices to the wrong status. If the live AI still sends 50% of invoices to the queue, "after" becomes 0.5 × 1 + 0.5 × 5 = 3.0 minutes, and the invoice saving drops from 5.6 to 4.0 hours.
- **Draft edit rate.** If agents rewrite most drafts, "after" for enquiries moves towards 4 minutes, and that saving halves to 5 hours.
- **Volumes.** These are guesses for a mid-size retailer. The saving scales roughly linearly with volume.

## How to measure the real number

1. **Baseline (2 weeks before go-live):** each team logs, for a sample of 30 items, the start and end time of the manual task (time-and-motion), plus weekly volumes from the inbox, helpdesk and finance system.
2. **After go-live (2–4 weeks):**
   - get volumes and outcomes from n8n executions and the CSV sheets;
   - get review time from the approval inbox timestamps (draft created → decision);
   - get the human-review queue size per day;
   - sample-time 30 items again.
3. **Compare** the median minutes per item, and report the range rather than one number. Also count quality: wrong replies caught at approval, invoices corrected, P1 response time.
4. **Include the owner's real maintenance hours.**
