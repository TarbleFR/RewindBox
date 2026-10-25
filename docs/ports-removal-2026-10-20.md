# Retrait de Dusklight et de la playlist Ports — 20 octobre 2026

## 1. Décision du mainteneur

Demande du 20 octobre 2026 (« Suppression complète de Dusklight et de la section ports ») :
Dusklight, réimplémentation de *The Legend of Zelda: Twilight Princess* construite sur sa
décompilation, présente un risque juridique. Il quitte entièrement le code, l'interface et toute
IPA future, ainsi que la playlist **Ports** du menu principal qui le lançait. Interrogé sur KartPad
(seulement atteignable par Ports), le mainteneur a répondu « Retirer aussi KartPad » : son retrait
complet avait déjà été fait par une autre session le 19 octobre (`docs/kartpad-removal-2026-10-19.md`,
Build 491) et il est conservé tel quel.

Règles posées :

- aucun autre portage de Twilight Princess ne remplace Dusklight : **Dolphin** reste la solution
  pour les versions GameCube et Wii du jeu (playlists GameCube et Wii inchangées) ;
- aucun jeu, aucune sauvegarde, aucune donnée personnelle n'est supprimé automatiquement ; aucune
  suppression irréversible de données sans sauvegarde adaptée ;
- aucune IPA future ne contient le framework `DusklightCore`, ses sources, ses bibliothèques propres,
  ses ressources ni de référence capable de charger son ancien exécutable ; rien ne le réintroduit
  automatiquement lors d'une compilation ;
- l'historique Git n'est pas réécrit ; les crédits nécessaires aux versions antérieures restent.

## 2. Ce qui est retiré

| Domaine | Retiré |
| --- | --- |
| Natif | `native/dusklight/` (32 fichiers : hôte, ABI, correctifs amont canoniques, SDL) ; `packages/dusklight_internal_bridge/` (7 fichiers, plugin iOS) |
| Outils et CI | `build-utils/dusklight/` (construction et épinglage du Core), `build-utils/validate_dusklight_ipa.py`, `.github/workflows/dusklight-core.yml` ; dans `retroarch-delivery.yml`, `neoswap-ipa.yml` et `ios-ci.yml` : épinglage, attente, téléchargement, vérification et intégration du Core, contrôle de syntaxe du pont, tests Dusklight |
| Application | `lib/services/dusklight_internal_service.dart`, `dusklight_game_identity.dart`, `ports_game_identity.dart`, `lib/widgets/ports_internal_playlist_actions.dart`, `lib/l10n/dusklight_locale.dart`, `ports_locale.dart` ; route de lancement `ios_dusklight_internal`, import, menu de la playlist, réglages, identité de scraping, entrée NeoPlay (`NeoDusklightControls`), lignes de crédit |
| Système Ports | `assets/systems/ports.json` (la playlist quitte le menu principal), `assets/images/ports-gaming.webp`, capsule Canvas (ES-DE) `ports` régénérée par `tools/system_art/canvas_es_de.py` |
| Dépendances | `dusklight_internal_bridge` de `pubspec.yaml` (dépendance et espace de travail) ; `pubspec.lock` inchangé (dépendance de chemin) |
| Stockage | racine INV-13 (`Documents/Ports/Dusklight`, `Caches/Dusklight`), `StorageEngine.dusklight`, `StorageLayout.dusklight*` |
| Licences embarquées | `assets/legal/Dusklight-CC0-1.0.txt`, notices et identité Dusklight du paquet `Legal/` |
| Tests | 19 fichiers de test propres à Dusklight ou à Ports (`test/dusklight_*`, `test/ports_external_display_test.py`, `test/kartpad_removal_test.dart` dont la fonction et la traduction testées ont disparu) ; leurs contrats sont remplacés par les tests du § 6 |

Conservé volontairement :

- l'énumération `NEOSWAP_DUSKLIGHT = 3` de NeoSwap (`packages/neo_swap/ios/Classes/NeoSwap.h`) et son
  libellé dans la table des propriétaires : ABI partagée avec le Core RPCS3 épinglé
  (`build-utils/rpcs3/embedded-core.patch`), qu'on ne reconstruit pas pour ce retrait ; la valeur 3 n'a
  plus de producteur ;
- `ExternalDisplayService.runUnsupportedEngineSession` et `suspendForUnsupportedEngine` : RPCS3
  utilise la suspension pendant l'arrêt de son cœur ;
