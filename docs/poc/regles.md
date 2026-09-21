# Règles du POC et contrats d’import

## Règles hebdomadaires

- `FORECAST` : livraison ramenée au lundi de sa semaine ISO, à l’import comme à l’édition. Exemple : 30/09/2026 → 28/09/2026 ; 03/01/2027 → 28/12/2026. La quantité et l’identifiant ne changent pas.
- `FIRM` : date exacte conservée, y compris un jour autre que lundi.
- PDP : `week_start` ramené au lundi ISO ; deux lignes devenues identiques programme/lundi sont refusées, sans agrégation implicite.
- CBN : les calendriers fournisseurs du POC autorisent seulement le lundi. Le moteur choisit un lundi admissible ; il ne déplace pas a posteriori une proposition déjà calculée. MOQ, multiple, délai et période gelée restent appliqués.
- En mode « lundi précédent admissible », si avancer enfreint le délai ou la période gelée, le prochain lundi admissible est retenu. Aucune livraison CBN n’est créée dans le passé. La règle du moteur ne propose pas le jour de référence lui-même : le premier lundi possible de la démonstration est le 28/09.
- Un lundi fermé ne devient pas un mardi : le calendrier cherche un autre lundi admissible. S’il n’y en a aucun dans l’horizon, pas de proposition.
- Les prévisionnels historiques restent à leur lundi ; le POC ne les redate pas au jour courant (`late_order_policy=keep`). Un flux antérieur au stock initial n’est pas rajouté à ce stock.

## Rapprochement entre simulation et commande ferme

Chaque cellule simulée conserve sa quantité originale et le total ferme existant à l’article/date lors de sa saisie ou de son calcul. Une **augmentation ultérieure** du ferme à ce même article/date absorbe la quantité simulée positive, dans la limite du disponible. Le reliquat est calculé, pas détruit.

- Le ferme déjà présent à la création de la simulation ne l’absorbe pas une deuxième fois.
- Une confirmation partielle laisse un reliquat simulé ; une diminution/suppression du ferme restaure ce reliquat.
- Le rafraîchissement ne consomme pas à nouveau les quantités.
- Une quantité ferme ne s’applique qu’une fois, même en présence de cellules manuelles et CBN au même jour. Les bases fermes les plus récentes sont allouées en premier ; à égalité, les cellules CBN précèdent les manuelles.
- Une nouvelle saisie manuelle est une nouvelle intention de simulation : sa base ferme est celle du moment de cette saisie.
- Une relance CBN efface ses précédentes propositions et recalcule les besoins sur le ferme courant et les saisies manuelles effectives. Elle crée de nouvelles bases de rapprochement.
- Les ajustements et les quantités simulées négatives ne sont pas absorbés.
- Le rapprochement du POC utilise article/date, sans rapprochement multi-fournisseurs ni lien juridique avec une ligne d’OA. Les ordres réels restent distincts des simulations.

Après modification du PDP, d’une nomenclature ou d’un paramètre, les projections se mettent à jour à l’enregistrement. **Relancer Calcul CBN** pour remplacer les propositions existantes. Cette action est volontairement explicite.

## Chargement et enregistrement

Chaque vue propose **Charger**, **Exemple CSV**, **Ajouter une ligne**, **Enregistrer**, **Annuler** et **Supprimer**. Charger remplace le brouillon de la table ; aucune donnée n’est enregistrée tant qu’Enregistrer n’a pas été validé. L’import ne fusionne pas silencieusement des clés.

- CSV UTF-8 : séparateur point-virgule, virgule ou tabulation. Noms techniques des colonnes ou labels français exacts.
- XLSX : feuille portant le nom technique de la table si présente, sinon première feuille. En-têtes en première ligne, valeurs sans formules ; dates Excel ou ISO `AAAA-MM-JJ`.
- Maximum 2 000 lignes par table, 12 Mo de fichier. Pas de macros ni de liens externes. Quantités non finies, codes manquants et clés dupliquées refusés.
- Enregistrement atomique, validation des références et verrou de révision. En cas d’erreur, les données précédentes restent intégralement disponibles.
- Pour remplacer intégralement les articles par un autre périmètre, retirer d’abord les anciennes lignes BOM/commandes qui les référencent. Pour la démonstration, les exemples fournis forment un ensemble cohérent.

| Table | Colonnes | Clé |
|---|---|---|
| articles | article_id, designation, unit, stock_initial, coverage_target_days, safety_stock_qty, supplier_id, moq, pack_qty, lead_time_days | article_id |
| bom | program_id, article_id, qty_per | program_id + article_id |
| pdp | program_id, week_start, qty | program_id + lundi |
| orders | order_id, article_id, supplier_id, expected_date, qty, order_type, note (optionnel) | order_id |

Les programmes et les fournisseurs sont dérivés des quatre tables. Les unités BOM sont celles des articles ; coefficient strictement positif, pas de conversion implicite d’unité. Les besoins sont calculés à un seul niveau de nomenclature. Les quantités prévisionnelles/fermes représentent ici des soldes ouverts.

## Isolation et validation

`run_poc.py` active l’adaptateur POC et une base dédiée. Le moteur et les services transactionnels sont ceux de la V2. `PocWorkspace` persiste les tables ; `AppCell.firm_baseline` permet le rapprochement réversible. Le mode standard conserve son comportement quand `poc=False`.

L’application ne lit ni n’écrit les données métier d’APPRO. Aucun accès Unity Catalog n’est requis pour cette démonstration. Le déploiement de l’application complète reste un autre chantier.

Les tests API couvrent les lundis, les fins d’année ISO, le CBN reproductible, l’impact PDP, les confirmations complètes/partielles, leur annulation, les imports CSV/XLSX, les rejets atomiques et la réinitialisation. Le parcours navigateur vérifie les six écrans, les onglets vides, l’absence d’icônes/marque latérales, les saisies, l’export et le menu mobile. Le recalcul Excel hérité est vérifié séparément avec LibreOffice.
