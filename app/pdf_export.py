"""
Export PDF des rapports financiers et des factures, via ReportLab.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from .ui_utils import fmt_money


def _base_doc(path):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleGH", parent=styles["Title"], textColor=colors.HexColor("#1F3D2E"))
    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    return doc, styles, title_style


def _styled_table(rows, bold_rows=()):
    table = Table(rows, colWidths=[10 * cm, 5 * cm])
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#2CA01C")),
    ]
    for r in bold_rows:
        style.append(("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"))
        style.append(("LINEABOVE", (0, r), (-1, r), 0.5, colors.grey))
    table.setStyle(TableStyle(style))
    return table


def _report_elements(report, styles):
    """Éléments ReportLab pour un rapport structuré (voir app/reports.py)."""
    els = [Paragraph(report["title"], styles["Heading2"]),
           Paragraph(report["subtitle"], styles["Normal"]), Spacer(1, 6)]
    rows, style = [], []
    for r in report["rows"]:
        i = len(rows)
        kind = r["kind"]
        label = ("    " if kind == "line" else "") + (r["label"] or "")
        if r["code"] and kind == "line":
            label = f"    {r['code']}  {r['label']}"
        amount = "" if r["amount"] is None else fmt_money(r["amount"], "GHS")
        rows.append([label, amount])
        if kind in ("section", "subtotal", "total"):
            style.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
        if kind in ("subtotal", "total"):
            style.append(("LINEABOVE", (0, i), (-1, i), 0.5, colors.grey))
        if kind == "total":
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E6F4EA")))
        if kind == "warn":
            style.append(("TEXTCOLOR", (0, i), (-1, i), colors.red))
    table = Table(rows, colWidths=[11.5 * cm, 4.5 * cm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ] + style))
    els.append(table)
    return els


def export_report_pdf(path, reports):
    """
    reports : liste de rapports structurés (ex. [version US GAAP, version SYCEBNL]).
    Chaque version est placée sur sa propre page du même PDF.
    """
    from reportlab.platypus import PageBreak
    doc, styles, title_style = _base_doc(path)
    elements = []
    for i, rep in enumerate(reports):
        if i:
            elements.append(PageBreak())
        elements.append(Paragraph("GH-Compta", title_style))
        elements.extend(_report_elements(rep, styles))
    doc.build(elements)


def export_invoice_pdf(path, invoice, lines, customer, company_name="GH-Compta"):
    """invoice: sqlite3.Row de la facture ; lines: liste de invoice_lines ; customer: sqlite3.Row."""
    doc, styles, title_style = _base_doc(path)
    elements = [Paragraph(company_name, title_style)]
    elements.append(Paragraph(f"FACTURE {invoice['number'] or ('#' + str(invoice['id']))}", styles["Heading2"]))
    elements.append(Spacer(1, 6))

    info_rows = [
        ["Client", customer["name"]],
        ["Date", invoice["date"]],
        ["Échéance", invoice["due_date"] or "-"],
        ["Devise", invoice["currency"]],
        ["Statut", invoice["status"]],
    ]
    info_table = Table(info_rows, colWidths=[4 * cm, 8 * cm])
    info_table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9),
                                     ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    line_rows = [["Description", "Qté", "Prix unitaire", "Montant"]]
    for l in lines:
        line_rows.append([
            l["description"] or "", f"{l['qty']:.2f}",
            fmt_money(l["unit_price"], invoice["currency"]), fmt_money(l["amount"], invoice["currency"]),
        ])
    items_table = Table(line_rows, colWidths=[7 * cm, 2 * cm, 3.5 * cm, 3.5 * cm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3D2E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 10))

    total_rows = [
        ["Total", fmt_money(invoice["total"], invoice["currency"])],
        ["Payé", fmt_money(invoice["paid"], invoice["currency"])],
        ["Solde dû", fmt_money(invoice["total"] - invoice["paid"], invoice["currency"])],
    ]
    total_table = Table(total_rows, colWidths=[9 * cm, 3.5 * cm])
    total_table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 10), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                                      ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
    elements.append(total_table)

    doc.build(elements)
