import io
import csv
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        # Decorative border
        self.saveState()
        self.setStrokeColor(colors.HexColor("#1E3A8A"))
        self.setLineWidth(2.5)
        self.rect(25, 25, self._pagesize[0] - 50, self._pagesize[1] - 50)
        self.setLineWidth(0.8)
        self.setStrokeColor(colors.HexColor("#D97706"))
        self.rect(29, 29, self._pagesize[0] - 58, self._pagesize[1] - 58)
        self.restoreState()


def generate_sacramental_certificate(cert_type: str, member: dict, parish: dict = None, diocese: dict = None, issue_date: str = None) -> bytes:
    """
    Generates a beautifully styled Sacramental Certificate PDF.
    cert_type: 'baptism', 'communion', 'confirmation', 'marriage', 'holy_orders'
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    # Custom styles
    diocese_title_style = ParagraphStyle(
        'DioceseTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=17,
        leading=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1E3A8A")
    )

    parish_sub_style = ParagraphStyle(
        'ParishSub',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#374151")
    )

    parish_details_style = ParagraphStyle(
        'ParishDetails',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#6B7280")
    )

    cert_banner_style = ParagraphStyle(
        'CertBanner',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=21,
        leading=26,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#B45309")
    )

    cert_no_style = ParagraphStyle(
        'CertNo',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#4B5563")
    )

    body_lead_style = ParagraphStyle(
        'BodyLead',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=18,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1F2937")
    )

    candidate_name_style = ParagraphStyle(
        'CandidateName',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=25,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1E3A8A")
    )

    details_table_label = ParagraphStyle(
        'DetailsLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#374151")
    )

    details_table_val = ParagraphStyle(
        'DetailsVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#111827")
    )

    story = []

    # Diocese & Parish Header
    diocese_name = (diocese.get("name") if diocese else member.get("diocese_name")) or "CATHOLIC DIOCESE"
    parish_name = (parish.get("name") if parish else member.get("parish_name")) or "Parish Church"
    parish_addr = (parish.get("address") if parish else "") or ""
    parish_phone = (parish.get("phone") if parish else "") or ""
    pastor = (parish.get("pastor") if parish else "") or "Parish Priest"

    story.append(Spacer(1, 15))
    story.append(Paragraph(diocese_name.upper(), diocese_title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(parish_name, parish_sub_style))
    if parish_addr or parish_phone:
        contact_line = " | ".join(filter(None, [parish_addr.strip(), f"Tel: {parish_phone.strip()}" if parish_phone else ""]))
        story.append(Paragraph(contact_line, parish_details_style))
    story.append(Spacer(1, 10))

    # Divider
    story.append(HRFlowable(width="80%", thickness=1.5, color=colors.HexColor("#D97706"), spaceBefore=5, spaceAfter=15))

    # Title mapping
    titles = {
        "baptism": ("CERTIFICATE OF BAPTISM", "BAP"),
        "communion": ("CERTIFICATE OF FIRST HOLY COMMUNION", "FHC"),
        "confirmation": ("CERTIFICATE OF CONFIRMATION", "CNF"),
        "marriage": ("CERTIFICATE OF HOLY MATRIMONY", "MAT"),
        "holy_orders": ("CERTIFICATE OF SACRED ORDINATION", "ORD")
    }
    cert_title, prefix = titles.get(cert_type.lower(), ("SACRAMENTAL CERTIFICATE", "SAC"))
    cert_id = f"{prefix}-{datetime.now().year}-{member.get('id', 0):04d}"

    story.append(Paragraph(cert_title, cert_banner_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"Certificate No: <b>{cert_id}</b>", cert_no_style))
    story.append(Spacer(1, 20))

    # Main certification sentence
    story.append(Paragraph("This is to solemnly certify that", body_lead_style))
    story.append(Spacer(1, 8))
    full_name = f"{member.get('first_name', '')} {member.get('last_name', '')}".strip()
    story.append(Paragraph(full_name, candidate_name_style))
    story.append(Spacer(1, 12))

    # Specific sacrament dates
    sacrament_date = member.get(f"{cert_type.lower()}_date") or "—"
    sacrament_parish = member.get(f"{cert_type.lower()}_parish") or parish_name

    data = [
        [Paragraph("Date of Birth:", details_table_label), Paragraph(member.get("dob") or "—", details_table_val)],
        [Paragraph("Gender:", details_table_label), Paragraph(member.get("gender") or "—", details_table_val)],
        [Paragraph("Parish Affiliation:", details_table_label), Paragraph(parish_name, details_table_val)],
        [Paragraph("Date of Sacrament:", details_table_label), Paragraph(f"<b>{sacrament_date}</b>", details_table_val)],
        [Paragraph("Church of Sacrament:", details_table_label), Paragraph(sacrament_parish, details_table_val)],
    ]

    if cert_type.lower() == "marriage":
        data.append([Paragraph("Sacrament Received:", details_table_label), Paragraph("Holy Matrimony in accordance with Canonical Law", details_table_val)])
    elif cert_type.lower() == "baptism":
        data.append([Paragraph("Sacrament Received:", details_table_label), Paragraph("Baptized in the Name of the Father, and of the Son, and of the Holy Spirit", details_table_val)])

    table = Table(data, colWidths=[160, 320])
    table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
    ]))
    story.append(table)
    story.append(Spacer(1, 25))

    cert_text = "According to the official registers and records of this Parish, the above mentioned information is true and authentic in every detail."
    story.append(Paragraph(cert_text, ParagraphStyle('CertText', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=10, leading=15, alignment=TA_CENTER, textColor=colors.HexColor("#4B5563"))))
    story.append(Spacer(1, 40))

    # Signatures Table
    today_str = issue_date or datetime.now().strftime("%B %d, %Y")
    sig_data = [
        [
            Paragraph(f"<b>Issued on:</b> {today_str}<br/><br/><i>Place: {parish_name}</i>", details_table_val),
            Paragraph("<b>[ PARISH SEAL ]</b><br/><br/>", ParagraphStyle('Seal', alignment=TA_CENTER, fontName='Helvetica-Oblique', fontSize=9, textColor=colors.HexColor("#9CA3AF"))),
            Paragraph(f"<b>{pastor}</b><br/>Parish Priest / Pastor<br/><i>Official Signature</i>", ParagraphStyle('PastorSig', alignment=TA_RIGHT, fontName='Helvetica', fontSize=10, leading=14))
        ]
    ]
    sig_table = Table(sig_data, colWidths=[180, 140, 180])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('ALIGN', (1,0), (1,0), 'CENTER'),
        ('ALIGN', (2,0), (2,0), 'RIGHT'),
    ]))
    story.append(sig_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()


def generate_contribution_receipt(contribution: dict, parish: dict = None, member: dict = None, family: dict = None) -> bytes:
    """
    Generates an official PDF receipt for parish offerings/tithes/subscriptions.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=35, rightMargin=35, topMargin=35, bottomMargin=35)
    styles = getSampleStyleSheet()

    story = []
    parish_name = (parish.get("name") if parish else "") or "Parish Church"
    parish_addr = (parish.get("address") if parish else "") or ""
    receipt_no = contribution.get("receipt_no") or f"RCP-{contribution.get('id', 0):05d}"
    amount = float(contribution.get("amount", 0.0))

    story.append(Paragraph(parish_name.upper(), ParagraphStyle('PTitle', fontName='Helvetica-Bold', fontSize=15, leading=19, alignment=TA_CENTER, textColor=colors.HexColor("#1E3A8A"))))
    if parish_addr:
        story.append(Paragraph(parish_addr, ParagraphStyle('PAddr', fontName='Helvetica', fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#6B7280"))))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#D97706"), spaceBefore=4, spaceAfter=10))

    # Header with Receipt Title and No.
    story.append(Paragraph("OFFICIAL CONTRIBUTION RECEIPT", ParagraphStyle('RTitle', fontName='Helvetica-Bold', fontSize=14, leading=18, alignment=TA_CENTER, textColor=colors.HexColor("#111827"))))
    story.append(Spacer(1, 12))

    payer_name = "Anonymous"
    if member:
        payer_name = f"{member.get('first_name', '')} {member.get('last_name', '')}".strip()
    elif family:
        payer_name = f"Family of {family.get('name', '')}"

    details = [
        [Paragraph("Receipt Number:", ParagraphStyle('B', fontName='Helvetica-Bold', fontSize=10)), Paragraph(f"<b>{receipt_no}</b>", ParagraphStyle('N', fontName='Helvetica', fontSize=10)),
         Paragraph("Date:", ParagraphStyle('B', fontName='Helvetica-Bold', fontSize=10)), Paragraph(contribution.get("payment_date") or datetime.now().strftime("%Y-%m-%d"), ParagraphStyle('N', fontName='Helvetica', fontSize=10))],
        [Paragraph("Received From:", ParagraphStyle('B', fontName='Helvetica-Bold', fontSize=10)), Paragraph(payer_name, ParagraphStyle('N', fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor("#1E3A8A"))),
         Paragraph("Payment Mode:", ParagraphStyle('B', fontName='Helvetica-Bold', fontSize=10)), Paragraph(contribution.get("payment_method") or "Cash", ParagraphStyle('N', fontName='Helvetica', fontSize=10))],
        [Paragraph("Contribution Type:", ParagraphStyle('B', fontName='Helvetica-Bold', fontSize=10)), Paragraph(contribution.get("category") or "General Offering", ParagraphStyle('N', fontName='Helvetica', fontSize=10)),
         Paragraph("Ref / Trans ID:", ParagraphStyle('B', fontName='Helvetica-Bold', fontSize=10)), Paragraph(contribution.get("reference_no") or "—", ParagraphStyle('N', fontName='Helvetica', fontSize=10))],
    ]

    t = Table(details, colWidths=[110, 170, 100, 160])
    t.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F9FAFB")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#F3F4F6")),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))

    # Amount box
    amt_data = [
        [Paragraph(f"AMOUNT RECEIVED: <font size=14 color='#1E3A8A'><b>₹ {amount:,.2f}</b></font>", ParagraphStyle('Amt', fontName='Helvetica-Bold', fontSize=12, alignment=TA_CENTER))]
    ]
    amt_table = Table(amt_data, colWidths=[540])
    amt_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FEF3C7")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#F59E0B")),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(amt_table)
    story.append(Spacer(1, 20))

    if contribution.get("notes"):
        story.append(Paragraph(f"<b>Notes:</b> {contribution.get('notes')}", ParagraphStyle('N', fontName='Helvetica', fontSize=9, textColor=colors.HexColor("#4B5563"))))
        story.append(Spacer(1, 10))

    # Footer
    sig_data = [
        [
            Paragraph("<i>Thank you for your generous contribution.<br/>May God bless you and your family abundantly!</i>", ParagraphStyle('Blessing', fontName='Helvetica-Oblique', fontSize=9, textColor=colors.HexColor("#6B7280"))),
            Paragraph(f"Authorized Signature<br/><b>{parish.get('pastor', 'Parish Office') if parish else 'Parish Office'}</b>", ParagraphStyle('Auth', fontName='Helvetica', fontSize=9, alignment=TA_RIGHT))
        ]
    ]
    sig_table = Table(sig_data, colWidths=[340, 200])
    sig_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'BOTTOM')]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def export_members_to_excel(members: list) -> bytes:
    """
    Exports a list of members to a styled Excel workbook.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Parishioners Directory"
    ws.views.sheetView[0].showGridLines = True

    # Palette
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    border_side = Side(style="thin", color="D1D5DB")
    cell_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)

    headers = [
        "Member ID", "First Name", "Last Name", "Gender", "Date of Birth",
        "Role", "Parish Name", "Deanery", "Phone", "Email", "Address",
        "Baptism", "Communion", "Confirmation", "Marriage"
    ]
    ws.append(headers)

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 25

    for m in members:
        row = [
            m.get("id"),
            m.get("first_name", ""),
            m.get("last_name", ""),
            m.get("gender", ""),
            m.get("dob", ""),
            m.get("role", ""),
            m.get("parish_name", ""),
            m.get("deanery_name", ""),
            m.get("phone", ""),
            m.get("email", ""),
            m.get("address", ""),
            "Yes" if m.get("baptism_received") else "No",
            "Yes" if m.get("communion_received") else "No",
            "Yes" if m.get("confirmation_received") else "No",
            "Yes" if m.get("marriage_received") else "No"
        ]
        ws.append(row)

    # Style data rows and auto-fit column widths
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=len(headers)):
        for cell in row:
            cell.font = data_font
            cell.border = cell_border
            cell.alignment = Alignment(vertical="center")

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_members_to_csv(members: list) -> str:
    """
    Exports members to CSV string.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Member ID", "First Name", "Last Name", "Gender", "Date of Birth",
        "Role", "Parish Name", "Deanery", "Phone", "Email", "Address",
        "Baptism", "Communion", "Confirmation", "Marriage"
    ])
    for m in members:
        writer.writerow([
            m.get("id"),
            m.get("first_name", ""),
            m.get("last_name", ""),
            m.get("gender", ""),
            m.get("dob", ""),
            m.get("role", ""),
            m.get("parish_name", ""),
            m.get("deanery_name", ""),
            m.get("phone", ""),
            m.get("email", ""),
            m.get("address", ""),
            "Yes" if m.get("baptism_received") else "No",
            "Yes" if m.get("communion_received") else "No",
            "Yes" if m.get("confirmation_received") else "No",
            "Yes" if m.get("marriage_received") else "No"
        ])
    return output.getvalue()


