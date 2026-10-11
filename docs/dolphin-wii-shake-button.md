# Build 438 — « Secouer » de la Wiimote dans Dolphin intégré

Demande du mainteneur du 11 octobre 2026 (paquet A de
`docs/build438-plan.md`) : un bouton tactile « Secouer » dans les commandes
tactiles Wii, assignable à un bouton de manette, réellement transmis au
moteur Dolphin intégré, sans secouer le téléphone et sans activation
permanente. Ce document sépare ce qui est vérifié dans les sources, ce qui est
testé automatiquement et ce qui reste à valider sur l'iPhone.

## 1. Chemin d'entrée réutilisé (aucun changement du cœur)

- La secousse de la Wiimote correspond, dans le cœur épinglé (DolphiniOS
  `7cac5416`), aux entrées tactiles `Button 132`, `133` et `134` du port 4
  (`iOS/4/Touchscreen`). Le profil `Touchscreen` de Dolphin les lie déjà à
  `Shake/X`, `Shake/Y` et `Shake/Z`, et la secousse du téléphone
  (`DolphinPhoneShake.swift`) écrit exactement ces trois entrées.
- Dolphin secoue tant que ces entrées sont pressées et revient au repos dès
  qu'elles sont relâchées : un appui maintenu est donc la sémantique native de
  Dolphin (qui lie lui-même les trois axes à un seul bouton par défaut).
- Seuls des identifiants déjà lus par le cœur sont utilisés. Le Nunchuk
  (`220–222`) n'est pas concerné. Aucun fichier de
  `packages/dolphin_internal_bridge/core/`,
  `build-utils/patch_dolphin_internal_core_v2.py`, DolphinCore, nib de
  `TouchResources`, `DolphinSessionMenu.h`, ni des fichiers de la secousse
  téléphone (`DolphinPhoneShake.swift`, `DolphinPhoneShakeRouting.*`,
  `DolphinPhoneShakeBinding.h`, `DolphinPhoneShakeLabels.h`,
  `native/dolphin_motion/strings.json`) n'est modifié.

## 2. Bouton tactile « Secouer »

- Ajouté par code (`DolphinShakeButton.swift`) dans
  `DolphinTouchOverlay.swift`, uniquement pour une session Wii : la
  surcouche GameCube ne le crée jamais et n'écrit jamais sur le port 4.
  Masqué avec la manette classique, visible avec la disposition Wiimote
  (avec ou sans Nunchuk). Pas d'option afficher/masquer.
- Placement : rond de 56 pt, au-dessus de la colonne droite du pad Wii
  (Z, B, A), centré sur cette colonne ; si la place manque (écrans courts en
  paysage), à gauche du bouton du haut de la colonne. Il ne recouvre aucune
  commande du pad, reste dans la zone sûre et sous une bande de 64 pt en haut
  de l'écran (gestes système, boutons du menu). La mise en page vit dans
  `DolphinShakeLayout` (`DolphinShakeInput.swift`), testée seule.
- Le pad est inséré sous le bouton (`insertSubview(at: 0)`) : il reste le
  premier sous-vue et le bouton reste touchable par-dessus. Le pointeur IR
  n'est pas déplacé par un appui sur le bouton.
- Appui : les trois entrées sont pressées immédiatement (vibration légère).
  Maintien : la secousse dure tant que le doigt est posé. Relâchement normal
  (`touchUpInside`, `touchUpOutside`, sortie du doigt) : la secousse dure au
  moins 120 ms (la durée de l'impulsion téléphone), pour qu'un appui bref ou
  une activation VoiceOver donne une secousse détectable. Ce minimum est
  libéré sur une file dédiée, sans dépendre du fil principal.
- Relâchement immédiat, sans minimum, sur : annulation du toucher, pause
  (menu en jeu), passage en arrière-plan, fermeture du jeu, retrait de la
  vue, surcouche masquée ou désactivée, branchement ou retrait d'une
  manette, passage à la manette classique. Toute libération en attente est
  annulée par un numéro de génération : un ancien minuteur ne peut pas
  relâcher un nouvel appui.
- Libellé et aide d'accessibilité traduits (`shakeTouchButton`,
  `shakeTouchHint`), transmis par les libellés de session au chargement de
  la vue de jeu.

## 3. Téléphone et bouton tactile ensemble

Les deux sources écrivent les mêmes entrées. `DolphinShakeInput` est leur
unique propriétaire : chaque appui réécrit les trois entrées (ce qui survit à
`neostation_dolphin_release_touches`), et le relâchement n'est écrit que
lorsque plus aucune source ne tient la secousse. La fin d'une impulsion
téléphone ne coupe donc pas un doigt posé, et inversement. Ordre des verrous :
téléphone puis arbitre, jamais l'inverse ; l'arbitre ne rappelle jamais le
code téléphone.

## 4. Manette : ligne « Secouer » du menu Commandes

