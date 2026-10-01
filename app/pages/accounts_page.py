from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDialogButtonBox, QMessageBox, QDoubleSpinBox, QFileDialog,
    QPlainTextEdit
)
from PyQt5.QtGui import QFont, QColor

from .. import logic
from .. import chart_plan as cp
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

STATUS_COLORS = {"Modifié": "#FFE8CC", "Sans équivalent": "#FFD6D6", "À confirmer": "#D6E6FF"}


class AccountDialog(QDialog):
    """Création / modification d'un compte, avec sa correspondance SYCEBNL."""

    def __init__(self, parent=None, account=None):
        super().__init__(parent)
        self.setWindowTitle("Modifier le compte" if account else "Nouveau compte")
        self.setMinimumWidth(520)
        form = QFormLayout(self)

        self.number = QLineEdit()
        self.name = QLineEdit()
        self.type_combo = QComboBox()
        for key, label in TYPE_LABELS.items():
            self.type_combo.addItem(label, key)
        self.section_combo = QComboBox()
        for key, (label, _side) in cp.GAAP_SECTIONS.items():
            self.section_combo.addItem(label, key)
        self.currency = QComboBox()
        self.currency.addItems(["GHS", "USD", "EUR", "XOF"])
        self.syc_code = QLineEdit()
        self.syc_code.setPlaceholderText("ex. 521  (N/A si aucun équivalent)")
        self.syc_name = QLineEdit()
        self.coef = QDoubleSpinBox()
        self.coef.setRange(-1000, 1000)
        self.coef.setDecimals(4)
        self.coef.setValue(1.0)
        self.status = QComboBox()
        self.status.addItems(cp.REVIEW_STATUSES)
        self.remark = QPlainTextEdit()
        self.remark.setFixedHeight(60)

        form.addRow("Code US GAAP", self.number)
        form.addRow("Intitulé US GAAP*", self.name)
        form.addRow("Section US GAAP*", self.section_combo)
        form.addRow("Type fonctionnel*", self.type_combo)
        form.addRow("Devise", self.currency)
        form.addRow("Compte SYCEBNL", self.syc_code)
        form.addRow("Intitulé SYCEBNL", self.syc_name)
        form.addRow("Coefficient", self.coef)
        form.addRow("Statut de revue", self.status)
        form.addRow("Remarque", self.remark)

        self.section_combo.currentIndexChanged.connect(self._sync_type)
        if account:
            self.number.setText(account["number"] or "")
            self.name.setText(account["name"])
            i = self.type_combo.findData(account["account_type"])
            self.type_combo.setCurrentIndex(max(i, 0))
            i = self.section_combo.findData(cp.effective_section(account))
            self.section_combo.setCurrentIndex(max(i, 0))
            self.currency.setCurrentText(account["currency"] or "GHS")
            self.syc_code.setText(account["syc_code"] or "")
            self.syc_name.setText(account["syc_name"] or "")
            self.coef.setValue(account["coefficient"] if account["coefficient"] is not None else 1.0)
            self.status.setCurrentText(account["review_status"] or "")
            self.remark.setPlainText(account["remark"] or "")
        else:
            self._sync_type()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)

    def _sync_type(self):
        """Propose le type fonctionnel correspondant à la section (modifiable ensuite)."""
        if self.windowTitle() == "Nouveau compte":
            t = cp.DEFAULT_TYPE_FOR_SECTION.get(self.section_combo.currentData())
            i = self.type_combo.findData(t)
            if i >= 0:
                self.type_combo.setCurrentIndex(i)

    def get_data(self):
        atype = self.type_combo.currentData()
        return {
            "number": self.number.text().strip(),
            "name": self.name.text().strip(),
            "account_type": atype,
            "gaap_section": self.section_combo.currentData(),
            "detail_type": ACCOUNT_TYPES.get(atype, ("", ""))[1],
            "currency": self.currency.currentText(),
            "syc_code": self.syc_code.text().strip(),
            "syc_name": self.syc_name.text().strip(),
            "coefficient": self.coef.value(),
            "review_status": self.status.currentText(),
            "remark": self.remark.toPlainText().strip(),
        }


class AccountsPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._accounts = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        top = QHBoxLayout()
        header = QLabel("Plan comptable (US GAAP ↔ SYCEBNL)")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        top.addWidget(header)
        top.addStretch()
        for text, slot, color in (
            ("+ Nouveau compte", self.add_account, "#2CA01C"),
            ("Modifier", self.edit_account, "#1F3D2E"),
            ("Désactiver / Réactiver", self.toggle_account, "#6c757d"),
            ("Supprimer", self.delete_account, "#b02a37"),
            ("Importer Excel", self.import_xlsx, "#0B5FFF"),
            ("Exporter Excel", self.export_xlsx, "#0B5FFF"),
            ("Compléter avec le plan standard", self.load_standard, "#6c757d"),
        ):
            b = QPushButton(text)
            b.setStyleSheet(f"background:{color}; color:white; padding:8px 12px; border-radius:4px;")
            b.clicked.connect(slot)
            top.addWidget(b)
        layout.addLayout(top)

        filt = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher (code, intitulé, compte SYCEBNL)…")
        self.search.textChanged.connect(self.refresh)
        self.show_inactive = QComboBox()
        self.show_inactive.addItems(["Comptes actifs", "Tous les comptes"])
        self.show_inactive.currentIndexChanged.connect(self.refresh)
        filt.addWidget(self.search)
        filt.addWidget(self.show_inactive)
        layout.addLayout(filt)

        self.table = make_table(["Code US GAAP", "Intitulé US GAAP", "Section US GAAP",
                                 "Compte SYCEBNL", "Intitulé SYCEBNL", "Coef.", "Statut",
                                 "Devise", "Solde"])
        self.table.doubleClicked.connect(lambda _i: self.edit_account())
        layout.addWidget(self.table)
        self.refresh()

    # ------------------------------------------------------------------ #
    def _selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._accounts):
            QMessageBox.information(self, "Plan comptable", "Sélectionnez d'abord un compte.")
            return None
        return self._accounts[row]

    def _save(self, data, account_id=None):
        if not data["name"]:
            QMessageBox.warning(self, "Erreur", "L'intitulé du compte est obligatoire.")
            return False
        if data["number"]:
            dup = self.db.query("SELECT id FROM accounts WHERE number=? AND id IS NOT ?",
                                (data["number"], account_id))
            if dup:
                QMessageBox.warning(self, "Erreur", f"Le code {data['number']} existe déjà.")
                return False
        cols = ["number", "name", "account_type", "gaap_section", "detail_type", "currency",
                "syc_code", "syc_name", "coefficient", "review_status", "remark"]
        vals = [data[c] for c in cols]
        if account_id is None:
            self.db.execute(
                f"INSERT INTO accounts ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
        else:
            self.db.execute(
                f"UPDATE accounts SET {','.join(c + '=?' for c in cols)} WHERE id=?", vals + [account_id])
        return True

    def add_account(self):
        dlg = AccountDialog(self)
        if dlg.exec_() == QDialog.Accepted and self._save(dlg.get_data()):
            self.refresh()

    def edit_account(self):
        acc = self._selected()
        if not acc:
            return
        dlg = AccountDialog(self, acc)
        if dlg.exec_() == QDialog.Accepted and self._save(dlg.get_data(), acc["id"]):
            self.refresh()

    def toggle_account(self):
        acc = self._selected()
        if not acc:
            return
        self.db.execute("UPDATE accounts SET is_active=? WHERE id=?",
                        (0 if acc["is_active"] else 1, acc["id"]))
        self.refresh()

    def delete_account(self):
        acc = self._selected()
        if not acc:
            return
        used = self.db.query("SELECT COUNT(*) n FROM journal_lines WHERE account_id=?", (acc["id"],))[0]["n"]
        used += self.db.query("SELECT COUNT(*) n FROM items WHERE income_account_id=? OR "
                              "expense_account_id=? OR asset_account_id=?",
                              (acc["id"],) * 3)[0]["n"]
        if used:
            QMessageBox.warning(
                self, "Suppression impossible",
                "Ce compte est utilisé par des écritures ou des articles.\n"
                "Utilisez « Désactiver » pour le retirer des listes sans perdre l'historique.")
            return
        if QMessageBox.question(self, "Supprimer", f"Supprimer le compte « {acc['name']} » ?") == QMessageBox.Yes:
            self.db.execute("DELETE FROM accounts WHERE id=?", (acc["id"],))
            self.refresh()

    def import_xlsx(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importer un plan comptable", "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            created, updated = cp.import_chart_xlsx(self.db, path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'import", str(e))
            return
        QMessageBox.information(self, "Import terminé",
                                f"{created} compte(s) créé(s), {updated} mis à jour (par code US GAAP).")
        self.refresh()

    def export_xlsx(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le plan comptable",
                                              "Plan_comptable_US_GAAP_SYCEBNL.xlsx", "Excel (*.xlsx)")
        if path:
            try:
                cp.export_chart_xlsx(self.db, path)
                QMessageBox.information(self, "Export réussi", path)
            except Exception as e:
                QMessageBox.critical(self, "Erreur d'export", str(e))

    def load_standard(self):
        n = cp.load_standard_chart(self.db)
        QMessageBox.information(self, "Plan standard",
                                f"{n} compte(s) ajouté(s). Les comptes existants n'ont pas été modifiés.")
        self.refresh()

    # ------------------------------------------------------------------ #
    def refresh(self):
        sql = "SELECT * FROM accounts"
        if self.show_inactive.currentIndex() == 0:
            sql += " WHERE is_active=1"
        sql += " ORDER BY CASE WHEN number IS NULL OR number='' THEN 1 ELSE 0 END, number, name"
        accounts = self.db.query(sql)
        q = self.search.text().strip().lower()
        if q:
            accounts = [a for a in accounts if q in " ".join(
                str(a[k] or "") for k in ("number", "name", "syc_code", "syc_name")).lower()]
        self._accounts = accounts
        self.table.setRowCount(len(accounts))
        today = date.today().isoformat()
        for row, acc in enumerate(accounts):
            bal = logic.account_balance(self.db, acc["id"], today)
            sec = cp.GAAP_SECTIONS[cp.effective_section(acc)][0].split(" (")[0]
            set_row(self.table, row, [
                acc["number"] or "", acc["name"] + ("" if acc["is_active"] else "  (inactif)"), sec,
                acc["syc_code"] or "", acc["syc_name"] or "",
                f"{acc['coefficient']:g}" if acc["coefficient"] is not None else "1",
                acc["review_status"] or "", acc["currency"], fmt_money(bal, acc["currency"]),
            ], align_right_cols={5, 8})
            color = STATUS_COLORS.get(acc["review_status"] or "")
            if color:
                for c in range(self.table.columnCount()):
                    self.table.item(row, c).setBackground(QColor(color))
