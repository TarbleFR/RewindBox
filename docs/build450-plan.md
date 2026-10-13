# Build 450 — système de shaders (moteur libretro, Dolphin)

Demande du mainteneur (cahier des charges « catalogue universel de shaders, téléchargements in-game et
amélioration graphique RetroArch / Dolphin ») : parcourir, télécharger, installer, prévisualiser, appliquer et
régler des shaders depuis le menu en jeu, pour le moteur libretro intégré, Dolphin et les moteurs futurs ; ne pas
déclarer un shader compatible parce que son fichier est reconnu ; étudier le portage Mattias CRT pour Dolphin sans
l'empaqueter tant que les droits ne sont pas établis ; compiler l'application sur la version 0.0.7.

Base : Build 449 (`ff2a491c83b9eb7477b0e38e6f4a83e4a20680d1`). Aucun cœur, helper JIT ni fichier verrouillé sur la
Build 419 n'est modifié ; le cœur Dolphin conservé et son interface C restent identiques (`DolphinSessionMenu.h`
inchangé) ; `pubspec.lock` est identique ; `pubspec.yaml` ajoute le paquet `neo_shader_kit` (membre de l'espace
de travail) et passe à `0.0.7+450`.

## Chantiers

| Chantier | Commits | Contenu |
| --- | --- | --- |
| Kit partagé | `0b44a737`, `63d991b8` | cœur C++17, glslang et SPIRV-Cross vendorisés, exécution Metal des préréglages slang, catalogue officiel, stockage vérifié, profils |
| Menu libretro | `2a076d80` | Réglages › Shaders : préréglages intégrés et installés, catalogue (recherche, favoris, catégories, fiche, aperçu, téléchargement vérifié), profils, réglages ; 71 textes en douze langues ; catalogue « rendu » (982) |
| Dolphin | `71b8815e`, `d5cab2a3` | Affichage › Effet de post-traitement : effets officiels, imports vérifiés sur l'appareil, réglages, choix appliqué au lancement suivant ; 36 textes en douze langues ; validation CI par une reproduction de l'interface de Dolphin : 43 effets officiels sur 45 rendus (les deux effets HDR, sans effet sur iPhone, écartés), 6 fichiers Mattias sur 6 |
| Mentions légales, documentation, version | `bcf666b3` | glslang (dont l'exception Bison), SPIRV-Cross (Apache-2.0 et notices MIT des en-têtes Khronos) : `assets/legal/`, `THIRD_PARTY_NOTICES.md`, crédits dans l'application, contrôle du paquet légal de l'IPA ; `docs/shaders-system.md`, `docs/shaders-mattias-crt.md` ; `0.0.7+450` |
| Porte de livraison | ce plan | bloc `BUILD450_DELTA` (201 entrées revues depuis `ff2a491c`) ; inventaire `native/` du test de livraison complété par les textes de la page Dolphin (changement de contrat commenté) |

Architecture et vérifications détaillées : `docs/shaders-system.md` ; étude Mattias : `docs/shaders-mattias-crt.md`.

## Où se trouvent les fonctions

- Moteur libretro : menu en jeu › Réglages › **Shaders** (portée console/jeu, préréglages, installés, « Catalogue
  officiel », « Profils », réglages du shader en effet).
- Dolphin : menu en jeu › Graphismes › Affichage › **Effet de post-traitement**.

## Vérifications

Exécuté dans ce conteneur (Linux x86_64, Flutter 3.47.2) :

| Contrôle | Résultat |
| --- | --- |
| Les huit séries `flutter test` du job `checks` de la livraison (bibliothèque, dossiers de ROM, stockage, NeoSwap, musique, RPCS3, Dolphin, couvertures) | toutes réussies |
| Tests Python du job `checks` | réussis, sauf trois cas : `game_audio_handoff_test.py` réussit avec Flutter dans le `PATH` ; `cheats_media_source_contract_test.py` (commit absent du clone superficiel) et `library_cover_delivery_test.py` (porte du périmètre `library_covers`) échouent à l'identique sur la source 449 |
| `flutter analyze` des fichiers Dart modifiés | aucun problème |
| Douze langues : `libretro_locale` (71 textes), page Dolphin (36 textes, `dolphin_shader_localizations_test.py`) | réussis |
| Paquet légal : `embed_legal_bundle.py` puis `validate_legal_bundle_ipa.py` sur une IPA d'essai | réussis |
| Porte `verify_delivery_reuse.py --offline` (bloc `BUILD450_DELTA`) | réussie |
| `delivery_pipeline_test.py` | 12 sur 13 ; le test du cache demande `zstd`, absent du conteneur (présent sur la CI), comme pour la 449 |
| Tests de périmètre historiques (`import_memory_candidate_scope_test.py`, `neoplay_build397_integration_test.py`, `check_neo_swap_scope.py`) | échecs identiques sur la source 449, sans lien avec ce chantier |

CI GitHub (branche `Claude`) :

- `shader-kit-checks` `38332666178` (`2a076d80`) : 982 préréglages du catalogue sur 982 compilés pour iPhone et
  rendus visiblement avec Metal ; tests de rendu, pod iPhone.
- `shader-kit-checks` `38334940237` (`71b8815e`) : deux attentes de test fausses (pas d'une option Dolphin lue en
  float ; fichier JSON rejeté en bloc à cause de `1e999`), corrigées par `d5cab2a3` ; validation Dolphin : 43 effets
  officiels sur 45 et 6 fichiers Mattias sur 6 rendus.
- `shader-kit-checks` `38336456305` (`bcf666b3`) : entièrement réussi (rendus Metal, pod iPhone, magasin Dolphin sur
  de vrais fichiers et page compilée pour iPhone, 982 préréglages, 43 effets Dolphin redessinés avec le catalogue
  régénéré).
- `libretro-checks` `38334940229` (`71b8815e`), `external-display-check` `38332666189` (`2a076d80`),
  `dolphin-motion-check` `38334944250` (`71b8815e`), `legal-compliance-check` `38336464575` (`bcf666b3`) : réussis.
- `libretro-simulator` : voir ci-dessous.

### Sonde simulateur : constat ouvert repris

`ppsspp-crowded` échoue sur `71b8815e` (`38334940216`), `bcf666b3` (`38336456293`), `8472350` (`38337609542`,
avec `ppsspp-crowded-prx`) et `b5b57a0f` (`38338491666`). Il avait réussi sur `2a076d80` (`38332666123`). Tous les
autres scénarios réussissent, et le jeu PSP démarre puis se ferme dans l'ordre. Ce défaut de sonde est déjà consigné
dans `docs/libretro-touch-skins-audit.md` (échecs sur `4da3154` et `194d427`). Il est resté ouvert sans correction
par décision du mainteneur du 12 octobre 2026.

- L'estimation faite juste avant le démarrage ne voit libre que la base réservée (1 base sur 256).
- PPSSPP prend pourtant ensuite une autre base, plus basse.
- Depuis que la sonde lie le kit (binaire plus gros, disposition mémoire différente), le cas est plus fréquent :
  avant, il était rare (2 runs sur l'historique connu).

Relevé ajouté à la sonde, sans changer ses vérifications (`8472350`, `b5b57a0f`). Il note les régions de la
fenêtre avant et après le remplissage, puis au lancement. Runs `38337609542` et `38338491666` :

- **Zone basse.** Les emplacements des 5 à 9 bases les plus basses (à partir de `0x100000000`) sont vides pour
  `vm_region`, mais `vm_allocate` fixe les refuse : le remplissage ne peut pas les prendre. PPSSPP, qui place ses
  vues par `vm_remap`, a pourtant utilisé des bases de cette zone : `0x101000000`, `0x103000000` et `0x104000000`
  sur `bcf666b3`, `0x103000000` pour `ppsspp-prx` sur `b5b57a0f`.
- **Remplissage intact.** Aucun emplacement pris par le remplissage ne disparaît pendant le démarrage
  (`b5b57a0f`).
- **Base retenue.** Sur `b5b57a0f`, la base prise dans le scénario encombré (`0x106800000`) avait, au remplissage,
  son emplacement occupé par une autre région, de mêmes adresse et taille au lancement. Sur `8472350`, les bases
  prises (`0x10e800000`, `0x107000000`) n'étaient ni libres ni libérées selon le relevé. Hypothèse non démontrée :
  une vue de 16 Kio laissée par PPSSPP lui-même lors d'un essai de base antérieur, puis remplacée pendant ce
  démarrage.
- **Réservation toujours utile.** Avec les sources d'avant la réservation, le même scénario échoue toujours avec
  « Failed finding a memory base » : la réservation reste ce qui fait démarrer le jeu quand la fenêtre est pleine.

En résumé, la sonde ne peut pas garantir sa condition de départ, « aucune base libre hors réservation ». Des
emplacements tenus par des régions qu'elle ne peut pas prendre redeviennent utilisables par PPSSPP pendant le
démarrage. Le jeu démarre dans tous les cas.

Aucune correction n'est appliquée, conformément à la décision du 12 octobre. Pistes proposées au mainteneur :

1. Faire prendre les emplacements par le remplissage avec l'appel qu'utilise PPSSPP (`vm_remap` fixe), afin
   d'occuper aussi la zone basse.
2. Vérifier si PPSSPP laisse des vues aux bases qu'il essaie sans les retenir. Une telle fuite encombrerait
   peu à peu la fenêtre au fil des lancements PSP, sur iPhone aussi. Ce n'est pas établi.

## Livraison

Run `retroarch-delivery.yml` lancé sur `Claude` (`build_number` 450, périmètre `full`, artefact chiffré pour
`build-utils/delivery-424-recipient.pem`) depuis la source qui contient ce plan. Identité (run, artefact, taille,
SHA-256 de l'archive) consignée après le run.

## Ce qui n'est pas vérifié

Aucun shader appliqué sur un iPhone ni sur une Apple TV ; aucun effet Dolphin dans le cœur Dolphin lui-même ;
durées de compilation et temps GPU sur iPhone non mesurés. Le chantier 3DS (« je ne peux toujours pas importer un
dossier Nand-zip ») attend les éléments demandés au mainteneur (message exact, contenu du ZIP).
