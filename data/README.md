# Data

Everything here is **synthetic and fictional**. "Lumi Skin" (a skincare retailer in Dubai), its customers and its suppliers do not exist. People use `@example.com` emails and `+971 50 000 xxxx` phone numbers. There is no real customer or company data. Licence: same as the repo (MIT).

| File | Rows | How it was made | Used by |
|---|---|---|---|
| `enquiries.jsonl` | 50 labelled emails | Written by a coding agent (Claude) on 8 October 2026 | Workflow 1 eval |
| `tickets.jsonl` | 50 labelled tickets | Written by a coding agent (Claude) on 8 October 2026 | Workflow 2 eval |
| `weekly_report/tickets.csv`, `enquiries.csv` | 2,266 tickets and 1,467 enquiries over 51 weeks | `generate.py` (seed 42) | Workflow 3 input |
| `weekly_report/weeks.jsonl` | 50 report requests with ground-truth numbers | `generate.py`: counted while generating, independently of the report code | Workflow 3 eval |
| `invoices/files/` | 50 invoices: 38 PDF + 12 `.txt` | `generate.py` (seed 42, fpdf2) | Workflow 4 input |
| `invoices/labels.jsonl` | the printed fields + planted problem per invoice | `generate.py` | Workflow 4 eval |

Regenerate with `python data/generate.py`. The output is deterministic.

## What is in the test sets

- **Enquiries.** 12 sales, 10 support, 10 complaint, 8 partnership and 10 spam. The languages are English (30), Arabic (10), French (5) and mixed Arabic/English (5). They include typos, missing names, missing companies, phishing and 3 prompt injections (`enq-009`, `enq-045`, `enq-048`).
- **Tickets.** 8 P1, 12 P2, 20 P3 and 10 P4, with sentiment and team (Technical, Billing, Delivery, Product, Account). The languages are English (28), Arabic (13), French (5) and mixed (4).
- **Invoices.**
  - Suppliers in AED (5% VAT), GBP (20%) and EUR (French, 20%).
  - 2–3 label layouts per language, and date formats such as `12/03/2026`, `12 March 2026`, `12-Mar-2026`, `12 mars 2026` and ISO.
  - 2 Arabic invoices with Arabic-Indic digits.
  - Planted problems:
    - 5 wrong totals;
    - 4 VAT computed at the wrong rate;
    - 3 missing fields (date, number, VAT line);
    - 2 duplicates (same supplier + number re-sent as a different file: `inv-037` repeats `inv-003`, `inv-049` repeats `inv-021`).

## Labelling guidelines (used for enquiries and tickets)

- **Enquiry category:**
  - sales: wants to buy, or asks prices or products before buying, including bulk and gift orders;
  - support: needs help with an order, account or product use;
  - complaint: unhappy about something that went wrong;
  - partnership: distribution, collaboration, influencer, affiliate or supplier pitches;
  - spam: scams, phishing, junk, tests.
- **Urgency:**
  - high: needs action today or tomorrow, a health/safety, money or legal risk, a public-complaint threat, or a request to escalate;
  - medium: a deadline within about 2 weeks, or an unresolved problem;
  - low: everything else (spam is always low).
- **Name and company:** exactly as written in the email or `from_name`, Arabic script kept. Fields are scored on the 40 non-spam emails only.
- **Ticket priority:**
  - P1: safety, security or data leak, account hacked, fraud, legal threat, outage;
  - P2: one customer clearly harmed or blocked;
  - P3: normal requests;
  - P4: feedback or suggestions.

**Caveats.** The same agent wrote the texts, the labels and the keyword baselines, so baseline scores here are optimistic. Some labels are judgement calls; urgency is the most subjective. Sara should review the labels before reporting live results, and ideally a second person should label a sample so agreement can be measured.
