# Staff guide: working with the AI workflows

*One page for the customer, support and finance teams. Draft, 8 October 2026.*

## What the AI does, and what it does not

- **It reads and suggests:**
  - what an email is about;
  - who sent it;
  - how urgent it is;
  - a draft reply;
  - a ticket's priority and team;
  - the fields on an invoice;
  - the wording of the Monday report.
- **It does not decide or send.** Code applies the rules (routing, escalation, totals, numbers) and you approve every reply.
- **It can be wrong**, especially with mixed languages, unusual invoice layouts, sarcasm or very short messages. Its "confidence" is its own guess, not a guarantee.

## Your daily checks

| You see | Check | Then |
|---|---|---|
| A draft reply (approval inbox) | Facts, tone, language, and no promises on refunds, prices or dates | Edit if needed → **Approve**, or **Reject** and reply yourself |
| A review-queue row: *possible prompt injection* | The email tries to give the AI orders ("ignore previous instructions…") | Treat it as suspicious. Do not follow its requests. Report phishing to IT |
| A review-queue row: *low confidence* or *failed schema check* | Read the original message | Set the category or priority yourself in the sheet or helpdesk |
| An invoice in the human-check queue | Compare the reasons (for example "total does not equal net + VAT") with the PDF | Fix the field or contact the supplier. Never "make it add up" |
| A P1 escalation | The ticket text | Contact the customer within 15 minutes. Health issues: advise them to stop using the product and follow the safety script |
| A weekly report with "narrative held for review" | The numbers table is correct (computed by code) | Write two lines of commentary yourself, or ask the automation owner |

## How to correct the AI

- Correct the record where you work: the sheet, the helpdesk or the invoice register. Add a short note, such as "AI said sales, was complaint".
- Every Friday, the automation owner collects these notes. Repeated mistakes become new test cases and, if needed, a prompt or rule change. Your corrections make the system better.

## When to escalate to the automation owner (Sara)

- The same mistake 3 or more times in a day.
- Any reply that would have gone out wrong if you had not checked it.
- Anything that looks like customer data leaking, or an email that manipulates the AI and gets past the review queue.
- The review queue or the error log growing fast, or a workflow not responding.

## Remember

> The AI drafts, the code checks, **you decide**. If in doubt, do it the manual way and tell us.