def export_contributions_to_excel(contributions: list) -> bytes:
    """
    Exports contributions/financials to Excel.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Parish Contributions"
    ws.views.sheetView[0].showGridLines = True

    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    border_side = Side(style="thin", color="D1D5DB")
    cell_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)

    headers = [
        "Receipt No", "Date", "Parish Name", "Member Name", "Family Name",
        "Category", "Amount", "Payment Mode", "Reference No", "Notes", "Recorded By"
    ]
    ws.append(headers)

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 25

    for c in contributions:
        row = [
            c.get("receipt_no", ""),
            c.get("payment_date", ""),
            c.get("parish_name", ""),
            c.get("member_name", ""),
            c.get("family_name", ""),
            c.get("category", ""),
            float(c.get("amount", 0.0)),
            c.get("payment_method", ""),
            c.get("reference_no", ""),
            c.get("notes", ""),
            c.get("recorded_by", "")
        ]
        ws.append(row)

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=len(headers)):
        for cell in row:
            cell.font = data_font
            cell.border = cell_border
            cell.alignment = Alignment(vertical="center")

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def generate_competition_certificate(participant: dict, program: dict, commission: dict = None, parish: dict = None, diocese: dict = None) -> bytes:
    """
    Generates an official Certificate of Merit / Participation for Diocesan Commission programs and competitions.
    """
    buffer = io.BytesIO()
    # Landscape orientation for presentation certificates
    from reportlab.lib.pagesizes import landscape
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=35,
        rightMargin=35,
        topMargin=35,
        bottomMargin=35
    )

    styles = getSampleStyleSheet()

    diocese_name = (diocese.get("name") if diocese else "DIOCESE OF SIMLA-CHANDIGARH").upper()
    comm_name = (commission.get("name") if commission else "DIOCESAN PASTORAL COMMISSION").upper()
    rank = participant.get("rank") or "Certificate of Participation"
    is_winner = any(w in rank.lower() for w in ["1st", "2nd", "3rd", "first", "second", "third", "winner", "prize", "merit"])
    
    cert_title = "CERTIFICATE OF MERIT & EXCELLENCE" if is_winner else "CERTIFICATE OF PARTICIPATION"

    elements = []
    elements.append(Spacer(1, 10))

    # Cross symbol
    cross_style = ParagraphStyle(
        'CrossStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#D97706")
    )
    elements.append(Paragraph("&#10013;", cross_style))
    elements.append(Spacer(1, 6))

    # Diocese Header
    d_style = ParagraphStyle(
        'DioceseStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=3
    )
    elements.append(Paragraph(diocese_name, d_style))

    # Commission Subtitle
    comm_style = ParagraphStyle(
        'CommStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#B45309"),
        spaceAfter=10
    )
    elements.append(Paragraph(comm_name, comm_style))

    # Decorative Line
    elements.append(HRFlowable(width="80%", thickness=1.5, color=colors.HexColor("#D97706"), spaceBefore=2, spaceAfter=12))

    # Certificate Title
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1E3A8A") if not is_winner else colors.HexColor("#B91C1C"),
        spaceAfter=14
    )
    elements.append(Paragraph(cert_title, title_style))

    # Presentation text
    body_style = ParagraphStyle(
        'BodyStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=13,
        leading=18,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#334155")
    )
    elements.append(Paragraph("This certificate is proudly awarded to", body_style))
    elements.append(Spacer(1, 8))

    # Participant Name (Grand serif / bold)
    name_style = ParagraphStyle(
        'NameStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1E3A8A")
    )
    elements.append(Paragraph(f"<u>{participant.get('participant_name', 'Participant')}</u>", name_style))
    elements.append(Spacer(1, 8))

    # Parish & Details
    p_name = parish.get("name") if parish else "Parish Community"
    team_info = f" (Team: {participant.get('team_name')})" if participant.get("team_name") else ""
    prog_title = program.get("title", "Diocesan Program")
    venue = program.get("venue", "Diocese of Simla-Chandigarh")
    date_str = program.get("start_date", datetime.now().strftime("%B %Y"))

    desc_text = f"Representing <b>{p_name}</b>{team_info} for exemplary participation and securing <b>{rank}</b> in the <b>{prog_title}</b> held at {venue} on {date_str}."
    elements.append(Paragraph(desc_text, body_style))
    elements.append(Spacer(1, 28))

    # Signatures Table
    sig_data = [
        [
            Paragraph(f"<b>{commission.get('director_name', 'Director')}</b><br/><font size=9 color='#64748B'>Director, {comm_name}</font>", ParagraphStyle('SigL', alignment=TA_CENTER, fontSize=11, leading=14)),
            Paragraph("<font size=11 color='#D97706'>&#10016; DIOCESAN SEAL &#10016;</font>", ParagraphStyle('Seal', alignment=TA_CENTER, fontSize=10)),
            Paragraph(f"<b>{diocese.get('bishop', 'Most Rev. Bishop')}</b><br/><font size=9 color='#64748B'>Bishop of {diocese.get('name', 'Diocese')}</font>", ParagraphStyle('SigR', alignment=TA_CENTER, fontSize=11, leading=14))
        ]
    ]
    sig_table = Table(sig_data, colWidths=[240, 220, 240])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('LINEABOVE', (0,0), (0,0), 1, colors.HexColor("#94A3B8")),
        ('LINEABOVE', (2,0), (2,0), 1, colors.HexColor("#94A3B8")),
    ]))
    elements.append(sig_table)

    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()

