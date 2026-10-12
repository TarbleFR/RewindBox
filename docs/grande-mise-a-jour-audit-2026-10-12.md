# Grande mise à jour — audit complet avant toute modification (12 octobre 2026)

Synthèse des six audits en lecture seule demandés par le mainteneur avant les cinq
chantiers de la « Grande mise à jour » : AirPlay universel, Nintendo 3DS, livres et
mangas 3D, musique d'ambiance, analyse et nettoyage du stockage. Aucun fichier du
dépôt n'a été modifié pendant cet audit ; ce document est le seul ajout.

- Révision auditée : `165c0201` (`origin/Claude`, sources de la Build 445, produit
  identique à la 444). Flutter 3.47.2 / Dart 3.13.2, hôte iOS généré à la compilation.
  Pendant l'audit, une autre session a livré la Build 446 (`9cca828e`, correctif des
  catalogues de skins libretro, `docs/build446-plan.md`) : elle ne touche aucun des
  fichiers examinés ici ; la candidate de la grande mise à jour se construira par-dessus
  la 446.
- Méthode : six auditeurs indépendants (un par chantier plus un sur les fondations
  communes), chacun citant les sources (`fichier:ligne`), puis six vérificateurs
  contradictoires chargés de réfuter chaque constat (relecture sur `fa3aba11`, HEAD de
  `Claude` au moment de la vérification). Les verdicts sont au § 10 ; leurs corrections
  sont intégrées dans les sections concernées, signalées par « ✱ vérif. ».
- Vocabulaire : **confirmé** = établi dans les sources du dépôt ou du SDK épinglé ;
  **hypothèse** = déduit, non démontré ; **non vérifiable ici** = exige l'iPhone,
  l'Apple TV ou un accès réseau que ce conteneur n'a pas. Rien de ce qui suit n'a
  été exécuté sur un iPhone.

## 1. Résumé

| Chantier | Cause principale du défaut (sources) | Faisabilité | Ce qui reste impossible |
| --- | --- | --- | --- |
| 1. AirPlay universel | Les bandes noires (menu compris) viennent de la **recopie système** : NeoStation n'ouvre aucune fenêtre sur l'écran externe hors session Dolphin (manifeste de scènes Flutter = rôle application seul, `FlutterSceneDelegate` sans fenêtre externe). Le correctif 442 ne vit que pendant un jeu Dolphin, sur des API dépréciées, jamais validé sur appareil. ✱ vérif. : à partir d'**iOS 27**, la scène externe n'est livrée qu'après enregistrement d'un `UISceneAccessory` (API iOS 27, SDK absent de la CI Xcode 26.3) ; la version iOS de l'iPhone du mainteneur décide du régime. | Plugin hôte commun `external_display` (scène `ExternalDisplayNonInteractive`, coordinateur, politique de placement), second moteur Flutter **complet** pour le menu, adoption vue par vue : libretro (vraie résolution TV), Dolphin, RPCS3, ARMSX2 (agrandissement seul). | Dusklight/KartPad (fenêtre SDL dans les cœurs verrouillés) ; rendu natif à la résolution TV pour Dolphin/RPCS3/ARMSX2 ; 4K imposé ; validation en CI (pas d'écran AirPlay) ; deux inconnues à lever sur l'appareil (régime iOS 27, `UIApplicationSupportsMultipleScenes`). |
| 2. Nintendo 3DS | Le cœur `azahar` n'expose aucun réglage curé ; aucune voie Dart n'écrit `Config/Azahar.json` ; le cœur ignore `RETRO_ENVIRONMENT_GET_LANGUAGE` ; sa langue n'est appliquée **que** si la région est « Auto ». ✱ vérif. : **l'artefact de cœurs épinglé expire le 23 octobre 2026** (rétention 14 jours) — bloquant pour toute livraison après cette date, pas seulement pour la 3DS. | Tout en Dart : trois réglages curés (langue, région, modèle), magasin d'options atomique, page « Nintendo 3DS », assistant d'import des données système (`config` CFG, `seeddb.bin`, titres NAND, clés en option avancée) avec sauvegarde et restauration. | Langue avec région fixe (limite du cœur) ; changement à chaud (le modèle exige même une nouvelle session) ; images NAND chiffrées (`nand.bin`) ; réglage par jeu sans natif ; aucune distribution de clés/firmware ; preuve par `session.log` non fiable. |
| 3. Livres 3D | La « couverture 3D » 443 est une pile de rectangles plats inclinés, sans volume, sans épaisseur, utilisée seulement dans le hub en ligne ; lecteurs sans pages fixes (EPUB), sans curl, sans marque-pages, un seul jeu de réglages global. | Tout en Dart/Impeller : volume texturé (`drawVertices` + `ImageShader`), ouverture animée par route dédiée, curl par shader de fragment avec repli painter, paginateur EPUB → CFI, marque-pages additifs dans `reading-state.json`, barre d'outils, réglages par livre. | Transition de route globale (`main.dart` verrouillé) ; portrait pendant une session libretro ; césure/veuves ; CBR/MOBI/DRM ; mesure de fluidité et de mémoire sans iPhone. |
| 4. Musique d'ambiance | Une musique de menu existe (`HomeMusicService`) mais : fichier utilisateur seulement, onglet Systèmes seulement, désactivée par défaut, sans fondu ni point de boucle ni volume ; `beginSession()` ne la coupe pas. | `AmbientMusicService` global sur le moteur SoLoud partagé (`LoadMode.disk`, `loopingStartAt`, `fadeVolume`/`scheduleStop`), crochets `beginSession`/`_finalize`, bouton d'en-tête, rangées Général, catalogue 12 langues. | **Licence et fichier « Fairy Lights » non vérifiables ici** (opengameart.org → 403) ; fin de boucle = fin de fichier (piste à découper) ; formats AAC/ALAC ; écoute ≥ 20 min ; fondu synchrone sur la voie Ports (150 ms). |
| 5. Stockage | Aucune vue du stockage ; imports par **copie** (double copie du sélecteur dans `tmp/` — copie système `-Inbox` puis copie du plugin — jamais supprimée, bibliothèque Dolphin cachée, extraction KartPad) ; orphelins laissés par le scanner verrouillé ; `RPCS3/Cache` jamais purgé par NeoStation (borné à 4 Gio par le Core) ; journaux Dolphin/KartPad sans borne. ✱ vérif. : `FilePicker.clearTemporaryFiles()` (import de sauvegardes RPCS3) **vide toute la racine `tmp/`**, y compris les dossiers d'autres moteurs. | Outil Réglages › Outils entièrement Dart : registre de racines sans effet de bord, scanner en isolate, catégories A–I, détecteurs d'orphelins et de doublons, trois niveaux, gestionnaire de suppression sûr, rapport exportable. | Inode/liens physiques et espace libre sans `dart:ffi` ou plugin ; fichiers NeoSwap délinkés ; reproduction exacte du chiffre des Réglages iOS ; correction à la source des orphelins (scanner verrouillé) ; preuve de la cause « 40 Go / 20 Go » sans mesure iPhone. |

Décisions à prendre avant le code : § 11. Ordre des phases et builds : § 9.

## 2. Fondations communes (contraintes et lacunes transversales)

### 2.1 Ce qui ne peut pas changer

- **Dix fichiers de bibliothèque verrouillés sur la Build 419** + `lib/main.dart`
  (seuls les trois blocs `LIBRARY_RELOCATION_*` sont tolérés) + 130 sources natives
  du manifeste, contrôlés par `test/retroarch_baseline_scope_test.py:45-92` sur
  quatre workflows. Conséquences directes pour les chantiers :
  - aucune colonne ni migration SQLite (`sqlite_service.dart`, `_databaseVersion = 112`) :
    toute préférence nouvelle passe par SharedPreferences, NSUserDefaults ou un JSON
    sous Application Support ;
  - aucun point d'entrée, `runApp`, transition de route ou initialisation dans `main.dart` :
    un second moteur Flutter (AirPlay) doit déclarer son `entrypoint` dans une autre
    bibliothèque Dart ; l'ouverture animée des livres doit être une route dédiée ;
    l'initialisation de la musique se fait depuis `app_screen.dart` ;
  - `HomeMusicService.setMainMenuActive(bool)` garde sa signature (appelée par
    `system_content.dart`, verrouillé) ;
  - les orphelins produits par le scanner verrouillé (`sqlite_database_service.dart:795-869`)
    ne peuvent être évités à la source, seulement détectés après coup.
- **Hôte iOS généré à chaque build** (`test ! -d ios`, `.gitignore:306`) : toute clé
  Info.plist (rôle de scène externe) passe par un configurateur Python idempotent
  appelé dans « Configure release host » (`retroarch-delivery.yml:1044-1066`), jamais
  à la main, avec assertion sur l'IPA. ✱ vérif. : la génération se fait en deux temps —
  `build_support.py scaffold` (nom, description réseau local) puis `configure`
  (`configure_dolphin_ios_v2.py` : clés Files `UIFileSharingEnabled`/
  `LSSupportsOpeningDocumentsInPlace`, orientations, schémas d'URL), puis
  `configure_neoswap_storage.py`, `patch_ios_video_player_audio_session.py` (patch du
  pub-cache `video_player_avfoundation`), `configure_neoplay_ios.py --deployment-only`
  et `stamp_host_version.py`. Plancher de l'app : **iOS 18.0** (Runner, Flutter.framework,
  relevé par le configurateur NeoPlay) ; 17.4 seulement pour les pods des ponts et les
  helpers. Toute nouvelle dépendance pub touchant `AVAudioSession` devra être patchée ou
  refusée comme `video_player`.
- **Cœurs et moteurs verrouillés** (Dolphin 350, RPCS3 Core épinglé, ARMSX2, Dusklight,
  KartPad, cœurs libretro du buildbot) : seuls les ponts Objective-C/Swift et le Dart
  changent ; toute modification de `build-utils/libretro` exige un nouveau run
  `libretro-cores.yml` et une nouvelle paire `LIBRETRO_CORES_HOST_SHA/RUN_ID`.
