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


def create_bill(db, vendor_id, date_str, due_date, lines, ap_account_id,
                 number="", memo="", currency="GHS"):
    """
    Facture fournisseur à crédit (paiement différé).
    lines: [{account_id (charge ou compte stock si item), description, qty, unit_cost, item_id?}]
    Écriture : Débit Charges/Stock (au coût) / Crédit Comptes fournisseurs.
    Si une ligne référence un article de type 'Stock', le stock est mis à jour (entrée).
    """
    total = round(sum((l.get("qty") or 1) * (l.get("unit_cost") or 0) for l in lines), 2)
    if total <= 0:
        raise LedgerError("Le total de la facture fournisseur doit être positif")

    je_lines = []
    for l in lines:
        amt = round((l.get("qty") or 1) * (l.get("unit_cost") or 0), 2)
        if amt:
            je_lines.append({"account_id": l["account_id"], "debit": amt, "credit": 0,
                              "description": l.get("description", "")})
    je_lines.append({"account_id": ap_account_id, "debit": 0, "credit": total,
                      "description": f"Facture fournisseur {number or ''}".strip()})

    entry_id = post_journal_entry(
        db, date_str, "FACTURE_FOURNISSEUR", je_lines, doc_number=number, memo=memo,
        vendor_id=vendor_id,
    )

    bill_id = db.execute(
        """INSERT INTO bills (number, vendor_id, date, due_date, currency, memo,
                               total, paid, status, entry_id)
           VALUES (?,?,?,?,?,?,?,0,'Ouverte',?)""",
        (number, vendor_id, date_str, due_date, currency, memo, total, entry_id),
    )
    for l in lines:
        amt = round((l.get("qty") or 1) * (l.get("unit_cost") or 0), 2)
        db.execute(
            """INSERT INTO bill_lines (bill_id, account_id, item_id, description, qty, unit_cost, amount)
               VALUES (?,?,?,?,?,?,?)""",
            (bill_id, l["account_id"], l.get("item_id"), l.get("description", ""),
             l.get("qty", 1), l.get("unit_cost", 0), amt),
        )
        if l.get("item_id"):
            receive_stock(db, l["item_id"], l.get("qty", 1), l.get("unit_cost", 0), date_str,
                          ref_doc=number or f"Bill#{bill_id}")
    return bill_id


def record_vendor_payment(db, vendor_id, bill_id, amount, date_str, payment_account_id, memo=""):
    """Débit Comptes fournisseurs / Crédit Trésorerie, puis met à jour la facture fournisseur."""
    bill = db.query("SELECT * FROM bills WHERE id=?", (bill_id,))[0]
    ap_line = db.query(
        "SELECT jl.account_id FROM journal_lines jl WHERE jl.entry_id=? AND jl.credit>0",
        (bill["entry_id"],),
    )
    ap_account_id = ap_line[0]["account_id"] if ap_line else None
    if ap_account_id is None:
        raise LedgerError("Compte fournisseurs introuvable pour cette facture")

    je_lines = [
        {"account_id": ap_account_id, "debit": amount, "credit": 0, "description": memo},
        {"account_id": payment_account_id, "debit": 0, "credit": amount, "description": memo},
    ]
    post_journal_entry(db, date_str, "PAIEMENT_FOURNISSEUR", je_lines, memo=memo, vendor_id=vendor_id)

    new_paid = round(bill["paid"] + amount, 2)
    status = "Payée" if new_paid >= bill["total"] else ("Partielle" if new_paid > 0 else "Ouverte")
    db.execute("UPDATE bills SET paid=?, status=? WHERE id=?", (new_paid, status, bill_id))


