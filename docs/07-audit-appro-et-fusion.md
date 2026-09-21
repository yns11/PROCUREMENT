# Audit actualisé d’APPRO et fusion dans PROCUREMENT

**Date : 21 septembre 2026.** Source auditée : `yns11/APPRO`, branche `claude/vibrant-dirac-lmhxj9`, commit **804b27117850748fffb996a1d93ae087882dba2f**. La branche `main` d’APPRO ne contient toujours pas l’application complète. Point de comparaison PROCUREMENT : `5700aaf46103a3dbd8ce8fbfc9f6174ef97d69b5`.

L’audit porte sur le code effectivement présent, ses tests et des reproductions exécutées dans une copie isolée. Aucune modification, aucun commit ni aucune écriture distante dans APPRO. La demande « XYZ » du premier audit est interprétée comme APPRO.

## Conclusion

APPRO constitue la meilleure base d’interface et offre une couverture métier plus large que PROCUREMENT V1 : navigation, trois niveaux de stock, modes de rupture, carnet de commandes, PDP versionné, paramétrage et saisie en grille. Ses nouvelles fonctions améliorent nettement l’usage, mais plusieurs défauts de fiabilité subsistent. La bonne stratégie est une reprise de ses composants dans PROCUREMENT avec une frontière transactionnelle, des scénarios figés et des échanges Excel contrôlés.

C’est la stratégie appliquée dans la V2 : React/TypeScript et moteur modulaire issus d’APPRO ; protections, migration et décisions métier reprises de PROCUREMENT ; export de simulation reconstruit selon la demande. La couverture du commit audité est reprise, avec des changements intentionnels de comportement détaillés ci-dessous. L’application n’est pas déclarée certifiée en production sans recette sur les tables UC et le Lakebase du workspace cible.

## Changements d’APPRO depuis l’audit précédent

Deux commits succèdent à `0b753a9` : `3a50a21` puis `804b271`.

- Trois couches cumulatives : ferme, prévisionnelle, simulée.
- Distinction stock physique non négatif, solde net et manque.
- Politiques `backlog` (report) et `lost` (perte du besoin non servi).
- Cellules simulées persistées, expressions arithmétiques, origine MANUAL/IMPORT/CBN.
- Calcul CBN à la demande ; son résultat est écrit dans la grille.
- Export Excel à formules ; saisie des commandes simulées dans SIMULATION, avec encore des feuilles auxiliaires pour d’autres flux.
- Désactivation des workflows CI/suivi de PR dans APPRO.

Le défaut de double acceptation de l’ancien écran de propositions n’est **pas** attribué à la version actuelle : cet écran et son ancien mécanisme ont été remplacés. En revanche, l’isolation du nouveau CBN devient un problème central.

## Méthode et preuves

1. Lecture des branches et des différences Git ; audit des modules métier, adaptateurs UC, services, API, stockage, UI, imports/exports, configuration et tests.
2. Exécution de la suite APPRO inchangée : **35 tests réussis en 46,49 s** dans cet environnement. Ce temps comprend sa régression sur les données du classeur ; ce n’est pas un benchmark comparable à la nouvelle suite synthétique.
3. Reproductions isolées, sans appels à un ERP ni écritures dans APPRO : commande de 100/réception de 60, changement de base après création d’un scénario, CBN de scénario, paramètre invalide et lissage décimal.
4. Tests de PROCUREMENT V1 conservés ; tests V2 synthétiques ; recalcul natif des classeurs et pipeline navigateur séparé.

Les résultats bruts sont dans [preuves/audit-appro-804b271.json](preuves/audit-appro-804b271.json). Les reproductions ne contiennent pas de données opérationnelles. Les tests hérités qui dépendaient du classeur réel n’ont pas été redistribués ; leurs contrôles applicatifs sont remplacés par des jeux synthétiques et des assertions portant sur les politiques corrigées.

## Points forts

