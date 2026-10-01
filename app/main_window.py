from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QStackedWidget, QLabel, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from .database import Database
from .pages.dashboard import DashboardPage
from .pages.accounts_page import AccountsPage
from .pages.customers_page import CustomersPage
from .pages.vendors_page import VendorsPage
from .pages.invoices_page import InvoicesPage
from .pages.expenses_page import ExpensesPage
from .pages.bills_page import BillsPage
from .pages.items_page import ItemsPage
from .pages.reconciliation_page import ReconciliationPage
from .pages.currency_page import CurrencyPage
from .pages.journal_page import JournalPage
from .pages.reports_page import ReportsPage
from .pages.import_page import ImportPage

NAV_ITEMS = [
    ("Tableau de bord", "dashboard"),
    ("Plan comptable", "accounts"),
    ("Clients", "customers"),
    ("Fournisseurs", "vendors"),
    ("Ventes / Factures", "invoices"),
    ("Dépenses / Achats", "expenses"),
    ("Factures fournisseurs", "bills"),
    ("Stock / Articles", "items"),
    ("Rapprochement bancaire", "reconciliation"),
    ("Devises", "currency"),
    ("Journal général", "journal"),
    ("Rapports", "reports"),
    ("Importer des données", "import"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GH-Compta — Comptabilité")
        self.resize(1280, 800)
        self.setMinimumSize(1000, 600)

        self.db = Database()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Barre latérale ---
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("background-color:#1F3D2E;")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        title = QLabel("  GH-Compta")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet("color:white; padding:20px 10px;")
        sb_layout.addWidget(title)

        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet(
            """
            QListWidget { background-color:#1F3D2E; border:none; color:white; font-size:13px;
                          outline:none; }
            QListWidget::item { padding:10px 20px; }
            QListWidget::item:selected { background-color:#2CA01C; color:white; }
            QListWidget::item:hover { background-color:#2b5240; }
            QScrollBar:vertical { background:#1F3D2E; width:12px; margin:0; }
            QScrollBar::handle:vertical { background:#4a7a63; min-height:24px; border-radius:5px; }
            QScrollBar::handle:vertical:hover { background:#5c9a7d; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:none; }
            """
        )
        self.nav_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        for label, _key in NAV_ITEMS:
            QListWidgetItem(label, self.nav_list)
        sb_layout.addWidget(self.nav_list)

        layout.addWidget(sidebar)

        # --- Zone de contenu ---
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self.pages = {}
        self._add_page("dashboard", DashboardPage(self.db))
        self._add_page("accounts", AccountsPage(self.db))
        self._add_page("customers", CustomersPage(self.db))
        self._add_page("vendors", VendorsPage(self.db))
        self._add_page("invoices", InvoicesPage(self.db))
        self._add_page("expenses", ExpensesPage(self.db))
        self._add_page("bills", BillsPage(self.db))
        self._add_page("items", ItemsPage(self.db))
        self._add_page("reconciliation", ReconciliationPage(self.db))
        self._add_page("currency", CurrencyPage(self.db))
        self._add_page("journal", JournalPage(self.db))
        self._add_page("reports", ReportsPage(self.db))
        self._add_page("import", ImportPage(self.db))

        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        self.nav_list.setCurrentRow(0)

    def _add_page(self, key, widget):
        self.pages[key] = widget
        self.stack.addWidget(widget)

    def _on_nav_changed(self, row):
        key = NAV_ITEMS[row][1]
        widget = self.pages[key]
        if hasattr(widget, "refresh"):
            widget.refresh()
        self.stack.setCurrentWidget(widget)

    def closeEvent(self, event):
        self.db.close()
        event.accept()
