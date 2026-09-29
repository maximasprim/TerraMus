"""Same reasoning and pattern as apps/api/app/modules/finance/pdf.py's
module docstring: reportlab is already a dependency (requirements.txt,
added for that module), not installable/testable in this sandbox (no
network) - written and statically checked, not run, same caveat this
codebase already carries for its other reportlab usage and its payment
providers. Kept as its own small rendering-only module for the same
reason finance/pdf.py is: no DB session in here, easier to test in
isolation once reportlab can actually be exercised.
"""
import io
from datetime import datetime

from app.modules.billing.models import SubscriptionPayment, SubscriptionTier
from app.modules.identity.models import Organization


def render_subscription_receipt_pdf(
    payment: SubscriptionPayment, tier: SubscriptionTier, organization: Organization,
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=20 * mm, rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReceiptTitle", parent=styles["Title"], fontSize=20, spaceAfter=2 * mm)
    small = styles["Normal"]

    status_label = {
        "successful": "Paid", "failed": "Failed", "pending": "Pending", "initiated": "Initiated",
    }.get(payment.status, payment.status)

    story = [
        Paragraph(organization.name, title_style),
        Paragraph("Subscription payment receipt", styles["Heading2"]),
        Spacer(1, 4 * mm),
        Paragraph(f"Reference: {payment.provider_reference or payment.id}", small),
        Paragraph(f"Date: {payment.initiated_at.strftime('%Y-%m-%d %H:%M')}", small),
        Paragraph(f"Status: {status_label}", small),
        Spacer(1, 6 * mm),
    ]

    table_data = [
        ["Plan", tier.name],
        ["Billing period", "Monthly"],
        ["Amount", f"{payment.currency} {payment.amount:,.2f}"],
        ["Payment method", payment.provider.upper()],
    ]
    if payment.completed_at:
        table_data.append(["Completed", payment.completed_at.strftime("%Y-%m-%d %H:%M")])

    table = Table(table_data, colWidths=[60 * mm, 100 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        "This is an automated receipt. Contact support if any details above look incorrect.",
        small,
    ))

    doc.build(story)
    return buffer.getvalue()
