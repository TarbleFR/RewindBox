# Sauvegardes de jeu RPCS3 (savedata) — Build 442 (paquet 3)

Demande du mainteneur du 11 octobre 2026 (soir), `docs/build442-plan.md`,
section 3 : l'export et l'import des sauvegardes de jeu RPCS3 depuis le
gestionnaire RPCS3 doivent réellement fonctionner, en Dart seulement, sans
toucher au Core RPCS3 (pin 441), au pont natif ni aux fichiers verrouillés
de la baseline 419 (`lib/main.dart` compris). Les savestates ne font pas
partie de ce flux. Aucune validation sur iPhone n'est revendiquée ici.

## Causes trouvées dans les sources 441

Toutes dans `lib/services/rpcs3_internal_service.dart` et
`lib/screens/rpcs3_manager_screen.dart` (révision `351b738c`) :

1. `synchronizeFilesWorkspace()` était appelée au démarrage par
   `lib/main.dart` (`_prepareIosFilesWorkspaceAfterStartup`, 750 ms après le
   premier rendu), avant chaque démarrage explicite du Core
   (`_initializeRuntime`) et après `stop()`. Elle **consommait** le dossier
   `Documents/RPCS3/Import` (`_copyTree(consumeSource: true)`) : chaque
   fichier déposé était copié dans l'arborescence vivante
   (`dev_hdd0/home/00000001/savedata` et `savestates`) sans validation, sans
   confirmation (`_copyReplacing` écrasait l'existant), puis supprimé de
   `Import`. Elle **supprimait** ensuite `Documents/RPCS3/Export` entier
   (`exportRoot.delete(recursive: true)`) et le recréait à chaque démarrage.
2. `importSaveDataFromFiles()` (bouton « Importer ») arrivait donc après la
   consommation silencieuse : le dossier `Import` était déjà vide, d'où
   l'exception `saveImportEmpty` et le message générique
   `operationFailed`. Quand il restait des fichiers, ils étaient copiés un
   par un sans contrôle de `PARAM.SFO` ni des noms de dossier, avec un
   fichier `.neostation-import-backup` écrasé à chaque passage.
3. `exportSaveData()` (bouton « Exporter ») copiait l'arborescence brute
   (sauvegardes et savestates) dans `Export`, sans archive, sans partage et
   sans rapport ; l'utilisateur ne savait pas ce qui avait été produit ni où.
4. Tous les échecs remontaient `_ui('operationFailed')` (« L'opération a
   échoué ») : aucune raison, aucun détail technique.
5. L'utilisateur `00000001` et le chemin `savedata` étaient codés en dur dans
   deux fonctions, sans la garde `Data/vfs.yml` ajoutée pour les licences
   RAP en Build 440.

## Où le Core lit les sauvegardes

Faits déjà établis pour la Build 440 (`docs/rpcs3-rap-import-build440.md`,
sources XITRIX/rpcs3 `22f1152783cef1f7e04af7b1c895173e28fd5b03`) :

| Fait | Référence |
| --- | --- |
| Sous iOS, le dossier d'émulation est le `support_path` transmis par l'hôte : `<ApplicationSupport>/NeoStation/RPCS3/Data` (`Rpcs3InternalService.dataDirectory()`). | `Utilities/File.cpp`, `rpcs3/Emu/vfs_config.cpp` |
| Le Core iOS choisit toujours l'utilisateur `00000001` (`Emu.SetUsr("00000001")`). | `rpcs3/ios/RPCS3IOS.cpp` |
| `dev_hdd0` vaut `$(EmulatorDir)dev_hdd0/` sauf redirection par `vfs.yml` dans ce même dossier. | `rpcs3/Emu/vfs_config.h`, `system_utils.cpp` |
| Une sauvegarde de jeu est un dossier `dev_hdd0/home/<usr>/savedata/<DIR>/` contenant `PARAM.SFO`, les icônes et les fichiers de données ; `<DIR>` (dirName) accepte `[A-Za-z0-9_-]`, 32 caractères au plus. | `rpcs3/Emu/Cell/Modules/cellSaveData.cpp` |

Le chemin réel est donc
`<ApplicationSupport>/NeoStation/RPCS3/Data/dev_hdd0/home/00000001/savedata/<DIR>/`.
Il est résolu à chaque appel à partir de `dataDirectory()`, de la garde
`Rpcs3RapLicenceService.storageRedirection` et de
`Rpcs3RapLicenceService.activeUserId` ; aucun chemin absolu n'est codé. Les
autres dossiers `home/<utilisateur valide>` (8 caractères, préfixe numérique
non nul, règle `check_user`) sont seulement énumérés : s'ils contiennent des
sauvegardes, le rapport d'export le signale (« seul 00000001 est utilisé par
le Core ») sans les exporter.

