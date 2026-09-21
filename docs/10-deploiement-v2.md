# Déploiement Databricks Apps V2

## Préparer les données

Le fichier `scripts/uc/create_tables.sql` définit onze tables canoniques : articles, fournisseurs, liens, programmes, BOM, PDP, production réelle, commandes, réceptions, mouvements et stock. Elles peuvent être des vues sur les tables ERP existantes, à condition de respecter exactement leur contrat.

Chaque ligne porte un `batch_id`. Le manifeste `erp_batches(batch_id, published_at, status)` n’est publié avec `status='READY'` qu’après chargement et validation de toutes les tables. Un lot publié est immuable. `published_at` est un timestamp UTC ; sa fraîcheur maximale par défaut est 24 heures (`PROCUREMENT_ERP_MAX_AGE_HOURS`). Le stock est connu en fin de journée de `snapshot_date` ; les faits déjà inclus dans ce stock ne doivent pas être rejoués.

Valider avant publication : clés uniques, grain des lignes de commande, référence des réceptions, unité BOM/article, cohérence commande reçue/stock/réceptions et trous de PDP. Le numéro de ligne fait partie du grain commande ; les références de réception doivent utiliser la clé canonique correspondante. Le plan choisi par programme/semaine est celui de la publication la plus récente. Ne pas supposer qu’une chaîne de version permet à elle seule de classer les publications.

`load_seed.py` n’accepte qu’un schéma au nom terminé par `_demo` et ajoute un lot synthétique ; il n’écrase aucune table. Ne pas l’utiliser sur les tables ERP opérationnelles.

## Ressources et variables

1. Créer l’App PROCUREMENT et lui attacher un SQL warehouse sous la clé `sql-warehouse` (Can use).
2. Attacher le projet/branche/base Lakebase Autoscaling via l’interface Apps, clé `postgres`. Ne pas remplacer une ressource `database` déjà attachée sans migration de ses rôles. Les variables `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` sont injectées par la plateforme.
3. Dans `app.yaml`, renseigner `PROCUREMENT_UC_CATALOG`, `PROCUREMENT_UC_SCHEMA`, `PROCUREMENT_EDITORS`, `PROCUREMENT_ADMINS`. Les adresses sont séparées par des virgules ; employer des UPN normalisés en minuscules sans espaces.
4. `DATABRICKS_WAREHOUSE_ID` provient de `sql-warehouse`. `LAKEBASE_ENDPOINT` doit résoudre le chemin de l’endpoint Autoscaling attendu par `WorkspaceClient.postgres.generate_database_credential` ; vérifier la valeur résolue dans le workspace. Les identifiants secrets OAuth restent injectés par Databricks.
5. Attribuer au service principal USE CATALOG/SCHEMA et SELECT sur les vues du portefeuille. Restreindre l’accès à l’app à l’équipe autorisée. Le proxy fournit l’identité `x-forwarded-email` ; ne jamais publier ce serveur directement sur Internet en acceptant cet en-tête d’un client arbitraire.

Le bundle fourni gère le code et le warehouse ; l’attachement Lakebase doit être effectué dans l’interface Apps. La version du SDK épinglée ne doit pas être utilisée pour inventer un schéma de ressource Autoscaling non supporté par son modèle `apps`.

## Stockage transactionnel

Initialiser une base/schéma dédié à PROCUREMENT V2 avec un compte propriétaire :

```bash
python scripts/init_db.py
```

Le runtime de production vérifie l’existence du schéma au lieu de lancer `create_all`. Réduire ensuite ses privilèges à ceux nécessaires sur les tables/séquences. Configurer sauvegarde/restauration et conservation des journaux. Les jetons Lakebase sont régénérés à chaque nouvelle connexion physique ; le pool recycle les connexions.

Les anciennes tables PROCUREMENT V1 sont distinctes et ne sont ni écrasées ni converties en place. Exporter les scénarios V1 et utiliser l’import de migration vers une base V2. Pour une instance V2 déjà créée avec un schéma intermédiaire de développement, recréer seulement sa base de démonstration ; ne pas appliquer de suppression implicite à une base opérationnelle.

## Construction et démarrage

```bash
cd client
npm ci
npm run build
cd ..
bash start.sh
```

`run.py` utilise le port `DATABRICKS_APP_PORT`. En production, le mode par défaut refuse une source locale, un stockage SQLite, une absence de contexte App et une liste d’éditeurs absente. Pour une démonstration locale, renseigner explicitement `PROCUREMENT_MODE=demo` et `PROCUREMENT_DATA_SOURCE=local`.

Le build du frontend doit idéalement être réalisé dans le pipeline et inclus dans l’artefact de déploiement (`client/dist`, ignoré par Git). `start.sh` sait le reconstruire si Node est disponible dans le runtime. Vérifier la version Node de l’environnement et les dépendances avant déploiement ; ne pas servir une App API seule en pensant que l’interface a été publiée.

## Recette de l’environnement cible

- Contrôler la lecture d’un lot UC complet et le refus d’un lot périmé.
- Vérifier un lecteur, un éditeur, un administrateur et un scénario privé.
- Ouvrir deux sessions d’éditeur ; confirmer qu’une écriture avec une ancienne révision produit 409.
- Déployer/re-déployer et confirmer la persistance Lakebase ; attendre le renouvellement d’une connexion OAuth.
- Reproduire les cas métier de la fiche de recette avec les données ERP.
- Exporter, modifier puis réimporter un fichier dans Excel Desktop/Microsoft 365, en plus des tests LibreOffice.

Aucun déploiement dans le workspace ni aucune écriture dans UC/ERP n’a été réalisé au cours de cette fusion. L’absence d’accès au workspace empêche de certifier les ressources, grants, mappings et limites de charge réels.

Sources : [autorisation](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth), [ressources Lakebase et PG*](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase), [ressources d’une App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources).
