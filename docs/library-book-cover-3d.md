# Couvertures de livres en 3D

Demande du 11 octobre 2026, branche `Claude` : donner aux couvertures du
catalogue Livres/Mangas un effet de livre qui s'ouvre pendant la navigation.

`LibraryBookCover` conserve la couverture réelle et ajoute une tranche,
trois feuilles et une ouverture en perspective à 46°. Les mangas ont leur
charnière à droite ; les autres titres l'ont à gauche. Le dessin du papier
est décoratif : aucune page de chapitre n'est téléchargée pour cet effet.

L'ouverture accompagne la sélection à la manette, le survol et le contact
du doigt. Le relâchement ou l'annulation referme une couverture non sélectionnée.
Le toucher est observé sans prendre la main sur les gestes : le défilement et
l'ouverture de la fiche gardent leur comportement et leur délai habituels.
Il n'y a pas de boucle d'animation ni de nouvelle dépendance.

La taille des cartes, les images en cache, les en-têtes des fournisseurs,
les badges et les textes du catalogue sont conservés. L'image est isolée
des reconstructions à chaque image de l'animation. Les lecteurs et les moteurs
d'émulation ne sont pas modifiés.

« Réduire les animations » et la navigation accessible gardent une couverture
immobile. `TickerMode` arrête l'animation lorsque la vue est masquée ; le
contrôleur est libéré avec la carte.

Vérifications ciblées : `library_book_cover_test.dart`,
`library_ui_hub_test.dart`, `library_ui_hub_open_test.dart`, et le contrôle de
la baseline `retroarch_baseline_scope_test.py`. Les tests Flutter vérifient
les gestes et le rendu logique ; la fluidité réelle reste à vérifier sur iPhone.

Validation locale du 11 octobre 2026 (Linux, Flutter 3.47.2 / Dart 3.13.2) :

- Analyse Dart des deux fichiers produit et des deux fichiers de tests :
  aucun problème.
- Les trois suites Flutter citées ci-dessus : 31 tests réussis.
- Contrôle de baseline : 3 tests réussis ; fichiers protégés et moteurs intacts.
- Rendu de contrôle du composant réel : couverture fermée, livre ouvert et
  manga ouvert inspectés visuellement avec des couvertures de démonstration.
- Résolution des dépendances avec le fichier de verrouillage conservé.

Aucune validation sur appareil iOS n'est revendiquée par ces contrôles.