| Domaine | Apport vérifié | Intérêt pour PROCUREMENT |
|---|---|---|
| Architecture | `engine`, `data`, `services`, `api` séparés | Moteur testable hors UI et hors Databricks |
| Calcul | NumPy, séries journalières, stocks cumulés | Bonne base pour calculer plusieurs articles sans boucles par cellule UI |
| Métier | BOM, rebut, validité, réel/PDP, sources de commandes, calendrier fournisseur | Couverture sensiblement supérieure à une simple extrapolation de stock |
| Stock | Physique/net/manque, trois couches, deux politiques | Rend visibles les hypothèses de disponibilité et les conséquences d’une rupture |
| CBN | Action explicite, MOQ, conditionnement, délai, quotas, motifs | Interaction lisible ; l’affichage n’ajoute plus automatiquement des commandes |
| UX | React, filtres globaux, fiches, pivot, graphiques, thèmes, composants réutilisables | Meilleure continuité entre diagnostic, détail et action |
| Gestion | PDP versionné, journal, scénarios, paramètres documentés | Les opérations ne se limitent pas au calcul MRP |
| Excel | Formules et saisie de commandes simulées | Transition progressive depuis le travail sous Excel |

## Faiblesses et corrections prioritaires

Les chemins ci-dessous désignent le commit APPRO audité. **Reproduit** signifie exécuté ; **lecture** signifie démontré par le chemin de code, sans prétendre à une mesure de production.

| Priorité | Constat APPRO et preuve | Conséquence | Traitement dans PROCUREMENT V2 |
|---|---|---|---|
| P0 | `api/routers/entries.py:92` additionne la nouvelle réception après qu’un autoflush SQLAlchemy l’a déjà incluse dans la somme. **Reproduit : 60 reçus sur 100 → statut RECEIVED.** | Clôture prématurée et disparition du reliquat | Somme unique, contrôle du solde, calcul du reliquat depuis les réceptions ; suppression d’une réception rétablit la disponibilité |
| P0 | `services/mrp_service.py:132,262` lit/réinitialise les cellules sans scénario. **Reproduit : CBN de scénario → 11 cellules visibles dans la base.** | Une simulation modifie le portefeuille commun et les autres simulations | Clé de cellule incluant le scénario ; contrôle d’accès avant reset ; tests de non-contamination |
| P0 | Scénario stockant des événements mais recalculé sur la base courante. **Reproduit : un ajustement de base change les séries d’un scénario sauvegardé.** | Comparaisons non reproductibles | Dataset et paramètres figés ; comparaison avec la même base figée ; duplication explicite |
| P0 | `api/deps.py` identifie un utilisateur mais n’impose pas de rôle métier ; absence d’identité remplacée par une valeur de secours | Le proxy Databricks ne remplace pas l’autorisation de modifier/administrer | Identité obligatoire en production, lecteurs/éditeurs/admins, scénarios privés, écritures avec révision |
| P0 | Aucun verrou optimiste sur les modifications métier | Écrasements silencieux entre approvisionneurs | `If-Match` et mise à jour atomique du compteur en PostgreSQL ; conflit HTTP 409 |
| P1 | Contrôle de paramètres insuffisant. **Reproduit : horizon global -50 enregistré, HTTP 200.** | Configuration invalide persistante, erreurs ou calculs hors budget | Validation des types, enums, bornes et cohérence avant commit ; transaction annulée si invalide |
| P1 | `data/schemas.py:76–82` transforme les valeurs numériques illisibles en zéro et les dates en valeurs absentes | Fausse absence de besoin ou de stock | Erreur explicite sur données non convertibles, clés dupliquées et colonnes absentes ; validation du dataset |
| P1 | Cache de résultats `services/context.py:48` sans expiration, indépendant du rafraîchissement réel des données | ERP actualisé mais affichage ancien | Cache borné dans le temps et indexé par révision ; cache source par génération |
| P1 | Lecture UC table par table, sans lot commun ni borne de lignes | Mélange de publications ERP, coût mémoire non maîtrisé | Contrat `batch_id`, manifeste READY, contrôles de fraîcheur, cohorte complète, limites de lignes et de calcul |
| P1 | Import actif de PDP remplace toutes les semaines des programmes présents | Un import partiel supprime implicitement les semaines non fournies | Remplacement limité au couple programme/semaine ; arrêt sur doublons ou lignes invalides |
| P1 | `engine/demand.py:43` arrondit le total en mode exact. **Reproduit : 2519,748 → 2520.** | Dérive des quantités fractionnaires | Conservation du total décimal ; règle historique `per_day` disponible explicitement |
| P1 | `engine/proposals.py:155–156` lot fixe calculé sans appliquer simultanément MOQ et conditionnement | Ordre impossible pour le fournisseur | Multiple commun décimal lot fixe/conditionnement, puis MOQ |
| P1 | Sélection de lien actif sans exclusion complète du fournisseur inactif ou du calendrier incompatible | Proposition non exécutable | Exclusion des sources inactives/incompatibles ; absence de source signalée |
| P1 | `respect_lead_time=False` par défaut | Livraison théorique proposée avant le délai | Délai respecté par défaut ; mode d’urgence explicite conservé |
| P1 | Calcul cible/couverture borné par le tableau, sans prolongement du PDP | Biais en fin d’horizon | Fenêtre de calcul prolongée, demande future masquée dans Excel, horizon visible inchangé ; alerte en cas de PDP insuffisant |
| P1 | Scénario changeant l’origine d’une commande modifiée en SCENARIO | Une commande ERP déplacée peut changer de couche ou contourner la sélection des sources | Origine ERP/APP conservée lors des modifications |
| P1 | Export `excel_service.py:331–349` : stock net étiqueté stock, couverture comptée en périodes ; calcul hebdomadaire après agrégation | Décalage moteur/Excel ; pertes journalières masquées par les arrivages ultérieurs | Stocks physiques et soldes nets séparés ; calcul journalier ; couverture en jours ; synthèse hebdomadaire après calcul |
| P1 | Réimport d’onglets additionnels et de cellules sans manifeste d’export ni idempotence | Doublons, écrasement ou import de formules sans résultat enregistré | Manifeste serveur lié au propriétaire, contrôles du fichier, expressions arithmétiques bornées, détection de doublon, nouveau scénario |
| P1 | Édition d’un total hebdomadaire par écriture sur une seule date | Conservation possible d’autres cellules de la semaine, total incohérent | Saisie au jour ; depuis la semaine, bascule vers la vue journalière |
| P2 | Sourcing et motifs du CBN conservés essentiellement en texte de cellule/session UI | Décision et reprise moins robustes | Propositions structurées persistées ; accepter/ignorer/quantité modifiée ; audit et rejet de double décision |
| P2 | Journal incomplet avant/après, identifiants attribués tardivement | Traçabilité fragile | Identifiants avant insert et snapshots avant/après dans la transaction |
| P2 | Totaux de quantités pouvant mélanger KG et pièces | KPI sans signification physique | KPI principal de commandes exprimé en nombre d’articles ; quantités détaillées avec unité. Les agrégats historiques restant dans l’API sont explicitement techniques, à ne pas employer comme KPI économique |
| P2 | UI initiale volumineuse, navigation mobile dense, gestion de focus modale incomplète | Chargement et accessibilité perfectibles | Chargement par page, focus clavier, retour de focus, lien d’évitement, menus et barre de filtres adaptatifs |
| P2 | CI désactivée dans le dernier commit APPRO | Régressions moins détectables | CI PROCUREMENT : backend, typecheck/build, navigateur et recalcul Excel |

