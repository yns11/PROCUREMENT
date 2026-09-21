# Recette V2

## Vérifications automatiques

- Suite PROCUREMENT V1 conservée comme oracle de non-régression de l’ancien contrat.
- Unités V2 : calendriers, lissage, réel zéro, nomenclature, stock, trois couches, MOQ/multiples, propositions, délais, quotas, scénarios et expressions.
- API V2 : neuf familles de lecture, réception partielle/réversalité, contrôle d’entrée, conflit 409, scénarios figés, CBN isolé/reproductible, acceptation sans double flux, rôles/privacité, duplication, migration V1, PDP partiel, Excel inchangé/modifié/réimporté.
- Excel natif : quatre configurations (`backlog`/`lost` × jours calendaires/ouvrés), avec fermeture de site et modification de cellules ; recalcul LibreOffice puis comparaison de chaque cellule de stock, manque, cible et couverture au moteur Python.
- Frontend : TypeScript et build Vite ; script Playwright de neuf routes, calcul CBN, décision d’acceptation et menu mobile. Son exécution navigateur dépend de la disponibilité des sockets/processus Chromium dans l’environnement. La CI prévoit un runner Ubuntu complet ; ne pas confondre un build réussi avec une recette visuelle réussie.

## Cas à faire signer par le métier

| Cas | Résultat attendu |
|---|---|
| 100 commandés, 60 reçus | 40 à livrer ; 60 ajoutés au stock à la date de réception si après snapshot |
| Suppression de cette réception | Solde à livrer restauré à 100, flux de réception supprimé |
| Réception déjà publiée par l’ERP | Un seul flux grâce au rapprochement d’identifiant |
| Réel déclaré à zéro | Zéro remplace le plan pour cette journée |
| PDP incomplet | Avertissement et CBN limité, pas de présomption silencieuse de demande nulle |
| MOQ 100, pack 30, besoin 80 | 120 proposés |
| Lot fixe + conditionnement | Quantité respectant les deux multiples et le MOQ |
| Fournisseur inactif / calendrier incompatible | Aucune proposition sur cette source |
| Commande en retard | Effet conforme à la politique choisie et visible dans les alertes |
| Besoin perdu puis réception tardive | La réception ne sert pas rétroactivement le besoin perdu |
| Scénario puis modification de base | Le scénario reste identique |
| CBN dans un scénario | Aucune cellule ajoutée au portefeuille de base |
| Accepter puis cliquer à nouveau | Une seule commande planifiée, deuxième action refusée |
| Export semaine avec rupture mercredi et arrivée vendredi | Calcul quotidien conservé ; manque perdu de mercredi non effacé |
| Grille Excel inchangée | Aucune saisie ni réception supplémentaire |
| Modifier un besoin/flux/ajustement Excel | Nouveau scénario ; projection recalculée ; pas d’écriture ERP |
| Même fichier réimporté | Pas de doublon |
| Deux éditeurs concurrents | Deuxième écriture obsolète refusée, rechargement explicite |

## Limites de validation

Le recalcul a été vérifié avec LibreOffice, pas avec un automate Excel Desktop. Les formules utilisent des fonctions compatibles Excel courantes (`SUM`, `MAX`, `IF`, `COUNTIF`, `SUMIF`) et demandent un recalcul complet à l’ouverture.

La recette locale utilise huit articles synthétiques. Elle ne valide pas les véritables tables UC, la configuration Lakebase, l’IAM du workspace, la reprise d’une base de production ni le temps de réponse d’un portefeuille industriel complet. Ces points restent des étapes de mise en service, documentées et non présentées comme accomplies.
