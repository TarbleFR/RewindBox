# Build 438 — sources de la Bibliothèque supprimables depuis Fichiers (11 octobre 2026)

## Décision du mainteneur

Demande du 11 octobre 2026 : « supprimer les sources manuellement
directement avec un accès dans les dossiers de NeoStation », puis : « les
sources ne doivent pas être directement accessibles ! les gens doivent les
trouver par eux-mêmes ».

Choix retenu par le mainteneur :

- chaque source installée devient un fichier dans
  **Fichiers › NeoStation › Library › Sources** ;
- supprimer ce fichier retire la source de NeoStation ;
- l’application n’affiche **aucun** bouton, lien, chemin, indice, message ou
  notification vers ce dossier. Les utilisateurs le trouvent eux-mêmes. Le
  README n’en parle pas.

Les listes de sources (catalogues mémorisés,
`Application Support/Library/catalogs.json`) ne sont pas concernées : elles
restent gérées dans l’application.

## Dossier et fichiers

- Dossier : `Documents/Library/Sources`, à côté de `Books/` et `Downloads/`
  déjà visibles dans Fichiers sous NeoStation › Library. Le scanner des
  livres locaux ne lit que `Books/` et `Downloads/` : il ignore `Sources/`.
- Un petit fichier JSON par source installée que l’utilisateur peut retirer.
  Jamais pour une source intégrée (`builtIn`, origine `builtin:`).
- Nom lisible : `<nom de la source> (<langue>).json`, par exemple
  `LelscanFR (fr).json`. Le nom est nettoyé pour iOS et Fichiers : pas de
  `/ \ : * ? " < > |`, de caractère de contrôle ou de mise en forme
  invisible, pas de point initial (fichier masqué), ni de point ou d’espace
  final, au plus 180 octets UTF-8, noms réservés de Windows suffixés `_`.
- Collision (comparaison sans tenir compte de la casse, avec tout fichier
  du dossier, y compris étranger) : suffixe court dérivé de l’identifiant
  (`LelscanFR (fr) [3f9a].json`, puis 8 chiffres, puis un compteur).
- Contenu :

```json
{
  "schema": "neostation.library.source-file.v1",
  "id": "aidoku.fr.lelscanfr",
  "name": "LelscanFR",
  "language": "fr",
  "version": "5",
  "origin": "https://example.org/aidoku/index.min.json"
}
```

- L’identification se fait par `id` dans le fichier : un fichier renommé
  garde sa source (le nouveau nom est mémorisé, les mises à jour sont
  écrites dans le fichier renommé).
- NeoStation n’écrit et ne supprime **que** des fichiers portant le marqueur
  `neostation.library.source-file.v1`. Tout autre fichier, les dossiers et
  le contenu des sous-dossiers ne sont jamais touchés.
- Écriture par fichier temporaire masqué puis renommage : une écriture
  interrompue ne laisse jamais de fichier partiel visible.

## Règles de réconciliation

NeoStation mémorise dans les préférences
(`neostation_library_source_files_v1`, identifiant → nom de fichier) les
sources dont il a écrit le fichier. Le fichier est écrit **avant** d’être
mémorisé : une interruption ne peut pas faire passer une source pour
supprimée.

| Situation | Action |
| --- | --- |
| Source installée, fichier présent (nom quelconque) | Rien ; un renommage est mémorisé ; contenu mis à jour s’il a changé |
| Source installée, fichier absent, fichier déjà écrit | L’utilisateur l’a supprimé : la source est retirée (`removeMany`, une fois par passage) |
| Source installée, fichier absent, jamais écrit | Le fichier est écrit |
| Fichier marqué dont l’identifiant n’est pas installé (retrait dans l’app, fichier venant d’ailleurs) | Le fichier est supprimé |
| Plusieurs fichiers marqués pour la même source (copie) | Un seul est gardé (celui mémorisé, sinon le nom habituel) |
| Dossier `Sources` supprimé entièrement | Toutes les sources dont le fichier avait été écrit sont retirées |
| Échec de listage ou de lecture d’un fichier, `Documents` absent, `Sources` qui n’est pas un dossier, préférences illisibles | Rien n’est modifié |
| Premier passage après la mise à jour (rien d’écrit) | Tous les fichiers sont écrits, rien n’est retiré |

