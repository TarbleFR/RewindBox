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
- `libretro-simulator` : échec connu de la sonde sur `ppsspp-crowded`, sans panne de l'application ; voir
  ci-dessous.

### Sonde simulateur : limitation connue de la sonde simulateur — aucune régression de lancement démontrée

Le lancement PSP est corrigé. Les correctifs `d4de3c76` (réservation de la fenêtre mémoire de PPSSPP au lancement)
et `54147b97` (arène placée sous la plage des vues de RAM) sont présents dans cette source.

Le scénario automatisé `ppsspp-crowded` exige que PPSSPP utilise précisément la base réservée. Or sa préparation ne
garantit pas que les autres bases soient inutilisables. Son échec, quand le contenu PSP démarre et se ferme
correctement, ne démontre donc pas une régression du lancement PSP.

Statut : limitation de la sonde connue et hors périmètre du chantier actuel. Les tests et leurs vérifications sont
conservés tels quels. Un rapport de CI signale cet échec comme l'échec connu de la sonde, pas comme une panne de
l'application. Le sujet ne se rouvre que sur un élément nouveau et vérifiable (règle permanente dans `AGENTS.md`).

Relevé de ce cycle, pour mémoire :

- **Runs.** Seule l'assertion « PPSSPP's memory at the reserved base » échoue, sur `71b8815e` (`38334940216`),
  `bcf666b3` (`38336456293`), `8472350` (`38337609542`, avec `ppsspp-crowded-prx`) et `b5b57a0f` (`38338491666`).
  Le jeu PSP démarre puis se ferme dans l'ordre, et tous les autres scénarios réussissent.
- **Diagnostic seulement.** Un relevé a été ajouté à la sonde sans changer ses vérifications (`8472350`,
  `b5b57a0f`). Il note les régions de la fenêtre avant et après le remplissage, puis au lancement.
- **Zone basse.** Les emplacements des 5 à 9 bases les plus basses (à partir de `0x100000000`) sont refusés à
  `vm_allocate` fixe : le remplissage ne peut pas les prendre. PPSSPP place ses vues par `vm_remap` et peut donc
  utiliser des bases de cette zone (`0x101000000`, `0x103000000`, `0x104000000` sur `bcf666b3`).
- **Remplissage intact.** Aucun emplacement pris par le remplissage ne disparaît pendant le démarrage
  (`b5b57a0f`).
- **Réservation utile.** Avec les sources d'avant la réservation, le même scénario échoue toujours avec « Failed
  finding a memory base ». La réservation reste ce qui fait démarrer le jeu quand la fenêtre est pleine.

## Livraison

- **Run.** `retroarch-delivery.yml` `38339349667`, lancé sur `Claude` (`build_number` 450, périmètre `full`),
  depuis la source `e7f223365a12327c62bfc154b0bddd789d2a0131`, qui contient ce plan.
  - Jobs `checks` (tests Dart et gardes de livraison), `native` et `Release device build • cold` réussis.
  - Horaires : 02:57 → 03:18 UTC, 13 octobre 2026. Compilation Release (AOT et Xcode) : 314 s.
- **Version.** L'étape d'alignement a posé 0.0.7 (450) dans l'application et ses extensions.
- **Contenu vérifié par le job.**
  - `neo_shader_kit.framework` est embarqué avec `slang-catalog.json`, `dolphin-catalog.json` et leurs
    diagnostics.
  - Paquet légal de l'IPA validé, dont `glslang-LICENSE.txt` et `SPIRV-Cross-Apache-2.0.txt`.
  - Portes d'IPA réussies.
  - IPA validée avant scellement : SHA-256 `418444d95bb54fef381fc15e34b8cc0ce8f25fd7c2d1cdd676022a2fe3d8e309`.
  - Binaire principal : SHA-256 `5b86085c6cb5dd5cf67069322171e62182872d67715622d1a1d25dea7bdd5a08`.
- **Artefact remis.** `NeoStation-Build-450-e7f223365a12327c62bfc154b0bddd789d2a0131-cold`.
  - ID `11786148903`, 212 085 661 octets.
  - SHA-256 de l'archive : `ba07914261d9ba8066939c3f8cf406147f6274e6ac61d8020387edbca00d061a`.
  - Conservé jusqu'au 27 octobre 2026, chiffré pour `build-utils/delivery-424-recipient.pem`.
  - Le SHA-256 de l'IPA scellée pour SideStore se lit après déchiffrement (`SHA256SUMS` de l'enveloppe). Il
    n'est pas connu dans ce conteneur, qui ne peut pas télécharger les artefacts.
- **Diagnostics chiffrés.** `…-cold-diagnostics`, ID `11785899316`, 5 170 621 octets.

## Ce qui n'est pas vérifié

Aucun shader appliqué sur un iPhone ni sur une Apple TV ; aucun effet Dolphin dans le cœur Dolphin lui-même ;
durées de compilation et temps GPU sur iPhone non mesurés. Le chantier 3DS (« je ne peux toujours pas importer un
dossier Nand-zip ») attend les éléments demandés au mainteneur (message exact, contenu du ZIP).
