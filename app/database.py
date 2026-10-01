"""
Couche base de données (SQLite) pour GH-Compta.
Comptabilité en partie double : chaque opération (facture, achat, paiement...)
génère des écritures de journal équilibrées (total débit = total crédit).
"""
import sqlite3
import os
from datetime import date

DB_FILENAME = "gh_compta.db"


def get_db_path():
    """Stocke le fichier de base à côté de l'exécutable / du script."""
    base = os.environ.get("GHCOMPTA_DATA_DIR") or os.path.expanduser("~/GH-Compta")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, DB_FILENAME)


class Database:
    def __init__(self, path=None):
        self.path = path or get_db_path()
        first_time = not os.path.exists(self.path)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        self._create_schema()
        self._migrate_accounts()
        if first_time:
            self._seed_accounts()
            self._seed_misc()

    # ------------------------------------------------------------------ #
    # Schéma
    # ------------------------------------------------------------------ #
    def _create_schema(self):
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT,
                name TEXT NOT NULL,
                account_type TEXT NOT NULL,   -- catégorie principale (voir ACCOUNT_TYPES)
                detail_type TEXT,
                description TEXT,
                currency TEXT DEFAULT 'GHS',
                is_active INTEGER DEFAULT 1,
                gaap_section TEXT,            -- CA/NCA/CL/LTL/EQ/REV/COGS/OPEX/OINC/OEXP/TAX
                syc_code TEXT,                -- compte SYCEBNL correspondant
                syc_name TEXT,
                mapping_type TEXT,
                coefficient REAL DEFAULT 1,
                review_status TEXT,
                remark TEXT
            );

            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                address TEXT,
                currency TEXT DEFAULT 'GHS',
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                address TEXT,
                currency TEXT DEFAULT 'GHS',
                is_active INTEGER DEFAULT 1
            );

            -- En-tête d'écriture de journal (une opération = 1 entry + plusieurs lines)
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                doc_type TEXT NOT NULL,     -- FACTURE, ACHAT, PAIEMENT_CLIENT, PAIEMENT_FOURN, OD, ...
                doc_number TEXT,
                memo TEXT,
                site_id INTEGER,
                class_id INTEGER,
                customer_id INTEGER,
                vendor_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (site_id) REFERENCES sites(id),
                FOREIGN KEY (class_id) REFERENCES classes(id),
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (vendor_id) REFERENCES vendors(id)
            );

            CREATE TABLE IF NOT EXISTS journal_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                description TEXT,
                debit REAL NOT NULL DEFAULT 0,
                credit REAL NOT NULL DEFAULT 0,
                reconciled INTEGER DEFAULT 0,
                reconciliation_id INTEGER,
                FOREIGN KEY (entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT,
                customer_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                due_date TEXT,
                currency TEXT DEFAULT 'GHS',
                memo TEXT,
                total REAL DEFAULT 0,
                paid REAL DEFAULT 0,
                status TEXT DEFAULT 'Ouverte',   -- Ouverte / Payée / Partielle
                entry_id INTEGER,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (entry_id) REFERENCES journal_entries(id)
            );

            CREATE TABLE IF NOT EXISTS invoice_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                item_id INTEGER,
                description TEXT,
                qty REAL DEFAULT 1,
                unit_price REAL DEFAULT 0,
                amount REAL DEFAULT 0,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                FOREIGN KEY (item_id) REFERENCES items(id)
            );

            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT,
                vendor_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                due_date TEXT,
                currency TEXT DEFAULT 'GHS',
                memo TEXT,
                total REAL DEFAULT 0,
                paid REAL DEFAULT 0,
                status TEXT DEFAULT 'Ouverte',
                entry_id INTEGER,
                FOREIGN KEY (vendor_id) REFERENCES vendors(id),
                FOREIGN KEY (entry_id) REFERENCES journal_entries(id)
            );

            CREATE TABLE IF NOT EXISTS bill_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                item_id INTEGER,
                description TEXT,
                qty REAL DEFAULT 1,
                unit_cost REAL DEFAULT 0,
                amount REAL DEFAULT 0,
                FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                FOREIGN KEY (item_id) REFERENCES items(id)
            );

            -- Articles (produits/services) pour la gestion de stock
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT,
                name TEXT NOT NULL,
                item_type TEXT NOT NULL DEFAULT 'Stock',  -- Stock / Service / Non-stock
                income_account_id INTEGER,     -- compte de produit utilisé à la vente
                expense_account_id INTEGER,    -- compte de charge (COGS) utilisé à la vente
                asset_account_id INTEGER,      -- compte d'actif "Stock" utilisé à l'achat
                sales_price REAL DEFAULT 0,
                cost REAL DEFAULT 0,           -- coût moyen unitaire actuel
                qty_on_hand REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (income_account_id) REFERENCES accounts(id),
                FOREIGN KEY (expense_account_id) REFERENCES accounts(id),
                FOREIGN KEY (asset_account_id) REFERENCES accounts(id)
            );

            -- Historique des mouvements de stock (pour audit et coût moyen pondéré)
            CREATE TABLE IF NOT EXISTS stock_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                move_type TEXT NOT NULL,  -- ACHAT / VENTE / AJUSTEMENT
                qty_change REAL NOT NULL, -- positif = entrée, négatif = sortie
                unit_cost REAL DEFAULT 0,
                ref_doc TEXT,
                FOREIGN KEY (item_id) REFERENCES items(id)
            );

            -- Taux de change vers la devise de base (GHS)
            CREATE TABLE IF NOT EXISTS exchange_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                currency TEXT NOT NULL,
                rate_to_base REAL NOT NULL,   -- 1 unité de 'currency' = X GHS
                date TEXT NOT NULL,
                UNIQUE(currency, date)
            );

            -- Sessions de rapprochement bancaire
            CREATE TABLE IF NOT EXISTS reconciliations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                statement_date TEXT NOT NULL,
                statement_ending_balance REAL NOT NULL,
                beginning_balance REAL NOT NULL,
                cleared_balance REAL NOT NULL,
                difference REAL NOT NULL,
                status TEXT DEFAULT 'Terminé',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );

            -- Dépense payée directement (Achat comptant / Chèque), sans passer par "Fournisseur à payer"
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT,
                vendor_id INTEGER,
                payment_account_id INTEGER NOT NULL,  -- compte de trésorerie utilisé
                date TEXT NOT NULL,
                currency TEXT DEFAULT 'GHS',
                memo TEXT,
                total REAL DEFAULT 0,
                entry_id INTEGER,
                FOREIGN KEY (vendor_id) REFERENCES vendors(id),
                FOREIGN KEY (payment_account_id) REFERENCES accounts(id),
                FOREIGN KEY (entry_id) REFERENCES journal_entries(id)
            );

            CREATE TABLE IF NOT EXISTS expense_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                description TEXT,
                amount REAL DEFAULT 0,
                FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );
            """
        )
        c.commit()

    def _migrate_accounts(self):
        """Ajoute les colonnes de correspondance US GAAP / SYCEBNL aux bases créées avant cette version."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(accounts)").fetchall()}
        wanted = [
            ("gaap_section", "TEXT"), ("syc_code", "TEXT"), ("syc_name", "TEXT"),
            ("mapping_type", "TEXT"), ("coefficient", "REAL DEFAULT 1"),
            ("review_status", "TEXT"), ("remark", "TEXT"),
        ]
        for name, decl in wanted:
            if name not in cols:
                self.conn.execute(f"ALTER TABLE accounts ADD COLUMN {name} {decl}")
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Données de départ : plan comptable US GAAP <-> SYCEBNL
    # ------------------------------------------------------------------ #
    def _seed_accounts(self):
        from .chart_plan import load_standard_chart
        load_standard_chart(self)

    def _seed_misc(self):
        self.conn.execute("INSERT OR IGNORE INTO classes (name) VALUES ('programme')")
        self.conn.execute("INSERT OR IGNORE INTO sites (name) VALUES ('ouaga')")
        # Taux de change de départ (modifiable dans le module Devises) — GHS = devise de base
        self.conn.execute(
            "INSERT OR IGNORE INTO exchange_rates (currency, rate_to_base, date) VALUES ('GHS', 1.0, ?)",
            (date.today().isoformat(),),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO exchange_rates (currency, rate_to_base, date) VALUES ('USD', 15.0, ?)",
            (date.today().isoformat(),),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Helpers génériques
    # ------------------------------------------------------------------ #
    def query(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        return cur.fetchall()

    def execute(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur.lastrowid

    def close(self):
        self.conn.close()


# Catégories de comptes -> section du bilan / compte de résultat
ACCOUNT_TYPES = {
    "TRESORERIE": ("Actif", "Actif à court terme"),
    "COMPTES_CLIENTS": ("Actif", "Actif à court terme"),
    "STOCK": ("Actif", "Actif à court terme"),
    "AUTRE_ACTIF_CT": ("Actif", "Actif à court terme"),
    "ACTIF_LONG_TERME": ("Actif", "Actif à long terme"),
    "COMPTES_FOURNISSEURS": ("Passif", "Passif à court terme"),
    "CARTE_CREDIT": ("Passif", "Passif à court terme"),
    "PASSIF_COURT_TERME": ("Passif", "Passif à court terme"),
    "PASSIF_LONG_TERME": ("Passif", "Passif à long terme"),
    "CAPITAUX_PROPRES": ("Capitaux propres", "Capitaux propres"),
    "PRODUITS": ("Résultat", "Produits"),
    "COUT_DES_VENTES": ("Résultat", "Coût des ventes"),
    "DEPENSES": ("Résultat", "Dépenses"),
    "AUTRES_PRODUITS": ("Résultat", "Autres produits"),
    "AUTRES_DEPENSES": ("Résultat", "Autres dépenses"),
}

# Types de comptes dont le solde normal est DEBIT (Actif, Dépenses, Coût des ventes)
DEBIT_NORMAL_TYPES = {
    "TRESORERIE", "COMPTES_CLIENTS", "STOCK", "AUTRE_ACTIF_CT", "ACTIF_LONG_TERME",
    "DEPENSES", "COUT_DES_VENTES", "AUTRES_DEPENSES",
}
