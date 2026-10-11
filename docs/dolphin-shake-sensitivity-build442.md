# Build 442 — Secousse du téléphone (Wii / Dolphin intégré)

Demande du mainteneur du 11 octobre 2026 : la secousse du téléphone manque de
sensibilité et de régularité (« je dois secouer l'iPhone plusieurs fois de
manière aléatoire »). Objectif : une secousse légère et volontaire reconnue
rapidement et de manière reproductible, un réglage simple de sensibilité, des
gestes successifs reconnus chacun, sans double action involontaire ni
déclenchement par les mouvements ordinaires du téléphone.

## 1. Chaîne vérifiée et causes trouvées dans les sources (Build 440)

Chaîne : CoreMotion (`deviceMotion`, 100 Hz, file série dédiée) →
`DolphinShakeDetector` → `DolphinPhoneShake` (propriétaire capteur) →
`DolphinShakeInput` (arbitre téléphone/bouton tactile) →
`neostation_dolphin_touch_event` (Touchscreen 132–134 du port 4, liées à
`Shake/X|Y|Z` de la première Wiimote) → secousse émulée de Dolphin.

Causes confirmées dans `DolphinShakeDetector.swift` et `DolphinPhoneShake.swift`
de la 440 :

| Défaut | Effet observé |
| --- | --- |
| Seuil unique de 0,90 g sur la norme de l'accélération utilisateur (gravité retirée). | Une secousse légère (0,5–0,8 g de pic) n'atteint jamais le seuil : il faut secouer fort. |
| Après un déclenchement, réarmement seulement quand la norme repasse sous 0,30 g, plus un délai fixe de 300 ms. | Pendant une secousse continue, un seul déclenchement par 300 ms au mieux ; des gestes rapprochés sont perdus. |
| Chaque déclenchement n'écrit qu'une impulsion fixe de 120 ms. | La secousse émulée de Dolphin (2 Hz par défaut, 250 ms par demi-course) démarre à peine : le jeu voit un mouvement partiel, d'où des secousses « non prises ». |
| Échantillons rejetés au-delà de 100 ms d'ancienneté. | Une livraison CoreMotion retardée (charge, lot) perd le geste. |
| Déclenchement sur un seul échantillon. | Incompatible avec un seuil plus bas : un coup de doigt sur l'écran (pointe de 10 ms) aurait déclenché. |

Les axes et l'orientation ne sont pas en cause : la norme du vecteur est
indépendante de l'orientation, et le pointeur IR (rotation du poignet) produit
moins de 0,3 g en accélération linéaire. L'arbitre, le routage vers Dolphin et
les entrées 132–134 sont inchangés et restent ceux validés en 440.

## 2. Nouveau détecteur (`DolphinShakeDetector.swift`)

- **Sensibilité** `DolphinShakeSensitivity` : `low` (0,90 g, comportement 440),
  `medium` (0,55 g, défaut), `high` (0,35 g) ; chaque niveau a un seuil de
  maintien plus bas (0,45 / 0,30 / 0,20 g). Préférence
  `NeoStation.Dolphin.PhoneShake.Sensitivity` (`low|medium|high`), valeur
  inconnue = `medium`.
- **Appui** : deux échantillons consécutifs (20 ms à 100 Hz) au-dessus du
  seuil, ou un seul échantillon à deux fois le seuil (coup de poignet net).
  Une pointe isolée de 10 ms ne déclenche jamais.
- **Maintien** : les trois entrées restent pressées tant que le téléphone
  bouge (échantillons au-dessus du seuil de maintien) ; Dolphin secoue la
  Wiimote émulée pendant tout l'appui, comme pour le bouton tactile. Les
  passages par zéro à l'intérieur d'un geste ne coupent pas l'appui.
- **Relâchement** (`DolphinPhoneShake.swift`) : 100 ms après le dernier
  échantillon au-dessus du seuil de maintien, jamais avant 120 ms d'appui
  (impulsion minimale commune au bouton tactile). Le relâchement est un
  minuteur sur la file d'entrée : un capteur qui se tait relâche quand même,
  et le fil principal n'intervient pas. Au-delà de 3 s de maintien continu,
  relâchement puis réarmement (aucun capteur bruyant ne peut tenir la secousse
  indéfiniment).