- Dans le menu en jeu, Commandes, une ligne « Secouer » (dans sa propre
  section, avec une aide en pied) apparaît pour la Wiimote d'une partie Wii
  uniquement (jamais pour une partie GameCube, ni sur la page manette
  GameCube d'une partie Wii). La section 0 garde ses 5 lignes Wii
  (3 GameCube) ; le remappage par axe passe en section 2, inchangé.
- Le détail affiche l'entrée de manette commune aux trois axes, « Non
  attribuée » si seuls le tactile et le téléphone sont liés (profil tactile
  par défaut), ou « Différent selon l'axe ».
- Choisir la ligne ouvre la même liste périphérique → entrée que le
  remappage existant. Le menu envoie au pont
  `{kind: "shakeBinding", wii: YES, slot, expression}` ; ce type n'atteint
  jamais le cœur. Le pont (`DolphinShakeAssignment.mm`), déjà sur la file
  d'exécution Dolphin (aucun `dispatch_sync`), lit une fois le profil du
  joueur, puis envoie trois requêtes de liaison existantes
  (`{kind: "binding", id: "Shake/X|Y|Z"}`), avec retour arrière des axes déjà
  écrits si l'une échoue.
- Joueur 1 : l'entrée choisie est combinée avec la branche
  `iOS/4/Touchscreen:Button 13x` (même forme que le routage téléphone), de
  sorte que le bouton tactile et la secousse du téléphone continuent de
  fonctionner. « Supprimer l'affectation » laisse uniquement cette branche.
  Joueurs 2 à 4 : exactement l'entrée choisie.
- Les profils ne sont jamais réécrits automatiquement : seule une action
  explicite de l'utilisateur écrit ces trois liaisons, par le même mécanisme
  de sauvegarde du donneur que le remappage existant. Un profil tactile dont
  l'utilisateur aurait retiré `Button 132–134` est respecté (le bouton
  tactile n'a alors plus d'effet).

## 5. Traductions

Les cinq textes nouveaux sont dans `lib/l10n/dolphin_shake_locale.dart`
(12 langues : en, es, ru, zh, zh_Hant, pt, fr, de, it, id, ja, ko), fusionnés
dans `DolphinImportLocale.labelsFor` et transmis au natif par `menuLabels`.
Rien n'est ajouté au catalogue natif verrouillé de la secousse téléphone.
Clés réutilisées : `unassigned`, `chooseInput`, `clearBinding`, `bindings`.

## 6. Vérifications

Exécuté sous Windows (sans compilateur C++, Swift ni Xcode) :

- `flutter test test/dolphin_shake_locale_test.dart` : 12 langues, mêmes
  clés, aucun texte vide ni copie de l'anglais, chinois traditionnel par
  `zh-Hant`, `zh_TW`, `zh_HK`, `zh_MO`, clés lues par le natif présentes ;
- `python test/localization_12_locale_coverage_test.py`,
  `test/dolphin_shake_wiring_test.py` (en-tête C++ privé, arbitre sans
  UIKit, interception sur la file d'exécution sans `dispatch_sync`) ;
- un miroir Python des règles C++ a reproduit toutes les assertions de
  `test/dolphin_shake_assignment_test.cpp` (aide au développement, ne
  remplace pas la compilation).

Sur macOS CI (`dolphin-motion-check.yml`, `workflow_dispatch --ref Claude`) :

- `test/dolphin_touch_shake_test.py` : arbitre, maintien, minimum de 120 ms,
  annulation, minuteur périmé, téléphone + tactile, concurrence, `deinit`,
  placement ;
- `test/dolphin_shake_assignment_test.py` : règles C++ (aussi sous Linux) et
  transaction Objective-C++ réelle contre une ABI de menu simulée : trois
  requêtes, rien d'autre modifié, idempotence, joueur 3, retour arrière à la
  2e et à la 3e écriture, refus GameCube, joueur ou entrée invalides,
  instantanés invalides ;
- `test/dolphin_touch_shake_ui_test.py` : simulateur iOS, vraie surcouche et
  vrai menu (pads de test construits par code, nibs du donneur absents de
  git) : bouton unique traduit au-dessus du pad, aucune commande recouverte,
  appui/maintien/relâchement, minimum hors fil principal, annulation, chaque
  sortie de cycle de vie, GameCube sans bouton ni écriture, ligne Commandes
  dans les 12 langues, requêtes envoyées ;
- vérification de type Swift iOS de tout `TouchController` et syntaxe de
  `DolphinShakeAssignment.mm` et `DolphinSessionMenu.mm`.

À valider sur l'iPhone (aucun de ces tests ne le démontre) : prise en compte
par les jeux (Super Mario Galaxy, New Super Mario Bros. Wii, Donkey Kong
Country Returns, Mario Kart Wii) d'une secousse maintenue et d'un appui bref ;
position et confort du bouton selon le modèle ; absence de secousse continue
après Centre de contrôle, appel, arrière-plan, menu et fermeture ; téléphone
et bouton ensemble ; manette MFi : assignation, maintien, branchement à chaud
et conservation après redémarrage de l'application (le résultat d'écriture
disque du donneur n'est pas observable) ; jeux et commandes GameCube
inchangés ; sauvegardes, profils et réglages existants intacts.
