"""Generate the sample KFS PDFs (build plan §7.2, phase 2).

A Key Fact Statement is what the RBI requires a lender to hand a borrower before
they sign: one document, prescribed order, every charge named. The demo needs
real-looking ones for three reasons - the app opens them in a PDF viewer, their
SHA-256 is check #4 of receipt verification (§11.3), and phase 11 feeds them back
through Sarvam Document Intelligence to prove the extraction works on a document
nobody tuned it against.

Every page is watermarked SAMPLE and every contact detail is fictional, so a
printout cannot be mistaken for a real lender's paperwork.

Run with `make seed` (which calls this) or directly:

    backend/.venv/bin/python backend/scripts/generate_kfs_pdf.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.journey.loan_math import quote  # noqa: E402

OUT_DIR = BACKEND_DIR / "app" / "assets" / "kfs"
SEED_DIR = BACKEND_DIR / "app" / "seed" / "data"

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

NAVY = colors.HexColor("#002E6E")
GREY = colors.HexColor("#6B7280")
RED = colors.HexColor("#D92D20")
RULE = colors.HexColor("#D1D5DB")


def rupees(value: int | float) -> str:
    """Indian digit grouping: 1,00,000 rather than 100,000."""
    whole = round(value)
    text = str(abs(whole))
    if len(text) > 3:
        head, tail = text[:-3], text[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        text = ",".join(parts) + "," + tail
    return ("-" if whole < 0 else "") + text


class KfsPage:
    """Thin layout helper over the reportlab canvas.

    `self.y` is the current baseline, moving down the page; every writer returns
    after advancing it, so sections compose without any absolute coordinates.
    """

    def __init__(self, pdf: canvas.Canvas) -> None:
        self.pdf = pdf
        self.y = PAGE_H - MARGIN

    def watermark(self) -> None:
        """Diagonal SAMPLE across the page, drawn first so text sits on top."""
        self.pdf.saveState()
        self.pdf.setFont("Helvetica-Bold", 86)
        self.pdf.setFillColor(colors.HexColor("#E5E7EB"))
        self.pdf.translate(PAGE_W / 2, PAGE_H / 2)
        self.pdf.rotate(38)
        self.pdf.drawCentredString(0, -20, "SAMPLE")
        self.pdf.restoreState()

    def heading(self, lender: str, version: str) -> None:
        self.pdf.setFillColor(NAVY)
        self.pdf.setFont("Helvetica-Bold", 15)
        self.pdf.drawString(MARGIN, self.y, "KEY FACT STATEMENT (KFS)")
        self.pdf.setFont("Helvetica", 9)
        self.pdf.setFillColor(GREY)
        self.y -= 14
        self.pdf.drawString(MARGIN, self.y, f"{lender}  ·  Personal loan  ·  {version}")
        self.y -= 6
        self.rule()
        self.y -= 12

    def rule(self) -> None:
        self.pdf.setStrokeColor(RULE)
        self.pdf.setLineWidth(0.6)
        self.pdf.line(MARGIN, self.y, PAGE_W - MARGIN, self.y)

    def section(self, title: str) -> None:
        self.pdf.setFillColor(NAVY)
        self.pdf.setFont("Helvetica-Bold", 10.5)
        self.y -= 6
        self.pdf.drawString(MARGIN, self.y, title.upper())
        self.y -= 12

    def row(self, label: str, value: str, *, emphasis: bool = False) -> None:
        """A label/value line. `emphasis` is for the figures that cost money."""
        self.pdf.setFont("Helvetica", 9.5)
        self.pdf.setFillColor(colors.HexColor("#3A3A3C"))
        self.pdf.drawString(MARGIN + 2, self.y, label)
        self.pdf.setFont("Helvetica-Bold" if emphasis else "Helvetica", 9.5)
        self.pdf.setFillColor(RED if emphasis else colors.HexColor("#1C1C1E"))
        self.pdf.drawRightString(PAGE_W - MARGIN - 2, self.y, value)
        self.y -= 14

    def paragraph(self, title: str, body: str) -> None:
        """A clause: bold title, then the text wrapped to the column width."""
        self.pdf.setFont("Helvetica-Bold", 9.5)
        self.pdf.setFillColor(NAVY)
        self.pdf.drawString(MARGIN + 2, self.y, title)
        self.y -= 12

        self.pdf.setFont("Helvetica", 9)
        self.pdf.setFillColor(colors.HexColor("#3A3A3C"))
        for line in self._wrap(body, PAGE_W - 2 * MARGIN - 4, "Helvetica", 9):
            self.pdf.drawString(MARGIN + 2, self.y, line)
            self.y -= 11
        self.y -= 6

    def _wrap(self, text: str, width: float, font: str, size: float) -> list[str]:
        lines: list[str] = []
        current = ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if self.pdf.stringWidth(candidate, font, size) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def footer(self, page_no: int, total: int, grievance: str) -> None:
        self.pdf.setFont("Helvetica", 7.5)
        self.pdf.setFillColor(GREY)
        self.pdf.drawString(
            MARGIN,
            MARGIN - 6,
            "SAMPLE document for a concept demonstration. Not a real loan offer. "
            "All lender details are fictional.",
        )
        self.pdf.drawRightString(PAGE_W - MARGIN, MARGIN - 6, f"Page {page_no} of {total}")
        self.pdf.setFillColor(GREY)
        self.pdf.drawString(MARGIN, MARGIN + 6, f"Grievance: {grievance}")


def build_pdf(path: Path, lender: dict, offer: dict, facts: dict, clauses: list[dict]) -> None:
    """Write a two-page KFS: the prescribed facts table, then the clauses."""
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setTitle(f"Key Fact Statement - {lender['name']} - {facts['kfs_version']}")
    pdf.setAuthor("Spasht concept demo (synthetic)")
    pdf.setSubject("SAMPLE Key Fact Statement, not a real loan offer")

    # --- page 1: the facts table, in the RBI's order --------------------
    page = KfsPage(pdf)
    page.watermark()
    page.heading(lender["name"], facts["kfs_version"])

    page.section("1. Loan details")
    page.row("Loan amount sanctioned", f"INR {rupees(facts['principal'])}")
    page.row(
        "Processing fee",
        f"INR {rupees(facts['processing_fee'])}",
        emphasis=facts["processing_fee"] > 0,
    )
    page.row("GST on processing fee", f"INR {rupees(facts['gst'])}")
    page.row(
        "Net amount credited to borrower",
        f"INR {rupees(facts['net_disbursed'])}",
        emphasis=facts["net_disbursed"] < facts["principal"],
    )
    page.row("Tenure", f"{facts['tenure_months']} months")

    page.section("2. Interest and annual percentage rate")
    page.row("Rate of interest (per annum)", f"{facts['rate_pa']:.2f}%  (reducing balance)")
    page.row(
        "Annual Percentage Rate (APR), all-inclusive",
        f"{facts['apr']:.2f}%",
        emphasis=True,
    )

    page.section("3. Repayment")
    page.row("Monthly instalment (EMI)", f"INR {rupees(facts['emi'])}", emphasis=True)
    page.row("Number of instalments", str(facts["tenure_months"]))
    page.row("Total interest payable", f"INR {rupees(facts['total_interest'])}")
    page.row("Total amount repayable", f"INR {rupees(facts['total_repay'])}", emphasis=True)
    page.row(
        "Total cost of credit to borrower", f"INR {rupees(facts['total_cost'])}", emphasis=True
    )
    page.row("Repayment mode", "UPI AutoPay mandate, 5th of each month")

    page.section("4. Other charges and rights")
    page.row(
        "Late payment charge, per instalment", f"INR {rupees(facts['late_fee'])}", emphasis=True
    )
    page.row("Foreclosure charge", f"{facts['foreclosure_pct']:.0f}% of principal outstanding")
    page.row("Cooling-off / look-up period", f"{facts['cooling_off_days']} days")
    page.row(
        "Credit-life insurance",
        f"OPTIONAL · one-time INR {rupees(facts['insurance_premium'])}",
    )
    page.row("Lender registration (sample)", lender["reg_no_sample"])

    page.footer(1, 2, lender["grievance_contact_sample"])
    pdf.showPage()

    # --- page 2: the clauses, which phase 8 searches --------------------
    page = KfsPage(pdf)
    page.watermark()
    page.heading(lender["name"], facts["kfs_version"])
    page.section("5. Terms and conditions")
    for clause in clauses:
        page.paragraph(clause["title"], clause["text_en"])
    page.footer(2, 2, lender["grievance_contact_sample"])

    pdf.save()


def render_clauses(clause_templates: list[dict], facts: dict, lender: dict) -> list[dict]:
    """Fill the `{PLACEHOLDER}`s of each clause template from this offer's facts.

    One template set serves every offer, so a wording improvement lands in all
    three PDFs at once and cannot drift between them.
    """
    values = {
        "PRINCIPAL": rupees(facts["principal"]),
        "TENURE": facts["tenure_months"],
        "EMI": rupees(facts["emi"]),
        "TOTAL_REPAY": rupees(facts["total_repay"]),
        "TOTAL_INTEREST": rupees(facts["total_interest"]),
        "RATE_PA": f"{facts['rate_pa']:.2f}",
        "APR": f"{facts['apr']:.2f}",
        "PROCESSING_FEE": rupees(facts["processing_fee"]),
        "GST": rupees(facts["gst"]),
        "NET_DISBURSED": rupees(facts["net_disbursed"]),
        "LATE_FEE": rupees(facts["late_fee"]),
        "FORECLOSURE_PCT": f"{facts['foreclosure_pct']:.0f}",
        "COOLING_OFF_DAYS": facts["cooling_off_days"],
        "INSURANCE_PREMIUM": rupees(facts["insurance_premium"]),
        "LENDER": lender["name"],
        "GRIEVANCE": lender["grievance_contact_sample"],
    }
    rendered = []
    for template in clause_templates:
        text = template["text_en"]
        for key, value in values.items():
            text = text.replace("{" + key + "}", str(value))
        rendered.append(
            {
                "clause_key": template["clause_key"],
                "title": template["title"],
                "text_en": text,
            }
        )
    return rendered


def facts_for(offer: dict) -> dict:
    """The complete, machine-readable fact set for one offer.

    This dict is the Number Guard's allow-list (§10.5) and the source of every
    `{PLACEHOLDER}` in a template or question, so it is computed from
    `loan_math` rather than read from the seed file - the database and the
    arithmetic cannot disagree.
    """
    priced = quote(
        offer["principal"],
        float(offer["rate_pa"]),
        offer["tenure_months"],
        offer["processing_fee"],
        offer["gst_on_fee"],
    )
    return {
        "principal": priced.principal,
        "tenure_months": priced.tenure_months,
        "rate_pa": float(offer["rate_pa"]),
        "processing_fee": priced.processing_fee,
        "gst": priced.gst_on_fee,
        "net_disbursed": priced.net_disbursed,
        "emi": priced.emi,
        "total_repay": priced.total_repay,
        "total_interest": priced.total_interest,
        "total_cost": priced.total_cost,
        "apr": priced.apr,
        "late_fee": offer["late_fee"],
        "foreclosure_pct": float(offer["foreclosure_pct"]),
        "cooling_off_days": offer["cooling_off_days"],
        "insurance_optional": True,
        "insurance_premium": offer["insurance_premium"],
        "kfs_version": offer["kfs_version"],
    }


def generate_all() -> list[dict]:
    """Write one PDF per offer. Returns a descriptor per document.

    The SHA-256 is of the file on disk, so the hash stored with the KFS document
    row is the hash of exactly the bytes the customer can open.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((SEED_DIR / "offers.json").read_text(encoding="utf-8"))
    lenders = {entry["id"]: entry for entry in catalog["lenders"]}

    documents = []
    for offer in catalog["offers"]:
        lender = lenders[offer["lender_id"]]
        facts = facts_for(offer)
        clauses = render_clauses(catalog["clauses"], facts, lender)

        path = OUT_DIR / f"kfs_{offer['id']}_{facts['kfs_version']}.pdf"
        build_pdf(path, lender, offer, facts, clauses)

        documents.append(
            {
                "offer_id": offer["id"],
                "lender_id": lender["id"],
                "version": facts["kfs_version"],
                "file_path": str(path.relative_to(BACKEND_DIR)),
                "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "facts": facts,
                "clauses": clauses,
            }
        )
    return documents


if __name__ == "__main__":
    for doc in generate_all():
        print(f"  {doc['file_path']}  sha256={doc['file_sha256'][:12]}...")