Les accès directs de développement sans proxy ont bien accepté une écriture lors du test. Cela ne démontre pas une exposition publique de l’instance Databricks d’APPRO : le problème établi est l’absence de contrôle de rôle applicatif et de configuration production fermée dans son code.

## Matrice de couverture

| Fonction actuelle d’APPRO | PROCUREMENT V1 | PROCUREMENT V2 | Validation principale |
|---|---|---|---|
| Cockpit et filtres globaux | Partiel | Repris, amélioré | API + build + scénario navigateur |
| Fiches, graphiques, tableau jour/semaine | Partiel | Repris | Sommes jour/semaine |
| Thèmes clair/sombre/système | Limité | Repris | Frontend typé |
| Référentiels articles/fournisseurs/liens/programmes/BOM | Contrat canonique | Écrans repris + contrôles | Endpoints de référence |
| Besoin PDP + réel prioritaire + vrai zéro | Oui | Conservé | Tests moteur |
| Répartition hebdomadaire et rebut/validité BOM | Partiel | Repris + précision corrigée | Tests moteur |
| Décalage de consommation | Non | Repris | Paramètres et moteur |
| Trois couches de stock | Non | Repris | Tests de cumul |
| Stocks physiques/net/manques | Partiel | Repris | Tests politiques + Excel natif |
| Backlog/perte de demande | Backlog | Deux modes | Tests moteur et Excel |
| Couverture jours ouvrés/calendaires, égalité configurable | Oui/partiel | Repris + alerte de borne | Tests moteur et Excel |
| Cible couverture/sécurité/max | Règle additive | Repris + option somme V1 | Tests moteur |
| MOQ/conditionnement/lot fixe/cycle | Partiel | Repris, règles combinées | Tests moteur |
| Sourcing quotas/priorité, calendrier fournisseur | Partiel | Repris | Tests moteur |
| Sources ERP/app/fusion, gestion du retard | Oui | Repris | Moteur et paramétrage |
| CBN explicite et cellules calculées | Propositions | Repris et isolé | API de CBN/scénarios |
| Expressions dans la grille | Non | Repris et borné | Tests expressions/API |
| Commandes/réceptions/ajustements/réel | Oui | Écrans CRUD + audit | Tests partiel/réversalité |
| PDP Excel long et historique, activation/version | Import simple | Repris + contrôle atomique | Test PDP partiel |
| Scénarios par événements et simulation libre | Dataset complet | Repris + base figée/clone | Scénarios et migration |
| Paramètres par article/lien/globaux | Partiel | Repris + rôle admin | Validation et autorisations |
| Exports simulation/alertes/carnet | Oui | Repris ; simulation reconstruite | API et recalcul natif |
| Réimport simulation | Oui | Nouveau scénario, contrôlé/idempotent | Aller-retour de grille |
| Décisions accepter/modifier/ignorer | Oui | Ajoutées au nouveau CBN | Test non-duplication |
| Contrôle de version, scénarios privés | Oui | Conservés dans le nouveau socle | Tests 409/403 |
| Historique et récupération V1 | Oui | Journal, révisions de définition, import V1 | API migration/clone |

