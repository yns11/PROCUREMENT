# Procurement

Application de planification des approvisionnements destinée à **Databricks Apps**. Le moteur transforme un PDP hebdomadaire et une nomenclature à un niveau en besoins, stocks projetés, alertes et propositions de commandes. L’interface est en français.

Le code est exécutable en démonstration locale. Le raccordement aux données industrielles exige de configurer les ressources Databricks et le mapping de vos tables Unity Catalog. Aucune connexion à un workspace réel n’est supposée déjà réalisée.

## Démarrer localement

Python 3.11 ou 3.12 :

```bash
python -m venv .venv
# Windows PowerShell : .venv\Scripts\Activate.ps1
# Linux/macOS : source .venv/bin/activate
python -m pip install -r requirements.txt
# Windows PowerShell : $env:APP_MODE="demo"
# Linux/macOS : export APP_MODE=demo
python run.py
```

Ouvrir http://localhost:8000. La démonstration contient uniquement des données fictives et conserve les scénarios dans `procurement-demo.db`. Le mode par défaut est production : une configuration incomplète provoque un refus de démarrage, jamais un basculement silencieux vers SQLite.

## Fonctionnalités

- Cockpit des ruptures, couvertures et surstocks ; recherche et filtre fournisseur.
- Projection ferme/simulée, courbes et tableaux journaliers, hebdomadaires et mensuels.
- Propositions avec MOQ, multiples, délais, jours fermés, priorité fournisseur ou quotas.
- Saisie et modification des référentiels, PDP, réalisé, commandes, réceptions et ajustements.
- Modes plan, réalisé prioritaire et réalisé seul ; choix des conventions de réception et des retards.
- Scénarios indépendants, duplication, versions, conflits de modification et restauration.
- Export/réimport Excel versionné ; import PDP CSV ; lecture des données ERP via SQL Warehouse.
- Persistance PostgreSQL/Lakebase et identité Databricks ; aucun envoi vers l’ERP.

## Documentation

1. [Analyse du classeur et du processus actuel](docs/01-analyse-excel.md)
2. [Règles métier et variantes](docs/02-regles-metier.md)
3. [Architecture et design](docs/03-architecture.md)
4. [Déploiement Databricks pas à pas](docs/04-deploiement.md)
5. [Recette et limites de validation](docs/05-recette.md)

Voir également le [schéma PostgreSQL](sql/app_schema.sql), le [contrat UC](sql/uc_contract.sql) et le [rapport de validation](docs/06-validation.md).

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

API documentée sur `/api/docs`. Les opérations de mutation exigent `X-Procurement-Request: 1`. Les scénarios appartiennent à leur créateur. En production, l’App doit rester derrière le proxy d’authentification Databricks.

## Reprise Excel

```bash
python -m scripts.inspect_legacy "chemin/ancien-classeur.xlsx" --output "chemin-prive/staging.json"
```

Cet extracteur lit le modèle existant sans le modifier et liste les points à résoudre. Le résultat contient des données opérationnelles et doit rester hors du dépôt public. Le réimport depuis l’interface attend le format Excel exporté par cette application, pas le classeur historique.