- **Gestes successifs** : nouvel appui possible 80 ms après un relâchement
  (le temps que Dolphin lise le relâchement) ; le délai fixe de 300 ms et le
  réarmement sous 0,30 g disparaissent.
- **Fraîcheur** : échantillons acceptés jusqu'à 250 ms d'ancienneté (au lieu
  de 100 ms) ; un retard plus grand reste un arriéré ignoré.
- Latence de reconnaissance : second échantillon confirmé (≈ 20 ms) plus la
  latence CoreMotion, sans aucun traitement sur le fil principal.

Ce que cela change pour le jeu : une secousse légère donne un appui d'environ
150–300 ms (la durée réelle du geste), une secousse continue un appui continu,
et chaque geste distinct un appui distinct. Aucune valeur de physique, aucun
cheat et aucun réglage d'émulation ne sont modifiés ; la secousse émulée reste
celle du profil Dolphin.

## 3. Réglages

- **Menu en jeu › Commandes** (Wii seulement) : nouvelle ligne « Sensibilité
  de la secousse » sous « Secouer l'appareil — Wiimote » ; un appui passe
  Faible → Moyenne → Élevée. Aide en pied de section. Aucune requête n'atteint
  le cœur ; la surcouche relit le niveau sur la notification déjà utilisée par
  l'interrupteur, sans redémarrer le capteur.
- **Réglages › Systèmes › Wii › onglet Émulateurs** (Flutter) : section
  « Mouvements de la Wiimote » avec l'interrupteur « Secouer le téléphone pour
  secouer la Wiimote » et le choix Faible / Moyenne / Élevée
  (`lib/widgets/dolphin_wii_motion_panel.dart`). Les valeurs passent par le
  canal du pont (`phoneShakeSettings` / `setPhoneShakeSettings`, préférences
  natives uniquement) ; une session en cours applique le changement
  immédiatement. GameCube n'affiche rien.
- Préférences partagées : `DolphinPhoneShakePreferences.h` (menu natif et
  canal Flutter), mêmes clés et mêmes valeurs brutes que le code Swift.

## 4. Traductions

Huit textes nouveaux dans `lib/l10n/dolphin_shake_locale.dart` (12 langues :
en, es, ru, zh, zh_Hant, pt, fr, de, it, id, ja, ko), transmis au menu natif par
les libellés de session. `native/dolphin_motion/strings.json` et son en-tête
généré restent verrouillés et inchangés.

## 5. Vérifications

Exécuté sous Windows (sans compilateur Swift ni Xcode) :

- `flutter test test/dolphin_shake_locale_test.dart test/dolphin_wii_motion_panel_test.dart` :
  22 réussis (clés, substitutions, chinois traditionnel, panneau : lecture,
  interrupteur, niveau, écriture refusée, pont absent) ;
- `python test/dolphin_shake_wiring_test.py` (détecteur Foundation seule,
  clés partagées, menu sans copie des helpers) ;
- `flutter analyze --no-fatal-infos` : aucune erreur ni avertissement.

Sur macOS CI (`dolphin-motion-check.yml`, `workflow_dispatch --ref Claude`) :

- `test/dolphin_phone_shake_test.py` réécrit : préréglages, confirmation sur
  deux échantillons, échantillon fort, pointe de 10 ms refusée, maintien tant
  que le mouvement continue, relâchement au calme, gestes successifs, maximum
  de 3 s, changement de sensibilité à chaud sans redémarrage du capteur, et
  tous les cas de cycle de vie de la 440 (fil principal bloqué, arrêt, erreur
  capteur, préparation, routage) ;
- `test/dolphin_touch_shake_ui_test.py` : ligne Sensibilité dans les 12
  langues, cycle Moyenne → Élevée → Faible → Moyenne écrit la préférence,
  aucune requête au cœur ;
- vérification de type Swift iOS et syntaxe Objective-C++ des fichiers
  modifiés.

À valider sur l'iPhone (aucun de ces tests ne le démontre) : secousses
légères successives reconnues chacune (Super Mario Galaxy, New Super Mario
Bros. Wii, Donkey Kong Country Returns, Mario Kart Wii), absence de
déclenchement en marchant ou en visant avec le pointeur, niveaux Faible et
Élevée, réglage depuis l'onglet Wii et depuis le menu en jeu, manette MFi
connectée.
