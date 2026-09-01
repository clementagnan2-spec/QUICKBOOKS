"""
GH-Compta — Logiciel de comptabilité (style QuickBooks) en Python + PyQt5.
Point d'entrée de l'application.
"""
import sys
import os
import traceback
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMessageBox
from app.main_window import MainWindow


def _log_path():
    base = os.environ.get("GHCOMPTA_DATA_DIR") or os.path.expanduser("~/GH-Compta")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "erreurs.log")


def install_exception_hook():
    """
    Empêche PyQt5 de fermer brutalement l'application quand une exception
    survient dans un gestionnaire d'événement (clic, saisie, etc.).
    Affiche une boîte de dialogue et enregistre le détail dans erreurs.log
    au lieu de planter le logiciel.
    """
    def handle_exception(exc_type, exc_value, exc_tb):
        message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open(_log_path(), "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now().isoformat()} ---\n{message}\n")
        except Exception:
            pass
        print(message, file=sys.stderr)
        try:
            QMessageBox.critical(
                None, "Une erreur est survenue",
                "Une opération a échoué et a été annulée.\n\n"
                f"{exc_type.__name__}: {exc_value}\n\n"
                f"Détail enregistré dans : {_log_path()}",
            )
        except Exception:
            pass  # si même l'affichage échoue, on évite de planter deux fois

    sys.excepthook = handle_exception


def main():
    install_exception_hook()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
