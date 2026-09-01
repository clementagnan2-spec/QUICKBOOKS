from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDateEdit, QDialogButtonBox, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QDoubleSpinBox
)
from PyQt5.QtCore import QDate
from PyQt5.QtGui import QFont

from .. import logic
from ..ui_utils import make_table, set_row, fmt_money


class BillLinesTable(QTableWidget):
    """Compte (charge/stock) | Article (optionnel) | Description | Qté | Coût unitaire | Montant"""
    def __init__(self, expense_accounts, items):
        super().__init__()
        self.expense_accounts = expense_accounts
        self.items = items
        self.setColumnCount(6)
        self.setHorizontalHeaderLabels(
            ["Compte", "Article (stock)", "Description", "Qté", "Coût unitaire", "Montant"]
        )
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setRowCount(0)
        self.add_row()
        self.cellChanged.connect(self._recompute_row)

    def add_row(self):
        row = self.rowCount()
        self.insertRow(row)
        combo = QComboBox()
        for a in self.expense_accounts:
            combo.addItem(f"{a['number'] or ''} {a['name']}".strip(), a["id"])
        self.setCellWidget(row, 0, combo)

        item_combo = QComboBox()
        item_combo.addItem("(aucun)", None)
        for it in self.items:
            item_combo.addItem(it["name"], it["id"])
        self.setCellWidget(row, 1, item_combo)

        self.setItem(row, 2, QTableWidgetItem(""))
        self.setItem(row, 3, QTableWidgetItem("1"))
        self.setItem(row, 4, QTableWidgetItem("0"))
        self.setItem(row, 5, QTableWidgetItem("0.00"))
        self.item(row, 5).setFlags(self.item(row, 5).flags() & ~2)

    def _recompute_row(self, row, col):
        if col not in (3, 4):
            return
        try:
            qty = float(self.item(row, 3).text() or 0)
            cost = float(self.item(row, 4).text() or 0)
        except ValueError:
            return
        self.blockSignals(True)
        self.item(row, 5).setText(f"{qty * cost:.2f}")
        self.blockSignals(False)

    def get_lines(self):
        lines = []
        for row in range(self.rowCount()):
            combo = self.cellWidget(row, 0)
            item_combo = self.cellWidget(row, 1)
            desc = self.item(row, 2).text() if self.item(row, 2) else ""
            try:
                qty = float(self.item(row, 3).text() or 0)
                cost = float(self.item(row, 4).text() or 0)
            except ValueError:
                qty, cost = 0, 0
            if combo and qty and cost:
                lines.append({"account_id": combo.currentData(), "item_id": item_combo.currentData(),
                              "description": desc, "qty": qty, "unit_cost": cost})
        return lines


class BillDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Nouvelle facture fournisseur (à crédit)")
        self.setMinimumWidth(720)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.vendor_combo = QComboBox()
        for v in db.query("SELECT * FROM vendors WHERE is_active=1 ORDER BY name"):
            self.vendor_combo.addItem(v["name"], v["id"])

        self.ap_combo = QComboBox()
        self.ap_accounts = db.query(
            "SELECT * FROM accounts WHERE account_type='COMPTES_FOURNISSEURS' AND is_active=1"
        )
        for a in self.ap_accounts:
            self.ap_combo.addItem(a["name"], a["id"])

        self.number = QLineEdit()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.due_edit = QDateEdit(QDate.currentDate().addDays(30))
        self.due_edit.setCalendarPopup(True)

        form.addRow("Fournisseur*", self.vendor_combo)
        form.addRow("Compte 'Comptes fournisseurs'", self.ap_combo)
        form.addRow("N° de facture", self.number)
        form.addRow("Date", self.date_edit)
        form.addRow("Échéance", self.due_edit)
        layout.addLayout(form)

        expense_accounts = db.query(
            "SELECT * FROM accounts WHERE account_type IN ('DEPENSES','COUT_DES_VENTES','STOCK') "
            "AND is_active=1 ORDER BY name"
        )
        items = db.query("SELECT * FROM items WHERE is_active=1 ORDER BY name")
        self.lines_table = BillLinesTable(expense_accounts, items)
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
            "ap_account_id": self.ap_combo.currentData(),
            "number": self.number.text().strip(),
            "date": self.date_edit.date().toString("yyyy-MM-dd"),
            "due_date": self.due_edit.date().toString("yyyy-MM-dd"),
            "lines": self.lines_table.get_lines(),
        }