# ---------------------------------------------------------------------- #
# Stock
# ---------------------------------------------------------------------- #
def receive_stock(db, item_id, qty, unit_cost, date_str, ref_doc=""):
    """Entrée de stock (achat) : met à jour la quantité et le coût moyen pondéré (CMP)."""
    item = db.query("SELECT * FROM items WHERE id=?", (item_id,))[0]
    old_qty, old_cost = item["qty_on_hand"], item["cost"]
    new_qty = old_qty + qty
    if new_qty > 0:
        new_cost = round(((old_qty * old_cost) + (qty * unit_cost)) / new_qty, 4)
    else:
        new_cost = old_cost
    db.execute("UPDATE items SET qty_on_hand=?, cost=? WHERE id=?", (new_qty, new_cost, item_id))
    db.execute(
        """INSERT INTO stock_moves (item_id, date, move_type, qty_change, unit_cost, ref_doc)
           VALUES (?,?,?,?,?,?)""",
        (item_id, date_str, "ACHAT", qty, unit_cost, ref_doc),
    )


def issue_stock(db, item_id, qty, date_str, ref_doc=""):
    """Sortie de stock (vente), au coût moyen pondéré actuel. Retourne le coût total sorti."""
    item = db.query("SELECT * FROM items WHERE id=?", (item_id,))[0]
    cost = item["cost"]
    new_qty = item["qty_on_hand"] - qty
    db.execute("UPDATE items SET qty_on_hand=? WHERE id=?", (new_qty, item_id))
    db.execute(
        """INSERT INTO stock_moves (item_id, date, move_type, qty_change, unit_cost, ref_doc)
           VALUES (?,?,?,?,?,?)""",
        (item_id, date_str, "VENTE", -qty, cost, ref_doc),
    )
    return round(qty * cost, 2)


def create_invoice_with_items(db, customer_id, date_str, due_date, lines, ar_account_id,
                               stock_account_id=None, cogs_account_id=None,
                               number="", memo="", currency="GHS"):
    """
    Variante de create_invoice qui gère aussi les articles de stock (sortie de stock + COGS).
    lines: [{account_id (produit), description, qty, unit_price, item_id?}]
    """
    total = round(sum((l["qty"] or 0) * (l["unit_price"] or 0) for l in lines), 2)
    if total <= 0:
        raise LedgerError("Le total de la facture doit être positif")

    je_lines = [{"account_id": ar_account_id, "debit": total, "credit": 0,
                 "description": f"Facture {number or ''}".strip()}]
    total_cogs = 0
    for l in lines:
        amt = round((l["qty"] or 0) * (l["unit_price"] or 0), 2)
        if amt:
            je_lines.append({"account_id": l["account_id"], "debit": 0, "credit": amt,
                              "description": l.get("description", "")})
        if l.get("item_id"):
            item = db.query("SELECT * FROM items WHERE id=?", (l["item_id"],))[0]
            if item["item_type"] == "Stock":
                cogs = issue_stock(db, l["item_id"], l["qty"], date_str, ref_doc=number)
                total_cogs += cogs
    if total_cogs and stock_account_id and cogs_account_id:
        je_lines.append({"account_id": cogs_account_id, "debit": round(total_cogs, 2), "credit": 0,
                          "description": "Coût des marchandises vendues"})
        je_lines.append({"account_id": stock_account_id, "debit": 0, "credit": round(total_cogs, 2),
                          "description": "Sortie de stock"})

    entry_id = post_journal_entry(
        db, date_str, "FACTURE", je_lines, doc_number=number, memo=memo, customer_id=customer_id,
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
            """INSERT INTO invoice_lines (invoice_id, account_id, item_id, description, qty,
                                           unit_price, amount)
               VALUES (?,?,?,?,?,?,?)""",
            (invoice_id, l["account_id"], l.get("item_id"), l.get("description", ""),
             l["qty"], l["unit_price"], amt),
        )
    return invoice_id


# ---------------------------------------------------------------------- #
# Devises
# ---------------------------------------------------------------------- #
def get_exchange_rate(db, currency, as_of_date=None):
    """Dernier taux connu pour 'currency' à la date donnée (ou le plus récent)."""
    if currency == "GHS":
        return 1.0
    sql = "SELECT rate_to_base FROM exchange_rates WHERE currency=?"
    params = [currency]
    if as_of_date:
        sql += " AND date <= ?"
        params.append(as_of_date)
    sql += " ORDER BY date DESC LIMIT 1"
    rows = db.query(sql, params)
    return rows[0]["rate_to_base"] if rows else 1.0


