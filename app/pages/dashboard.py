from datetime import date
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout
from PyQt5.QtGui import QFont

from .. import logic
from ..ui_utils import fmt_money


class KpiCard(QFrame):
    def __init__(self, title, value_text, color="#2CA01C"):
        super().__init__()
        self.setStyleSheet(
            f"QFrame {{ background:white; border:1px solid #e0e0e0; border-radius:8px; }}"
        )
        layout = QVBoxLayout(self)
        t = QLabel(title)
        t.setStyleSheet("color:#666; font-size:12px;")
        v = QLabel(value_text)
        v.setFont(QFont("Segoe UI", 20, QFont.Bold))
        v.setStyleSheet(f"color:{color};")
        layout.addWidget(t)
        layout.addWidget(v)
        self.value_label = v


class DashboardPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        header = QLabel("Tableau de bord")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        layout.addWidget(header)

        self.grid = QGridLayout()
        layout.addLayout(self.grid)
        layout.addStretch()

        self.cards = {}
        self._build_cards()
        self.refresh()

    def _build_cards(self):
        specs = [
            ("Trésorerie totale", "#2CA01C"),
            ("Total Actif", "#1F3D2E"),
            ("Total Passif", "#B00020"),
            ("Résultat net (cumulé)", "#0B5FFF"),
        ]
        for i, (title, color) in enumerate(specs):
            card = KpiCard(title, "—", color)
            self.grid.addWidget(card, 0, i)
            self.cards[title] = card

    def refresh(self):
        today = date.today().isoformat()
        cash_accounts = self.db.query(
            "SELECT id FROM accounts WHERE account_type='TRESORERIE' AND is_active=1"
        )
        total_cash = sum(logic.account_balance(self.db, a["id"], today) for a in cash_accounts)
        bs = logic.balance_sheet(self.db, today)

        self.cards["Trésorerie totale"].value_label.setText(fmt_money(total_cash))
        self.cards["Total Actif"].value_label.setText(fmt_money(bs["total_actif"]))
        self.cards["Total Passif"].value_label.setText(fmt_money(bs["total_passif"]))
        self.cards["Résultat net (cumulé)"].value_label.setText(fmt_money(bs["net_income"]))