Les passages sont sérialisés et regroupés : un seul à la fois, les demandes
reçues pendant un passage partagent un passage suivant. La suppression
qu’un passage déclenche (`removeMany`, qui redemande une synchronisation)
ne le rappelle pas : un appel fait depuis un passage revient aussitôt.

### Suppression du dossier entier

Avant d’appliquer cette règle, les chemins de NeoStation ont été vérifiés :
aucun ne supprime `Documents/Library` ni `Documents/Library/Sources`.

- Bibliothèque locale (`LibraryLocalLibraryService`) : supprime seulement
  des fichiers de livres situés dans `Books/` ou `Downloads/` ; l’index et
  les couvertures sont dans `Application Support/Library`.
- Téléchargements (`LibraryDownloadService`) : supprime seulement le fichier
  partiel d’un téléchargement dans `Downloads/`.
- Nettoyages au démarrage (`lib/main.dart`) : uniquement `full_themes` et
  `custom_themes` du dossier de données ; la relocalisation
  `LIBRARY_RELOCATION_*` réécrit des chemins enregistrés sans rien déplacer
  ni supprimer.
- Déplacement de bibliothèque de jeux (`NeoStationRomLibrary.moveLibrary`) :
  seulement les dossiers de consoles du dossier choisi.
- Suppression de jeu native (`ExternalFolderAccessPlugin.deleteGameFile`) :
  refuse les dossiers.
- Caches de la Bibliothèque : `Caches/Library` et dossiers temporaires.

Un dossier `Sources` absent alors que `Documents` existe ne peut donc venir
que de l’utilisateur. Si un futur chemin de code devait supprimer ou
déplacer `Documents/Library`, il devra conserver `Sources/` (ou effacer
d’abord la préférence `neostation_library_source_files_v1`, ce qui ramène à
la règle sûre « jamais écrit : on réécrit »).

## Déclencheurs

- Au premier chargement de `LibraryAddonService` du processus : le
  passage est attendu avant que la liste soit rendue, puis NeoStation suit
  le cycle de vie de l’application.
- À chaque retour au premier plan (`AppLifecycleState.resumed`) :
  supprimer un fichier dans Fichiers puis revenir dans NeoStation retire la
  source.
- À l’ouverture de la section Sources de la Bibliothèque.
- Juste après une installation, une mise à jour ou un retrait dans
  l’application (fichiers écrits ou supprimés immédiatement).

Pas d’interrogation périodique ni de surveillance de fichiers.

Actif sur iOS uniquement (`Platform.isIOS`) ; ailleurs rien ne change. Les
tests activent le mécanisme par
`LibraryAddonService.forTesting(sourceFiles: true)`.

## Effets d’un retrait par Fichiers

Exactement ceux du retrait dans l’application : la source quitte la liste
persistée par le même `removeMany`. Progression de lecture, favoris,
téléchargements, livres locaux, catalogues mémorisés et rapports de santé
des sources sont conservés (le retrait dans l’application ne touche pas non
plus les rapports de santé, rangés par identifiant de source Aidoku).

## Rafraîchissement des écrans

Silencieux : aucun texte ajouté, aucune traduction nécessaire, journaux
`LoggerService` uniquement.

- Section Sources : la liste se recharge et le hub est prévenu
  (`onSourcesChanged`), comme après une désactivation dans l’application.
- Aperçu de catalogue : une source retirée n’est plus affichée comme active.
- Hub de la Bibliothèque : le flux du catalogue (`LibraryCatalogFeed`, que
  `LibraryScreen` écoute) reçoit la nouvelle liste lorsqu’il affichait une
  source retirée. `LibraryScreen` n’est pas modifié par ce paquet : sa copie
  interne de la liste (transmise aux Favoris) se met à jour à son prochain
  chargement (changement d’onglet ou retour de la section Sources).
- `library_hub_dialog.dart` n’affiche pas de sources : inchangé.
- Une page de titre déjà ouverte d’une source retirée reste utilisable
  jusqu’à sa fermeture (elle garde la source qu’elle a reçue).

Coût : chaque passage liste le dossier et lit ses petits fichiers (au plus
64 Kio chacun, les plus gros sont ignorés) ; le premier passage après la
mise à jour écrit un fichier par source, une seule fois.

## Fichiers

- Nouveau : `lib/services/library_source_files.dart`
  (`LibrarySourceFiles`, `LibrarySourceFileDescriptor`).
