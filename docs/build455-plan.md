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

Cœurs : Azahar ×1–×10, DeSmuME ×1–×10, Beetle PSX HW et Beetle PSX ×1/×2/×4/×8, PPSSPP ×1–×5 en cours de jeu ;
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
  réussis.
- Contrats Python : `libretro_core_options_test.py` (sans `--cores`), `libretro_frontend_ui_contract_test.py`,
  `localization_12_locale_coverage_test.py`, `delivery_pipeline_test.py`, `external_display_host_plist_test.py` et
  les autres contrats du job Dart : réussis. `verify_delivery_reuse.py --offline` : réussi (`BUILD455_DELTA`,
  36 entrées).
- L'Objective-C n'a pas pu être compilé dans ce conteneur (pas de SDK Apple) : compilation et exécution natives
  en CI macOS seulement.

### CI

À compléter : `libretro-checks` (compilation iPhone de tout le pont, test hôte macOS, contrat des binaires épinglés
avec `--cores`), sonde simulateur (PPSSPP réel), livraison.

## Limites

- Aucun essai sur iPhone : charge, chaleur, mémoire aux facteurs élevés, Vulkan d'Azahar sur l'appareil, rendu
  logiciel de DeSmuME et de Beetle PSX aux facteurs élevés.
- Les binaires du buildbot embarqués peuvent différer des sources lues ; le contrat `--cores` vérifie clés, valeurs et
  noms, pas le comportement en cours de jeu. Celui-ci est prouvé par les sources (`docs/libretro-resolution.md` § 2),
  par le cœur de test et, pour PPSSPP, par la sonde simulateur.
