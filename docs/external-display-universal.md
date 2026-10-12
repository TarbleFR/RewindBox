# AirPlay universel et écrans externes — conception et contrat (12 octobre 2026)

Chantier 1 de la grande mise à jour (`docs/grande-mise-a-jour-audit-2026-10-12.md`, § 3).
Candidate : la prochaine IPA unique construite par-dessus la Build 446 ; numéro attribué
à la livraison. Ce document fixe les noms, canaux, clés et fichiers **avant** le code ;
chaque implémentation s'y conforme exactement, et toute déviation y est reportée.

## 1. Décisions du mainteneur et cadre

- Version iOS de l'iPhone de test inconnue : les **deux régimes** de scène externe sont
  couverts (connexion automatique avant iOS 27 ; accessoire de scène à partir d'iOS 27,
  appelé par sélecteurs car la CI compile avec Xcode 26.3 / SDK iOS 26). La version est
  consignée à la première validation.
- Téléviseur hors jeu : vue TV par second moteur Flutter complet (`SecondaryScreen`),
  détruit pendant RPCS3. Mode par défaut Automatique (menu plein écran, jeu Adapter) ;
  réglage global remplaçant la ligne Dolphin 442 par jeu. Dusklight/KartPad : recopie
  système acceptée. libretro : rendu à la résolution du téléviseur. NeoPlay inchangé
  (pas de diffusion Windows/Chromecast pendant un affichage AirPlay propre).
- Contraintes AGENTS.md : aucun fichier verrouillé (dix de la 419, `lib/main.dart`,
  manifeste natif), aucun cœur, hôte iOS généré uniquement par configurateur, douze
  langues, bloc DELTA, aucune annonce de validation iPhone.

## 2. Cause et principe

Les bandes noires (menu compris) sont la recopie système d'un écran ≈ 19,5:9 sur 16:9 ;
NeoStation n'a aucune fenêtre sur l'écran externe hors session Dolphin. Principe retenu :
**une seule infrastructure hôte** possédant une fenêtre par scène externe, dans laquelle on
place soit la vue Flutter d'un second moteur (menu), soit la vue de rendu du moteur en cours
(jeu), selon une politique de placement commune. La recopie système reste le repli (mode
Désactivé, moteurs non pris en charge).

## 3. Plugin `packages/external_display` (Objective-C, framework dynamique)

Framework **dynamique** (pas `static_framework`) : les ponts d'émulation en dépendent
(`s.dependency 'external_display'` dans leur podspec) et un framework statique lié dans
plusieurs images dupliquerait la classe et le singleton. UIKit résout
`UISceneDelegateClassName` par nom dans toute image chargée avant `main` (précédent :
pont libretro dynamique avec `+load`). Plancher `:ios, '17.4'` comme les autres ponts.

```
packages/external_display/
  pubspec.yaml                      (name: external_display, resolution: workspace, pluginClass: ExternalDisplayPlugin)
  ios/external_display.podspec      (s.source_files 'Classes/**/*.{h,m}', public headers ci-dessous, dependency 'Flutter', frameworks UIKit/Foundation/QuartzCore/MetalKit)
  ios/Classes/ExternalDisplayPlugin.{h,m}            (canal Flutter)
  ios/Classes/NeoExternalDisplayLayout.h             (politique pure, CoreGraphics/Foundation seulement)
  ios/Classes/NeoExternalRenderHost.h                (protocole des ponts)
  ios/Classes/NeoExternalDisplayCoordinator.{h,m}    (singleton, fil principal)
  ios/Classes/NeoExternalDisplaySceneDelegate.{h,m}  (UIWindowSceneDelegate du rôle externe)
  ios/Classes/NeoExternalDisplayPreferences.{h,m}    (NSUserDefaults, clés, repli 442)
  ios/Classes/NeoExternalDisplayLabels.h             (libellés natifs 12 langues, modèle DolphinPacingLabels.h)
  lib/external_display.dart                          (état, canal, événements ; modèle ui_refresh_rate.dart)
```

Headers publics (`public_header_files`) : `ExternalDisplayPlugin.h`, `NeoExternalDisplayLayout.h`,
`NeoExternalRenderHost.h`, `NeoExternalDisplayCoordinator.h`, `NeoExternalDisplayPreferences.h`.

### 3.1 `NeoExternalDisplayLayout.h` — politique pure (exécutable sur macOS CI)

