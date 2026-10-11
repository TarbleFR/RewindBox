# Build 442 — cadrage, décisions et vérifications (11 octobre 2026, soir)

Demande du mainteneur du 11 octobre 2026 (soir), branche `Claude` : quatre
défauts à corriger dans le projet existant, avec des modifications
fonctionnelles et vérifiées, traduites dans les douze langues. La candidate
est la **Build 442**, construite par-dessus la Build 441 (NeoSwap, autre
session, `e1283fe5`). Cœur Dolphin (identité 350) et Core RPCS3 (pin 441)
inchangés.

## 1. Secousse du téléphone — Wii / Dolphin intégré

Causes confirmées dans les sources 440 : seuil unique de 0,90 g, impulsion
fixe de 120 ms, réarmement sous 0,30 g plus 300 ms de délai, échantillons
rejetés au-delà de 100 ms, déclenchement sur un seul échantillon. Décisions :
détecteur à trois niveaux (Faible = 440, Moyenne par défaut, Élevée),
confirmation sur deux échantillons (ou un fort), maintien tant que le
téléphone bouge, relâchement au calme, gestes successifs 80 ms après un
relâchement, réglage dans le menu Commandes en jeu et dans Réglages ›
Systèmes › Wii › Émulateurs. Détail : `docs/dolphin-shake-sensitivity-build442.md`.

## 2. Stabilité et saccades — Dolphin intégré

Le cœur verrouillé interdit les changements de shaders, JIT, synchronisation
et audio dans cette build. Côté hôte : fréquence d'affichage 60 Hz par défaut
(raisonnement de cadence documenté, non mesuré), mesure des pics (10 Hz,
compteurs par ligne de trace et par session, mémoire, thermique), surcouche
enrichie. Aucune baisse automatique de résolution ni hack. Procédure de
comparaison avant/après sur iPhone : `docs/dolphin-smoothness-build442.md`.

## 3. Sauvegardes RPCS3 (savedata)

Causes confirmées dans les sources : consommation silencieuse du dossier
Import et suppression du dossier Export à chaque démarrage, aucune
validation ni confirmation, aucun ZIP, messages génériques. Décisions : export
ZIP dans Fichiers › NeoStation › RPCS3 › Export › Game Saves avec partage ;
import depuis Import › Game Saves (dossier ou ZIP, dossier parent accepté),
depuis un ZIP ou un dossier choisi ; validation PARAM.SFO, noms, traversée,
taille ; confirmation avant remplacement avec copie dans
`NeoStation/RPCS3/SaveBackups` ; refus pendant qu'un jeu tourne ; chemins
résolus à l'appel (`Data`, `vfs.yml`, utilisateur `00000001`). Le démarrage ne
touche plus aux fichiers (`lib/main.dart` verrouillé, inchangé). Détail :
`docs/rpcs3-save-exchange-build442.md`.

## 4. AirPlay / Apple TV

Origine des bandes établie (recopie au format iPhone, puis bandes latérales
du jeu). Décision : sortie dédiée à l'écran externe pour Dolphin
(`DolphinExternalDisplay`), modes Désactivé / Adapter (défaut) / Remplir
(recadrage annoncé), commandes sur l'iPhone, aucun redimensionnement de la
surface. Les autres moteurs gardent la recopie dans cette build. Détail :
`docs/dolphin-external-display-build442.md`.

## Fichiers partagés et livraison

- `build-utils/verify_delivery_reuse.py` : `BUILD442_DELTA`.
- `.github/workflows/retroarch-delivery.yml` : tests Dart et Python de la
  442 ajoutés au job `checks` ; `dolphin-motion-check.yml` : placement
  externe, syntaxe des fichiers Objective-C++ modifiés, harnais simulateur
  `dolphin_external_display_ui_test.py` ; `dolphin-pacing-check.yml` : syntaxe
  et placement (ce workflow reste bloqué avant ses tests par le verrou NeoSwap
  connu depuis la 440).
- `test/localization_12_locale_coverage_test.py` : catalogues
  `dolphin_display_locale.dart` et `rpcs3_saves_locale.dart`.

## Vérifications et résultats (11 octobre 2026, soir)

Windows (Flutter 3.47.2, Python 3.12, sans Xcode ni Swift) :

- `flutter analyze --no-fatal-infos` : aucune erreur ni avertissement
  (52 informations préexistantes) ;
- `flutter test` ciblé : 148 réussis (`rpcs3_save_exchange_service_test`,
  `rpcs3_saves_locale_test`, `rpcs3_save_export_contract_test`,
  `rpcs3_internal_integration_test`, `rpcs3_firmware_library_test`,
  `rpcs3_rap_import_menu_test`, `rpcs3_rap_licence_service_test`,
  `rpcs3_lazy_load_contract_test`, `dolphin_shake_locale_test`,
  `dolphin_wii_motion_panel_test`, `rpcs3_embedded_identity_test`) et
  52 réussis pour les tests du dialogue de réglages système
  (`armsx2_embedded_library_contract_test`, `gamepad_settings_scrolling_test`,
  `libretro_engine_settings_test`, `rpcs3_embedded_identity_test`) ;
