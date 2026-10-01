"""
Rapports financiers en double version : US GAAP et SYCEBNL.

Les deux versions sont calculées à partir des MÊMES écritures du journal ;
seul le regroupement des comptes change (section US GAAP d'un côté, compte
SYCEBNL de l'autre, selon le plan comptable). Tous les montants sont
convertis dans la devise de base.

Chaque rapport est une structure indépendante de l'affichage :
    {"title": str, "subtitle": str, "rows": [ {kind, code, label, amount}, ... ]}
avec kind dans : section | line | subtotal | total | blank | warn
"""
from datetime import datetime, timedelta

from .logic import get_exchange_rate
from .chart_plan import (
    ASSET_SECTIONS, INCOME_SECTIONS, EXPENSE_SECTIONS,
    BS_ASSET_GROUPS, BS_LIAB_GROUPS,
    effective_section, has_syc, syc_balance_group, syc_result_group,
)

BASE = "GHS"
GAAP = "GAAP"
SYCEBNL = "SYCEBNL"
FRAMEWORKS = (GAAP, SYCEBNL)
FRAMEWORK_LABELS = {GAAP: "US GAAP", SYCEBNL: "SYCEBNL"}
TOLERANCE = 0.005


# ---------------------------------------------------------------------- #
# Calculs de base
# ---------------------------------------------------------------------- #
def _net_debits(db, as_of=None, start=None):
    """Liste de (compte, solde net débit converti en devise de base) pour les comptes mouvementés."""
    sql = """SELECT a.*, COALESCE(SUM(x.debit),0) AS d, COALESCE(SUM(x.credit),0) AS c
             FROM accounts a
             LEFT JOIN (SELECT jl.account_id, jl.debit, jl.credit
                        FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
                        WHERE (? IS NULL OR je.date >= ?) AND (? IS NULL OR je.date <= ?)) x
                    ON x.account_id = a.id
             GROUP BY a.id ORDER BY a.number, a.name"""
    rows = db.query(sql, (start, start, as_of, as_of))
    rates = {}
    out = []
    for r in rows:
        cur = r["currency"] or BASE
        if cur not in rates:
            rates[cur] = get_exchange_rate(db, cur, as_of)
        nd = round((r["d"] - r["c"]) * rates[cur], 2)
        if abs(nd) >= TOLERANCE:
            out.append((r, nd))
    return out


def _signed(section, nd):
    """Montant présenté positivement dans le sens normal de la section."""
    return nd if section in ASSET_SECTIONS or section in EXPENSE_SECTIONS else -nd


def _net_income(items):
    total = 0.0
    for acc, nd in items:
        sec = effective_section(acc)
        if sec in INCOME_SECTIONS:
            total += -nd
        elif sec in EXPENSE_SECTIONS:
            total -= nd
    return round(total, 2)


