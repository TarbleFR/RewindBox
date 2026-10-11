# Interface 120 Hz — Build 438

Réglages › Général › « Interface 120 Hz » (iOS uniquement), description
« Améliore la fluidité des menus et du défilement sur les écrans
compatibles. ». Décision du mainteneur : plan `docs/build438-plan.md`,
section D.

## Faits établis dans les sources

- Toutes les IPA livrées contiennent déjà
  `CADisableMinimumFrameDurationOnPhone = YES` : la clé vient du modèle
  `flutter create` (Flutter 3.47.2) et `flutter build ios --config-only` la
  rajoute si elle manque. La livraison l’exige
  (`retroarch-delivery.yml`, « iPhone ProMotion opt-in missing », depuis la
  Build 362). L’interface Flutter de la 437 demande donc déjà jusqu’à
  120 Hz sur un écran ProMotion, et tous les émulateurs ont été validés avec
  cette clé. Elle n’est **ni modifiée ni réécrite** : l’application ne peut
  pas changer son propre Info.plist signé, et la retirer changerait le
  comportement des émulateurs.
- Dans Flutter 3.47.2, le moteur lit la fréquence voulue par une seule
  méthode de classe, `+[FlutterDisplayLinkManager displayRefreshRate]`
  (`DisplayLinkManager.swift`, classe Swift exposée en Objective-C), appelée
  par `objc_msgSend` depuis quatre fichiers Objective-C++ du moteur :
  `vsync_waiter_ios.mm` (à chaque demande d’image), `FlutterMetalLayer.mm`
  (lien d’affichage du fil principal), `FlutterViewController.mm` (lien de
  correction pendant le toucher, créé seulement au-dessus de 60 Hz) et
  `FlutterKeyboardInsetManager.mm`. Aucun appelant Swift ni aucun émulateur
  de NeoStation ne l’utilise.
- Les émulateurs fixent leur cadence eux-mêmes (Dolphin
  `DolphinFramePacing.mm`, RPCS3 et ARMSX2 par
  `UIScreen.maximumFramesPerSecond`, libretro par son propre
  `CADisplayLink` et `mach_wait_until`, Dusklight, KartPad) : ils ne
  passent pas par cette méthode.

## Fonctionnement

### Natif — `packages/ui_refresh_rate` (nouveau plugin d’espace de travail)

- `UiRefreshRateEngineHook.m` remplace une seule fois l’implémentation de
  `+[FlutterDisplayLinkManager displayRefreshRate]` par
  `method_setImplementation`, après avoir vérifié que la classe existe, que
  la méthode est déclarée par la classe elle-même et que sa signature est
  `d16@0:8` (celle validée avec Flutter 3.47.2). Sinon rien n’est remplacé et
  l’état est `classMissing`, `methodMissing` ou `signatureMismatch`.
- Politique (fonction pure `NeoUiRefreshPolicy`) :
  - activé : valeur du moteur inchangée (comportement de la 437 : plage
    60–120 Hz, préférence 120 Hz, lien mis en pause au repos ; iOS garde sa
    fréquence adaptative et ses limites) ;
  - désactivé : `min(valeur, 60)` ; les liens du moteur demandent
    60/60/60 et le lien de correction du toucher n’est pas créé ;
  - 0, négatif ou NaN : rendu tel quel (replis du moteur).
- Installation dans `+load` de `UiRefreshRatePlugin` (classe référencée par
  `GeneratedPluginRegistrant`, pod statique lié dans l’exécutable Runner),
  donc avant `main()` et avant la création de la première vue Flutter, de
  sa couche Metal et du `VsyncWaiterIOS`. Une installation à
  l’enregistrement du plugin serait trop tardive pour la couche Metal.
- Préférence : `NSUserDefaults` clé `NeoStation.UI.HighRefreshRate.Enabled`.
  Absente : activée (comportement de la 437, aucune réécriture des
  préférences existantes). Lue **une fois par processus**, à la première
  demande du moteur : un changement s’applique au prochain lancement.
- Canal `neostation/ui_refresh_rate` :
  - `getState` → `hookStatus`, `storedEnabled`, `activeEnabled`,
    `screenMaxHz` (`UIScreen.maximumFramesPerSecond` de l’écran de
    NeoStation, jamais plafonné par l’option), `engineTargetHz` (valeur
    reçue par le moteur), `cappedHz` (60), `lowPowerMode`, `thermalState` ;
  - `setEnabled {enabled}` → écrit puis relit la préférence ; erreur
    `SAVE_FAILED` si la relecture diffère ; ne change jamais la valeur du
    processus en cours.
