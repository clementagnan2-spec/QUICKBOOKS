from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QDialog, QFormLayout,
    QComboBox, QDateEdit, QLineEdit, QDialogButtonBox, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import QDate
from PyQt5.QtGui import QFont

from .. import logic
from ..ui_utils import make_table, set_row, fmt_money


class ODLinesTable(QTableWidget):
    """Compte | Description | Débit | Crédit — pour les opérations diverses (OD)."""
    def __init__(self, accounts):
        super().__init__()
        self.accounts = accounts
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["Compte", "Description", "Débit", "Crédit"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setRowCount(0)
        self.add_row()
        self.add_row()

    def add_row(self):
        row = self.rowCount()
        self.insertRow(row)
        combo = QComboBox()
        for a in self.accounts:
            combo.addItem(f"{a['number'] or ''} {a['name']}".strip(), a["id"])
        self.setCellWidget(row, 0, combo)
        self.setItem(row, 1, QTableWidgetItem(""))
        self.setItem(row, 2, QTableWidgetItem("0"))
        self.setItem(row, 3, QTableWidgetItem("0"))

    def get_lines(self):
        lines = []
        for row in range(self.rowCount()):
            combo = self.cellWidget(row, 0)
            desc = self.item(row, 1).text() if self.item(row, 1) else ""
            try:
                debit = float(self.item(row, 2).text() or 0)
                credit = float(self.item(row, 3).text() or 0)
            except ValueError:
                debit, credit = 0, 0
            if combo and (debit or credit):
                lines.append({"account_id": combo.currentData(), "description": desc,
                              "debit": debit, "credit": credit})
        return lines


class ManualEntryDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Nouvelle écriture manuelle (OD)")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.memo = QLineEdit()
        form.addRow("Date", self.date_edit)
        form.addRow("Mémo", self.memo)
        layout.addLayout(form)

        accounts = db.query("SELECT * FROM accounts WHERE is_active=1 ORDER BY account_type, name")
        self.lines_table = ODLinesTable(accounts)
        layout.addWidget(self.lines_table)

        add_line_btn = QPushButton("+ Ajouter une ligne")
        add_line_btn.clicked.connect(self.lines_table.add_row)
        layout.addWidget(add_line_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        return {
            "date": self.date_edit.date().toString("yyyy-MM-dd"),
            "memo": self.memo.text().strip(),
            "lines": self.lines_table.get_lines(),
        }


class JournalPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        top = QHBoxLayout()
        header = QLabel("Journal général")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        top.addWidget(header)
        top.addStretch()
        add_btn = QPushButton("+ Écriture manuelle")
        add_btn.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        add_btn.clicked.connect(self.add_entry)
        top.addWidget(add_btn)
        layout.addLayout(top)

        self.table = make_table(["Date", "Type", "N°", "Compte", "Description", "Débit", "Crédit"])
        layout.addWidget(self.table)
        self.refresh()

    def add_entry(self):
        dlg = ManualEntryDialog(self.db, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                logic.post_journal_entry(self.db, data["date"], "OD", data["lines"], memo=data["memo"])
            except logic.LedgerError as e:
                QMessageBox.critical(self, "Erreur comptable", str(e))
                return
            self.refresh()

    def refresh(self):
        rows = self.db.query(
            """SELECT je.date, je.doc_type, je.doc_number, a.name as account_name,
                      jl.description, jl.debit, jl.credit
               FROM journal_lines jl
               JOIN journal_entries je ON je.id = jl.entry_id
               JOIN accounts a ON a.id = jl.account_id
               ORDER BY je.date DESC, je.id DESC"""
        )
        self.table.setRowCount(len(rows))
        for row, r in enumerate(rows):
            set_row(self.table, row,
                    [r["date"], r["doc_type"], r["doc_number"] or "", r["account_name"],
                     r["description"] or "", fmt_money(r["debit"]) if r["debit"] else "",
                     fmt_money(r["credit"]) if r["credit"] else ""],
                    align_right_cols={5, 6})
