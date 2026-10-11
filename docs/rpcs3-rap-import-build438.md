# Licences RAP pour RPCS3 — Build 438 (paquet B)

Demande du mainteneur du 11 octobre 2026 (`docs/build438-plan.md`,
section B) : dans le menu Importer de la bibliothèque PS3, à côté des dossiers
décryptés et des ISO, ajouter « Importer des licences RAP » (anglais :
« Import RAP licenses »), installer les fichiers là où RPCS3 les cherche et
rendre compte de chaque fichier. Aucune validation sur iPhone n'est
revendiquée ici.

## Où le Core épinglé lit une licence

Sources XITRIX/rpcs3 `22f1152783cef1f7e04af7b1c895173e28fd5b03`
(`build-utils/rpcs3/canonical-source.json`), lues avant application de
`embedded-core.patch` :

| Fait | Référence |
| --- | --- |
| `get_rap_file_path(content_id)` parcourt chaque utilisateur valide de `get_hdd0_dir() + "home"` et retourne le premier `<utilisateur>/exdata/<content_id>.rap` qui est un fichier. | `rpcs3/Emu/system_utils.cpp:405-428` |
| Utilisateur valide : nom de 8 caractères dont le préfixe numérique est non nul ; Content ID accepté : `[A-Za-z0-9_-]`, 0x30 caractères au plus. | `system_utils.cpp:70-79`, `:392-402` |
| La licence fait 16 octets : `GetKeyFromRap` (SELF NPDRM, types 1 et 2), `GetEdatRifKeyFromRapFile` (EDAT), `npDrmIsAvailable` (`BAD_FORMAT` sous 16 octets, `LICENSE_NOT_FOUND` absent). Le message fatal demande une extension en minuscules. | `rpcs3/Crypto/unself.cpp:1081-1095`, `:1312-1343` ; `rpcs3/Crypto/unedat.cpp:678-688`, `:842` ; `rpcs3/Emu/Cell/Modules/sceNp.cpp:702-717` |
| `dev_hdd0` vaut `$(EmulatorDir)dev_hdd0/`, et un `$(EmulatorDir)` vide désigne le dossier de configuration. `vfs.yml` est lu dans ce même dossier. | `rpcs3/Emu/vfs_config.h:12-13`, `vfs_config.cpp:144`, `system_utils.cpp:157-166` |
| Sous iOS, le dossier de configuration est le `support_path` transmis par l'hôte. | `Utilities/File.cpp:2537-2546`, `:2691` |
| Le Core iOS choisit toujours l'utilisateur `00000001` ; `Emu::Init` crée `home/<usr>/exdata/` et accepte un dossier existant. | `rpcs3/ios/RPCS3IOS.cpp:1393` (`Emu.SetUsr("00000001")`) ; `rpcs3/Emu/System.cpp:458-484`, `:674` |

NeoStation transmet `supportPath = <AppSupport>/NeoStation/RPCS3/Data`
(`Rpcs3InternalService.dataDirectory()`). La licence se place donc dans
`<AppSupport>/NeoStation/RPCS3/Data/dev_hdd0/home/00000001/exdata/<CONTENT_ID>.rap`.
Le système de fichiers d'iOS distingue les majuscules : RPCS3 construit le nom
à partir de l'en-tête NPD (Content ID en majuscules) et ne trouverait jamais
`x.RAP` ni un ID en minuscules.

Le Core exporte aussi `rpcs3_ios_install_rap` (`RPCS3IOS.cpp:1703`), mais le
pont NeoStation ne le charge pas et il exigerait le Core prêt (VPN, appairage,
JIT). L'import est donc fait en Dart : mêmes octets au même endroit, sans Core,
JIT, ni modification native. `embedded-core.patch` ne touche ni la recherche
de licence, ni l'utilisateur, ni la racine VFS ; c'est vérifié par
`test/rpcs3_rap_core_contract_test.py`, qui échoue aussi si le Core est
rebasé (nouveau commit amont) : la recherche doit alors être revérifiée dans
les nouvelles sources.

