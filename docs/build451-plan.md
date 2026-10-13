# Build 451 — import 3DS des titres chiffrés par Azahar pour leur console

Demande du mainteneur : « je ne peux toujours pas importer un dossier Nand-zip pour la 3DS ». Il a fourni le ZIP
qui échoue, `nand.zip`, sur son PC. Ce fichier a été examiné en lecture seule par Desktop Commander : noms,
tailles, en-têtes. Rien n'a été copié ni versionné.

Base : Build 450 (`e7f223365a12327c62bfc154b0bddd789d2a0131`).
- Aucun cœur, natif, helper JIT ni fichier verrouillé sur la Build 419 n'est modifié.
- `pubspec.lock` est identique.
- `pubspec.yaml` passe à `0.0.7+451`.

## Cause

Le ZIP est le dossier `nand` d'un dossier utilisateur Azahar : 133 titres système, TMD lisibles. Les contenus
(`.app`) de 129 de ces titres sont stockés chiffrés pour leur console, dans l'ancienne forme qu'Azahar lit encore
(« Legacy mode » de `CryptoIOFile`). C'est AES-CTR sur tout le fichier, sans en-tête `AZCR`. La clé est dérivée de
l'OTP de la console.
- **Démontré sur le fichier.** Les 140 contenus partagent un seul flux de clé. Il est obtenu sur quatre champs que
  tout NCCH porte en clair, dont la taille et l'identifiant de titre, qui varient d'un fichier à l'autre.
- **Défaut de NeoStation.** L'import ne reconnaissait que la forme à en-tête `AZCR`. Il refusait donc ces 129 titres
  comme invalides, alors que le cœur les lit avec l'`otp.bin` de la console.
- **Fichier manquant.** Cet `otp.bin` n'est pas dans le ZIP : Azahar le range dans `sysdata`, à côté de `nand`.

Détail, sources amont (azahar `a5c3d4f8`) et limites : `docs/libretro-3ds-system-settings.md` § 9.

## Correctif

| Élément | Contenu |
| --- | --- |
| Reconnaissance | Empreinte sans clé de chaque contenu sans en-tête lisible (`consoleCryptoFingerprint`) : SHA-256 du flux sur ces champs. Un contenu n'est gardé que si un contenu d'un autre titre ou d'une autre taille confirme son empreinte, et si l'import ne contient qu'une seule empreinte confirmée. Un contenu isolé, chiffré titre par titre ou issu de deux consoles reste refusé. |
| Installation | Un tel titre (`consoleEncrypted`) n'est installé que si `sysdata/otp.bin` est déjà en place, ou s'il est importé avec la case « données de console ». Sinon il est laissé de côté. Les octets installés sont ceux du ZIP. |
| Copie | Un gros contenu, sans SHA-256 à l'analyse, doit redonner la même empreinte une fois copié. |
| Textes | `system3dsConsoleEncrypted`, douze langues. Il apparaît une fois par groupe du plan et une fois dans le résultat. |
| Porte de livraison | Bloc `BUILD451_DELTA` : 7 entrées revues depuis `e7f22336`. |

La règle de la Build 448 est conservée : un NCCH chiffré (sans NoCrypto) reste refusé, et aucun texte ne présente un
fichier de clés comme remède. `otp.bin` est une donnée de console, nommée parce que le cœur en dérive réellement la
clé de ces titres.

## Où

Onglet Consoles › Nintendo 3DS › « Réglages système » › « Importer des données système » › Un ZIP (ou Dossier).

Ce que donnera le ZIP du mainteneur :
- **Seul** : les 4 titres DS, et les données de console si la case est cochée. Les 129 titres sont laissés de côté,
  avec l'explication.
- **Avec `sysdata/otp.bin` du même dossier Azahar** (dans le même ZIP ou importé avant), case cochée : les 133
  titres.

## Vérifications

Exécuté dans ce conteneur (Linux x86_64, Flutter 3.47.2) :

| Contrôle | Résultat |
| --- | --- |
| Service 3DS : 64 tests existants et 5 nouveaux (groupe « titles Azahar encrypted for their console (Build 451) ») | réussis |
| Écran 3DS : 2 nouveaux tests (texte et contenus laissés de côté sans `otp.bin` ; installés avec `otp.bin` et la case) | réussis |
| `libretro_locale_test` et tests 3DS de langue, de chiffrement au lancement et de défaut de lancement : 132 tests au total | réussis |
| `flutter analyze` des fichiers Dart modifiés | aucun problème |
| Porte `verify_delivery_reuse.py --offline` (bloc `BUILD451_DELTA`) | réussie |
| `delivery_pipeline_test.py` | 13 sur 13 (`zstd` installé dans le conteneur) |

## Ce qui n'est pas vérifié

- Aucun import ni lancement sur iPhone.
- L'import ne peut pas vérifier que l'`otp.bin` fourni est celui de la console qui a chiffré les titres. Un autre
  `otp.bin` les laisse illisibles, et le cœur les traite alors comme absents.
- La présence des clés OTP intégrées dans le binaire du buildbot n'est pas prouvée. Elles sont activées par défaut à
  `a5c3d4f8` et dans la recette iOS d'Azahar.
- Azahar annonce le retrait futur du « Legacy mode ».
