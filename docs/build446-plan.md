# Build 446 — catalogues de skins de nouveau chargeables

Demande du mainteneur du 12 octobre 2026 : « apporte un correctif et produit
le build 446 », après le constat sur la Build 445 installée (vidéo du
mainteneur) : la page « Catalogues de skins » reste sur « Loading the
catalog… », champ de recherche grisé, puis affiche « The catalog could not be
loaded. Check the connection and try again. », pour toutes les consoles.

Base : Build 445 (`165c0201`), produit identique à la Build 444.

## Cause démontrée

- `LibretroSkinCatalogs.normalizeDownloadURL`
  (`lib/services/libretro_skin_catalogs.dart`, commit `6639e7a3`, livré en 444
  et 445) décodait une seconde fois les segments de chemin que Dart a déjà
  décodés (`uri.pathSegments.map(Uri.decodeComponent)`). Ce second décodage
  lève « Illegal percent encoding in URI » sur tout caractère non ASCII ou
  tout `%` littéral.
- Le catalogue Provenance publié contient 1 358 skins, dont deux liens
  DeltaStyles avec des caractères non ASCII :
  `…/pokÃ©mon pinball GBA.deltaskin` et
  `…/652/DK control + real dpad Â (1981) v.05.zip`.
- `load()` appelait `fromProvenance` hors de tout `try` : la première de ces
  entrées interrompait tout le chargement (Provenance, site Delta Skins et
  overlays), et l'écran passait en échec, recherche désactivée.
- Reproduit sur ce poste avec les données réelles téléchargées le 12 octobre
  2026 (MockClient servant `catalog.json` et les sept pages du site) :
  exception sur l'entrée « pokÃ©mon pinball ». Les tests de la 444 utilisaient
  uniquement des liens ASCII. La Build 443 (ancien écran Provenance seul)
  n'utilisait pas cette fonction.
- Réseau mis hors de cause : les deux adresses Provenance et les sept pages
  Delta Skins répondent 200 depuis ce poste.

## Correctif

- `normalizeDownloadURL` utilise les segments déjà décodés, sans second
  décodage, et ne lève plus jamais (repli : le lien d'origine en minuscules).
  Les clés des liens ASCII sont inchangées : verdicts en cache et favoris
  restent valides.
- `load()` ignore, en le journalisant, une entrée Provenance inutilisable au
  lieu d'abandonner tout le catalogue.
- Le site Delta Skins : une carte inutilisable est ignorée, la page et la
  source restent chargées.
- Aucun libellé ajouté ou modifié, aucun changement natif, d'écran ou de
  dépendance.

## Vérifications locales (Windows, Flutter 3.47.2)

- `test/libretro_skin_catalogs_test.dart` : deux tests ajoutés, avec les deux
  liens réels, un `%` littéral, un `%` invalide, l'équivalence des formes
  encodée et brute, et un chargement complet où ces entrées et une carte
  Delta Skins non ASCII cohabitent avec des entrées normales sur trois
  consoles.
- `libretro_skin_catalogs_test.dart`, `libretro_skin_catalog_test.dart`,
  `libretro_skin_manager_test.dart`, `libretro_skin_service_test.dart` :
  57 tests réussis ; `flutter analyze` sans problème sur les fichiers changés.
- Données réelles via le chargeur corrigé : 1 605 entrées dédoublonnées, aucune
  source indisponible ; GBA 372, PlayStation 71, DS 358, SNES 188, NES 147,
  N64 64, Mega Drive 89 ; la recherche répond.

## Livraison

Les identités de la livraison sont consignées dans ce document après le run.
Aucune validation sur iPhone n'est revendiquée avant l'essai du mainteneur.
