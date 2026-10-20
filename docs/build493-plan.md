# Build 493 — boîtiers 3D dans les trois vues, notice dans le boîtier, Retour, 20 octobre 2026

Demande du mainteneur (20 octobre 2026) : généraliser les boîtiers 3D de la Build 490 (vue Carrousel) aux vues **Carrousel, Grille et Liste** ; supprimer le halo lumineux autour des boîtiers et le garder **uniquement sur le nom du jeu sélectionné en vue Liste** ; ajouter un bouton **Retour** à la visionneuse ; rendre le dos lisible (zoom, déplacement, recentrage, vue plane haute résolution, lecture multilingue conservée) ; **« Ouvrir la boîte »** sans lancer le jeu, avec le support et la **notice PDF déjà téléchargée** posée dedans, que l'on prend et lit dans le lecteur de notices existant ; conserver l'animation d'ouverture au lancement ; une IPA testable, aucune release. Branche `Claude`.

La Build 492 (retrait de Dusklight et de la playlist Ports) est le chantier d'une autre session, construit sur la 491 livrée ; la 493 se construit par-dessus la 492 livrée et en conserve tout le produit.

Conception, placements, règles et limites : [`game-box-3d.md`](game-box-3d.md) § 3 et § 11.

## 1. Audit préalable (réutilisé, rien n'est recommencé)

- Boîtiers 490 : `lib/widgets/game_box/` (géométrie `Matrix4` par faces, scène, surfaces, carte), `lib/screens/game_box/` (visionneuse, lecture du dos), `lib/services/game_box/` (profils, médias, éditions, texte). Tout est réutilisé : la carte sert aux trois vues, la visionneuse est commune, la géométrie reçoit une pièce de plus (la notice).
- Halo : `RainbowSelectionBorder`, utilisé par le carrousel (`_withRainbowSelection`), la grille (bordure dans la cellule sélectionnée) et la liste (surbrillance de toute la ligne).
- Notices : `GameModel.getManualPath` (résolu par le `FileProvider`, `media/<système>/manuals/<jeu>.pdf`), `GameSettingsManualTab` (lire, retélécharger, supprimer), `ScreenScraperService.downloadGameManual`, `GameManualReaderScreen` (pdfrx, plein écran, pincement, pages, hors ligne, Retour et manette). Ils sont réutilisés tels quels ; le choix du dossier, du système et l'appel de téléchargement de l'onglet passent dans `lib/services/game_manual_service.dart`, que l'onglet et le boîtier appellent tous deux (même comportement pour l'onglet).
- Lancement : `launch_flow.dart`, `game_launch_utils.dart`, `game_launch_service.dart` et les moteurs ne changent pas ; « Jouer » passe toujours par `_selectCurrentGame` et ses vérifications.

## 2. Périmètre

Fichiers produit (liste fermée dans `test/build493_targeted_test.py`, `PRODUCT`) :
- nouveaux : `lib/services/game_manual_service.dart`, `lib/services/game_box/game_box_manual.dart` (première page du PDF), `lib/screens/game_box/game_box_scan_viewer.dart` (vue plane), `lib/widgets/game_box/game_box_library.dart` (commun aux trois vues) ;
- modifiés : géométrie, scène, surfaces, carte et chargeur d'images des boîtiers ; visionneuse et lecture du dos ; `my_games_carousel.dart` (halo retiré du style Boîte, système transmis pour la notice) ; `my_games_grid.dart` (boîtiers 3D, sans halo en style Boîte, visionneuse, « Jouer » avec ouverture) ; `game_list_view.dart`, `my_games_list.dart`, `my_games_list/gamepad_nav.dart` (miniatures 3D, halo sur le titre, visionneuse, « Jouer » avec ouverture) ; `game_details_card_list.dart`, `game_details_box2d_tab.dart` (boîtier 3D du panneau de détails) ; `game_settings_manual_tab.dart` (même service, même comportement) ; textes : `tools/game_box/strings.json` (123 textes × 12 langues), générateur et catalogue généré.

Inchangés : fichiers de bibliothèque verrouillés sur la 419, lancement et moteurs, cœurs, ponts, plugin `neo_box_reader`, catalogues, NeoSwap ; aucun Core reconstruit.

## 3. Vérifications

Dans la session (Linux, Flutter 3.47.2 installé dans le conteneur) :
- `flutter analyze` de toute l'application : aucun constat ;
- suites des boîtiers : géométrie (dont 9 tests de la notice), médias, texte, visionneuse (7 tests de la 490, libellés des faces mis à jour : « Front cover » / « Back cover »), notice dans le boîtier (12), vues Grille et Liste (7), textes (16) ; suites existantes qui lisent un fichier modifié ;
- aperçus rendus et examinés (boîtiers PS2, PS1, NES, DS, SNES ouverts, prise de la notice, retour au boîtier ouvert, vue Liste) : `test/game_box_render_open_preview_test.dart`.

