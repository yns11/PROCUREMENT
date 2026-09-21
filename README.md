# PROCUREMENT — pilotage des approvisionnements

Application Databricks Apps unifiée : interface React issue d’APPRO, moteur MRP indépendant, données ERP en Unity Catalog et écritures dans Lakebase/PostgreSQL. La V2 reprend les fonctions d’APPRO au commit `804b271` et les protections de PROCUREMENT V1. **Aucune modification apportée à APPRO.**

- Cockpit, filtres par approvisionneur/scénario/horizon, fiches articles, graphiques et grille jour/semaine.
- Trois stocks : ferme, prévisionnel et simulé ; stock physique, solde net et manque distincts ; report ou perte de demande.
- PDP versionné, nomenclatures, production réelle, commandes, réceptions partielles, ajustements, sourcing, MOQ/multiples/délais/calendriers.
- Calcul CBN explicite, saisies arithmétiques, décisions accepter/modifier/ignorer, audit transactionnel.
- Scénarios privés à base figée, comparaison, duplication et historique des définitions.
- Excel à formules : **saisies directement dans SIMULATION**. Pas d’onglets COMMANDES/SAISIES dans cet export. La synthèse hebdomadaire utilise les calculs quotidiens.
- Réimport Excel validé et idempotent dans un nouveau scénario ; migration de scénarios V1 JSON/Excel.

## Démarrage local

Python 3.11/3.12 et Node 22. Les huit articles de démonstration sont entièrement synthétiques ; aucun classeur industriel n’est distribué.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cd client
npm ci
npm run build
cd ..
PROCUREMENT_MODE=demo PROCUREMENT_DATA_SOURCE=local python run.py
```

Ouvrir `http://localhost:8000`. La date de la démonstration est fixée par le snapshot synthétique du 20 septembre 2026. En production, la référence est la date courante et la fraîcheur du lot ERP est contrôlée.

## Vérification

```bash
python -m pytest backend/tests tests -q
ruff check backend scripts/generate_demo_v2.py scripts/init_db.py scripts/check_v2_browser.py scripts/uc run.py
cd client && npm run build
```

`python scripts/check_v2_browser.py` teste neuf routes, le CBN, l’acceptation et la navigation mobile. Installer Chromium avec `python -m playwright install chromium`. Les quatre tests `test_grid_recalculation.py` nécessitent LibreOffice : ils **recalculent** le classeur puis comparent ses résultats au moteur Python. La CI installe ces dépendances.

## Documentation

- [Audit actualisé d’APPRO, preuves et matrice de couverture](docs/07-audit-appro-et-fusion.md)
- [Architecture et décisions de fusion](docs/08-architecture-v2.md)
- [Règles métier V2 et contrat Excel](docs/09-regles-et-excel-v2.md)
- [Déploiement et contrat Unity Catalog](docs/10-deploiement-v2.md)
- [Recette et limites vérifiées](docs/11-recette-v2.md)

Les documents `01` à `06` et le paquet Python `procurement/` décrivent la V1, conservée comme oracle de régression et adaptateur de migration. L’application servie par `run.py` utilise `backend/procurement_app/` et `client/`. Il n’y a qu’une interface publiée.

## Production

Le mode par défaut est `production` et échoue si Unity Catalog, l’identité Databricks ou le stockage durable ne sont pas configurés. Attacher le SQL warehouse et Lakebase Autoscaling, renseigner les variables et les rôles, initialiser le schéma avec un compte propriétaire puis déployer. Voir le guide V2 : les tests locaux ne constituent pas une validation de votre workspace Databricks.
