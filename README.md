# GH-Compta

Logiciel de comptabilité en partie double, style QuickBooks, développé en **Python + PyQt5**
avec une base de données **SQLite locale**. Compilable en `.exe` Windows via GitHub Actions.

## Fonctionnalités (v1)

- **Plan comptable** pré-rempli à partir de votre structure existante (Trésorerie, Comptes
  clients, Immobilisations, Comptes fournisseurs, Capitaux propres, Coût des ventes, Dépenses...)
- **Clients** et **Fournisseurs**
- **Ventes / Factures** avec lignes multiples → écriture automatique (Débit Comptes clients /
  Crédit Produits)
- **Dépenses / Achats comptant** → écriture automatique (Débit Charges / Crédit Trésorerie)
- **Paiements clients** (encaissement partiel ou total d'une facture)
- **Journal général** consultable + écritures manuelles (opérations diverses)
- **Rapports** : Bilan, Compte de résultat, État des flux de trésorerie (simplifié)
- Toute écriture est vérifiée : le total débit doit toujours égaler le total crédit avant
  d'être enregistrée (partie double garantie).

## Structure du projet

```
gh-compta/
├── main.py                  # point d'entrée
├── requirements.txt
├── app/
│   ├── database.py          # schéma SQLite + plan comptable initial
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

- Factures fournisseurs à crédit (Bill) avec paiement différé
- Rapprochement bancaire
- Gestion de stock / articles
- Export PDF des factures et rapports
- Gestion multi-devises avec taux de change
- Classes et sites déjà présents en base (ex. "programme", "ouaga") à exploiter dans les
  formulaires et rapports filtrés