- Jamais touchés : `CADisplayLink`, `UIScreen`, `NSBundle`, l’Info.plist,
  les clés `NeoStation.Dolphin.DisplayTrial.*` et les ponts d’émulation.

### Dart

- `lib/services/ui_refresh_rate_service.dart` (`UiRefreshRateService`,
  remplace l’amorce de la base) : état natif, enregistrement (échec affiché,
  jamais présenté comme enregistré), mesure.
- Disponibilité : point d’accroche installé **et** écran au-dessus de
  60 Hz. En mode Économie d’énergie, iOS peut annoncer 60 Hz pour un écran
  ProMotion : l’option reste alors utilisable avec la mention « Limité à
  60 Hz par le mode Économie d’énergie » (non vérifié sur iPhone).
- Mesure passive (`startProbe()`, déjà appelé par `AppScreen` sur iOS) :
  un seul `SchedulerBinding.addTimingsCallback`, aucun ticker, aucune image
  demandée. `lib/utils/frame_cadence_estimator.dart` découpe les images en
  rafales (écart > 50 ms entre deux vsync), exige 24 intervalles, calcule la
  médiane (`effectiveHz = round(1e6 / médiane)`), le 95e centile, les vsync
  manqués (> 1,5 × médiane) et les dépassements de budget ; mémoire bornée
  (240 intervalles, 8 rafales). Une interface au repos ne produit aucune
  image, donc aucune mesure : c’est voulu.
- Pendant un jeu (`FrontendMediaGate` tenu), les images Flutter sont
  seulement comptées (`framesDuringGame`, journalisé à la fin du jeu) : ≈ 0
  pour les jeux plein écran, davantage derrière Dusklight et KartPad où
  Flutter reste actif. Les images signalées dans la seconde qui suit un
  lancement peuvent y être comptées (le moteur les signale par lots).
- Après le jeu (libération du verrou, ou retour au premier plan après un
  jeu, cas de l’application RetroArch externe), la première rafale
  mesurable dans les 60 s devient « Après le dernier jeu : N Hz ».
- Action « Mesurer » : une animation bornée de 1,5 s (barre de
  progression), puis attente du prochain lot du moteur (≤ 1,2 s, sans
  image) ; la plus longue rafale mesurable est retenue. Sans images
  suffisantes : « Mesure impossible… », jamais une valeur supposée.
- Aucune fréquence n’est affichée sans mesure (« Pas encore mesurée —
  faites défiler une liste ou touchez Mesurer. »).

### Interface

- `widgets/ui_refresh_rate_setting_row.dart`, inséré après « Horloge 12 h »
  dans `general_settings_content.dart` (même position dans `build()`,
  `getItemCount()` et `selectItem()` ; A de la manette inverse le choix).
- Lignes d’état : non disponible (écran « maximum N Hz » ou moteur, avec le
  code technique brut séparé) ; échec d’enregistrement (avec le code
  brut) ; « Prendra effet à la prochaine ouverture de NeoStation, après
  l’avoir fermée depuis le sélecteur d’apps. » ; limite Économie d’énergie
  ou température ; fréquence mesurée ; fréquence après le dernier jeu.
- Textes : `lib/l10n/ui_refresh_rate_locale.dart`, douze langues, chinois
  traditionnel pour le script Hant ou TW/HK/MO.

### Boucle de rendu au repos supprimée

`lib/widgets/notification_bell.dart` : la pulsation de la cloche ne tourne
plus que s’il existe une notification (arrêtée dès qu’il n’y en a plus).
Avant, `repeat()` tournait en permanence alors que l’opacité restait à 1 :
une image à chaque vsync sur tous les écrans avec l’en-tête, y compris
derrière Dusklight et KartPad. Rien ne change visuellement. Les autres
animations (bordure arc-en-ciel, GIF, titres défilants) restent inchangées.

## Ce qui ne change pas

Info.plist, émulateurs (Dolphin, RPCS3, libretro, ARMSX2, Dusklight,
KartPad), vitesse d’émulation et FPS des jeux, bibliothèques, sauvegardes,
configuration SQLite, fichiers verrouillés de la baseline 419, cœur RPCS3.

## Risques