class PayBillDialog(QDialog):
    def __init__(self, db, bill, parent=None):
        super().__init__(parent)
        self.db = db
        self.bill = bill
        self.setWindowTitle(f"Payer la facture {bill['number'] or bill['id']}")
        form = QFormLayout(self)

        remaining = bill["total"] - bill["paid"]
        form.addRow("Solde restant", QLabel(fmt_money(remaining, bill["currency"])))

        self.amount = QDoubleSpinBox()
        self.amount.setMaximum(10_000_000)
        self.amount.setDecimals(2)
        self.amount.setValue(remaining)
        form.addRow("Montant à payer", self.amount)

        self.account_combo = QComboBox()
        for a in db.query("SELECT * FROM accounts WHERE account_type='TRESORERIE' AND is_active=1"):
            self.account_combo.addItem(a["name"], a["id"])
        form.addRow("Payer depuis", self.account_combo)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        form.addRow("Date", self.date_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)

    def get_data(self):
        return {
            "amount": self.amount.value(),
            "payment_account_id": self.account_combo.currentData(),
            "date": self.date_edit.date().toString("yyyy-MM-dd"),
        }


class BillsPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        top = QHBoxLayout()
        header = QLabel("Factures fournisseurs (à crédit)")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        top.addWidget(header)
        top.addStretch()
        add_btn = QPushButton("+ Nouvelle facture fournisseur")
        add_btn.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        add_btn.clicked.connect(self.add_bill)
        top.addWidget(add_btn)
        pay_btn = QPushButton("Enregistrer un paiement")
        pay_btn.setStyleSheet("background:#1F3D2E; color:white; padding:8px 16px; border-radius:4px;")
        pay_btn.clicked.connect(self.pay_bill)
        top.addWidget(pay_btn)
        layout.addLayout(top)

        self.table = make_table(["N°", "Fournisseur", "Date", "Échéance", "Total", "Payé", "Statut"])
        layout.addWidget(self.table)
        self.refresh()

    def add_bill(self):
        if not self.db.query("SELECT 1 FROM vendors LIMIT 1"):
            QMessageBox.warning(self, "Attention", "Créez d'abord un fournisseur.")
            return
        if not self.db.query("SELECT 1 FROM accounts WHERE account_type='COMPTES_FOURNISSEURS' LIMIT 1"):
            QMessageBox.warning(self, "Attention", "Créez d'abord un compte 'Comptes fournisseurs'.")
            return
        dlg = BillDialog(self.db, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["lines"]:
                QMessageBox.warning(self, "Erreur", "Ajoutez au moins une ligne valide.")
                return
            try:
                logic.create_bill(
                    self.db, data["vendor_id"], data["date"], data["due_date"],
                    data["lines"], data["ap_account_id"], number=data["number"],
                )
            except logic.LedgerError as e:
                QMessageBox.critical(self, "Erreur comptable", str(e))
                return
            self.refresh()

    def pay_bill(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Sélection", "Sélectionnez d'abord une facture dans la liste.")
            return
        bill_id = self._bill_ids[row]
        bill = self.db.query("SELECT * FROM bills WHERE id=?", (bill_id,))[0]
        if bill["status"] == "Payée":
            QMessageBox.information(self, "Déjà payée", "Cette facture est déjà entièrement payée.")
            return
        dlg = PayBillDialog(self.db, bill, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if data["amount"] <= 0:
                QMessageBox.warning(self, "Erreur", "Le montant doit être positif.")
                return
            try:
                logic.record_vendor_payment(
                    self.db, bill["vendor_id"], bill_id, data["amount"], data["date"],
                    data["payment_account_id"],
                )
            except logic.LedgerError as e:
                QMessageBox.critical(self, "Erreur comptable", str(e))
                return
            self.refresh()

    def refresh(self):
        bills = self.db.query(
            """SELECT b.*, v.name as vendor_name FROM bills b
               JOIN vendors v ON v.id=b.vendor_id ORDER BY b.date DESC"""
        )
        self.table.setRowCount(len(bills))
        self._bill_ids = [b["id"] for b in bills]
        for row, b in enumerate(bills):
            set_row(self.table, row,
                    [b["number"] or f"#{b['id']}", b["vendor_name"], b["date"], b["due_date"] or "",
                     fmt_money(b["total"], b["currency"]), fmt_money(b["paid"], b["currency"]), b["status"]],
                    align_right_cols={4, 5})