## Choix intentionnels et limites

- La reprise est fonctionnelle, pas une exigence de reproduire les bugs : délai sûr, paramètres invalides refusés, scénario isolé, total fractionnaire conservé et saisie quotidienne changent volontairement certains résultats.
- La simulation Excel travaille sur des **flux agrégés par article et jour**. Une commande signifie un solde à livrer. Une réception nouvelle nécessite de diminuer le solde correspondant dans la grille pour ne pas compter deux fois le même flux. L’application conserve le rapprochement détaillé des commandes/réceptions réelles ; l’export de simulation n’est pas un outil de comptabilisation ERP.
- Les décisions restent locales ; aucun DELJIT, DELFOR, bon d’achat ou message fournisseur n’est envoyé automatiquement.
- Les scénarios partagent le référentiel figé à leur création ; les écrans de référence affichent le référentiel opérationnel courant. Le moteur du scénario utilise bien sa copie figée.
- Le calcul vectorisé est en flottants ; les arrondis fournisseurs utilisent Decimal. Ce n’est pas un module de valorisation comptable. La V1 Decimal est conservée comme oracle, sans prétendre à une égalité bit à bit entre politiques différentes.
- Le MRP est mono-niveau. Ni APPRO ni cette reprise ne réalisent un APS à capacité finie, une réservation physique d’entrepôt, une optimisation globale multi-usines ou un lancement automatique d’ordres.
- Le contrat UC suppose une publication immuable et cohérente de chaque lot READY. L’intégration des vraies tables ERP exige un mapping validé des clés, unités, dates, soldes déjà reçus et politiques de stock. La V2 ne devine pas cette sémantique.

## Recommandations restantes après fusion

1. **Avant production :** mapper les onze vues/tables canoniques vers UC, certifier le grain, le batch, les unités, l’état des réceptions déjà intégrées au stock et la signification métier de PLA. Attacher Lakebase et vérifier rôles, restauration et rotation OAuth dans le workspace cible.
2. **Recette métier :** confronter une semaine complète à l’ERP pour chaque famille de cas : partiel, retard, retour, correction d’inventaire, multi-source, stock bloqué et absence de PDP. Les écarts doivent être expliqués par une règle versionnée.
3. **Montée en charge :** mesurer les portefeuilles réels, envisager des vues UC préfiltrées et des calculs asynchrones par périmètre au-delà du budget interactif. Les performances sur huit articles synthétiques ne préjugent pas de celles sur des milliers d’articles.
4. **Évolutions ultérieures :** groupes d’accès synchronisés avec l’IAM, journal réglementaire à rétention dédiée, historisation complète de tous les états de simulation et workflow d’approbation achats avant publication ERP. Ces développements ne sont pas présentés comme déjà validés.

## Sources de plateforme

Les en-têtes utilisateur restent fiables uniquement derrière le proxy Databricks, et les permissions du service principal sont distinctes de celles des utilisateurs : [modèle d’autorisation Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth).

Lakebase est un stockage PostgreSQL durable ; ses ressources injectent les variables PG* et les ressources Autoscaling utilisent la clé `postgres` : [ressources Lakebase](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase). Le déploiement doit respecter le type de ressource existant : il ne faut pas transformer arbitrairement une ressource `database` en `postgres`.
