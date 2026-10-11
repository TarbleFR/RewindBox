# Bouton retour des lecteurs — Build 438 (11 octobre 2026)

Demande du mainteneur du 11 octobre 2026 : « ajoute un bouton retour en
arrière pour la lecture des livres pour le lecteur car c’est compliqué de
sortir et revenir dans le menu précédent ». Branche `Claude`, base
`a434881e` (cadrage Build 438). Aucune modification de `lib/main.dart`, des
catalogues de traduction, des workflows ni des moteurs.

## Problème (constaté dans les sources)

- Les trois lecteurs (pages CBZ et chapitres en ligne, EPUB/TXT, PDF) n’ont
  qu’une sortie tactile : la flèche de la barre du haut
  (`LibraryReaderTopBar`). `LibraryReaderChromeController` masque les barres
  4 s après leur affichage et après chaque tour de page : il fallait toucher
  le milieu de la page, puis la flèche avant qu’elle ne disparaisse. Le
  bouton B de la manette fermait déjà.
- Pas de balayage depuis le bord : `lib/main.dart` (verrouillé) impose
  `FadeUpwardsPageTransitionsBuilder` à toutes les plateformes, donc iOS n’a
  pas de retour par balayage dans l’application, et un balayage horizontal
  depuis le bord se confondrait avec les tours de page (glissement du
  `PageView`, zones de toucher gauche et droite). Écarté.

## Comportement

- Un seul contrôle retour à la fois, dans les trois lecteurs et dans tous
  les états : barres affichées, la flèche de la barre ; barres masquées
  (mode page, défilement vertical, zoom, PDF, EPUB/TXT), un bouton flottant
  compact **au même endroit** (coin haut côté début de ligne, dans la zone
  sûre : encoche ou Dynamic Island, coins arrondis, portrait et paysage).
  Pendant le chargement ou après une erreur, les barres restent affichées
  (inchangé) : la flèche est alors le contrôle.
- Fondu croisé de 200 ms avec les barres. Le contrôle caché n’est ni dans
  l’arbre VoiceOver ni focalisable au clavier (Tab sur iPad ou clavier
  Bluetooth) ; la barre du haut quitte l’arbre VoiceOver dès le début de son
  masquage (au lieu de la fin du fondu), pour qu’un seul « Retour » soit
  annoncé. Barres masquées, leurs commandes (barre du haut et barre du bas)
  ne sont ni touchables ni focalisables (avant la 438, Tab parcourait encore
  les barres invisibles).
- Pendant les 200 ms où la barre du haut glisse vers le bas, sa flèche
  n’atteint la place du bouton flottant qu’en fin de course : le bouton
  flottant garde donc les touchers à sa place jusqu’à la fin du glissement
  (fin de `AnimatedSlide`), déjà retiré de VoiceOver et du focus. Un toucher
  à cet endroit est toujours un retour (les deux appellent le même
  `_close()`), jamais un tour de page. Revue 438 : avant ce correctif, un
  toucher 20 à 100 ms après l’apparition des barres atteignait la page
  (page précédente, barres masquées). Au masquage, il reprend les touchers
  immédiatement (inchangé).
- Bouton flottant : cible de 44 × 44 pt ; disque de 38 pt en
  `chromeBackground` à 80 % d’opacité avec un liseré `divider` ; flèche
  `chromeForeground`, même icône que la barre ; infobulle et libellé
  VoiceOver par la clé existante `back` (12 langues, aucune clé ajoutée).
  Contraste flèche/disque ≥ 3:1 (WCAG 1.4.11) dans les thèmes Clair, Sépia,
  Sombre et Noir, sur page noire, blanche ou du thème.
- Il ne se masque jamais, ne tourne pas de page et n’affiche pas les barres :
  il appelle `_close()` du lecteur, comme la flèche et B (sauvegarde avant
  le retrait, y compris la page visée par un tour de page animé, puis
  retour au paysage dès le début de la fermeture par `PopScope`).
