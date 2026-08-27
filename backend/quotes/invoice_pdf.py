from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _font_name() -> str:
    candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for path in candidates:
        if path.exists():
            pdfmetrics.registerFont(TTFont("DigitalPTTUnicode", str(path)))
            return "DigitalPTTUnicode"
    return "Helvetica"


def build_invoice_pdf(*, quote_request, site_settings) -> bytes:
    output = BytesIO()
    font = _font_name()
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "InvoiceBody",
        parent=styles["BodyText"],
        fontName=font,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#344054"),
    )
    small = ParagraphStyle("InvoiceSmall", parent=body, fontSize=8, leading=11)
    table_header = ParagraphStyle(
        "InvoiceTableHeader",
        parent=small,
        textColor=colors.white,
    )
    heading = ParagraphStyle(
        "InvoiceHeading",
        parent=styles["Heading1"],
        fontName=font,
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#071a36"),
    )
    amount = ParagraphStyle("InvoiceAmount", parent=body, alignment=TA_RIGHT)
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Invoice {quote_request.invoice_number}",
        author=site_settings.site_name,
    )

    story = [
        Table(
            [[Paragraph(f"<b>{site_settings.site_name}</b>", heading), Paragraph("INVOICE", heading)]],
            colWidths=[110 * mm, 50 * mm],
            style=TableStyle([
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]),
        ),
        Table(
            [[
                Paragraph(
                    f"<b>Bill to</b><br/>{escape(quote_request.requester_contact_person)}<br/>"
                    f"{escape(quote_request.requester_company_name or '')}<br/>"
                    f"{escape(quote_request.requester_email)}<br/>{escape(quote_request.requester_phone or '')}",
                    body,
                ),
                Paragraph(
                    f"<b>Invoice number</b><br/>{quote_request.invoice_number}<br/><br/>"
                    f"<b>Issue date</b><br/>{quote_request.invoiced_at:%Y-%m-%d}<br/><br/>"
                    f"<b>Reference</b><br/>{quote_request.quote_number}",
                    amount,
                ),
            ]],
            colWidths=[105 * mm, 55 * mm],
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8dee9")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f7fb")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]),
        ),
        Spacer(1, 8 * mm),
    ]

    currency = site_settings.default_currency or "USD"
    rows = [[
        Paragraph("<b>Product</b>", table_header),
        Paragraph("<b>SKU</b>", table_header),
        Paragraph("<b>Qty</b>", ParagraphStyle("InvoiceTableHeaderRight", parent=table_header, alignment=TA_RIGHT)),
        Paragraph("<b>Unit price</b>", ParagraphStyle("InvoiceTableHeaderRight2", parent=table_header, alignment=TA_RIGHT)),
        Paragraph("<b>Total</b>", ParagraphStyle("InvoiceTableHeaderRight3", parent=table_header, alignment=TA_RIGHT)),
    ]]
    for item in quote_request.items.all():
        rows.append([
            Paragraph(escape(item.product_name), body),
            Paragraph(escape(item.sku or "-"), small),
            Paragraph(str(item.quantity), amount),
            Paragraph(f"{currency} {item.quoted_unit_price:,.2f}", amount),
            Paragraph(f"{currency} {item.quoted_line_total:,.2f}", amount),
        ])
    items_table = Table(rows, colWidths=[63 * mm, 27 * mm, 15 * mm, 27 * mm, 28 * mm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2b55")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d8dee9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([items_table, Spacer(1, 5 * mm)])

    totals = Table([
        [Paragraph("Subtotal", body), Paragraph(f"{currency} {quote_request.quoted_subtotal:,.2f}", amount)],
        [Paragraph("Shipping / fees", body), Paragraph(f"{currency} {quote_request.quoted_shipping:,.2f}", amount)],
        [Paragraph("<b>Amount due</b>", body), Paragraph(f"<b>{currency} {quote_request.quoted_total:,.2f}</b>", amount)],
    ], colWidths=[35 * mm, 38 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#0b2b55")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([totals, Spacer(1, 8 * mm)])

    if quote_request.admin_message:
        story.extend([
            Paragraph("<b>Terms and notes</b>", body),
            Spacer(1, 2 * mm),
            Paragraph(escape(quote_request.admin_message).replace("\n", "<br/>"), body),
            Spacer(1, 6 * mm),
        ])
    # The invoice should only offer a method that is currently enabled for customers.
    from payments.models import PaymentProvider

    bank_transfer_available = PaymentProvider.objects.filter(
        code=PaymentProvider.Code.BANK_TRANSFER,
        is_enabled=True,
        is_customer_available=True,
    ).exists()
    if site_settings.bank_transfer_is_configured and bank_transfer_available:
        bank_rows = [
            [Paragraph("<b>Bank transfer payment instructions</b>", body), ""],
            [Paragraph("Beneficiary", small), Paragraph(escape(site_settings.bank_beneficiary_name), small)],
            [Paragraph("Bank", small), Paragraph(escape(site_settings.bank_name), small)],
            [Paragraph("Account number", small), Paragraph(escape(site_settings.bank_account_number), small)],
        ]
        if site_settings.bank_iban:
            bank_rows.append([Paragraph("IBAN", small), Paragraph(escape(site_settings.bank_iban), small)])
        if site_settings.bank_swift_bic:
            bank_rows.append([Paragraph("SWIFT / BIC", small), Paragraph(escape(site_settings.bank_swift_bic), small)])
        bank_rows.append([
            Paragraph("Required transfer reference", small),
            Paragraph(f"<b>{escape(quote_request.invoice_number)}</b>", small),
        ])
        bank_table = Table(bank_rows, colWidths=[52 * mm, 108 * mm])
        bank_table.setStyle(TableStyle([
            ("SPAN", (0, 0), (1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4ff")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9dbdff")),
            ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#d8dee9")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.extend([bank_table, Spacer(1, 6 * mm)])
        if site_settings.bank_payment_instructions:
            story.extend([
                Paragraph(escape(site_settings.bank_payment_instructions).replace("\n", "<br/>"), small),
                Spacer(1, 4 * mm),
            ])
        closing_copy = (
            f"Use {quote_request.invoice_number} as the transfer reference. "
            f"Contact {site_settings.support_email or 'support'} with questions."
        )
    else:
        closing_copy = (
            f"Payment is confirmed through the Digital PTT customer account. "
            f"Contact {site_settings.support_email or 'support'} with questions."
        )
    story.append(Paragraph(closing_copy, small))
    document.build(story)
    return output.getvalue()