- Point d’accroche privé de Flutter.framework ; un ticket amont
  (flutter#185759) prévoit de supprimer `displayRefreshRate`. Après une
  mise à jour de Flutter, l’option peut devenir « non disponible » (rien
  n’est remplacé) tant que la vérification n’est pas refaite :
  `test/ui_refresh_rate_scope_test.py` (sources du moteur si présentes),
  `ui-refresh-rate-check.yml` (simulateur, vrai `Flutter.xcframework`) et
  les contrôles d’IPA ci-dessous.
- iOS peut toujours limiter l’écran (Économie d’énergie, température,
  réglage d’accessibilité « Limiter la fréquence d’images », sans API
  publique) : l’interface montre les fréquences mesurées.
- `FrameTiming` mesure la cadence des images Flutter, pas le balayage de
  l’écran.
- `native/import-memory-candidate.json` épingle l’ancien SHA-256 de
  `pubspec.yaml` ; ce manifeste dormant échoue déjà sur la base
  (`docs/LEGAL_AND_CREDITS.md`) et n’est pas modifié ici.

## Validation

### Exécuté sous Windows (Flutter 3.47.2)

- `flutter test test/frame_cadence_estimator_test.dart
  test/ui_refresh_rate_service_test.dart test/ui_refresh_rate_locale_test.dart
  test/general_settings_ui_refresh_rate_test.dart
  test/notification_bell_idle_test.dart`
- `python test/ui_refresh_rate_scope_test.py`,
  `python test/localization_12_locale_coverage_test.py`,
  `python test/retroarch_baseline_scope_test.py`
- `notification_bell_idle_test.dart` échoue sur le code de la base
  (« pumpAndSettle timed out ») et passe avec la correction.

### macOS (CI, `workflow_dispatch --ref Claude`)

- `ui-refresh-rate-check.yml` : `flutter precache --ios`, garde de
  périmètre, compilation iPhone arm64 `-Wall -Werror` des deux sources, puis
  XCTest sur simulateur avec le vrai `Flutter.xcframework` : signature du
  point d’accroche, installation par `+load` avant `main()`, 60 Hz si
  désactivé et valeur d’origine si activé, plage du lien de
  `FlutterMetalLayer` 60/60/60 ou 60/120/120, contrôles négatifs
  (`CADisplayLink`, `UIScreen`, `NSBundle` intacts, clé Info.plist à YES),
  canal `getState`/`setEnabled`.
- À ajouter à `retroarch-delivery.yml` (réservé à l’intégration) : les tests
  Dart ci-dessus dans la liste `flutter test`, la garde de périmètre dans
  l’étape des gardes Python, et dans les deux blocs d’assertions d’IPA :
  `Frameworks/Flutter.framework/Flutter` contient
  `FlutterDisplayLinkManager` et `displayRefreshRate`, l’exécutable Runner
  contient `NeoStation.UI.HighRefreshRate.Enabled` et `UiRefreshRatePlugin`.

### iPhone uniquement (à confirmer par le mainteneur)

1. Option activée (défaut) : faire défiler la bibliothèque, la recherche,
   les réglages ; « Fréquence mesurée » attendue ≈ 120 Hz sur iPhone
   ProMotion (comme la 437). Contrôle indépendant possible par le HUD Metal
   (Réglages › Développeur).
2. Désactiver, fermer NeoStation depuis le sélecteur d’apps, rouvrir :
   ≈ 60 Hz mesurés ; réactiver, relancer : ≈ 120 Hz.
3. Mode Économie d’énergie, température, « Limiter la fréquence
   d’images » : mention affichée et ≈ 60 Hz mesurés.
4. Retour d’un jeu (libretro, RPCS3, Dolphin, ARMSX2, Dusklight, KartPad,
   RetroArch externe) : « Après le dernier jeu » égal à la mesure d’avant ;
   journal `framesDuringGame` ≈ 0 pour les jeux plein écran.
5. Émulateurs identiques option activée et désactivée, même scène :
   Dolphin (export « Affichage et fluidité » : requestedHz,
   displayLinkCallbackHz), RPCS3 (FPS, God of War III), libretro (FPS du
   cœur, avance rapide), ARMSX2, Dusklight (30/max), KartPad (120/180).
6. Dix minutes au repos sur une liste de jeux : chaleur et batterie, avec la
   cloche sans notification.
7. iPhone sans ProMotion si disponible : « Non disponible sur cet écran
   (maximum 60 Hz). ».