- **Gate de livraison** : tout fichier créé ou modifié sous `lib/`, `packages/`,
  `native/`, `build-utils/`, `assets/`, `test/`, `pubspec*` doit figurer dans un bloc
  `DELTA` de `build-utils/verify_delivery_reuse.py` (modèle `BUILD440_DELTA` ; les
  nouveaux blocs se numérotent à partir de **447**, la 446 étant livrée) ; les
  fichiers `native/` modifiés doivent rester l'ensemble exact attendu par
  `test/delivery_pipeline_test.py:45-52` ; `pubspec.yaml`/`pubspec.lock` sans diff.
  ✱ vérif. : `test/delivery_pipeline_test.py:71-83,118-126` fige aussi la forme du job
  `checks` (trois `hashFiles` identiques, la ligne `flutter test …`, le nom de l'étape de
  validation) ; les listes `flutter test` sont explicites, pas des globs (un
  `test/storage_*_test.dart` ne tourne que s'il est ajouté) ; le périmètre « complet »
  reste un jeu fermé, ce qui vaut aussi pour le chantier livres.
- **Douze langues** par les catalogues du projet (`AppLocale` ×12, `LibretroLocale.values`,
  catalogues de fonctionnalité « values map » comme `UiRefreshRateLocale`), test de
  parité par catalogue, inscription dans `test/localization_12_locale_coverage_test.py:35-45`
  (liste fixe), interdiction des branches `languageCode == 'fr'` hors `lib/l10n`.
- **Audio** ✱ vérif. : deux régimes, pas un. Frontend : catégorie `.ambient` +
  `.mixWithOthers` appliquée nativement par `ExternalFolderAccessPlugin.swift:470-488`
  et pilotée par `AudioPolicyService` aux frontières structurelles (Sonnerie/Silence
  maître). Moteurs : libretro, Dolphin et RPCS3 passent en `.playback` pendant le jeu et
  restaurent la catégorie à l'arrêt ; KartPad agit sur la session via le sous-système
  audio SDL de son donneur binaire (`DonorAudioSession.h`, identité verrouillée) — d'où
  `restoreAfterGameSession()` puis `restoreAfterKartPad()`. miniaudio (SoLoud) enregistre
  son propre observateur d'interruption et appelle `setActive:YES` à la reprise. SoLoud
  partagé entre SFX, lecteur Musique et musique du menu ; `FrontendMediaGate`
  (`ChangeNotifier`, `blocked`) pour toute vidéo du frontend, et écoutable passivement.
- **Réglages** : pas de registre de panneaux ; une rangée = `getItemCount` +
  `selectItem` + `build` + `_itemKeys` cohérents ; pages poussées avec
  `LibretroPageNavigation` + `libretroPage` + `libretroPageAppBar`.
- **Cycle de lancement** : `GameLaunchManager.beginSession()` est le seul point commun
  avant la remise native (tous moteurs, RetroArch externe compris) ; `_finalize()` le
  seul point commun du retour (après `AudioPolicyService.restoreAfterGameSession`) ;
  fin de session observée par `sessionEvents` (Dusklight/KartPad/ARMSX2 ; libretro
  l'émet aussi, Dolphin et RPCS3 **jamais**) ou par sondage 2 s (Dolphin/RPCS3/libretro ;
  seules les exceptions de canal valent « actif », toute autre exception ferme) ; ordre
  des routes verrouillé par `test/libretro_route_contract_test.py:23-32`. ✱ vérif. :
  pour la route externe `ios_direct_launch` (RetroArch, MeloNX), `isProcessRunning`
  renvoie `false` sur iOS : la session se ferme au premier tick de sondage exécuté
  (≈ 4 s après la remise, en pratique au retour au premier plan) et **`_finalize()`
  peut s'exécuter pendant que l'application externe est au premier plan** — tout état
  AirPlay/musique restauré là doit être idempotent avec l'observateur de cycle de vie.
  Le harnais `test/game_audio_handoff_test.py` compile `game_launch_manager.dart` en
  retirant ses imports : tout nouvel import exige un double.
- **CI sur `Claude` par push** : seulement `libretro-checks`, `libretro-cores`,
  `libretro-simulator`, `retroarch-double-open-probe`, `ui-refresh-rate-check` ; tout
  le reste (dont `launch-ui-checks`, `legal-compliance-check`, `retroarch-delivery`,
  `dolphin-*`, `neoswap-*`) exige `workflow_dispatch --ref Claude` (filtres
  `branches: [experimental]` jamais mis à jour — confirmé). ✱ vérif. : les `paths:` de
  `libretro-checks.yml` ne couvrent ni `game_launch_manager.dart`, ni
  `audio_policy_service.dart`, ni `home_music_service.dart`, ni un futur
  `lib/l10n/<feature>_locale.dart` ; `test/game_audio_handoff_test.py` n'est **pas**
  dans `retroarch-delivery.yml` (seulement ios-ci, launch-ui-checks, libretro-checks,
  neoswap-ipa) ; `home_music_silent_mode_test.dart` et `theme_importer_retirement_test.py`
  ne tournent dans aucun workflow ; `libretro-simulator.yml` se déclenche sur
  `lib/services/libretro_core_catalog.dart` (pertinent pour la 3DS).
- **Légal** : tout composant ou média tiers → `docs/LEGAL_AND_CREDITS.md`,
  `assets/legal/THIRD_PARTY_NOTICES.md`, fichier de licence dans `assets/legal` +
  `REQUIRED_LEGAL_FILES` (`embed_legal_bundle.py:18-32`) + `REQUIRED`/marqueurs de
  `validate_legal_bundle_ipa.py`, `legal_bundle_preflight_test.py`. Les deux documents
  sont épinglés au commit `7f42929e` par `test/import_memory_candidate_scope_test.py`
  (test non exécuté par la CI, déjà rouge sur 444/445 : décision du mainteneur).

### 2.2 Lacunes des fondations relevées

- Filtres de branche des workflows restés sur `experimental` : fausse impression de CI
  verte sur `Claude` pour `game_launch_manager.dart`, `audio_policy_service.dart`, le
  bundle légal, Dolphin et NeoSwap (confirmé).
- `test/import_memory_candidate_scope_test.py` : épinglage historique non entretenu
  (confirmé).
- Plugins qui parcourent `connectedScenes` sans filtrer le rôle (`NPController.swift:146-148`,
  `UiRefreshRatePlugin.m:37-41`) : une scène externe pourrait être prise pour la scène
  application (hypothèse, à garder par des tests si le chantier 1 crée cette scène).
  ✱ vérif. : KartPad est protégé (la fenêtre du contrôleur Flutter du registrar est le
  premier candidat) — risque mineur, filtre de rôle à ajouter par cohérence.
- `IosSetupLocale`/`HomeMusicLocale` reposent sur `MapLocale('zh_Hant')` pour le chinois
  traditionnel — ✱ vérif. : **confirmé** (`flutter_localization` fabrique
  `languageCode == 'zh_Hant'`), donc sans risque tant que `main.dart` le déclare ainsi ;
  les nouveaux catalogues gèrent `zh_Hant` + script + TW/HK/MO explicitement.
- ✱ vérif. (hypothèse à tester) : les écrans de démarrage (`_startupStrings`,
  `lib/main.dart:608-624`, verrouillé) cherchent `zh_Hant` puis `languageCode` ; un
  iPhone en chinois traditionnel (`zh-Hant-TW`) retomberait sur le chinois simplifié.
  Hors périmètre sans autorisation sur `main.dart`.
- ✱ vérif. : 18 catalogues de `lib/l10n` sont hors de la liste fixe de
  `localization_12_locale_coverage_test.py` (dont `home_music_locale.dart`, sans test de
  parité) ; ce test n'interdit que six chaînes anglaises historiques, aucune détection
  générique — la seule garantie reste la parité des maps et les tests Dart par catalogue.
- ✱ vérif. : écart légal préexistant — les 14 cœurs libretro embarqués (dont quatre
  « non commerciaux » et picodrive), `rcheevos` et MoltenVK ne figurent ni dans
  `docs/LEGAL_AND_CREDITS.md`, ni dans `assets/legal`, ni dans `REQUIRED_LEGAL_FILES`
  (AGENTS.md : licences des cœurs à revoir après les tests ; à ne pas aggraver avec la 3DS).
- ✱ vérif. : `FilePicker.clearTemporaryFiles()` (`rpcs3_save_exchange_service.dart:865`)
  supprime **toutes** les entrées de `NSTemporaryDirectory()` sur iOS (`tmp/KartPad`,
  `tmp/Dusklight`, `tmp/NeoStationDolphinJIT`, FramePacing, SoLoud…) ; son `guard()` ne
  protège que RPCS3. Danger latent pendant une session KartPad/Dusklight/Dolphin-JIT,
  à signaler au mainteneur ; jamais à réutiliser comme primitive de nettoyage.

### 2.3 Socle commun retenu pour les cinq chantiers

1. Un catalogue de traduction « values map » par chantier (`lib/l10n/<feature>_locale.dart`)
   avec test Dart de parité/placeholders/`zh_Hant`, inscrit dans le test de couverture et
   dans les listes `flutter test` de `libretro-checks.yml:102` et `retroarch-delivery.yml:103`.
   Les textes des pages libretro (3DS) vont dans `LibretroLocale.values`.
2. Un service `ChangeNotifier` par chantier (modèle `UiRefreshRateService`), préférences
   SharedPreferences `neostation_<feature>_<nom>` ou NSUserDefaults `NeoStation.<Domaine>.<Nom>`
   quand le natif doit lire avant Flutter, JSON atomique sous Application Support pour
   l'état structuré. Aucune colonne SQLite.
3. Les crochets de session uniquement dans `GameLaunchManager.beginSession()` /
   `onGameStarted()` / `_finalize()` ; le harnais `test/game_audio_handoff_test.py`
   est étendu pour chaque nouvelle dépendance du manager, et ajouté aux lanes de
   `retroarch-delivery.yml` (il n'y est pas aujourd'hui).
3 bis. Une nouvelle catégorie du menu Réglages ou un nouvel onglet exigent, en plus des
   dispatchs déjà cités, `_buildContentForSelectedMenu` (+ `GlobalKey<…ContentState>`)
   et `AppTabs.<nom>` + `AppTabs.count` (`app_screen.dart:52-64`) — ✱ vérif.
4. Un bloc `BUILD44x_<CHANTIER>_DELTA` par chantier dans `verify_delivery_reuse.py`,
   vérifié hors ligne (`--offline`) avec `test/delivery_pipeline_test.py` et
   `test/retroarch_baseline_scope_test.py` avant chaque commit.
5. Un document `docs/<chantier>-build44x.md` par chantier (décisions, preuves, limites,
   procédure de validation iPhone) et une entrée AGENTS.md par décision du mainteneur.

## 3. Chantier 1 — AirPlay universel et écrans externes

### 3.1 État constaté

- L'hôte iOS vient du modèle Flutter 3.47.2 : `UIApplicationSceneManifest` avec
  `UIApplicationSupportsMultipleScenes = false` et **un seul rôle**
  `UIWindowSceneSessionRoleApplication` (`Info.plist.tmpl`). Aucun configurateur
  (`configure_dolphin_ios_v2.py`, `build_support.py`, `configure_neoplay_ios.py`) ne
  touche aux scènes ; aucune source du dépôt ne mentionne
  `UIWindowSceneSessionRoleExternalDisplayNonInteractive`. La migration UIScene de
  `flutter_tools` n'injecterait de toute façon que le rôle application.
- Le moteur Flutter ne crée jamais de fenêtre externe : `FlutterSceneDelegate` relaie le
  cycle de vie sans distinguer les rôles ; `FlutterAppDelegate` n'implémente pas
  `configurationForConnectingSceneSession` ; Flutter se dit « pas pleinement multi-scène »
  (`FlutterSceneLifeCycle.mm:128-136`). En revanche un `FlutterViewController` placé dans
  une fenêtre d'une autre scène se dimensionne à **son** écran
  (`FlutterViewController.mm:1507-1521`), et `FlutterEngineGroup` permet un second moteur
  avec `entrypoint` + `libraryURI`.
- Le code AirPlay actuel est informatif (bouton → panneau NeoPlay, `NPAirPlayMonitor`
  observe `UIScreen.mirrored`). `DolphinExternalDisplay` (442) : `UIScreen.screens` +
  `UIWindow.screen` (dépréciés, pragmas `-Wdeprecated-declarations`), déplace la `MTKView`
  et applique une transformation d'échelle sans changer `drawableSize` ; actif seulement
  entre lancement et fin d'un jeu Dolphin ; réglage propre à Dolphin ; jamais validé sur
  iPhone + Apple TV (`docs/dolphin-external-display-build442.md:102-107`).
- Chemins de présentation : libretro (`_metalView` déplaçable, `drawableSize` recalculé
  depuis `view.bounds`, présentateur Metal acceptant toute taille → **rendu à la
  résolution TV possible**, 3DS inclus) ; RPCS3 (couche Metal = couche de la vue racine
  qui porte aussi les commandes, échelle transmise au Core au démarrage) ; ARMSX2 (vue
  créée par le Core) ; Dusklight et KartPad (fenêtre `UIWindow` créée par SDL **dans le
  cœur verrouillé**, boucle suspendue si elle n'est plus clé).
- Un second point d'entrée Dart `subDisplay`/`SecondaryScreen` existe, mais son partage
  d'état (`sub_screen`) est Android seulement et il vit dans `main.dart` verrouillé.
- ✱ vérif. — **iOS 27** : selon la documentation Apple consultée le 12 octobre 2026
  (« Presenting content on a connected display », `UISceneAccessory`,
  `UIViewController.registerSceneAccessory(_:)`), « à partir d'iOS 27, l'app ne reçoit
  une scène `windowExternalDisplayNonInteractive` qu'après avoir enregistré un accessoire
  de scène ; dans les versions antérieures, le système connectait cette scène
  automatiquement ». L'API est iOS 27.0 ; la CI compile avec Xcode 26.3 (SDK iOS 26) :
  non compilable sans Xcode 27 ou appel par sélecteurs à l'exécution. L'enregistrement
  se fait sur le contrôleur de vue le plus haut présenté (menu Flutter et chaque
  contrôleur de jeu). Non vérifié : si ce changement s'applique aux apps liées à un SDK
  antérieur. **La version iOS de l'iPhone du mainteneur doit être consignée.**
- ✱ vérif. — `UIApplicationSupportsMultipleScenes = false` : Apple écrit « UIKit never
  creates more than one scene for your app ». Rien n'établit que la scène externe en est
  exemptée ; si `true` est requis, l'app devient multi-fenêtre sur iPad (orientations
  `~ipad` déclarées) alors que Flutter se dit « pas pleinement multi-scène ». Inconnue à
  lever au premier essai iPhone + Apple TV (deux variantes de configurateur).
- ✱ vérif. — second moteur : `spawnWithEntrypoint:` n'est pas une API publique
  (`FlutterEngine_Internal.h`) et le moteur principal est le moteur implicite du
  storyboard, hors de tout groupe ; le premier moteur d'un `FlutterEngineGroup` est un
  **moteur complet** (`runWithEntrypoint`) : isolat, raster, caches et registre de
  plugins propres, VM partagée par le processus. Coût mémoire = un moteur entier.
- ✱ vérif. — AOT : une bibliothèque Dart jamais importée n'entre pas dans l'instantané
  AOT même annotée `vm:entry-point` (sonde `dart compile aot-snapshot` sur le SDK du
  dépôt : 0 occurrence non importée, 4 importée). Le point d'entrée externe doit être
  importé transitivement depuis `lib/main.dart` par un fichier **non verrouillé** déjà
  importé (comme `secondary_screen.dart` l'est aujourd'hui).
- ✱ vérif. — plugins du second moteur : ne jamais rejouer `GeneratedPluginRegistrant`
  (chaque `registerWithRegistrar:` recrée un pont : RPCS3 ré-acquiert l'escrow JIT,
  Dolphin remplace une file globale ; seul NeoSwap s'en protège). Liste minimale
  explicite : sqflite (`ConfigRepository.getUserConfig()` dans `subDisplay`),
  `video_player` (`SecondaryScreen`), `path_provider`, le canal d'état — avec test.
- ✱ vérif. — NeoPlay utilise aussi `UIScreen.screens` (déprécié iOS 16) pour
  `externalMirroring` ; Dusklight reçoit déjà sa scène UIKit de l'hôte
  (`SDL_PROP_WINDOW_CREATE_WINDOWSCENE_POINTER`), ce qui n'ouvre rien dans ce cycle
  (cœur verrouillé) mais rend un cycle cœur ultérieur envisageable.

### 3.2 Causes

| Défaut | Cause | Statut |
| --- | --- | --- |
| Bandes noires sur l'Apple TV dès le menu | Recopie système d'un écran ≈ 19,5:9 sur 16:9 ; aucune fenêtre NeoStation sur l'écran externe. Pas un défaut de mise en page. | confirmé |
| Le correctif 442 ne change rien au menu ni aux autres moteurs | Instancié après un lancement Dolphin, arrêté à la fin ; réglage et menu propres à Dolphin. | confirmé |
| Le chemin 442 n'est pas démontré fonctionnel | API dépréciées dans un hôte à scènes ; aucun essai appareil. | hypothèse |
| Image Dolphin agrandie, pas rendue en 1080p | Surface fixée par le cœur verrouillé. | confirmé |
| Aucun autre moteur n'a de vue déplaçable prête | Structures décrites ci-dessus. | confirmé |
| Plugins sans filtre de rôle de scène | `connectedScenes` non ordonné. | hypothèse |
| Témoin NeoPlay « recopie détectée » changerait de sens | Dérivé de `UIScreen.mirrored` : quand NeoStation possède la fenêtre externe, iOS cesse la recopie. | hypothèse |

### 3.3 Architecture proposée

Une seule infrastructure hôte « écran externe », une fenêtre par scène externe, dans
laquelle on place soit un second moteur Flutter (menu), soit la vue de rendu du moteur
en cours (jeu), avec une politique de placement commune ; la recopie système reste le
repli (mode Désactivé, moteurs non pris en charge).

1. **Plugin `packages/external_display/`** (Objective-C, `static_framework` recommandé
   pour une assertion IPA simple — pas obligatoire, UIKit résout la classe du délégué
   dans toute image chargée avant `main`, cf. pont libretro dynamique ; patron
   `ui_refresh_rate`) : `NeoExternalDisplaySceneDelegate` (rôle
   `ExternalDisplayNonInteractive`, `UIWindow(windowScene:)`, jamais `makeKey`),
   enregistrement d'accessoire de scène par sélecteurs à l'exécution quand iOS ≥ 27
   (`registerSceneAccessory:` sur le contrôleur présenté, menu et jeux) et repli
   automatique < 27 ; variante de configuration dynamique par ajout de méthode sur le
   délégué d'application (précédent `LibretroOrientation`, `class_addMethod`) si la
   configuration statique Info.plist ne suffit pas ;
   `NeoExternalDisplayCoordinator` (état scène/fenêtre/contenu/mode, `attachRenderHost`,
   `attachFlutterViewController`), `NeoExternalDisplayLayout.h` (politique pure testable
   sur macOS : Automatique / Adapter / Remplir / Format d'origine), protocole
   `NeoExternalRenderHost` adopté par les ponts, préférences NSUserDefaults
   `NeoStation.ExternalDisplay.{Enabled,Mode,MenuOnTV}` avec lecture de repli de la clé
   442, canal `neostation/external_display` + `EventChannel`. Repli « legacy »
   (`UIScreen.screens`) isolé, à trancher au premier essai appareil.
2. **Second moteur Flutter pour le menu** : `lib/external_display/external_display_entrypoint.dart`
   (`@pragma('vm:entry-point')`, hors `main.dart`, importé transitivement par un fichier
   non verrouillé), moteur complet d'un `FlutterEngineGroup` dédié avec registre de
   plugins minimal explicite, écran TV réutilisant `SecondaryScreen` et
   `SecondaryDisplayStateData.toJson()` poussé par un `BasicMessageChannel` (remplace
   `sub_screen` sur iOS), création paresseuse, destruction pendant RPCS3 (mémoire à
   mesurer sur l'appareil).
3. **Ponts** : libretro (surface externe → `drawableSize` à la résolution TV, skin/overlay
   sur l'iPhone) ; Dolphin (adaptateur du protocole, mêmes garanties 442) ; RPCS3
   (conteneur noir + vue Metal en sous-vue, transformation seule, Core et pont NeoSwap
   intacts) ; ARMSX2 (transformation) ; Dusklight/KartPad exclus (fenêtre externe masquée,
   iOS reprend la recopie).
4. **Réglages** : ligne « AirPlay et écran externe » dans Réglages › Général (iOS) après
   « Interface 120 Hz » (le brief demande une section Réglages → AirPlay et écran externe :
   une rangée ouvrant une page est le chemin sans nouvelle catégorie de menu, cf. § 8),
   modes Automatique / Adapter / Remplir (avertissement de recadrage) / Format d'origine,
   « Afficher le menu sur le téléviseur », état de l'écran détecté (`1920×1080`) ;
   `lib/l10n/external_display_locale.dart` ×12, libellés natifs ×12, phrase Apple TV de
   NeoPlay complétée.
5. **Hôte et CI** : `build-utils/configure_external_display_ios.py` (ajoute la
   configuration du rôle externe sans toucher le rôle application), assertion IPA,
   `test/external_display_host_plist_test.py`, workflow `external-display-check.yml`
   (macOS, patron `ui-refresh-rate-check.yml`), tests XCTest avec scène/fenêtre injectées.

### 3.4 Non faisable ou limité

- Supprimer les bandes de la recopie sans fenêtre propre : impossible ; le mode Désactivé
  garde les bandes.
- 4K : l'app ne choisit que parmi `UIScreen.availableModes` ; aucune API n'impose 4K.
- Dusklight/KartPad sur le téléviseur : cœurs verrouillés.
- Rendu natif 1080p pour Dolphin/RPCS3/ARMSX2 : cœurs verrouillés ; libretro seulement.
- Validation CI : impossible (simulateur sans écran externe) ; la bascule recopie →
  fenêtre externe, la latence et la synchronisation A/V restent des vérifications
  iPhone + Apple TV.
- Interaction tactile sur le téléviseur : rôle non interactif par construction.

### 3.5 Risques principaux

Livraison effective de la scène externe par iOS dans cet hôte (régime iOS 27 et valeur
de `UIApplicationSupportsMultipleScenes` : deux hypothèses à lever sur l'appareil avant
d'engager RPCS3/ARMSX2) ; mémoire d'un second moteur Flutter complet pendant
RPCS3/NeoSwap (≈ 0,6 Go libres) ;
charge GPU libretro en 1080p ; plugins sans filtre de rôle ; changement de sémantique du
réglage Dolphin 442 (clé globale) ; régressions tactiles sur RPCS3 après restructuration
du contrôleur.

## 4. Chantier 2 — Nintendo 3DS : langue système, région, données système

### 4.1 État constaté

- Cœur `azahar` (Vulkan) lié à la console `3ds` ; le catalogue ne déclare que deux
  surcharges sans JIT et quatre options verrouillées, **aucun `LibretroCuratedSetting`**
  (`libretro_core_catalog.dart:249-272`) ; la ligne « Réglages du cœur » du menu en jeu
  n'apparaît donc pas.
- Options réellement déclarées par le cœur (source amont `azahar-emu/azahar a5c3d4f8`,
  commit consigné comme « dernier avant le run ») : `citra_is_new_3ds` {New 3DS, Old 3DS,
  Restart required}, `citra_region_value` {Auto, Japan, USA, Europe, Australia, China,
  Korea, Taiwan}, `citra_language_value` {English, Japanese, French, Spanish, German,
  Italian, Dutch, Portuguese, Russian, Korean, Traditional Chinese, Simplified Chinese},
  `citra_use_libretro_save_path`, `citra_use_virtual_sd`. Le défaut déclaré « english »
  étant hors liste, le magasin natif retient la première valeur : **English**.
- Persistance : un seul fichier `Documents/Libretro/Config/Azahar.json` (`{"values":{…}}`)
  écrit par le natif pendant une session ; aucune portée par jeu ; aucune API Dart
  d'écriture (seul `setFrontendSetting` existe, pour `Config/Frontend/<console>.json`) ;
  Dart sait déjà lire ce JSON (vérificateur de BIOS).
- Dossier utilisateur du cœur : `Documents/Libretro/Saves/Azahar/Azahar/` (`config/`,
  `nand/`, `sysdata/`, `sdmc/`, …) ; il lit `sysdata/keys.txt` (pas `aes_keys.txt` à ce
  commit), `sysdata/seeddb.bin`, la sauvegarde CFG
  `nand/data/<id0>/sysdata/00010017/00000000/config` (créée si absente) et les titres
  `nand/<id0>/title/<high>/<low>/content/…`. Remplacements open source embarqués pour
  Mii, pays, mots interdits et police partagée ; **pas** pour les polices CHN/KOR/TWN.
- Le cœur **n'appelle jamais** `RETRO_ENVIRONMENT_GET_LANGUAGE` : la langue de NeoStation
  n'a aucun effet sur la 3DS.
- `citra_language_value` n'est appliquée que par `UpdatePreferredRegionCode`, appelée
  **seulement si `citra_region_value == Auto`**, puis ajustée aux régions acceptées par le
  jeu (`cfg.cpp:1141-1168`). Langue, région et modèle sont consommés au démarrage du
  système : un changement en jeu n'agit qu'après « Redémarrer le jeu » (`retro_reset`)
  ou une nouvelle session. ✱ vérif. : vrai pour langue et région (le reset recrée le
  module CFG) ; **faux pour le modèle** Old/New 3DS — le reset mis en file s'exécute
  avant la relecture des options et `do_load_game` ne relit pas `ParseCoreOptions` :
  nouvelle session requise (ou reprise d'au moins une image avant le redémarrage) ; le
  pied de page `settingsRestartHint` ne suffit pas pour le modèle.
- Vérification possible sur iPhone — ✱ vérif. : **pas par `session.log`** (le cœur
  fixe son filtre de journal à Debug et `HostLog` garde tous les niveaux dans un anneau
  de 200 lignes : les lignes INFO du démarrage sont expulsées même sur une session
  courte) ; preuves fiables = contenu de `Config/Azahar.json`, dossiers
  `Saves/Azahar/Azahar/{config,nand,sdmc,sysdata}` créés, texte du jeu ; les lignes
  `[WARN] System language … Adjusted` passent par `NSLog` (console de l'appareil).
- ✱ vérif. — identité de l'artefact : `48635465…` est le SHA NeoStation qui nomme
  l'artefact ; l'artefact GitHub est **11623625077** (50 832 131 octets, run
  `37945318237`, créé le 2026-10-09T14:36Z, zip buildbot `azahar_libretro.dylib.zip`
  27 474 904 octets, iOS min 14.0). **Rétention 14 jours (`libretro-cores.yml:41`) :
  expiration le 2026-10-23T14:36Z.** Après cette date, `libretro-checks.yml:107` et le
  téléchargement de `retroarch-delivery.yml:453-454` échouent pour **toute** livraison ;
  un nouveau run du buildbot donnera un autre binaire nightly (autre commit Azahar,
  options non garanties) et une nouvelle paire `LIBRETRO_CORES_HOST_SHA/RUN_ID`.
  **Fait le 12 octobre 2026 sur décision du mainteneur** : run `38195212647` (dispatch
  sur `Claude`, HEAD `ba3dc14d`), artefact **11722558457**
  `LibretroCores-ba3dc14d7196429b65f20cdb8573616633dfb8a2`, 50 488 901 octets, digest
  `sha256:5e778e2309229276bdc7eadf1d84d01d3d2e77b95a54b20def6d930efa246b11`, créé le
  2026-10-12T02:18:14Z, **expire le 2026-10-26T02:18:08Z** (à renouveler avant toute
  livraison ultérieure). Les commits amont de `coreSources` n'ont pas pu être re-dérivés
  (dépôts amont inaccessibles d'ici) : les binaires nightly peuvent être plus récents que
  a5c3d4f8 ; la preuve des options 3DS passe par `--cores` sur ce nouvel artefact. Indice favorable, pas une preuve : l'archive buildbot `azahar_libretro.dylib.zip` fait 27 474 904 octets dans les deux runs (même taille le 9 et le 12 octobre), identité binaire non comparée.
- ✱ vérif. — clés AES : au commit a5c3d4f8, `ENABLE_BUILTIN_KEYBLOB` est **ON par
  défaut** (`src/core/hw/default_keys.h` existe, `GetKeysStream` déchiffre le blob si
  `sysdata/keys.txt` est absent) ; sauf désactivation par la recette du buildbot
  (non lisible ici), le cœur épinglé n'a besoin d'aucun `keys.txt` pour les jeux
  chiffrés. L'import de clés est un cas avancé, pas l'étape principale.
- ✱ vérif. — le job `--cores` de `libretro-checks.yml` est le job `dart` (Ubuntu),
  pas le job macOS ; `file_picker` sait présenter un sélecteur de dossier sur iOS mais
  sans portée de sécurité ni signet (d'où `ExternalFolderAccess.pickAndActivateFolder`).
- ✱ vérif. — la requête de lancement porte déjà une couche `optionDefaults` calculée
  en Dart à chaque lancement (`libretro_internal_service.dart:265`, priorité sous la
  valeur stockée) : « langue 3DS = langue de NeoStation » est possible sans écrire
  `Config/Azahar.json` ; réserve : `libretro_core_options_test.py` ne contrôle que les
  littéraux du catalogue, et `id` (indonésien) n'a pas d'équivalent 3DS (repli explicite
  English à afficher).
- Flux réutilisables : `FilePicker.pickFiles`, `ExternalFolderAccess.pickAndActivateFolder`,
  échange de sauvegardes RPCS3 (ZIP validé, limites 2000 entrées / 1 Gio / 512 Mio, refus
  de traversée et de liens, staging + `rename`, copie avant remplacement, restauration).

### 4.2 Causes

| Défaut | Cause | Statut |
| --- | --- | --- |
| Ni langue, ni région, ni modèle réglables | Catalogue sans réglage curé ; aucune voie d'écriture Dart. | confirmé |
| Langue inopérante hors région « Auto » ; ajustée au jeu en Auto | Logique du cœur (`UpdatePreferredRegionCode`, `AdjustLanguageInfoBlock`). | confirmé (sur la source a5c3d4f8) |
| Identité du binaire épinglé ↔ commit a5c3d4f8 non attestée | `identity.json` de l'artefact sans commit ; seul le contrôle de chaînes `--cores` existe. | hypothèse |
| La langue NeoStation ne se répercute pas | Pas de `GET_LANGUAGE` dans le cœur. | confirmé |
| Le vérificateur de BIOS ne voit pas les fichiers 3DS | Emplacements limités à `system`, `system/<sub>`, `gameFolder`. | confirmé |
| `aes_keys.txt` (Citra/Lime3DS) non lu | `KEYS_FILE = "keys.txt"` ; blob de clés intégré non vérifiable. | hypothèse |
| Pas de réglage par jeu | Un fichier d'options par cœur. | confirmé |

### 4.3 Architecture proposée (tout en Dart, aucun natif, aucun cœur)

0. **Préalable — ré-épinglage des cœurs** : avant le 23 octobre 2026, lancer
   `libretro-cores.yml` (`--ref Claude`), consigner le nouvel artefact, puis mettre à
   jour `LIBRETRO_CORES_HOST_SHA/RUN_ID` et `libretro-checks.yml:107`. L'analyse 3DS
   doit viser le binaire qui sera livré : faire ce ré-épinglage **avant** l'étape 1.
1. **Étape 1 obligatoire** : les chaînes `citra_region_value`, `citra_language_value`,
   `citra_is_new_3ds` et leurs valeurs sont contrôlées **durablement** par
   `test/libretro_core_options_test.py` dès que les `LibretroCuratedSetting` existent
   (:111-115) — pas de contrôle « temporaire » (AGENTS.md) ; lancer `libretro-checks.yml`
   (job `dart`, Ubuntu, `--cores`) **avant toute UI** : seule preuve disponible que le
   binaire épinglé déclare ces options (le proxy refuse le blob et le buildbot).
2. **Catalogue** : trois `LibretroCuratedSetting` pour `azahar` (valeurs brutes exactes du
   cœur, libellés traduits ×12) ; verrou optionnel `citra_use_libretro_save_path =
   LibRetro Default` pour garantir que les données restent dans Fichiers › NeoStation ›
   Libretro › Saves. Effet mécanique : le menu en jeu expose aussi ces réglages avec le
   pied de page « après redémarrage ».
3. **`lib/services/libretro_core_option_store.dart`** : lecture/écriture de
   `Config/<library_name>.json` (fusion clé par clé, valeurs inconnues conservées,
   écriture atomique temporaire + `rename`), **refusée quand `isSessionActive()`**.
4. **Page `lib/screens/libretro/libretro_3ds_system_screen.dart`** (« Nintendo 3DS »),
   atteinte par une ligne du `LibretroEngineSettingsPanel` quand `_console?.id == '3ds'`
   (contrat de lignes mis à jour explicitement) — le brief demande
   « Réglages → Nintendo 3DS » : voir § 8 pour l'emplacement. Sélecteurs Langue / Région /
   Modèle ; note « s'applique au prochain lancement ou après Redémarrer le jeu » ;
   avertissement traduit quand une région fixe est choisie (langue ignorée par le cœur),
   avec proposition de remettre la région sur Auto quand l'utilisateur choisit une langue.
5. **`lib/services/libretro_3ds_system_data_service.dart`** : inventaire lecture seule du
   dossier utilisateur Azahar ; assistant d'import (ZIP par signature `PK\x03\x04`,
   dossier via `ExternalFolderAccess`, fichiers isolés) ; détection et validation :
   `config` CFG (0x8000 octets, en-tête plausible), `seeddb.bin` (taille cohérente),
   titres `title/<high>/<low>/content/*.app|*.tmd`, et en option avancée `keys.txt` ou
   `aes_keys.txt` (renommé `keys.txt`, lignes `slot0xNN…=hex`) ; ✱ vérif. : les
   **données uniques de console** d'un dump GodMode9 (`nand/rw/sys/SecureInfo_A`,
   `LocalFriendCodeSeed_B`, `nand/private/movable.sed`, `sysdata/otp.bin`, `mcu.dat`)
   sont aussi lues par le cœur, `SecureInfo_A` peut imposer la région de certains
   titres et ces fichiers identifient la console (vie privée) : l'assistant doit les
   accepter ou les exclure explicitement et les lister dans le plan ; **refus
   explicite** des images brutes (`nand.bin`, `*.img`, `ctrnand*`) avec message
   traduit ; plan affiché (créé/remplacé) ; confirmation ; sauvegarde dans
   `Documents/Libretro/Backups/Azahar/<horodatage>/` (jamais supprimée par l'app) ;
   staging + vérification octet à octet + `rename` ; restauration en cas d'échec ; bouton
   « Restaurer la dernière sauvegarde » ; refus pendant une session.
6. **Vérificateur de BIOS** (optionnel) : nouvel emplacement `saves/<core>/<sub>` pour
   afficher `keys.txt`, `seeddb.bin`, `config` comme optionnels.
7. **Traductions** : nouvelles clés en fin des douze cartes de `LibretroLocale` (titres,
   trois réglages et toutes leurs valeurs, notes, assistant, erreurs typées) ; valeurs
   brutes (« Japan », « keys.txt », chemins) hors traduction.

### 4.4 Non faisable ou limité

Langue avec région fixe (cœur) ; changement à chaud (modèle : nouvelle session) ; suivi
automatique de la langue NeoStation (sauf `optionDefaults` ou pré-écriture explicite de
`citra_language_value`, avec repli English pour `id`) ; conversion d'images NAND
chiffrées ; distribution ou téléchargement de clés/firmware/polices ; réglage par jeu ;
preuve d'effet sur l'iPhone. ✱ vérif. : `preferred_region_chosen` est sérialisé dans
les états de sauvegarde — charger un état pris avant un changement de langue restaure
l'ancienne décision (à documenter dans la page et la procédure iPhone).

## 5. Chantier 3 — Livres et mangas 3D

### 5.1 État constaté

- `LibraryBookCover` (443) : `Stack` de couches plates (planche de dos, papier décoratif,
  trois feuilles `DecoratedBox`, couverture) inclinées par une matrice de perspective ;
  pas de volume, pas de tranche dépendant du nombre de pages, pas de face arrière, un
  gradient fixe ; paramètres `child/selected/rightToLeft/radius` seulement ; utilisée
  **uniquement** dans le hub en ligne (`library_screen.dart:2996`), pas dans la
  bibliothèque locale ni dans « reprendre ».
- Lecteurs : EPUB/TXT en **défilement continu** (un « tour de page » = défilement de
  0,9 écran) ; CBZ/en ligne en `PageView` (glissement, RTL, vertical, pas de double page) ;
  PDF en `PdfViewer` pdfrx 2.4.7 continu (pas de mode page, ni RTL, ni double page, mais
  `layoutPages`, `PdfPage.render` disponibles). Reduce Motion ignoré par les trois
  lecteurs (seule la couverture et un widget le lisent).
- Positions : CFI NeoStation `epubcfi(/6/<n>[idref]!<cfiPath>:<offset>)` (offset propre
  à NeoStation), résolution tolérante, stable aux changements de police (tests
  existants) ; TXT `txt:<bloc>:<car>` ; pages `page:N`.
- Magasin `reading-state.json` (version 1, écriture atomique, clés inconnues ignorées) :
  une position de reprise par clé, marques de chapitres, favoris, **un seul**
  `LibraryReaderSettings` global ; aucun marque-page, aucune clé de traduction « bookmark ».
- Chrome 440 : un seul contrôle « Retour » touchable/VoiceOver/focalisable (20 tests) ;
  lecteurs = couches modales manette (d-pad, A, B, LB/RB, X, Y, Start).
- Couvertures locales ≤ 360 px (`covers/<id>.png`), `pageCount` connu pour CBZ/PDF, null
  pour EPUB/TXT ; CBZ déjà streamé (isolate, une page à la demande, 64 Mio max) ;
  `imageCache` Flutter 100 Mio partagé.
- Capacités du SDK épinglé : `drawVertices` + `ImageShader`, `FragmentShader.setImageSampler`
  (le projet charge déjà des `.frag`), `Picture.toImage`, `RenderRepaintBoundary.toImage`,
  `TextPainter.computeLineMetrics`. `flutter_gpu` écarté (paquet moteur hors lockfile).
- La voie CI « library_covers » (443) n'accepte que la couverture : inutilisable. ✱ vérif. :
  le périmètre « complet » est lui aussi fermé (`verify_delivery_reuse.py --scope full`,
  `verify_tree`) — chaque fichier créé ou modifié, `assets/shaders/page_curl.frag` et les
  tests compris, doit entrer dans un bloc `DELTA` revu, sinon la livraison échoue avant
  le premier test Flutter.
- ✱ vérif. — manette : le hub en ligne n'utilise **pas** `LibraryFocusGamepadLayer`
  (modèle de sélection par index, `selected:` calculé) ; la bibliothèque locale utilise
  le focus Flutter + `onFocusChange` et `_BookTile` n'a pas de paramètre `selected` :
  deux mécanismes à traiter séparément lors de l'intégration du volume.
- ✱ vérif. — mémoire : trois pages décodées au plus (page ± 1), pas cinq ; aucun
  préchargement disque pour les CBZ (`LibraryArchivePageSource.prefetch` est vide) ;
  les lecteurs n'ont aucun `didHaveMemoryPressure` (purge entièrement nouvelle).
- ✱ vérif. — l'indice EPUB `page-progression-direction="rtl"` est déjà extrait à
  l'import (`LibraryLocalBook.rightToLeft`) mais n'est transmis qu'au lecteur de pages ;
  le lecteur EPUB l'ignore. Une clé sémantique `pageNumber` (`{page}`) existe déjà.
  Fournisseurs de métadonnées : `mangaupdates` (pas `mangadex`). Le shader est compilé
  pour la cible `tester` par l'outil ; son exécution en test n'est pas prouvée
  (repli painter justifié par prudence).

### 5.2 Causes

Toutes confirmées sauf mention : couverture perçue comme « image inclinée » (aucun
modèle de volume) ; effet absent de la bibliothèque locale ; aucune animation d'ouverture
(route `MaterialPageRoute` + transition imposée par `main.dart` verrouillé) ; pas de pages
fixes EPUB ; pas de curl ni verso ; pas de marque-pages ; réglages non mémorisés par
livre ; pas de double page ; Reduce Motion ignoré ; mémoire des textures sur grands CBZ
(hypothèse de calcul ≈ 29 Mo par page décodée au maximum) ; couverture trop petite pour
une ouverture plein écran.

### 5.3 Architecture proposée (tout en Dart/Impeller, aucun natif)

1. **Volume** `lib/widgets/library_book_volume.dart` : boîte à 8 sommets projetés, faces
   triées, couverture par `drawVertices` + `ImageShader`, dos = bande de la couverture
   assombrie, tranches de papier, face arrière, éclairage Lambert par face, ombre au sol ;
   épaisseur = `lerp(tMin, tMax, clamp(pageCount, 40, 1200)/1200)` (estimation pour
   EPUB/TXT : question ouverte). `LibraryBookCover` garde son API (7 tests inchangés) et
   gagne `pageCount`/`format`/`spineColor` ; intégration hub, bibliothèque locale et
   « reprendre ». Source de couverture : ordre du brief (stockée → embarquée → source →
   première page → générée) déjà matérialisé à l'import par `_findCover` ; aucune seconde
   requête réseau.
2. **Ouverture animée** `library_book_open_transition.dart` : overlay racine (vol de la
   tuile vers le centre, pivot 15°, couverture à 180°, 520 ms) + `LibraryReaderRoute
   extends PageRouteBuilder` (transition propre, sans toucher `main.dart`) ; couverture
   redécodée à la largeur d'écran ; retour inverse ; Reduce Motion = fondu 200 ms.
3. **Curl** `reader/library_page_curl.dart` + `assets/shaders/page_curl.frag` (sampler
   page pliée / page dessous, verso, ombres) avec **repli painter** (maillage 24×32 +
   `drawVertices`) utilisé si `FragmentProgram.fromAsset` échoue et dans `flutter test` ;
   geste suivi du doigt, deux sens, RTL, complétion/annulation (> 30 % ou vitesse) ;
   `PageView` conservé pour « glissement » et Reduce Motion (35 tests préservés).
4. **Textures** `reader/library_page_textures.dart` : LRU ≤ 5 textures / 48 Mio, `dispose`
   explicite, prefetch ±1, annulation des rendus PDF, purge sur pression mémoire.
5. **EPUB/TXT** `reader/library_reflow_paginator.dart` : pagination `TextPainter` par
   chapitre et typographie, incrémentale (budget par frame), page → `LibraryReflowPosition`
   → CFI inchangé ; textures `Picture.toImage` ; mode défilement conservé.
6. **PDF** : mode page (`PdfPage.render` → textures, curl, double page, RTL) en plus du
   mode défilement/zoom (avec `layoutPages` pour la double page).
7. **Marque-pages** : `LibraryBookmark{id, key, location, fraction, chapterTitle,
   pageIndex, label, createdAt}` sous la clé additive `bookmarks` de `reading-state.json`
   (format 1 conservé ; le chargeur ne relit jamais `version`, donc compatibilité
   ascendante, à couvrir par un test « clés inconnues » qui n'existe pas encore),
   limite 500/titre, jamais évincés pour `local:`/favoris (règle `_progressEvictable`,
   `store:1281-1284`) ; ruban optionnel.
7 bis. **Gate** : bloc `BUILD447_BOOKS_DELTA` dans `verify_delivery_reuse.py` listant
   chaque fichier (sources, `.frag`, `pubspec.yaml`, tests) et mise à jour de
   `test/delivery_pipeline_test.py`.
8. **Barre d'outils** `reader/library_reader_toolbar.dart` : Réglages, Marque-pages,
   Sommaire/Chapitres, Progression (page N/M, %, temps restant), Bibliothèque ; mode
   `auto` (440) ou `always` sans second « Retour » ; réglages en trois sections
   Apparence / Texte / Navigation (style de tour curl/glissement/aucun, double page
   auto/toujours/jamais, première page seule, LTR/RTL, page/vertical) ; réglages par
   livre `bookSettings[key]` prioritaires sur le global, puis indice du contenu.
9. **Accessibilité/performance** : Reduce Motion dans les trois lecteurs, sémantique
   « Page N sur M », compteurs de textures et temps de pagination, traces comparables à
   la 442 pour la validation iPhone.

### 5.4 Non faisable ou limité

Transition globale ou swipe-back (`main.dart`) ; portrait pendant une session libretro ;
pagination « d'éditeur », césure, veuves/orphelines ; polices autres que système ; zoom
libre/sélection/liens en mode curl PDF ; CBR/CB7/MOBI/DRM ; correspondance exacte de
`disableAnimations` avec le réglage iOS (hypothèse) ; interopérabilité des marque-pages
avec d'autres lecteurs ; mesures de fluidité et de mémoire sans iPhone.

## 6. Chantier 4 — Musique d'ambiance « Fairy Lights »

### 6.1 État constaté

- Moteur audio du frontend : flutter_soloud 4.0.12 (décodeurs OGG Vorbis, WAV, FLAC,
  MP3 ; **pas** d'AAC/ALAC), partagé par SFX, lecteur Musique et musique du menu ; iOS :
  SoLoud ne touche pas à la catégorie `AVAudioSession`, les interruptions (appel, Siri)
  sont gérées par le plugin.
- `HomeMusicService` : fichier choisi par l'utilisateur dans `<user-data>/menu_music`,
  boucle entière à volume fixe 0,28, **uniquement quand l'onglet Systèmes est la route
  courante**, arrêt immédiat ailleurs et en arrière-plan ; désactivée par défaut et
  `init()` écrit `false` dès qu'aucun fichier n'existe (la préférence existante ne peut
  donc pas servir de base « absent = activé »). UI dans Réglages › Thèmes.
- Cycle de jeu : `beginSession()` coupe les SFX et met en pause le lecteur Musique mais
  **pas** la musique du menu ; `_finalize()` ne la relance qu'après KartPad ; 2 s de
  présentation (150 ms pour les Ports) ; `appPaused()` **détruit** le moteur SoLoud,
  `appResumed()` le recrée.
- `fadeVolume`, `scheduleStop`, `loopingStartAt`/`setLoopPoint`, `LoadMode.disk`,
  `setProtectVoice` existent dans SoLoud ; le point de boucle ne définit que le **début**,
  la fin est toujours la fin du fichier ; la boucle est sans silence (rembobinage dans le
  même bloc de mixage) ; OGG/FLAC repositionnés à l'échantillon en flux, MP3 par force brute.
- Actifs audio : `assets/sounds/` (5 WAV), aucun OGG/MP3 jamais ajouté ; déclaration non
  récursive.
- **Réseau : opengameart.org répond 403 via le proxy** (page du pack et racine) : la
  licence CC0 annoncée **n'a pas pu être vérifiée** et le fichier n'a pas pu être récupéré.
  Aucune trace antérieure de « Fairy Lights »/« Troubadour » dans le dépôt.
- Légal : crédit = `docs/LEGAL_AND_CREDITS.md` + `THIRD_PARTY_NOTICES.md` (épinglés
  `7f42929e`) + `assets/legal/<Nom>-<Licence>.txt` + `REQUIRED_LEGAL_FILES`.

### 6.2 Causes

Toutes confirmées sauf mention : aucune piste embarquée ; musique non continue entre les
menus (`_mainMenuActive`) ; désactivée par défaut ; aucun fondu ni lien avec le cycle de
jeu ; boucle entière sans point de boucle ; pas de volume ni de bouton d'en-tête ; reprise
non garantie après tous les moteurs (moteur SoLoud détruit en arrière-plan) ; voie Ports
trop courte pour un fondu synchrone ; `LoadMode.memory` coûteux (≈ 53 Mo de float32 pour
2 min 30) ; mixage par-dessus une autre application sans détection (`isOtherAudioPlaying`
non exposé). ✱ vérif. — **réfuté** : « dr_mp3 ignore les informations gapless LAME » est
faux (`dr_mp3.h:3219-3234, 4170-4183, 4556-4557` lit délai et padding et les retire) ;
OGG Vorbis reste recommandé pour les bonnes raisons : repositionnement MP3 par force
brute en mode flux (`LoadMode.disk`), pré-écho au raccord, absence de métadonnées de
boucle. ✱ vérif. : `loadAsset(mode: LoadMode.disk)` copie l'actif dans
`tmp/SoLoudLoader-Temp-Files` à chaque démarrage à froid (3–4 Mo écrits) ; des curseurs
existent déjà hors réglages (lecteur Musique, `LibraryReaderPageSlider`) comme modèle
de volume ; NeoPlay observe `routeChangeNotification` et s'arrête quand son audio local
est actif — interaction avec une voix d'ambiance permanente à vérifier.

### 6.3 Architecture proposée (un gestionnaire global unique sur SoLoud)

Un second moteur AVAudioPlayer/AVAudioEngine est **écarté** : il créerait un second
propriétaire d'`AVAudioSession`, contraire à `docs/IOS_AUDIO_ARCHITECTURE.md`, et
empêcherait fondu/ducking cohérents avec les SFX. Le brief demandait une étude
AVFoundation/AVAudioEngine : conclusion, elle n'apporte que les formats AAC/ALAC et une
fin de boucle à l'échantillon, au prix d'un second arbitre de session ; SoLoud fournit
déjà boucle sans silence, fondu, protection de voix et lecture en flux.

1. `assets/sounds/fairy_lights.ogg` (Vorbis q5–q6, ≈ 3–3,6 Mo pour 2 min 30, **découpé
   pour que la fin du fichier soit la fin de boucle**, intro conservée en tête) +
   `lib/services/ambient_music_track.dart` (asset, fréquence, `loopStartSample`,
   `lengthSamples`, titre, auteur, licence).
2. `lib/services/ambient_music_service.dart` (`ChangeNotifier` + `WidgetsBindingObserver`) :
   `loadAsset(mode: LoadMode.disk)`, `play(looping: true, loopingStartAt:)`,
   `setProtectVoice`, `fadeOutForGame(700 ms)` non bloquant (`fadeVolume` + `scheduleStop`),
   `resumeAfterGame(900 ms)`, `handleEngineTornDown`, `before/afterSharedEngineRestart`,
   ducking ×0,1 comme le lecteur Musique ; `_shouldPlay = enabled && appActive &&
   !suspendedByGame && !launchInProgress && !MusicPlayer.isPlaying && !engineRestarting` ;
   la piste personnalisée de `HomeMusicService` (si présente et activée) remplace la
   piste embarquée.
3. Préférences SharedPreferences : `neostation_ambient_music_enabled` (**absent = true**
   — ✱ vérif. : c'est une décision produit, car les installations existantes, dont la clé
   HomeMusic vaut déjà `false` sans traduire d'intention, entendraient une piste après
   mise à jour ; le brief parle de « nouvelles installations » : question 24 bis),
   `neostation_ambient_music_volume` (absent = 0,28) ; aucune migration.
4. Crochets : `beginSession()` → fondu de sortie juste après `pauseForGame()` ;
   `_finalize()` → reprise après `restoreAfterGameSession()` et après la recréation KartPad ;
   `music_player_service.dart:200` → `handleEngineTornDown()` ; `app_screen.dart` →
   `init()` (pas `main.dart`).
5. UI : `lib/widgets/ambient_music_header_button.dart` (chrome droit avant la cloche,
   modèle `airplay_menu_button.dart` ; les onglets d'en-tête ne sont pas focalisables à la
   manette → l'ON/OFF reste aussi dans Réglages) ; rangées « Musique d'ambiance » et
   « Volume » dans Réglages › Général après SFX (aucun `Slider` n'existe dans les
   réglages : chip à trois niveaux comme la secousse 442, ou nouveau curseur) ; carte
   Thèmes renommée « piste personnalisée » (tokens conservés pour
   `theme_importer_retirement_test.py`).
6. `lib/l10n/ambient_music_locale.dart` ×12 + test, et enregistrement de
   `home_music_locale.dart` (aujourd'hui hors du test de couverture, sans test de
   parité) ; crédit légal (`FairyLights-CC0-1.0.txt`, notices, `REQUIRED_LEGAL_FILES`,
   **et la boîte de dialogue intégrée `legal_credits_dialog.dart` + `legal_credits_locale.dart`**)
   **après** vérification de la licence et re-pin par le mainteneur.
7. Tests : service avec moteur factice ; `game_audio_handoff_test.py` étendu (ordre
   `activated` < reprise, fondu juste après `pause`, KartPad, échec non bloquant) ;
   `ambient_music_asset_test.py` (en-tête Vorbis 44,1 kHz stéréo, granule final =
   `lengthSamples`, point de boucle < longueur, ≤ 4 Mo) ; réécriture explicite de
   `home_music_silent_mode_test.dart` et `audio_policy_service_test.dart` vers le nouveau
   contrat ; câblage explicite de `game_audio_handoff_test.py` et des deux tests
   aujourd'hui hors CI dans les lanes de `retroarch-delivery.yml` ; reprise idempotente
   entre `_finalize()` (qui peut s'exécuter pendant que RetroArch/MeloNX est au premier
   plan, § 2.1) et l'observateur de cycle de vie.

### 6.4 Non faisable ou limité

Vérification de la licence et récupération du pack depuis ce conteneur ; écoute ≥ 20 min
et inaudibilité du raccord (seules des vérifications statiques sont possibles ici) ; fin
de boucle à l'échantillon (piste à découper) ; AAC/M4A/ALAC ; MP3 en flux ; catégorie
`.ambient` imposée (coupée par Sonnerie/Silence et au verrouillage) ; fondu synchrone sur
la voie Ports (150 ms) ; détection de l'audio d'autres applications sans ajout natif ;
taille exacte de l'IPA.

## 7. Chantier 5 — Analyse et nettoyage du stockage

### 7.1 Inventaire des chemins (audit préalable, INV-01 … INV-29)

Légende utilisée (le brief ne la fournit pas ; **à confirmer**, § 11) : A jeux
installés/ROM · B sauvegardes, états, NAND, cartes mémoire · C BIOS, firmware, licences,
fichiers système, pairing/JIT · D caches régénérables · E médias et métadonnées scrapés ·
F temporaires d'import/extraction/staging · G journaux et diagnostics · H contenu
utilisateur hors jeux (livres, skins, enregistrements, musique, fonds, exports) ·
I NeoSwap/mémoire.

| Racine | Contenu | Catégorie / classe |
| --- | --- | --- |
| `Documents/roms/<console>/` | bibliothèque NeoStation | A, jamais |
| `Documents/user-data/` | `config.json`, `data.sqlite` (+wal/shm) ; `app.log(.old)` (rotation 5 Mio) ; `temp/<système>/<archive>/` (extraction pour hachage, dossiers laissés) ; `themes/`, `systems/*.json` ; `media/systems/` (logos), fond, `menu_music/` | jamais ; G ; F ; D ; H jamais |
| `Documents/media/<système>/<type>/<nom>.<ext>` | médias ScreenScraper/Steam/MeloNX (6 types), liés par **convention de nom**, supprimés seulement par `deleteGame` | E, régénérable à coût (quota) ou orphelin |
| `Documents/Diagnostics/` | journaux RPCS3/NeoSwap/StikJIT/ARMSX2/sync/launch/scraper/batterie, jamais supprimés | G, confirmation |
| `Documents/NeoPlay.jsonl`, `armsx2_jit_debug.log` | journaux bornés à la racine | G |
| `Documents/Recordings/Dolphin/*.mp4` | enregistrements | H, confirmation |
| `Documents/Dolphin/`, `Documents/RPCS3/{Import,Export}` | dossiers d'échange visibles dans Fichiers | C/H, jamais / confirmation |
| `Documents/ARMSX2/{Games,BIOS,Saves/Memory Cards,Saves/Savestates,cheats}` | | A / C / B / B / H |
| `Documents/Ports/KartPad/{Games,Saves/NAND,Config,Mods,Logs,Metadata}` + `Runtime/GameData` + `GameData.import-*`/`rollback-*` + journal sans rotation ; `Application Support/KartPad` = liens | | A/B/H ; D ; F ; G |
| `Documents/Ports/Dusklight/{Games,Saves,Config,Mods,Metadata}` ; `tmp/Dusklight` | | A/B/H ; F |
| `Documents/Libretro/{System,Saves,States,Config,Cheats,Skins,SkinFavorites.json,Logs}` | BIOS (jamais écrasés) ; sauvegardes/états ; options ; skins (+ staging purgé par âge) ; journaux bornés | C ; B ; H ; H/F ; G |
| `Documents/Library/{Books,Downloads,Sources}` | livres ; `Sources` **jamais nommé** | H ; jamais |
| `Application Support/NeoStation/RPCS3/Data` | `dev_hdd0/game`, `games/*` (A) ; `savedata` (B) ; `exdata/*.rap`, `dev_flash` (C) ; `savestates` (B) ; `dev_hdd0/tmp` (F) ; `games.yml` | voir classes |
| `Application Support/NeoStation/RPCS3/Cache` | objets LLVM PPU/SPU ; ✱ vérif. : borné à **4 Gio par le Core** (`embedded-core.patch:13490-13491`, si la routine amont s'exécute sur iOS — non vérifié), **jamais purgé par NeoStation** ; le Core vide aussi `dev_hdd0/tmp` | D, régénérable à coût élevé |
| `Data/dev_hdd1` et autres racines VFS (`dev_usb000`, `dev_bdvd`, mises à jour `USRDIR`) | ✱ vérif. : absents de l'inventaire initial ; `dev_hdd1` = disque cache PS3 écrit par les jeux (souvent plusieurs Go), chemin déduit de l'amont (sources canoniques hors dépôt) | D / A |
| `Application Support/NeoStation/RPCS3/{Imports/*.PUP,SaveBackups,RapBackups}` | résidu possible ; copies avant remplacement | F ; H confirmation |
| `Application Support/NeoStation/Dolphin/{Library/gc,wii}` | **bibliothèque Dolphin cachée** (copies hors Fichiers) | A |
| `Application Support/NeoStation/Dolphin/User/{Config,GC,Wii,StateSaves,Load/Textures,Dump,GameSettings}`, `ShaderCache`, `Logs/dolphin-*.jsonl` (un par lancement), `dolphin-persistent.jsonl` (sans borne) | | C/B/H/D ; D ; G |
| `Application Support/Library/{local-index.json,covers/,catalogs.json,source-health.json,reading-state.json}` | | jamais ; D ; jamais |
| `Application Support/<pairing>`, `StikJIT/` | pairing, images DDI | C, jamais |
| `Caches/Libretro/{SkinCache,Content/<contenu>,SkinDownloads,SkinInspection,*.json}` | extraction ZIP effacée seulement au prochain chargement du même contenu | D ; F |
| `Caches/Library/{library_http (96 Mio LRU), library_images (256 Mio LRU)}` | | D |
| `Caches/NeoSwap-v1`, `NeoSwapShaderStorage-v1` | fichiers créés puis **`unlink`** : non listables | I, jamais |
| `tmp/` | **copies file_picker de chaque fichier choisi (ISO/ROM/PKG) jamais supprimées** — ✱ vérif. : **deux** copies par sélection (`asCopy: true` : copie système dans `tmp/<bundle-id>-Inbox/` — emplacement iOS documenté, hypothèse — puis recopie du plugin dans `tmp/<nom>` sans suppression de la première), helpers JIT, SoLoud (copie de l'actif à chaque démarrage), FramePacing, shaders ARMSX2 ; résidus `.part` (KartPad/Dusklight Games, exports RPCS3), `background.importing<ext>` | F |
| `Application Support/*.ttf` (google_fonts), `Caches/<bundle-id>` (NSURLCache du pack de shaders ARMSX2), `Documents/RPCS3-core-load-stderr.log`, `Diagnostics/jit_launch_debug.txt`, `armsx2_launch_debug.txt` | ✱ vérif. : hors de l'inventaire initial | D / G |

Pas d'App Group (entitlements NeoSwap) ; conteneurs des `.appex` illisibles ; dossiers liés
par signet (RetroArch, bibliothèques externes) hors conteneur, lecture seule. ✱ vérif. :
les clés Files de l'Info.plist sont bien écrites par la CI (`configure_dolphin_ios_v2.py`,
étape `build_support.py configure`), pas seulement supposées ; aucun `CFBundleDocumentTypes`
(pas de `Documents/Inbox` par « Ouvrir dans »). Chemins de suppression existants à
connaître et **à ne jamais appeler** depuis l'outil : `FilePicker.clearTemporaryFiles()`
(toute la racine `tmp/`), `UserDataLocationService` (migration, inactive sur iOS),
`SqliteService.resetDatabase()` et la remise à zéro du fichier verrouillé ; effets de
démarrage de `main.dart` (thèmes retirés :204-227, fichiers iFly et déplacement des
diagnostics :246-306) = exceptions connues hors périmètre. Trois parcours existants
suivent les liens (`config_service.dart:607` verrouillé, `user_data_location_service.dart:310,333`) ;
le nouveau scanner reste en `followLinks: false`.

### 7.2 Causes de l'écart « 40 Go pour 20 Go de jeux »

| Cause | Statut |
| --- | --- |
| Les imports **copient** sans jamais supprimer les copies faites par `file_picker` dans `tmp/` (deux par sélection : `-Inbox` système + copie du plugin ; la seule suppression existante est `FilePicker.clearTemporaryFiles()` dans l'import de sauvegardes RPCS3, qui vide toute la racine) ; Dolphin copie dans une bibliothèque cachée ; KartPad extrait `Runtime/GameData` : un même jeu peut exister trois ou quatre fois. | copie : confirmé ; part dans l'écart : **hypothèse** (à mesurer sur l'iPhone) |
| Orphelins du scanner verrouillé (ligne `user_roms` supprimée, `user_screenscraper_metadata` et `Documents/media` conservés) et de `removeRomFolder`. | confirmé |
| La suppression d'un jeu laisse sauvegardes/états/caches des moteurs (par conception pour les sauvegardes). | confirmé |
| `RPCS3/Cache` (objets LLVM par titre) jamais purgé par NeoStation, même après suppression du titre (borné à 4 Gio par le Core si sa routine s'exécute sur iOS). | confirmé (ordre de grandeur non mesuré) |
| Journaux Dolphin et KartPad sans borne. | confirmé |
| Résidus de staging après arrêt brutal (`*.PUP`, `GameData.import-*`, `Caches/Libretro/Content`). | hypothèse |
| Dossiers `user-data/temp/<système>/…` laissés vides par la voie MD5 (`temp_rom.7z` n'y reste qu'après une exception) ; doublons laissés par le déplacement de bibliothèque ; copie RetroArch additive (BIOS/sauvegardes en double). | confirmé |
| `du` sous-estime pendant une session (fichiers NeoSwap délinkés). | confirmé |

### 7.3 Architecture proposée (tout en Dart, lecture seule par défaut)

- `lib/services/storage/storage_roots.dart` : registre déclaratif des racines (jamais de
  chemin absolu codé), règles relatives → catégorie, classe de suppression, ancre
  d'orphelin. ✱ vérif. : **sans effet de bord** — plusieurs résolveurs existants créent
  des dossiers (`Rpcs3InternalService.dataDirectory/cacheDirectory`,
  `ConfigService.getDefaultIOSRomsFolder`, `LibretroInternalService.ensureLayout`,
  `filesWorkspaceDirectory` qui réécrit un README) ; le registre recompose les chemins
  (`path.join` sur `getApplicationDocumentsDirectory()`/`getApplicationSupportDirectory()`/
  `getApplicationCacheDirectory()`) ou n'appelle que des accesseurs sans création
  (`rootDirectory()` de Dolphin/KartPad/Dusklight/ARMSX2/Libretro), et traite une racine
  absente comme 0 octet. Primitives réutilisables : `LibraryDiskCache.sizeBytes()`,
  `LibraryImageCache.cacheSizeBytes()`, `Rpcs3SaveExchangeService.formatBytes`,
  `NeoAssetsService.clearThemeCache`, `LibraryHttp.clearCache`.
- `storage_scanner.dart` : parcours type `du` dans `Isolate.run`, `followLinks: false`,
  liens comptés à part, `.icloud` à 0, erreurs d'accès signalées, annulation, progression,
  garde contre les boucles ; sortie agrégée par nœud/catégorie/racine.
- `storage_categorizer.dart` : classes **jamais** (A, B, C, H, I, index/DB/config,
  `Sources`), régénérable avec coût, temporaire si inactif, confirmation.
- `storage_orphan_detector.dart` : médias scrapés (convention de nom via
  `FileProvider.stripRomExtension` et les quatre variantes de `game_repository.dart:166-170`),
  métadonnées (LEFT JOIN), Saves/States libretro, états Dolphin (listés, non attribués),
  savedata/savestates RPCS3 par TITLE_ID avec validation `PARAM.SFO`, savestates ARMSX2
  par serial, covers de livres hors `local-index.json`, doublons de jeux par nom + taille
  (hachage sur demande seulement) ; **jamais de suppression automatique**.
- `lib/repositories/storage_maintenance_repository.dart` : `previewOrphanMetadata()`,
  `deleteOrphanMetadata(keys)` transactionnel sur les clés prévisualisées,
  `integrity_check`, `wal_checkpoint` ; ✱ vérif. : `VACUUM INTO '<sauvegarde>'`
  (sqlite3 3.5.0, liaison FFI sur le SQLite du système iOS) plutôt qu'une copie brute
  d'une base en mode WAL, hors transaction, sauvegarde inventoriée ; **jamais de
  `DELETE` sur `user_roms`**.
- `storage_cleanup_planner.dart` + `storage_deletion_manager.dart` : plan par niveau ;
  re-stat avant suppression (ignoré si modifié), refus des liens, canonicalisation
  (`resolveSymbolicLinks`, `isWithin`), liste blanche des racines résolues, refus des
  racines elles-mêmes, de Documents, des dossiers de bibliothèque, du dossier lié externe,
  de `Library/Sources`, de `Caches/NeoSwap*`, de `dev_flash`/`exdata`/`System`/`BIOS` ;
  suppression fichier par fichier ; ENOENT toléré, EACCES remonté ; **garde de session**
  (`GameLaunchManager.isActive`, mutations RPCS3, marqueur Dolphin, journal libretro sans
  END) avant et pendant ; journal `Documents/Diagnostics/storage-cleanup-<date>.jsonl`.
- Trois niveaux : 1 « Sûr » (temporaires seulement, aucune ligne de base, aucune donnée
  de jeu) ; 2 « Régénérable » (+ caches à coût, médias/métadonnées orphelins, journaux
  anciens, avec avertissements RPCS3/quota) ; 3 « Avec confirmation détaillée » (classe
  confirmation, cochée une à une, jamais présélectionnée, deux chemins pour les doublons).
- `storage_report.dart` : export JSON/texte « sans données personnelles » (agrégats,
  compteurs, aucun nom de jeu/livre/utilisateur, chemins relatifs sans UUID, jamais
  « Sources ») et mode « détaillé » opt-in ; partage via `share_plus`.
- Écrans `lib/screens/storage/{storage_audit_screen,storage_cleanup_preview_screen}.dart`
  (modèle BIOS checker : scan à l'ouverture, au retour au premier plan, bouton « Analyser
  à nouveau », erreur conservée), cinquième ligne iOS de Réglages › Outils, catalogue
  `lib/l10n/storage_locale.dart` ×12 (~70 clés).
- Correspondance avec le brief : 5.19 analyse-avant-suppression = aperçu obligatoire ;
  5.20 données protégées = classe « jamais » testée (ROM, ISO, jeux installés,
  sauvegardes, états, cartes mémoire, BIOS, firmware, NAND, licences, clés, livres,
  marque-pages, skins, réglages, NeoSwap, données non identifiées) ; 5.21 maintenance
  légère = **chantier séparé** (suppression de la copie `tmp/` après import vérifié, si
  et seulement si le chemin est sous `getTemporaryDirectory()`, et rotation des journaux
  Dolphin/KartPad) — jamais au démarrage (`main.dart` verrouillé, AGENTS.md) ; 5.22
  prévention = registre des temporaires avec expiration dans le planificateur ; 5.23
  réconciliation iOS = somme logique affichée avec explication de l'écart (blocs APFS,
  `tmp` purgé par iOS, NeoSwap délinké, placeholders iCloud) ; 5.24 tests A–J = tests
  scanner, catégoriseur, détecteurs (base en mémoire + arbres temporaires), dépôt de
  maintenance, gestionnaire de suppression (lien sortant, racine, modifié-depuis-aperçu,
  EACCES, ENOENT, session active, journal), rapport, écran.

### 7.4 Non faisable ou limité

Inode/liens physiques/taille allouée/espace libre : impossibles en `dart:io` (`FileStat`
sans inode ni blocs, pas de `statvfs`) — ✱ vérif. : mais **possibles via `dart:ffi`**
(`lstat`, `statvfs` par `DynamicLibrary.process()`, précédent `packages/flutter_7zip`,
aucune empreinte native touchée ; disposition des structures arm64 à déclarer et à
valider sur l'appareil) ou par un plugin ; fichiers NeoSwap délinkés ; conteneurs des
extensions ; chiffre exact des Réglages iOS ; prévention des orphelins à la source
(scanner verrouillé) ; attribution jeu↔état Dolphin ; disposition interne de
`RPCS3/Cache` par titre ; nettoyage automatique au démarrage ou en arrière-plan
(AGENTS.md) ; preuve des tailles réelles sans iPhone ; `Logs/session.log` libretro :
trois fichiers au plus, taille non bornée (à vérifier).

## 8. Cohérence entre systèmes et placement dans l'interface (chantiers 6 et 7)

- **Un seul gestionnaire par domaine** : `NeoExternalDisplayCoordinator` (écran externe),
  `AmbientMusicService` (audio), `StorageCleanupPlanner`/`StorageDeletionManager`
  (stockage), `LibretroCoreOptionStore` (options 3DS), `LibraryReadingStore` étendu
  (marque-pages). Chacun est injectable et testé avec un double.
- **Isolation des moteurs** : les ponts n'adoptent que des protocoles hôte
  (`NeoExternalRenderHost`) ; aucun cœur, helper JIT ni fichier `native/` du manifeste
  n'est touché ; le pont NeoSwap reste intact.
- **Session** : AirPlay et musique s'accrochent aux mêmes trois points de
  `GameLaunchManager` ; le stockage et l'import 3DS refusent toute écriture pendant une
  session (mêmes signaux).
- **Emplacements demandés par le brief et chemin retenu** :
  - « Réglages → AirPlay et écran externe » : rangée dans Réglages › Général (iOS) ouvrant
    une page dédiée, plutôt qu'une nouvelle catégorie du menu Réglages (qui exige d'éditer
    quatre dispatchs positionnels de `NewSettingsScreen`) — **à confirmer** ;
  - « Réglages → Nintendo 3DS » : ligne « Nintendo 3DS » dans le panneau Émulateurs du
    système 3DS (chemin cohérent avec la Build 440) et, si souhaité, la carte 3DS de
    l'onglet Consoles — **à confirmer** ;
  - « Réglages → Général → Musique d'ambiance » + bouton ON/OFF dans l'en-tête du menu ;
  - « Réglages → Outils → Analyse et nettoyage du stockage » : cinquième ligne iOS.
- **Traductions** : quatre nouveaux catalogues (`external_display`, `ambient_music`,
  `storage`, + clés `LibraryReaderLocale`) et extension de `LibretroLocale` ; toutes les
  nouvelles chaînes ×12 avec tests de parité ; jamais de repli anglais.
- **Jamais** : aucun bouton, lien, chemin ou message vers `Library/Sources` (l'outil de
  stockage l'agrège sous « Bibliothèque » sans le nommer).

## 9. Ordre des phases et builds proposés (chantier 8)

Le brief fixe l'ordre audit → AirPlay → 3DS → livres → musique → stockage → tests de
régression → compilation → rapport. AGENTS.md impose une seule candidate clairement
identifiée par cycle, et aucune IPA pour une hypothèse non vérifiée.

Proposition :

| Phase | Contenu | Gate avant de passer à la suivante |
| --- | --- | --- |
| 0 | Décisions du § 11 (dont version iOS de l'iPhone) ; **ré-épinglage des cœurs libretro avant le 23 octobre** (`libretro-cores.yml`, nouvelle paire `LIBRETRO_CORES_HOST_SHA/RUN_ID`) ; documents de décision ; contrôle `--cores` des options 3DS par dispatch | `libretro-checks.yml` vert sur le nouvel artefact avec les clés 3DS |
| 1 | AirPlay (plugin, configurateur, second moteur, ponts, réglages, 12 langues) | `external-display-check.yml`, syntaxe iPhone des ponts, `delivery_pipeline_test.py`, baseline |
| 2 | 3DS (catalogue, store, page, import, 12 langues) | `libretro-checks.yml` (+ `--cores`), tests Dart |
| 3 | Livres (magasin → volume → ouverture → curl CBZ → PDF → EPUB → barre/marque-pages → accessibilité) | `flutter test test/library_*_test.dart`, couverture 12 langues |
| 4 | Musique (service, crochets, UI, 12 langues ; actif et crédit **seulement** après fourniture du fichier et preuve de licence) | `launch-ui-checks.yml`, `game_audio_handoff_test.py`, `legal-compliance-check.yml` |
| 5 | Stockage (registre → scanner → détecteurs → suppression → écrans → CI) | tests `storage_*`, baseline, couverture 12 langues |
| 6 | Régression complète : baseline 419, `delivery_pipeline_test.py`, `verify_delivery_reuse.py --offline`, tous les tests Dart/Python listés, `flutter analyze` | tout vert sur un SHA unique |
| 7 | **Une** IPA candidate (numéro inédit, par-dessus la 446) par `retroarch-delivery.yml --ref Claude` | SHA, run, artefact consignés |
| 8 | Rapport technique final (chantier 9) et protocole de validation iPhone/Apple TV | — |

Variante à décider (§ 11) : une IPA intermédiaire après la phase 1 pour vérifier tôt sur
l'iPhone que iOS livre bien la scène externe (l'hypothèse la plus structurante de tout le
chantier AirPlay), avant d'engager RPCS3/ARMSX2.

## 10. Vérification contradictoire

Six vérificateurs indépendants ont reçu pour consigne de **réfuter** chaque constat des
audits en relisant les sources (HEAD `fa3aba11`, 12 agents au total, 949 lectures et
commandes, 0 échec). Bilan : 114 constats confirmés ligne par ligne, 49 affirmations
réfutées ou nuancées, 49 omissions, dont **trois bloquantes** et quatorze importantes.
Toutes sont intégrées ci-dessus (« ✱ vérif. ») ; aucun des six verdicts n'invalide la
cause racine d'un chantier ni une architecture proposée, mais chacun impose des
corrections avant de figer un plan.

| Chantier | Verdict | Réfutations et omissions déterminantes |
| --- | --- | --- |
| AirPlay | Base utilisable ; cause racine démontrée ; citations exactes. | **Bloquant** : régime iOS 27 (`UISceneAccessory`, API iOS 27.0 non compilable avec Xcode 26.3 ; version iOS de l'iPhone à consigner). Important : `UIApplicationSupportsMultipleScenes=false` (« jamais plus d'une scène » selon Apple) à lever sur appareil ; second moteur = moteur complet (pas de `spawn` public) ; point d'entrée à importer transitivement depuis `main.dart` (sinon absent de l'AOT) ; registre de plugins minimal (jamais `GeneratedPluginRegistrant`). Mineur : plancher Runner iOS 18.0, `static_framework` optionnel, chemins `lib/services/game/`, risque KartPad surévalué, NeoPlay aussi sur `UIScreen.screens`. |
| 3DS | Globalement solide ; copie amont vérifiée = commit a5c3d4f8. | **Bloquant** : expiration de l'artefact de cœurs épinglé le 2026-10-23 (toute livraison). Important : modèle Old/New non appliqué par « Redémarrer le jeu » ; preuve par `session.log` non fiable ; `keys.txt` optionnel (blob intégré ON par défaut) ; données uniques de console (SecureInfo_A, movable.sed, otp.bin…) à traiter ; couche `optionDefaults` existante ; identité du binaire toujours non prouvée hors CI. Mineur : job `--cores` = Ubuntu ; `file_picker` sait choisir un dossier sans portée de sécurité ; `preferred_region_chosen` dans les états ; `id` sans équivalent ; contrôle `--cores` durable, pas temporaire. |
| Livres | Base utilisable ; état des lieux exact à la ligne près. | **Bloquant** : jeu fermé `DELTA` à inscrire au plan (sinon échec avant tout test). Important : mécanismes manette distincts hub/locale ; indice EPUB `page-progression-direction` ignoré par le lecteur EPUB. Mineur : 3 pages décodées (pas 5), pas de préchargement disque CBZ ; `mangaupdates` ; `_progressEvictable` ; gradient 443 partiellement dépendant de l'ouverture ; shader compilé pour `tester`, exécution non prouvée ; clé `pageNumber` existante ; aucun `didHaveMemoryPressure` ; repli anglais de `forLocale` (seule la parité protège). |
| Musique | Base utilisable ; architecture corroborée ligne par ligne. | **Réfuté** : « dr_mp3 ignore le gapless LAME » (il le gère) — OGG conservé pour d'autres raisons. Important : boîte de dialogue légale intégrée à mettre à jour ; `game_audio_handoff_test.py` absent de `retroarch-delivery.yml`, deux tests hors de tout workflow ; `home_music_locale.dart` hors du test de couverture. Mineur : copie de l'actif dans `tmp` à chaque démarrage ; « absent = activé » pour les installations existantes = décision produit ; `_finalize()` pendant RetroArch au premier plan ; KartPad via `DonorAudioSession.h` ; curseurs existants ; NeoPlay et `routeChangeNotification` ; lignes citées décalées. |
| Stockage | Base utilisable ; inventaire et architecture confirmés. | Important : `FilePicker.clearTemporaryFiles()` vide toute la racine `tmp` (danger latent) ; double copie du sélecteur (`-Inbox` + plugin) ; `dev_hdd1` et racines VFS absents ; `RPCS3/Cache` borné à 4 Gio par le Core ; résolveurs de racines à effets de bord ; `VACUUM INTO` au lieu d'une copie brute ; `dart:ffi` possible pour inode/blocs/espace libre. Mineur : clés Files écrites par la CI ; trois parcours existants suivent les liens ; `temp_rom.7z` seulement après exception ; `.icloud`, citations décalées, risque NSFileProtection à retirer, effets de démarrage de `main.dart` à lister, résidus `.part`, journaux omis, polices google_fonts, primitives existantes, chemins de suppression à ne jamais appeler, NSURLCache, listes de tests explicites. |
| Fondations | Socle utilisable ; quasi-totalité des citations exactes. | **Bloquant** (pour le rapport de l'auditeur, résolu ici) : rebaser sur `fa3aba11`/Build 446 et réconcilier avec ce document. Important : modèle audio à deux régimes ; fermeture automatique ≈ 4 s de `ios_direct_launch` ; `paths:` de libretro-checks ; doubles du harnais audio ; assertions de `delivery_pipeline_test.py` sur le job checks ; `AppTabs.count`/`_buildContentForSelectedMenu` ; écart légal préexistant (cœurs libretro, rcheevos, MoltenVK) ; 18 catalogues hors couverture ; `setMainMenuActive` appelé depuis un fichier verrouillé ; liste complète de « Configure release host ». Mineur : `zh_Hant_TW` au démarrage (hypothèse, `main.dart` verrouillé) ; hypothèse `MapLocale('zh_Hant')` confirmée ; six chaînes anglaises seulement interdites ; `settings_title.dart` ; sqlite3 = FFI sur le SQLite système ; Dolphin/RPCS3 sans `sessionEnded`. |

Ce qui n'a pas pu être vérifié ni par les auditeurs ni par les vérificateurs, et reste
une hypothèse jusqu'à l'essai sur l'appareil : la livraison effective de la scène
externe (iOS 26/27, valeur de `UIApplicationSupportsMultipleScenes`), l'identité exacte
du binaire azahar épinglé, la part de `tmp/` dans l'écart de stockage, l'exécution d'un
shader de fragment dans `flutter test`, et la routine de plafonnement du cache RPCS3 sur
iOS.

## 11. Décisions demandées au mainteneur

Les recommandations entre parenthèses sont celles de l'audit ; sans réponse, elles seront
appliquées et consignées.

**Réponses du mainteneur (12 octobre 2026)** : 4 quater — version iOS inconnue, les deux
régimes sont couverts et la version sera consignée à la première validation ; 4 bis —
ré-épinglage des cœurs immédiat ; 21 à 25 — **chantier musique reporté** (fichier et
licence inaccessibles d'ici) ; 1 — **une seule IPA** en fin de cycle. Les autres
recommandations s'appliquent sauf avis contraire (consigné dans AGENTS.md).

**Transversal**
1. Nombre de builds : une seule IPA en fin de cycle (recommandé par AGENTS.md) ou une IPA
   intermédiaire après AirPlay pour lever tôt l'hypothèse de la scène externe ?
2. Préférences nouvelles en SharedPreferences/NSUserDefaults/JSON (seule voie sans
   dé-verrouiller `sqlite_service.dart`) : accepté ? (oui)
3. Filtres `branches: [experimental]` des workflows : les passer à `Claude` dans ce cycle,
   ou conserver le fonctionnement par dispatch ? (conserver, dispatch obligatoire)
4. `test/import_memory_candidate_scope_test.py` (inactif, épinglage historique) : retirer,
   remettre en service ou ignorer ? (ignorer dans ce cycle ; re-pin nécessaire pour le
   crédit musical)
4 bis. **Ré-épinglage des cœurs libretro avant le 23 octobre 2026** (artefact 11623625077
   expirant ; bloque toute livraison ensuite) : lancer `libretro-cores.yml --ref Claude`
   maintenant, avant le chantier 3DS, et accepter que le binaire azahar change de
   nightly ? (oui, tout de suite ; les options 3DS seront prouvées sur le nouveau binaire)
4 ter. `FilePicker.clearTemporaryFiles()` dans l'import de sauvegardes RPCS3 vide toute la
   racine `tmp/` : le restreindre aux copies du sélecteur dans le chantier « maintenance
   légère » ? (oui)

**AirPlay**
4 quater. **Version iOS de l'iPhone de test** (26 ou 27 ?) : elle décide du régime de
   scène externe (automatique < 27, accessoire de scène ≥ 27, API non compilable avec le
   Xcode de la CI → appel par sélecteurs). Sans cette information, le chantier AirPlay ne
   peut pas être planifié de façon fiable.
5. Contenu du téléviseur hors jeu : menu complet par second moteur Flutter (coût mémoire),
   vue TV simplifiée (patron `SecondaryScreen`), ou jeux seulement ? (vue `SecondaryScreen`
   par second moteur, détruit pendant RPCS3)
6. Mode par défaut Automatique (menu plein écran, jeu Adapter) et réglage global
   remplaçant la ligne Dolphin par jeu de la 442 ? (oui)
7. Dusklight/KartPad : recopie système avec bandes acceptée pendant ces jeux ? (oui, seule
   option sans cœur)
8. libretro : rendu à la résolution du téléviseur dès ce cycle, ou transformation seule
   comme Dolphin ? (résolution TV, repli transformation si la charge GPU le justifie)
9. NeoPlay : diffusion vers Windows/Chromecast autorisée quand NeoStation affiche sa propre
   fenêtre AirPlay ? (non, inchangé)

**3DS**
10. Région + langue : offrir les deux avec l'avertissement « langue ignorée hors Auto » et
    proposition de repasser en Auto, ou forcer Auto et masquer la région ? (les deux)
11. Exposer le modèle Old/New 3DS ? (oui) Verrouiller `citra_use_libretro_save_path =
    LibRetro Default` ? (oui)
12. Import : fichiers système seulement, ou aussi les titres NAND (`title/0004009b/…`,
    requis pour les polices CHN/KOR/TWN) ? Accepter `aes_keys.txt` renommé ? (titres
    inclus avec limites de taille ; `aes_keys.txt` accepté en option avancée)
12 bis. Données uniques de console d'un dump GodMode9 (`SecureInfo_A`,
    `LocalFriendCodeSeed_B`, `movable.sed`, `otp.bin`, `mcu.dat` : identifient la console,
    `SecureInfo_A` peut imposer la région) : les importer sur choix explicite, ou les
    exclure toujours ? (exclues par défaut, case explicite « données de console »)
13. Emplacement : panneau Émulateurs du système 3DS, carte 3DS de l'onglet Consoles, ou les
    deux ? (panneau Émulateurs)

**Livres**
14. Épaisseur pour EPUB/TXT et titres en ligne : estimation (taille/1800) ou fixe ?
    (estimation bornée)
15. Volume 3D aussi dans le hub en ligne ? (oui, épaisseur fixe)
16. Style de tour par défaut : curl partout (hors vertical) ? (oui) Double page : auto en
    paysage, première page seule ? (oui) PDF : deux modes avec bascule ? (oui)
17. Barre d'outils : automatique par défaut avec option « toujours visible » ? (oui)
18. Shader de fragment `page_curl.frag` accepté comme actif de build (avec repli painter) ?
    (oui)
19. Manette : Y = marque-page partout, « Ajuster » PDF déplacé sur le clic du stick droit ?
    (oui)
20. `reading-state.json` : version 1 conservée avec clés additives ? (oui)

**Musique**
21. **Fourniture du fichier « Fairy Lights » et de la preuve de licence** (capture de la
    page, LICENSE du pack, SHA-256 du fichier) par une machine ayant accès à
    opengameart.org — le conteneur ne peut ni vérifier ni télécharger. Sans cela, le
    service est livré sans actif embarqué (piste personnalisée seulement) et le crédit
    n'est pas ajouté.
22. Piste personnalisée actuelle (Réglages › Thèmes) conservée comme remplacement
    prioritaire ? (oui)
23. Couper l'ambiance quand une autre application joue (`isOtherAudioPlaying`, ajout Swift
    minime) ? (non dans ce cycle)
24. Volume : trois niveaux (chip 442) ou curseur (modèle du lecteur Musique) ? (chip)
    Défaut 0,28 ? (oui) Fondus 700 ms / 900 ms, reprise à la position mémorisée ? (oui)
24 bis. « Activée par défaut » : pour les nouvelles installations seulement (clé posée à
    la première ouverture après mise à jour = conserver le silence actuel), ou aussi pour
    les installations existantes ? (nouvelles installations seulement, conformément au
    brief ; les installations existantes gardent le silence jusqu'à activation)
25. Voie Ports : accepter un fondu qui chevauche le démarrage natif (150 ms) ? (oui)

**Stockage**
26. Légende A–I : la correspondance du § 7.1 est-elle la bonne ?
27. Suppression explicite et prévisualisée des lignes orphelines de
    `user_screenscraper_metadata` : compatible avec « aucune réparation automatique » ?
    (oui, car explicite, prévisualisée, transactionnelle et journalisée ; sinon compteur
    seulement)
28. `RPCS3/Cache` en niveau 2 (recompilation LLVM, impact JITPROF 444) ou « jamais »
    jusqu'aux captures iPhone ? (niveau 2 avec avertissement)
29. Mesure fine : Dart pur (tailles logiques), **`dart:ffi` dans un fichier Dart**
    (`lstat`/`statvfs` : blocs alloués, liens physiques, espace libre, aucune empreinte
    native touchée, à valider sur l'appareil), ou plugin natif `storage_stat` ? (`dart:ffi`
    pour l'espace libre et la taille allouée, avec repli tailles logiques)
30. Export : agrégats par défaut, mode détaillé opt-in ? (oui)
31. Chantier séparé « maintenance légère » (suppression de la copie `tmp/` après import,
    rotation des journaux Dolphin/KartPad) autorisé dans ce cycle ? (oui, après l'outil de
    mesure)
32. Journaux Dolphin conservés : 10 ? `Documents/Diagnostics` supprimable en niveau 3 ?
    (10 ; Diagnostics en niveau 3 seulement)

## 12. Ce qui ne sera jamais présenté comme opérationnel sans vérification sur l'appareil

- AirPlay : livraison de la scène externe par iOS, disparition des bandes, rendu libretro
  1080p, mémoire du second moteur pendant RPCS3, connexion/déconnexion en jeu.
- 3DS : changement effectif de langue/région en jeu, lecture des fichiers importés.
- Livres : fluidité du curl, mémoire sur grands CBZ, VoiceOver, manette.
- Musique : raccord inaudible sur ≥ 20 min, reprise après chaque moteur, interruptions.
- Stockage : tailles réelles, cause mesurée de l'écart 40 Go / 20 Go, comportement de purge
  d'iOS.

Chaque chantier livrera son protocole de validation iPhone dans son document
`docs/<chantier>-build44x.md`, et le rapport final distinguera, comme l'exige AGENTS.md,
défauts confirmés, hypothèses, tests exécutés, tests ignorés et validation sur iPhone.