def set_exchange_rate(db, currency, rate, date_str):
    db.execute(
        "INSERT OR REPLACE INTO exchange_rates (currency, rate_to_base, date) VALUES (?,?,?)",
        (currency, rate, date_str),
    )


# ---------------------------------------------------------------------- #
# Rapprochement bancaire
# ---------------------------------------------------------------------- #
def unreconciled_lines(db, account_id, up_to_date=None):
    sql = """SELECT jl.id, je.date, je.doc_type, je.doc_number, jl.description, jl.debit, jl.credit
              FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
              WHERE jl.account_id=? AND jl.reconciled=0"""
    params = [account_id]
    if up_to_date:
        sql += " AND je.date <= ?"
        params.append(up_to_date)
    sql += " ORDER BY je.date"
    return db.query(sql, params)


def finish_reconciliation(db, account_id, statement_date, statement_ending_balance,
                           selected_line_ids):
    """
    Marque les lignes sélectionnées comme rapprochées et enregistre la session.
    Le solde de départ est celui de la DERNIÈRE session terminée pour ce compte
    (0 si c'est le premier rapprochement), pour ne jamais compter deux fois les
    mêmes mouvements.
    """
    prev = db.query(
        "SELECT cleared_balance FROM reconciliations WHERE account_id=? "
        "ORDER BY statement_date DESC, id DESC LIMIT 1",
        (account_id,),
    )
    beginning_balance = prev[0]["cleared_balance"] if prev else 0
    cleared_delta = 0
    rec_id = db.execute(
        """INSERT INTO reconciliations (account_id, statement_date, statement_ending_balance,
                                         beginning_balance, cleared_balance, difference)
           VALUES (?,?,?,?,0,0)""",
        (account_id, statement_date, statement_ending_balance, beginning_balance),
    )
    for line_id in selected_line_ids:
        row = db.query("SELECT debit, credit FROM journal_lines WHERE id=?", (line_id,))[0]
        cleared_delta += row["debit"] - row["credit"]
        db.execute(
            "UPDATE journal_lines SET reconciled=1, reconciliation_id=? WHERE id=?",
            (rec_id, line_id),
        )
    cleared_balance = round(beginning_balance + cleared_delta, 2)
    difference = round(statement_ending_balance - cleared_balance, 2)
    db.execute(
        "UPDATE reconciliations SET cleared_balance=?, difference=? WHERE id=?",
        (cleared_balance, difference, rec_id),
    )
    return {"reconciliation_id": rec_id, "cleared_balance": cleared_balance, "difference": difference}


def _day_before_or_none(date_str):
    return _day_before(date_str) if date_str else None


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
        rate = get_exchange_rate(db, a["currency"], as_of_date)
        results.append({
            "account": a, "balance": round(balance, 2),
            "balance_base": round(balance * rate, 2), "rate": rate,
        })
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
        base_bal = row["balance_base"]  # converti en devise de base (GHS) pour les totaux
        if cat == "Résultat":
            if acc["account_type"] in ("PRODUITS", "AUTRES_PRODUITS"):
                net_income += base_bal
            else:
                net_income -= base_bal
        elif section and row["balance"] != 0:
            # affichage en devise native, mais on garde le montant converti pour les totaux
            sections[section].append((acc, row["balance"], base_bal))

    total_actif_ct = sum(b for _, _, b in sections["Actif à court terme"])
    total_actif_lt = sum(b for _, _, b in sections["Actif à long terme"])
    total_passif_ct = sum(b for _, _, b in sections["Passif à court terme"])
    total_passif_lt = sum(b for _, _, b in sections["Passif à long terme"])
    total_cp = sum(b for _, _, b in sections["Capitaux propres"])

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
        entry = (acc, row["balance"], row["balance_base"])
        if acc["account_type"] == "PRODUITS":
            produits.append(entry)
        elif acc["account_type"] == "COUT_DES_VENTES":
            cout_ventes.append(entry)
        elif acc["account_type"] == "DEPENSES":
            depenses.append(entry)

    total_produits = sum(b for _, _, b in produits)
    total_cout = sum(b for _, _, b in cout_ventes)
    total_dep = sum(b for _, _, b in depenses)
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
