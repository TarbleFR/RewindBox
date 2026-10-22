# RewindBox — bulles interactives, build de test 503

Branche de développement : `Claude`. Aucune fusion vers `main`, aucun tag,
aucune release. Références visuelles : captures du mainteneur du 22 octobre
2026 (carte Sega 32X et barre de navigation).

## Présentation

- Lentille neutre mobile de la barre de navigation : contour convexe, reflet,
  flou de 5 px limité à cette petite surface, arrivée élastique et compression.
- Cartes de consoles : artwork et cache existants, contours très arrondis,
  reflet neutre, nom conservé, agrandissement et flottement du seul élément
  sélectionné. Les cartes de jeux récents conservent leur surface précédente.
- Curseur du carrousel, sélection de la grille, menus de tri et d'affichage et
  navigation des réglages : verre neutre au lieu de remplissages violets.
- Ouverture d'une bibliothèque : compression puis expansion de la carte vers
  le plein écran, artwork accompagnant le mouvement, voisins atténués et
  révélation progressive de la vue de playlist existante. Retour inverse vers
  l'ancre actuelle. Le carrousel, la sélection et les contrôleurs restent montés.

## Durée de vie et performances

Un instantané GPU de la carte, limité à 512 px de côté et moins de 1 Mio RGBA,
est libéré avec la route. Aucun nouveau décodage d'artwork, aucune copie CPU de
l'image, aucun flou par carte. La vraie playlist garde une taille et un chemin
d'élément constants pendant l'animation : aucun second chargement à la fin.

Le verrou commun reste actif jusqu'à la fin du retour, y compris pour des
appuis rapides provenant de plusieurs commandes. La couche de focus existante
isole les entrées pendant le mouvement et préserve la priorité des dialogues.
Les commandes tactiles et manette ouvrent la même route. Les mappages des
manettes restent inchangés.

Le flottement s'arrête hors écran, en arrière-plan et dès que la barrière
d'émulation existante est active. « Réduire les animations » est lu directement
depuis l'accessibilité iOS, même sans `MediaQuery.disableAnimations` ; dans ce
cas, l'ouverture utilise une courte révélation sans déplacement ni instantané.
L'option existante de rafraîchissement 120 Hz est conservée. Aucun débit réel
de 60/120 FPS ni essai matériel Bluetooth/iPhone n'est attesté par ces tests CI.

## Périmètre conservé

Les moteurs, imports, modèles et stockage des playlists, catalogues HD,
jaquettes 3D, configurations, raccourcis, traductions des douze langues et
dépendances sont inchangés par rapport à la livraison 502 (`3c59580b`). Les
contrôles natifs réussis sont réutilisés après comparaison fermée des sources
et de Xcode/SDK ; les nouvelles interactions font l'objet de tests ciblés.
L'IPA est recompilée avec le workflow de livraison existant et soumise aux
contrôles complets de payload et de signature. L'installation requiert la
re-signature Apple habituelle par SideStore ou AltStore.
