# POC — Tableau de simulation approvisionnement

Branche **`feat/poc-simulation-management`**, dérivée de `feat/unified-procurement` (`9b81013`). Application de démonstration autonome, avec deux articles fictifs et une date de référence fixée au **21 septembre 2026**.

## Démarrer

```bash
python -m pip install -r requirements.txt
npm ci --prefix client
npm run build --prefix client
python run_poc.py
```

Ouvrir `http://localhost:8000`. Le port peut être défini par `DATABRICKS_APP_PORT`.

Sur Databricks, utiliser une **App dédiée** et les fichiers de cette branche. `app.yaml` démarre `start.sh`, qui construit le client si nécessaire puis lance `run_poc.py`. Aucun warehouse ni mapping Unity Catalog n’est nécessaire au POC. Le bundle facultatif nomme l’App `procurement-poc` pour la distinguer de l’application complète. Aucun déploiement n’est effectué par la création de cette branche.

Le POC utilise sa propre base `data/local/poc-management.db`. Elle ne remplace pas la base de l’application complète. Ce stockage de démonstration ne garantit pas la conservation après redéploiement Databricks ; les exemples peuvent être rechargés ou réinitialisés. Ne pas pointer cette branche vers une base de production existante : son schéma contient des champs propres au POC.

## Écrans

- **Référentiel** : Articles et Nomenclatures (BOM), import CSV/XLSX et édition.
- **PDP** : import et édition du plan hebdomadaire.
- **Commandes** : import et édition des commandes fermes et prévisionnelles.
- **Fiches articles** : graphiques, tableau jour/semaine, Calcul CBN, Saisir, Excel. Les quatre onglets secondaires sont volontairement vides.
- **Paramètres** : règles de calcul et réinitialisation de la démonstration.

Pas de marque ni d’icône dans la navigation latérale. Les écrans n’affichent que les titres, labels, données et commandes ; les explications sont dans le guide de présentation.

## Présenter

**[Guide de démonstration et scénarios chiffrés](docs/poc/presentation.md)** — préparation, cinq séquences et résultats attendus.

**[Règles et contrats d’import](docs/poc/regles.md)** — normalisation au lundi, rapprochement ferme/simulé réversible, types et limites du POC.

**[Preuves de calcul](docs/poc/preuves.json)** — valeurs obtenues par les appels API sur le jeu fictif, indépendantes d’un navigateur.

## Vérifier

```bash
python -m pip install -r requirements-dev.txt
python -m pytest backend/tests tests -q --ignore=backend/tests/test_grid_recalculation.py
python -m playwright install --with-deps chromium
python scripts/check_poc_browser.py
python -m pytest backend/tests/test_grid_recalculation.py -q
```

La dernière commande nécessite LibreOffice. La CI exécute Python 3.11/3.12, le build TypeScript, les parcours navigateur du POC et le recalcul Excel. Les captures et le classeur de test se trouvent dans l’artefact `poc-browser-evidence`.

Le moteur modulaire de la V2 reste commun. L’adaptateur POC, ses entrées, sa règle de rapprochement et son lanceur sont séparés. Les documents V1/V2 restent dans `docs/` comme historique de conception ; ils ne décrivent pas le périmètre réduit de cette branche.