- contrats Python : `rpcs3_ui_status_cleanup_test`,
  `diagnostics_files_workspace_test`, `localization_12_locale_coverage_test`
  (12 langues, 917 clés AppLocale), `dolphin_shake_wiring_test`,
  `retroarch_baseline_scope_test`, `cheats_media_source_contract_test`,
  `ui_refresh_rate_scope_test`, `dolphin_external_display_test` (contrats de
  source ; exécution sur macOS) : réussis ;
- couverture du `DELTA` : chaque entrée modifiée depuis la référence est
  enregistrée (`BUILD442_DELTA`, 48 fichiers ; vérification hors ligne par
  comparaison Git, le vérificateur complet exigeant les modes de fichier
  POSIX).

macOS CI, `dolphin-motion-check.yml` (`workflow_dispatch --ref Claude`) :

| Run | Révision | Résultat |
|---|---|---|
| `38169421678`, `38169517739`, `38169592767` | `2f85ad47`, `0696f243`, `7a353ef0` | échecs du harnais (espacement des opérateurs Swift dans le test, non dans le produit) |
| `38169663106` | `39dabcf8` | harnais secousse vert (352 assertions) ; harnais tactile interrompu sans message (relancé, vert ensuite : aucune modification de l’arbitre) |
| `38169810165` | `01d7b03d` | harnais Swift, placement (24), vérification de type iOS verts ; harnais simulateur sans CoreGraphics lié |
| `38170060946` | `71a00189` | **réussi** : 352 + 47 + 24 assertions, routage, localisations, vérification de type Swift/Objective-C++, simulateur iOS : 4 tests écran externe/réglages/compteurs et 11 tests bouton tactile/ligne Commandes (dont la ligne Sensibilité en 12 langues), 0 échec |

`dolphin-pacing-check.yml` n'a pas été lancé : il échoue avant ses tests sur
le verrou NeoSwap connu depuis la Build 440 ; ses contrôles de syntaxe et le
test de placement sont couverts par `dolphin-motion-check.yml`.

Les révisions `0696f243` à `71a00189` ne diffèrent de `2f85ad47` que par
`test/dolphin_phone_shake_test.py`, `test/dolphin_touch_shake_test.py` et
`test/dolphin_external_display_ui_test.py` : aucune entrée de l'application
ne change.

## Livraison (11 octobre 2026, soir)

| Run | Révision | Résultat |
|---|---|---|
| `38170075778` | `71a00189` | `checks` réussi (analyse Flutter, tests Dart ciblés, contrats Python exécutés sur cette révision) ; `native` réussi ; `cold` échoué à la compilation : `DolphinExternalDisplay.h`, en-tête public du pod, incluait l'en-tête privé `DolphinExternalDisplayLayout.h` (module Swift `dolphin_internal_bridge` non construit) |
| `38170927050` | `e8808dd3` | **réussi** : `checks` réutilise l'évidence Dart de `38170075778` (entrées Dart identiques, seul le podspec diffère ; les contrats Python sont ré-exécutés), `native` réussi, `cold` réussi |

`e8808dd3` ne diffère de `71a00189` que par
`packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec`
(les deux en-têtes de l'écran externe deviennent privés) ; aucune source
Dart, Swift ou Objective-C ne change.

IPA livrée : `NeoStation-Build442-e8808dd32301f71fdd421a70c0ac6be2ed6fba47-cold.ipa`,
artefact chiffré `NeoStation-Build-442-e8808dd32301f71fdd421a70c0ac6be2ed6fba47-cold`,
SHA-256 `64f3e64d339881703c363be041d09bfd6349f168af599b4e38608184b1e4cbae`,
207 398 424 octets, signature ad hoc de préparation (re-signature Apple par
SideStore requise). Vérifié après déchiffrement : empreinte identique à
`SHA256SUMS` et à `signed-payload-identity.json` ; le pont
`dolphin_internal_bridge` contient les marqueurs
`NeoStation.Dolphin.ExternalDisplay.Mode`,
`NeoStation.Dolphin.PhoneShake.Sensitivity`, `dolphin.externalDisplay.hint`
et `dolphinPhoneShakeSensitivity` ; l'instantané Dart contient les
marqueurs de l'échange de sauvegardes (`RPCS3-saves-`, `SaveBackups`,
`.neostation-save-import-`). Le cœur `DolphinCore` est vérifié à son identité
de baseline par le workflow avant scellement. Aucun essai sur iPhone ni
Apple TV : les validations attendues par le mainteneur sont listées dans les
quatre documents de la 442.