`PARAM.SFO` est lu par `lib/services/rpcs3_param_sfo.dart` : magie
`00 50 53 46`, en-tête petit-boutiste (version, table des clés, table des
données, nombre d'entrées), index de 16 octets par entrée, formats `0x0204`
(chaîne UTF-8), `0x0004` et `0x0404`. `TITLE`, `SUB_TITLE`, `DETAIL` et
`SAVEDATA_DIRECTORY` servent aux rapports ; un dossier n'est une sauvegarde
que si son `PARAM.SFO` s'analyse (fichier de 1 Mio au plus).

## Comportement livré

Service : `lib/services/rpcs3_save_exchange_service.dart`
(`Rpcs3SaveExchangeService`), racines injectables (`dataRoot`,
`backupRoot`, `filesWorkspace`, limites, horloge, garde) ; instance de
production liée aux dossiers de NeoStation. Interface :
`lib/widgets/rpcs3_save_exchange_dialogs.dart` et les deux boutons du
gestionnaire RPCS3 (`rpcs3-manager-export-saves`,
`rpcs3-manager-import-saves`, libellés « Exporter les sauvegardes de jeu » /
« Importer des sauvegardes de jeu »).

### Export

- Archive `RPCS3-saves-<aaaaMMjj-HHmmss>.zip` (heure locale, suffixe `-2`,
  `-3` si le nom existe) dans `Documents/RPCS3/Export/Game Saves/`,
  contenant chaque sauvegarde valide sous `savedata/<DIR>/…` (arborescence
  complète, sous-dossiers vides compris, liens ignorés). Écriture en flux
  (`archive` 4.0.9, `ZipFileEncoder`, un fichier à la fois) sous le nom
  temporaire `.<nom>.part`, puis renommage. En cas d'échec le fichier
  temporaire est supprimé.
- Rapport : nombre de sauvegardes, de fichiers, taille, nom de l'archive,
  emplacement « Fichiers › Sur mon iPhone › NeoStation › RPCS3 › Export ›
  Game Saves › <zip> », dossiers exportés, dossiers de `savedata` ignorés
  (nom invalide, `PARAM.SFO` absent ou illisible, lien) avec leur motif,
  mention des autres utilisateurs. Bouton « Partager… » : feuille de partage
  iOS (`share_plus` 13.3.0, `SharePlus.instance.share(ShareParams(files:
  [XFile(zip)]))`) vers iCloud Drive, AirDrop ou une app.
- Refus (message précis + détail brut) : aucune sauvegarde valide ;
  `Data/vfs.yml` redirige `dev_hdd0` ; jeu PS3 en cours ou bibliothèque
  occupée ; échec d'écriture de l'archive. L'arborescence vivante n'est
  jamais lue autrement qu'en lecture.

### Import — trois sources (boîte de choix depuis le bouton Importer)

1. **Dossier Fichiers** `Documents/RPCS3/Import/Game Saves/` : dossiers de
   sauvegarde trouvés jusqu'à trois niveaux (`<DIR>`, `<X>/<DIR>`,
   `<X>/<Y>/<DIR>` — par exemple `MyExport/BLES01234-SAVE` ou
   `RPCS3-saves-…/savedata/<DIR>` après décompression dans Fichiers) et
   archives `*.zip` (toute casse) placées directement dans le dossier. Rien
   n'y est déplacé ni supprimé. Dossier vide ou sans sauvegarde ni archive :
   refus avec le chemin Fichiers.
