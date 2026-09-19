# Architecture applicative

Le navigateur affiche une interface française en HTML/CSS/JavaScript, servie par FastAPI. Les règles métier sont intégralement exécutées en Python. Aucun Node.js ni build frontend n’est nécessaire dans Databricks Apps. Les dépendances Python sont versionnées.

| Couche | Modules | Responsabilité |
|---|---|---|
| Domaine | models.py, calendar.py, engine.py | Contrat, intégrité, calendriers, besoins, stocks et propositions |
| Application | api.py | Authentification via proxy, autorisation, scénarios et cas d’usage |
| Persistance | store.py | Transactions PostgreSQL, contrôle de version, historique |
| Sources | uc.py | Lecture SQL Warehouse d’un snapshot publié Unity Catalog |
| Échange | exchange.py | Excel versionné, PDP CSV et contrôles à l’import |
| Présentation | static/ | Navigation, cockpit, formulaire, graphique, tables et dialogues |

## Stockage durable

En production, les entrées et l’audit résident dans PostgreSQL, de préférence Lakebase Autoscaling. Le moteur utilise un snapshot JSON typé : une sauvegarde modifie une ligne de scénario et ajoute une révision dans la même transaction. La condition `WHERE version = version_attendue` empêche les pertes de mises à jour. Les entrées restent atomiques, y compris lorsque plusieurs référentiels changent ensemble.

Ce choix privilégie la cohérence et l’audit d’un portefeuille de taille modérée. Il est moins adapté aux jointures BI directes sur des millions d’événements et à l’édition collaborative ligne par ligne. Pour ces usages, projeter les révisions vers des tables Delta normalisées, puis faire évoluer le repository sans modifier le moteur. La BI de production et l’historique ERP volumineux restent côté Unity Catalog.

Deux tables PostgreSQL sont créées par le script d’initialisation. En exploitation, la version du code gère le format applicatif 1 ; toute évolution incompatible nécessitera une migration explicite. Aucun effacement automatique de l’historique n’est implémenté.

SQLite est réservé à la démonstration locale. Le mode production le refuse. Aucun stockage de base de données sur volume UC, filesystem éphémère ou fichier Excel partagé n’est utilisé.

## Identités et permissions

Databricks authentifie l’accès à l’App. L’API exploite `X-Forwarded-Email` uniquement derrière ce proxy. Les scénarios sont privés par propriétaire ; toute lecture ou modification vérifie ce propriétaire. `PROCUREMENT_EDITORS` désigne les utilisateurs autorisés à créer et modifier. Retirer une personne de cette liste conserve ses propres scénarios en lecture seule. Il n’y a pas de rôle administrateur permettant de lire tous les portefeuilles dans cette version.

Le service principal applicatif lit la vue UC : tous les éditeurs peuvent donc importer les données autorisées à cette identité. Pour des portefeuilles de confidentialité différente, utiliser une App/vue distincte ou ajouter une autorisation déléguée utilisateur avant mutualisation. Un filtre visuel fournisseur n’est jamais une frontière de sécurité.

Les requêtes de mutation exigent un en-tête applicatif que les formulaires intersites ne peuvent pas ajouter. Aucune politique CORS permissive n’est activée. Les noms et textes sont échappés dans le DOM ; les noms d’objets SQL sont validés et les valeurs des écritures utilisent SQLAlchemy. Une CSP empêche les scripts externes et inline. Ne pas exposer directement Uvicorn de production à Internet hors du proxy Databricks.

## Performance et limitations concrètes

Le calcul utilise des index en mémoire, des sommes préfixées et des recherches binaires pour la couverture. Les données de référence sont chargées une seule fois par snapshot, jamais cellule par cellule. Le calcul est synchrone et sans file de tâches ; dimensionner les portefeuilles pour conserver des temps courts. Le garde-fou initial est 200 000 couples article/jour par calcul et 100 000 lignes par snapshot UC. Les imports sont limités à 10 Mo compressés, 80 Mo décompressés et 50 000 lignes par feuille.

Les grandes grilles sont dans des conteneurs défilants ; l’écran affiche au maximum 100 alertes/articles, 200 propositions et 300 lignes de référentiel par table. Les lignes supplémentaires restent dans les données et dans les exports. Une pagination serveur et un éditeur de masse sont à prévoir au-delà de ces volumes d’utilisation.

## Design

Tokens CSS : fond `#f4f7f7`, texte `#172f35`, action `#087e78`, navigation `#12373c`, bordures `#dce5e5`, rayons 7 à 14 px, rythme 4/8/12/16/24/32 px. Titres 32/18/15 px, corps 14 px, données compactes 12 px. Police système sans dépendance réseau. Couleur + libellé pour chaque statut, focus visible, tableaux sémantiques, dialogues natifs, lien d’évitement, navigation mobile et graphiques accompagnés de valeurs tabulaires.

Ce système est propre à l’application et modifiable via les tokens. La surface ne dépend d’aucun service externe d’images, polices ou composants.
