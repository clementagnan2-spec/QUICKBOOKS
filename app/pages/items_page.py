from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDialogButtonBox, QMessageBox, QDoubleSpinBox
)
from PyQt5.QtGui import QFont

from ..ui_utils import make_table, set_row, fmt_money

ITEM_TYPES = ["Stock", "Service", "Non-stock"]


class ItemDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Nouvel article")
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        self.sku = QLineEdit()
        self.name = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(ITEM_TYPES)
        self.type_combo.currentTextChanged.connect(self._toggle_stock_fields)

        self.income_combo = QComboBox()
        for a in db.query("SELECT * FROM accounts WHERE account_type='PRODUITS' AND is_active=1"):
            self.income_combo.addItem(a["name"], a["id"])

        self.expense_combo = QComboBox()
        for a in db.query(
            "SELECT * FROM accounts WHERE account_type IN ('COUT_DES_VENTES','DEPENSES') AND is_active=1"
        ):
            self.expense_combo.addItem(a["name"], a["id"])

        self.asset_combo = QComboBox()
        for a in db.query("SELECT * FROM accounts WHERE account_type='STOCK' AND is_active=1"):
            self.asset_combo.addItem(a["name"], a["id"])

        self.sales_price = QDoubleSpinBox()
        self.sales_price.setMaximum(10_000_000)
        self.sales_price.setDecimals(2)

        self.opening_qty = QDoubleSpinBox()
        self.opening_qty.setMaximum(10_000_000)
        self.opening_cost = QDoubleSpinBox()
        self.opening_cost.setMaximum(10_000_000)
        self.opening_cost.setDecimals(2)

        form.addRow("Référence (SKU)", self.sku)
        form.addRow("Nom*", self.name)
        form.addRow("Type", self.type_combo)
        form.addRow("Compte de produit (vente)", self.income_combo)
        form.addRow("Compte de charge (coût des ventes)", self.expense_combo)
        form.addRow("Compte de stock (actif)", self.asset_combo)
        form.addRow("Prix de vente", self.sales_price)
        form.addRow("Quantité initiale", self.opening_qty)
        form.addRow("Coût unitaire initial", self.opening_cost)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)
        self._toggle_stock_fields(self.type_combo.currentText())

    def _toggle_stock_fields(self, item_type):
        is_stock = item_type == "Stock"
        for w in (self.asset_combo, self.opening_qty, self.opening_cost):
            w.setEnabled(is_stock)

    def get_data(self):
        return {
            "sku": self.sku.text().strip(), "name": self.name.text().strip(),
            "item_type": self.type_combo.currentText(),
            "income_account_id": self.income_combo.currentData(),
            "expense_account_id": self.expense_combo.currentData(),
            "asset_account_id": self.asset_combo.currentData() if self.type_combo.currentText() == "Stock" else None,
            "sales_price": self.sales_price.value(),
            "opening_qty": self.opening_qty.value(),
            "opening_cost": self.opening_cost.value(),
        }


class ItemsPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        top = QHBoxLayout()
        header = QLabel("Stock / Articles")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        top.addWidget(header)
        top.addStretch()
        add_btn = QPushButton("+ Nouvel article")
        add_btn.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        add_btn.clicked.connect(self.add_item)
        top.addWidget(add_btn)
        layout.addLayout(top)

        self.table = make_table(["SKU", "Nom", "Type", "Prix de vente", "Coût moyen", "Qté en stock", "Valeur stock"])
        layout.addWidget(self.table)
        self.refresh()

    def add_item(self):
        if not self.db.query("SELECT 1 FROM accounts WHERE account_type='PRODUITS' LIMIT 1"):
            QMessageBox.warning(self, "Attention", "Créez d'abord un compte de produits.")
            return
        dlg = ItemDialog(self.db, self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Erreur", "Le nom de l'article est obligatoire.")
                return
            self.db.execute(
                """INSERT INTO items (sku, name, item_type, income_account_id, expense_account_id,
                                       asset_account_id, sales_price, cost, qty_on_hand)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (data["sku"], data["name"], data["item_type"], data["income_account_id"],
                 data["expense_account_id"], data["asset_account_id"], data["sales_price"],
                 data["opening_cost"], data["opening_qty"]),
            )
            self.refresh()

    def refresh(self):
        items = self.db.query("SELECT * FROM items WHERE is_active=1 ORDER BY name")
        self.table.setRowCount(len(items))
        for row, it in enumerate(items):
            value = round((it["qty_on_hand"] or 0) * (it["cost"] or 0), 2)
            set_row(self.table, row,
                    [it["sku"] or "", it["name"], it["item_type"], fmt_money(it["sales_price"]),
                     fmt_money(it["cost"]), f"{it['qty_on_hand']:.2f}" if it["item_type"] == "Stock" else "—",
                     fmt_money(value) if it["item_type"] == "Stock" else "—"],
                    align_right_cols={3, 4, 5, 6})
