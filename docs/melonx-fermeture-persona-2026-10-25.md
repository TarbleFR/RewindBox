# MeloNX embarqué — fermeture des jeux, Persona 4 Golden et revalidation GPU (25 octobre 2026)

Travail sur `Claude`, à partir de `3494edc9`. Journaux fournis : `app (1)(1).log`
(52 723 lignes, 29 tentatives MeloNX du 23 au 25 octobre) et `app (1)(3).log`
(8 479 lignes, sessions Persona du 24 au 25 octobre). Les vidéos citées dans
les rapports précédents ne sont pas disponibles dans cette session : aucune
conclusion visuelle nouvelle n'en est tirée. Preuves brutes et synthèses :
`docs/evidence/melonx-close-teardown-2026-10-25.json`. Analyseur réutilisable :
`build-utils/melonx/analyze_session_logs.py`.

Le build exact d'une session n'est pas écrit dans le journal. Il est encadré par
des marqueurs introduits par des commits connus : événement `configuration`
(533, `77388b61`), journal audio Apple (537, `94ae1314`), préfixe
`Applied graphics:` non masqué (539, `8a7fe586`).

## 1. Audit des correctifs existants

| Correctif | Commit(s) et emplacement | Classement |
| --- | --- | --- |
| Fenêtre native / `presentationUnavailable` (518) | `303d9084` — `MeloNXPresentation.swift`, plugin | **Implémenté et vérifié** : toutes les sessions récentes journalisent `presentation passed` puis `firstFrame passed` |
| `VK_ERROR_FEATURE_NOT_PRESENT` / `VK_EXT_external_memory_host` (530) | `acd7314a` — `adapt_runtime.py::disable_ios_host_import` | **Implémenté et vérifié** : 15 quarantaines ≤ 529 ont cette cause ; aucune occurrence ensuite (P4G, P5R, Mario, Smash) |
| Erreurs de fences Vulkan, buffers hôtes (533) | `77388b61` — `adapt_runtime.py::preserve_fence_errors` | **Implémenté mais non validé sur appareil** : aucun `ErrorDeviceLost` dans ces journaux ; le cas Zelda n'y figure pas |
| Cache de shaders actif, compilation asynchrone désactivée (531) | `02f154dc` — `EmbeddedGraphicsSettings.cs` | **Implémenté et vérifié** : Smash ≥ 539 journalise `shaderCache=True; asyncShaders=False` |
| Récupération des pipelines après préchauffage échoué (540) | `97915e50` — `adapt_pipeline.py` | **Implémenté mais non validé sur appareil** : aucune `Graphics pipeline creation failed` ; les avertissements de préchauffage restent (§ 4) |
| Audio (SDL3 532, Apple AVAudioEngine 537, interruptions) | `6c08b52d`, `94ae1314`, `23d92f17` | **Implémenté mais non validé sur appareil** : `backendReady` 48 kHz / 2 canaux / 20 ms journalisé ; la qualité sonore n'est pas mesurable dans un journal |
| Importation jeux, mises à jour, DLC (535, 537) | `6ddf9d7c`, `753bbdb1` — `melonx_embedded_library_service.dart` | Jeu et **99 DLC** importés en un lot ; mise à jour Smash v13.0.4 importée au second essai. Le premier refus (10:52, build 533–536) **précède** le correctif 537 : non revalidé sur ≥ 537 |
| Suppression, anciens chemins externes (509) | `d4e61fa1`, `0a7975e3` — `game_repository.dart` | **Implémenté et vérifié** : 7 échecs `melonx://` et 1 `localGameRequired` les 22–23 oct., puis « removed 3 external library references » et suppression Smash complète le 25 (`filesystem_complete`, `database_complete`) |
| Entitlements, JIT, mémoire étendue (514, 519) | `07407ed8`, `c8424c32`, `verifyMemoryAccess` | **Implémenté et vérifié** : `entitlements`, `jitProbe`, `jitArena` et bail donneur de 4 Gio `mapped/offered` dans chaque lancement récent |
| Durée de vie des sessions (506–533) | `90ac4ab1`, `65f957e7`, `dc46d73c`, `77388b61` | **Régression constatée** (Smash) : fermeture bloquée ; corrigée ici, non validée sur appareil |

## 2. Diagnostic de la fermeture de Super Smash Bros. Ultimate (PID 30506)

Session `Super Smash Bros. Ultimate.xci` (15 971 909 632 octets, firmware 22.5.0,
build ≥ 539, résolution 1×, cache de shaders actif, compilation synchrone).
Premier frame 14:07:35 ; 17 min 40 s de jeu ; fermeture demandée 14:25:14.393.
Le guest s'arrête normalement (`TerminationRequested` sur tous les threads,
fermeture des deux canaux GPU). Le travailleur de rendu exécute alors sa seule
libération GPU : `GpuContext.Dispose → RunDeferredActions → PhysicalMemory.Destroy`.
`ShaderCache.Dispose` et `BufferCache.Dispose` réussissent, puis
`TextureCache.Dispose → TextureGroup.Dispose → RegionHandle.Dispose` lève
`ObjectDisposedException`.

