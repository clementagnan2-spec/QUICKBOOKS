from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QDateEdit,
    QDoubleSpinBox, QFormLayout, QMessageBox
)
from PyQt5.QtCore import QDate
from PyQt5.QtGui import QFont

from .. import logic
from ..ui_utils import make_table, set_row

COMMON_CURRENCIES = ["USD", "EUR", "XOF", "GBP", "NGN"]


class CurrencyPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        header = QLabel("Devises et taux de change")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        layout.addWidget(header)

        note = QLabel("Devise de base : GHS. Les rapports consolidés (Bilan, Compte de résultat) "
                       "convertissent automatiquement chaque compte en devise étrangère vers GHS, "
                       "au taux le plus récent disponible à la date choisie.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666;")
        layout.addWidget(note)

        form = QFormLayout()
        self.currency_combo = QComboBox()
        self.currency_combo.addItems(COMMON_CURRENCIES)
        self.currency_combo.setEditable(True)
        form.addRow("Devise", self.currency_combo)

        self.rate = QDoubleSpinBox()
        self.rate.setMaximum(1_000_000)
        self.rate.setDecimals(4)
        form.addRow("1 unité = X GHS", self.rate)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        form.addRow("Date d'effet", self.date_edit)

        layout.addLayout(form)

        save_btn = QPushButton("Enregistrer le taux")
        save_btn.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        save_btn.clicked.connect(self.save_rate)
        layout.addWidget(save_btn)

        self.table = make_table(["Devise", "Taux vers GHS", "Date d'effet"])
        layout.addWidget(self.table)
        self.refresh()

    def save_rate(self):
        currency = self.currency_combo.currentText().strip().upper()
        if not currency:
            QMessageBox.warning(self, "Erreur", "Indiquez une devise.")
            return
        if self.rate.value() <= 0:
            QMessageBox.warning(self, "Erreur", "Le taux doit être positif.")
            return
        logic.set_exchange_rate(self.db, currency, self.rate.value(),
                                 self.date_edit.date().toString("yyyy-MM-dd"))
        self.refresh()

    def refresh(self):
        rates = self.db.query(
            "SELECT * FROM exchange_rates WHERE currency != 'GHS' ORDER BY currency, date DESC"
        )
        self.table.setRowCount(len(rates))
        for row, r in enumerate(rates):
            set_row(self.table, row, [r["currency"], f"{r['rate_to_base']:.4f}", r["date"]],
                    align_right_cols={1})