- Modifiés : `lib/services/library_addon_service.dart` (déclencheurs,
  `syncSourceFiles`, `removedThroughSourceFiles` ; correction d’un
  avertissement d’analyse préexistant par interpolation, sans changement de
  comportement), `lib/screens/library_screen/library_sources_view.dart`,
  `lib/screens/library_screen/library_catalog_preview_screen.dart`.
- Tests : `test/library_source_files_test.dart`.

À l’intégration (fichiers réservés) : ajouter ces fichiers à
`BUILD438_DELTA` de `build-utils/verify_delivery_reuse.py`. Aucun nouveau
workflow : `retroarch-delivery.yml` exécute déjà `test/library_*_test.dart`.

## Tests

`test/library_source_files_test.dart` (fichiers réels dans un dossier
temporaire, `SharedPreferences.setMockInitialValues`, canal
`path_provider` simulé) :

- premier chargement après la mise à jour : un fichier par source, contenu
  vérifié, rien retiré ;
- suppression d’un fichier : seule cette source est retirée, une seule fois
  par passage via `removeMany`, liste persistée et événement vérifiés ;
- fichier renommé : la source reste, la mise à jour va dans le fichier
  renommé, sa suppression retire la source ;
- fichiers étrangers (même nom que le nôtre, autre schéma, JSON invalide,
  texte, sous-dossier) jamais modifiés ; collision résolue par suffixe ;
- retrait dans l’app (désactivation, oubli d’un catalogue avec ses sources)
  : fichier supprimé aussitôt ; fichier marqué d’une source non installée
  supprimé ;
- réinstallation après suppression par Fichiers : fichier recréé ;
- dossier entier supprimé : les sources écrites sont retirées, une source
  jamais écrite est gardée, `Books/` et `Downloads/` intacts ;
- échec de listage, fichier illisible, chemin introuvable, `Documents`
  absent : rien retiré, puis application une fois le dossier lisible ;
- sources intégrées : aucun fichier ;
- demandes concurrentes : un seul passage à la fois, regroupement ;
- flux du hub : la source retirée disparaît ;
- progression, favoris, rapports de santé, catalogues et livres locaux
  conservés ;
- noms sûrs et uniques ; copie d’un fichier réduite à un seul ;
- widgets : retour au premier plan (cycle de vie) ; section Sources qui se
  met à jour et prévient le hub sans message ; ouverture de la section qui
  applique une suppression ; aperçu de catalogue.

Résultats sous Windows (Flutter 3.47.2, `--no-pub`, `pubspec.lock`
inchangé), arbre de travail basé sur `Claude` `a434881e` :

- `test/library_source_files_test.dart` : 18 réussis sur 18.
- Suite `test/library_*_test.dart` avant modification : 682 réussis,
  2 ignorés, 1 échec ; après : 700 réussis (682 + 18), 2 ignorés, le même
  échec, connu et propre à Windows (`library_scan_restart_test.dart`,
  « Build419 rescans and database reopen retain one physical row and user
  metadata »), sans lien avec ce paquet.
- `flutter analyze` sur les quatre fichiers `lib/` modifiés ou créés et sur
  le test : aucun problème.
- Contrôle par mutations (chaque mutation appliquée seule puis annulée) :
  retour au premier plan ignoré, retrait d’une source jamais écrite, échec
  de listage traité comme dossier vide, marqueur non vérifié, section
  Sources ou aperçu non rafraîchis, absence de synchronisation après un
  changement dans l’app, garde de réentrance retirée : chacune fait échouer
  au moins un test.

Une compilation réussie ou un test simulé ne démontre pas le comportement
sur iPhone.

## Vérifications restant à faire sur iPhone

1. Ouvrir la Bibliothèque une fois, puis Fichiers › NeoStation › Library :
   le dossier `Sources` est présent avec un fichier par source installée.
2. Supprimer un fichier dans Fichiers, revenir dans NeoStation : la source
   disparaît de la section Sources et du hub, sans message.
3. Renommer un fichier : la source reste.
4. Supprimer le dossier `Sources` entier : toutes les sources sont retirées.
5. Réinstaller une source depuis son catalogue : son fichier réapparaît.
6. Vérifier que favoris et progression d’une source retirée puis réactivée
   sont toujours là.
7. Vérifier qu’aucun écran ne mentionne ce dossier.
