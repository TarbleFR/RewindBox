# AirPlay universel et écrans externes — conception et contrat (12 octobre 2026)

> **20 octobre 2026.** KartPad (19 octobre), puis Dusklight et la playlist Ports ont quitté
> NeoStation (`docs/ports-removal-2026-10-20.md`). Les mentions « Dusklight/KartPad » ci-dessous
> décrivent les builds antérieures ; `suspendForUnsupportedEngine` reste utilisé par RPCS3 pendant
> l'arrêt de son cœur, et `runUnsupportedEngineSession` n'a plus d'appelant en production.

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
CGSize NeoExternalDisplaySurfaceSize(CGSize screen, CGSize source, NeoExternalDisplayMode mode); // taille en points de la surface quand le rendu suit le téléviseur (libretro) : l'écran entier dans tous les modes (revue du 12 octobre, M3) ; CGSizeZero si une taille est inutilisable
BOOL NeoExternalDisplayModeCrops(NeoExternalDisplayMode mode);                           // YES seulement pour Fill
static const NSInteger NeoExternalDisplayAccessorySDKMajor = 27;                          // régime accessoire iOS 27 (note Apple 177015874)
NSInteger NeoExternalDisplayVersionMajor(NSString *_Nullable text);                       // « 26.2 » → 26 ; vide, lettre, « 26. », « .26 », > 10000 → 0
NSInteger NeoExternalDisplaySDKMajorVersion(NSString *_Nullable platformVersion, NSString *_Nullable sdkName); // DTPlatformVersion d'abord, puis la version de DTSDKName (« iphoneos26.2 ») ; 0 = inconnu
```

Les fonctions `Scale`/`Frame` reproduisent **à l'identique** `DOLExternalDisplayScale`/
`DOLExternalDisplayFrame` pour Fit et Fill (les tests 442 doivent rester vrais). Les
formats (Adapter, Remplir, Format d'origine) s'appliquent aux vues à `fixedDrawable` (Dolphin,
RPCS3, ARMSX2), seulement mises à l'échelle ; un hôte qui dessine à la résolution du
téléviseur (libretro) reçoit l'écran entier et y place chaque jeu à son propre format
(`LibretroRenderSurfacePlacement`) : un écran GBA d'un iPhone en portrait occupe
1620 × 1080 d'un téléviseur 1080p, un écran 4:3 1440 × 1080, en paysage comme en portrait.

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
@property(nonatomic, readonly) BOOL suspended;                 // Dusklight/KartPad en cours : fenêtre masquée, recopie système
@property(nonatomic, readonly, copy) NSArray<UIWindowScene *> *externalScenes; // scènes externes connectées, dans l'ordre
- (void)attachRenderHost:(id<NeoExternalRenderHost>)host;     // le jeu prend l'écran (la vue Flutter externe est masquée, jamais libérée ici)
- (void)detachRenderHost:(id<NeoExternalRenderHost>)host;     // retour de la vue à l'index 0 du placeholder AVANT tout arrêt de cœur
- (void)suspendForUnsupportedEngine;                           // Dusklight/KartPad : fenêtre masquée, iOS reprend la recopie
- (void)resumeAfterUnsupportedEngine;
- (void)attachMenuViewController:(UIViewController *)controller; // contrôleur Flutter du second moteur
- (void)detachMenuViewController;
- (void)refresh;                                               // relit préférences, reparcourt UIApplication.connectedScenes, réapplique (appelé pendant une passe : exécuté à sa fin)
@property(nonatomic, copy, nullable) void (^stateChanged)(void);
// seams de test
@property(nonatomic, copy, nullable) UIWindow *_Nullable (^windowFactory)(UIWindowScene *_Nullable scene, UIScreen *_Nullable screen);
@property(nonatomic, copy, nullable) NSArray<UIScreen *> *(^legacyScreens)(void);
@property(nonatomic, copy, nullable) NSInteger (^buildSDKMajorVersion)(void); // remplace la lecture de l'Info.plist principal
@property(nonatomic, copy, nullable) CGFloat (^screenScaleReader)(void);     // remplace l'échelle de l'écran externe
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
scène n'a jamais été connecté ; journalisé (`display.external_legacy`). Dans une app à
scènes, une fenêtre sans scène n'est jamais affichée : si une scène externe de cet écran est
déjà connectée, elle est adoptée (`display.external_legacy_scene`) ; sinon la fenêtre n'est
utilisée que si elle se retrouve dans une scène de cet écran, et à défaut rien ne bouge,
iOS continue la recopie (`display.legacy_unavailable`, revue du 12 octobre, M2).

Scènes (revue du 12 octobre, M1) : le coordinateur tient l'**ensemble** des scènes externes
connectées. Une seconde scène ne remplace jamais la fenêtre affichée (elle attend,
`display.external_scene_standby`) ; la déconnexion de la scène affichée adopte la plus
récente encore attachée (`display.external_scene_adopted` : vue de rendu rendue au téléphone
et menu détaché d'abord, moteur de menu conservé) ; `refresh` reparcourt
`UIApplication.connectedScenes` (scène disparue = déconnexion, `display.external_scene_lost` ;
scène externe dont personne n'a parlé = connexion, `display.external_scene_found`). Le
délégué de scène ne garde que la fenêtre de sa propre scène.

Passes : un appel reçu pendant une passe (rappel d'un hôte ou du fournisseur de menu)
demande une passe de plus à la fin (au plus quatre de suite, `display.external_apply_passes`
sinon) au lieu d'être perdu (m5). Chaque passe relit l'échelle de l'écran externe et compare
taille **et** échelle de la surface annoncée à un hôte non fixe (m6) ; pour un tel hôte la
surface est recalculée à chaque passe depuis les bounds actuels du placeholder (rotation),
et `LibretroGameViewController` demande un `refresh` (fil principal, regroupé) quand ses
bounds changent pendant que l'image est sur le téléviseur. Le moteur de menu est prévenu à
chaque passe (`externalMenuSetVisible:`, optionnel) ; il est détruit quand le menu sur le
téléviseur ou toute la sortie est désactivé (`menu_off`, `disabled`).

Régime iOS 27 : `NeoExternalDisplaySceneAccessory` (dans le coordinateur) enregistre, par
sélecteurs (`NSClassFromString(@"UISceneAccessory")`, `externalNonInteractiveWithSceneConfiguration:`,
`registerSceneAccessory:`), un accessoire sur le contrôleur présenté le plus haut de la
scène application à chaque changement (menu Flutter, contrôleur de jeu présenté) ; no-op si
les classes/sélecteurs n'existent pas (iOS ≤ 26) ; état `accessoryStatus` ∈
{`unavailable`, `registered`, `failed:<raison>`} exposé dans `getState`.
*Remplacé par la revue du 12 octobre (M1, m10)* : ce chemin n'est pris que par un binaire
construit avec le SDK 27 ou plus (`DTPlatformVersion`/`DTSDKName` de l'Info.plist principal,
`display.external_build_sdk` ; absent ou illisible = inactif : la livraison Xcode 26.3 reste
sur la connexion automatique, y compris sur iOS 27) et jamais pendant qu'une scène offerte
par le système seul est connectée (connectée sans inscription active de NeoStation). Il
inscrit alors la racine de la scène application (activée tant qu'il y a quelque chose à
montrer : sortie activée, non suspendue, menu ou jeu) et le contrôleur présenté qui possède
l'hôte de rendu attaché (trouvé depuis son placeholder, jamais le plus haut de la chaîne,
qui peut être un menu présenté par-dessus le jeu) ; `isEnabled` (`setEnabled:`) coupe une
inscription sans rien à montrer, une inscription sans ce setter est désinscrite ; les
contrôleurs sortis de la chaîne sont désinscrits à la passe suivante. `accessoryStatus` ∈
{`unavailable`, `inactive:sdk`, `inactive:automatic_scene`, `registered`, `disabled`,
`failed:<raison>`}.

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
Choisir un format alors que ni `Enabled` ni `Mode` n'est stocké met fin à ce repli : la
valeur `Enabled` dérivée (NO pour un 442 Désactivé) est d'abord écrite, sans notification,
pour que le choix d'un format n'active jamais la sortie à lui seul (revue du 12 octobre, m1).

### 3.6 Canal Flutter

`MethodChannel neostation/external_display` :

| Méthode | Arguments | Réponse |
| --- | --- | --- |
| `getState` | — | état (ci-dessous) |
| `setEnabled` | `{enabled: bool}` | état ; `SAVE_FAILED` |
| `setMode` | `{mode: int}` | état ; `BAD_ARGS` hors 0..3 ; `SAVE_FAILED` |
| `setMenuOnTV` | `{enabled: bool}` | état |
| `configureMenuEngine` | `{entrypoint: String, libraryUri: String, languageCode: String?, themeName: String?}` | état (mémorise la paire pour la création paresseuse, avec la langue et le thème de départ du second moteur ; sans cet appel, aucun moteur externe n'est créé ; autre type → `BAD_ARGS`) |
| `updateMenuEngine` | `{languageCode: String?, themeName: String?}` | `true` ; la copie donnée au prochain moteur suit, une nouvelle langue est envoyée au moteur en cours (`neostation/external_display/menu_locale`) ; `null` = inchangé |
| `pushMenuState` | `{json: String}` | `true` ; relayé au second moteur par `BasicMessageChannel neostation/external_display/menu` (`StringCodec`) |
| `suspendForUnsupportedEngine` | — | `true` ; masque la fenêtre externe pendant une session KartPad (iOS recopie l'iPhone) |
| `resumeAfterUnsupportedEngine` | — | `true` ; la réaffiche |

État (`getState` et chaque réponse) :
`{supported: bool, connected: bool, content: 'none'|'menu'|'game', screenWidth: double, screenHeight: double, screenScale: double, mode: int, enabled: bool, menuOnTV: bool, suspended: bool, mirroringActive: bool, accessoryStatus: String, sceneRole: 'scene'|'legacy'|'none', menuEngine: 'none'|'created'|'attached'|'destroyed'}`
(`suspended` ajouté par la revue du 12 octobre, m2 ; absent = `false`).

`EventChannel neostation/external_display/events` : émet l'état complet à chaque
`NeoStation.ExternalDisplayStateChanged`.

`BasicMessageChannel neostation/external_display/menu` (`StringCodec`) : du natif vers le
second moteur ; message = JSON de `SecondaryDisplayStateData.toJson()`.
`BasicMessageChannel neostation/external_display/menu_locale` (`StringCodec`) : du natif vers
le second moteur en cours ; message = code d'une des douze langues (tout autre texte est
compté comme refusé et ignoré).

### 3.7 Libellés natifs (`NeoExternalDisplayLabels.h`)

Douze langues, clés : `externalOnPhone` (« Jeu affiché sur l'écran externe »), `modeAutomatic`,
`modeFit`, `modeFill`, `modeOriginal`, `modeOff`. Un test de parité (Python) vérifie
les douze codes et l'égalité des jeux de clés.

## 4. Second moteur Flutter (menu sur le téléviseur)

- `lib/external_display/external_display_entrypoint.dart` : `@pragma('vm:entry-point')
  Future<void> externalDisplayMain()` : `WidgetsFlutterBinding.ensureInitialized()`, lecture
  de la langue et du thème comme `subDisplay` (`ConfigRepository.getUserConfig()`), init de
  `FlutterLocalization` sur les douze `MapLocale`, `runApp(ExternalMenuApp(...))`.
  *Remplacé par la revue du 12 octobre (m11, sécurité des données)* : le second moteur
  n'ouvre jamais la base (une seconde connexion SQLite y jouerait ses PRAGMA, ses écritures
  correctives et, sur erreur d'E/S, supprimerait les -wal/-shm de la connexion du moteur
  principal). `externalDisplayMain(List<String> args)` reçoit la langue et le thème du moteur
  principal (`language=<code>`, `theme=<nom>`, `ExternalDisplayMenuArgs`), passés par
  `FlutterEngineGroupOptions.entrypointArgs` (`makeEngineWithOptions:`, API vérifiée dans les
  headers Flutter épinglés) ; une langue suivante arrive par `menu_locale`, le thème avec
  chaque état. `FlutterLocalization` est initialisé sur les douze langues sans écrire ses
  préférences (la langue du moteur principal l'emporte sur celle stockée) ; tout échec y est
  intercepté, `runApp` est toujours atteint et le téléviseur reste noir plutôt que d'afficher
  un menu sans langue.
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
  `GeneratedPluginRegistrant`). *Remplacé par la revue du 12 octobre (m3)*, vérifié contre
  `pubspec.lock` : seul `shared_preferences_foundation.SharedPreferencesPlugin` (2.5.6, classe
  Swift sans nom `@objc` ; `flutter_localization` 0.4.1 y lit la langue stockée).
  `path_provider_foundation` 2.6.0 n'a pas de classe native (FFI), `sqflite` n'est pas une
  dépendance, et le menu du téléviseur n'a **pas de lecteur vidéo** : les relais n'envoient
  que des images (§ 8 bis), la classe de `video_player_avfoundation` 2.11.0 (Swift
  `VideoPlayerPlugin`) n'est pas enregistrée et aucun aperçu n'y démarre. Le test de scope
  épingle ces versions.
- Cycle : création paresseuse à la première connexion avec `menuOnTV`, `FlutterEngineGroup`
  dédié `neostation-external`, `FlutterViewController` placé dans la fenêtre externe ;
  masquée (pas détruite) pendant un jeu ; **détruite** quand le pont RPCS3 s'attache
  (`destroyMenuEngineForMemory`) et recréée après ; détruite à la déconnexion. Depuis la
  revue (m4) : un moteur masqué passe à `AppLifecycleState.hidden` (canal de cycle de vie :
  aucune image dessinée, fonds animés compris), réaffirmé 0,1 s après une activation de
  l'app (le `FlutterViewController` renvoie alors `resumed`), et revient à `resumed`
  (`inactive` si l'app n'est pas active) quand le menu se montre ; il est aussi détruit
  quand le menu sur le téléviseur ou toute la sortie est désactivé.

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
  « enregistré » sans relecture. Depuis la revue (m11) : `init({languageCode, themeName})`,
  appelé par `app_screen.dart` dans `didChangeDependencies` (premier endroit où le
  `ThemeProvider` est lisible ; la dépendance à `Localizations` y fait revenir le
  changement de langue), et `updateMenuEngine({languageCode, themeName})` pour une langue
  (même endroit) ou un thème (`_onThemeChanged`) qui change ; rien n'est envoyé avant
  `init` ni pour une valeur inchangée.
- Réglages › Général (iOS), trois rangées après « Interface 120 Hz » :
  1. « AirPlay et écran externe » — `CustomToggleSwitch` (Enabled) + sous-titre d'état
     (`noExternalScreen` / `externalScreen {width}×{height}` / `gameOnExternal` /
     `mirroringOff`) ; depuis la revue (m2), dans l'ordre : `mirroringOff`,
     `noExternalScreen`, `gameOnExternal`, `unsupportedEngine` **seulement** quand l'état
     natif est `suspended`, `menuOffMirroring` quand le menu sur le téléviseur est coupé hors
     jeu, sinon la ligne neutre `externalScreen` (y compris pendant la recopie qui précède
     la création du moteur de menu) ;
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
  `unsupportedEngine`, `unavailable`, `saveFailed`, `technicalCode` (`{code}`), et
  `menuOffMirroring` ×12 (revue du 12 octobre, m2 : « Menu sur le téléviseur désactivé :
  hors jeu, iOS recopie l'iPhone. »).
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
| `test/external_display_layout_test.mm` + `test/external_display_test.py` | Scale/Frame = 442 pour Fit/Fill ; Original ; SurfaceSize (écran entier) ; Crops ; lecture du SDK de construction ; contrats de source (pas de `makeKeyAndVisible` sur la fenêtre externe, retour avant arrêt, ensemble de scènes et adoption, repli legacy isolé et refusé hors scène, accessoire par sélecteurs conditionné au SDK 27 et à l'absence de scène automatique, passes réentrantes, arguments du moteur de menu, cycle de vie masqué) |
| `test/external_display_scope_test.py` | plugin : aucun pont importé, aucune API dépréciée hors `activateLegacyIfNeeded`, registre de plugins du menu = liste figée vérifiée contre `pubspec.lock` ; fermeture d'imports Dart du point d'entrée du téléviseur sans fichier de la couche base hors des quatre imports partagés épinglés, aucun membre de base atteint ; ponts : `s.dependency 'external_display'` ; `NPController`/`UiRefreshRatePlugin` filtrent `UIWindowSceneSessionRoleApplication` |
| `test/external_display_host_plist_test.py` | configurateur sur une fixture : rôle ajouté, rôle application intact, idempotence, variante `--multiple-scenes` |
| `test/external_display_ui_test.py` | XCTest simulateur (harnais de `dolphin_external_display_ui_test.py`) : connexion, modes, déconnexion, seconde scène en attente puis adoptée, repli legacy refusé hors scène, surface libretro à l'écran entier, échelle seule, appel pendant une passe, choix de format sans activation, régime accessoire (SDK, scène automatique, propriétaire de l'hôte, `isEnabled`) |
| `test/external_display_locale_test.dart` | 12 langues, parité, placeholders, non-anglais, zh_Hant, français du mainteneur |
| `test/external_display_service_test.dart` | canal simulé : état (`suspended` compris), setMode/Enabled/MenuOnTV, SAVE_FAILED jamais « enregistré », événements, configureMenuEngine à l'init avec langue et thème, updateMenuEngine |
| `test/general_settings_external_display_test.dart` | trois rangées iOS, comptage/sélection manette, chip cyclique, avertissement Remplir, lignes d'état (suspension, menu coupé, ligne neutre) |
| `test/external_menu_screen_test.dart` | rendu 1920×1080 sans bande, état reçu par le canal, thème/langue initiaux, arguments du point d'entrée, langue du moteur principal sans écriture des préférences, langue reçue par `menu_locale`, écran noir et `runApp` atteint si la localisation échoue |
| `test/external_display_games_list_test.dart` | relais de la liste des jeux ; `forwardSelection`, renvoi de la sélection quand un téléviseur commence à montrer le menu, ordre, annulation, `systemSelected`, câblage des trois producteurs |
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
  `shared_preferences_foundation.SharedPreferencesPlugin`) — *remplacé par la revue (m3)*,
  voir § 4.
- § 5 libretro : `performSkinLayoutIfNeeded` passe `points:surface.points` ; les zones de
  jeu du skin iPhone sont placées dans la surface TV par `LibretroRenderSurface.h`
  (union des zones mise à l'échelle et centrée) ; skin, overlay et chrome gardent les
  bounds iPhone ; l'attache a lieu à la fin de la présentation (après `viewDidAppear`,
  avant le fil d'émulation), le détachement avant la demande d'arrêt. En portrait sur
  le téléviseur, l'image reste un pilier au format du téléphone (politique du
  coordinateur) — *remplacé par la revue (M3)* : la surface est l'écran entier. Les
  écrans tactiles DS/3DS sont alors opérés à l'aveugle sur le téléphone.
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

- Revue contradictoire du 12 octobre 2026 (correctifs avant l'IPA, rien d'exécuté sur
  l'appareil) :
  - m11 : le second moteur ne touche plus la base (§ 4). Limite consignée : la fermeture
    d'imports Dart de son point d'entrée contient encore quatre imports de la couche base
    venus de fichiers partagés hors du périmètre du chantier —
    `screens/secondary_screen/secondary_screen.dart` → `repositories/retro_achievements_repository.dart`,
    `providers/theme_provider.dart` → `repositories/config_repository.dart` et
    `services/config_service.dart`, `services/logger_service.dart` → `services/config_service.dart`.
    Un import Dart n'exécute rien ; les seuls membres appelés sont
    `RetroAchievementsRepository.getRAApiKey` (stockage sécurisé, pas SQLite, après une
    sélection tactile de succès, impossible sur la scène non interactive), les méthodes
    d'instance de `ThemeProvider` (jamais construit dans le second moteur, qui lit le
    `availableThemes` statique) et `LoggerService.init` (appelé par `main.dart` seulement).
    `test/external_display_scope_test.py` calcule la fermeture, refuse tout nouvel import ou
    membre et vérifie ces trois conditions. Pour une fermeture sans aucun fichier de la
    couche base, il faudrait modifier ces fichiers partagés (injecter le lecteur de clé dans
    `SecondaryScreen`, faire lire `AppThemes` directement par `now_playing_helpers.dart`,
    passer le chemin du journal à `LoggerService`), hors périmètre.
  - M3 / m12 : libretro reçoit l'écran entier dans tous les formats ; Adapter, Remplir et
    Format d'origine ne changent plus rien pour libretro (chaque jeu garde son format). Les
    vues fixes gardent la politique 442 : ARMSX2 tenu en portrait reste un pilier au format
    du téléphone, et Adapter peut couper RPCS3/ARMSX2 quand leur propre réglage de format
    étire l'image au-delà de 16:9 (consigné, non corrigé).
  - M1 / m10 / M2 / m1 / m2 / m4 / m5 / m6 : § 3.3, § 3.5, § 4, § 6.
  - m7–m9 : la grille et le carrousel ne relaient une sélection que tant qu'un téléviseur
    montre le menu (`forwardSelection`) ; grille, carrousel et liste des jeux renvoient leur
    sélection courante quand un téléviseur commence à le montrer
    (`SecondaryDisplayBridge.followSelections`, producteur tenu faiblement, rappel statique
    qui vérifie `mounted` ; carrousel et liste l'annulent dans `dispose`, la grille dont
    l'état vit dans `my_systems_grid.dart`, hors périmètre, est retirée quand son état
    disparaît).

## 9. Ce qui reste à vérifier sur l'iPhone + Apple TV (jamais annoncé avant)

Livraison de la scène externe (iOS 26 / 27, `UIApplicationSupportsMultipleScenes`),
disparition des bandes dans le menu, rendu libretro 1080p et charge GPU, Dolphin/RPCS3/
ARMSX2 agrandis, connexion/déconnexion en jeu, retour au premier plan, mémoire du second
moteur et sa destruction pendant RPCS3, Dusklight/KartPad en recopie, NeoPlay inchangé.
Ajouts de la revue du 12 octobre : SDK lu dans l'Info.plist de l'IPA livrée
(`display.external_build_sdk`, attendu 26 avec Xcode 26.3) et connexion automatique sur
iOS 27 avec ce binaire ; régime accessoire seulement avec un binaire SDK 27 ; seconde scène
en attente puis adoptée ; repli legacy réellement affiché ou refusé ; moteur de menu
`hidden` sans image dessinée pendant un jeu, puis `resumed` ; changement de langue sur le
téléviseur ; rotation de l'iPhone pendant un jeu libretro sur le téléviseur ; sélection
renvoyée à la connexion du téléviseur.
Journal : `display.external_scene_connected`, `display.external_attached:<pont>`,
`display.external_detached:<pont>`, `display.external_legacy`, `display.external_accessory:<statut>`,
`display.external_build_sdk`, `display.external_scene_standby`, `display.external_scene_adopted`,
`display.external_scene_lost`, `display.external_scene_found`, `display.external_legacy_scene`,
`display.legacy_unavailable`, `display.external_apply_passes:`, `display.external_menu_engine:`,
`display.external_menu_plugin:`, `display.external_menu_lifecycle:`, `display.external_menu_language:`.

## 10. Build 449 — l'Apple TV recopie l'interface de NeoStation hors jeu (12 octobre 2026)

**Constat du mainteneur (Build 447/448 installée, iPhone recopié sur une Apple TV).** Pendant
la navigation dans NeoStation, le téléviseur n'affichait que le logo de la console sélectionnée
(par exemple PS2), jamais le menu, la bibliothèque ni les jaquettes ; les jeux s'affichaient
correctement. Exigence : l'Apple TV doit montrer exactement l'interface visible sur l'iPhone,
sans écran de logo fixe, en conservant l'affichage des jeux sur le téléviseur.

**Cause établie dans les sources (pas une hypothèse sur les vidéos).**

1. Le manifeste de l'hôte déclare le rôle `UIWindowSceneSessionRoleExternalDisplayNonInteractive`
   (`build-utils/configure_external_display_ios.py`) ; à la connexion AirPlay, iOS livre la scène à
   `NeoExternalDisplaySceneDelegate`, et le coordinateur y crée une fenêtre. Une fenêtre de l'app
   dans cette scène met fin à la recopie système (documentation `UIScreen.mirrored`, Apple
   Developer Forums 766398 et 815376) : le téléviseur ne montre plus que cette fenêtre.
2. Hors jeu, le coordinateur plaçait dans cette fenêtre le second moteur Flutter
   (`externalDisplayMain` → `ExternalMenuApp` → `SecondaryScreen`), réglage « Afficher le menu sur
   le téléviseur » activé par défaut. `SecondaryScreen` est l'écran secondaire des consoles
   portables Android (logo et fond de la console sélectionnée, illustrations du jeu), alimenté par
   les relais de sélection (§ 8 bis) : ce n'est pas l'interface de NeoStation. D'où « seulement le
   logo de la console » pendant la navigation. Pendant un jeu, la vue de rendu du pont prenait la
   fenêtre : les jeux s'affichaient bien.
3. Les cas « recopie » (sortie désactivée, moteur non pris en charge, menu coupé) masquaient
   seulement la fenêtre (`hidden = YES`) en la laissant dans la scène. Apple indique que la recopie
   revient quand la fenêtre est **retirée** de la scène (`windowScene = nil`) ; le simple masquage
   ne figure pas dans cette consigne et son effet n'est pas documenté (rapport SDL 16161 : une
   fenêtre posée sur la scène AirPlay laisse le téléviseur noir au lieu de la recopie).

Les lecteurs vidéo ne sont pas en cause : `video_player_avfoundation` 2.11.0 laisse
`usesExternalPlaybackWhileExternalScreenIsActive` à sa valeur par défaut (NO), la vidéo reste dans
l'interface recopiée ; aucun autre code natif ne crée de fenêtre sur l'écran externe, et
`sub_screen` 0.1.9 n'a pas d'implémentation iOS.

**Correctif ciblé (aucune refonte, aucun pont modifié).**

- `NeoExternalDisplayCoordinator.m` : hors jeu, rien de propre à NeoStation sur le téléviseur — la
  fenêtre est masquée puis **sort de sa scène** (`placeWindowInScene:NO`), iOS recopie l'iPhone.
  Quand un jeu prend le téléviseur, la fenêtre revient dans la même scène, reprend la taille de la
  scène, puis la vue de rendu y est déplacée (comportement des Builds 442/447 inchangé : Adapter,
  Remplir, Format d'origine, rendu libretro à la résolution du téléviseur, commandes sur l'iPhone).
  Même retour à la recopie pour la sortie désactivée et Dusklight/KartPad. Une fenêtre qui n'a
  jamais été dans une scène (repli legacy, harnais de test) n'est pas touchée.
- Le coordinateur ne crée plus jamais le moteur de menu du téléviseur ; un contrôleur ou un moteur
  laissé par un état antérieur est libéré. `menuOnTV` vaut toujours NO ; la préférence
  `NeoStation.ExternalDisplay.MenuOnTV` n'est plus lue (ni effacée). Régime iOS 27 : l'inscription
  de la racine n'est activée que pendant un jeu.
- Réglages › Général : la rangée « Afficher le menu sur le téléviseur » est retirée (deux rangées au
  lieu de trois). Hors jeu, la ligne d'état affiche l'écran connecté puis « Hors jeu, iOS recopie
  l'interface NeoStation de l'iPhone. » ; textes `description` et `modeAutomaticHelp` corrigés ;
  clés `menuOnTv`, `menuOnTvHelp`, `menuOffMirroring` retirées, `mirroringOutsideGames` ajoutée, en
  douze langues. La phrase Apple TV de NeoPlay (`appleTVOwnWindow`) dit désormais « pendant un jeu,
  plein écran ; hors jeu, iOS recopie l'iPhone ».
- Code dormant laissé en place pour limiter le correctif : `NeoExternalDisplayMenuEngine`, le point
  d'entrée `externalDisplayMain`, `ExternalMenuApp` et les relais de `SecondaryDisplayBridge`
  (inactifs : `forwardsSelections` exige `menuOnTV`). Leur retrait relève d'un nettoyage séparé.

**Limite connue.** La recopie système conserve le format de l'iPhone (≈ 19,5:9) : des bandes
apparaissent autour de l'interface sur un téléviseur 16:9. C'est la contrepartie d'une copie
exacte de l'interface ; les jeux, eux, restent en plein écran sur le téléviseur.

**Tests remplacés et ajoutés (contrats retirés commentés dans chaque fichier).** XCTest simulateur
(`test/external_display_ui_test.py`) : connexion en recopie, fenêtre construite dans sa scène qui la
quitte hors jeu et y revient avant la vue de rendu (suspension, sortie coupée, fin de jeu,
déconnexion), contrôleur de menu jamais montré, régime accessoire sans inscription hors jeu.
Contrats de source (`test/external_display_test.py`, contrôle négatif : le coordinateur de la
Build 448 échoue). Dart : rangées et ligne d'état (`test/general_settings_external_display_test.dart`),
catalogue douze langues (`test/external_display_locale_test.dart`), NeoPlay
(`test/neoplay_locale_test.dart`), compte des rangées (`test/general_settings_ui_refresh_rate_test.dart`).

**À vérifier sur iPhone + Apple TV (rien n'est annoncé avant).** Menu, bibliothèque, jaquettes,
réglages et animations recopiés à l'identique ; aucun écran de logo ; un jeu libretro, Dolphin,
RPCS3 et ARMSX2 en plein écran sur le téléviseur, puis retour à la recopie en quittant le jeu ;
Dusklight/KartPad recopiés ; connexion et déconnexion AirPlay en jeu et hors jeu. Journal :
`display.external_mirroring`, `display.external_window_back_in_scene`,
`display.external_attached:` / `display.external_detached:`.