```objc
typedef NS_ENUM(NSInteger, NeoExternalDisplayMode) {
  NeoExternalDisplayModeAutomatic = 0,  // menu : fenêtre pleine ; jeu : Fit
  NeoExternalDisplayModeFit = 1,        // image entière, bandes seulement si les formats diffèrent
  NeoExternalDisplayModeFill = 2,       // zoom 4:3 à la largeur, haut et bas coupés (recadrage annoncé)
  NeoExternalDisplayModeOriginal = 3,   // format de l'iPhone centré à la hauteur du téléviseur
};
typedef NS_ENUM(NSInteger, NeoExternalContentKind) { NeoExternalContentNone = 0, NeoExternalContentMenu = 1, NeoExternalContentGame = 2 };
NeoExternalDisplayMode NeoExternalDisplayModeFromValue(id _Nullable value);          // hors plage → Automatic
NeoExternalDisplayMode NeoExternalDisplayEffectiveMode(NeoExternalDisplayMode stored, NeoExternalContentKind content); // Automatic → Fit pour un jeu
BOOL NeoExternalDisplayUsableSize(CGSize size);
CGFloat NeoExternalDisplayScale(CGSize screen, CGSize source, NeoExternalDisplayMode mode); // Fit/Fill = DOLExternalDisplayScale (442) ; Original = screen.height / source.height borné par la largeur
CGRect NeoExternalDisplayFrame(CGSize screen, CGSize source, NeoExternalDisplayMode mode);  // cadre centré
CGSize NeoExternalDisplaySurfaceSize(CGSize screen, CGSize source, NeoExternalDisplayMode mode); // taille en points de la surface quand le rendu suit le téléviseur (libretro) : Fit → cadre de l'image au format de `source` ; Fill → cadre 4:3 étendu ; Original → source × échelle ; Automatic(jeu) → Fit
BOOL NeoExternalDisplayModeCrops(NeoExternalDisplayMode mode);                           // YES seulement pour Fill
```

Les fonctions `Scale`/`Frame` reproduisent **à l'identique** `DOLExternalDisplayScale`/
`DOLExternalDisplayFrame` pour Fit et Fill (les tests 442 doivent rester vrais).

### 3.2 `NeoExternalRenderHost.h` — protocole adopté par les ponts

```objc
@protocol NeoExternalRenderHost <NSObject>
@property(nonatomic, readonly) UIView *renderView;         // vue déplacée (MTKView, RPCS3MetalView, LibretroMetalView, vue ARMSX2)
@property(nonatomic, readonly) UIView *placeholderView;    // conteneur iPhone qui la reprend à l'index 0
@property(nonatomic, readonly) BOOL fixedDrawable;         // YES : transformation seule (Dolphin, RPCS3, ARMSX2) ; NO : la surface suit le téléviseur (libretro)
@optional
- (void)externalSurfaceDidChange:(CGSize)pointSize scale:(CGFloat)scale; // fixedDrawable == NO : nouvelle surface (CGSizeZero = retour iPhone)
- (void)externalDisplayDidChange:(BOOL)active;                          // fil principal, après le déplacement
@end
```

### 3.3 `NeoExternalDisplayCoordinator` — singleton fil principal

```objc
+ (instancetype)shared;
@property(nonatomic, readonly) BOOL connected;                 // une scène/fenêtre externe existe
@property(nonatomic, readonly) NeoExternalContentKind content;
@property(nonatomic, readonly) CGSize screenPointSize;         // 0 quand déconnecté
@property(nonatomic, readonly) CGFloat screenScale;
@property(nonatomic, readonly) NeoExternalDisplayMode mode;    // préférence stockée
@property(nonatomic, readonly) BOOL enabled, menuOnTV;
- (void)attachRenderHost:(id<NeoExternalRenderHost>)host;     // le jeu prend l'écran (la vue Flutter externe est masquée, jamais libérée ici)
- (void)detachRenderHost:(id<NeoExternalRenderHost>)host;     // retour de la vue à l'index 0 du placeholder AVANT tout arrêt de cœur
- (void)suspendForUnsupportedEngine;                           // Dusklight/KartPad : fenêtre masquée, iOS reprend la recopie
- (void)resumeAfterUnsupportedEngine;
- (void)attachMenuViewController:(UIViewController *)controller; // contrôleur Flutter du second moteur
- (void)detachMenuViewController;
- (void)refresh;                                               // relit préférences + scènes (réglage changé)
@property(nonatomic, copy, nullable) void (^stateChanged)(void);
// seams de test
@property(nonatomic, copy, nullable) UIWindow *_Nullable (^windowFactory)(UIWindowScene *_Nullable scene, UIScreen *_Nullable screen);
@property(nonatomic, copy, nullable) NSArray<UIScreen *> *(^legacyScreens)(void);
- (void)sceneDidConnect:(UIWindowScene *)scene;                // appelé par le délégué de scène
- (void)sceneDidDisconnect:(UIWindowScene *)scene;
```

