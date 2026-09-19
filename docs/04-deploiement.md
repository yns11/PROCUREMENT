# Déploiement Databricks Apps

Le code est prêt à être configuré et déployé. Cette livraison ne dispose pas d’un accès au workspace du site : la connexion réelle à Unity Catalog, les autorisations et le démarrage dans Databricks restent à recetter. Ne pas interpréter la démonstration comme une lecture des données ERP réelles.

## 1 Préparer les ressources dans l’interface

Dans Databricks, ouvrir **Compute > Apps** ou la rubrique **Apps** disponible dans le workspace. Créer une App Python nommée par exemple `procurement-dev`. Relever son service principal dans l’onglet Authorization.

Ajouter un SQL Warehouse avec la clé de ressource `sql-warehouse`, avec l’autorisation d’utilisation. Ajouter une base **Lakebase Autoscaling** avec la clé `postgres` : choisir le projet, la branche et la base réellement créés dans votre workspace. Le propriétaire du projet doit disposer de CAN MANAGE pour ajouter cette ressource. L’application obtient les variables PostgreSQL de connexion ; `LAKEBASE_ENDPOINT` reçoit le chemin de l’endpoint via `valueFrom: postgres`. Ne pas saisir un chemin de volume UC à la place d’une base.

Le service principal doit disposer de USE CATALOG, USE SCHEMA et SELECT sur la vue de lecture ERP. L’ajout du Warehouse ne confère pas automatiquement ces droits Unity Catalog. Le modèle SQL est dans `sql/uc_contract.sql`. Ces droits peuvent nécessiter l’intervention du propriétaire des objets. [Ressource Lakebase](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase) et [ressource SQL Warehouse](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/sql-warehouse).

## 2 Initialiser la base applicative

Depuis le SQL Editor PostgreSQL/Lakebase, avec le propriétaire de la base, exécuter `sql/app_schema.sql`, puis remplacer `APP_CLIENT_ID` dans les GRANT par le client ID exact du service principal de l’App. Ce script crée deux tables dans le schéma public. Vérifier que ce schéma ne contient pas déjà des objets homonymes d’une autre application.

Alternative pour une équipe technique : depuis un environnement Python configuré avec l’identité propriétaire et les variables de connexion, lancer `python -m scripts.init_db`. Ne pas lancer ce script à chaque requête. Le démarrage de production ne crée pas automatiquement les tables.

