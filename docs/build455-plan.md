# Build 455 — résolution interne du moteur libretro intégré

Demande du mainteneur du 13 octobre 2026 : « Ajoute un réglage d'augmentation de résolution pour les émulateurs
RetroArch embarqués dans NeoStation, avec une architecture extensible aux futurs cœurs », puis livrer une IPA vérifiée
en précisant les essais réellement effectués.

Base : Build 454, source `6dcdfd1aa903c8efb28d5d4bc4cd04464f395255` (livrée, run `38370668542`). Le paquet de cœurs
`8b9e87ba` (Azahar 2127.0-alpha1 avec Fast Interpreter et les 13 autres cœurs) ne change pas ; aucun helper JIT,
aucun fichier verrouillé sur la Build 419. `pubspec.lock` identique ; `pubspec.yaml` passe à `0.0.7+455`.

Architecture, sources amont et règles : `docs/libretro-resolution.md`.

## Ce qui change pour l'utilisateur

| Surface | Contenu |
| --- | --- |
| Menu en jeu › Réglages d'émulation | Toujours présent (même pour un cœur sans réglage curaté) ; première ligne « Résolution et image ». |
| Page « Résolution et image » | Résolution interne (Native, ×2… seulement les valeurs déclarées par le cœur et applicables), portée « Tous les jeux avec {cœur} » ou « Ce jeu uniquement », application dès la reprise du jeu ou au prochain lancement selon le cœur, avertissement de charge graphique, taille réelle de l'image produite ; agrandissement de l'image (format d'écran, disposition DS/3DS, shaders, shaders d'agrandissement) ; filtrage (image lissée). Cœur 2D : « Non proposée par {cœur} » et explication. |
| Paramètres du système › Émulateurs, onglet Consoles | « Résolution et image » par console : chaque cœur, valeurs, choix pour tous les jeux du cœur (prochain lancement, refusé pendant un jeu), nombre de jeux réglés individuellement. |
| Défaut | Natif pour tous les cœurs. Mupen64Plus-Next (défaut du cœur 640 × 480) et PPSSPP (ancien défaut NeoStation 960 × 544) démarrent désormais en natif ; un choix déjà enregistré est conservé. |
| Remplacé | Les réglages curatés « Résolution interne » de Mupen64Plus-Next, Beetle PSX HW et PPSSPP. |

Cœurs : Azahar ×1–×10, DeSmuME ×1–×10, Beetle PSX HW et Beetle PSX ×1/×2/×4/×8, PPSSPP ×1–×5 (avec OpenGL ES ;
rien dans son contexte logiciel) en cours de jeu ;
Mupen64Plus-Next ×1–×6 (dont ×4,5) au prochain lancement ; Nestopia, Snes9x, Gambatte, mGBA, Genesis Plus GX (+ Wide),
PicoDrive, FinalBurn Neo : pas de résolution interne.

## Préservé

- Proportions : le présentateur ajuste l'image au rapport annoncé par le cœur (inchangé), quelle que soit sa taille.
- Écrans tactiles et doubles écrans : régions et pointeur normalisés (DS 256N × 384N, 3DS 400N × 480N avec la
  disposition verrouillée).
- Shaders : taille console transmise pour une image agrandie uniformément (existant).
- Sauvegardes : aucune ; seules les options (`Config/<bibliothèque>.json`) et le nouveau `Config/Games/` sont écrits.
- Fast Interpreter d'Azahar : option, défaut et choix inchangés ; la résolution d'Azahar est une autre option.

## Vérifications

Résultats consignés ci-dessous au fil des runs ; aucune validation sur iPhone n'a été faite.

### Locales (conteneur Linux, Flutter 3.47.2)

- `flutter analyze --no-fatal-infos` : aucun avertissement ni erreur (52 infos préexistantes ailleurs).
- `flutter test` de la liste du job Dart de `libretro-checks` (45 fichiers, dont les deux nouveaux) : 558 tests
  réussis sur `53cf9fb6`, 561 après le correctif des moteurs de rendu (profils, option inapplicable dans le service
  et la page de la console) ; `flutter test test/storage_*_test.dart` : 244 réussis.
- Contrats Python : `libretro_core_options_test.py` (sans `--cores`), `libretro_frontend_ui_contract_test.py`,
  `localization_12_locale_coverage_test.py`, `delivery_pipeline_test.py`, `external_display_host_plist_test.py` et
  les autres contrats du job Dart : réussis. `verify_delivery_reuse.py --offline` : réussi (`BUILD455_DELTA`,
  36 entrées).
- L'Objective-C n'a pas pu être compilé dans ce conteneur (pas de SDK Apple) : compilation et exécution natives
  en CI macOS seulement.

### CI

**`libretro-checks`, run `38385450260`, source `53cf9fb6`** — réussi (jobs `native` macOS 15 / Xcode 26.3 et `dart`).