def _day_before(date_str):
    return (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------- #
# Constructeur de lignes
# ---------------------------------------------------------------------- #
class _Rows:
    def __init__(self):
        self.rows = []

    def add(self, kind, label="", amount=None, code=""):
        self.rows.append({"kind": kind, "code": code, "label": label, "amount": amount})

    def section(self, label): self.add("section", label)
    def line(self, label, amount, code=""): self.add("line", label, amount, code)
    def subtotal(self, label, amount): self.add("subtotal", label, amount)
    def total(self, label, amount): self.add("total", label, amount)
    def blank(self): self.add("blank")
    def warn(self, label, amount=None): self.add("warn", label, amount)


def _sycebnl_lines(entries):
    """
    entries: [(acc, montant)] -> lignes regroupées par compte SYCEBNL, coefficient appliqué.
    Les comptes sans correspondance restent isolés, signalés « à reclasser ».
    Retourne [(code, libellé, montant)] triées par code.
    """
    agg = {}
    for acc, amt in entries:
        coef = acc["coefficient"] if acc["coefficient"] is not None else 1.0
        amt = amt * coef
        if has_syc(acc["syc_code"]):
            key = (0, acc["syc_code"].strip())
            label = acc["syc_name"] or acc["name"]
            code = acc["syc_code"].strip()
        else:
            key = (1, f"{acc['number'] or ''}|{acc['name']}")
            label = f"À reclasser — {acc['name']}"
            code = "N/A"
        if key in agg:
            agg[key][2] += amt
        else:
            agg[key] = [code, label, amt]
    return [(c, l, round(a, 2)) for _, (c, l, a) in sorted(agg.items())]


# ---------------------------------------------------------------------- #
# BILAN
# ---------------------------------------------------------------------- #
def balance_sheet_report(db, as_of, framework):
    items = _net_debits(db, as_of=as_of)
    net_income = _net_income(items)
    bs_items = [(a, nd) for a, nd in items
                if effective_section(a) not in INCOME_SECTIONS + EXPENSE_SECTIONS]
    return (_balance_gaap if framework == GAAP else _balance_sycebnl)(bs_items, net_income, as_of)


def _balance_gaap(bs_items, net_income, as_of):
    R = _Rows()
    by_sec = {}
    for acc, nd in bs_items:
        sec = effective_section(acc)
        by_sec.setdefault(sec, []).append((acc, _signed(sec, nd)))

    def block(sec, title, total_label):
        entries = by_sec.get(sec, [])
        R.section(title)
        for acc, amt in entries:
            R.line(acc["name"], amt, acc["number"] or "")
        tot = round(sum(a for _, a in entries), 2)
        R.subtotal(total_label, tot)
        return tot

    R.section("ASSETS")
    ca = block("CA", "Current assets", "Total current assets")
    nca = block("NCA", "Non-current assets", "Total non-current assets")
    total_assets = round(ca + nca, 2)
    R.total("TOTAL ASSETS", total_assets)
    R.blank()
    R.section("LIABILITIES AND EQUITY")
    cl = block("CL", "Current liabilities", "Total current liabilities")
    ltl = block("LTL", "Long-term liabilities", "Total long-term liabilities")
    R.subtotal("Total liabilities", round(cl + ltl, 2))
    eq_entries = by_sec.get("EQ", [])
    R.section("Equity")
    for acc, amt in eq_entries:
        R.line(acc["name"], amt, acc["number"] or "")
    R.line("Net income (cumulative to date)", net_income)
    eq = round(sum(a for _, a in eq_entries) + net_income, 2)
    R.subtotal("Total equity", eq)
    total_le = round(cl + ltl + eq, 2)
    R.total("TOTAL LIABILITIES AND EQUITY", total_le)
    if abs(total_assets - total_le) > TOLERANCE:
        R.warn("Out of balance (assets − liabilities and equity)", round(total_assets - total_le, 2))
    return {"title": "Balance Sheet",
            "subtitle": f"As of {as_of} — amounts in {BASE}", "rows": R.rows,
            "totals": {"assets": total_assets, "liab_equity": total_le, "net_income": net_income}}


def _balance_sycebnl(bs_items, net_income, as_of):
    R = _Rows()
    groups = {}
    for acc, nd in bs_items:
        sec = effective_section(acc)
        groups.setdefault(syc_balance_group(acc), []).append((acc, _signed(sec, nd)))

    def block(group, extra=None):
        lines = _sycebnl_lines(groups.get(group, []))
        R.section(group)
        for code, label, amt in lines:
            R.line(label, amt, code)
        tot = sum(a for _, _, a in lines)
        if extra:
            R.line(extra[0], extra[1])
            tot += extra[1]
        tot = round(tot, 2)
        R.subtotal(f"Total {group}", tot)
        return tot

    R.section("ACTIF")
    total_actif = round(sum(block(g) for g in BS_ASSET_GROUPS), 2)
    R.total("TOTAL ACTIF", total_actif)
    R.blank()
    R.section("PASSIF")
    parts = [block(BS_LIAB_GROUPS[0], ("Excédent (déficit) net de l'exercice — cumul", net_income))]
    parts += [block(g) for g in BS_LIAB_GROUPS[1:]]
    total_passif = round(sum(parts), 2)
    R.total("TOTAL PASSIF", total_passif)
    if abs(total_actif - total_passif) > TOLERANCE:
        R.warn("Écart d'équilibre (actif − passif) : vérifier les coefficients de correspondance",
               round(total_actif - total_passif, 2))
    return {"title": "Bilan SYCEBNL",
            "subtitle": f"Au {as_of} — montants en {BASE}", "rows": R.rows,
            "totals": {"assets": total_actif, "liab_equity": total_passif, "net_income": net_income}}


# ---------------------------------------------------------------------- #
# COMPTE DE RÉSULTAT
# ---------------------------------------------------------------------- #
def income_statement_report(db, start, end, framework):
    items = [(a, nd) for a, nd in _net_debits(db, as_of=end, start=start)
             if effective_section(a) in INCOME_SECTIONS + EXPENSE_SECTIONS]
    return (_income_gaap if framework == GAAP else _income_sycebnl)(items, start, end)


def _income_gaap(items, start, end):
    R = _Rows()
    by_sec = {}
    for acc, nd in items:
        sec = effective_section(acc)
        by_sec.setdefault(sec, []).append((acc, _signed(sec, nd)))

    def block(sec, title, total_label):
        entries = by_sec.get(sec, [])
        R.section(title)
        for acc, amt in entries:
            R.line(acc["name"], amt, acc["number"] or "")
        tot = round(sum(a for _, a in entries), 2)
        R.subtotal(total_label, tot)
        return tot

    revenue = block("REV", "Revenue", "Total revenue")
    cogs = block("COGS", "Cost of goods sold", "Total cost of goods sold")
    gross = round(revenue - cogs, 2)
    R.total("GROSS PROFIT", gross)
    opex = block("OPEX", "Operating expenses", "Total operating expenses")
    operating = round(gross - opex, 2)
    R.total("OPERATING INCOME", operating)
    oinc = block("OINC", "Other income", "Total other income")
    oexp = block("OEXP", "Other expenses", "Total other expenses")
    before_tax = round(operating + oinc - oexp, 2)
    R.total("INCOME BEFORE INCOME TAXES", before_tax)
    tax = block("TAX", "Income taxes", "Total income taxes")
    net = round(before_tax - tax, 2)
    R.total("NET INCOME", net)
    return {"title": "Income Statement",
            "subtitle": f"For the period {start} to {end} — amounts in {BASE}",
            "rows": R.rows, "totals": {"net_income": net}}


def _income_sycebnl(items, start, end):
    R = _Rows()
    buckets = {}  # (groupe, 'P'|'C') -> [(acc, montant)]
    for acc, nd in items:
        sec = effective_section(acc)
        side = "P" if sec in INCOME_SECTIONS else "C"
        buckets.setdefault((syc_result_group(acc), side), []).append(
            (acc, -nd if side == "P" else nd))

    def block(group, side, title):
        lines = _sycebnl_lines(buckets.get((group, side), []))
        R.section(title)
        for code, label, amt in lines:
            R.line(label, amt, code)
        tot = round(sum(a for _, _, a in lines), 2)
        R.subtotal(f"Total {title.lower()}", tot)
        return tot

    results = []
    for group, nom_p, nom_c, nom_r in (
        ("exploitation", "Produits d'exploitation", "Charges d'exploitation", "RÉSULTAT D'EXPLOITATION"),
        ("financier", "Produits financiers", "Charges financières", "RÉSULTAT FINANCIER"),
        ("hao", "Produits HAO", "Charges HAO", "RÉSULTAT HORS ACTIVITÉS ORDINAIRES (HAO)"),
    ):
        p = block(group, "P", nom_p)
        c = block(group, "C", nom_c)
        r = round(p - c, 2)
        R.total(nom_r, r)
        R.blank()
        results.append(r)
    net = round(sum(results), 2)
    R.total("EXCÉDENT (DÉFICIT) NET DE LA PÉRIODE", net)
    return {"title": "Compte de résultat SYCEBNL",
            "subtitle": f"Du {start} au {end} — montants en {BASE}",
            "rows": R.rows, "totals": {"net_income": net}}


# ---------------------------------------------------------------------- #
# FLUX DE TRÉSORERIE (version simplifiée : variation des comptes de trésorerie)
# ---------------------------------------------------------------------- #
def cash_flow_report(db, start, end, framework):
    cash = [a for a in db.query("SELECT * FROM accounts WHERE account_type='TRESORERIE'")]
    before = {a["id"]: nd for a, nd in _net_debits(db, as_of=_day_before(start))
              if a["account_type"] == "TRESORERIE"}
    after = {a["id"]: nd for a, nd in _net_debits(db, as_of=end)
             if a["account_type"] == "TRESORERIE"}
    entries_start, entries_end = [], []
    for a in cash:
        entries_start.append((a, before.get(a["id"], 0.0)))
        entries_end.append((a, after.get(a["id"], 0.0)))
    return (_cash_gaap if framework == GAAP else _cash_sycebnl)(entries_start, entries_end, start, end)


def _cash_gaap(es, ee, start, end):
    R = _Rows()
    total_s = round(sum(a for _, a in es), 2)
    total_e = round(sum(a for _, a in ee), 2)
    R.line("Cash and cash equivalents — beginning of period", total_s)
    R.section("Net change by account")
    start_by_id = {a["id"]: v for a, v in es}
    for a, v in ee:
        change = round(v - start_by_id.get(a["id"], 0.0), 2)
        if abs(change) >= TOLERANCE:
            R.line(a["name"], change, a["number"] or "")
    R.subtotal("Net increase (decrease) in cash", round(total_e - total_s, 2))
    R.total("Cash and cash equivalents — end of period", total_e)
    return {"title": "Statement of Cash Flows (simplified)",
            "subtitle": f"For the period {start} to {end} — amounts in {BASE}",
            "rows": R.rows, "totals": {"net_change": round(total_e - total_s, 2)}}


def _cash_sycebnl(es, ee, start, end):
    R = _Rows()
    total_s = round(sum(a for _, a in es), 2)
    total_e = round(sum(a for _, a in ee), 2)
    R.line("Trésorerie nette au début de la période", total_s)
    R.section("Variation par compte de trésorerie")
    start_by_id = {a["id"]: v for a, v in es}
    changes = [(a, round(v - start_by_id.get(a["id"], 0.0), 2)) for a, v in ee]
    changes = [(a, c) for a, c in changes if abs(c) >= TOLERANCE]
    for code, label, amt in _sycebnl_lines(changes):
        R.line(label, amt, code)
    R.subtotal("Variation nette de la trésorerie", round(total_e - total_s, 2))
    R.total("Trésorerie nette à la fin de la période", total_e)
    return {"title": "Tableau des flux de trésorerie SYCEBNL (simplifié)",
            "subtitle": f"Du {start} au {end} — montants en {BASE}",
            "rows": R.rows, "totals": {"net_change": round(total_e - total_s, 2)}}


# ---------------------------------------------------------------------- #
# Point d'entrée unique
# ---------------------------------------------------------------------- #
REPORT_KINDS = ["Bilan", "Compte de résultat", "État des flux de trésorerie"]


def build_report(db, kind, start, end, framework):
    if kind == "Bilan":
        return balance_sheet_report(db, end, framework)
    if kind == "Compte de résultat":
        return income_statement_report(db, start, end, framework)
    return cash_flow_report(db, start, end, framework)
