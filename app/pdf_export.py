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


def export_report_pdf(path, report_name, data, start, end):
    doc, styles, title_style = _base_doc(path)
    elements = [Paragraph("GH-Compta", title_style), Spacer(1, 4)]

    if report_name == "Bilan":
        elements.append(Paragraph(f"Bilan au {end}", styles["Heading2"]))
        rows, bold = [], []
        rows.append(["ACTIF", ""]); bold.append(len(rows) - 1)
        for label in ("Actif à court terme", "Actif à long terme"):
            for acc, bal, _base in data["sections"][label]:
                rows.append([f"  {acc['name']}", fmt_money(bal, acc["currency"])])
        rows.append(["Total Actif", fmt_money(data["total_actif"], "GHS")]); bold.append(len(rows) - 1)
        rows.append(["", ""])
        rows.append(["PASSIF & CAPITAUX PROPRES", ""]); bold.append(len(rows) - 1)
        for label in ("Passif à court terme", "Passif à long terme"):
            for acc, bal, _base in data["sections"][label]:
                rows.append([f"  {acc['name']}", fmt_money(bal, acc["currency"])])
        for acc, bal, _base in data["sections"]["Capitaux propres"]:
            rows.append([f"  {acc['name']}", fmt_money(bal, acc["currency"])])
        rows.append(["  Résultat net (cumulé)", fmt_money(data["net_income"], "GHS")])
        rows.append(["Total Passif + Capitaux propres",
                      fmt_money(data["total_passif"] + data["total_capitaux_propres"], "GHS")])
        bold.append(len(rows) - 1)
        elements.append(_styled_table(rows, bold))

    elif report_name == "Compte de résultat":
        elements.append(Paragraph(f"Compte de résultat du {start} au {end}", styles["Heading2"]))
        rows, bold = [], []
        rows.append(["Produits", ""]); bold.append(len(rows) - 1)
        for acc, bal, _base in data["produits"]:
            rows.append([f"  {acc['name']}", fmt_money(bal, acc["currency"])])
        rows.append(["Total Produits", fmt_money(data["total_produits"], "GHS")]); bold.append(len(rows) - 1)
        rows.append(["Coût des ventes", ""]); bold.append(len(rows) - 1)
        for acc, bal, _base in data["cout_ventes"]:
            rows.append([f"  {acc['name']}", fmt_money(bal, acc["currency"])])
        rows.append(["Total Coût des ventes", fmt_money(data["total_cout_ventes"], "GHS")])
        bold.append(len(rows) - 1)
        rows.append(["Marge brute", fmt_money(data["marge_brute"], "GHS")]); bold.append(len(rows) - 1)
        rows.append(["Dépenses", ""]); bold.append(len(rows) - 1)
        for acc, bal, _base in data["depenses"]:
            rows.append([f"  {acc['name']}", fmt_money(bal, acc["currency"])])
        rows.append(["Total Dépenses", fmt_money(data["total_depenses"], "GHS")]); bold.append(len(rows) - 1)
        rows.append(["RÉSULTAT NET", fmt_money(data["resultat_net"], "GHS")]); bold.append(len(rows) - 1)
        elements.append(_styled_table(rows, bold))

    else:  # État des flux de trésorerie
        elements.append(Paragraph(f"État des flux de trésorerie du {start} au {end}", styles["Heading2"]))
        rows, bold = [], []
        rows.append(["Trésorerie en début de période", fmt_money(data["total_start"], "GHS")])
        for r in data["rows"]:
            rows.append([f"  {r['account']['name']} — variation", fmt_money(r["change"], "GHS")])
        rows.append(["Variation nette de trésorerie", fmt_money(data["net_change"], "GHS")])
        bold.append(len(rows) - 1)
        rows.append(["Trésorerie en fin de période", fmt_money(data["total_end"], "GHS")])
        bold.append(len(rows) - 1)
        elements.append(_styled_table(rows, bold))

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
