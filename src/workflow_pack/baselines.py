"""Rule-based baselines: what you get with keywords and regular expressions, no AI.

They give a floor to compare the AI against, and they power the fake model used by
tests and `--dry-run`. Caveat: the same person wrote these rules and the test labels,
so baseline scores on our own test set are optimistic.
"""

import re
from datetime import datetime

from workflow_pack.triage import safety_match


def _has(text: str, *patterns: str) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


# ---------------------------------------------------------------- enquiries

ENQUIRY_RULES = [  # first match wins; generic keywords, not tuned per example
    ("spam", [r"\bwon\b|winner|prize|click here|\bseo\b|followers|crypto|bank details|verify your password|lottery",
              r"اربح|مجاناً|بطاقتك|\biban\b|admin mode|lorem|asdf"]),
    ("complaint", [r"wrong|disappoint|burn|charged twice|broken|cass[ée]|melted|rude|refund|money back|mony back|expired",
                   r"منته|متأخر|غير مقبول|bad service|still (no|nothing)|pimples"]),
    ("partnership", [r"collaborat|partner|شراكة|distribut|affiliate|sponsor|\bstand\b|meeting|اجتماع"]),
    ("support", [r"track|how (do|can|should) i|password|كلمة المرور|change|modifier|\bcode\b|\badd\b|invoice|أستبدل|exchange",
                 r"deliver|\bsafe\b"]),
]  # fmt: skip
CLOSINGS = r"^(thanks|thx|thank you|regards|best|kind regards|best regards|cordialement|merci|مع الشكر|شكرا|hi|hello|dear)"


def enquiry_baseline(enquiry: dict) -> dict:
    text = f"{enquiry.get('subject', '')}\n{enquiry.get('body', '')}"
    category = next((cat for cat, patterns in ENQUIRY_RULES if _has(text, *patterns)), "sales")
    name, company = _signature(enquiry)
    if category == "spam":
        name = company = None
    return {
        "category": category,
        "name": name,
        "company": company,
        "need": (enquiry.get("subject") or "")[:120],
        "urgency": "low" if category == "spam" else _urgency(text),
        "language": detect_language(enquiry.get("body", "")),
        "confidence": 0.7,
    }


def _urgency(text: str) -> str:
    if _has(text, r"today|tomorrow|immediately|urgent|demain|tonight|اليوم|escalate|burning|charged twice|منته|instagram"):
        return "high"
    if _has(
        text, r"\bby\b|next week|sunday|saturday|friday|vendredi|end of|نهاية|disappoint|not work|wrong|refund|متأخر|never got"
    ):
        return "medium"
    return "low"


def _signature(enquiry: dict) -> tuple[str | None, str | None]:
    """Guess name and company from the last short lines of the email."""
    lines = [ln.strip(" -,") for ln in enquiry.get("body", "").splitlines() if ln.strip()]
    tail = [
        ln for ln in lines[-2:] if len(ln.split()) <= 5 and not ln.endswith(("?", ".", "!")) and not re.match(CLOSINGS, ln, re.I)
    ]
    from_name = (enquiry.get("from_name") or "").strip() or None
    if len(tail) == 2:
        return from_name or tail[0], tail[1]
    if len(tail) == 1:
        return (from_name, None) if from_name else (tail[0], None)
    return from_name, None


def detect_language(text: str) -> str:
    arabic_words = len(re.findall(r"[؀-ۿ]{2,}", text))
    latin_words = len(re.findall(r"\b[a-zA-Zàâçéèêëîïôûùüÿœ]{2,}\b", text))
    if arabic_words >= 2 and latin_words >= 3:
        return "mixed"
    if arabic_words >= 2:
        return "ar"
    if _has(text, r"\b(bonjour|merci|je|vous|nous|cordialement|commande|investissez)\b"):
        return "fr"
    return "en"


# ---------------------------------------------------------------- tickets

PRIORITY_RULES = [  # generic keywords, not tuned per example
    ("P1", [r"\b(down|outage)\b"]),
    ("P2", [r"charged twice|double charge|refund|rembours|\blate\b|delayed|متأخر|damaged|broken|wrong item",
            r"received .* (but|instead)|can't complete|cannot complete|failing|لا أستطيع|never arrived|لم يصل",
            r"disappeared|\blost\b|returned to"]),
    ("P4", [r"thank|شكرا|suggest|would be nice|ce serait bien|unsubscribe|any plans|loved|في المستقبل"]),
]  # fmt: skip
TEAM_RULES = [  # first match wins
    ("Technical", [r"\bapp\b|website|checkout|error|crash|slow|التطبيق|\bbug\b"]),
    ("Billing", [r"charge|refund|rembours|invoice|فاتورة|tabby|تقسيط|payment|promo|price"]),
    ("Account", [r"account|حساب|password|log ?in|phone number|e-mail|email address|unsubscribe|points"]),
    ("Delivery", [r"deliver|courier|tracking|ship|التوصيل|المندوب|تشحن|exchange|address|parcel|package|pickup",
                  r"warehouse|\blate\b|متأخر"]),
]  # fmt: skip


