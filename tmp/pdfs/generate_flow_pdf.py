from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


OUT = Path("output/pdf/DigitalPTT_SYSTEM_FLOW_DIAGRAMS.pdf")
W, H = landscape(A3)

INK = colors.HexColor("#10203F")
MUTED = colors.HexColor("#5C6F8D")
LINE = colors.HexColor("#CBD5E1")
BLUE = colors.HexColor("#146BFF")
BLUE_SOFT = colors.HexColor("#EAF2FF")
GREEN = colors.HexColor("#168647")
GREEN_SOFT = colors.HexColor("#E5F7EC")
AMBER = colors.HexColor("#B35C00")
AMBER_SOFT = colors.HexColor("#FFF3D8")
RED = colors.HexColor("#B42318")
RED_SOFT = colors.HexColor("#FEECEB")
SLATE = colors.HexColor("#F8FAFC")


def wrap(text, font, size, width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def text(c, value, x, y, width, size=7.4, bold=False, color=INK, leading=None, align="left"):
    font = "Helvetica-Bold" if bold else "Helvetica"
    leading = leading or size * 1.25
    c.setFillColor(color)
    c.setFont(font, size)
    lines = wrap(value, font, size, width)
    for index, line in enumerate(lines):
        yy = y - index * leading
        if align == "center":
            c.drawCentredString(x + width / 2, yy, line)
        else:
            c.drawString(x, yy, line)
    return len(lines) * leading


def rounded_box(c, title, detail, x, y, w, h, fill=SLATE, border=LINE):
    c.setFillColor(fill)
    c.setStrokeColor(border)
    c.roundRect(x, y, w, h, 7, fill=1, stroke=1)
    text(c, title, x + 9, y + h - 16, w - 18, 8.2, True)
    text(c, detail, x + 9, y + h - 30, w - 18, 6.8, False, MUTED, 8.2)


def diamond(c, label, x, y, size=76):
    cx, cy, half = x + size / 2, y + size / 2, size / 2
    p = c.beginPath()
    p.moveTo(cx, y + size)
    p.lineTo(x + size, cy)
    p.lineTo(cx, y)
    p.lineTo(x, cy)
    p.close()
    c.setFillColor(BLUE_SOFT)
    c.setStrokeColor(BLUE)
    c.drawPath(p, fill=1, stroke=1)
    text(c, label, x + 10, cy + 3, size - 20, 7.1, True, INK, 8, "center")


def arrow(c, x1, y1, x2, y2, label=None):
    c.setStrokeColor(BLUE)
    c.setLineWidth(1)
    c.line(x1, y1, x2, y2)
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5 or 1
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    ah = 5
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - ah * ux + 2.4 * px, y2 - ah * uy + 2.4 * py)
    p.lineTo(x2 - ah * ux - 2.4 * px, y2 - ah * uy - 2.4 * py)
    p.close()
    c.setFillColor(BLUE)
    c.drawPath(p, fill=1, stroke=0)
    if label:
        text(c, label, (x1 + x2) / 2 - 16, (y1 + y2) / 2 + 4, 36, 6.2, True, BLUE, 7, "center")