## Comportement livré

- **Entrée** : `Importer des licences RAP` dans le menu Importer existant
  (bibliothèque plein écran et onglet intégré), juste après l'import de
  dossier. Le menu reste réservé au firmware installé, comme les autres
  imports.
- **Sélection** : sélecteur ouvert sur place existant
  (`Rpcs3InternalBridge.pickGameFilesOpenInPlace`), sélection multiple, tous
  fournisseurs Fichiers (iCloud compris). Les 16 octets de chaque fichier sont
  lus puis `releaseScopedResources` est toujours appelé (`finally`), y compris
  après une annulation ou une erreur, avant toute boîte de dialogue.
- **Format** : extension `.rap` en toute casse ; nom = Content ID de
  36 caractères `XXNNNN-XXXXNNNNN_NN-<16 caractères>` (les majuscules sont
  rétablies) ; suffixe de doublon retiré (` (1)` des téléchargements, ` 2` de
  « Garder les deux » dans Fichiers ; un Content ID ne contient jamais
  d'espace) ; taille exactement 16 octets (contrôle de la taille puis lecture
  bornée à 17 octets).
- **Installation** : `exdata/<CONTENT_ID>.rap`, extension en minuscules,
  écrit dans un fichier temporaire du même dossier (`flush`), relu, renommé,
  puis relu à nouveau. Le dossier `exdata` doit se résoudre dans `Data`.
  Un fichier temporaire est supprimé en cas d'échec.
- **Déjà présente** : mêmes octets déjà installés sous ce nom exact ; le
  fichier n'est pas réécrit (date inchangée).
