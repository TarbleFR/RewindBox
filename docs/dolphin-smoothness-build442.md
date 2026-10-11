# Build 442 — Dolphin intégré : stabilité et saccades (analyse et changements hôte)

Demande du mainteneur du 11 octobre 2026 : rendre les jeux Wii et GameCube
plus réguliers, notamment en session prolongée ; mesurer les temps d'image et
les pics plutôt que la moyenne ; ne pas masquer les problèmes par la
résolution, le saut d'images ou des hacks. Ce document sépare ce qui est
établi dans les sources, ce qui est changé dans la Build 442, ce qui reste une
hypothèse et ce qui doit être mesuré sur l'iPhone. Aucune mesure sur appareil
n'a été faite ici : les gains ne sont pas démontrés.

## 1. Périmètre : le cœur Dolphin est verrouillé

Le cœur (`DolphinCore.framework`, DolphiniOS `7cac5416` + 
`build-utils/patch_dolphin_internal_core_v2.py`) est conservé à l'identité
validée de la Build 350 : `retroarch-delivery.yml` refuse toute différence du
script de patch et de `packages/dolphin_internal_bridge/core/` depuis
`ae7d46f9`. Compilation des shaders, JIT, synchronisation CPU/GPU, audio,
cache de textures et fuites internes du cœur ne peuvent donc être modifiés
dans cette build sans reconstruction du cœur, qui exigerait une décision
séparée du mainteneur (lien établi entre un défaut et le cœur, rebuild
`dolphin-core.yml`, nouveau pin). Les changements ci-dessous sont
uniquement côté hôte (Objective-C/Swift) et réglages.

## 2. Ce qui est établi dans les sources

- **Shaders** : le profil par défaut (« Metal + hybrid ») demande
  `ShaderCompilationMode = 2` (ubershaders asynchrones) et le cœur active
  `ShaderCache` et `WaitForShadersBeforeStarting`. Les pipelines jamais vus
  restent compilés à la volée par Metal (`newLibraryWithSource`), mis en
  cache par iOS entre deux lancements du même jeu : le premier lancement d'un
  jeu ou d'une scène reste plus saccadé que les suivants. Rien d'autre n'est
  disponible côté hôte sans le cœur.
- **Fils critiques** : la secousse du téléphone travaille sur une file série
  dédiée (`userInteractive`) et n'écrit dans le cœur qu'aux transitions
  d'appui, sous le verrou d'état des manettes déjà utilisé par le pointeur
  tactile. Le moniteur 500 ms ne rafraîchit les manettes qu'au changement
  (profil « Original » excepté) et `neostation_dolphin_refresh_controllers`
  rend la main immédiatement sans changement de périphérique. La trace de
  performance lit des atomiques (`PerformanceMetrics`), sans verrou ni
  lecture GPU. Aucune de ces fonctions NeoStation n'est identifiée comme
  source de saccade.
- **Cadence d'affichage** : Dolphin présente chaque image dès qu'elle est
  prête (`presentDrawable`, sans horodatage), sans alignement sur le
  balayage ; le pacing de la 362 demandait par défaut un lien d'affichage à
  120 Hz. À 120 Hz, une image de jeu à 60 FPS couvre deux rafraîchissements
  et toute gigue de présentation de quelques millisecondes se traduit par des
  durées d'affichage de 8,3 / 16,7 / 25 ms : une saccade visible alors que
  la moyenne reste à 60 FPS. À 60 Hz, la même gigue est absorbée dans la
  fenêtre de 16,7 ms. Ceci est un raisonnement sur le modèle de présentation,
  pas une mesure.
- **Sessions prolongées** : la seule cause hôte identifiable est thermique
  (`NSProcessInfo.thermalState`) ; le pacing abaisse déjà le lien à 60 Hz en
  état « sérieux », et l'état est tracé.
- **Transitions / ressources** : la fermeture attend la fin de la file
  d'exécution, restaure l'audio et détruit le contrôleur après rejet ; les
  observateurs (contrôleur, pacing, surcouche, secousse) sont retirés à la
  destruction. Aucune rétention hôte identifiée entre deux jeux. La mémoire
  retenue par le cœur après `neostation_dolphin_stop` n'est pas observable
  depuis l'hôte sans mesure.

