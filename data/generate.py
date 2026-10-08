"""Generate the synthetic invoices and weekly-report CSVs (seed 42).

Run:  python data/generate.py
All companies, people and numbers are fictional. Emails use @example.com.

The enquiry and ticket test sets (enquiries.jsonl, tickets.jsonl) were written by hand
and are not produced by this script.
"""

import csv
import json
import random
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from fpdf import FPDF

SEED = 42
DATA = Path(__file__).resolve().parent
INVOICE_DIR = DATA / "invoices"
REPORT_DIR = DATA / "weekly_report"
CENT = Decimal("0.01")

# ---------------------------------------------------------------- invoices

SUPPLIERS = {
    "DBP": ("Desert Bloom Packaging LLC", "Warehouse 12, Al Quoz Industrial Area 3, Dubai, UAE", "AED", 5, "en"),
    "GGB": ("Gulf Glass Bottles FZE", "Plot S-41, Jebel Ali Free Zone, Dubai, UAE", "AED", 5, "en"),
    "OPS": ("Oasis Print Studio", "Office 204, Al Nahda 1, Dubai, UAE", "AED", 5, "en"),
    "MCS": ("Marina Courier Services LLC", "Marina Plaza, Dubai Marina, Dubai, UAE", "AED", 5, "en"),
    "ATB": ("Atlas Botanicals Ltd", "14 Mill Lane, Bristol, United Kingdom", "GBP", 20, "en"),
    "NLS": ("Northbank Lab Supplies Ltd", "3 Canal Street, Manchester, United Kingdom", "GBP", 20, "en"),
    "LC": ("Laboratoires Céleste SARL", "12 rue des Lilas, 69003 Lyon, France", "EUR", 20, "fr"),
    "PDP": ("Parfums de Provence SAS", "8 avenue des Oliviers, Aix-en-Provence, France", "EUR", 20, "fr"),
    "NAD": ("مؤسسة الندى للتجارة", "دبي، الإمارات العربية المتحدة", "AED", 5, "ar"),
    "WMR": ("شركة الواحة للمواد الخام", "الشارقة، الإمارات العربية المتحدة", "AED", 5, "ar"),
}
ITEMS = {
    "DBP": [("Kraft gift boxes", 0.9, 4.5), ("Tissue paper sheets", 0.1, 0.4), ("Shipping cartons", 1.5, 6.0)],
    "GGB": [("Amber glass bottle 30ml", 0.8, 2.5), ("Dropper caps", 0.3, 1.2), ("Frosted jar 50ml", 1.1, 3.4)],
    "OPS": [("Product labels (roll)", 40, 120), ("Leaflets A6", 0.2, 0.6), ("Thank-you cards", 0.3, 1.0)],
    "MCS": [("Same-day deliveries", 12, 25), ("Next-day deliveries", 8, 15), ("Return pick-ups", 10, 18)],
    "ATB": [("Rosehip oil 1L", 18, 35), ("Shea butter 1kg", 9, 16), ("Aloe vera gel 5L", 22, 40)],
    "NLS": [("pH test strips", 4, 9), ("Glass beakers set", 12, 30), ("Nitrile gloves box", 5, 11)],
    "LC": [("Acide hyaluronique 100g", 45, 80), ("Niacinamide 250g", 20, 38), ("Vitamine C 100g", 30, 55)],
    "PDP": [("Huile essentielle lavande 1L", 35, 70), ("Eau de rose 5L", 15, 30), ("Fragrance neroli 250ml", 40, 75)],
    "NAD": [("عبوات بلاستيكية ١٠٠ مل", 0.6, 1.8), ("أغطية مضخة", 0.4, 1.1), ("ملصقات المنتجات", 30, 90)],
    "WMR": [("زيت الأرغان ١ لتر", 60, 110), ("زبدة الكاكاو ١ كغ", 25, 45), ("جلسرين نباتي ٥ لتر", 30, 55)],
}
# Which supplier and format each invoice uses (index 1..50).
PDF_SUPPLIERS = ["DBP", "GGB", "OPS", "MCS", "ATB", "NLS", "LC", "PDP"]
PLANTED = {  # invoice number -> planted problem
    5: "total_mismatch", 14: "total_mismatch", 23: "total_mismatch", 33: "total_mismatch", 42: "total_mismatch",
    9: "vat_mismatch", 19: "vat_mismatch", 28: "vat_mismatch", 44: "vat_mismatch",
    12: "missing_date", 31: "missing_number", 48: "missing_vat",
    37: "duplicate", 49: "duplicate",
}  # fmt: skip
DUPLICATE_OF = {37: 3, 49: 21}
EXPECTED_STATUS = {"total_mismatch": "needs_review", "vat_mismatch": "needs_review", "missing_date": "needs_review",
                   "missing_number": "needs_review", "missing_vat": "needs_review", "duplicate": "duplicate"}  # fmt: skip
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
ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_en(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def fmt_fr(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")


def format_date(d: date, lang: str, style: int) -> str:
    if lang == "fr":
        return f"{d.day} {FR_MONTHS[d.month - 1]} {d.year}"
    if lang == "ar":
        return d.isoformat() if style % 2 == 0 else d.strftime("%d/%m/%Y")
    return [d.strftime("%d/%m/%Y"), d.strftime("%d %B %Y"), d.isoformat(), d.strftime("%d-%b-%Y")][style % 4]


def make_invoice(rng: random.Random, index: int, code: str) -> dict:
    """Build one invoice's true values (before any planted problem)."""
    name, address, currency, rate, lang = SUPPLIERS[code]
    lines = []
    for description, low, high in rng.sample(ITEMS[code], k=rng.randint(1, 3)):
        qty = rng.choice([1, 2, 5, 10, 20, 50, 100, 200, 500]) if high < 10 else rng.randint(1, 12)
        unit = money(rng.uniform(low, high))
        lines.append((description, qty, unit, (unit * qty).quantize(CENT)))
    net = sum((amount for *_, amount in lines), Decimal("0.00"))
    vat = (net * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    issued = date(2026, 1, 5) + timedelta(days=rng.randint(0, 250))
    return {
        "index": index, "code": code, "supplier_name": name, "address": address, "currency": currency,
        "vat_rate": rate, "lang": lang, "invoice_number": f"{code}-2026-{rng.randint(1000, 9999)}",
        "invoice_date": issued, "lines": lines, "net": net, "vat": vat, "total": net + vat,
    }  # fmt: skip


def plant_problem(inv: dict, problem: str, rng: random.Random) -> dict:
    """Change what is *printed* so the invoice contains the planted problem."""
    printed = dict(inv)
    if problem == "total_mismatch":
        printed["total"] = inv["total"] + Decimal(rng.choice(["10.00", "-5.00", "0.50", "100.00", "-1.00"]))
    elif problem == "vat_mismatch":  # VAT computed at the wrong rate; total is consistent with the wrong VAT
        printed["vat"] = (inv["net"] * (inv["vat_rate"] + 5) / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        printed["total"] = inv["net"] + printed["vat"]
    elif problem == "missing_date":
        printed["invoice_date"] = None
    elif problem == "missing_number":
        printed["invoice_number"] = None
    elif problem == "missing_vat":
        printed["vat"] = None
    return printed


# Label wording varies between suppliers, as on real invoices: (number, date, net, vat, total).
EN_LAYOUTS = [
    ("Invoice No: {}", "Invoice Date: {}", "Subtotal: {cur} {}", "VAT {rate}%: {cur} {}", "Total: {cur} {}"),
    ("Inv # {}", "Date of issue {}", "Net amount {} {cur}", "VAT @ {rate}% {} {cur}", "Amount due {} {cur}"),
    ("INVOICE NUMBER    {}", "DATE    {}", "Sub-total    {cur} {}", "Tax ({rate}%)    {cur} {}", "GRAND TOTAL    {cur} {}"),
]
FR_LAYOUTS = [
    ("N° de facture : {}", "Date : {}", "Total HT : {} {cur}", "TVA {rate} % : {} {cur}", "Total TTC : {} {cur}"),
    ("Facture n° {}", "Date d'émission : {}", "Montant HT {} {cur}", "TVA ({rate} %) {} {cur}", "Net à payer {} {cur}"),
]
AR_LAYOUTS = [
    ("رقم الفاتورة: {}", "التاريخ: {}", "المجموع الفرعي: {} درهم", "ضريبة القيمة المضافة {rate}%: {} درهم", "الإجمالي: {} درهم"),
    ("رقم: {}", "تاريخ الفاتورة: {}", "الصافي: {} درهم", "الضريبة ({rate}%): {} درهم", "المبلغ المستحق: {} درهم"),
]


def invoice_lines(p: dict, header_note: str = "") -> list[str]:
    """The text content of an invoice, in its supplier's language and one of its label layouts."""
    cur, lang = p["currency"], p["lang"]
    f = fmt_fr if lang == "fr" else fmt_en
    layouts = FR_LAYOUTS if lang == "fr" else EN_LAYOUTS
    number_l, date_l, net_l, vat_l, total_l = layouts[p["index"] % len(layouts)]
    if lang == "fr":
        out = [header_note, "FACTURE", p["supplier_name"], p["address"], "TVA intracom. : FR00 000000000"]
    else:
        out = [header_note, "TAX INVOICE", p["supplier_name"], p["address"], "TRN: 100000000000003"]
    if p["invoice_number"]:
        out.append(number_l.format(p["invoice_number"]))
    if p["invoice_date"]:
        out.append(date_l.format(format_date(p["invoice_date"], lang, p["index"])))
    if lang == "fr":
        out += ["Client : Lumi Skin Trading LLC, Dubai, UAE", "Désignation | Qté | Prix unitaire | Montant"]
    else:
        out += ["Bill To: Lumi Skin Trading LLC, Dubai, UAE", "Description | Qty | Unit Price | Amount"]
    out += [f"{d} | {q} | {f(u)} | {f(a)}" for d, q, u, a in p["lines"]]
    out.append(net_l.format(f(p["net"]), cur=cur))
    if p["vat"] is not None:
        out.append(vat_l.format(f(p["vat"]), cur=cur, rate=p["vat_rate"]))
    out.append(total_l.format(f(p["total"]), cur=cur))
    if lang != "fr":
        out.append("Payment terms: 30 days")
    return [line for line in out if line]


def arabic_lines(p: dict, arabic_digits: bool) -> list[str]:
    def f(x):
        return fmt_en(x).translate(ARABIC_DIGITS) if arabic_digits else fmt_en(x)

    number_l, date_l, net_l, vat_l, total_l = AR_LAYOUTS[p["index"] % len(AR_LAYOUTS)]
    out = ["فاتورة ضريبية", f"المورد: {p['supplier_name']}", f"العنوان: {p['address']}"]
    if p["invoice_number"]:
        out.append(number_l.format(p["invoice_number"]))
    if p["invoice_date"]:
        out.append(date_l.format(format_date(p["invoice_date"], "ar", p["index"])))
    out.append("العميل: لومي سكين للتجارة ذ.م.م، دبي")
    out += [f"{d} - الكمية {q} - السعر {f(u)} - المبلغ {f(a)}" for d, q, u, a in p["lines"]]
    out.append(net_l.format(f(p["net"])))
    if p["vat"] is not None:
        out.append(vat_l.format(f(p["vat"]), rate=p["vat_rate"]))
    out.append(total_l.format(f(p["total"])))
    return out


def email_lines(p: dict) -> list[str]:
    body = invoice_lines(p)
    return ["From: accounts@supplier.example.com", f"Subject: Invoice from {p['supplier_name']}",
            "Hello Lumi Skin team,", "Please find our invoice details below.", "", *body, "", "Kind regards,",
            "Accounts team"]  # fmt: skip


def write_pdf(path: Path, lines: list[str]) -> None:
    pdf = FPDF()
    pdf.set_creation_date(datetime(2026, 10, 8, tzinfo=UTC))  # fixed, so regenerating gives identical files
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def label_for(p: dict, problem: str) -> dict:
    return {
        "supplier_name": p["supplier_name"],
        "invoice_number": p["invoice_number"],
        "invoice_date": p["invoice_date"].isoformat() if p["invoice_date"] else None,
        "currency": p["currency"],
        "net_amount": float(p["net"]),
        "vat_rate": float(p["vat_rate"]) if p["vat"] is not None else None,
        "vat_amount": float(p["vat"]) if p["vat"] is not None else None,
        "total_amount": float(p["total"]),
        "issue": problem,
        "expected_status": EXPECTED_STATUS.get(problem, "accepted"),
    }


def generate_invoices(rng: random.Random) -> None:
    files_dir = INVOICE_DIR / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    originals, labels = {}, []
    for i in range(1, 51):
        problem = PLANTED.get(i, "none")
        if problem == "duplicate":
            printed = dict(originals[DUPLICATE_OF[i]], index=i)  # same supplier + number, re-sent as a new file
        else:
            if i <= 38:
                code = PDF_SUPPLIERS[(i - 1) % len(PDF_SUPPLIERS)]
            elif i <= 46:
                code = ["NAD", "WMR"][i % 2]
            else:
                code = ["DBP", "OPS", "MCS", "GGB"][i % 4]
            invoice = make_invoice(rng, i, code)
            originals[i] = invoice
            printed = plant_problem(invoice, problem, rng)
        if i <= 38:
            name = f"inv-{i:03d}.pdf"
            note = "REMINDER - COPY OF INVOICE" if problem == "duplicate" else ""
            write_pdf(files_dir / name, invoice_lines(printed, note))
        else:
            name = f"inv-{i:03d}.txt"
            if printed["lang"] == "ar":
                lines = arabic_lines(printed, arabic_digits=i in (45, 46))
            else:
                lines = email_lines(printed)
            (files_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        labels.append({"id": f"inv-{i:03d}", "input": {"file": f"invoices/files/{name}"}, "label": label_for(printed, problem)})
    with (INVOICE_DIR / "labels.jsonl").open("w", encoding="utf-8") as f:
        for row in labels:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- weekly report data

FIRST_MONDAY = date(2025, 9, 29)
N_WEEKS = 51  # week 1 only provides the "previous week" for week 2; reports cover weeks 2-51 (50 reports)
PRIORITY_WEIGHTS = {"P1": 6, "P2": 22, "P3": 47, "P4": 25}
SLA = {"P1": 60, "P2": 240, "P3": 1440, "P4": 2880}
TEAMS = ["Technical", "Billing", "Delivery", "Product", "Account"]
CATEGORIES = {"sales": 30, "support": 25, "complaint": 15, "partnership": 10, "spam": 20}


def half_up(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def timestamp_in_week(rng: random.Random, monday: date, boundary: str = "") -> str:
    if boundary == "start":
        moment = datetime.combine(monday, datetime.min.time())
    elif boundary == "end":
        moment = datetime.combine(monday + timedelta(days=6), datetime.max.time()).replace(microsecond=0)
    else:
        moment = datetime.combine(monday, datetime.min.time()) + timedelta(seconds=rng.randint(0, 7 * 86400 - 1))
    return moment.isoformat() + "+04:00"


def generate_weekly(rng: random.Random) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    tickets, enquiries, truth = [], [], []
    for w in range(N_WEEKS):
        monday = FIRST_MONDAY + timedelta(weeks=w)
        n = rng.randint(25, 70)
        counts = {p: 0 for p in SLA}
        teams = {t: 0 for t in TEAMS}
        negatives = breaches = minutes_total = 0
        for k in range(n):
            priority = rng.choices(list(PRIORITY_WEIGHTS), weights=list(PRIORITY_WEIGHTS.values()))[0]
            team = rng.choice(TEAMS)
            negative_share = {"P1": 0.9, "P2": 0.7, "P3": 0.3, "P4": 0.1}[priority]
            sentiment = "negative" if rng.random() < negative_share else rng.choice(["neutral", "positive"])
            breach = rng.random() < 0.15
            minutes = rng.randint(SLA[priority] + 1, SLA[priority] * 3) if breach else rng.randint(1, SLA[priority])
            boundary = "start" if k == 0 and w % 3 == 0 else ("end" if k == 1 and w % 4 == 0 else "")
            tickets.append({
                "ticket_id": f"W{w:02d}-{k:03d}", "created_at": timestamp_in_week(rng, monday, boundary),
                "priority": priority, "team": team, "sentiment": sentiment,
                "first_response_minutes": minutes, "status": rng.choice(["resolved", "resolved", "open"]),
            })  # fmt: skip
            counts[priority] += 1
            teams[team] += 1
            negatives += sentiment == "negative"
            breaches += breach
            minutes_total += minutes
        m = rng.randint(15, 45)
        by_cat = {c: 0 for c in CATEGORIES}
        for k in range(m):
            category = rng.choices(list(CATEGORIES), weights=list(CATEGORIES.values()))[0]
            enquiries.append(
                {"enquiry_id": f"E{w:02d}-{k:03d}", "received_at": timestamp_in_week(rng, monday), "category": category}
            )
            by_cat[category] += 1
        truth.append({"week_start": monday.isoformat(), "week_end": (monday + timedelta(days=6)).isoformat(),
                      "tickets_total": n, "tickets_by_priority": counts, "tickets_by_team": teams,
                      "negatives": negatives, "breaches": breaches, "minutes_total": minutes_total,
                      "enquiries_total": m, "enquiries_by_category": by_cat})  # fmt: skip

    rng.shuffle(tickets)  # row order must not matter
    rng.shuffle(enquiries)
    write_csv(REPORT_DIR / "tickets.csv", tickets)
    write_csv(REPORT_DIR / "enquiries.csv", enquiries)
    with (REPORT_DIR / "weeks.jsonl").open("w", encoding="utf-8") as f:
        for prev, cur in zip(truth, truth[1:]):
            f.write(json.dumps({"id": f"week-{cur['week_start']}", "input": {"week_start": cur["week_start"]},
                                "label": expected_numbers(cur, prev)}) + "\n")  # fmt: skip


def expected_numbers(cur: dict, prev: dict) -> dict:
    """Ground truth, counted while generating (independent of the report code)."""
    n, prev_n = cur["tickets_total"], prev["tickets_total"]
    change = half_up(Decimal(abs(n - prev_n)) * 100 / Decimal(prev_n)) * (-1 if n < prev_n else 1)
    return {
        "week_start": cur["week_start"],
        "week_end": cur["week_end"],
        "tickets_total": n,
        "tickets_prev_week": prev_n,
        "tickets_change_pct": change,
        "tickets_by_priority": cur["tickets_by_priority"],
        "tickets_by_team": cur["tickets_by_team"],
        "negative_sentiment_pct": half_up(Decimal(cur["negatives"]) * 100 / n),
        "avg_first_response_minutes": half_up(Decimal(cur["minutes_total"]) / n),
        "sla_breaches": cur["breaches"],
        "enquiries_total": cur["enquiries_total"],
        "enquiries_by_category": cur["enquiries_by_category"],
        "spam_pct": half_up(Decimal(cur["enquiries_by_category"]["spam"]) * 100 / cur["enquiries_total"]),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    rng = random.Random(SEED)
    generate_invoices(rng)
    generate_weekly(rng)
    print("wrote", INVOICE_DIR, "and", REPORT_DIR)
