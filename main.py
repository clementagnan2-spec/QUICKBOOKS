"""
GH-Compta — Logiciel de comptabilité (style QuickBooks) en Python + PyQt5.
Point d'entrée de l'application.
"""
import sys
from PyQt5.QtWidgets import QApplication
from app.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
