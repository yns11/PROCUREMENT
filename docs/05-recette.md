# Recette et limites de validation

## Automatisation locale

`python -m pytest -q` exécute les tests métier, API et échanges. Les tests utilisent des données fictives et une base SQLite temporaire. Ils ne remplacent pas les tests d’intégration PostgreSQL/UC dans le workspace.

| Cas | Résultat attendu |
|---|---|
| PDP hebdomadaire non divisible par jours ouverts | Somme journalière exactement égale au total de départ |
| Fermeture de semaine avec PDP non nul | Calcul refusé |
| Réalisé explicitement nul | Remplace le prévu en actual_preferred |
| Réalisé absent | Repli au plan ; actual_only refuse l’absence |
| Réception partielle | Réception physique + reliquat = quantité restant à recevoir à l’ancrage |
| Réception décalée et complète | Stock crédité à la date de réception, jamais une seconde fois à la date initiale |
| Brouillon | Effet sur stock simulé uniquement |
| Délai trop long | Livraison faisable postérieure au besoin, rupture maintenue |
| MOQ et multiple fractionnaire | Arrondi supérieur conforme |
| Quotas incorrects | Sauvegarde refusée |
| Réception après consommation | Alerte même si stock final positif |
| PDP trop court après l’horizon | Cible indisponible et avertissement ; pas de zéro implicite |
| Deux onglets modifient la même version | Deuxième sauvegarde refusée avec conflit |
| Utilisateur différent | Scénario inaccessible |
| Réimport du classeur exporté | Même contrat d’entrée et résultats recalculables |
| Formule dans une feuille d’entrée | Import refusé |
| Texte commençant par = dans une désignation exportée | Chaîne de caractères, pas de formule exécutable |
| Passage de semaine à cheval sur le nouvel an | Dates ISO conservées |

## Recette interface

Sur ordinateur et mobile : ouvrir le cockpit, filtrer les références, cliquer un article, changer la granularité, accepter une proposition après édition, vérifier son statut brouillon, saisir une réception, tester une saisie invalide, dupliquer le scénario et restaurer une version. Vérifier la navigation clavier, les erreurs visibles et l’absence de débordement horizontal global. Les tableaux ont leur propre défilement horizontal.

## Recette dans Databricks à effectuer

- Lire une vue UC autorisée, puis une vue sans permission pour vérifier le diagnostic.
- Publier un lot cohérent, un lot ancien, des lots mélangés et une donnée invalide : seuls les jeux conformes sont acceptés.
- Vérifier la correspondance entre identité affichée et utilisateur connecté.
- Simuler deux sessions simultanées et contrôler l’unicité des numéros de révision dans PostgreSQL.
- Redéployer l’App : les scénarios et l’historique doivent rester présents.
- Laisser expirer le premier jeton Lakebase, ouvrir une nouvelle connexion et vérifier le renouvellement.
- Restaurer une sauvegarde de la base dans l’environnement de recette.
- Comparer manuellement le besoin et le stock de quelques articles représentatifs : mono-source, multi-source, kg, faible rotation, réception partielle, retard, semaine fermée.
- Faire valider les hypothèses métier par les utilisateurs et les accès par les propriétaires des données.

## Périmètre livré et suites

Le lot livré couvre le MRP prioritaire, les données manuelles/ERP sous forme de snapshots, les scénarios privés, les propositions, les réceptions/ajustements, les imports/exports et le cockpit de projection. Les tableaux de performance fournisseur et d’EDI historiques, l’ordonnancement de capacité finie, le write-back ERP, les envois automatiques, le partage collaboratif d’un scénario et l’optimisation multi-échelons ne sont pas implémentés. Le cadrage donne la priorité au MRP ; ces extensions restent des travaux distincts.

L’analyse du classeur est livrée et l’extracteur de staging est disponible. Il ne s’agit pas d’une migration automatique validée du classeur industriel : les liens historiques commande/réception, les délais et la signification d’engagé ne peuvent pas être déduits avec certitude de la grille seule.