## 3. Changements de la Build 442

1. **Défaut d'affichage à 60 Hz** (`DolphinFramePacing.mm`) : « Fréquence
   d'affichage » vaut 60 Hz par défaut ; 120 Hz et Automatique restent au
   choix, effet immédiat en jeu, pour comparer sur l'iPhone. Aucun changement
   de vitesse d'émulation, de résolution ni de saut d'image. Aide ajoutée
   (« hzDefaultHelp ») en 12 langues.
2. **Mesure des pics** : un sous-échantillonneur à 10 Hz sur la file
   d'exécution relit `lastFrameTimeMs` du cœur (atomiques) quand la trace ou
   la surcouche est active, ignore les valeurs répétées (cœur en pause) et
   alimente par ligne de trace (2 Hz) : `frameSamples`, `frameTimeMaxMs`,
   `frameTimeMinMs`, `slowSamples` (≥ 25 ms), `verySlowSamples` (≥ 50 ms),
   `memoryFootprintMB` (`phys_footprint`), `thermalState`,
   `externalDisplayActive` ; et en résumé de session : pire image,
   totaux, seuils. Un blocage de plus de 100 ms est toujours vu, un plus
   court avec une probabilité partielle : c'est un indicateur de saccades,
   pas une trace par image (le cœur verrouillé n'expose pas l'historique
   des images). Export JSON (schéma 2) inchangé dans son usage.
3. **Surcouche de performance** : ligne « Pic xx ms · Thermique état ·
   Mémoire xxx MB » sous la résolution interne (12 langues, catalogue Dart
   `dolphin_display_locale.dart`).
4. **Secousse du téléphone** : le nouveau détecteur ne crée pas plus de
   travail (100 Hz inchangés, un minuteur de relâchement au lieu d'un par
   échantillon). Voir `docs/dolphin-shake-sensitivity-build442.md`.
5. **Écran externe** : la vue Metal est déplacée, jamais redimensionnée ;
   la présentation de Dolphin n'est pas touchée. Voir
   `docs/dolphin-external-display-build442.md`.

Non fait, volontairement : aucune baisse automatique de résolution, aucun
hack d'émulation, aucune modification des réglages Dolphin existants.

## 4. Comment mesurer avant/après sur l'iPhone

Même appareil, même jeu, même scène, mêmes réglages ; distinguer premier
lancement (shaders non vus) et relancement (cache constitué) ; session courte
puis prolongée (≥ 20 min) ; avec et sans AirPlay.

1. Menu en jeu › Graphismes › Affichage et fluidité › « Mémoire de
   diagnostic » activée (défaut) ; jouer la scène ; « Exporter le
   diagnostic ».
2. Dans le JSON : `summary.worstFrameTimeMs`, `slowSampleTotal`,
   `verySlowSampleTotal`, `frameSampleTotal`, et par ligne `frameTimeMaxMs`,
   `slowSamples`, `thermalState`, `memoryFootprintMB`. Comparer 60 Hz et
   120 Hz (changement immédiat) sur la même scène.
3. Surcouche (bouton graphique) : lire « Pic » et l'état thermique pendant
   une session prolongée.
4. Transitions : lancer, pause, reprise, fermer, relancer, alterner Wii et
   GameCube ; noter `memoryFootprintMB` au début de chaque session.

## 5. Vérifications effectuées

- Windows : `flutter analyze` sans erreur ; contrats Python ; tests Dart du
  catalogue et du panneau Wii.
- macOS CI (`dolphin-motion-check.yml`) : `dolphin_external_display_ui_test.py`
  vérifie le défaut 60 Hz, les compteurs (`recordFrameTimeMs` : total,
  lents, très lents, pire image ; réinitialisation par ligne, totaux
  conservés) ; syntaxe Objective-C++ des fichiers modifiés.
- Non vérifié : fluidité sur iPhone, AirPlay, sessions prolongées, mémoire
  réelle. Les gains éventuels de la cadence 60 Hz restent à confirmer par le
  mainteneur avec la procédure ci-dessus.
