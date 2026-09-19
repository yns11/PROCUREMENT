# Validation de la livraison

Validation exécutée le 19 septembre 2026 sur le code livré et des données fictives.

## Résultats obtenus

- **36 tests automatisés réussis** : calcul MRP, calendrier, quantités décimales, réalisé nul, réceptions partielles/décalées, retard, quotas, dates faisables, couverture, versions concurrentes, permissions, Excel et contrat UC simulé.
- Parcours Chromium exécutés : ouverture du cockpit, acceptation de proposition en brouillon, granularité semaine, modification d’un article et consultation de l’historique. Aucun événement d’erreur JavaScript relevé.
- Inspection visuelle des captures ordinateur 1512 px et mobile 390 px. Pas de débordement horizontal global mobile ; défilement local des tableaux conservé.
- Mesure du moteur seul : **500 articles × 180 jours**, soit **90 000 lignes**, calculés en **2,733 secondes**. Une seule mesure dans l’environnement de développement ; ce n’est pas une garantie de latence Databricks ni un test de charge multi-utilisateur.
- Signature du SDK Lakebase Autoscaling vérifiée avec la version 0.79.0 spécifiée.

## Limites explicites

Les tests UC utilisent un client SQL simulé ; les tests de persistance utilisent SQLite. Les accès réels au SQL Warehouse, les données du site, les permissions, PostgreSQL/Lakebase, le renouvellement du jeton en situation réelle et la conservation après redéploiement ne sont pas vérifiés dans cette session. Ils font partie de la recette documentée.

Les valeurs calculées en cache du classeur source ont été lues, mais le classeur n’a pas été recalculé avec Excel. Les différences attendues de logique sont documentées. Aucune égalité aveugle aux résultats Excel n’est recherchée lorsque la règle actuelle est ambiguë ou inadéquate.

Aucune garantie d’absence absolue de défaut n’est revendiquée. Les tests et les limites donnent une base concrète pour une recette métier avant usage opérationnel.
