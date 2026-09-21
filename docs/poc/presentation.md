# Présentation du POC — 10 à 15 minutes

## Préparation

1. Démarrer l’application de la branche `feat/poc-simulation-management`.
2. Dans **Paramètres**, cliquer **Réinitialiser la démonstration** et confirmer.
3. Choisir un horizon de **60 jours**. La date de référence est le **21/09/2026**.
4. Utiliser `DEMO-001 — Connecteur de phase`, unité PCE. Le programme fictif est `MOTEUR-A`.
5. Pour chaque scénario indépendant, réinitialiser à nouveau. Les chiffres ci-dessous supposent les paramètres initiaux.

Les fichiers joints à des imports sont des exemples fictifs. Deux articles, un programme, 24 semaines de PDP et deux commandes sont présents dès l’ouverture.

## 1. Charger les données et normaliser les dates — 2 minutes

- Ouvrir **Référentiel**, puis les onglets **Articles** et **Nomenclatures (BOM)**. Montrer les cellules éditables.
- Ouvrir **Commandes** et télécharger **Exemple CSV**. Le fichier contient une commande ferme de 200 pièces au jeudi **24/09** et un prévisionnel de 200 pièces au mercredi **30/09**.
- Charger ce fichier. Le prévisionnel apparaît au lundi **28/09** dans l’aperçu. Cliquer **Enregistrer**.
- Autre démonstration : saisir `30/09/2026` dans Livraison ligne 2 puis Enregistrer ; la valeur devient `28/09/2026`.
- Ouvrir la fiche `DEMO-001`, cliquer **Jour** au-dessus du tableau. Les 200 pièces prévisionnelles figurent au 28/09 ; aucune quantité prévisionnelle ne figure au 30/09. Les 200 pièces fermes restent au 24/09.

**Message oral :** le plan prévisionnel s’exprime à la semaine, le ferme garde sa date d’exécution.

## 2. Montrer le CBN puis augmenter le PDP — 3 minutes

Après réinitialisation, dans la fiche `DEMO-001`, vue Jour :

| Indicateur au lundi 28/09 | Avant changement du PDP | Après changement |
|---|---:|---:|
| PDP de la semaine | 250 moteurs | 400 moteurs |
| Besoin composants du lundi | 100 pièces | 160 pièces |
| Stock ferme de fin de lundi | 200 pièces | 140 pièces |
| Total des propositions CBN sur 60 jours, après relance | 4 000 pièces | 4 300 pièces |

1. Lancer **Calcul CBN**. La première proposition est de **800 pièces au lundi 28/09**. Toutes les autres propositions sont également des lundis.
2. Aller dans **PDP** ; pour `MOTEUR-A`, ligne du **28/09**, remplacer **250 par 400**, puis **Enregistrer**.
3. Revenir à la fiche : le besoin et les stocks sont déjà mis à jour.
4. Relancer **Calcul CBN** pour remplacer les propositions de l’ancien calcul. Le total est maintenant de **4 300 pièces**, contre 4 000 initialement.
5. Basculer entre Jour et Semaine. Le calcul reste quotidien ; les flux hebdomadaires sont sommés et les stocks sont ceux de fin de semaine.

**Message oral :** PDP → nomenclature → besoins composants → stocks projetés → nouvelles propositions. L’affichage n’engendre pas de commande ; le CBN se relance explicitement.

## 3. Transformer le simulé en ferme sans doubler le stock — 3 minutes

1. Réinitialiser. Ouvrir `DEMO-001`, puis **Calcul CBN**.
2. En vue Jour, repérer les **800 pièces simulées au 28/09**. Le stock simulé de fin de journée est **1 200 pièces**.
3. Cliquer **Saisir** ; choisir commande ferme, fournisseur `FOURN-01`, livraison **28/09/2026**, quantité **800**, puis Enregistrer.
4. Au 28/09 :

| Ligne | Avant | Après |
|---|---:|---:|
| Commandes fermes | 0 | 800 |
| Commandes simulées | 800 | 0 |
| Stock simulé | 1 200 | 1 200 |

5. Ouvrir **Commandes** : la nouvelle commande est présente et éditable.

**Message oral :** une quantité devenue ferme ne s’ajoute pas une seconde fois à la simulation.

## 4. Montrer le reliquat et la réversibilité — 2 minutes

Continuer le scénario 3 **sans relancer le CBN** entre les étapes :

- Dans Commandes, réduire cette nouvelle commande de **800 à 400**, puis Enregistrer.
- Au 28/09, **400 fermes + 400 simulées**. Le stock simulé reste **1 200**.
- Supprimer uniquement la nouvelle commande, puis Enregistrer : **0 ferme + 800 simulées** réapparaissent.
- Rafraîchir la page : le résultat reste identique, sans absorption supplémentaire.

La même règle s’applique à une quantité simulée positive saisie manuellement dans la grille. Elle s’applique au **même article et au même jour**, pas à une autre date de la semaine.

## 5. Paramétrage, Excel et périmètre futur — 2 minutes

- Dans Référentiel → Nomenclatures, passer le coefficient de `DEMO-001` de **2 à 3** ; Enregistrer. À PDP inchangé de 250 moteurs, le besoin quotidien passe de **100 à 150 pièces**. Relancer le CBN pour adapter les propositions.
- Montrer les paramètres de couverture, gestion du manque, délai et positionnement au lundi. Les règles de lot et de délai de chaque article se modifient dans Référentiel → Articles.
- Dans une fiche, cliquer **Excel**. Les saisies sont dans la grille de simulation. Les calculs restent quotidiens même avec une synthèse hebdomadaire.
- Cliquer les quatre autres onglets de la fiche : ils sont volontairement vides. Expliquer oralement que ces fonctions et leurs décisions métier/UX restent à construire.

## Ce que le POC démontre — et ses limites de lecture

Ce sont des données fictives, des règles explicitement choisies pour la présentation et un périmètre réduit. Aucun ordre fournisseur ni aucune donnée ERP n’est publié. Le rapprochement de simulation repose sur article/date ; il ne remplace pas une traçabilité OA/ligne/fournisseur en production.

Les chiffres jour ne se lisent pas dans une colonne semaine : les stocks hebdomadaires sont des fins de semaine. Réinitialiser remet les données et paramètres initiaux ; l’horizon reste sélectionnable en haut de l’écran.
