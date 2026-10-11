# Build 442 — AirPlay / Apple TV : sortie dédiée à l'écran externe (Dolphin intégré)

Demande du mainteneur du 11 octobre 2026 : des bandes noires en haut et en bas
du téléviseur avec AirPlay vers une Apple TV ; exploiter la surface du
téléviseur, proposer « Adapter » et « Remplir », ne pas déformer l'image par
défaut, garder les commandes sur l'iPhone.

## 1. Origine des bandes

- **Recopie de l'écran** : avec la recopie AirPlay (ou un adaptateur sans
  fenêtre dédiée), le téléviseur reçoit l'écran entier de l'iPhone, au format
  de l'iPhone (≈ 2,17:1 en paysage sur un iPhone 15). Sur un téléviseur 16:9
  (1,78:1), iOS ajoute des bandes en haut et en bas : c'est la cause des
  bandes signalées.
- **Format du jeu** : à l'intérieur de l'écran iPhone, Dolphin dessine le jeu
  à la hauteur complète de la surface et ajoute des bandes **latérales** (un
  jeu 16:9 ou 4:3 est moins large que l'iPhone). Recopiées, ces bandes
  s'ajoutent aux précédentes : un jeu 16:9 n'occupe qu'environ les deux tiers
  de la surface du téléviseur.
- **NeoStation** : la vue Metal de Dolphin occupe toute la vue du contrôleur,
  sans marge ni zone sûre ; aucune marge d'application n'est en cause.
- **Téléviseur / Apple TV** : hors de portée de l'app (sur-balayage, zoom du
  téléviseur) ; non modifié.

## 2. Ce que fait la Build 442

`DolphinExternalDisplay` (`packages/dolphin_internal_bridge/ios/Classes/`) :

- Quand un écran externe est connecté (`UIScreen` autre que l'écran principal :
  AirPlay, adaptateur) et que le mode n'est pas « Désactivé », la **vue Metal
  de la session** est déplacée dans une fenêtre créée sur cet écran, et les
  commandes tactiles, le bouton de menu, la surcouche de performance restent
  sur l'iPhone, qui affiche « Jeu affiché sur l'écran externe » sur fond noir.
  iOS passe alors de la recopie à l'affichage étendu : le téléviseur ne
  reçoit que la fenêtre du jeu.
- **Aucun changement du cœur Dolphin ni de la surface** : Dolphin continue de
  dessiner dans le même `CAMetalLayer`, à la taille de l'iPhone qu'il a reçue
  au lancement (le cœur verrouillé n'expose pas de redimensionnement). La vue
  garde ses limites et son échelle (`autoResizeDrawable` coupé pendant le
  déplacement, `contentScaleFactor` conservé) ; seule une transformation
  d'échelle la place sur le téléviseur.
- **Adapter** (défaut) : la hauteur de la surface iPhone remplit la hauteur du
  téléviseur. Comme Dolphin remplit cette hauteur avec le jeu et ne
  letterboxe que sur les côtés, le téléviseur ne perd que les bandes noires
  latérales propres à l'iPhone : un jeu 16:9 remplit exactement un téléviseur
  16:9, un jeu 4:3 est centré avec des bandes latérales correctes. Sur un
  écran plus étroit que 16:9, l'échelle est limitée par la largeur pour ne
  jamais couper une image 16:9. Aucune déformation.
- **Remplir** : agrandit une image 4:3 à la largeur du téléviseur (4/3 de
  « Adapter », jamais plus) et coupe le haut et le bas de 25 %. L'app ne
  connaît pas le format effectif du jeu (choisi par Dolphin selon le réglage
  « Format » et le jeu) : une image 16:9 est coupée aussi. Ce recadrage est
  annoncé dans le libellé et l'aide ; ce mode n'est jamais le défaut.
- **Désactivé** : comportement précédent (recopie de l'iPhone, bandes
  comprises).
- Réglage dans le menu en jeu › Graphismes › « Affichage et fluidité » :
  ligne « Écran externe (AirPlay) » (Désactivé / Adapter / Remplir), effet
  immédiat par notification ; état « Aucun écran externe connecté » ou « Jeu
  affiché sur l'écran externe ». Préférence
  `NeoStation.Dolphin.ExternalDisplay.Mode` (0/1/2).
- Connexion et déconnexion pendant le jeu : observées
  (`UIScreenDidConnect/Disconnect/ModeDidChange`, retour au premier plan) ;
  la déconnexion ramène la vue Metal sur l'iPhone (index 0, sous les
  commandes), transformation identité, cadre complet. À la fermeture du jeu,
  la vue revient sur l'iPhone **avant** l'arrêt du cœur et la fermeture du
  contrôleur, puis la fenêtre externe est libérée.
- Le menu en jeu s'ouvre sur l'iPhone ; le téléviseur garde l'image (en
  pause). Le lien d'affichage de cadence reste attaché à l'écran de l'iPhone.
- Limites connues : le format « Étirer » de Dolphin, qui étire l'image sur
  toute la largeur de l'iPhone, est recadré aux côtés en mode Adapter ; la
  qualité est celle de la résolution interne choisie, le rendu restant à la
  taille logique de l'iPhone. RPCS3, ARMSX2, Dusklight, Kartpad et le pont
  libretro ne sont pas concernés par cette build (même architecture possible,
  vue par vue, décision séparée).

## 3. Traductions

Huit textes dans `DolphinPacingLabels.h` (catalogue natif, 12 langues),
dont le libellé de l'iPhone pendant l'affichage externe.

## 4. Vérifications

Sous Windows : contrats de source de `test/dolphin_external_display_test.py`
(en-tête de placement sans UIKit, déplacement par transformation sans
`drawableSize` ni `ResizeSurface`, retour de la vue avant l'arrêt du cœur).

Sur macOS CI (`dolphin-motion-check.yml`, et `dolphin-pacing-check.yml`) :

- `test/dolphin_external_display_test.mm` exécute le placement : Adapter =
  hauteur du téléviseur, un jeu 16:9 remplit exactement 1920 px, un jeu 4:3
  est à 1440 px, seul le débord des bandes latérales de l'iPhone dépasse ;
  Remplir = 4/3 d'Adapter, 25 % coupés ; écran 4:3 jamais coupé en largeur ;
  tailles dégénérées ;
- `test/dolphin_external_display_ui_test.py` (simulateur iOS, vrai
  `DolphinExternalDisplay`, `DolphinFramePacing` et menu) : déplacement de la
  seule vue de rendu, commandes restées sur l'iPhone, échelle et centre,
  retour à l'index 0 au `stop`, Désactivé → notification Remplir → déconnexion
  → reconnexion → arrêt, `MTKView` avec `drawableSize` et échelle conservées,
  ligne de réglage en 12 langues avec feuille Désactivé/Adapter/Remplir,
  écriture de la préférence et notification.

À valider sur l'iPhone et l'Apple TV (aucun de ces tests ne le démontre) :
recopie AirPlay en cours de jeu puis bascule en affichage étendu, image
pleine hauteur sans déformation, Remplir sur un jeu 4:3, déconnexion AirPlay en
jeu, rotation de l'iPhone, fluidité et synchronisation audio/vidéo (latence
AirPlay inchangée, propre au protocole), fermeture et relancement du jeu avec
l'écran externe connecté.