- les documents de builds antérieures (`docs/build3xx-*`, `docs/dusklight-build31x.md`…), les
  reçus de livraison et les manifestes historiques (`build-utils/baselines/ios-322.json`,
  `native/import-memory-candidate.json`, `build-utils/package_release00x.py`) : ils décrivent des
  binaires déjà livrés.

## 3. Données des joueurs

- **Fichiers** : rien n'est déplacé ni supprimé. `Documents/Ports/Dusklight` et
  `Documents/Ports/KartPad` restent dans Fichiers › NeoStation. Une copie GameCube/Wii de Twilight
  Princess rangée dans une bibliothèque GameCube ou Wii reste jouable par Dolphin ; un fichier rangé
  seulement dans `Ports/Dusklight/Games` n'est plus listé : il suffit de le placer (ou de l'importer)
  dans la bibliothèque GameCube ou Wii.
- **Base `data.sqlite`** : au premier démarrage, la synchronisation des systèmes retire la ligne
  `ports` d'`app_systems` (elle n'est plus définie) et, par les clés étrangères `ON DELETE CASCADE`
  de production, les jeux de cette playlist avec leur temps de jeu, favoris et métadonnées scrapées.
  Avant cela, `RetiredPortsBackup.prepareForSync` (`lib/services/retired_ports_backup.dart`, appelé
  par `SqliteService.loadAndSyncSystems`) fait une copie complète de la base :
  - seulement s'il reste des jeux ou métadonnées `ports` ; une seule fois (ensuite il n'y a plus
    rien à copier) ;
  - `VACUUM INTO` vers `Library/Application Support/NeoStation/Maintenance/data-before-ports-removal-<aaaammjj-hhmmss>.sqlite`,
    puis ouverture en lecture seule, `PRAGMA integrity_check = ok` et mêmes nombres de lignes `ports` ;
    une copie invalide est effacée ;
  - sans copie vérifiée (dossier non inscriptible, transaction ouverte, erreur), **rien n'est
    retiré** : la synchronisation est reportée au démarrage suivant, la playlist reste masquée du
    menu et un jeu de ces lignes est refusé au lancement (« Émulateur non configuré », traduit dans les
    douze langues, détail technique séparé) sans jamais passer par RetroArch, un lien ou la feuille
    de partage ;
  - la rotation des copies de maintenance (`data-<horodatage>.sqlite`, trois gardées) ne touche pas
    ce fichier ; l'outil de stockage le classe « jamais » (règle `NEVER.sqlite`).
- **Restauration** : la copie est une base SQLite complète ; elle peut être remise à la place de
  `data.sqlite` avec une build antérieure, NeoStation fermé.
- **Stockage** : ce que Dusklight a laissé (`Ports/Dusklight`, `Caches/Dusklight`) est désormais
  « inconnu », donc jamais proposé au nettoyage. KartPad (INV-12) garde la protection décidée le
  19 octobre.

## 4. Fichiers de bibliothèque verrouillés (Build 419)

Exception autorisée par la demande du mainteneur, réversible et vérifiée par
`test/retroarch_baseline_scope_test.py` (`PORTS_REMOVAL_EDITS`, blocs `RETIRED_PORTS_BEGIN/END`) :

- `sqlite_config_provider.dart`, `scanning.dart` : la racine de scan native `Ports/Dusklight` et le
  rafraîchissement de la bibliothèque Dusklight disparaissent ;
