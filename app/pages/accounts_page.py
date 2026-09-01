from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDialogButtonBox, QMessageBox
)
from PyQt5.QtGui import QFont

from .. import logic
from ..database import ACCOUNT_TYPES
from ..ui_utils import make_table, set_row, fmt_money

TYPE_LABELS = {
    "TRESORERIE": "Trésorerie",
    "COMPTES_CLIENTS": "Comptes clients",
    "STOCK": "Stock",
    "AUTRE_ACTIF_CT": "Autre actif court terme",
    "ACTIF_LONG_TERME": "Actif à long terme",
    "COMPTES_FOURNISSEURS": "Comptes fournisseurs",
    "CARTE_CREDIT": "Carte de crédit",
    "PASSIF_COURT_TERME": "Passif à court terme",
    "PASSIF_LONG_TERME": "Passif à long terme",
    "CAPITAUX_PROPRES": "Capitaux propres",
    "PRODUITS": "Produits",
    "COUT_DES_VENTES": "Coût des ventes",
    "DEPENSES": "Dépenses",
    "AUTRES_PRODUITS": "Autres produits",
    "AUTRES_DEPENSES": "Autres dépenses",
}


class AccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nouveau compte")
        self.setMinimumWidth(400)
        form = QFormLayout(self)

        self.number = QLineEdit()
        self.name = QLineEdit()
        self.type_combo = QComboBox()
        for key, label in TYPE_LABELS.items():
            self.type_combo.addItem(label, key)
        self.detail = QLineEdit()
        self.currency = QComboBox()
        self.currency.addItems(["GHS", "USD", "EUR", "XOF"])

        form.addRow("N°", self.number)
        form.addRow("Nom du compte*", self.name)
        form.addRow("Type de compte*", self.type_combo)
        form.addRow("Type détaillé", self.detail)
        form.addRow("Devise", self.currency)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)

    def get_data(self):
        return {
            "number": self.number.text().strip(),
            "name": self.name.text().strip(),
            "account_type": self.type_combo.currentData(),
            "detail_type": self.detail.text().strip(),
            "currency": self.currency.currentText(),
        }


class AccountsPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        top = QHBoxLayout()
        header = QLabel("Plan comptable")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        top.addWidget(header)
        top.addStretch()
        add_btn = QPushButton("+ Nouveau compte")
        add_btn.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        add_btn.clicked.connect(self.add_account)
        top.addWidget(add_btn)
        layout.addLayout(top)

        self.table = make_table(["N°", "Nom", "Type de compte", "Type détaillé", "Devise", "Solde"])
        layout.addWidget(self.table)

        self.refresh()

    def add_account(self):
        dlg = AccountDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Erreur", "Le nom du compte est obligatoire.")
                return
            self.db.execute(
                """INSERT INTO accounts (number, name, account_type, detail_type, currency)
                   VALUES (?,?,?,?,?)""",
                (data["number"], data["name"], data["account_type"], data["detail_type"], data["currency"]),
            )
            self.refresh()

    def refresh(self):
        accounts = self.db.query(
            "SELECT * FROM accounts WHERE is_active=1 ORDER BY account_type, name"
        )
        self.table.setRowCount(len(accounts))
        today = date.today().isoformat()
        for row, acc in enumerate(accounts):
            bal = logic.account_balance(self.db, acc["id"], today)
            set_row(
                self.table, row,
                [acc["number"] or "", acc["name"], TYPE_LABELS.get(acc["account_type"], acc["account_type"]),
                 acc["detail_type"] or "", acc["currency"], fmt_money(bal, acc["currency"])],
                align_right_cols={5},
            )
