from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDateEdit, QDialogButtonBox, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import QDate
from PyQt5.QtGui import QFont

from .. import logic
from ..ui_utils import make_table, set_row, fmt_money


class ExpenseLinesTable(QTableWidget):
    """Compte de charge | Description | Montant"""
    def __init__(self, expense_accounts):
        super().__init__()
        self.expense_accounts = expense_accounts
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(["Catégorie (compte de charge)", "Description", "Montant"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setRowCount(0)
        self.add_row()

    def add_row(self):
        row = self.rowCount()
        self.insertRow(row)
        combo = QComboBox()
        for a in self.expense_accounts:
            combo.addItem(f"{a['number'] or ''} {a['name']}".strip(), a["id"])
        self.setCellWidget(row, 0, combo)
        self.setItem(row, 1, QTableWidgetItem(""))
        self.setItem(row, 2, QTableWidgetItem("0"))

    def get_lines(self):
        lines = []
        for row in range(self.rowCount()):
            combo = self.cellWidget(row, 0)
            desc = self.item(row, 1).text() if self.item(row, 1) else ""
            try:
                amount = float(self.item(row, 2).text() or 0)
            except ValueError:
                amount = 0
            if combo and amount:
                lines.append({"account_id": combo.currentData(), "description": desc, "amount": amount})
        return lines


class ExpenseDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Nouvel achat / dépense")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.vendor_combo = QComboBox()
        self.vendor_combo.addItem("(aucun)", None)
        for v in db.query("SELECT * FROM vendors WHERE is_active=1 ORDER BY name"):
            self.vendor_combo.addItem(v["name"], v["id"])

        self.payment_account_combo = QComboBox()
        self.cash_accounts = db.query("SELECT * FROM accounts WHERE account_type='TRESORERIE' AND is_active=1")
        for a in self.cash_accounts:
            self.payment_account_combo.addItem(a["name"], a["id"])

        self.number = QLineEdit()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.memo = QLineEdit()

        form.addRow("Fournisseur / Bénéficiaire", self.vendor_combo)
        form.addRow("Payé depuis*", self.payment_account_combo)
        form.addRow("N° de référence", self.number)
        form.addRow("Date", self.date_edit)
        form.addRow("Mémo", self.memo)
        layout.addLayout(form)

        expense_accounts = db.query(
            "SELECT * FROM accounts WHERE account_type IN ('DEPENSES','COUT_DES_VENTES') "
            "AND is_active=1 ORDER BY name"
        )
        self.lines_table = ExpenseLinesTable(expense_accounts)
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
            "vendor_id": self.vendor_combo.currentData(),
            "payment_account_id": self.payment_account_combo.currentData(),
            "number": self.number.text().strip(),
            "date": self.date_edit.date().toString("yyyy-MM-dd"),
            "memo": self.memo.text().strip(),
            "lines": self.lines_table.get_lines(),
        }


class ExpensesPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        top = QHBoxLayout()
        header = QLabel("Dépenses / Achats")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        top.addWidget(header)
        top.addStretch()
        add_btn = QPushButton("+ Nouvel achat")
        add_btn.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        add_btn.clicked.connect(self.add_expense)
        top.addWidget(add_btn)
        layout.addLayout(top)

        self.table = make_table(["Date", "N°", "Fournisseur", "Payé depuis", "Mémo", "Total"])
        layout.addWidget(self.table)
        self.refresh()

    def add_expense(self):
        if not self.db.query("SELECT 1 FROM accounts WHERE account_type='TRESORERIE' LIMIT 1"):
            QMessageBox.warning(self, "Attention", "Créez d'abord un compte de trésorerie.")
            return
        dlg = ExpenseDialog(self.db, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["lines"]:
                QMessageBox.warning(self, "Erreur", "Ajoutez au moins une ligne valide.")
                return
            try:
                logic.create_expense(
                    self.db, data["payment_account_id"], data["date"], data["lines"],
                    vendor_id=data["vendor_id"], number=data["number"], memo=data["memo"],
                )
            except logic.LedgerError as e:
                QMessageBox.critical(self, "Erreur comptable", str(e))
                return
            self.refresh()

    def refresh(self):
        expenses = self.db.query(
            """SELECT e.*, v.name as vendor_name, a.name as account_name FROM expenses e
               LEFT JOIN vendors v ON v.id=e.vendor_id
               JOIN accounts a ON a.id=e.payment_account_id
               ORDER BY e.date DESC"""
        )
        self.table.setRowCount(len(expenses))
        for row, ex in enumerate(expenses):
            set_row(self.table, row,
                    [ex["date"], ex["number"] or f"#{ex['id']}", ex["vendor_name"] or "",
                     ex["account_name"], ex["memo"] or "", fmt_money(ex["total"], ex["currency"])],
                    align_right_cols={5})
