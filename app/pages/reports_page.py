from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QDateEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox
)
from PyQt5.QtCore import QDate, Qt
from PyQt5.QtGui import QFont, QColor

from ..reports import build_report, REPORT_KINDS, GAAP, SYCEBNL, FRAMEWORK_LABELS
from ..ui_utils import fmt_money
from ..pdf_export import export_report_pdf

VIEWS = [("Les deux versions (côte à côte)", "BOTH"),
         ("US GAAP", GAAP), ("SYCEBNL", SYCEBNL)]


def _table():
    t = QTableWidget()
    t.setColumnCount(2)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
    t.horizontalHeader().setVisible(False)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    return t


def _fill(table, report):
    table.setRowCount(0)
    for r in report["rows"]:
        row = table.rowCount()
        table.insertRow(row)
        kind = r["kind"]
        text = r["label"] or ""
        if kind == "line":
            text = "    " + (f"{r['code']}  " if r["code"] else "") + text
        li = QTableWidgetItem(text)
        vi = QTableWidgetItem("" if r["amount"] is None else fmt_money(r["amount"], "GHS"))
        vi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for it in (li, vi):
            f = it.font()
            if kind in ("section", "subtotal", "total"):
                f.setBold(True)
            it.setFont(f)
            if kind == "total":
                it.setBackground(QColor("#E6F4EA"))
            if kind == "warn":
                it.setForeground(QColor("red"))
        table.setItem(row, 0, li)
        table.setItem(row, 1, vi)


class ReportsPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._reports = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        header = QLabel("Rapports (US GAAP et SYCEBNL)")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        layout.addWidget(header)

        top = QHBoxLayout()
        self.report_combo = QComboBox()
        self.report_combo.addItems(REPORT_KINDS)
        self.report_combo.currentIndexChanged.connect(self._render)
        top.addWidget(QLabel("Rapport :"))
        top.addWidget(self.report_combo)

        self.view_combo = QComboBox()
        for label, key in VIEWS:
            self.view_combo.addItem(label, key)
        self.view_combo.currentIndexChanged.connect(self._render)
        top.addWidget(QLabel("Version :"))
        top.addWidget(self.view_combo)

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

        self.body = QHBoxLayout()
        layout.addLayout(self.body)
        self.tables = {}
        for fw in (GAAP, SYCEBNL):
            col = QVBoxLayout()
            lab = QLabel(FRAMEWORK_LABELS[fw])
            lab.setFont(QFont("Segoe UI", 12, QFont.Bold))
            lab.setStyleSheet("color:#1F3D2E;")
            t = _table()
            col.addWidget(lab)
            col.addWidget(t)
            holder = QWidget()
            holder.setLayout(col)
            self.body.addWidget(holder)
            self.tables[fw] = (holder, t)
        self._render()

    def refresh(self):
        self._render()

    def _frameworks(self):
        key = self.view_combo.currentData()
        return (GAAP, SYCEBNL) if key == "BOTH" else (key,)

    def _render(self):
        kind = self.report_combo.currentText()
        start = self.start_date.date().toString("yyyy-MM-dd")
        end = self.end_date.date().toString("yyyy-MM-dd")
        shown = self._frameworks()
        self._reports = []
        for fw in (GAAP, SYCEBNL):
            holder, table = self.tables[fw]
            holder.setVisible(fw in shown)
            if fw in shown:
                rep = build_report(self.db, kind, start, end, fw)
                _fill(table, rep)
                self._reports.append(rep)

    def _export_pdf(self):
        if not self._reports:
            return
        kind = self.report_combo.currentText().replace(" ", "_")
        end = self.end_date.date().toString("yyyy-MM-dd")
        suffix = "US-GAAP_et_SYCEBNL" if len(self._reports) == 2 else FRAMEWORK_LABELS[self._frameworks()[0]]
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter en PDF", f"{kind}_{suffix}_{end}.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            export_report_pdf(path, self._reports)
            QMessageBox.information(self, "Export réussi", f"Rapport exporté :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", str(e))