- Code unique dans `reader/library_reader_chrome.dart`
  (`LibraryReaderFloatingBackButton`, `LibraryReaderChromeOverlay` reçoit
  `palette` et `onBack`) ; les trois lecteurs passent leur `_close`.
  Auto-masquage, zones de toucher, liaisons de la manette, orientation et
  sauvegarde inchangés. Seul changement de lecture : le pas de page EPUB/TXT
  est plafonné (section suivante).

## Contenu sous le bouton (choix)

- **EPUB/TXT** : la ligne lue était placée à `padding.top + 12`, donc sous
  le bouton (de `padding.top + 2` à `+ 46`) et déjà sous la barre du haut
  affichée à l’ouverture. Elle est désormais placée juste sous le contrôle
  retour : `padding.top + 50` (bas du contrôle + 4). Les positions sont des
  emplacements de texte (CFI EPUB, `txt:bloc:car`) et la même ligne sert à
  placer et à relire la position : une position de la 437 se rouvre sur les
  mêmes mots (environ 38 pt plus bas, rien n’est perdu) et l’aller-retour
  ouverture/fermeture reste exact (tests existants inchangés). Le texte
  défile toujours sur tout l’écran.
- **EPUB/TXT, tour de page** (revue 438) : le pas de 0,9 écran (zones de
  toucher gauche/droite, manette gauche/droite) ne laissait que 0,1 écran
  de recouvrement, moins que la bande du bouton : la première ligne pas
  encore vue arrivait sous le disque (portrait y ≈ 67-95, paysage
  y ≈ 21-40) et la position enregistrée était souvent la ligne suivante.
  Le pas est désormais plafonné : `min(0,9 écran, hauteur − (bas du
  contrôle retour + 4) − ligne la plus haute)`, la ligne la plus haute étant
  celle du corps ou d’un titre h1 (2 em). Sur iPhone 393 × 852, police
  18 pt, interligne 1,5 : 707 pt au lieu de 767 en portrait, 307 au lieu
  de 354 en paysage (recouvrement relu : 145 pt au lieu de 85, 86 au lieu
  de 39). En avant, la ligne coupée par le bas de l’écran arrive sur la
  ligne de lecture ou en dessous, jamais sous le bouton, et la position
  enregistrée n’est jamais au-delà d’une ligne pas encore affichée ; en
  arrière, la ligne coupée par le bouton revient entière en bas de l’écran.
  Aucune ligne n’est donc montrée seulement derrière le bouton. Zones de
  toucher, pas de 0,3 écran de la manette (haut/bas) et positions
  inchangés. Le plafond s’applique aussi barres affichées (la barre du
  haut couvre la même bande). Alternative écartée : un disque plus
  transparent au repos aurait laissé la ligne sous le bouton.
- **Pages et PDF** : aucune modification de mise en page. En mode page,
  `BoxFit.contain` laisse en portrait une bande vide au-dessus d’une page de
  manga, où se trouve le bouton ; en zoom et dans le PDF (défilement
  continu), le contenu passe sous le bouton et se dégage par un défilement
  ou un déplacement. Changer les marges de pdfrx ou l’ajustement des pages
  modifierait le zoom et la restauration de la page : écarté. Le disque
  reste petit et translucide.
- **Défilement vertical (webtoon), compromis assumé** : un tour de page
  (zones de toucher, manette gauche/droite) aligne le haut de la page
  suivante en haut de l’écran, comme à l’ouverture, au changement de mode
  et en 437 (le haut de page passait déjà en partie sous la Dynamic
  Island) ; le disque couvre alors un coin de 38 pt de l’image, dégagé
  par le moindre défilement. Décaler seulement ce saut rendrait le tour de
  page incohérent avec l’ouverture et le changement de mode ; décaler
  toutes ces places ferait de l’ancre de rotation (élément en haut de
  l’écran, `_anchorItem`) la fin de la page précédente, donc changerait la
  gestion de la rotation que la demande exclut, et la première page ne
  peut pas être décalée (défilement borné à 0). Non mesuré sur iPhone.
