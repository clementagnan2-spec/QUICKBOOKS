from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDateEdit, QDialogButtonBox, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QDoubleSpinBox
)
from PyQt5.QtCore import QDate
from PyQt5.QtGui import QFont

from .. import logic
from ..ui_utils import make_table, set_row, fmt_money
from ..pdf_export import export_invoice_pdf


class InvoiceLinesTable(QTableWidget):
    """Compte produit | Article (stock, optionnel) | Description | Qté | PU | Montant."""
    def __init__(self, income_accounts, items):
        super().__init__()
        self.income_accounts = income_accounts
        self.items = items
        self.setColumnCount(6)
        self.setHorizontalHeaderLabels(
            ["Compte de produit", "Article (stock)", "Description", "Qté", "Prix unitaire", "Montant"]
        )
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setRowCount(0)
        self.add_row()
        self.cellChanged.connect(self._recompute_row)

    def add_row(self):
        row = self.rowCount()
        self.insertRow(row)
        combo = QComboBox()
        for a in self.income_accounts:
            combo.addItem(f"{a['number'] or ''} {a['name']}".strip(), a["id"])
        self.setCellWidget(row, 0, combo)

        item_combo = QComboBox()
        item_combo.addItem("(aucun)", None)
        for it in self.items:
            item_combo.addItem(it["name"], it["id"])
        item_combo.currentIndexChanged.connect(lambda _i, r=row: self._on_item_selected(r))
        self.setCellWidget(row, 1, item_combo)

        self.setItem(row, 2, QTableWidgetItem(""))
        self.setItem(row, 3, QTableWidgetItem("1"))
        self.setItem(row, 4, QTableWidgetItem("0"))
        self.setItem(row, 5, QTableWidgetItem("0.00"))
        self.item(row, 5).setFlags(self.item(row, 5).flags() & ~2)  # non éditable

    def _on_item_selected(self, row):
        item_combo = self.cellWidget(row, 1)
        item_id = item_combo.currentData()
        if item_id is None:
            return
        item = next((it for it in self.items if it["id"] == item_id), None)
        if not item:
            return
        self.blockSignals(True)
        self.item(row, 2).setText(item["name"])
        self.item(row, 4).setText(str(item["sales_price"]))
        account_combo = self.cellWidget(row, 0)
        if item["income_account_id"]:
            idx = account_combo.findData(item["income_account_id"])
            if idx >= 0:
                account_combo.setCurrentIndex(idx)
        try:
            qty = float(self.item(row, 3).text() or 0)
        except ValueError:
            qty = 0
        self.item(row, 5).setText(f"{qty * item['sales_price']:.2f}")
        self.blockSignals(False)

    def _recompute_row(self, row, col):
        if col not in (3, 4):
            return
        try:
            qty = float(self.item(row, 3).text() or 0)
            price = float(self.item(row, 4).text() or 0)
        except ValueError:
            return
        self.blockSignals(True)
        self.item(row, 5).setText(f"{qty * price:.2f}")
        self.blockSignals(False)

    def get_lines(self):
        lines = []
        for row in range(self.rowCount()):
            combo = self.cellWidget(row, 0)
            item_combo = self.cellWidget(row, 1)
            desc = self.item(row, 2).text() if self.item(row, 2) else ""
            try:
                qty = float(self.item(row, 3).text() or 0)
                price = float(self.item(row, 4).text() or 0)
            except ValueError:
                qty, price = 0, 0
            if combo and qty and price:
                lines.append({"account_id": combo.currentData(), "item_id": item_combo.currentData(),
                              "description": desc, "qty": qty, "unit_price": price})
        return lines


class InvoiceDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Nouvelle facture")
        self.setMinimumWidth(650)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.customer_combo = QComboBox()
        self.customers = db.query("SELECT * FROM customers WHERE is_active=1 ORDER BY name")
        for c in self.customers:
            self.customer_combo.addItem(c["name"], c["id"])

        self.number = QLineEdit()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.due_edit = QDateEdit(QDate.currentDate())
        self.due_edit.setCalendarPopup(True)

        self.ar_combo = QComboBox()
        self.ar_accounts = db.query("SELECT * FROM accounts WHERE account_type='COMPTES_CLIENTS' AND is_active=1")
        for a in self.ar_accounts:
            self.ar_combo.addItem(a["name"], a["id"])

        form.addRow("Client*", self.customer_combo)
        form.addRow("N° de facture", self.number)
        form.addRow("Date", self.date_edit)
        form.addRow("Échéance", self.due_edit)
        form.addRow("Compte 'Comptes clients'", self.ar_combo)
        layout.addLayout(form)

        income_accounts = db.query(
            "SELECT * FROM accounts WHERE account_type='PRODUITS' AND is_active=1 ORDER BY name"
        )
        if not income_accounts:
            QMessageBox.warning(self, "Attention",
                                 "Aucun compte de produits trouvé. Créez-en un dans le Plan comptable.")
        items = db.query("SELECT * FROM items WHERE is_active=1 AND item_type='Stock' ORDER BY name")
        self.lines_table = InvoiceLinesTable(income_accounts, items)
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
            "customer_id": self.customer_combo.currentData(),
            "number": self.number.text().strip(),
            "date": self.date_edit.date().toString("yyyy-MM-dd"),
            "due_date": self.due_edit.date().toString("yyyy-MM-dd"),
            "ar_account_id": self.ar_combo.currentData(),
            "lines": self.lines_table.get_lines(),
        }


class InvoicesPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        top = QHBoxLayout()
        header = QLabel("Ventes / Factures")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        top.addWidget(header)
        top.addStretch()
        add_btn = QPushButton("+ Nouvelle facture")
        add_btn.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        add_btn.clicked.connect(self.add_invoice)
        top.addWidget(add_btn)

        pdf_btn = QPushButton("Exporter PDF")
        pdf_btn.setStyleSheet("background:#1F3D2E; color:white; padding:8px 16px; border-radius:4px;")
        pdf_btn.clicked.connect(self.export_selected_pdf)
        top.addWidget(pdf_btn)
        layout.addLayout(top)

        self.table = make_table(["N°", "Client", "Date", "Échéance", "Total", "Payé", "Statut"])
        layout.addWidget(self.table)
        self.refresh()

    def export_selected_pdf(self):
        from PyQt5.QtWidgets import QFileDialog
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Sélection", "Sélectionnez d'abord une facture dans la liste.")
            return
        invoice_id = self._invoice_ids[row]
        invoice = self.db.query("SELECT * FROM invoices WHERE id=?", (invoice_id,))[0]
        customer = self.db.query("SELECT * FROM customers WHERE id=?", (invoice["customer_id"],))[0]
        lines = self.db.query("SELECT * FROM invoice_lines WHERE invoice_id=?", (invoice_id,))
        default_name = f"Facture_{invoice['number'] or invoice_id}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter la facture", default_name, "PDF (*.pdf)")
        if not path:
            return
        try:
            export_invoice_pdf(path, invoice, lines, customer)
            QMessageBox.information(self, "Export réussi", f"Facture exportée :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", str(e))

    def add_invoice(self):
        if not self.db.query("SELECT 1 FROM customers LIMIT 1"):
            QMessageBox.warning(self, "Attention", "Créez d'abord un client.")
            return
        dlg = InvoiceDialog(self.db, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["lines"]:
                QMessageBox.warning(self, "Erreur", "Ajoutez au moins une ligne valide.")
                return
            stock_acc = self.db.query("SELECT id FROM accounts WHERE account_type='STOCK' LIMIT 1")
            cogs_acc = self.db.query("SELECT id FROM accounts WHERE account_type='COUT_DES_VENTES' LIMIT 1")
            try:
                logic.create_invoice_with_items(
                    self.db, data["customer_id"], data["date"], data["due_date"],
                    data["lines"], data["ar_account_id"],
                    stock_account_id=stock_acc[0]["id"] if stock_acc else None,
                    cogs_account_id=cogs_acc[0]["id"] if cogs_acc else None,
                    number=data["number"],
                )
            except logic.LedgerError as e:
                QMessageBox.critical(self, "Erreur comptable", str(e))
                return
            self.refresh()

    def refresh(self):
        invoices = self.db.query(
            """SELECT i.*, c.name as customer_name FROM invoices i
               JOIN customers c ON c.id=i.customer_id ORDER BY i.date DESC"""
        )
        self.table.setRowCount(len(invoices))
        self._invoice_ids = [inv["id"] for inv in invoices]
        for row, inv in enumerate(invoices):
            set_row(self.table, row,
                    [inv["number"] or f"#{inv['id']}", inv["customer_name"], inv["date"], inv["due_date"] or "",
                     fmt_money(inv["total"], inv["currency"]), fmt_money(inv["paid"], inv["currency"]),
                     inv["status"]],
                    align_right_cols={4, 5})