2. **Archive ZIP** choisie avec `FilePicker.pickFiles(type: FileType.custom,
   allowedExtensions: ['zip'])` (extension vérifiée sans casse sur le nom,
   copie du sélecteur lue puis nettoyée par `clearTemporaryFiles`). Dans
   l'archive, chaque entrée `PARAM.SFO` désigne une sauvegarde ; son dossier
   parent est `<DIR>`, avec un nombre quelconque de dossiers en tête
   (`savedata/`, nom d'export…). `__MACOSX` est ignoré.
3. **Dossier** ouvert sur place avec
   `Rpcs3InternalBridge.pickGameFolderOpenInPlace()` : le dossier choisi
   s'il contient `PARAM.SFO`, sinon ses sous-dossiers jusqu'à trois niveaux.
   `releaseScopedResources` est toujours appelé (`finally`) dès la fin de la
   copie en zone de transit, avant toute boîte de dialogue.

### Validation, avant toute écriture dans `savedata`

- Archive : entrées refusées en bloc si un nom est vide, contient `..`,
  `.`, un segment vide, une barre oblique inverse, un caractère NUL, un
  chemin absolu ou une lettre de lecteur ; si une entrée est un lien
  symbolique (`isSymbolicLink` ou mode `0xA000`) ; au-delà de 2000 entrées ;
  total déclaré supérieur à 1 Gio ; un fichier déclaré supérieur à 512 Mio ;
  fichier qui n'est pas une archive ZIP lisible ; entrée chiffrée ou
  compression autre que « stored »/deflate.
- Dossiers : mêmes limites par sauvegarde (entrées, 1 Gio, 512 Mio), lien
  symbolique refusé (`followLinks: false`), taille de chaque copie
  vérifiée.
- Sauvegarde : nom `^[A-Za-z0-9_\-]{1,32}$`, comparé exactement (iOS
  distingue la casse ; `bles01234-save` n'est pas `BLES01234-SAVE`) ;
  `PARAM.SFO` analysé dans la source puis **à nouveau** après extraction ;
  un même `<DIR>` présent deux fois dans une sélection : le premier décide,
  le second est « refusé (doublon) ».
- Zone de transit `<Data>/dev_hdd0/home/00000001/.neostation-save-import-<ts>/<DIR>`
  (même volume) : chaque entrée est gonflée en flux par `dart:io`
  (`ZLibDecoder`), comptée et vérifiée (taille et CRC-32 de l'archive) ;
  une entrée qui ment sur sa taille ne remplit ni la mémoire ni le disque
  (« données corrompues »). Les zones laissées par une interruption sont
  supprimées à l'import suivant ; toute erreur supprime la zone en cours.
- Installation par `rename` atomique de `<transit>/<DIR>` vers
  `savedata/<DIR>`, après vérification que `savedata` se résout dans `Data`.

### Conflits

- Cible `savedata/<DIR>` existante au contenu différent : une seule
  demande pour toute la sélection (liste des `<DIR>` et des titres) :
  « Remplacer » / « Conserver l'existante » (B, fermeture = conserver).
- Remplacer : le dossier existant est **déplacé** dans
  `<ApplicationSupport>/NeoStation/RPCS3/SaveBackups/<DIR>-<UTC aaaaMMjj-HHmmss>/`
  (suffixe `-2` si le nom existe ; hors de l'arborescence du Core, jamais
  supprimé), puis la copie de transit est renommée en place ; si ce dernier
  renommage échoue, la copie de secours est remise en place et la ligne est
  « refusée » avec le détail. Conserver : « sauvegarde existante
  conservée », copie de transit jetée.
- Contenu identique déjà présent (mêmes fichiers, tailles et octets) : « déjà
  présente », rien n'est réécrit (date de modification inchangée), aucune
  copie de secours.

### Garde « jeu en cours »

`Rpcs3InternalService.runSaveExchange<T>(body)` applique les contrôles de
`deleteInstalledGame` : refus si une mutation de bibliothèque, une
préparation du runtime ou un import de contenu est en cours, si une session
de jeu est active (`GameLaunchManager().isActive`) et, Core chargé, si
`Rpcs3InternalBridge.emulationState()` n'est ni 0 ni 1 ; le drapeau
`_libraryMutationInProgress` est tenu pendant tout l'échange (y compris
pendant la demande de remplacement). Messages traduits : « Un jeu PS3 est en
cours. Fermez-le d'abord : RPCS3 est peut-être en train d'écrire une
sauvegarde. » / « Une autre opération RPCS3 est en cours… ». Export et
import passent tous deux par cette garde.

### Démarrage

`synchronizeFilesWorkspace()` garde son nom et sa signature (appelée par
`lib/main.dart`, verrouillé, par `_initializeRuntime` et après `stop()`)
mais ne fait plus qu'assurer les dossiers `Import/Game Saves`,
`Import/Savestates`, `Export/Game Saves`, `Export/Savestates` et le
`README.txt` (texte réécrit quand il diffère : il décrit les flux manuels).
Plus aucune lecture, copie, consommation ni suppression ; les compteurs
rendus au code verrouillé valent toujours zéro. `exportSaveData()` et
`importSaveDataFromFiles()` ne sont plus que des enveloppes du nouveau
service (conservées pour les branches dormantes de
`rpcs3_internal_playlist_actions.dart`, qui n'expose toujours aucune action
de sauvegarde) ; l'ancienne logique de copie est retirée.

### Rapports

Modèle du rapport de licences RAP : une ligne par sauvegarde dans l'ordre de
la source — `<DIR>` brut, titre brut (`TITLE`), statut traduit (importée /
remplacée / déjà présente / conservée / refusée), nombre de fichiers et
taille, mention de la copie de secours, motif traduit, détail système brut à
part. Résumé par statut en tête, source (« Fichiers › Sur mon iPhone ›
NeoStation › RPCS3 › Import › Game Saves » ou nom brut de l'archive/du
dossier), et la ligne « RPCS3 lit ces sauvegardes dans le dossier RPCS3 privé
de NeoStation. Elles apparaissent dans RPCS3 sans autre étape. ». Bouton
Fermer focalisé ; manette : croix, A, B (`LibraryFocusGamepadLayer`,
`LibraryFocusRing`). Aucun message de succès sans transfert terminé ; chaque
refus a une raison traduite et son détail brut.

### Sans effet ailleurs

Savestates, firmware, jeux, caches, trophées, `games.yml`, réglages et
licences restent intacts ; aucun appel Core/JIT/VPN, aucun rechargement de
bibliothèque, aucune tuile ; `Rpcs3InternalBridge` inchangé (seuls le
sélecteur de dossier existant et `emulationState` sont utilisés) ; aucune
dépendance ajoutée (`archive`, `share_plus`, `file_picker` et `path` étaient
déjà dans `pubspec.yaml`).

## Traductions

`lib/l10n/rpcs3_saves_locale.dart` couvre les douze langues (`en`, `es`,
`ru`, `zh`, `zh_Hant`, `pt`, `fr`, `de`, `it`, `id`, `ja`, `ko`) ; le
chinois traditionnel est choisi par l'écriture Hant, la région TW/HK/MO ou
l'étiquette de langue (`textForLocale`, utilisé par la garde du service).
`exportSaves` / `importSaves` de `lib/l10n/rpcs3_ui_locale.dart` disent
« sauvegardes de jeu » dans les douze langues ; les autres clés sont
conservées. Noms de dossiers, titres, noms de fichiers, chemins, tailles et
diagnostics restent bruts.

## Fichiers

- `lib/services/rpcs3_save_exchange_service.dart` (nouveau)
- `lib/services/rpcs3_param_sfo.dart` (nouveau)
- `lib/l10n/rpcs3_saves_locale.dart` (nouveau)
- `lib/widgets/rpcs3_save_exchange_dialogs.dart` (nouveau)
- `lib/services/rpcs3_internal_service.dart` : `filesWorkspaceDirectory`,
  `synchronizeFilesWorkspace`, `runSaveExchange` et les deux enveloppes ;
  `_copyTree`, `_copyReplacing`, `_allowedSavestateFile` et les anciens corps
  retirés. JIT, Core, firmware et lancement inchangés.
- `lib/screens/rpcs3_manager_screen.dart` : `_exportSaves`, `_importSaves`,
  `_showSaveFailure`, `_shareExport`.
- `lib/l10n/rpcs3_ui_locale.dart` : deux clés, douze langues.
- Tests : `test/rpcs3_save_exchange_service_test.dart`,
  `test/rpcs3_saves_locale_test.dart` (nouveaux) ;
  `test/rpcs3_save_export_contract_test.dart` (contrat réécrit pour le
  nouveau comportement), `test/diagnostics_files_workspace_test.py`
  (jetons de la consommation remplacés par ceux du nouveau comportement :
  plus de `delete`/`copy`/`rename` dans le démarrage, service d'échange
  présent), `test/rpcs3_ui_status_cleanup_test.py` (appel conservé, lecture
  UTF-8 explicite : le script échouait déjà sous Windows avec l'encodage
  cp1252 par défaut), `test/localization_12_locale_coverage_test.py`
  (catalogue ajouté).
- `docs/rpcs3-save-exchange-build442.md` (ce document).

Inchangés : `lib/main.dart`, `packages/`, `build-utils/`, `.github/`,
`pubspec.yaml`, `pubspec.lock`, `rpcs3_internal_playlist_actions.dart`,
`rpcs3_rap_licence_service.dart`, Core, pont, cœurs, `PATCH_SHA256`.

## Vérifications

Sous Windows 11 (Flutter 3.47.2, Python 3.12, `-I`), le 11 octobre 2026 :

- `flutter test test/rpcs3_save_exchange_service_test.dart
  test/rpcs3_saves_locale_test.dart test/rpcs3_save_export_contract_test.dart
  test/rpcs3_internal_integration_test.dart test/rpcs3_firmware_library_test.dart
  test/rpcs3_rap_import_menu_test.dart test/rpcs3_rap_licence_service_test.dart
  test/rpcs3_lazy_load_contract_test.dart` : 123 tests, tous réussis. Le
  service est testé avec des dossiers temporaires (racines injectées, sans
  `path_provider`) : export (contenu de l'archive, arborescence vivante
  intacte, suffixe, refus sans sauvegarde et sous redirection `vfs.yml`),
  import depuis un ZIP avec dossier parent, depuis un dossier (lui-même ou
  jusqu'à trois niveaux), depuis le dossier Fichiers (sources non
  consommées), analyseur `PARAM.SFO` sur une fixture construite, refus de
  traversée/absolu/barre inverse/segment vide, lien symbolique, nombre
  d'entrées, tailles (limites injectées), archive invalide, nom invalide,
  `PARAM.SFO` illisible, doublon, entrée « stored », conflit → copie de
  secours déplacée puis remplacement, conserver → intact, déjà présente →
  non réécrite, comparaison exacte des noms, redirection `vfs.yml`, zone de
  transit obsolète nettoyée, garde (jeu en cours par état d'émulation
  injecté, échange imbriqué, libération après exception), démarrage
  (dossiers et README seulement, contenu d'Import/Export intact). Le test du
  lien symbolique dans un dossier se retire de lui-même quand l'hôte ne
  permet pas d'en créer ; le cas ZIP le couvre partout.
- `python -I test/rpcs3_ui_status_cleanup_test.py`,
  `test/diagnostics_files_workspace_test.py`,
  `test/localization_12_locale_coverage_test.py` : PASS.
- `flutter analyze --no-fatal-infos` : aucune erreur ni avertissement ;
  aucun nouveau message dans les fichiers de ce paquet (les 52 informations
  restantes préexistent ailleurs).

NTFS ne distinguant pas les majuscules, les tests comparent les noms exacts
listés et le service fait de même pour reproduire iOS. Ni la feuille de
partage, ni les sélecteurs iOS, ni `emulationState` réel ne sont exercés sur
Windows.

À exécuter sur iPhone (Build 442 signée par SideStore) :

1. Jouer à un titre PS3 jusqu'à une sauvegarde en jeu, fermer le jeu, puis
   « Exporter les sauvegardes de jeu » : le rapport annonce le nombre de
   sauvegardes, de fichiers, la taille et le nom `RPCS3-saves-….zip` ; le
   fichier est visible dans Fichiers › Sur mon iPhone › NeoStation › RPCS3 ›
   Export › Game Saves et s'ouvre (aperçu ZIP) ; « Partager… » propose
   iCloud Drive et AirDrop.
2. Pendant qu'un jeu PS3 tourne (NeoStation au premier plan via le menu en
   jeu ou retour), les deux boutons refusent avec le message « Fermez-le
   d'abord ».
3. Environnement de test : après l'export, supprimer la sauvegarde dans
   RPCS3 (ou la déplacer) puis importer l'archive par « Choisir une archive
   ZIP… » (copie du sélecteur) et par le dossier Fichiers (archive déposée
   dans Import › Game Saves, puis dossier décompressé dans Fichiers, qui
   produit `RPCS3-saves-…/savedata/<DIR>`) : lignes « importée », puis
   relancer le jeu et retrouver la progression dans le menu de chargement du
   jeu (RPCS3 liste la sauvegarde sans autre étape).
4. Réimport de la même archive : « déjà présente », date du dossier
   inchangée. Archive contenant une sauvegarde différente sous le même
   `<DIR>` : demande unique, « Remplacer » crée `RPCS3/SaveBackups/<DIR>-<UTC>`
   (vérifiable par un export de diagnostic ou le journal), « Conserver »
   laisse tout intact.
5. « Choisir un dossier de sauvegarde… » sur un dossier d'iCloud Drive (téléchargé
   et non téléchargé) et sur un dossier de « Sur mon iPhone » ; les imports
   de jeux (dossier, ISO, PKG/ZIP) et de licences fonctionnent juste après
   (portées de sécurité libérées).
6. Vérifier l'absence de dossier `.neostation-save-import-*` restant dans
   `home/00000001` après une interruption volontaire (fermeture de l'app
   pendant un import volumineux, puis nouvel import).
7. Démarrage : déposer un dossier dans Import › Game Saves, relancer
   NeoStation deux fois : le dossier est toujours là, `Export` n'est pas
   vidé, le `README.txt` décrit les flux manuels.
8. Manette : boîte de choix de la source, demande de remplacement et
   rapports pilotables à la croix, A et B.

Le choix d'un sélecteur en mode copie pour les dossiers iCloud non
téléchargés, et toute reprise des savestates, seraient des décisions
séparées.
