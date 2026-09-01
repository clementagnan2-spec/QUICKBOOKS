"""
Logique métier : création d'écritures équilibrées, factures, dépenses,
et calcul des rapports (Bilan, Compte de résultat, Flux de trésorerie).
"""
from datetime import date
from .database import ACCOUNT_TYPES, DEBIT_NORMAL_TYPES


class LedgerError(Exception):
    pass


def post_journal_entry(db, date_str, doc_type, lines, doc_number="", memo="",
                        site_id=None, class_id=None, customer_id=None, vendor_id=None):
    """
    lines: liste de dicts {account_id, description, debit, credit}
    Vérifie que total débit == total crédit avant d'écrire.
    Retourne l'id de l'écriture créée.
    """
    total_debit = round(sum(l.get("debit", 0) or 0 for l in lines), 2)
    total_credit = round(sum(l.get("credit", 0) or 0 for l in lines), 2)
    if total_debit != total_credit:
        raise LedgerError(
            f"Écriture déséquilibrée : débit={total_debit} crédit={total_credit}"
        )
    if total_debit == 0:
        raise LedgerError("Écriture vide (montant total = 0)")

    entry_id = db.execute(
        """INSERT INTO journal_entries
           (date, doc_type, doc_number, memo, site_id, class_id, customer_id, vendor_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (date_str, doc_type, doc_number, memo, site_id, class_id, customer_id, vendor_id),
    )
    for l in lines:
        db.execute(
            """INSERT INTO journal_lines (entry_id, account_id, description, debit, credit)
               VALUES (?,?,?,?,?)""",
            (entry_id, l["account_id"], l.get("description", ""), l.get("debit", 0) or 0,
             l.get("credit", 0) or 0),
        )
    return entry_id


def create_invoice(db, customer_id, date_str, due_date, lines, ar_account_id,
                    number="", memo="", currency="GHS"):
    """
    lines: [{account_id (compte de produit), description, qty, unit_price}]
    Crée la facture + l'écriture : Débit Comptes clients / Crédit Produits.
    """
    total = round(sum((l["qty"] or 0) * (l["unit_price"] or 0) for l in lines), 2)
    if total <= 0:
        raise LedgerError("Le total de la facture doit être positif")

    je_lines = [{"account_id": ar_account_id, "debit": total, "credit": 0,
                 "description": f"Facture {number or ''}".strip()}]
    for l in lines:
        amt = round((l["qty"] or 0) * (l["unit_price"] or 0), 2)
        if amt:
            je_lines.append({
                "account_id": l["account_id"], "debit": 0, "credit": amt,
                "description": l.get("description", ""),
            })

    entry_id = post_journal_entry(
        db, date_str, "FACTURE", je_lines, doc_number=number, memo=memo,
        customer_id=customer_id,
    )

    invoice_id = db.execute(
        """INSERT INTO invoices (number, customer_id, date, due_date, currency, memo,
                                  total, paid, status, entry_id)
           VALUES (?,?,?,?,?,?,?,0,'Ouverte',?)""",
        (number, customer_id, date_str, due_date, currency, memo, total, entry_id),
    )
    for l in lines:
        amt = round((l["qty"] or 0) * (l["unit_price"] or 0), 2)
        db.execute(
            """INSERT INTO invoice_lines (invoice_id, account_id, description, qty, unit_price, amount)
               VALUES (?,?,?,?,?,?)""",
            (invoice_id, l["account_id"], l.get("description", ""), l["qty"], l["unit_price"], amt),
        )
    return invoice_id


def create_expense(db, payment_account_id, date_str, lines, vendor_id=None,
                    number="", memo="", currency="GHS", site_id=None, class_id=None):
    """
    Achat comptant / Chèque : Débit compte(s) de charge, Crédit compte de trésorerie.
    lines: [{account_id, description, amount}]
    """
    total = round(sum(l["amount"] or 0 for l in lines), 2)
    if total <= 0:
        raise LedgerError("Le total de la dépense doit être positif")

    je_lines = []
    for l in lines:
        if l["amount"]:
            je_lines.append({"account_id": l["account_id"], "debit": l["amount"], "credit": 0,
                              "description": l.get("description", "")})
    je_lines.append({"account_id": payment_account_id, "debit": 0, "credit": total,
                      "description": f"Paiement {memo or ''}".strip()})

    entry_id = post_journal_entry(
        db, date_str, "ACHAT", je_lines, doc_number=number, memo=memo,
        vendor_id=vendor_id, site_id=site_id, class_id=class_id,
    )

    expense_id = db.execute(
        """INSERT INTO expenses (number, vendor_id, payment_account_id, date, currency,
                                  memo, total, entry_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (number, vendor_id, payment_account_id, date_str, currency, memo, total, entry_id),
    )
    for l in lines:
        if l["amount"]:
            db.execute(
                """INSERT INTO expense_lines (expense_id, account_id, description, amount)
                   VALUES (?,?,?,?)""",
                (expense_id, l["account_id"], l.get("description", ""), l["amount"]),
            )
    return expense_id


def record_customer_payment(db, customer_id, invoice_id, amount, date_str, deposit_account_id, memo=""):
    """Débit Trésorerie / Crédit Comptes clients, puis met à jour la facture."""
    inv = db.query("SELECT * FROM invoices WHERE id=?", (invoice_id,))[0]
    ar_line = db.query(
        "SELECT jl.account_id FROM journal_lines jl WHERE jl.entry_id=? AND jl.debit>0",
        (inv["entry_id"],),
    )
    ar_account_id = ar_line[0]["account_id"] if ar_line else None
    if ar_account_id is None:
        raise LedgerError("Compte clients introuvable pour cette facture")

    je_lines = [
        {"account_id": deposit_account_id, "debit": amount, "credit": 0, "description": memo},
        {"account_id": ar_account_id, "debit": 0, "credit": amount, "description": memo},
    ]
    post_journal_entry(db, date_str, "PAIEMENT_CLIENT", je_lines, memo=memo, customer_id=customer_id)

    new_paid = round(inv["paid"] + amount, 2)
    status = "Payée" if new_paid >= inv["total"] else ("Partielle" if new_paid > 0 else "Ouverte")
    db.execute("UPDATE invoices SET paid=?, status=? WHERE id=?", (new_paid, status, invoice_id))


# ---------------------------------------------------------------------- #
# Rapports
# ---------------------------------------------------------------------- #
def account_balance(db, account_id, as_of_date=None):
    sql = """SELECT COALESCE(SUM(debit),0) d, COALESCE(SUM(credit),0) c
              FROM journal_lines jl JOIN journal_entries je ON jl.entry_id=je.id
              WHERE jl.account_id=?"""
    params = [account_id]
    if as_of_date:
        sql += " AND je.date <= ?"
        params.append(as_of_date)
    row = db.query(sql, params)[0]
    return round(row["d"] - row["c"], 2)  # positif = solde débiteur naturel


def trial_balance(db, as_of_date=None, start_date=None):
    """Retourne solde par compte, en tenant compte du sens normal (débit ou crédit positif)."""
    accounts = db.query("SELECT * FROM accounts WHERE is_active=1 ORDER BY account_type, name")
    results = []
    for a in accounts:
        sql = """SELECT COALESCE(SUM(debit),0) d, COALESCE(SUM(credit),0) c
                  FROM journal_lines jl JOIN journal_entries je ON jl.entry_id=je.id
                  WHERE jl.account_id=?"""
        params = [a["id"]]
        if start_date:
            sql += " AND je.date >= ?"
            params.append(start_date)
        if as_of_date:
            sql += " AND je.date <= ?"
            params.append(as_of_date)
        row = db.query(sql, params)[0]
        net_debit = row["d"] - row["c"]
        normal_debit = a["account_type"] in DEBIT_NORMAL_TYPES
        balance = net_debit if normal_debit else -net_debit
        results.append({"account": a, "balance": round(balance, 2)})
    return results


def balance_sheet(db, as_of_date=None):
    """Bilan : Actifs / Passifs / Capitaux propres, au 'as_of_date' (inclut le résultat cumulé)."""
    tb = trial_balance(db, as_of_date=as_of_date)
    sections = {"Actif à court terme": [], "Actif à long terme": [],
                "Passif à court terme": [], "Passif à long terme": [],
                "Capitaux propres": []}
    net_income = 0
    for row in tb:
        acc = row["account"]
        cat, section = ACCOUNT_TYPES.get(acc["account_type"], ("Résultat", None))
        if cat == "Résultat":
            if acc["account_type"] in ("PRODUITS", "AUTRES_PRODUITS"):
                net_income += row["balance"]
            else:
                net_income -= row["balance"]
        elif section and row["balance"] != 0:
            sections[section].append((acc, row["balance"]))

    total_actif_ct = sum(b for _, b in sections["Actif à court terme"])
    total_actif_lt = sum(b for _, b in sections["Actif à long terme"])
    total_passif_ct = sum(b for _, b in sections["Passif à court terme"])
    total_passif_lt = sum(b for _, b in sections["Passif à long terme"])
    total_cp = sum(b for _, b in sections["Capitaux propres"])

    return {
        "sections": sections,
        "net_income": round(net_income, 2),
        "total_actif": round(total_actif_ct + total_actif_lt, 2),
        "total_passif": round(total_passif_ct + total_passif_lt, 2),
        "total_capitaux_propres": round(total_cp + net_income, 2),
    }


def income_statement(db, start_date, end_date):
    """Compte de résultat entre deux dates."""
    tb = trial_balance(db, as_of_date=end_date, start_date=start_date)
    produits, cout_ventes, depenses = [], [], []
    for row in tb:
        acc = row["account"]
        if row["balance"] == 0:
            continue
        if acc["account_type"] == "PRODUITS":
            produits.append((acc, row["balance"]))
        elif acc["account_type"] == "COUT_DES_VENTES":
            cout_ventes.append((acc, row["balance"]))
        elif acc["account_type"] == "DEPENSES":
            depenses.append((acc, row["balance"]))

    total_produits = sum(b for _, b in produits)
    total_cout = sum(b for _, b in cout_ventes)
    total_dep = sum(b for _, b in depenses)
    marge_brute = total_produits - total_cout
    resultat_net = marge_brute - total_dep

    return {
        "produits": produits, "cout_ventes": cout_ventes, "depenses": depenses,
        "total_produits": round(total_produits, 2), "total_cout_ventes": round(total_cout, 2),
        "total_depenses": round(total_dep, 2), "marge_brute": round(marge_brute, 2),
        "resultat_net": round(resultat_net, 2),
    }


def cash_flow(db, start_date, end_date):
    """Version simplifiée : variation de chaque compte de trésorerie sur la période."""
    cash_accounts = db.query("SELECT * FROM accounts WHERE account_type='TRESORERIE' AND is_active=1")
    rows = []
    total_start = 0
    total_end = 0
    for a in cash_accounts:
        bal_start = account_balance(db, a["id"], as_of_date=_day_before(start_date))
        bal_end = account_balance(db, a["id"], as_of_date=end_date)
        rows.append({"account": a, "start": bal_start, "end": bal_end, "change": round(bal_end - bal_start, 2)})
        total_start += bal_start
        total_end += bal_end
    return {"rows": rows, "total_start": round(total_start, 2), "total_end": round(total_end, 2),
            "net_change": round(total_end - total_start, 2)}


def _day_before(date_str):
    from datetime import datetime, timedelta
    d = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)
    return d.strftime("%Y-%m-%d")
