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

## Vérifications et résultats

Voir la section « Résultats » ajoutée à la fin de ce document après les
exécutions locales et CI.
