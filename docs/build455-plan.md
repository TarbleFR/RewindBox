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

À compléter : contrôles et sonde sur la source corrigée, livraison.

## Limites

- Aucun essai sur iPhone : charge, chaleur, mémoire aux facteurs élevés, Vulkan d'Azahar sur l'appareil, rendu
  logiciel de DeSmuME et de Beetle PSX aux facteurs élevés.
- Les binaires du buildbot embarqués peuvent différer des sources lues ; le contrat `--cores` vérifie clés, valeurs et
  noms, pas le comportement en cours de jeu. Celui-ci est prouvé par les sources (`docs/libretro-resolution.md` § 2),
  par le cœur de test et, pour DeSmuME, par la sonde simulateur. Le changement en jeu de PPSSPP avec OpenGL ES, de
  Beetle PSX et d'Azahar n'est exécuté par aucun essai automatique (pas de contexte OpenGL ES ni de GPU suffisant dans
  le Simulateur, pas de BIOS PS1 en CI).
