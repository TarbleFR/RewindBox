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
- Fondu croisé de 200 ms avec les barres. Le contrôle caché n’est ni
  touchable, ni dans l’arbre VoiceOver, ni focalisable ; la barre du haut
  quitte l’arbre VoiceOver dès le début de son masquage (au lieu de la fin
  du fondu), pour qu’un seul « Retour » soit annoncé.
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
  Auto-masquage, zones de toucher, manette, orientation et sauvegarde
  inchangés.

## Contenu sous le bouton (choix)

- **EPUB/TXT** : la ligne lue était placée à `padding.top + 12`, donc sous
  le bouton (de `padding.top + 2` à `+ 46`) et déjà sous la barre du haut
  affichée à l’ouverture. Elle est désormais placée juste sous le contrôle
  retour : `padding.top + 50` (bas du contrôle + 4). Les positions sont des
  emplacements de texte (CFI EPUB, `txt:bloc:car`) et la même ligne sert à
  placer et à relire la position : une position de la 437 se rouvre sur les
  mêmes mots (environ 38 pt plus bas, rien n’est perdu) et l’aller-retour
  ouverture/fermeture reste exact (tests existants inchangés). Le texte
  défile toujours sur tout l’écran ; le pas de page (0,9 écran) ne change
  pas.
- **Pages et PDF** : aucune modification de mise en page. En mode page,
  `BoxFit.contain` laisse en portrait une bande vide au-dessus d’une page de
  manga, où se trouve le bouton ; en défilement vertical, en zoom et dans le
  PDF (défilement continu), le contenu passe sous le bouton et se dégage par
  un défilement ou un déplacement. Changer les marges de pdfrx ou
  l’ajustement des pages modifierait le zoom et la restauration de la page :
  écarté. Le disque reste petit et translucide.
- Limite connue : avec un très grand texte d’accessibilité, la barre du
  haut grandit et sa flèche se centre plus bas que le bouton flottant.

## Tests

- `test/library_reader_back_button_test.dart` (21 tests, vrais lecteurs,
  navigateur, magasin de lecture et service d’orientation) : barres
  masquées, un toucher sur le bouton flottant ferme le lecteur, revient à
  l’écran d’origine (un seul retrait de route), sauvegarde page ou ligne et
  rétablit le paysage, pour les trois lecteurs ; page visée par un tour
  animé ; double toucher (immédiat et à 80 ms) ; aucun tour de page,
  défilement ni affichage des barres (retrait refusé par un `PopScope` pour
  observer le lecteur après le toucher) ; un seul contrôle touchable et un
  seul nœud VoiceOver en mode page, pendant les deux fondus, en zoom, en
  vertical, au chargement, après erreur, en EPUB/TXT et en PDF ; position
  dans la zone sûre identique à la flèche (portrait et paysage) ; libellés
  `fr` et `zh-TW` (chinois traditionnel) ; couleurs des palettes sombre et
  claire ; contraste de tous les thèmes ; ligne EPUB/TXT sous le bouton.
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
- Exécutés sous Windows (Flutter 3.47.2) sur les sources de ce commit :
  `flutter test --no-pub test/library_*_test.dart` → 703 réussis,
  2 ignorés, 1 échec connu hors sujet (`library_scan_restart_test.dart`,
  « Build419 rescans… » : séparateur de chemin `\` propre à Windows) ;
  les fichiers `library_reader_*` passent de 102 réussis (5 fichiers, avant
  modification) à 123 (les mêmes plus les 21 nouveaux), et
  `library_reader_orientation_contract_test.py` reste OK.
  `flutter analyze --no-pub` sans remarque sur les fichiers modifiés.
  Aucun essai sur iPhone.

## Intégration

- Fichiers à ajouter à `BUILD438_DELTA` : `reader/library_reader_chrome.dart`,
  `reader/library_page_reader_screen.dart`,
  `reader/library_book_reader_screen.dart`, `library_pdf_reader_screen.dart`,
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
  mêmes mots.
