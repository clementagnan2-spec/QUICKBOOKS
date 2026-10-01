# GH-Compta

Logiciel de comptabilité en partie double, style QuickBooks, développé en **Python + PyQt5**
avec une base de données **SQLite locale**. Compilable en `.exe` Windows via GitHub Actions.

## Fonctionnalités (v2)

- **Plan comptable double référentiel US GAAP ↔ SYCEBNL**, pré-rempli (79 comptes) à partir de
  `Correspondance_US_GAAP_SYCEBNL.xlsx`. Entièrement **modifiable** : ajout, modification,
  désactivation, suppression (si jamais utilisé), import / export Excel. Chaque compte porte son
  code et intitulé US GAAP, sa section US GAAP, son compte SYCEBNL et un coefficient.
- **Rapports en double version** (Bilan, Compte de résultat, Flux de trésorerie) : version
  **US GAAP** et version **SYCEBNL**, côte à côte à l'écran et dans un même PDF (une page par version).
  Les écritures sont saisies une seule fois ; seul le regroupement des comptes change.
- **Import Excel** (menu « Importer des données ») : écritures comptables, balance N-1 (à-nouveaux)
  et balance N (soldes de clôture), avec contrôle d'équilibre, résumé avant validation et modèles Excel.
- **Clients** et **Fournisseurs**
- **Ventes / Factures** avec lignes multiples, liées ou non à un article de stock → écriture
  automatique (Débit Comptes clients / Crédit Produits, + sortie de stock et COGS si applicable)
- **Dépenses / Achats comptant** → écriture automatique (Débit Charges / Crédit Trésorerie)
- **Factures fournisseurs à crédit** (paiement différé) → écriture (Débit Charges ou Stock /
  Crédit Comptes fournisseurs), avec enregistrement de paiements partiels ou totaux ensuite
- **Gestion de stock** : articles avec quantité en main, coût moyen pondéré (CMP) recalculé
  automatiquement à chaque achat, sortie de stock + coût des marchandises vendues (COGS)
  générés automatiquement à la vente
- **Rapprochement bancaire** : pointage des opérations d'un compte de trésorerie face à un
  relevé, calcul de l'écart, historique des sessions de rapprochement
- **Devises multiples** : taux de change par devise et par date, conversion automatique en
  devise de base (GHS) dans les totaux des rapports consolidés
- **Export PDF** des factures clients et des rapports (Bilan, Compte de résultat, Flux de
  trésorerie)
- **Paiements clients** (encaissement partiel ou total d'une facture)
- **Journal général** consultable + écritures manuelles (opérations diverses)
- **Rapports** : Bilan, Compte de résultat, État des flux de trésorerie (simplifié), tous
  exportables en PDF
- Toute écriture est vérifiée : le total débit doit toujours égaler le total crédit avant
  d'être enregistrée (partie double garantie).

## Structure du projet

```
gh-compta/
├── main.py                  # point d'entrée
├── requirements.txt
├── app/
│   ├── database.py          # schéma SQLite (+ migration des anciennes bases)
│   ├── chart_data.py        # plan comptable standard US GAAP ↔ SYCEBNL
│   ├── chart_plan.py        # sections, classement SYCEBNL, import/export Excel
│   ├── reports.py           # rapports en double version
│   ├── importers.py         # import Excel : écritures, balance N-1, balance N
│   ├── logic.py              # écritures comptables, factures, dépenses, rapports
│   ├── main_window.py        # fenêtre principale (barre latérale + navigation)
│   ├── ui_utils.py
│   └── pages/                # chaque module de l'interface
└── .github/workflows/build-exe.yml   # compilation automatique en .exe
```

## Lancer en local (développement)

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

Les données sont stockées dans `~/GH-Compta/gh_compta.db` (créé automatiquement au premier
lancement, avec le plan comptable pré-rempli).

## Obtenir le .exe via GitHub (sans installer Windows)

1. Créez un dépôt GitHub et poussez ce dossier :
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/VOTRE-COMPTE/gh-compta.git
   git push -u origin main
   ```
2. Le workflow `.github/workflows/build-exe.yml` se déclenche automatiquement à chaque
   `push` sur `main` (ou manuellement depuis l'onglet **Actions** > *Build Windows .exe* >
   *Run workflow*).
3. GitHub compile le projet sur une machine Windows dans le cloud (`windows-latest`) avec
   PyInstaller.
4. Une fois le job terminé (onglet **Actions**), téléchargez l'artifact
   **GH-Compta-windows-exe** : il contient `GH-Compta.exe`, prêt à l'emploi, aucune
   installation de Python requise sur le poste final.
5. Optionnel : pour obtenir une **Release** téléchargeable avec un lien permanent, créez un
   tag (`git tag v1.0 && git push origin v1.0`) — le workflow y attachera automatiquement
   l'exécutable.

## Prochaines étapes possibles

- Filtrage des rapports par classe / site (déjà en base, ex. "programme", "ouaga")
- Export PDF des factures fournisseurs (actuellement disponible pour les factures clients)
- Import de relevés bancaires (CSV) pour le rapprochement automatique
- Gestion des acomptes / avoirs
- Utilisateurs multiples avec droits d'accès
