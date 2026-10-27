"""Generate a PDF of personalized outreach drafts (for manual sending)."""
from fpdf import FPDF


def _clean(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\u2014", "-").replace("\u2013", "-")  # em/en dash
    s = s.replace("\u2018", "'").replace("\u2019", "'")  # curly quotes
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2026", "...")
    s = s.replace("\u00a0", " ")
    return s.encode("ascii", "replace").decode("ascii")


def build_pdf(drafts: list[dict]) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "lead_er - Outreach Drafts", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"{len(drafts)} leads", ln=1)
    pdf.ln(4)

    for i, d in enumerate(drafts, 1):
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, _clean(f"{i}. {d.get('business_name', '')}"), ln=1)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, _clean(f"To: {d.get('email', '')}"), ln=1)
        pdf.cell(0, 6, _clean(f"Subject: {d.get('subject', '')}"), ln=1)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, _clean(d.get("body", "")))
        pdf.ln(3)
        y = pdf.get_y()
        pdf.set_draw_color(180, 180, 180)
        pdf.line(10, y, 200, y)
        pdf.ln(6)

    return bytes(pdf.output())