- Test hôte macOS (`test/libretro_host_test.py`) : « All libretro host checks passed », dont les 43 vérifications de
  la session 7 :
  - les cas de valeurs partagés lus comme en Dart, valeur par valeur et liste par liste ;
  - le profil reconnaît l'option du cœur de test dès sa déclaration, avant `retro_init` ; quatre facteurs, natif en
    premier ;
  - natif appliqué par défaut (défaut du cœur ×2) sans être une mise à jour : le cœur, qui lit l'option dans
    `retro_init`, dessine 320 × 240 dès sa première image ;
  - ×3 pour tous les jeux du cœur : signalé au cœur, images 960 × 720 dès la reprise, nouvelle taille annoncée par
    `SET_SYSTEM_AV_INFO`, valeur écrite tout de suite dans le fichier du cœur ;
  - ×2 pour ce jeu seul : 640 × 480 aussitôt, valeur dans `Config/Games/NeoTest.json`, autres jeux et clés inconnues
    conservés, valeur du cœur intacte, valeur non proposée refusée ;
  - relancement du même jeu : ×2 conservé (jamais remplacé par le natif) ; valeur du jeu retirée : retour en direct au
    ×3 du cœur ; un autre jeu garde son ×4, un troisième suit le ×3 du cœur ;
  - option reconnue par son seul nom : « au prochain lancement », aucune mise à jour pour le cœur en cours, qui garde
    ×3 ; le relancement démarre en natif ;
  - cœur sans option de résolution, profil dont la condition échoue puis réussit, option masquée, option nommée sans
    natif : rien n'est proposé à tort.
- Modules frontend, préréglages de shaders Metal, compilation et édition de liens de toutes les sources du pont pour
  iPhone (`libretro_ios_syntax_test.py`), test du codec du canal dans le Simulateur iOS (sources de cette build et
  de la 453) : réussis.
- Dart : `flutter analyze`, la liste de tests libretro (dont `libretro_resolution_test.dart` et
  `libretro_resolution_screen_test.dart`), puis les contrats. Ligne du contrat des binaires épinglés
  (`--cores`, paquet `LibretroCores-8b9e87ba…`) : « internal resolution checked for azahar, desmume, mednafen_psx,
  mednafen_psx_hw, mupen64plus_next, ppsspp » — clé, chaque valeur, défaut et nom de bibliothèque présents dans chaque
  binaire.

**`libretro-simulator`, run `38385450271`, source `53cf9fb6`** — échec, cause trouvée et corrigée.

- Les scénarios existants (NeoTest, PPSSPP PRX et ISO, fenêtre mémoire encombrée) se sont déroulés comme avant ;
  les deux scénarios encombrés finissent sur la limitation connue de la sonde.
- `ppsspp-resolution-live` : lancement réussi en rendu `software` (le Simulateur refuse le contexte OpenGL ES :
  « GL texture creation failed »), puis le processus de la sonde s'est arrêté au moment du choix ×2 ; les scénarios
  suivants n'ont pas eu de résultat.
- Cause, lue dans les sources de PPSSPP (`libretro/libretro.cpp`, `LibretroGraphicsContext.h`) : sans contexte
  matériel, PPSSPP dessine dans `LibretroSoftwareContext`, toujours en 480 × 272 ; quand la résolution interne
  change en jeu, `check_variables` met `resetHWContext` pour tout contexte non Vulkan et appelle
  `((LibretroHWRenderContext *)ctx)->ContextReset()` sur ce contexte logiciel, qui n'a pas cette méthode
  (comportement indéfini). Le rapport de plantage n'a pas pu être lu depuis le conteneur (artefact) : la cause est
  établie par les sources et par le moment de l'arrêt, pas par une pile d'appels.