Règles : jamais `makeKeyAndVisible` sur la fenêtre externe (`hidden = NO` seulement,
`windowLevel` normal) ; `autoResizeDrawable` coupé et `contentScaleFactor` conservé pour
une `MTKView` à `fixedDrawable` (garanties 442) ; retour de la vue à l'index 0 du
placeholder avant arrêt ; observation de `UIScreenModeDidChangeNotification`,
`UIApplicationDidBecomeActiveNotification`, `NeoStation.ExternalDisplayChanged` ;
notification `NeoStation.ExternalDisplayStateChanged` (NSNotificationCenter) à tout
changement d'état. Repli « legacy » (`UIScreen.screens` + `UIWindow.screen`, chemin 442)
isolé dans une méthode `activateLegacyIfNeeded`, utilisé **seulement** si aucune scène
externe n'a été livrée 1,5 s après `UIScreenDidConnectNotification` et si le délégué de
scène n'a jamais été connecté ; journalisé (`display.external_legacy`).

Régime iOS 27 : `NeoExternalDisplaySceneAccessory` (dans le coordinateur) enregistre, par
sélecteurs (`NSClassFromString(@"UISceneAccessory")`, `externalNonInteractiveWithSceneConfiguration:`,
`registerSceneAccessory:`), un accessoire sur le contrôleur présenté le plus haut de la
scène application à chaque changement (menu Flutter, contrôleur de jeu présenté) ; no-op si
les classes/sélecteurs n'existent pas (iOS ≤ 26) ; état `accessoryStatus` ∈
{`unavailable`, `registered`, `failed:<raison>`} exposé dans `getState`.

### 3.4 `NeoExternalDisplaySceneDelegate`

`UIResponder <UIWindowSceneDelegate>` pour le rôle `UIWindowSceneSessionRoleExternalDisplayNonInteractive` :
`scene:willConnectToSession:options:` → `UIWindow` via `windowFactory` ou
`[[UIWindow alloc] initWithWindowScene:]`, `rootViewController` noir non rotatif
(`NeoExternalDisplayViewController`, repris de `DOLExternalDisplayViewController`),
`hidden = NO`, puis `[coordinator sceneDidConnect:]` ; `sceneDidDisconnect:` → rend la vue
de rendu au téléphone puis libère la fenêtre.

### 3.5 Préférences (`NeoExternalDisplayPreferences`)

| Clé NSUserDefaults | Type | Défaut | Note |
| --- | --- | --- | --- |
| `NeoStation.ExternalDisplay.Enabled` | bool | YES | Désactivé = recopie système |
| `NeoStation.ExternalDisplay.Mode` | int 0..3 | 0 Automatique | |
| `NeoStation.ExternalDisplay.MenuOnTV` | bool | YES | |

Repli de lecture : si `NeoStation.ExternalDisplay.Mode` est absent et que la clé 442
`NeoStation.Dolphin.ExternalDisplay.Mode` existe, 0 → `Enabled = NO`, 1 → Fit, 2 → Fill
(lecture seule, jamais réécrite). Notification posée après chaque écriture :
`NeoStation.ExternalDisplayChanged`. Écriture refusée → `SAVE_FAILED` (comme 120 Hz).

### 3.6 Canal Flutter

`MethodChannel neostation/external_display` :