def ticket_baseline(ticket: dict) -> dict:
    text = f"{ticket.get('subject', '')}\n{ticket.get('body', '')}"
    priority = "P1" if safety_match(text) else next((p for p, pats in PRIORITY_RULES if _has(text, *pats)), "P3")
    team = next((t for t, pats in TEAM_RULES if _has(text, *pats)), "Product")
    if _has(text, r"amazing|thanks|loved|رائع|polite|يحب|great"):
        sentiment = "positive"
    elif priority in ("P1", "P2") or _has(text, r"stopped|slow|crash|not working|problem"):
        sentiment = "negative"
    else:
        sentiment = "neutral"
    return {
        "priority": priority,
        "sentiment": sentiment,
        "team": team,
        "summary": ticket.get("subject", "")[:200],
        "confidence": 0.7,
    }


# ---------------------------------------------------------------- invoices

LABELS = {
    "invoice_number": r"(?:Invoice No|N° de facture|رقم الفاتورة)\s*:\s*(\S+)",
    "invoice_date": r"(?:Invoice Date|^Date|التاريخ)\s*:\s*(.+)$",
    "net_amount": r"(?:Subtotal|Total HT|المجموع الفرعي)\s*:\s*(.+)$",
    "vat_line": r"(?:VAT|TVA|ضريبة القيمة المضافة)\s*([\d.,]+)\s*%\s*:\s*(.+)$",
    "total_amount": r"(?:^Total|Total TTC|الإجمالي)\s*:\s*(.+)$",
}
FR_MONTHS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


def parse_amount(text: str) -> float | None:
    """'AED 1,234.50' -> 1234.5 ; '1 234,50 EUR' -> 1234.5. (Python's \\d and float() also accept Arabic-Indic digits.)"""
    raw = re.sub(r"[^\d.,]", "", text.replace(" ", " ").replace(" ", ""))
    if not raw or not re.search(r"\d", raw):
        return None
    if "," in raw and "." not in raw and re.search(r",\d{2}$", raw):
        raw = raw.replace(",", ".")  # French decimal comma
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def parse_date(text: str) -> str | None:
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    parts = text.split()
    if len(parts) == 3 and parts[1] in FR_MONTHS:
        return f"{parts[2]}-{FR_MONTHS.index(parts[1]) + 1:02d}-{int(parts[0]):02d}"
    return None


def invoice_baseline(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    def find(key: str):
        for line in lines:
            match = re.search(LABELS[key], line, flags=re.IGNORECASE)
            if match:
                return match
        return None

    number, date_match, net, vat, total = (
        find(k) for k in ("invoice_number", "invoice_date", "net_amount", "vat_line", "total_amount")
    )
    fields = {
        "supplier_name": _supplier(lines),
        "invoice_number": number.group(1) if number else None,
        "invoice_date": parse_date(date_match.group(1)) if date_match else None,
        "currency": _currency(text),
        "net_amount": parse_amount(net.group(1)) if net else None,
        "vat_rate": parse_amount(vat.group(1)) if vat else None,
        "vat_amount": parse_amount(vat.group(2)) if vat else None,
        "total_amount": parse_amount(total.group(1)) if total else None,
    }
    fields["confidence"] = 0.9 if all(v is not None for v in fields.values()) else 0.5
    return fields


def _supplier(lines: list[str]) -> str | None:
    for line in lines:
        if line.startswith("المورد:"):
            return line.split(":", 1)[1].strip()
    for i, line in enumerate(lines[:-1]):
        if line in ("TAX INVOICE", "FACTURE"):
            return lines[i + 1]
    return None


def _currency(text: str) -> str | None:
    for code in ("AED", "EUR", "GBP", "USD"):
        if code in text:
            return code
    return "AED" if "درهم" in text else None


# ---------------------------------------------------------------- weekly report


def narrative_baseline(numbers: dict) -> dict:
    """A template narrative written with placeholders, like the real model must (what the fake model returns)."""
    return {
        "headline": "{tickets_total} tickets this week ({tickets_change_pct}% change vs last week).",
        "narrative": "\n".join([
            "- The team handled {tickets_total} tickets and {enquiries_total} enquiries.",
            "- There were {tickets_by_priority.P1} P1 tickets and {sla_breaches} first-response SLA breaches.",
            "- Negative sentiment was {negative_sentiment_pct}% of tickets.",
            "- Suggested action: review the SLA breaches with the team leads.",
        ]),
    }  # fmt: skip