L’application renouvelle le mot de passe OAuth à chaque nouvelle connexion physique et recycle les connexions du pool. Utiliser l’endpoint direct Lakebase, pas son pooler PgBouncer pour l’authentification OAuth. La rotation est implémentée dans `store.py`. [Authentification Lakebase](https://docs.databricks.com/aws/en/oltp/projects/authentication).

Si Lakebase n’est pas disponible, une base PostgreSQL durable autorisée est compatible. Dans `app.yaml`, remplacer `LAKEBASE_ENDPOINT` par `DATABASE_URL` avec `valueFrom` vers une ressource Secret. Valeur attendue : URL SQLAlchemy `postgresql+psycopg://…?sslmode=require`. Le secret contient le mot de passe d’un rôle PostgreSQL natif, pas un jeton OAuth à durée limitée. Les caractères réservés du nom ou du mot de passe doivent être encodés dans l’URL. La connectivité réseau à cette base doit être autorisée. L’application ne contourne pas les restrictions réseau.

## 3 Préparer le contrat Unity Catalog

Le nom exact des tables ERP et leur schéma n’étaient pas fournis. Le connecteur attend une **vue de snapshot canonique**, dont le nom se configure dans `PROCUREMENT_UC_VIEW`.

| Colonne de la vue | Type | Contrôle |
|---|---|---|
| entity | STRING | Une des dix entités ci-dessous |
| payload | STRING JSON | Un objet conforme à models.py |
| batch_id | STRING | Identique et non nul dans toutes les lignes |
| as_of | TIMESTAMP | Identique dans toutes les lignes, UTC, âge maximum 24 h par défaut |

Entités : une ligne `settings`, puis zéro ou plusieurs lignes `items`, `suppliers`, `sourcing`, `bom`, `plans`, `actuals`, `orders`, `receipts`, `adjustments`. Un import ERP doit au moins contenir articles et BOM. Les autres données manquantes sont ensuite diagnostiquées à la validation/calculation.

`python -m scripts.snapshot_rows` produit un exemple JSONL entièrement fictif. Le schéma des objets est aussi disponible via `/openapi.json` et les modèles Python. `sql/uc_contract.sql` prépare le conteneur Delta ; il ne remplit pas votre staging ERP. Un traitement amont doit publier un seul lot complet et validé, avec INSERT OVERWRITE atomique ou équivalent. Une vue qui joint des sources indépendamment mises à jour puis attribue artificiellement le même horodatage ne constitue pas un snapshot cohérent.

Contrôles de préparation amont :

1. Définir site et portefeuille, unité de stock et statut utilisable. Exclure ou isoler les stocks qualité/non disponibles suivant les règles validées.
2. Choisir une date d’ancrage et fournir le stock **début de journée** correspondant. Un stock à 14 h ne peut pas être associé au besoin d’une journée entière sans réconciliation.
3. Fournir les quantités totales de lignes ouvertes, les reçus antérieurs à l’ancrage et les réceptions à compter de l’ancrage, sans duplication DELFOR/DELJIT.
4. Valider liens articles/fournisseurs, MOQ, multiples, délais, quotas et unités.
5. Publier le PDP sur tout l’horizon visible plus la profondeur nécessaire au maximum de couverture. Renseigner explicitement les semaines à zéro.
6. Vérifier BOM à un niveau et correspondance exacte programme/PDP/réalisé. Le champ « engagé » Excel nécessite une décision de correspondance.

Le connecteur effectue une seule lecture bornée de la vue, rejette plusieurs lots/horodatages et refuse les données de plus de `ERP_MAX_AGE_HOURS` (24 par défaut). Le chargement ERP crée un scénario indépendant horodaté ; il ne remplace pas les scénarios existants. Recharger chaque jour pour changer d’ancrage.

## 4 Récupérer et configurer le code

Créer un Git folder dans le workspace depuis `https://github.com/yns11/PROCUREMENT`. Choisir la branche contenant la livraison. À la racine, adapter `app.yaml` :

- conserver `command: ['python', 'run.py']` et `APP_MODE: production` ;
- vérifier les clés de ressources `postgres` et `sql-warehouse` ;
- remplacer `REPLACE_CATALOG.REPLACE_SCHEMA.procurement_snapshot` par la vue réelle ;
- remplacer `PROCUREMENT_EDITORS` par les adresses e-mail des approvisionneurs autorisés, séparées par virgules, sans publication de cette configuration privée sur le dépôt public.

Ne pas renseigner de secret Databricks dans le code : l’App reçoit ses identifiants de service principal et le SDK les utilise. [Configuration app.yaml](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime), [variables injectées](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env) et [authentification de l’App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth).

## 5 Déployer depuis l’interface

Dans l’App, choisir Deploy, sélectionner le dossier source contenant `app.yaml`, `run.py`, `requirements.txt` et le package `procurement`, puis démarrer le déploiement. Aucun build Node.js n’est nécessaire. Vérifier les journaux d’installation et de démarrage. L’App écoute le port injecté par Databricks.

Ouvrir l’URL fournie, attribuer CAN USE aux utilisateurs de recette, puis cliquer **Charger ERP**. Vérifier l’identité affichée, la liste des articles et la date du stock initial. Le premier chargement crée un scénario personnel. Si la lecture échoue, le message renvoie vers les ressources, droits et journaux ; aucun fallback automatique vers des données fictives n’a lieu en production.

L’App s’appuie sur les [en-têtes d’identité transmis par Databricks](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/http-headers). Toute exposition hors Databricks nécessite une couche d’authentification dédiée avant utilisation en production.

## 6 Recette et bascule

Exécuter `docs/05-recette.md`, comparer sur un périmètre pilote et expliquer les écarts attendus avec Excel : répartition exacte, réceptions partielles, jours fermés et délais faisables. Valider les règles de `docs/02-regles-metier.md` avec les approvisionneurs. Déployer ensuite la même version dans une App de production avec ressources séparées et un dispositif de sauvegarde/restauration Lakebase.

Ne supprimer les fichiers de travail opérationnels qu’après un cycle parallèle concluant. Les scripts et tests locaux attestent du comportement testé, pas de la qualité des données source ni des autorisations du workspace réel.