Conclusions démontrées par le code et par une exécution réelle :

1. `Destroy` n'a pas été exécuté deux fois : une seconde exécution échouerait
   dans `BufferCache`. Une texture **encore indexée** dans `TextureCache` avait
   déjà libéré ses poignées de suivi.
2. MeloNX 2.6 a remplacé l'éviction unique amont (plancher de 32 textures) par
   une boucle `EnforceCapacity` qui peut évincer la texture en cours d'ajout.
   Or `AutoDeleteCache.Add` précède `_textures.Add` : la texture est libérée,
   puis indexée, renvoyée et utilisée. Le harnais reproduit exactement la pile
   de l'iPhone avec ce chemin. Le déclencheur précis de la session Smash n'est
   pas journalisé (les journaux Info ne sont pas relayés) ; d'autres chemins
   produisant une texture libérée mais indexée ne sont pas exclus.
3. RewindBox arrête le guest pendant que le rendu tourne. Les threads guest/HLE
   ajoutent alors des actions différées à une `Queue<Action>` non thread-safe
   que le rendu vide : 19 414 actions perdues et 71 dupliquées sur 80 000 dans le
   harnais. Une désinscription tardive du processus peut aussi demander deux
   destructions de `PhysicalMemory`.
4. L'échec rendait le travailleur « failed » : quarantaine, `Switch.Dispose`
   sauté, allocations invitées vivantes, bail donneur `retained` (4 294 967 296
   octets). Le plugin gardait alors l'hôte actif : `isSessionActive` répondait
   `true` indéfiniment, le sondeur Dart ne recevait jamais `false` et la boîte
   « Fermeture du jeu… » ne pouvait pas se fermer.

Aucune session ne s'est bloquée à cause d'une attente infinie : le travailleur
s'est terminé, l'état natif est resté en quarantaine par conception.

## 3. Corrections

**A — Destruction GPU** (`build-utils/melonx/adapt_gpu_lifetime.py`, branché dans
`prepare_embedded.py`, sources de production adaptées à la compilation) :

- `AutoDeleteCache.EnforceCapacity(protectedTexture)` n'évince jamais la texture
  ajoutée ou relevée par l'appelant ; un avertissement unique le signale.
- `Texture.Dispose` et `TextureGroup.Dispose` sont idempotents ;
  `TextureCache.Dispose` saute une texture déjà libérée, tolère une poignée déjà
  libérée par un autre propriétaire et journalise les deux compteurs.
- `PhysicalMemory.Dispose` ne programme `Destroy` qu'une fois ; `Destroy` tente
  chaque cache et libère toujours la référence mémoire CPU.
- `GpuContext.DeferredActions` devient `ConcurrentQueue<Action>` ;
  `GpuContext.Dispose` exécute chaque action restante et libère le renderer même
  si l'une échoue, puis propage la première erreur.

**B — Cycle de vie et navigation** : la quarantaine reste obligatoire pour toute
erreur non tolérée (garde-fou inchangé de `EmbeddedWindowLifetime`). Le plugin
mémorise une quarantaine survenue après l'exécution : `isSessionActive` répond
`false` (le jeu est terminé), `isSessionQuarantined` répond `true`, une relance
renvoie `quarantined` / `requiresRestart` au lieu de `busy`. Dart
(`GameLaunchManager`, `GameLaunchDialog`) termine la route, remplace « Fermeture
du jeu… » par l'explication déjà traduite en douze langues, attend
l'acquittement (toucher, B, Entrée) puis rend la playlist. L'audio de
l'interface reste en pause, comme pour une initialisation mise en quarantaine.
`MeloNXSessionHost.swift` est inchangé (identique à `084fdb5d`).

**C — Mémoire** : après une fermeture réussie, la référence CPU, les caches et le
renderer sont libérés, puis `Switch.Dispose` libère les allocations invitées et
le bail est retiré (`released`). En quarantaine, la rétention reste voulue :
aucun thread ne doit pouvoir accéder à une mémoire rendue.

Sauvegardes, clés, firmware, caches de shaders et réglages ne sont ni modifiés
ni réinitialisés. Aucun autre émulateur n'est touché.

## 4. Revalidation shaders, pipelines et attentes GPU

- `Background pipeline compile missed on draw` (ShaderCollection) est émis **au
  plus une fois par programme** quand le pipeline préchauffé ne correspond pas à
  l'état du dessin. Avec la compilation asynchrone désactivée, le pipeline est
  compilé de façon synchrone : saccade possible, pas de dessin sauté. P5R ≤ 532 :
  5 à 8 dans 4 sessions sur 19 ; P4G : aucun ; Smash ≥ 539 : 11 en 17 min 40 s.
- Budget du cache principal de pipelines Vulkan (128 Mio, `PipelineCacheManager`) :
  au-delà, l'instantané précédent est conservé ; les pipelines suivants sont
  recompilés à chaque lancement. Atteint dans 10 sessions P5R et dans Smash. C'est
  une limitation mesurable, pas un défaut démontré ; la taille réelle finale est
  journalisée en Info et n'est pas relayée. Aucun budget n'est modifié à
  l'aveugle.
