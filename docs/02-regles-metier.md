# Règles métier et variantes

Le moteur est un MRP déterministe à nomenclature un niveau. Il aide à décider ; il n’émet aucune commande ni message EDI. Les règles ci-dessous sont proposées comme configuration de départ. Elles doivent être confrontées aux pratiques du site lors de la recette.

## Référentiel et grain

Une simulation représente un site, une unité de stock par article et un portefeuille. Un article peut avoir plusieurs fournisseurs. Les stocks de plusieurs sites, statuts qualité, propriétaires ou unités doivent être séparés ou normalisés en amont ; l’application n’invente pas de conversion.

La clé BOM est programme × composant. Les doublons sont refusés ; si l’ERP a plusieurs positions identiques, les agréger avec justification avant import. Il n’y a ni explosion récursive ni netting de stocks intermédiaires. Le PDP doit donc contenir les programmes effectivement pilotés au niveau choisi, sans double explosion d’un parent et de son semi-fini.

## Calendrier et demande

- `settings.start` est le début de journée du stock initial ; le stock contient tous les mouvements strictement antérieurs. L’application travaille en dates locales du site, sans heures intra-journalières.
- Chaque semaine PDP est identifiée par son lundi ISO complet, jamais par un numéro de semaine seul.
- Les quantités hebdomadaires sont réparties uniformément sur les jours ouverts, après retrait des fermetures. Un résidu de précision est attribué au dernier jour pour conserver exactement la quantité de départ. Les fractions de production sont acceptées, comme dans le PDP fourni ; le besoin composant reste décimal.
- Une semaine totalement fermée accepte uniquement une quantité nulle. Les jours fermés ont un besoin prévu nul. Une production réelle explicitement renseignée un jour fermé reste prise en compte.
- `plan` utilise le PDP. `actual_preferred` remplace chaque programme/jour renseigné par le réalisé, même zéro. `actual_only` exige du réalisé pour chaque jour ouvert de l’horizon.
- Il n’y a pas de report automatique de la différence prévu/réalisé sur le reste de semaine : ce rattrapage nécessite une révision explicite du PDP. Il n’y a pas non plus de consommation du forecast par une autre demande non fournie.
- Les besoins valent somme(production × quantité BOM). Un PDP absent sur l’horizon bloque le calcul ; zéro doit être explicite. Au-delà de l’horizon, une profondeur insuffisante rend certaines cibles indisponibles et produit un avertissement.

## Flux et stock

La quantité totale d’une commande inclut le reçu antérieur au stock initial. Le reliquat ouvert vaut `quantity - received_before_start - somme(receipts de cette ligne)`. Les réceptions sont rattachées à une ligne confirmée et présentes une seule fois. Les surréceptions, quantités négatives et identifiants dupliqués sont rejetés. Une réception liée à une commande annulée est refusée : ajuster d’abord le reliquat de la commande, ne pas effacer son historique physique.

Le reliquat d’une commande confirmée est reçu à sa date prévue. Les réceptions déjà renseignées sont créditées à leur date propre, même si elles diffèrent de la commande. Une commande en retard est exclue par défaut des futures réceptions ; l’alternative `today` reporte son reliquat au premier jour ouvert à partir de l’ancrage et conserve l’alerte de retard.

`Stock ferme fin J = stock ferme début J + réceptions fermes J + ajustements J - besoin J`.

`Stock simulé` suit la même logique avec les commandes brouillon et les propositions générées. Accepter une proposition crée un brouillon ; le passage à confirmé est un acte explicite dans le carnet, qui doit correspondre à un engagement réel. Une donnée source ERP n’est jamais mise à jour par une modification du scénario.

Avec `before_demand`, les réceptions du jour sont disponibles avant la consommation. Avec `after_demand`, un manque avant réception est signalé même si le stock de fin de journée est positif. Il ne s’agit pas d’un ordonnancement horaire.

DELFOR et DELJIT sont des attributs de provenance, pas une clé de dédoublonnage. La préparation UC doit fusionner leurs représentations d’un même engagement au niveau ligne/livraison, en donnant la priorité au message métier applicable. Le moteur refuse les doublons de clé, mais ne peut reconnaître deux identifiants ERP différents désignant le même événement.

## Couverture et alertes

