"""Spec §59: "Generate downloadable PDF" for invoices. This was the one
concrete PDF deliverable the spec names explicitly (as opposed to §44's more
general "reports should support PDF export"), so it's built first and
kept as its own small module rather than folded into service.py - a
rendering concern, not a business-logic one, same reasoning that keeps
public/schemas.py's response shaping separate from public/service.py's
queries.

New dependency: reportlab (added to requirements.txt this session). Not
installable/testable in this sandbox (no network) - same "written and
statically checked, not run" caveat this codebase already applies to the
M-Pesa/Stripe providers and the Dockerfile. `import reportlab` itself would
fail here; nothing in the existing test suite imports this module eagerly
at collection time, so its absence doesn't break anything that already ran.
"""
import io
from datetime import datetime

from app.modules.commerce.models import Order
from app.modules.customers.models import Customer
from app.modules.finance.models import Invoice
from app.modules.identity.models import Organization


def render_invoice_pdf(invoice: Invoice, order: Order, customer: Customer, organization: Organization) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=20 * mm, rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("InvoiceTitle", parent=styles["Title"], fontSize=20, spaceAfter=2 * mm)
    small = styles["Normal"]

    story = [
        Paragraph(organization.name, title_style),
        Paragraph(f"Invoice {invoice.invoice_number}", styles["Heading2"]),
        Spacer(1, 4 * mm),
        Paragraph(f"Bill to: {customer.name}", small),
        Paragraph(customer.email or customer.phone or "", small),
        Paragraph(f"Issued: {invoice.issued_at.strftime('%Y-%m-%d')}", small),
        Paragraph(f"Order: {order.id}", small),
        Spacer(1, 6 * mm),
    ]

    table_data = [["Item", f"Price ({organization.currency})"]]
    for item in order.items:
        table_data.append([f"Animal {item.animal_id}", f"{item.price:,.2f}"])
    table_data.append(["Subtotal", f"{invoice.subtotal:,.2f}"])
    table_data.append([f"Tax", f"{invoice.tax_amount:,.2f}"])
    table_data.append(["Total", f"{invoice.total:,.2f}"])

    table = Table(table_data, colWidths=[110 * mm, 50 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b4332")),  # spec §34's suggested deep forest green
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, -3), (-1, -3), 0.5, colors.grey),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    story.append(table)

    doc.build(story)
    return buffer.getvalue()
