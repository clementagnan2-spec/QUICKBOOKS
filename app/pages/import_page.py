from datetime import date
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QMessageBox,
    QDialog, QFormLayout, QDateEdit, QCheckBox, QDialogButtonBox, QFrame
)
from PyQt5.QtCore import QDate
from PyQt5.QtGui import QFont

from .. import importers as im


class _OptionsDialog(QDialog):
    def __init__(self, parent, title, date_label, default_date, check_label=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        self.date_edit = QDateEdit(default_date)
        self.date_edit.setCalendarPopup(True)
        form.addRow(date_label, self.date_edit)
        self.check = None
        if check_label:
            self.check = QCheckBox(check_label)
            self.check.setChecked(True)
            form.addRow(self.check)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def iso_date(self):
        return self.date_edit.date().toString("yyyy-MM-dd")


class ImportPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        header = QLabel("Importer des données (Excel)")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        layout.addWidget(header)
        note = QLabel(
            "Les comptes du fichier sont reconnus par leur code US GAAP, sinon par leur compte "
            "SYCEBNL (s'il est unique), sinon par leur intitulé. Chaque import est contrôlé "
            "(équilibre, comptes connus) et vous montre un résumé avant d'écrire quoi que ce soit.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._card(layout, "Écritures comptables",
                   "Colonnes : Date, N° pièce, Libellé, Compte, Débit, Crédit. Les lignes d'une même "
                   "pièce doivent s'équilibrer. Les écritures déjà présentes sont ignorées.",
                   "Importer les écritures…", self.import_entries, "entries")
        self._card(layout, "Balance N-1 (à-nouveaux)",
                   "Colonnes : Compte, Intitulé, Débit, Crédit (ou Solde : + débiteur / − créditeur). "
                   "Crée l'écriture d'à-nouveaux à la date choisie ; les comptes de résultat N-1 sont "
                   "reportés sur 1920. Remplace une balance N-1 déjà importée.",
                   "Importer la balance N-1…", self.import_opening, "balance")
        self._card(layout, "Balance N (soldes de clôture)",
                   "Mêmes colonnes. Les soldes sont des soldes cumulés à la date de clôture : le logiciel "
                   "passe une écriture de régularisation pour l'écart avec le journal. Ré-importer le "
                   "même fichier ne change rien.",
                   "Importer la balance N…", self.import_closing, "balance")
        layout.addStretch()

    def _card(self, layout, title, text, btn_text, slot, template_kind):
        frame = QFrame()
        frame.setStyleSheet("QFrame { border:1px solid #d0d0d0; border-radius:6px; background:white; }")
        v = QVBoxLayout(frame)
        t = QLabel(title)
        t.setFont(QFont("Segoe UI", 13, QFont.Bold))
        t.setStyleSheet("border:none; color:#1F3D2E;")
        d = QLabel(text)
        d.setWordWrap(True)
        d.setStyleSheet("border:none;")
        v.addWidget(t)
        v.addWidget(d)
        row = QHBoxLayout()
        b = QPushButton(btn_text)
        b.setStyleSheet("background:#2CA01C; color:white; padding:8px 16px; border-radius:4px;")
        b.clicked.connect(slot)
        m = QPushButton("Modèle Excel")
        m.setStyleSheet("background:#6c757d; color:white; padding:8px 16px; border-radius:4px;")
        m.clicked.connect(lambda _=False, k=template_kind: self.save_template(k))
        row.addWidget(b)
        row.addWidget(m)
        row.addStretch()
        v.addLayout(row)
        layout.addWidget(frame)

    # ------------------------------------------------------------------ #
    def save_template(self, kind):
        name = "Modele_ecritures.xlsx" if kind == "entries" else "Modele_balance.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le modèle", name, "Excel (*.xlsx)")
        if path:
            im.export_template(kind, path)
            QMessageBox.information(self, "Modèle enregistré", path)

    def _pick_file(self, title):
        path, _ = QFileDialog.getOpenFileName(self, title, "", "Excel (*.xlsx)")
        return path

    def _run(self, build_plan):
        """build_plan() -> Plan ; affiche le résumé, demande confirmation, applique."""
        try:
            plan = build_plan()
        except im.ImportDataError as e:
            QMessageBox.critical(self, "Fichier non reconnu", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Erreur de lecture", f"{type(e).__name__}: {e}")
            return
        if plan.errors:
            QMessageBox.critical(
                self, "Import impossible — rien n'a été importé",
                "Corrigez le fichier (ou le plan comptable) puis recommencez :\n\n• "
                + "\n• ".join(plan.errors))
            return
        if plan.apply is None:
            QMessageBox.information(self, "Rien à importer", plan.summary)
            return
        text = plan.summary
        if plan.warnings:
            text += "\n\nÀ noter :\n• " + "\n• ".join(plan.warnings)
        text += "\n\nConfirmer l'import ?"
        if QMessageBox.question(self, "Confirmer l'import", text) != QMessageBox.Yes:
            return
        try:
            msg = plan.apply()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Import annulé :\n{e}")
            return
        QMessageBox.information(self, "Import terminé", msg)

    def import_entries(self):
        path = self._pick_file("Fichier des écritures comptables")
        if path:
            self._run(lambda: im.prepare_entries(self.db, path))

    def import_opening(self):
        path = self._pick_file("Fichier de la balance N-1")
        if not path:
            return
        default = QDate(date.today().year, 1, 1)
        dlg = _OptionsDialog(self, "Balance N-1", "Date des à-nouveaux :", default)
        if dlg.exec_() == QDialog.Accepted:
            self._run(lambda: im.prepare_opening_balance(self.db, path, dlg.iso_date()))

    def import_closing(self):
        path = self._pick_file("Fichier de la balance N")
        if not path:
            return
        default = QDate(date.today().year, 12, 31)
        dlg = _OptionsDialog(self, "Balance N", "Date de clôture :", default,
                             "Remettre à zéro les comptes absents du fichier")
        if dlg.exec_() == QDialog.Accepted:
            self._run(lambda: im.prepare_closing_balance(
                self.db, path, dlg.iso_date(), zero_missing=dlg.check.isChecked()))

    def refresh(self):
        pass