Contrôles ciblés en CI : `.github/workflows/build493-checks.yml` (`test/build493_targeted_test.py --part host`) — couverture des fichiers modifiés depuis la 492, générateur des textes, `flutter analyze`, la suite Dart de livraison lue dans `retroarch-delivery.yml`, les suites des boîtiers et des vues, les contrats Python (textes, douze langues, fichiers 419, sources des médias, routes). Aucune partie native : aucune entrée native ne change (vérifié par le lanceur et par la porte). Le contrôle macOS de la lecture du dos (`game-box-checks.yml`, Vision/Translation) n'est plus relancé par une poussée tant que le plugin et son lanceur ne changent pas.

Résultat : run `build493-checks.yml` `39356719105` sur `ccf64b632ec288efb95dc0de63ee519ef22c7940` (déclenché par la poussée de ses propres fichiers), job `118413081181` (Ubuntu 24.04, Flutter 3.47.2, 02:02:17 → 02:10:31 UTC) **réussi** : couverture, catalogue des textes, `flutter analyze` complet, suite Dart de livraison, suites des boîtiers et des vues, contrats Python ; « host: passed, 53 inputs recorded » ; artefact du verdict `12235312822` (`build493-host-ccf64b63…`, 12 237 octets, zip SHA-256 `619d11f665c852b7eb2a30fd7f346f31b0d6fb431da0b0c7c288e6ce96027028`).

Poussées : le commit produit `f181a123` a été poussé seul avec `[skip ci]`, puis `ccf64b63` (contrôles) : seuls les contrôles 493 ont démarré. `libretro-checks.yml`, qui se déclenche sur `my_games_list.dart`, n'a pas été relancé : ses tests Dart sont dans la suite de livraison exécutée ci-dessus, et ses parties natives (pont libretro, pression des skins) ont des entrées inchangées. Les deux poussées ont été faites après que la livraison 492 de l'autre session a été lancée et figée sur `3349513a` ; rien n'a touché `retroarch-delivery.yml` pendant cette livraison (son groupe de concurrence annule le run en cours).

Livraison et identités : § 4.

## 4. Livraison

À consigner : run des contrôles ciblés, porte `.github/diagnostics/gamebox493_delivery.py` (produit = 492 livrée + fichiers 493, aucune entrée native ni de Core modifiée, verdict réutilisé, jamais relancé), run `retroarch-delivery.yml`, artefact chiffré pour `build-utils/delivery-493-recipient.pem` (clé privée hors Git, dans le conteneur de la session), IPA et SHA-256.

## 5. Protocole sur iPhone

1. Bibliothèque PS1 ou PS2, vue Carrousel en style Boîte : aucun halo autour des boîtiers ; le boîtier centré est plus grand.
2. Vue Grille en style Boîte : boîtiers 3D, aucun halo ; le sélectionné est un peu plus grand ; toucher le boîtier sélectionné ouvre la visionneuse ; « Retour » revient à la grille au même jeu et à la même position.
3. Vue Liste : miniature 3D devant chaque titre, halo seulement autour du nom sélectionné (il suit la sélection, au toucher et à la manette) ; toucher une miniature ouvre la visionneuse ; l'onglet Jaquette du panneau montre le boîtier en volume.
4. Visionneuse : « Retour » en haut à gauche ; « Face arrière », pincer, déplacer, « Recentrer », « Vue à plat » (scan net, résolution affichée), « Lire la jaquette ».
5. Un jeu avec une notice téléchargée (Réglages du jeu › Notice) : « Ouvrir la boîte » → disque ou cartouche et notice dans le boîtier, aucun lancement ; toucher la notice → elle vient vers la caméra, le lecteur s'ouvre ; feuilleter, zoomer ; fermer → même boîtier ouvert ; Retour → boîtier fermé ; Retour → bibliothèque. En mode Avion, la notice se lit toujours.
6. Un jeu sans notice : « Aucune notice… », pas de livret ; « Télécharger la notice » (compte ScreenScraper) → la notice apparaît aussitôt dans la boîte.
7. « Jouer » depuis la visionneuse, depuis la boîte ouverte, depuis la grille et la liste (A) : ouverture puis un seul lancement ; avec « Réduire les animations » et avec l'animation désactivée.
8. Familles : cristal (PS1), DVD (PS2), Blu-ray (PS3), GameCube, Wii, DS/3DS, UMD (PSP), cartons NES/SNES/N64 ; portrait, paysage, iPad ; défilement rapide de la grille et de la liste.
