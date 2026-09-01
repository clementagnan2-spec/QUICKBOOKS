from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDialogButtonBox, QMessageBox
)
from PyQt5.QtGui import QFont

from ..ui_utils import make_table, set_row, fmt_money


class PartyDialog(QDialog):
    """Dialogue générique client / fournisseur."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.email = QLineEdit()
        self.phone = QLineEdit()
        self.address = QLineEdit()
        self.currency = QComboBox()
        self.currency.addItems(["GHS", "USD", "EUR", "XOF"])
        form.addRow("Nom*", self.name)
        form.addRow("Email", self.email)
        form.addRow("Téléphone", self.phone)
        form.addRow("Adresse", self.address)
        form.addRow("Devise", self.currency)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)

    def get_data(self):
        return {
            "name": self.name.text().strip(), "email": self.email.text().strip(),
            "phone": self.phone.text().strip(), "address": self.address.text().strip(),
            "currency": self.currency.currentText(),
        }


class CustomersPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        top = QHBoxLayout()
        header = QLabel("Clients")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        top.addWidget(header)
        top.addStretch()
        add_btn = QPushButton("+ Nouveau client")
        add_btn.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        add_btn.clicked.connect(self.add_customer)
        top.addWidget(add_btn)
        layout.addLayout(top)

        self.table = make_table(["Nom", "Email", "Téléphone", "Devise", "Solde dû"])
        layout.addWidget(self.table)
        self.refresh()

    def add_customer(self):
        dlg = PartyDialog("Nouveau client", self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Erreur", "Le nom est obligatoire.")
                return
            self.db.execute(
                "INSERT INTO customers (name, email, phone, address, currency) VALUES (?,?,?,?,?)",
                (data["name"], data["email"], data["phone"], data["address"], data["currency"]),
            )
            self.refresh()

    def refresh(self):
        customers = self.db.query("SELECT * FROM customers WHERE is_active=1 ORDER BY name")
        self.table.setRowCount(len(customers))
        for row, c in enumerate(customers):
            due = self.db.query(
                "SELECT COALESCE(SUM(total-paid),0) s FROM invoices WHERE customer_id=?", (c["id"],)
            )[0]["s"]
            set_row(self.table, row,
                    [c["name"], c["email"] or "", c["phone"] or "", c["currency"], fmt_money(due, c["currency"])],
                    align_right_cols={4})