| Méthode | Arguments | Réponse |
| --- | --- | --- |
| `getState` | — | état (ci-dessous) |
| `setEnabled` | `{enabled: bool}` | état ; `SAVE_FAILED` |
| `setMode` | `{mode: int}` | état ; `BAD_ARGS` hors 0..3 ; `SAVE_FAILED` |
| `setMenuOnTV` | `{enabled: bool}` | état |
| `configureMenuEngine` | `{entrypoint: String, libraryUri: String}` | état (mémorise la paire pour la création paresseuse ; sans cet appel, aucun moteur externe n'est créé) |
| `pushMenuState` | `{json: String}` | `true` ; relayé au second moteur par `BasicMessageChannel neostation/external_display/menu` (`StringCodec`) |
| `suspendForUnsupportedEngine` | — | `true` ; masque la fenêtre externe pendant une session KartPad (iOS recopie l'iPhone) |
| `resumeAfterUnsupportedEngine` | — | `true` ; la réaffiche |

État (`getState` et chaque réponse) :
`{supported: bool, connected: bool, content: 'none'|'menu'|'game', screenWidth: double, screenHeight: double, screenScale: double, mode: int, enabled: bool, menuOnTV: bool, mirroringActive: bool, accessoryStatus: String, sceneRole: 'scene'|'legacy'|'none', menuEngine: 'none'|'created'|'attached'|'destroyed'}`.

`EventChannel neostation/external_display/events` : émet l'état complet à chaque
`NeoStation.ExternalDisplayStateChanged`.

`BasicMessageChannel neostation/external_display/menu` (`StringCodec`) : du natif vers le
second moteur ; message = JSON de `SecondaryDisplayStateData.toJson()`.

### 3.7 Libellés natifs (`NeoExternalDisplayLabels.h`)

Douze langues, clés : `externalOnPhone` (« Jeu affiché sur l'écran externe »), `modeAutomatic`,
`modeFit`, `modeFill`, `modeOriginal`, `modeOff`. Un test de parité (Python) vérifie
les douze codes et l'égalité des jeux de clés.

## 4. Second moteur Flutter (menu sur le téléviseur)

- `lib/external_display/external_display_entrypoint.dart` : `@pragma('vm:entry-point')
  Future<void> externalDisplayMain()` : `WidgetsFlutterBinding.ensureInitialized()`, lecture
  de la langue et du thème comme `subDisplay` (`ConfigRepository.getUserConfig()`), init de
  `FlutterLocalization` sur les douze `MapLocale`, `runApp(ExternalMenuApp(...))`.
  Constantes exportées : `kExternalDisplayEntrypoint = 'externalDisplayMain'`,
  `kExternalDisplayLibraryUri = 'package:neostation/external_display/external_display_entrypoint.dart'`.
  **Inclusion AOT** : `ExternalDisplayService` importe ce fichier et passe les constantes à
  `configureMenuEngine` ; `ExternalDisplayService` est importé par la rangée de réglages et
  par `app_screen.dart` (non verrouillé, importé par `main.dart`) → chaîne d'import réelle.
- `lib/external_display/external_menu_screen.dart` : `ExternalMenuApp` = `MaterialApp`
  minimal + `SecondaryScreen(initialThemeName:)` ; les états arrivent par
  `ExternalDisplayStateChannel` (`BasicMessageChannel`, `StringCodec`) →
  `SecondaryDisplayStateData.fromJson` → `SecondaryDisplayState.instance` **n'est pas**
  utilisé (Android) : `SecondaryScreen` reçoit un `ValueListenable<SecondaryDisplayStateData?>`
  injecté par un nouveau paramètre optionnel `stateSource` (défaut : comportement actuel).
  Fond noir, aucune bande (la vue se met en page aux bounds du téléviseur).
- Côté moteur principal : `ExternalDisplayService.pushMenuState(SecondaryDisplayStateData)`
  appelé là où `SecondaryDisplayState.updateState` l'est déjà (iOS : no-op aujourd'hui) —
  un seul point d'appel ajouté dans `lib/services/secondary_display_bridge.dart` (nouveau,
  petit) utilisé par les producteurs existants via un `if (Platform.isIOS)` dans le
  nouveau fichier, jamais dans les fichiers verrouillés.
- Registre de plugins du second moteur (natif, `NeoExternalDisplayMenuEngine`) : **jamais**
  `GeneratedPluginRegistrant` ; enregistrement explicite de `SqflitePlugin` (si présent dans
  le registrant généré : classe résolue par `NSClassFromString(@"SqflitePlugin")`),
  `FLTPathProviderPlugin`, `FVPVideoPlayerPlugin`, `SharedPreferencesPlugin` — chaque classe
  résolue par nom et ignorée si absente ; liste figée dans
  `kNeoExternalMenuPlugins` et testée (test de scope : aucun pont d'émulation, aucun
  `GeneratedPluginRegistrant`).
- Cycle : création paresseuse à la première connexion avec `menuOnTV`, `FlutterEngineGroup`
  dédié `neostation-external`, `FlutterViewController` placé dans la fenêtre externe ;
  masquée (pas détruite) pendant un jeu ; **détruite** quand le pont RPCS3 s'attache
  (`destroyMenuEngineForMemory`) et recréée après ; détruite à la déconnexion.

## 5. Ponts (adoption vue par vue)

| Pont | Adoption | Garanties |
| --- | --- | --- |
| Dolphin | `DolphinExternalDisplay` devient un adaptateur : `DolphinInternalBridgePlugin` crée un `NeoExternalRenderHost` (`fixedDrawable = YES`, render = `_metalView`, placeholder = `container`) et appelle `attachRenderHost:` après les portes de lancement, `detachRenderHost:` **avant** `framePacing stop` (contrat 442 conservé : `test/dolphin_external_display_test.py` adapté explicitement). La ligne « Écran externe » du menu en jeu (`DolphinFramePacing.mm`) lit/écrit la clé globale par `NeoExternalDisplayPreferences`. `DolphinExternalDisplayLayout.h` reste (tests 442) mais délègue à `NeoExternalDisplayLayout.h`. | `autoResizeDrawable` coupé, échelle conservée, retour avant arrêt |
| libretro | `LibretroGameViewController` adopte le protocole (`fixedDrawable = NO`, render = `_metalView`, placeholder = `self.view`) ; `externalSurfaceDidChange:scale:` mémorise `_externalSurface` ; `performSkinLayoutIfNeeded` calcule `drawableSize` et `points` depuis la surface externe quand elle existe (skin/overlay restent aux bounds iPhone) ; le présentateur accepte toute taille. `attachRenderHost:` dans `LibretroSession` après `viewDidAppear`, `detachRenderHost:` avant `stop`. Libellé `externalOnPhone` affiché par `showStatus:`. | 3DS inclus ; rendu à la résolution TV |
| RPCS3 | `RPCS3GameViewController.loadView` : conteneur noir `UIView` racine + `RPCS3MetalView` en sous-vue d'index 0 (`metalLayer` renvoie la couche de la sous-vue), commandes au-dessus ; `fixedDrawable = YES` ; attach après la présentation réussie, detach avant `stopAndDismiss`. `Rpcs3InternalBridgePlugin` appelle `destroyMenuEngineForMemory` via le coordinateur à l'attach. Core et pont NeoSwap intacts. | `test/rpcs3_ui_status_cleanup_test.py` et `neoswap_donor_contract_test.py` inchangés |
| ARMSX2 | `coreView` déjà sous-vue ; `fixedDrawable = YES` ; attach après présentation, detach avant arrêt. | pas de redimensionnement de la vue du Core |
| Dusklight | `suspendForUnsupportedEngine` au lancement, `resumeAfterUnsupportedEngine` à la fin (pont natif). | fenêtre SDL intacte |
| KartPad | Même paire, demandée par Flutter : `KartPadInternalService.launchNativeSession` → `ExternalDisplayService.runUnsupportedEngineSession` → méthodes du canal (§ 3.6). Le pont KartPad reste identique octet pour octet à son Core épinglé (§ 8 bis). | fenêtre SDL intacte, pont non modifié |

Chaque podspec de pont concerné ajoute `s.dependency 'external_display'` (pas celui de KartPad).

## 6. Dart : service, réglages, traductions

- `lib/services/external_display_service.dart` : `ExternalDisplayService` (`ChangeNotifier`,
  singleton `instance`, `forTesting`, `isSupportedPlatform` iOS) ; `state`, `refresh()`,
  `setEnabled`, `setMode(ExternalDisplayMode)`, `setMenuOnTV`, `cycleMode()`, `pushMenuState`,
  abonnement à l'`EventChannel` ; erreurs `saveFailed` + `errorCode` brut ; `init()` appelle
  `configureMenuEngine(kExternalDisplayEntrypoint, kExternalDisplayLibraryUri)` ; jamais
  « enregistré » sans relecture.
- Réglages › Général (iOS), trois rangées après « Interface 120 Hz » :
  1. « AirPlay et écran externe » — `CustomToggleSwitch` (Enabled) + sous-titre d'état
     (`noExternalScreen` / `externalScreen {width}×{height}` / `gameOnExternal` /
     `mirroringOff`) ;
  2. « Format sur l'écran externe » — `SettingValueChip` cyclant Automatique / Adapter /
     Remplir / Format d'origine, sous-titre d'explication du mode et **avertissement de
     recadrage** quand Remplir est choisi (`fillCrops`) ;
  3. « Afficher le menu sur le téléviseur » — `CustomToggleSwitch` (MenuOnTV).
  `getItemCount` +3, `selectItem` +3 (toggle / cycleMode / toggle), `build` +3, clés
  `Key('externalDisplay.enabled')`, `Key('externalDisplay.mode')`, `Key('externalDisplay.menu')`.
  Widget : `lib/screens/settings_screen/new_settings_options/widgets/external_display_setting_rows.dart`.
- `lib/l10n/external_display_locale.dart` (modèle `UiRefreshRateLocale`, `codeFor` avec
  `zh_Hant`/script/TW-HK-MO) — clés : `title`, `description`, `modeTitle`, `modeAutomatic`,
  `modeFit`, `modeFill`, `modeOriginal`, `modeAutomaticHelp`, `modeFitHelp`, `modeFillHelp`,
  `modeOriginalHelp`, `fillCrops`, `menuOnTv`, `menuOnTvHelp`, `noExternalScreen`,
  `externalScreen` (`{width}`, `{height}`), `gameOnExternal`, `mirroringOff`,
  `unsupportedEngine`, `unavailable`, `saveFailed`, `technicalCode` (`{code}`).
  Français du mainteneur : `title` = « AirPlay et écran externe », modes = « Automatique »,
  « Adapter à l'écran », « Remplir l'écran », « Format d'origine ».
- `lib/l10n/neoplay_companion_locale.dart` : nouvelle clé `appleTVOwnWindow` ×12
  (« NeoStation affiche sa propre image sur l'écran externe ; le format se règle dans
  Réglages › Général › AirPlay et écran externe. ») affichée dans la carte Apple TV.
- Inscription de `external_display_locale.dart` dans `test/localization_12_locale_coverage_test.py`.

## 7. Hôte généré et CI

- `build-utils/configure_external_display_ios.py` (idempotent) : dans
  `ios/Runner/Info.plist`, `UIApplicationSceneManifest.UISceneConfigurations.UIWindowSceneSessionRoleExternalDisplayNonInteractive = [{UISceneClassName: UIWindowScene, UISceneConfigurationName: 'neostation-external-display', UISceneDelegateClassName: 'NeoExternalDisplaySceneDelegate'}]`,
  sans toucher le rôle application ; option `--multiple-scenes` (variable
  `NEOSTATION_EXTERNAL_DISPLAY_MULTIPLE_SCENES=1`) qui passe
  `UIApplicationSupportsMultipleScenes` à `true` — variante à essayer sur l'appareil seulement
  si la scène n'est pas livrée ; défaut : inchangé (`false`). Appelé dans « Configure
  release host » après `configure_neoplay_ios.py`.
- Assertion IPA (bloc Python existant de la livraison) : clé de rôle externe présente avec
  la classe attendue ; `Frameworks/external_display.framework/external_display` contient
  `NeoExternalDisplaySceneDelegate`, `neostation/external_display`,
  `NeoStation.ExternalDisplay.Mode` ; ponts contiennent `NeoExternalRenderHost`.
- `.github/workflows/external-display-check.yml` (macOS, patron `ui-refresh-rate-check.yml`,
  push sur `Claude` pour `packages/external_display/**` et ses tests, `workflow_dispatch`) :
  `test/external_display_test.py` (politique pure compilée + contrats de source),
  `test/external_display_scope_test.py`, `test/external_display_host_plist_test.py`,
  `test/external_display_ui_test.py` (XCTest simulateur : scène/fenêtre injectées —
  connexion, modes, déconnexion, ordre de retour, moteur de menu masqué pendant un jeu).
- Livraison : nouveaux tests Dart dans la liste `flutter test` du job `checks`
  (`test/external_display_locale_test.dart test/external_display_service_test.dart
  test/general_settings_external_display_test.dart test/external_menu_screen_test.dart`),
  contrats Python (`external_display_test.py`, `external_display_scope_test.py`,
  `external_display_host_plist_test.py`) après `ui_refresh_rate_scope_test.py`, syntaxe
  iPhone du plugin dans le job `native` (ajout à `test/libretro_ios_syntax_test.py` ou
  commande `xcrun clang -fsyntax-only` dédiée).
- `build-utils/verify_delivery_reuse.py` : bloc `BUILD447_EXTERNAL_DISPLAY_DELTA` listant
  **chaque** fichier créé ou modifié sous `lib/`, `packages/`, `build-utils/`, `test/`,
  `pubspec.yaml`, `pubspec.lock` ; `test/delivery_pipeline_test.py` ajusté si une assertion
  de forme change.
- `pubspec.yaml` : `workspace:` + `dependencies: external_display: path: packages/external_display` ;
  `pubspec.lock` régénéré par `flutter pub get` et commité (la livraison refuse un diff).

## 8. Tests (tous nouveaux, jamais affaiblis)

| Fichier | Vérifie |
| --- | --- |
| `test/external_display_layout_test.mm` + `test/external_display_test.py` | Scale/Frame = 442 pour Fit/Fill ; Original ; SurfaceSize ; Crops ; contrats de source (pas de `makeKeyAndVisible` sur la fenêtre externe, retour avant arrêt, repli legacy isolé, accessoire par sélecteurs) |
| `test/external_display_scope_test.py` | plugin : aucun pont importé, aucune API dépréciée hors `activateLegacyIfNeeded`, registre de plugins du menu = liste figée ; ponts : `s.dependency 'external_display'` ; `NPController`/`UiRefreshRatePlugin` filtrent `UIWindowSceneSessionRoleApplication` |
| `test/external_display_host_plist_test.py` | configurateur sur une fixture : rôle ajouté, rôle application intact, idempotence, variante `--multiple-scenes` |
| `test/external_display_ui_test.py` | XCTest simulateur (harnais de `dolphin_external_display_ui_test.py`) |
| `test/external_display_locale_test.dart` | 12 langues, parité, placeholders, non-anglais, zh_Hant, français du mainteneur |
| `test/external_display_service_test.dart` | canal simulé : état, setMode/Enabled/MenuOnTV, SAVE_FAILED jamais « enregistré », événements, configureMenuEngine à l'init |
| `test/general_settings_external_display_test.dart` | trois rangées iOS, comptage/sélection manette, chip cyclique, avertissement Remplir |
| `test/external_menu_screen_test.dart` | rendu 1920×1080 sans bande, état reçu par le canal, thème/langue initiaux |
| `test/dolphin_external_display_test.py` (adapté) | mêmes garanties 442 via l'adaptateur |
| `test/neoplay_locale_test.dart` (étendu) | clé `appleTVOwnWindow` ×12 |

## 8 bis. Déviations consignées pendant l'implémentation (12 octobre 2026)

Relevées par les agents d'implémentation et la revue contradictoire ; le code fait foi.

- § 3 : six headers publics, `NeoExternalDisplayLabels.h` compris (le pont libretro
  l'importe sous `<external_display/…>` ; avec `use_frameworks!` seuls les headers publiés
  résolvent). `NeoExternalDisplayText()` y est une fonction `static` (une copie par unité).
- § 3.3 / § 3.4 : la fenêtre externe est créée par le coordinateur dans `sceneDidConnect:`
  (même `windowFactory`), le délégué de scène ne fait que relayer ; le coordinateur ne
  dépend pas de Flutter : il parle au moteur de menu par le protocole
  `NeoExternalMenuProvider` adopté par `NeoExternalDisplayMenuEngine` ; le second moteur
  n'est créé qu'à la première connexion où le menu est réellement montré, jamais pendant
  qu'un jeu occupe le téléviseur ; `mirroringActive` est dérivé (connecté et fenêtre
  masquée), non lu sur `UIScreen`.