- Limite connue : avec un très grand texte d’accessibilité, la barre du
  haut grandit et sa flèche se centre plus bas que le bouton flottant.

## Tests

- `test/library_reader_back_button_test.dart` (30 tests, vrais lecteurs,
  navigateur, magasin de lecture et service d’orientation) : barres
  masquées, un toucher sur le bouton flottant ferme le lecteur, revient à
  l’écran d’origine (un seul retrait de route), sauvegarde page ou ligne et
  rétablit le paysage, pour les trois lecteurs ; page visée par un tour
  animé ; double toucher (immédiat et à 80 ms) ; aucun tour de page,
  défilement ni affichage des barres (retrait refusé par un `PopScope` pour
  observer le lecteur après le toucher) ; un seul contrôle touchable, un
  seul nœud VoiceOver et un seul « Retour » focalisable en mode page,
  pendant les deux fondus, en zoom, en vertical, au chargement, après
  erreur, en EPUB/TXT et en PDF ; position dans la zone sûre identique à la
  flèche (portrait et paysage) ; libellés `fr` et `zh-TW` (chinois
  traditionnel) ; couleurs des palettes sombre et claire ; contraste de tous
  les thèmes ; ligne EPUB/TXT sous le bouton.
- Ajouts de la revue 438 (9 tests) : toucher à la place du retour 20, 60,
  100, 140 et 250 ms après l’apparition des barres (lecteur de pages) et à
  60 ms (EPUB/TXT) : un seul retrait, page ou ligne conservée, aucun tour
  de page ; Tab (clavier) barres affichées puis masquées : jamais les
  barres invisibles, le bouton flottant seulement barres masquées ;
  EPUB/TXT en portrait et en paysage (encoches de 59 pt) : trois tours par
  la zone droite et trois par la manette, puis deux en arrière par chaque
  voie, en mesurant les boîtes des glyphes de chaque ligne — la première
  ligne pas encore vue arrive entière sous le disque, toute ligne sous le
  disque avait déjà été vue, la position n’est pas au-delà de cette ligne,
  le tour reste supérieur à 70 % de l’écran ; en arrière, la ligne coupée
  par le bouton revient entière à l’écran.
- Contrat remplacé (revue 438) : pendant le glissement de la barre du haut,
  `expectOneBack(slidingIn: true)` attend désormais deux cibles touchables
  (la flèche en mouvement et le bouton flottant, même action) au lieu
  d’une, toujours un seul nœud VoiceOver et un seul « Retour »
  focalisable ; fin du glissement, de nouveau une seule cible.
- PDF : pdfium n’est pas chargé dans les tests Flutter ; le test annonce le
  document prêt et les changements de page par les rappels du visualiseur
  du vrai lecteur (`onViewerReady`, `onPageChanged`).
- `test/library_reader_page_test.dart` : le test « sans VoiceOver, les
  barres se masquent après 4 s » vérifiait qu’aucun « Retour » ne restait
  une fois les barres masquées. Ce contrat est remplacé par le nouveau : les
  commandes des barres quittent l’arbre (`settings`, `switchToVertical`) et
  le seul « Retour » restant est celui du bouton flottant.
- `test/library_reader_test_support.dart` : `pumpReader` accepte un écran
  d’origine (`opener`) et des observateurs de navigation.
- Contrôles de sensibilité (mutations temporaires, non conservées) : chaque
  mutation suivante fait échouer au moins un test — bouton flottant
  toujours touchable, exclusion VoiceOver retirée (barre ou bouton), ancien
  décalage EPUB/TXT, bouton contournant `_close()`, page visée d’un tour
  animé ignorée. La suppression du seul garde `_closing` ne fait échouer
  aucun test : le double retrait est aussi empêché par le navigateur
  (pointeurs absorbés après un retrait, `maybePop` qui vérifie la dernière
  route) ; le test vérifie le résultat visible, pas ce garde.
