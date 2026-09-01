from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QDateEdit,
    QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QMessageBox,
    QFormLayout
)
from PyQt5.QtCore import QDate, Qt
from PyQt5.QtGui import QFont

from .. import logic
from ..ui_utils import fmt_money


class ReconciliationPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        header = QLabel("Rapprochement bancaire")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        layout.addWidget(header)

        top = QFormLayout()
        self.account_combo = QComboBox()
        top.addRow("Compte", self.account_combo)

        self.statement_date = QDateEdit(QDate.currentDate())
        self.statement_date.setCalendarPopup(True)
        top.addRow("Date de relevé", self.statement_date)

        self.statement_balance = QDoubleSpinBox()
        self.statement_balance.setRange(-100_000_000, 100_000_000)
        self.statement_balance.setDecimals(2)
        top.addRow("Solde du relevé bancaire", self.statement_balance)

        layout.addLayout(top)

        load_btn = QPushButton("Charger les opérations non rapprochées")
        load_btn.setStyleSheet("background:#1F3D2E; color:white; padding:8px 16px; border-radius:4px;")
        load_btn.clicked.connect(self.load_lines)
        layout.addWidget(load_btn)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["✓", "Date", "Type", "Réf.", "Description", "Montant"])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.table)

        bottom = QHBoxLayout()
        self.summary_label = QLabel("")
        bottom.addWidget(self.summary_label)
        bottom.addStretch()
        finish_btn = QPushButton("Terminer le rapprochement")
        finish_btn.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        finish_btn.clicked.connect(self.finish)
        bottom.addWidget(finish_btn)
        layout.addLayout(bottom)

        self._line_ids = []
        self.refresh()

    def refresh(self):
        self.account_combo.clear()
        for a in self.db.query("SELECT * FROM accounts WHERE account_type='TRESORERIE' AND is_active=1"):
            self.account_combo.addItem(a["name"], a["id"])
        self.table.setRowCount(0)
        self.summary_label.setText("")

    def load_lines(self):
        account_id = self.account_combo.currentData()
        if account_id is None:
            return
        up_to = self.statement_date.date().toString("yyyy-MM-dd")
        lines = logic.unreconciled_lines(self.db, account_id, up_to_date=up_to)
        self.table.setRowCount(len(lines))
        self._line_ids = [l["id"] for l in lines]
        self._line_amounts = []
        for row, l in enumerate(lines):
            cb = QCheckBox()
            cb.stateChanged.connect(self._update_summary)
            self.table.setCellWidget(row, 0, cb)
            amount = round((l["debit"] or 0) - (l["credit"] or 0), 2)
            self._line_amounts.append(amount)
            self.table.setItem(row, 1, QTableWidgetItem(l["date"] or ""))
            self.table.setItem(row, 2, QTableWidgetItem(l["doc_type"] or ""))
            self.table.setItem(row, 3, QTableWidgetItem(l["doc_number"] or ""))
            self.table.setItem(row, 4, QTableWidgetItem(l["description"] or ""))
            amount_item = QTableWidgetItem(fmt_money(amount))
            amount_item.setData(Qt.UserRole, amount)
            self.table.setItem(row, 5, amount_item)
        self._update_summary()

    def _selected_ids_and_total(self):
        selected_ids, total = [], 0
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if cb and cb.isChecked():
                selected_ids.append(self._line_ids[row])
                item = self.table.item(row, 5)
                amount = item.data(Qt.UserRole) if item is not None else None
                total += amount if amount is not None else 0
        return selected_ids, round(total, 2)

    def _update_summary(self):
        _ids, total = self._selected_ids_and_total()
        target = self.statement_balance.value()
        diff = round(target - total, 2)
        color = "#2CA01C" if diff == 0 else "#B00020"
        self.summary_label.setText(
            f"Total pointé : {fmt_money(total)}   |   Différence avec le relevé : "
            f"<span style='color:{color}; font-weight:bold'>{fmt_money(diff)}</span>"
        )
        self.summary_label.setTextFormat(Qt.RichText)

    def finish(self):
        account_id = self.account_combo.currentData()
        if account_id is None:
            return
        selected_ids, _total = self._selected_ids_and_total()
        if not selected_ids:
            QMessageBox.information(self, "Aucune sélection", "Cochez au moins une opération à rapprocher.")
            return
        result = logic.finish_reconciliation(
            self.db, account_id, self.statement_date.date().toString("yyyy-MM-dd"),
            self.statement_balance.value(), selected_ids,
        )
        if result["difference"] != 0:
            QMessageBox.warning(
                self, "Écart constaté",
                f"Le rapprochement présente un écart de {fmt_money(result['difference'])}.\n"
                "Vérifiez les opérations cochées ou le solde du relevé avant de continuer.",
            )
        else:
            QMessageBox.information(self, "Rapprochement terminé", "Le compte est rapproché sans écart.")
        self.load_lines()