- `sqlite_service.dart` : la copie vérifiée avant l'élagage (bloc marqué) et `folder_name IN
  ('android', 'ports')` → `folder_name = 'android'` (4 requêtes) ;
- `sqlite_database_service.dart`, `scraper_repository.dart`, `system_repository.dart` : exclusions
  et cas particuliers de `ports`.

Le test reconstruit chaque fichier tel qu'avant ce retrait (puis avant KartPad) et compare
l'empreinte 419. Aucune migration de schéma, aucune ligne de jeu d'un autre système n'est réécrite.

## 5. Livraison et IPA

- **Donneur natif Build 350** : `build-utils/fetch_native_donor_subset.py` refuse aussi tout membre
  `dusklight` ; sous-ensemble épinglé **2 656 membres** (2 698 − exactement les 42 membres Dusklight :
  framework, notices, identité), agrégat SHA-256
  `2f73382bc15c56f425e19aa29afd11e6a29a4c547e1aa7f40f29547204a85536` ; `game_content_gate.py` passe.
  Aucun octet d'un membre Dusklight n'est demandé (`test/native_donor_subset_test.py`).
- `build-utils/prepare_fast_native_runtime.py` exige un donneur sans `DusklightCore.framework`,
  identité ni notices, et supprime un `dist/dusklight` laissé par une ancienne étape ;
  `delivery_cipher.py` ne met plus `dist/dusklight` en cache ; `embed_legal_bundle.py` n'embarque
  plus de notice ni d'identité Dusklight, même si un ancien `dist/dusklight/licenses` traîne.
- **Contrôle d'absence** `build-utils/validate_no_dusklight_ipa.py`, appelé par les trois workflows
  qui produisent une IPA, à côté de `validate_no_kartpad_ipa.py` : refuse tout membre dont le chemin
  contient « dusklight », les ressources Ports, une entrée Ports du manifeste d'assets et les octets
  « dusklight » (toute casse) dans tout autre membre — exécutables, instantané Dart, plists, JSON,
  NOTICES Flutter décompressé. Seules exceptions : les notices texte de `Legal/` et `assets/legal/`
  (crédit des builds antérieures) et une seule occurrence, dans la table des propriétaires, du binaire
  NeoSwap. Étalonnage sur l'IPA publique 0.0.8 réelle (Build 480, Dusklight embarqué) : refusée,
  60 membres. Tests synthétiques : `test/no_dusklight_ipa_test.py`.
- Aucun cœur n'est reconstruit : RPCS3, ARMSX2, Dolphin, les 34 cœurs libretro, MoltenVK et les
  helpers gardent les identités de la build de base.

## 6. Vérifications

Résultats exacts, runs et identité de livraison : § 8 (renseigné à la livraison). Tests ajoutés :

- `test/retired_ports_backup_test.dart` — vraie initialisation de la base (schéma de production),
  vraies définitions de systèmes, vraie synchronisation : copie vérifiée avant élagage (2 jeux avec
  temps de jeu et favori, métadonnées), jeu GameCube intact, fichier de jeu intact, pas de seconde
  copie ; report si le dossier n'est pas inscriptible puis réussite au démarrage suivant ; pas de
  copie sans jeu ; jamais de copie dans une transaction ouverte. Contrôle négatif : sans le garde, les
  lignes disparaissent sans copie.
- `test/retired_ports_launch_test.dart` — vrai `GameLaunchService.launchGame` : un ancien jeu Ports
  est refusé (anglais, français) avec le message traduit, aucune session ouverte, fichier intact.
  Contrôle négatif : sans le garde, l'appel part vers le lanceur général et ne rend pas ce refus.
- `test/no_dusklight_ipa_test.py`, `test/native_donor_subset_test.py`,
  `test/legal_bundle_preflight_test.py`, `test/retroarch_baseline_scope_test.py`, tests de stockage
  (racines, catégorisation, planification, copies du sélecteur), contrats de route, de fermeture,
  d'écran externe et NeoPlay mis à jour ; `test/neoplay/companion_tests.swift` vérifie que l'ancien
  bouton de menu Dusklight n'est plus une ancre.

Comptes de tests mis à jour (contrat remplacé, non affaibli) : 85 → 84 consoles et 107 → 106
systèmes iOS (la console et le système Ports n'existent plus, ce que les tests vérifient
désormais explicitement). `test/build351_native_donor_test.py` n'exige plus l'empreinte du Core
Dusklight mais son absence ; il échoue toujours, comme à la Build 491, sur sa première assertion
(épinglage d'artefact du donneur, devenu une récupération par plages).

### 6.1 Exécutions locales (conteneur Linux, Flutter 3.47.2), comparées à la Build 491

Référence : arbre `23f4ca24` (produit 491) dans un arbre de travail séparé, mêmes outils.

- `flutter analyze --no-fatal-infos` : aucun constat.
- Suite Flutter complète (`flutter test test/`) : 3 117 réussis, 5 ignorés, 8 échecs, dont 2
  corrigés ensuite (comptes ci-dessus, 46/46 à la relance avec les deux nouveaux tests) ; les
  6 restants échouent à l'identique sur la référence (`dolphin_import_ui_test` ×2,
  `dolphin_isolation_contract_test` ×2, `rpcs3_import_spu_build230_contract_test` ×2, mêmes
  assertions).
- Tous les tests Python de `test/` et `.github/diagnostics/` (Flutter disponible) : aucun nouvel
  échec ; 108 échecs avant comme après, tous déjà présents (la plupart exigent macOS, Xcode ou le
  simulateur ; quelques contrôles de périmètre figés depuis les Builds 3xx). Les causes ont été
  comparées : mêmes messages, sauf trois contrôles de périmètre historiques dont l'ordre de
  parcours ou un plantage de `git` à la référence change la première ligne affichée, pas le motif.
- Vérification indépendante sur le PC du mainteneur (PowerShell, pas de Python) : le script
  `verify492.ps1` applique les règles de `validate_no_dusklight_ipa.py` ; sur l'IPA publique 0.0.8
  (SHA-256 `2e9f1868…`) il refuse les mêmes 60 membres.

Ce qui n'est pas prouvé ici : aucun essai sur iPhone ; le simulateur et la CI ne valident pas
l'appareil.

## 7. Protocole iPhone

1. Installer l'IPA (re-signature SideStore) par-dessus une build qui avait des jeux dans Ports.
2. Ouvrir NeoStation : la playlist Ports n'est plus dans le menu principal ; GameCube et Wii sont
   présents et lancent leurs jeux par Dolphin.
3. Fichiers › NeoStation : `Ports/Dusklight` et `Ports/KartPad` sont intacts. Le journal `app.log`
   contient une ligne `[RetiredPorts] Database copied to …data-before-ports-removal-….sqlite` avec le
   nombre de jeux et de métadonnées copiés (ou `Sync postponed` et sa cause).
4. Réglages › Outils › Stockage : `Ports/Dusklight` apparaît en « inconnu », jamais proposé.
5. Relancer une seconde fois : aucune nouvelle copie.

## 8. Livraison

Reçu : `docs/evidence/portsremoval492-delivery.json`.

- **Contrôles ciblés** `build492-checks.yml`, run `39355430653` sur `b1ca2a97` (commit produit) :
  partie hôte (job `118408989719`) réussie — couverture de chaque fichier modifié depuis la 491,
  absence des chemins retirés, preuves « commentaires seuls » et « messages d'assertion seuls »,
  générateur Canvas, analyse, suite Dart de livraison, deux nouveaux tests, 13 contrats Python, deux
  tests déjà en échec sur la 491 sans nouveau cas ; partie native (job `118408990326`) réussie —
  syntaxe iPhone arm64 de chaque source Objective-C d'`external_display` contre le
  `Flutter.xcframework` épinglé, harnais NPCheck dans le simulateur iOS 18.5 : 32 tests, 0 échec
  (Xcode 26.3, SDK iPhone 26.2).
- **Livraison** `retroarch-delivery.yml`, run `39356466695` sur `3349513a` (= `b1ca2a97` + le reçu
  491 de l'autre session, documents seulement) : `checks` et `native` réutilisent les preuves
  (aucune suite relancée), `cold` réussi (compilation Release 403 s), `warm` ignoré. Base : 491
  livrée `9faa3f9b`, run `39353891715`. Aucun Core reconstruit.
- **Artefact** `12236001799` (166 115 869 octets, archive SHA-256
  `54a7acdb8d66d62cc2288e0551f4671a11cda3c5008e38f125ce1bf71c46df2c`, conservé jusqu'au 3 novembre
  2026), chiffré pour `build-utils/delivery-492-recipient.pem` (clé privée créée sur le PC du
  mainteneur, supprimée après la remise).
- **IPA 0.0.8 (492)** `NeoStation-Build492-3349513a…-cold.ipa`, **165 863 534 octets**, SHA-256
  **`56eb53f31f3ee131ea7048ccac5f4f1f5ebd3ef23b41c282249932f7de3fbb79`**, égal à `SHA256SUMS`, à
  `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build492-3349513a.ipa`.
  Re-signature SideStore requise. 20,6 Mo de moins que la 491 (186 428 464 octets).
- **Inspection indépendante** de l'IPA scellée sur le PC : 4 082 membres, aucun élément Dusklight
  ni Ports (seules les notices historiques et la table d'ABI NeoSwap contiennent le mot) ;
  application et cinq extensions en 0.0.8 (492) ; garde Ports présent dans le code Dart, route
  Dusklight absente ; 70 frameworks dont 34 cœurs libretro, DolphinCore, ARMSX2Core et
  libRPCS3Core ; aucune image Dusklight ni KartPad dans la liste des images signées. Le reçu 491
  ne consignant pas d'empreintes par image, l'identité des moteurs repose sur les étapes d'identité
  épinglée de la livraison et sur la fermeture de source (aucune entrée de Core modifiée).

Aucune validation sur iPhone. Ne pas réutiliser le numéro 492.