- Contrôles de sensibilité de la revue 438 (mutations temporaires, non
  conservées) : pas de 0,9 écran rétabli → les deux tests de tour EPUB/TXT
  échouent (portrait : ligne à y = 88,7 pour un disque finissant à 102 ;
  paysage : 37,9 pour 43) ; plafond en avant seulement → échec en arrière
  (ligne sautée, bas à 870,6 pour un écran de 852) ; bouton flottant
  intouchable dès l’apparition des barres → échec à 20, 60 et 100 ms, du
  glissement en zoom et du test EPUB/TXT (140 et 250 ms passent, comme
  mesuré par la revue) ; exclusion du focus retirée de la barre du haut, de
  la barre du bas ou du bouton flottant → échec du test Tab (et des
  vérifications de focus de `expectOneBack` pour la barre du haut et le
  bouton).
- Exécutés sous Windows (Flutter 3.47.2) sur les sources de ce commit :
  `flutter test --no-pub test/library_*_test.dart` → 703 réussis,
  2 ignorés, 1 échec connu hors sujet (`library_scan_restart_test.dart`,
  « Build419 rescans… » : séparateur de chemin `\` propre à Windows) ;
  les fichiers `library_reader_*` passent de 102 réussis (5 fichiers, avant
  modification) à 123 (les mêmes plus les 21 nouveaux), et
  `library_reader_orientation_contract_test.py` reste OK.
  `flutter analyze --no-pub` sans remarque sur les fichiers modifiés.
  Aucun essai sur iPhone.
- Après les corrections de la revue 438, mêmes conditions :
  `flutter test --no-pub test/library_*_test.dart` → 712 réussis,
  2 ignorés, le même échec connu hors sujet ; les fichiers
  `library_reader_*` → 132 réussis (les 123 plus les 9 nouveaux) ;
  `library_reader_orientation_contract_test.py` OK ; `flutter analyze
  --no-pub` sans remarque sur les fichiers modifiés ; `pubspec.lock`
  inchangé. Aucun essai sur iPhone.

## Intégration

- Fichiers à ajouter à `BUILD438_DELTA` : `reader/library_reader_chrome.dart`,
  `reader/library_page_reader_screen.dart`,
  `reader/library_book_reader_screen.dart`,
  `reader/library_reflow_view.dart` (constantes des titres partagées avec le
  plafond du pas, sans changement de rendu), `library_pdf_reader_screen.dart`,
  les trois fichiers de test ci-dessus et ce document. Le nouveau test est
  déjà couvert par le motif `test/library_*_test.dart` de
  `retroarch-delivery.yml`.

## À vérifier sur iPhone (mainteneur)

- Bouton lisible et discret sur pages claires et sombres, thèmes Clair,
  Sépia, Sombre, Noir ; gêne éventuelle en lecture.
- Place sous la Dynamic Island ou l’encoche en portrait, côté encoche en
  paysage (rotation à gauche et à droite), sur iPad.
- Un toucher ferme le livre et revient à l’écran qui l’a ouvert, page ou
  position conservée, retour en paysage sans rotation visible.
- VoiceOver : un seul « Retour », barres affichées ou masquées.
- EPUB/TXT : première ligne sous le bouton après ouverture, saut de table
  des matières et changement de police ; livres lus en 437 rouverts sur les
  mêmes mots ; après chaque tour de page (toucher à droite ou à gauche,
  manette), aucune ligne nouvelle sous le bouton et recouvrement relu
  acceptable (environ 5 lignes en portrait).
- Toucher la place du retour juste après avoir fait apparaître les barres :
  le livre se ferme, sans tour de page.
- iPad avec clavier : Tab n’atteint pas les barres masquées.
- Défilement vertical : gêne éventuelle du disque sur le coin haut gauche
  d’une page après un tour de page (compromis décrit plus haut).
