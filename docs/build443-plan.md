# Build 443 — couvertures de livres en 3D

Demande explicite du mainteneur : livrer une IPA de test depuis `Claude`.
Produit : commit `164e1430ce14216d9864978fc621043941aed2b9`, par-dessus la
livraison 442 `e8808dd32301f71fdd421a70c0ac6be2ed6fba47`.

Les couvertures Livres/Mangas s'ouvrent en perspective lors de la sélection,
du survol ou du contact. La charnière des mangas est à droite. Les gestes de
navigation, les images en cache et les préférences d'accessibilité sont
conservés. Détails : `docs/library-book-cover-3d.md`.

## Vérifications et réutilisation

Validation locale Linux, Flutter 3.47.2 / Dart 3.13.2, dépendances résolues
avec `pubspec.lock` inchangé, produit et tests au commit `164e1430` :

- Analyse ciblée des deux fichiers produit et deux fichiers de tests : aucun
  problème ; 31 tests des suites `library_book_cover_test.dart`,
  `library_ui_hub_test.dart` et `library_ui_hub_open_test.dart` réussis.
- 16 tests supplémentaires réussis : `library_ui_dates_test.dart`,
  `library_e2e_journeys_test.dart`, `ios_selective_rollback_test.dart` et
  `library_no_native_sources_test.dart`. Le cache généré d'un hook pdfium
  tronqué a été régénéré avant cette exécution ; aucun fichier source modifié.
- Contrôle de baseline protégée : 3 tests réussis.

La livraison utilise le périmètre `library_covers` : comparaison fermée de
tous les fichiers suivis avec la 442, succès vérifié des jobs et étapes du
run `38170927050`, contrôle des entrées natives et de Xcode/SDK de ce run.
Les anciens résultats sont réutilisés, pas présentés comme exécutés à nouveau.
Le contrôle distant réexécute les trois suites directement concernées et
les nouveaux garde-fous de livraison. Les moteurs et dépendances sont
identiques à la 442 ; les donneurs restent épinglés dans le workflow.

La compilation Release, l'empaquetage, les vérifications ABI et les contrôles
de signature sont conservés. Une nouvelle clé publique de livraison 443
chiffre l'artefact avec le même protocole ; la clé privée reste hors dépôt.
Le numéro 443 est fourni au workflow, sans modifier les dépendances.

L'IPA est préparée pour la re-signature par SideStore. Aucune installation
ni fluidité sur iPhone n'est revendiquée avant l'essai du mainteneur.

## Production du 11 octobre 2026

Run `38173005985` réussi, source exacte
`79a5920af0f17b474bd8f1a0dcd88f798e2bede0` : contrôles ciblés, réutilisation
native vérifiée et compilation Release réussis. Le second build de benchmark
est volontairement désactivé. Les 31 tests Flutter concernés et les huit
contrôles du périmètre de livraison ont réussi sur le serveur.

IPA : `NeoStation-Build443-79a5920af0f17b474bd8f1a0dcd88f798e2bede0-cold.ipa`,
207 408 158 octets, SHA-256
`af860e8b7f00fac46a1a1ab6483b0ddc59a8abd59b99dd2e4eda965118ce14d7`.
Nom du fichier remis : `NeoStation-Build443.ipa` (mêmes octets).

Les contrôles CI valident la structure finale, l'identité intégrée, les
moteurs et les 57 signatures de préparation ad hoc. Mesures observées :
compilation Xcode 203 s, signature et export IPA 52 s. Le fichier téléchargé
a été rapproché du SHA-256 et de la taille de l'artefact GitHub avant son
déchiffrement ; le SHA-256 de l'IPA correspond aux rapports embarqués dans
la livraison. L'installation et la fluidité sur iPhone restent à tester.