- Correctif : les profils nomment les moteurs de rendu pour lesquels leur source a été lue (`renderers`), vérifiés
  une fois le contenu chargé ; PPSSPP n'a de résolution qu'avec OpenGL ES (en jeu) ou Vulkan (au relancement). Dans
  son contexte logiciel rien n'est proposé, et la page explique qu'il a le réglage mais qu'il ne s'applique pas
  (nouveau texte, douze langues, aussi dans les réglages de la console via `inapplicableKey`). Sur iPhone, PPSSPP
  obtient normalement le contexte OpenGL ES de NeoStation : le changement en jeu y reste proposé (non vérifié sur
  l'appareil).
- Sonde revue : un vrai cœur logiciel, DeSmuME, sur une image DS minimale écrite par la sonde (aucun contenu tiers),
  vérifie le changement effectif en jeu (×2 : 256 × 384 → 512 × 768), l'enregistrement pour le cœur, le relancement à
  ×2 et le choix pour un seul jeu ; PPSSPP vérifie le refus dans son contexte logiciel sans plantage (ou ×2 en jeu
  s'il obtient OpenGL ES). Les fichiers enregistrés (instantané, valeur du cœur, valeur du jeu) sont relus. En cas
  de nouvel arrêt, le pilote imprime le fil planté du rapport de plantage dans le journal du job.

**Source `c60bc4f8`** (correctif des moteurs de rendu) : `libretro-checks` `38390318590` échoue à la compilation du
test hôte (`rendered` déjà déclaré dans la même portée) ; la sonde `38390318971` échoue avant tout lancement : le
binaire DeSmuME du buildbot porte `LC_VERSION_MIN_IPHONEOS` et non `LC_BUILD_VERSION`. Corrigés dans `6865f458`
(variable renommée ; `vtool` d'Apple remplace cette commande par un `LC_BUILD_VERSION` du Simulateur, code et
données de DeSmuME inchangés). Le job Dart, la compilation iPhone et le test du codec de ce run avaient réussi.

**`libretro-checks`, run `38391711796`, source `6865f458`** — réussi.

- Test hôte macOS : « All libretro host checks passed » ; session 7 : 52 vérifications de résolution, les 43
  précédentes et 9 sur les moteurs de rendu : avant le chargement aucune condition de moteur ; un profil s'applique
  avec un moteur qu'il nomme, rien avec un autre (pas même par le nom de l'option) ; l'option est alors signalée
  inapplicable, jamais pour une option qu'aucun profil ne nomme ; règles de PPSSPP envoyées par l'app : OpenGL ES en
  jeu (natif à ×5), Vulkan au relancement, contexte logiciel et option de rendu logiciel : rien.
- Modules frontend, préréglages de shaders Metal, compilation et édition de liens des 68 sources du pont pour
  iPhone, test du codec dans le Simulateur : réussis.
- Job Dart : `flutter analyze`, liste de tests libretro (561), contrats dont les binaires épinglés (`--cores`).

**`libretro-simulator`, run `38391711861`, source `6865f458`** — réussi : « All 13 simulator scenarios behaved as
expected » (iPhone SE 3e génération, iOS 26.2, vrais cœurs, appel de session du menu en jeu).

- `desmume-resolution-live` : « load: resolution desmume_internal_resolution (live, profile) in effect 256x192 »,
  images 256 × 384 ; ×2 pour tous les jeux du cœur accepté ; « run: frame 512x768 (was 256x384) » dès la reprise ;
  `Config/DeSmuME.json` contient `512x384`, aucune valeur de jeu.
- `desmume-resolution-relaunch` : le relancement démarre « in effect 512x384 », images 512 × 768 ; le natif pour ce
  jeu seul est accepté, « run: frame 256x384 (was 512x768) » ; `Config/Games/DeSmuME.json` donne `256x192` à
  `probe/probe.nds`, le cœur garde `512x384`.
- `ppsspp-resolution` : rendu `software` (pas de contexte OpenGL ES dans le Simulateur) ; « load: resolution
  ppsspp_internal_resolution of PPSSPP does not apply (renderer software) » ; le choix ×2 est refusé, images
  480 × 270 avant et après, le jeu continue et se ferme normalement ; instantané `renderer` `software` et
  `inapplicableKey` ; rien d'enregistré pour le cœur.
- Les autres scénarios (NeoTest, PPSSPP PRX et ISO, fenêtres encombrées, cœur Vulkan de test) se sont déroulés
  comme attendu ; les jobs informatifs `before-fix` et `before-reservation` ont réussi.

### Livraison

**`retroarch-delivery`, run `38393178533`** — réussi (périmètre `full` ; jobs `checks`, `native` et
`Release device build • cold`). Source `a12f075906ef452885decbef78fefd6517ce0fe0` : arbre produit identique à
`6865f458` (seul ce plan diffère), celui des contrôles et de la sonde ci-dessus.

- Artefact `NeoStation-Build-455-a12f0759…-cold`, id `11812355580`, 211 121 053 octets, archive SHA-256
  `e35c8e13d125a0d302d840d297abe396eb6a15512d51d2bc1cdfb36d3bbc99ee`, conservé jusqu'au 27 octobre 2026, chiffré pour
  `build-utils/delivery-424-recipient.pem`.
- IPA validée avant scellement : `NeoStation.ipa`, 206 686 562 octets, SHA-256
  `7926a48c863cf38f7015f84f21b68353ccf0f91ce02b7e21f9c4e9c8c5ab2745`, version 0.0.7 (455) ; validation structurelle
  réussie ; « Libretro IPA validation passed » pour les 14 cœurs (dont desmume, mupen64plus_next, mednafen_psx_hw,
  mednafen_psx, ppsspp et azahar) ; contrôles des options du catalogue et des BIOS contre les cœurs épinglés
  réussis. Le scellement SideStore recrée l'IPA : SHA-256 de l'IPA scellée à relever après déchiffrement.
- Aucune validation sur iPhone. Ne pas réutiliser le numéro 455.

## Limites

- Aucun essai sur iPhone : charge, chaleur, mémoire aux facteurs élevés, Vulkan d'Azahar sur l'appareil, rendu
  logiciel de DeSmuME et de Beetle PSX aux facteurs élevés.
- Les binaires du buildbot embarqués peuvent différer des sources lues ; le contrat `--cores` vérifie clés, valeurs et
  noms, pas le comportement en cours de jeu. Celui-ci est prouvé par les sources (`docs/libretro-resolution.md` § 2),
  par le cœur de test et, pour DeSmuME, par la sonde simulateur. Le changement en jeu de PPSSPP avec OpenGL ES, de
  Beetle PSX et d'Azahar n'est exécuté par aucun essai automatique (pas de contexte OpenGL ES ni de GPU suffisant dans
  le Simulateur, pas de BIOS PS1 en CI).