La couverture mesure combien de jours de besoins futurs le stock de fin de journée peut satisfaire, hors réceptions futures. Elle inclut une fraction du premier jour non entièrement couvert. Un stock négatif donne zéro. La variante jours ouverts ignore les dates fermées dans le compteur, la variante calendaire les inclut. Les jours sans demande ne provoquent aucune division par zéro. Si la demande connue ne permet pas de trouver l’épuisement, la couverture est une borne inférieure, affichée avec ≥ ; ce n’est pas une couverture infinie ni une valeur exacte.

Minimum, cible et maximum utilisent les besoins des N jours suivants, augmentés d’un stock de sécurité fixe. Le minimum déclenche l’étude d’un réapprovisionnement vers la cible ; le maximum définit le surstock. La fenêtre commence après le jour courant. Le stock de sécurité s’ajoute à la couverture : mettre zéro si la couverture intègre déjà la marge voulue.

Priorité des statuts : rupture, sous-couverture, surstock, sous contrôle. Le cockpit prend le statut le plus critique sur tout l’horizon. Les vues agrégées affichent le statut de fin de période ; consulter la série journalière pour les ruptures intra-période. Les quantités de différents articles et unités ne sont pas additionnées dans un KPI global de stock.

## Propositions

1. Examiner chaque article et chaque jour dans un ordre stable.
2. Déclencher si le stock simulé est sous le seuil minimum.
3. Calculer la date de livraison réalisable en tenant compte du jour ouvert et du délai depuis la première date de lancement possible.
4. Prendre en compte les flux et propositions déjà en route jusqu’à cette date ; reconstituer la cible future à cette date.
5. Commander le manque positif vers la cible. Quantité fournisseur = multiple × plafond(max(part du manque, MOQ) / multiple).
6. En priorité, choisir le fournisseur au rang le plus faible (départage stable par code). En quotas, répartir le manque selon les quotas dont la somme vaut exactement 1. MOQ et multiples s’appliquent ensuite séparément, donc le résultat final peut s’écarter du quota théorique et dépasser le manque.
7. Calculer à rebours la date de lancement et conserver une alerte si la livraison réalisable arrive après le besoin. Les propositions ne réparent pas le stock ferme.

Les quotas s’appliquent à chaque événement de besoin, pas à un objectif annuel d’achats. Les capacités fournisseurs, coûts de changement de lot, jours spécifiques de livraison par fournisseur, transport, péremption, réceptions qualité, alternatives BOM et optimisation économique multi-contraintes ne sont pas calculés. Ce sont des extensions identifiées, pas des contraintes implicitement satisfaites.

Une proposition ignorée est mémorisée par son identifiant déterministe et ne revient pas à l’identique. Une modification du besoin ou un besoin à une autre date peut créer une nouvelle proposition : ignorer une ligne n’est pas une interdiction durable d’approvisionner l’article. Les arbitrages sont propres au scénario.

## Variantes à valider

| Sujet | Configuration initiale | Alternative disponible ou évolution |
|---|---|---|
| Couverture | Besoins futurs, jours ouverts | Calendaires ; stock de sécurité fixe configurable |
| Réalisé | Remplace le prévu quand renseigné | Plan seul ou réalisé seul |
| Retards | Exclus de la projection des réceptions | Reporter au premier jour ouvert avec alerte |
| MOQ | Minimum avec multiple indépendant | Lot pour lot via MOQ 0 et quantum d’unité adapté |
| Double source | Priorité | Quotas exacts avant arrondis |
| Réception du jour | Avant besoin | Après besoin, alerte intra-journalière |
| Référentiel ERP | Snapshot cohérent et figé | Scénario manuel indépendant |
| PLA | Information conservée sans effet calculatoire | Définir sa signification avant activation d’une règle |

## Explicabilité et historique

Chaque sauvegarde conserve le jeu complet d’entrées avec version, auteur, date UTC et motif. Le résultat comporte la version du scénario et celle du moteur. Les entrées sont décimales (six décimales maximum, dix-huit chiffres) et les calculs sans aléatoire. Une mise à jour du moteur peut modifier les résultats d’une ancienne version : conserver aussi le commit applicatif lors d’un audit, ou les exports figés. Les résultats ne constituent pas à eux seuls un engagement d’achat.
