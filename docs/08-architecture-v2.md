# Architecture PROCUREMENT V2

## Organisation

```text
backend/procurement_app/
  engine/       dataclasses, calendriers, demande, stock, CBN, scénarios, validation
  data/         contrat UC, adaptateurs, assemblage, tables transactionnelles
  services/     assemblage ERP + saisies, cache, expressions, échanges Excel, migration V1
  api/          dépendances d’identité/transaction, schémas, présentateurs, routes
client/src/
  components/   composants et mise en page
  pages/        neuf parcours métier
  state/        approvisionneur, scénario, horizon, granularité, thème
  lib/          client HTTP, types et requêtes
```

Le moteur ne dépend ni de FastAPI, ni de React, ni du stockage. Un `Dataset` et des `EngineParams` produisent un `MrpResult`. Les références ERP restent en lecture seule ; les saisies, scénarios et décisions résident en PostgreSQL/Lakebase. SQLite est réservé à la démonstration et aux tests.

## Frontières de cohérence

1. Une génération de données ERP comprend les onze tables du même `batch_id` READY. Le lot est immuable ; la source refuse un manifeste périmé. Une publication incomplète ne remplace pas la génération en cache.
2. Les paramètres persistés sont appliqués avant les paramètres explicites de requête. Un scénario conserve ses paramètres de création et une copie des données, puis applique ses événements et ses cellules locales.
3. Les écritures nécessitent `X-Procurement-Request: 1` et `If-Match: <révision>`. Une mise à jour atomique de `procurement_state` sérialise les mutations : un client obsolète reçoit 409. Les créations invalides sont annulées avec leur incrément de version.
4. Les journaux avant/après sont écrits dans la transaction. Une version identifie le portefeuille applicatif ; ce n’est pas un identifiant de publication ERP.
5. Le cache de calcul est borné (au plus 60 secondes), dépend de la révision et des paramètres/périmètres. Les adaptateurs UC ont une durée de vie configurable. La validité du lot et son immutabilité sont nécessaires : un cache n’est pas un substitut à la qualité des données.

## Scénarios et décisions

Les scénarios sont privés au propriétaire, avec accès administratif explicite. Ils figent le dataset et les paramètres à leur création. Leur comparaison utilise la même base figée. Le portefeuille opérationnel reste commun aux lecteurs/éditeurs de l’application ; les restrictions par approvisionneur sont des filtres d’analyse, pas une sécurité ligne par ligne.

Les événements sont appliqués à une copie et refusés s’ils sont invalides. La duplication transforme l’état courant du scénario en nouvelle base figée. `ScenarioRevision` conserve les versions de sa définition ; le journal garde les cellules et les décisions. Ce mécanisme ne prétend pas offrir un bouton de restauration universelle de tous les états intermédiaires.

Un CBN produit des propositions structurées et des cellules locales. Accepter en base convertit la quantité en commande planifiée, en retirant la quantité correspondante de la cellule CBN : le résultat ne double pas. Accepter dans un scénario reste une action de simulation. Une seconde décision sur la même proposition est rejetée. Relancer le CBN remplace les résultats CBN du périmètre, pas les saisies manuelles ni les commandes acceptées.

## Échanges Excel

Le serveur conserve le manifeste complet d’export : propriétaire, référence d’export, dataset, paramètres et coordonnées autorisées. Le fichier n’est pas une autorité de validation. La réimportation :

- limite la taille compressée et décompressée ; refuse macros et liens externes ;
- vérifie la référence d’export, les articles et les dates ;
- ne lit que les cellules de saisie déclarées ;
- accepte les nombres et l’arithmétique simple, sans exécuter les formules Excel ;
- crée une nouvelle simulation figée, sans publication ERP ;
- reconnaît un fichier déjà importé par SHA-256.

Les données des feuilles techniques ne suffisent donc pas à modifier un portefeuille étranger. L’aperçu d’import expose les différences avant écriture via `/api/imports/preview`.

## Interface et performances

La composition d’APPRO est conservée : navigation latérale, barre globale de contexte, cockpit, fiche article et pivot. Les améliorations comprennent une palette sémantique cohérente, une échelle typographique de ratio 1,25, une taille minimale de texte accrue, des chiffres tabulaires, un focus clavier visible, une boucle de focus dans les tiroirs, un lien d’évitement et une barre de contexte qui se replie sur mobile.

Les pages sont chargées à la demande. Le moteur travaille sur des tableaux NumPy et prolonge la demande au-delà de l’horizon visible pour calculer les cibles de fin de fenêtre. Les identifiants SQL sont validés et les lignes d’un lot sont bornées. Les sessions DB ne sont pas partagées entre requêtes ; l’accès au connecteur SQL partagé est sérialisé.

## V1

Le paquet `procurement/` et ses tests restent disponibles pour régression et migration ; `run.py` ne sert que la V2. `/api/imports/v1` accepte le contrat JSON ou le classeur V1, traduit ses paramètres et crée un scénario V2. Les politiques équivalentes sont préservées ; les algorithmes de propositions V1 et V2 ne sont pas annoncés identiques au chiffre près.
