# Build 484 — éditeur des commandes tactiles et masquage avec une manette (Dolphin, ARMSX2, RPCS3), 18 octobre 2026

Demande du mainteneur : un éditeur visuel des commandes tactiles des émulateurs intégrés Dolphin iOS (GameCube et Wii, dispositions distinctes), ARMSX2 (PS2) et RPCS3 (PS3) — déplacer, redimensionner, régler l'opacité, masquer/afficher chaque élément, sticks indépendants, aperçu à taille réelle, enregistrer, annuler, rétablir — accessible depuis les réglages de chaque émulateur et depuis le menu pause ; dispositions séparées par console, portrait/paysage, générale et par jeu ; option « Masquer les commandes tactiles lorsqu'une manette est connectée », activée par défaut ; une IPA de test avec le numéro de build suivant. Contraintes : aucune release, rien sur `main`. Candidate : **Build 484**, construite par-dessus la Build 483 livrée par une autre session (pipelines LLVM RPCS3) ; le Core RPCS3 483 et tous les autres moteurs sont réutilisés sans reconstruction.

## 1. Avant la Build 484 (sources)

| Moteur | Commandes tactiles | Manette |
|---|---|---|
| Dolphin (`DolphinInternalBridgePlugin.mm`, `TouchController/`) | Pads DolphiniOS (`TCGameCubePad`, `TCWiiPad`, `TCClassicWiiPad`), nibs compilés du donneur Build 350 copiés dans `TouchResources` ; positions fixes. | Superposition masquée dès que `GCController.controllers.count > 0` (tout contrôleur, profil micro compris), sans option et sans relâcher les touches tenues. |
| ARMSX2 (`Armsx2InternalBridgePlugin.mm`) | Cadres codés en dur dans le contrôleur de session (paysage et portrait). | Aucune règle : seul l'interrupteur « Commandes tactiles » du menu. |
| RPCS3 (`RPCS3GameInputController.mm`) | Cadres codés en dur ; manette et tactile jamais actifs ensemble. | Superposition masquée dès qu'une manette (étendue ou micro) est liée, sans option. |

## 2. Ce que la Build 484 change

### 2.1 Pod partagé `packages/neo_touch_layout`