- `WaitOnSyncpoint > 1000 ms` : 0 dans les 27 sessions Persona ayant un premier frame ; 3 sur Mario
  (≤ 532) ; 9 sur Smash (≥ 539), avec 147 « GPU processing thread is too slow ».
  Smash n'a pas de session comparable sur un build antérieur complet ; aucune
  comparaison avant/après n'est donc revendiquée pour ce titre.

## 5. Persona 4 Golden

- Fichier `Persona 4 Golden [010062B01525C000][v0][US].nsp`, Title ID
  `010062B01525C000`, version 0 (aucune mise à jour), 9 749 647 696 octets,
  firmware 23.0.1 reconnu.
- Sessions : 02:02 et 02:04 (build ≤ 529) mises en quarantaine par
  `ErrorFeatureNotPresent`, cause corrigée en 530 ; 03:24, 03:33, 03:44, 03:53
  (≤ 532) et 10:53, 10:54 (533–536) : premier frame 3 à 5 s après la sélection, 19 à 118 s de jeu,
  fermeture `passed`, bail `released`, aucune compilation manquée, aucun budget de
  cache atteint, aucune attente de syncpoint, aucun `DeviceLost`.
- Réglages graphiques : non récupérables (absents avant 533, masqués de 533 à
  538). Aucune session P4G ≥ 539 dans les journaux.
- 10:59:58 : `localGameRequired`, chemin d'un conteneur précédent huit secondes
  après une réinstallation, avant la relocalisation par l'analyse de la
  bibliothèque. Ce n'est pas une régression ; correctif proposé : au lancement,
  rechercher le même chemin relatif sous `Documents` dans le conteneur courant
  (`IosLibraryRootRelocation.split`).

**Aucune erreur confirmée de Persona 4 Golden après le correctif 530.** Les
modifications de ce lot visent donc les problèmes reproduits.

## 6. Persona 5 Royal — régions noires, analyse séparée

Le rapport porte sur le menu principal de P5R (`docs/melonx-visual-report-2026-10-25.md`).
Les journaux contiennent 39 tentatives P5R (19 avec un premier frame), toutes
≤ 538 : aucune n'utilise le candidat 540. Aucune erreur de compilation de pipeline n'y figure ; les
avertissements de préchauffage et de budget ci-dessus ne prouvent pas la cause
des pixels. Hypothèse **non confirmée** : une texture libérée puis utilisée
(§ 2.2) rendrait du noir ou des données périmées. Le nouvel engine journalise
désormais `Texture cache kept its texture in use…` et, à la fermeture, le nombre
de textures libérées mais indexées : ces lignes trancheront sur iPhone. Aucun
correctif P5R n'est appliqué à P4G.

## 7. Tests

Exécutés dans ce conteneur Linux (.NET SDK 10.0.100, Flutter 3.47.2) :

- `test/melonx_gpu_teardown_test.py` : compile les vrais projets
  `Ryujinx.Graphics.Gpu/Cpu/Memory` épinglés, sans puis avec l'adaptateur. Seul le
  renderer GAL est une doublure inerte. Le contrôle reproduit la pile de l'iPhone,
  la référence CPU retenue, le renderer non libéré et la file non sûre ; le
  corrigé passe 7 scénarios : nouvelle texture au-delà de la part de cache,
  texture libérée encore indexée, poignée périmée, double destruction,
  action différée en échec, 80 000 actions concurrentes, 5 sessions consécutives
  sans accumulation.
- `test/game_close_status_test.py` : 11 retours existants, contrôle négatif de la
  quarantaine (route « Fermeture du jeu » encore présente après 60 s) et parcours
  corrigé (explication, acquittement, playlist, audio en pause).
- `test/game_audio_handoff_test.py` (5), `test/game_launch_route_test.py` (7),
  `test/melonx_launch_flow_test.py` (11) : réussis. `flutter analyze` : aucune
  nouvelle remarque.

Non exécutés ici : compilation Swift et UIKit (`melonx-host.yml`), engine
NativeAOT et deux sessions ARM64 simulateur (`melonx-core.yml`), IPA. Aucune des
séquences sur iPhone demandées (fermeture depuis le jeu ou RewindBox, pendant un
chargement ou une compilation, enchaînement, session longue) n'a pu être
réalisée : elles restent la validation à faire avec l'IPA de test.

## 8. Protocole iPhone proposé

1. Smash : jouer 15 min, fermer depuis RewindBox ; attendu `close passed`, `memory
   released`, retour playlist, puis relancer.
2. P4G et P5R : trois lancements/fermetures chacun, dont une pendant un chargement.
3. Relever dans le journal toute ligne `Texture cache kept…` ou `Texture cache
   teardown skipped…` et les compteurs de l'analyseur.
4. En cas de quarantaine : la boîte affiche l'explication, se ferme à
   l'acquittement, et la relance demande de redémarrer RewindBox.
