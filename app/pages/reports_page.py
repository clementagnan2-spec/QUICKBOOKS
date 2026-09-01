from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QDateEdit,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import QDate
from PyQt5.QtGui import QFont

from .. import logic
from ..ui_utils import fmt_money
from ..pdf_export import export_report_pdf


def _simple_table():
    t = QTableWidget()
    t.setColumnCount(2)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
    t.horizontalHeader().setVisible(False)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    return t


def _add_row(table, label, value, bold=False):
    row = table.rowCount()
    table.insertRow(row)
    li = QTableWidgetItem(("  " if not bold else "") + label)
    vi = QTableWidgetItem(value)
    if bold:
        f = li.font(); f.setBold(True); li.setFont(f)
        f2 = vi.font(); f2.setBold(True); vi.setFont(f2)
    table.setItem(row, 0, li)
    table.setItem(row, 1, vi)


class ReportsPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        header = QLabel("Rapports")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        layout.addWidget(header)

        top = QHBoxLayout()
        self.report_combo = QComboBox()
        self.report_combo.addItems(["Bilan", "Compte de résultat", "État des flux de trésorerie"])
        self.report_combo.currentIndexChanged.connect(self._render)
        top.addWidget(QLabel("Rapport :"))
        top.addWidget(self.report_combo)

        top.addWidget(QLabel("Du :"))
        self.start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.start_date.setCalendarPopup(True)
        top.addWidget(self.start_date)

        top.addWidget(QLabel("Au :"))
        self.end_date = QDateEdit(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        top.addWidget(self.end_date)

        run_btn = QPushButton("Actualiser")
        run_btn.setStyleSheet("background:#2CA01C; color:white; padding:6px 14px; border-radius:4px;")
        run_btn.clicked.connect(self._render)
        top.addWidget(run_btn)

        pdf_btn = QPushButton("Exporter en PDF")
        pdf_btn.setStyleSheet("background:#1F3D2E; color:white; padding:6px 14px; border-radius:4px;")
        pdf_btn.clicked.connect(self._export_pdf)
        top.addWidget(pdf_btn)
        top.addStretch()
        layout.addLayout(top)

        self._last_report = None

        self.table = _simple_table()
        layout.addWidget(self.table)

        self._render()

    def refresh(self):
        self._render()

    def _export_pdf(self):
        if not self._last_report:
            return
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        name, data, start, end = self._last_report
        default_name = f"{name.replace(' ', '_')}_{end}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en PDF", default_name, "PDF (*.pdf)")
        if not path:
            return
        try:
            export_report_pdf(path, name, data, start, end)
            QMessageBox.information(self, "Export réussi", f"Rapport exporté :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", str(e))

    def _render(self):
        report = self.report_combo.currentText()
        end = self.end_date.date().toString("yyyy-MM-dd")
        start = self.start_date.date().toString("yyyy-MM-dd")
        self.table.setRowCount(0)
        self.table.setColumnCount(2)

        if report == "Bilan":
            self._render_balance_sheet(end)
        elif report == "Compte de résultat":
            self._render_income_statement(start, end)
        else:
            self._render_cash_flow(start, end)

    def _render_balance_sheet(self, as_of):
        bs = logic.balance_sheet(self.db, as_of)
        t = self.table
        _add_row(t, f"BILAN au {as_of} (totaux consolidés en GHS)", "", bold=True)
        _add_row(t, "ACTIF", "")
        for label in ("Actif à court terme", "Actif à long terme"):
            for acc, bal, _base in bs["sections"][label]:
                _add_row(t, f"  {acc['name']}", fmt_money(bal, acc["currency"]))
        _add_row(t, "Total Actif", fmt_money(bs["total_actif"], "GHS"), bold=True)
        _add_row(t, "", "")
        _add_row(t, "PASSIF & CAPITAUX PROPRES", "")
        for label in ("Passif à court terme", "Passif à long terme"):
            for acc, bal, _base in bs["sections"][label]:
                _add_row(t, f"  {acc['name']}", fmt_money(bal, acc["currency"]))
        for acc, bal, _base in bs["sections"]["Capitaux propres"]:
            _add_row(t, f"  {acc['name']}", fmt_money(bal, acc["currency"]))
        _add_row(t, "  Résultat net (cumulé)", fmt_money(bs["net_income"], "GHS"))
        _add_row(t, "Total Passif + Capitaux propres",
                 fmt_money(bs["total_passif"] + bs["total_capitaux_propres"], "GHS"), bold=True)
        self._last_report = ("Bilan", bs, as_of, as_of)

    def _render_income_statement(self, start, end):
        inc = logic.income_statement(self.db, start, end)
        t = self.table
        _add_row(t, f"COMPTE DE RÉSULTAT du {start} au {end} (totaux consolidés en GHS)", "", bold=True)
        _add_row(t, "Produits", "")
        for acc, bal, _base in inc["produits"]:
            _add_row(t, f"  {acc['name']}", fmt_money(bal, acc["currency"]))
        _add_row(t, "Total Produits", fmt_money(inc["total_produits"], "GHS"), bold=True)
        _add_row(t, "", "")
        _add_row(t, "Coût des ventes", "")
        for acc, bal, _base in inc["cout_ventes"]:
            _add_row(t, f"  {acc['name']}", fmt_money(bal, acc["currency"]))
        _add_row(t, "Total Coût des ventes", fmt_money(inc["total_cout_ventes"], "GHS"), bold=True)
        _add_row(t, "Marge brute", fmt_money(inc["marge_brute"], "GHS"), bold=True)
        _add_row(t, "", "")
        _add_row(t, "Dépenses", "")
        for acc, bal, _base in inc["depenses"]:
            _add_row(t, f"  {acc['name']}", fmt_money(bal, acc["currency"]))
        _add_row(t, "Total Dépenses", fmt_money(inc["total_depenses"], "GHS"), bold=True)
        _add_row(t, "RÉSULTAT NET", fmt_money(inc["resultat_net"], "GHS"), bold=True)
        self._last_report = ("Compte de résultat", inc, start, end)

    def _render_cash_flow(self, start, end):
        cf = logic.cash_flow(self.db, start, end)
        t = self.table
        _add_row(t, f"FLUX DE TRÉSORERIE du {start} au {end}", "", bold=True)
        _add_row(t, "Trésorerie en début de période", fmt_money(cf["total_start"]))
        for r in cf["rows"]:
            _add_row(t, f"  {r['account']['name']} — variation", fmt_money(r["change"]))
        _add_row(t, "Variation nette de trésorerie", fmt_money(cf["net_change"]), bold=True)
        _add_row(t, "Trésorerie en fin de période", fmt_money(cf["total_end"]), bold=True)
        self._last_report = ("État des flux de trésorerie", cf, start, end)