def header(c, title, subtitle, historical=False):
    c.setFillColor(colors.HexColor("#FFF7ED") if historical else colors.white)
    c.rect(0, H - 86, W, 86, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#F2B879") if historical else LINE)
    c.line(0, H - 86, W, H - 86)
    text(c, title, 36, H - 36, 660, 22, True)
    text(c, subtitle, 36, H - 58, 900, 9, False, AMBER if historical else MUTED)
    if historical:
        rounded_box(c, "HISTORICAL REFERENCE", "Earlier design state - not current policy", W - 315, H - 62, 275, 38, AMBER_SOFT, colors.HexColor("#F2B879"))
    else:
        rounded_box(c, "CURRENT POLICY", "Verified payment is required before provisioning", W - 315, H - 62, 275, 38, GREEN_SOFT, colors.HexColor("#B6E7C8"))


def lane(c, number, title, y, height):
    c.setFillColor(colors.white)
    c.setStrokeColor(LINE)
    c.roundRect(32, y, W - 64, height, 9, fill=1, stroke=1)
    text(c, f"{number}. {title}", 48, y + height - 16, 800, 8.6, True, MUTED)


def current_page(c):
    header(c, "Digital PTT - Current Operational Flow", "Current product behavior and operational policy | Updated 27 Aug 2026")
    lane(c, "1", "Customer identity and quote access", 680, 108)
    rounded_box(c, "Visitor", "Browse catalog or begin a quote", 55, 702, 130, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 185, 729, 212, 729)
    diamond(c, "Signed in?", 217, 691, 70)
    arrow(c, 287, 727, 322, 727, "Yes")
    rounded_box(c, "Client account", "Authenticated workspace", 327, 702, 150, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 252, 691, 252, 655, "No")
    rounded_box(c, "Guest quote", "Submit with contact email", 195, 592, 150, 54, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    arrow(c, 345, 619, 377, 619)
    rounded_box(c, "7-day secure claim", "Same email signs in or registers", 382, 592, 176, 54, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    arrow(c, 558, 619, 589, 619)
    diamond(c, "Matching email?", 594, 581, 78)
    arrow(c, 672, 620, 708, 620, "Yes")
    rounded_box(c, "Claim quote + order", "Attach private quote to account", 713, 592, 178, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    rounded_box(c, "Different email", "Quote remains private", 713, 534, 178, 42, RED_SOFT, colors.HexColor("#F5B5B0"))
    arrow(c, 633, 581, 760, 576, "No")

    lane(c, "2", "Organization ownership before license purchase", 544, 120)
    rounded_box(c, "Select organization", "Client chooses the purchasing workspace", 55, 568, 170, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 225, 595, 254, 595)
    diamond(c, "Organization?", 259, 557, 76)
    arrow(c, 335, 604, 372, 604, "One")
    rounded_box(c, "Selected organization", "Existing active organization", 377, 568, 170, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 335, 575, 372, 546, "Many")
    rounded_box(c, "Client chooses one", "That organization owns capacity", 377, 501, 170, 48, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 547, 595, 578, 595, "None")
    rounded_box(c, "Create organization", "Owner creates active workspace", 583, 568, 170, 54, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    arrow(c, 753, 595, 785, 595)
    rounded_box(c, "Active organization", "Owner assigned; purchases allowed", 790, 568, 170, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    rounded_box(c, "Staff creates organization", "Select or invite Owner", 1000, 568, 170, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 1170, 595, 1200, 595, "Unknown")
    rounded_box(c, "Draft organization", "No licenses, orders or payments", 1205, 568, 175, 54, RED_SOFT, colors.HexColor("#F5B5B0"))

    lane(c, "3", "Catalog, capacity and checkout", 398, 120)
    rounded_box(c, "Browse catalog", "Physical, licensed or quote-only products", 55, 422, 165, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 220, 449, 249, 449)
    rounded_box(c, "Cart validation", "Server checks price, stock and capacity", 254, 422, 185, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 439, 449, 470, 449)
    diamond(c, "Capacity sufficient?", 475, 411, 82)
    arrow(c, 557, 456, 594, 456, "Yes")
    rounded_box(c, "Checkout ready", "Compatible capacity covers products", 599, 422, 175, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 516, 411, 600, 383, "No")
    rounded_box(c, "Add uncovered license units", "Only capacity not already covered", 605, 329, 200, 48, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    arrow(c, 774, 449, 806, 449)
    rounded_box(c, "Checkout decision", "Quote or pay now", 811, 422, 158, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))

    lane(c, "4", "Payment paths - payment completes only after verification", 214, 162)
    rounded_box(c, "Quote path", "Staff prices and issues invoice", 55, 260, 150, 54, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    arrow(c, 205, 287, 235, 287)
    rounded_box(c, "Bank transfer invoice", "Bank details + required reference", 240, 260, 180, 54, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    arrow(c, 420, 287, 450, 287)
    rounded_box(c, "Admin reconciliation", "Match statement and confirm", 455, 260, 180, 54, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    arrow(c, 635, 287, 665, 287)
    rounded_box(c, "Verified payment", "One successful payment event", 670, 260, 165, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    rounded_box(c, "Pay now path", "Pending direct order", 55, 187, 150, 46, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 205, 210, 235, 210)
    rounded_box(c, "Online provider", "Simulator now; live provider later", 240, 187, 180, 46, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 420, 210, 450, 210)
    rounded_box(c, "Verified callback", "Signature, amount and reference checked", 455, 187, 195, 46, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    text(c, "Failed, cancelled or expired: retry only; no provisioning", 680, 202, 360, 7.2, True, RED)

    lane(c, "5", "Provisioning, renewals and automated notices", 42, 150)
    rounded_box(c, "Verified payment", "Idempotent payment success", 55, 78, 150, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 205, 105, 235, 105)
    rounded_box(c, "Physical", "Reserve stock; schedule, process and consume once", 240, 78, 178, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 418, 105, 448, 105)
    rounded_box(c, "License", "Create / allocate capacity; immutable event", 453, 78, 178, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 631, 105, 661, 105)
    rounded_box(c, "Notify", "In-app notice + queued email", 666, 78, 150, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    rounded_box(c, "Renew exact license", "Eligible owner/manager begins private renewal", 890, 78, 190, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 1080, 105, 1110, 105, "Paid")
    rounded_box(c, "Renewal completed", "Exact license dates extended", 1115, 78, 175, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    rounded_box(c, "Daily reconciliation", "Updates expiry and 60/30/7/due/overdue reminders", 55, 142, 260, 36, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    arrow(c, 315, 160, 345, 160)
    rounded_box(c, "Owners and managers", "In-app notice + queued email with retry", 350, 142, 225, 36, AMBER_SOFT, colors.HexColor("#FFE0A1"))


def historical_page(c):
    header(c, "Digital PTT - Historical Detailed Flow", "Earlier 24 Aug 2026 workflow - retained for traceability only", historical=True)
    lane(c, "1", "Entry and earlier account workspace flow", 650, 136)
    rounded_box(c, "Visitor / customer", "Browse catalog", 55, 694, 150, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 205, 721, 237, 721)
    diamond(c, "Signed in?", 242, 683, 76)
    arrow(c, 318, 726, 355, 726, "Yes")
    rounded_box(c, "Organization selected?", "Default workspace used when absent", 360, 694, 200, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 560, 721, 590, 721)
    rounded_box(c, "Store / catalog", "Product type determines next path", 595, 694, 175, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 280, 683, 280, 642, "No")
    rounded_box(c, "Register or sign in", "Earlier direct account path", 205, 576, 170, 54, AMBER_SOFT, colors.HexColor("#FFE0A1"))

    lane(c, "2", "Earlier catalogue and quote/order creation", 488, 138)
    rounded_box(c, "Physical / license / quote", "Product classification", 55, 532, 180, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 235, 559, 265, 559)
    rounded_box(c, "Cart", "Stock, price and capacity checks", 270, 532, 170, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 440, 559, 470, 559)
    rounded_box(c, "Cart ready", "Earlier flow auto-added a required license", 475, 532, 200, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 675, 559, 705, 559)
    diamond(c, "Pay or quote?", 710, 521, 76)
    arrow(c, 786, 570, 825, 570, "Quote")
    rounded_box(c, "Staff review and invoice", "Invoice creates pending quote order", 830, 532, 200, 54, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    arrow(c, 786, 540, 825, 504, "Pay")
    rounded_box(c, "Pending direct order", "Normal payment session", 830, 444, 185, 46, BLUE_SOFT, colors.HexColor("#B7D2FF"))

    lane(c, "3", "Earlier payment, fulfillment and licensing", 315, 138)
    rounded_box(c, "Provider bank handoff", "Earlier simulator / provider return", 55, 359, 190, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 245, 386, 275, 386)
    diamond(c, "Confirmed?", 280, 348, 76)
    arrow(c, 356, 392, 395, 392, "Yes")
    rounded_box(c, "Payment success", "Transactional provisioning", 400, 359, 170, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 570, 386, 600, 386)
    rounded_box(c, "Physical order", "Scheduled -> processing -> shipment", 605, 359, 200, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    rounded_box(c, "License order", "Find/create org -> license -> allocation", 830, 359, 210, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 318, 348, 318, 306, "No")
    rounded_box(c, "Failed / expired", "No provisioning", 250, 250, 150, 46, RED_SOFT, colors.HexColor("#F5B5B0"))

    lane(c, "4", "Earlier renewals, team control and staff operations", 138, 140)
    rounded_box(c, "Owner / manager", "Select license -> eligible -> extend", 55, 180, 200, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 255, 207, 285, 207)
    rounded_box(c, "Provider payment", "Success creates completed renewal order", 290, 180, 210, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    arrow(c, 500, 207, 530, 207)
    rounded_box(c, "Renewal event", "Earlier expiry reminder state", 535, 180, 175, 54, GREEN_SOFT, colors.HexColor("#B6E7C8"))
    rounded_box(c, "Owner team controls", "Invite manager / transfer ownership", 770, 180, 200, 54, BLUE_SOFT, colors.HexColor("#B7D2FF"))
    arrow(c, 970, 207, 1000, 207)
    rounded_box(c, "Staff license management", "Filter org -> adjustment / reminder", 1005, 180, 210, 54, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    rounded_box(c, "Daily expiry checks", "60 / 30 / 7 / due / overdue notices", 55, 76, 220, 44, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    arrow(c, 275, 98, 305, 98)
    rounded_box(c, "Owners and managers", "Earlier notice and email behavior", 310, 76, 200, 44, AMBER_SOFT, colors.HexColor("#FFE0A1"))
    text(c, "Historical note: this design predates secure guest-quote claims, explicit organization selection, bank-transfer reconciliation controls, and verified-payment-only provisioning.", 36, 28, W - 72, 8, True, MUTED)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=landscape(A3), pageCompression=1)
    current_page(c)
    c.showPage()
    historical_page(c)
    c.save()


if __name__ == "__main__":
    main()
