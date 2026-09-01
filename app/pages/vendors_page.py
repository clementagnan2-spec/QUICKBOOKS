from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QDialog, QMessageBox
from PyQt5.QtGui import QFont

from .customers_page import PartyDialog
from ..ui_utils import make_table, set_row, fmt_money


class VendorsPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        top = QHBoxLayout()
        header = QLabel("Fournisseurs")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        top.addWidget(header)
        top.addStretch()
        add_btn = QPushButton("+ Nouveau fournisseur")
        add_btn.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        add_btn.clicked.connect(self.add_vendor)
        top.addWidget(add_btn)
        layout.addLayout(top)

        self.table = make_table(["Nom", "Email", "Téléphone", "Devise", "Solde à payer"])
        layout.addWidget(self.table)
        self.refresh()

    def add_vendor(self):
        dlg = PartyDialog("Nouveau fournisseur", self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Erreur", "Le nom est obligatoire.")
                return
            self.db.execute(
                "INSERT INTO vendors (name, email, phone, address, currency) VALUES (?,?,?,?,?)",
                (data["name"], data["email"], data["phone"], data["address"], data["currency"]),
            )
            self.refresh()

    def refresh(self):
        vendors = self.db.query("SELECT * FROM vendors WHERE is_active=1 ORDER BY name")
        self.table.setRowCount(len(vendors))
        for row, v in enumerate(vendors):
            due = self.db.query(
                "SELECT COALESCE(SUM(total-paid),0) s FROM bills WHERE vendor_id=?", (v["id"],)
            )[0]["s"]
            set_row(self.table, row,
                    [v["name"], v["email"] or "", v["phone"] or "", v["currency"], fmt_money(due, v["currency"])],
                    align_right_cols={4})