- § 3.3 iOS 27 : sélecteur documenté par Apple
  `+externalNonInteractiveSceneAccessoryWithConfiguration:` essayé d'abord, puis la
  graphie du contrat ; une inscription par contrôleur encore présenté (racine Flutter
  toujours, contrôleur de jeu tant qu'il est présenté) au lieu d'une inscription déplacée.
- § 3.6 : registre figé `kNeoExternalMenuPlugins` = `SqflitePlugin` (absent : l'app utilise
  sqlite3 par FFI, ignoré), `FLTPathProviderPlugin`, `FVPVideoPlayerPlugin`,
  `SharedPreferencesPlugin` et leurs noms Swift qualifiés (`path_provider_foundation.PathProviderPlugin`,
  `shared_preferences_foundation.SharedPreferencesPlugin`).
- § 5 libretro : `performSkinLayoutIfNeeded` passe `points:surface.points` ; les zones de
  jeu du skin iPhone sont placées dans la surface TV par `LibretroRenderSurface.h`
  (union des zones mise à l'échelle et centrée) ; skin, overlay et chrome gardent les
  bounds iPhone ; l'attache a lieu à la fin de la présentation (après `viewDidAppear`,
  avant le fil d'émulation), le détachement avant la demande d'arrêt. En portrait sur
  le téléviseur, l'image reste un pilier au format du téléphone (politique du
  coordinateur). Les écrans tactiles DS/3DS sont alors opérés à l'aveugle sur le
  téléphone.
- § 5 RPCS3 : à l'attache, le pont demande la destruction du moteur de menu ; pendant
  l'arrêt du Core, il tient le menu masqué par `suspendForUnsupportedEngine` /
  `resumeAfterUnsupportedEngine` (seule paire disponible) pour éviter la recréation du
  second moteur pendant `stop_emulation` (≈ 0,6 Go libres).
- § 4 : chaîne d'import AOT réelle : `lib/main.dart` → `lib/screens/main_screen.dart` →
  `lib/screens/app_screen.dart` → `external_display_service.dart` →
  `external_display_entrypoint.dart`. Producteurs qui alimentent le téléviseur sur iOS :
  grille des consoles (`theme_background.dart`), onglets et thème (`app_screen.dart`), et
  depuis le 12 octobre la liste des jeux (`my_games_list/secondary_display.dart`, retour
  `_goBack` compris) : images seulement (fanart, capture, logo), jamais la vidéo d'aperçu
  (pas de second décodeur ni de son sur le téléviseur) ni les octets de pochette musicale,
  et seulement tant qu'un téléviseur affiche le menu (`SecondaryDisplayBridge
  .forwardsSelections`), pour qu'un iPhone sans téléviseur ne paie aucun contrôle de
  fichier ni message de canal par sélection ; une sélection déjà affichée n'est pas
  renvoyée (`showsSelection`). Le chemin Android est inchangé. Test :
  `test/external_display_games_list_test.dart`. Les succès ne sont pas relayés.
- § 6 : le texte Apple TV (`appleTVOwnWindow`) renvoie au libellé réel de l'onglet,
  « Paramètres › Général » en français (`AppLocale.settings`), pas « Réglages ».
- § 7 : assertion IPA étendue aux quatre ponts (`NeoExternalRenderHost` dans leurs
  binaires) et aux deux blocs (jobs `cold` et `warm`) ; preuve native RPCS3 réutilisable
  hachant aussi les headers du pod ; contrôle Dolphin `test/dolphin_external_display_test.py`
  réécrit vers la délégation (le header DOL ne contient plus l'arithmétique 442 ;
  `test/external_display_layout_test.mm` compare à une copie figée de la 442) ; quatre
  contrats de ponts (`libretro_external_surface`, `rpcs3_external_display`,
  `armsx2_external_display`, `ports_external_display`) ajoutés aux deux workflows.
- Tests déjà rouges avant ce chantier, non exécutés par la livraison, non affaiblis :
  `test/import_memory_candidate_scope_test.py`, `test/neoplay_build397_integration_test.py`
  (épinglages historiques), `test/library_cover_delivery_test.py` (voie 443 fermée).
  Le premier est aussi lancé par `dolphin-pacing-check.yml` (rouge depuis la Build 440,
  run 38161122592 sur `docs/LEGAL_AND_CREDITS.md`) ; ce chantier y ajoute deux écarts
  attendus, `.github/workflows/neoswap-ipa.yml` (headers du pod mis en scène pour le
  contrôle syntaxique RPCS3) et `lib/services/kartpad_internal_service.dart` (ci-dessous).
- § 5 KartPad (correctif du 12 octobre 2026) : la première version modifiait
  `KartPadInternalBridgePlugin.mm` et son podspec. La livraison épingle tout
  `packages/kartpad_internal_bridge` sur `KARTPAD_CORE_HOST_SHA` (`3934ac9d`, étape
  « Verify KartPad Core candidate identity ») : le run 38207626900 s'y est arrêté, avant
  toute IPA. Le pont et `kartpad-core.yml` sont revenus à leurs octets épinglés ; la paire
  suspend/resume est tenue par Flutter juste avant le lancement natif
  (`KartPadInternalService.launchNativeSession`), relâchée une seule fois : réponse sans
  session (refus du Core, session déjà active, erreur du canal), ou événement
  `sessionEnded` de la transaction en cours (retour, redémarrage de langue, échec, plantage,
  délai de première image, `stop`). Un délai de première image garde la fenêtre masquée
  jusqu'à cet événement, comme le pont garde la session. Tests :
  `test/external_display_unsupported_engine_test.dart` (comportement, vrai pont Dart KartPad
  sur canal simulé) et `test/ports_external_display_test.py` (épinglage et câblage).

## 9. Ce qui reste à vérifier sur l'iPhone + Apple TV (jamais annoncé avant)

Livraison de la scène externe (iOS 26 / 27, `UIApplicationSupportsMultipleScenes`),
disparition des bandes dans le menu, rendu libretro 1080p et charge GPU, Dolphin/RPCS3/
ARMSX2 agrandis, connexion/déconnexion en jeu, retour au premier plan, mémoire du second
moteur et sa destruction pendant RPCS3, Dusklight/KartPad en recopie, NeoPlay inchangé.
Journal : `display.external_scene_connected`, `display.external_attached:<pont>`,
`display.external_detached:<pont>`, `display.external_legacy`, `display.external_accessory:<statut>`.