- **Conflit** : contenu différent sous le même ID. Une seule demande pour
  toute la sélection (liste des Content ID). Remplacer : l'ancien fichier est
  d'abord copié dans `<AppSupport>/NeoStation/RPCS3/RapBackups/<ID>-<horodatage UTC>.rap`
  (hors de l'arborescence du Core, jamais supprimé), puis la nouvelle licence
  est installée (« remplacée »). Conserver, B ou fermeture : l'ancienne reste
  (« refusée », motif « conservée »).
- **Même ID deux fois dans la sélection** : le premier fichier décide ; une
  copie identique suit son résultat, une copie différente est refusée
  (« seul le premier a été utilisé »).
- **Garde `Data/vfs.yml`** : si ce fichier redirige `dev_hdd0` (ou
  `$(EmulatorDir)`) hors de `Data/dev_hdd0/`, ou s'il est illisible, aucune
  licence n'est écrite et chaque fichier valide est refusé avec ce motif.
  NeoStation n'écrit jamais ce fichier.
- **Rapport** : une ligne par fichier dans l'ordre du sélecteur — nom brut,
  statut traduit (importée / remplacée / déjà présente / refusée), nom
  installé quand il diffère, motif traduit, diagnostic système brut séparé.
  Résumé par statut en tête. Bouton Fermer focalisé ; manette : croix pour se
  déplacer (les lignes sont focalisables pour faire défiler), A pour activer,
  B pour fermer (`LibraryFocusGamepadLayer`).
- **Sans effet ailleurs** : pas de surcouche de progression (la surcouche
  racine du mode intégré masquerait les dialogues), pas d'appel à
  `onLibraryChanged`, aucune tuile de jeu (le scanner ne lit pas
  `dev_hdd0/home`), aucun appel Core/JIT, aucune autre écriture que
  `exdata/<ID>.rap`, son fichier temporaire et `RapBackups`. Sauvegardes,
  savestates, firmware, `games.yml`, réglages et licences existantes restent
  intacts ; la suppression d'un jeu conservait déjà les licences.

Seul l'utilisateur `00000001` est consulté : le Core iOS n'en utilise pas
d'autre et NeoStation n'en crée pas. `Rpcs3RapLicenceService.resolveLikeRpcs3`
reproduit la recherche complète de RPCS3 pour les tests.

## Traductions

`lib/l10n/rpcs3_rap_locale.dart` couvre les douze langues (`en`, `es`, `ru`,
`zh`, `zh_Hant`, `pt`, `fr`, `de`, `it`, `id`, `ja`, `ko`) ; le chinois
traditionnel est choisi par l'écriture Hant ou la région TW, HK ou MO.
L'anglais suit l'orthographe américaine demandée (« licenses »). Les noms de
fichiers, Content ID, chemins et diagnostics restent bruts.

## Fichiers

- `lib/services/rpcs3_rap_licence_service.dart` (nouveau)
- `lib/l10n/rpcs3_rap_locale.dart` (nouveau)
- `lib/widgets/rpcs3_rap_import_report_dialog.dart` (nouveau)
- `lib/widgets/rpcs3_internal_playlist_actions.dart` (entrée de menu, branche
  `licences`, surcouche non affichée pour cette action ; branches `games` et
  `folder` inchangées)
- Tests : `test/rpcs3_rap_licence_service_test.dart`,
  `test/rpcs3_rap_locale_test.dart`, `test/rpcs3_rap_import_menu_test.dart`,
  `test/rpcs3_rap_core_contract_test.py` (nouveaux) ;
  `test/rpcs3_internal_integration_test.dart` (valeur `licences`),
  `test/rpcs3_firmware_library_test.dart` (libellés actuels),
  `test/localization_12_locale_coverage_test.py` (catalogue ajouté).

Inchangés : Core, pont, code natif, cœurs, `PATCH_SHA256`,
`rpcs3_content_import_service.dart`, `rpcs3_internal_service.dart`,
`rpcs3_library_service.dart`, `my_games_list.dart` et les fichiers verrouillés
de la baseline.

## Vérifications

Sous Windows (Flutter 3.47.2) : les trois tests Dart nouveaux, les tests RPCS3
voisins et les deux scripts Python passent. NTFS ne distinguant pas les
majuscules, les tests comparent les noms exacts listés et le service fait de
même pour reproduire iOS. Le test `rpcs3_firmware_library_test.dart`
« installed firmware opens import menu » échouait déjà sur la base
`a434881e` (libellés antérieurs à `f1d19e58` et `9420bdcf`, export des
sauvegardes déplacé dans le gestionnaire RPCS3) : il vérifie désormais les
libellés actuels et la nouvelle entrée.

À exécuter sur iPhone (Build 438 signée par SideStore) :

1. L'entrée apparaît dans la bibliothèque plein écran et dans l'onglet
   intégré, au toucher et à la manette.
2. Sélection multiple de `.rap` et `.RAP` depuis Sur mon iPhone, iCloud Drive
   (téléchargé et non téléchargé avec l'optimisation du stockage) et un
   fournisseur tiers ; rapport correct pour chaque fichier.
3. Un titre PSN (licence NPDRM 1 ou 2) ou un DLC EDAT sous licence démarre ;
   `core_log` ne contient ni « Failed to locate the game license file », ni
   « Can't find RAP file », ni « A valid RAP file is needed », ni « Rap file
   not found ». L'absence du message « Loading RAP file » ne prouve rien (filtré
   au niveau 6 par `Rpcs3InternalBridgePlugin.mm`).
4. Réimport : « déjà présente » ; licence différente : demande puis sauvegarde
   dans `RapBackups`.
5. Les imports de dossier, d'ISO et de PKG/ZIP fonctionnent juste après un
   import de licences (portées de sécurité libérées).
6. Aucune nouvelle tuile ; sauvegardes, savestates et réglages intacts ; la
   licence persiste après relance et mise à jour.

Si le sélecteur ouvert sur place renvoie des fichiers iCloud non téléchargés,
ils sont signalés « refusée » avec le conseil de les télécharger dans
Fichiers ; un passage au sélecteur en mode copie serait une décision séparée.