- **Modèle et stockage** : une disposition par clé (`gc`, `wii` = Wiimote + Nunchuk, `wii-classic`, `ps2`, `ps3`), par orientation (`landscape`, `portrait`) et par portée (générale ou jeu). Fichiers `Library/Application Support/NeoStation/TouchControls/<clé>.json` (`format` 1, `general`, `games`), écriture atomique, clés inconnues conservées, fichier illisible mis de côté (`.unreadable-<date>`) au lieu d'être écrasé. Par élément : position relative à la zone sûre (x, y), échelle 0,5–2,5 de la taille d'origine, opacité 0,2–1 de l'opacité d'origine, masqué. Seuls les éléments modifiés sont écrits : un utilisateur qui ne personnalise rien garde exactement les commandes actuelles.
- **Application** (`NeoTouchLayoutApplier`) : chaque commande garde le centre et la taille que son moteur lui donne ; la disposition ajoute **une seule transformation** (échelle autour du centre puis translation). UIKit dessine et teste les touches à travers cette transformation : le dessin et la zone tactile restent le même rectangle après tout déplacement ou redimensionnement. L'opacité d'origine de chaque vue est lue une fois, avant toute opacité de disposition.
- **Éditeur** (`NeoTouchLayoutEditor`) : vue posée au-dessus des vraies commandes, à leur taille réelle. Glisser pour déplacer, pincer ou tirer un coin pour redimensionner, curseurs Taille/Opacité, interrupteur Visible, liste des éléments, Annuler (64 pas), Réinitialiser cet élément, Rétablir la disposition par défaut, Aperçu (exactement ce que le jeu affichera), barre déplaçable, portée « Tous les jeux » / « Ce jeu » avec « Utiliser la disposition générale ». Rien n'est enregistré avant « Enregistrer » ; « Annuler » laisse les fichiers intacts. Pendant l'édition, l'éditeur reçoit **tous** les gestes de l'écran : aucun n'atteint une commande ni le jeu. Une rotation pendant l'édition relâche le geste et passe à la disposition de la nouvelle orientation.
- **Politique manette** (`NeoTouchControllerMonitor`, `NeoTouchControlsShouldHide`) : manette compatible = `GCController` avec profil `extendedGamepad`, non instantané ; claviers et souris (`GCKeyboard`, `GCMouse`) et autres accessoires Bluetooth ne sont pas des `GCController`. Le moniteur suit connexion, déconnexion (le contrôleur sortant est ignoré même s'il est encore listé) et retour au premier plan. Règle commune aux trois moteurs : masqué si l'interrupteur du moteur est coupé, si un menu couvre la session, ou si une manette compatible est connectée **et** que la préférence de la console est active ; jamais masqué pendant l'édition. Préférence `NeoStation.TouchControls.<gc|wii|ps2|ps3>.HideWithControllerConnected`, **activée par défaut**.
- **Éditeur hors jeu** (`NeoTouchLayoutEditorController`, `NeoTouchLayoutRegistry`) : chaque moteur enregistre un aperçu de ses commandes, jamais interactif et sans session ; l'éditeur ouvert depuis les réglages n'offre que les orientations des sessions du moteur (paysage pour Dolphin et RPCS3, les deux pour ARMSX2).
- **Textes** : 48 clés dans les douze langues (`tools/touch_layout/strings.json`, générés vers `NeoTouchLayoutStrings.m` et `lib/l10n/touch_layout_locale.dart` ; `--check` en CI).
- **Canal Flutter** `neostation/touch_layout` : `settings`, `setHideWithController`, `openEditor`.

### 2.2 Dolphin (GameCube, Wii)

- Chaque bouton, stick et croix des trois pads d'origine, plus la commande Secouer de la Wiimote, est un élément (`button.<n>`, `stick.<n>`, `dpad.<n>`, `shake`). `DOLTouchLayout` applique la disposition après le placement des nibs à chaque passe de mise en page ; `DolphinTouchOverlay.hitTest` suit les transformations (boutons Classic imbriqués compris). `TCJoystick` mesure désormais son centre et sa course dans ses propres coordonnées (identique sans transformation) ; `resetToCenter` et `TCDirectionalPad.releaseAllDirections` relâchent un stick ou une croix tenus.
- Masquer (manette, menu), tourner, éditer ou fermer relâche d'abord chaque bouton, stick, croix et la secousse (`cancelTouchInteractions`).
- Menu en jeu : page « Commandes tactiles » après « Commandes » (Modifier ; Masquer avec une manette) ; l'éditeur remplace le menu, le jeu reste en pause (`set_paused`) pendant l'édition. Clé par jeu : identifiant du disque, sinon nom du fichier ; menu Wii sans clé.
- Le cœur Dolphin conservé (identité 350) attribue le joueur 1 à la manette connectée : avec l'option désactivée, les commandes tactiles restent visibles et utilisables, et la page l'explique (choisir l'écran tactile dans Commandes pour jouer le joueur 1 au tactile).

### 2.3 ARMSX2 (PS2)

- `Armsx2TouchControlsView` reprend les mêmes commandes aux mêmes cadres (paysage et portrait) : croix (quatre boutons en un élément), △ ✕ □ ○, deux sticks, L1/L2/R1/R2, START, SELECT. Clé par jeu : nom du fichier (aucune pour le BIOS).
- Visibilité : interrupteur existant « Commandes tactiles » + règle commune ; masquer relâche les seize boutons et recentre les sticks. Menu en jeu : page « Commandes tactiles » ; l'éditeur remplace le menu, ARMSX2 en pause pendant l'édition.

### 2.4 RPCS3 (PS3)

- `RPCS3TouchControlsView` reprend les commandes et leurs cadres ; `RPCS3GameInputController` garde l'état du pad et **fusionne** tactile et manette (`RPCS3PadMerge.h` : boutons OU, gâchettes au maximum, chaque stick prend la déviation la plus grande) quand l'option est désactivée.
- Avec l'option activée (défaut), une manette compatible masque et relâche les commandes ; leur retour suit la déconnexion de la dernière manette.
- RPCS3 n'a pas de pause : pendant l'édition, le Core reçoit un pad connecté et neutre (aucune entrée tactile ni manette). Clé par jeu : identifiant du titre PS3.

### 2.5 Flutter

- Réglages › Systèmes › GameCube / Wii / PS2 / PS3 › onglet Émulateurs : `EmbeddedTouchControlsPanel` (interrupteur « Masquer les commandes tactiles lorsqu'une manette est connectée », aide, note Dolphin, « Modifier les commandes tactiles » par disposition, deux pour la Wii, état Personnalisée / Disposition par défaut).

## 3. Vérifications

Toutes exécutées en CI par `.github/workflows/touch-layout-checks.yml` (`test/build484_targeted_test.py`, trois parties, verdicts avec le SHA-256 de chaque entrée testée). Résultats exacts : § 5.

| Partie | Contenu |
|---|---|
| host (Ubuntu) | Textes douze langues et usages (`touch_layout_strings_test.py`), géométrie portable C/C++ et fusion du pad PS3 (`touch_layout_host_test.py`), contrats moteurs existants qui lisent un fichier modifié (24 scripts), analyse Flutter des fichiers modifiés, 16 suites de tests Flutter (panneau, Dolphin, ARMSX2, RPCS3, onglets, réglages), et comparaison avec la base des 13 vérifications et de la suite `dolphin_import_ui_test.dart` (cas par cas) qui échouaient déjà avant la 484 (une vérification qui passait avant et échoue après bloque). |
| native (macOS, Xcode 26.3) | Compilation et édition de liens iPhone de chaque source modifiée, en-tête Swift réel des commandes Dolphin (`touch_layout_ios_build.py`) ; menus des trois moteurs avec le catalogue de cheats (`unified_native_ios_test.py`) ; suites UIKit existantes qui compilent les menus et commandes modifiés (menu Graphismes ARMSX2, Secouer Wii, cadence et effets Dolphin, écran externe Dolphin, magasin de shaders, éditeur de cheats) et contrôles macOS de Dolphin/RPCS3. |
| uikit (Simulateur iOS) | `test/touch_layout_ui_test.py` : framework de test nommé `dolphin_internal_bridge` avec les vrais fichiers Swift de DolphiniOS et les **nibs/images compilés du donneur Build 350** (asset `NeoStation.ipa` de la release 0.0.1, SHA-256 `e1017b96…`), les commandes ARMSX2 et le `RPCS3GameInputController` de production ; rotation réelle de l'interface ; pour chacune des cinq dispositions : glisser et coin de redimensionnement par la gestion des touches de l'éditeur, taille, opacité, masquage, annuler, enregistrer, rétablir, annuler sans enregistrer ; cadre dessiné = cadre de la disposition et zone tactile = dessin après transformation ; touche maintenue relâchée à la rotation ; portrait et paysage séparés ; appuis simultanés, diagonale de la croix, sticks à course proportionnelle au dessin, aucune touche bloquée ; disposition générale et par jeu, retour à la générale ; éditeur des réglages (aucune entrée envoyée, orientations) ; PS3 : manette avant la session, connexion pendant le jeu avec touche tenue, déconnexion, option désactivée (fusion), éditeur avec manette (pad neutre) ; persistance relue par un **autre processus**. |

Les gestes sont synthétisés sans API privée : la commande sous un point est trouvée par le test de touches d'UIKit (à travers les transformations) et reçoit ses événements de contrôle ; sticks et croix Dolphin reçoivent des reconnaisseurs de gestes de substitution ; l'éditeur reçoit des `UITouch` de substitution.

## 4. Limites

- Aucun essai sur iPhone ni avec une vraie manette dans ce cycle : compilation, tests hôtes et Simulateur seulement. Le relâchement et le masquage sont vérifiés au niveau des commandes et du pad PS3 ; la réception par les cœurs Dolphin et ARMSX2 n'est pas exécutée (aucun cœur en CI).
- Les sessions Dolphin et RPCS3 restent en paysage (contrôleurs de session existants) : leur disposition portrait n'est pas utilisée en jeu et l'éditeur des réglages ne la propose pas. ARMSX2 suit l'orientation du téléphone.
- La croix ARMSX2/RPCS3 reste faite de quatre boutons : une diagonale se fait avec deux doigts, comme avant.
- Dolphin : avec l'option désactivée et une manette connectée, le joueur 1 suit la manette (cœur verrouillé) ; la page l'explique.

## 5. Résultats

Source testée : **`1ff09e968276143f155242db4c4a3963d3c666c0`** (produit identique à `79968b07` ; seuls des harnais de test changent ensuite). Toolchain native : Xcode 26.3 (17C529), SDK iPhone 26.2 ; Flutter 3.47.2 sur Ubuntu 24.04.

| Partie | Run / job | Source | Résultat |
|---|---|---|---|
| host | `39175673497` / `117820408422` | `1ff09e96` | réussi : 40 vérifications (24 scripts Python, analyse Flutter, 16 suites Flutter), 113 entrées hachées ; 13 scripts et 1 cas Flutter qui échouaient déjà identiques sur la base `1b4f65e2` |
| native | `39175671512` / `117817705860` | `1ff09e96` | réussi : 12 vérifications, 71 entrées, **toutes réussies sans comparaison avec la base** (11 objets du pod compilés et liés pour iPhone, menus des trois moteurs avec le catalogue, menu Graphismes ARMSX2 sur UIKit, Secouer Wii, cadence Dolphin, écran externe Dolphin, magasin de shaders, éditeur de cheats) |
| uikit | `39174427738` / `117814065289` | `79968b07` | réussi : **35 tests** XCTest en 3 processus sur iPhone 16 Pro (iOS 26.2), 60 entrées ; **réutilisé** sans être relancé : aucune de ses 60 entrées ne change entre `79968b07` et `1ff09e96` (vérifié par `git diff` dans la clôture de livraison) |

Correctifs apportés pendant les essais (chacun suivi d'un run ciblé) :

- **Aperçu GameCube des réglages** (`testSettingsEditorGameCube`, run `39173370993`, échec) : le C-stick était dessiné à y = −304, car la géométrie d'origine relevée avant que la mise en page automatique du nib Dolphin se stabilise (centre 960, puis 318) était bornée à l'écran. Correctif `79968b07` : un contrôle ni déplacé ni redimensionné garde exactement la place que lui donne le moteur (aucune borne) ; Dolphin vérifie la place au tour suivant de la boucle d'exécution et refait la mise en page (au plus trois fois de suite) quand un contrôle a bougé depuis sa mesure, puis prévient l'éditeur ouvert (`NeoTouchLayoutHostDidRelayoutNotification`). Le test vérifie aussi que chaque cadre de sélection de l'éditeur coïncide avec son contrôle.
- **Cinq harnais UIKit/SDK obsolètes** (échec identique sur la base `1b4f65e2`, run `39174427738`) : `dolphin_recording_sdk_test.py`, `dolphin_touch_shake_ui_test.py`, `dolphin_pacing362_ui_test.py`, `dolphin_external_display_ui_test.py`, `cheat_editor361_ui_test.py`. Cause : depuis la Build 474, `DolphinSessionMenu.mm` importe `<neo_cheat_catalog/...>` et utilise `NeoUnifiedCheatList`/`NeoUnifiedCheatBrowser` ; ces harnais ne fournissaient ni les en-têtes ni les classes du pod (en-tête introuvable ou symboles non définis avant tout test), et `cheat_editor361` refusait en plus le bundle `DolphinAccount267.xcresult` laissé par le harnais précédent. Correctif `1ff09e96` : le harnais partagé `dolphin_account_267_test.py` prépare les en-têtes publics de tous les pods dont dépend le pont (`stage_dependency_headers`), compile les sources du catalogue sans Flutter (zlib, UniformTypeIdentifiers) et remplace un bundle de résultats existant ; le harnais Secouer et le contrôle C++20 strict préparent les mêmes en-têtes. Aucune assertion retirée ni affaiblie ; les cinq passent dans le run natif ci-dessus.
- `test/external_display_ui_test.py` (harnais générique de l'écran externe, sans menu Dolphin) vide `CATALOGUE_SOURCES` pour compiler exactement les mêmes sources qu'avant. Il n'est exécuté par aucune porte de cette livraison : `external-display-check` (run `39175666250`) s'arrête avant lui sur un échec de câblage déjà présent sur la base (`external_display_host_plist_test.py`, deux assertions sur la structure du workflow de livraison). La clôture le déclare comme chemin de test non exécuté.

Échecs conservés et non attribués à la 484 : les 13 vérifications de la liste `PRE_EXISTING` et le cas Flutter `import shares the pill without covering any media tab at width 430.0` échouent de la même façon sur la base (comparaison exécutée en CI à chaque run hôte).

IPA : à compléter après la livraison (identité exacte relevée sur l'IPA livrée).

## 6. Protocole d'essai sur l'iPhone

1. Sans manette : lancer un jeu GameCube → menu › Commandes tactiles › Modifier : déplacer A, l'agrandir, baisser l'opacité de B, masquer START ; Enregistrer ; vérifier que A répond à son nouvel emplacement et sur toute sa nouvelle taille, que START n'apparaît plus et ne répond plus à son ancien emplacement.
2. Même chose pour un jeu Wii (Wiimote + Nunchuk, puis Classic), un jeu PS2 (aussi en portrait) et un jeu PS3. Rouvrir l'éditeur avec « Ce jeu », déplacer un élément, Enregistrer ; un autre jeu garde la disposition générale ; « Utiliser la disposition générale » rétablit.
3. Fermer le jeu, quitter NeoStation, relancer : dispositions conservées. Réglages › Systèmes › GameCube › Émulateurs › Modifier les commandes tactiles : l'aperçu montre la disposition enregistrée.
4. Manette : la connecter avant le lancement → aucune commande tactile, le bouton menu reste là ; la déconnecter → retour des commandes ; la connecter en tenant un bouton tactile → commandes masquées, aucune touche bloquée. Désactiver l'option dans le menu en jeu → commandes visibles et utilisables avec la manette.
5. Appuis simultanés (deux boutons + stick), diagonales de la croix, rotation en tenant un bouton (PS2) : rien ne reste appuyé.
