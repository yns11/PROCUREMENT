# Analyse du processus Excel existant

L’analyse porte sur le cadrage Word et le classeur de simulation fournis pour le projet. Elle a été effectuée en lecture seule sur les cellules, les tables, les noms définis, les formules et leurs valeurs en cache. Les données industrielles, identités fournisseurs et volumes opérationnels ne sont pas repris dans ce dépôt public.

## Structure constatée

| Onglet | Dimensions utilisées | Formules | Rôle |
|---|---:|---:|---|
| BASE ARTICLE | 21 × 10 | 0 | 20 liens article fournisseur, 16 références distinctes, MOQ, approvisionneur, couverture, indicateurs et contacts |
| BOM | 29 × 875 | 24 360 | 28 lignes de nomenclature et explosion des besoins journaliers |
| SOP - PDP | 28 × 126 | 0 | Programme de production hebdomadaire saisi |
| PREVU - ENGAGÉ | 32 × 876 | 13 676 | Prévu, engagé et effectif par programme et jour |
| SIMULATION | 135 × 879 | 31 325 | Besoin, commande, réception, ajustement, stock, cible et couverture |

Total : **69 361 cellules de formule**. Les séries J400 à J1269 représentent 870 positions calendaires. Aucune connexion, liaison externe, table croisée dynamique ou macro VBA n’a été détectée dans le conteneur XLSX. Cela décrit ce fichier, pas d’éventuels outils externes de l’utilisateur. Aucune cellule d’erreur n’a été trouvée dans les valeurs en cache ; ceci ne prouve pas que les formules sont toutes correctes ni que le classeur a été recalculé récemment.

## Chaîne de calcul observée

Le PDP est saisi par semaine et programme. Le journal prévu retrouve la semaine du jour, recherche la quantité dans le PDP, divise par cinq et arrondit à l’entier. Les week-ends ne suivent pas cette formule. Le journal engagé contient des valeurs et parfois des additions écrites comme formules. L’effectif choisit l’engagé s’il est renseigné, sinon le prévu.

Chaque ligne BOM multiplie cet effectif par sa quantité unitaire. La simulation additionne ensuite les lignes BOM par composant. Pour le stock, la formule prend le stock du jour précédent, ajoute la réception si elle est renseignée, sinon la commande du même jour, ajoute les ajustements et soustrait le besoin.

La cible additionne des besoins futurs selon une couverture définie au référentiel. La couverture recherche le premier franchissement du stock dans le cumul des besoins futurs, avec des valeurs de repli en cas d’erreur. Les calculs utilisent notamment XLOOKUP, LET, FILTER, SEQUENCE et SCAN. Les stocks initiaux et certains besoins sont saisis directement. Le portefeuille est partagé entre plusieurs programmes ; certains articles sont multisourcés.

Les sorties actuelles sont donc une grille de projection, des saisies de commandes/réceptions/corrections et des indicateurs de couverture. Le fichier ne constitue pas un registre transactionnel de lignes de commande : les montants sont agrégés par référence et jour.

## Faiblesses et réponse applicative

| Constat vérifiable ou risque déduit | Conséquence | Réponse livrée |
|---|---|---|
| Cinq noms contiennent #REF! : AJAUNE, ALERTEPROG, AROUGE, ASURSTOCK, DATESSIMU | Dépendances cassées ou vestigiales ; impact à vérifier dans Excel | Contrat typé, validation avant calcul |
| Répartition /5 avec arrondi par jour | Écart possible au total hebdomadaire, fermetures non intégrées | Répartition sur calendrier avec conservation exacte du total |
| Réception du jour remplace globalement la commande | Réception partielle ou décalée difficile à rapprocher | Identifiants de ligne et réception, reliquat calculé |
| Engagé choisi selon renseignement | Le sens métier d’engagé n’est pas forcément « réalisé » | Mode explicite et zéro distinct d’absence ; mapping à confirmer |
| Grille de 870 jours | Maintenance et lecture complexes | Horizon visible 7 à 366 jours, demande future conservée pour couverture |
| Corrections arithmétiques dans les cellules | Auteur et motif non reconstituables | Ajustements signés motivés, versions et audit |
| Plages de couverture basées sur des positions de colonnes | Décalage possible entre colonne absolue et indice de tableau | Indexation par date testée ; pas de numéro de colonne métier |
| IFERROR et valeur -1 | Donnée manquante ou calcul invalide peuvent devenir un résultat plausible | Erreur explicite ou couverture censurée |
| Plusieurs fournisseurs par article et recherches premières occurrences | MOQ/délai/fournisseur potentiellement ambigus | Liens distincts, priorité ou quotas |
| Pas de délai fournisseur explicite utilisable dans la base observée | Ordonnancement irréalisable si délai supposé nul | Délai obligatoire à valider au paramétrage |
| Stock et commandes issus de saisies mêlées aux résultats | Difficile de distinguer un engagement réel d’une idée | Stock ferme / simulé, brouillons / confirmés |
| Pas d’unité article normalisée dans la base article | Confusion kg/m/pièces ou conversions implicites | Unité article et unité BOM cohérentes ; conversion amont explicite |
| Pas de version de scénario | Comparaison et retour arrière difficiles | Duplication, journal, restauration non destructive |
| Copies par portefeuille | Règles susceptibles de diverger | Moteur partagé et tests reproductibles |
| Pas de contrôle d’édition simultanée | Perte de saisies concurrentes | Verrou optimiste et HTTP 409 |
| Pas de fraîcheur source tracée | Risque de décision sur données obsolètes | Lot UC cohérent et contrôle d’âge à l’import |

## Reprise

La reprise ne doit pas reconstituer artificiellement des commandes fermes à partir des agrégats journaliers. Utiliser l’ERP pour le carnet ouvert et les réceptions, et le classeur pour le référentiel/PDP après rapprochement. `scripts.inspect_legacy` produit un inventaire JSON local des données sources et des anomalies pour préparer ce rapprochement. Il n’écrit pas de données dans l’ERP ni dans la base applicative.

La couverture cible, le sens d’engagé, les délais, le PLA, les quotas, les calendriers, les unités, la date/heure du stock initial et la distinction DELFOR/DELJIT doivent être validés avec l’équipe avant la bascule. Les règles proposées dans le document suivant sont des choix de conception paramétrables, pas des décisions déjà confirmées par les métiers.
