# Règles métier et contrat Excel V2

## Principes et paramètres

| Domaine | Règle par défaut | Alternatives |
|---|---|---|
| Stock initial | Stock disponible = stock physique − bloqué, connu en fin de journée du snapshot | Correction datée après le snapshot ; pas de double intégration des mouvements anciens |
| Demande | Réel déclaré prioritaire, y compris zéro ; PDP sinon | Plan seul, réel seul ; réel manquant passé remplacé par plan ou zéro |
| Lissage | Somme hebdomadaire conservée ; répartition sur les jours ouverts | Sans arrondi ; arrondi journalier historique qui peut modifier le total |
| BOM | Mono-niveau, quantité unitaire × production × (1 + rebut), validité datée | Décalage calendaire de consommation |
| Flux fermes | FIRM ; commandes applicatives réelles fermes | Types de flux configurables, priorité de routage ferme puis prévisionnel puis simulé |
| Flux prévisionnels | FORECAST ajouté aux flux fermes | Sélection ERP/app/fusion |
| Flux simulés | PLANNED, cellules et décisions locales | Propositions calculées explicitement par le CBN |
| Retard | Replanification au prochain jour ouvert | Ignorer ; garder une position historique compatible avec le snapshot |
| Rupture | Besoin non servi reporté (`backlog`) | Besoin perdu (`lost`) |
| Couverture | Nombre entier de jours futurs couverts, égalité incluse | Jours ouvrés ; égalité exclue ; indicateur de borne si PDP/fenêtre insuffisant |
| Cible | Maximum du besoin des N jours futurs et du stock de sécurité | Couverture seule, sécurité seule, somme couverture + sécurité pour migration V1 |
| Délai | Respecté, en jours ouvrés | Délai calendaire ; exception d’urgence explicite si respect désactivé |
| Lots | Besoin net, MOQ puis multiple de conditionnement | Cycle de commande ; lot fixe et multiple commun avec conditionnement |
| Fournisseur | Quotas relatifs des sources admissibles | Priorité ; fournisseurs inactifs ou sans intersection de jours exclus |
| Gel | Pas de proposition avant J + 1 + jours gelés | Nombre de jours paramétrable |
| Ordre intra-journalier | Arrivages disponibles avant consommation | Option V1 de signalement de rupture avant les arrivages ; la projection reste en fin de journée |

PLA ne doit être mappé vers `pack_qty` que si sa définition ERP correspond bien à un multiple de conditionnement. La V1 conservait PLA comme texte distinct ; l’adaptateur de migration ne l’interprète pas arbitrairement.

## Projection

Pour chaque couche, à partir du jour suivant le snapshot :

- Solde du jour = solde précédent + approvisionnements + réceptions + ajustements − besoin.
- En `backlog`, le solde peut être négatif ; physique = max(solde, 0) ; manque = max(−solde, 0).
- En `lost`, le solde est ramené à zéro après chaque journée ; le manque est celui de cette journée. Une réception ultérieure ne sert pas rétroactivement un besoin perdu.

Les flux fermes sont compris dans les couches prévisionnelle et simulée. Les flux prévisionnels sont compris dans la couche simulée. Une cellule simulée signée sert à faire une hypothèse ; elle n’est pas une autorisation d’émettre une commande réelle négative.

La demande est prolongée au-delà de l’horizon visible pour calculer couverture et cible sans tronquer systématiquement la dernière semaine. Un PDP manquant ne constitue pas une confirmation de demande nulle : il déclenche un avertissement et limite les propositions à la zone suffisamment connue. Pour la production réelle, compléter le PDP ou changer explicitement le mode de production avant de se fier à la projection.

## Réceptions et rapprochement ERP

Une réception applicative liée diminue le solde à livrer. Son addition au stock ne s’effectue qu’après le snapshot. Une réception de 60 sur une commande de 100 laisse 40 à livrer ; sa suppression restitue ces 60 au reliquat. Les surréceptions et les liens article/fournisseur incompatibles sont refusés.

Le dataset UC doit être cohérent : quantités reçues de commande et stock du snapshot correspondent au même lot. Les réceptions locales déjà publiées doivent être rapprochées par leur identifiant applicatif ou par `erp_receipt_id`. Il n’existe pas de rapprochement heuristique par date/quantité : deux livraisons peuvent légitimement être identiques. Le pipeline doit exposer le mapping, ou une procédure de rapprochement doit être mise en place avant l’usage opérationnel.

## Excel : tout saisir dans SIMULATION

Chaque article dispose de six lignes de saisie journalière :

1. Besoin composants.
2. Commandes fermes : **solde restant à livrer**, non quantité brute commandée.
3. Commandes prévisionnelles : solde restant à livrer.
4. Commandes simulées.
5. Réceptions.
6. Ajustements signés.

Les trois soldes nets, les trois stocks physiques, les trois manques, la cible et la couverture sont calculés par formules. Les stocks initiaux, références et règles sont protégés ; les modifier se fait dans l’application puis par un nouvel export.

**Exemple de réception :** une livraison ferme de 100 est attendue vendredi. Pour simuler 60 reçus jeudi et 40 restant vendredi, saisir 60 dans Réceptions jeudi et remplacer 100 par 40 dans Commandes fermes vendredi. Les deux lignes du même tableau produisent un flux total de 100. L’export ne comprend aucun onglet séparé COMMANDES, CARNET_COMMANDES, AJUSTEMENTS ou SAISIES.

La feuille `HEBDOMADAIRE`, lorsqu’elle est demandée, est une synthèse à formules : somme des flux, stock de fin de semaine, manque de fin de semaine en backlog ou somme des besoins perdus en lost. Les colonnes futures masquées de SIMULATION portent la demande nécessaire aux cibles et couvertures de fin d’horizon ; elles ne sont pas des onglets de saisie supplémentaires. `_FORMAT` est une feuille technique très masquée, sans valeurs métier à saisir. `LIRE_MOI` explique les règles et la provenance.

Les cellules bleues acceptent un nombre ou une expression comme `=2*600-50`. À la réimportation, les références de cellules, fonctions Excel, noms, appels et puissances sont refusés. Ce choix rend le fichier indépendant du cache de résultats des formules : un fichier modifié mais non recalculé n’entraîne pas la perte silencieuse de sa saisie arithmétique.

Le réimport crée une simulation, jamais une réception comptable ou une commande fournisseur. Une grille inchangée ne crée rien. Le même fichier réimporté ne crée pas de doublon. Le fichier d’un autre utilisateur est refusé. Les calculs de l’application sont relancés à partir des saisies autorisées, même si des formules de présentation ont été altérées.

## Règles de gouvernance

- Lecteur : consultation et export de son périmètre autorisé par l’app ; pas d’écriture.
- Éditeur : saisies et scénarios privés ; respect de la révision courante.
- Administrateur : paramètres globaux/référentiels et rafraîchissement ; accès aux scénarios pour assistance.
- Les tables UC sont lues par le service principal de l’app. Cela suppose une application partagée avec les personnes autorisées à voir ce portefeuille. Une isolation par utilisateur dans UC nécessiterait l’autorisation déléguée et un cache tenant compte de cette identité.
- Les ordres acceptés restent PLANNED ; la validation d’achat et la publication fournisseur/ERP sont des processus distincts.
