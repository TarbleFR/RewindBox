# Build 454 — import 3DS : la vérification de session réparée

Demande du mainteneur du 13 octobre 2026, avec une vidéo (`ScreenRecording_10-13-2026_09-45-07_1.mov`, Build 453) :
corriger l'import des BIOS et données système 3DS. Choisir le dossier Azahar, puis le dossier `sysdata`, affiche
« Impossible de vérifier si un jeu est en cours : rien n'a été modifié. Réessayez. », code technique
`isSessionActive probe failed: type 'int' is not a subtype of type 'bool?' in type cast`. Corriger cette erreur
avant de conclure à un problème de fichiers BIOS ; ajouter un test du véritable encodage natif/Flutter ; livrer une
IPA.

Base : Build 453, source `81efc2109e1052678bd881b8fc7c8dc1c53aa8bc` (la branche était à `39a88f25`, documentation
seule depuis).
- Le paquet de cœurs `8b9e87ba` (Azahar officiel 2127.0-alpha1, Fast Interpreter) et les 13 autres cœurs ne
  changent pas. Aucun helper JIT, réglage d'émulation ni fichier verrouillé sur la Build 419 n'est modifié.
- `pubspec.lock` est identique ; `pubspec.yaml` passe à `0.0.7+454`.

## Ce que montre la vidéo

- **Écran.** Page « Système Nintendo 3DS », ouverte depuis la console Nintendo 3DS de la bibliothèque (Mario Kart 7),
  bouton « Importer des données système ».
- **Premier essai.** « Un dossier (dump GodMode9 ou dossier utilisateur Citra, Lime3DS, Azahar) », puis le dossier
  `Azahar` d'iCloud Drive : 9 éléments, `cheats`, `config`, `log`, `nand` (6 éléments), `nand.zip` (203,2 Mo),
  `screenshots`, `sdmc`, `shaders`, `sysdata` (5 éléments).
- **Second essai.** « Des fichiers isolés », puis les cinq fichiers de `sysdata` : `mac` (17 octets), `mcu.dat`
  (24), `otp.bin` (256), `play_time.bin` (32), `seeddb.bin`.
- **Résultat, les deux fois.** Le message ci-dessus, sans plan d'import : l'analyse des fichiers n'a pas commencé.
- **Inventaire affiché.** Titres NAND 0, polices absentes ; données de console : `config` (32,8 Ko) et `mcu.dat`
  présents, `otp.bin` absent.

## Cause (démontrée)

1. **Le refus.** L'assistant appelle `recoverUnfinished()` avant l'analyse, puis `install()`. Les deux demandent au
   pont si un jeu est lancé ou en cours ; un échec de cette sonde est un état inconnu, et rien n'est écrit. C'est le
   comportement voulu : le défaut est dans la réponse du pont.
2. **Le natif.** `LibretroInternalBridgePlugin.m` répondait `result(@(self.session.active || self.launching))`.
   - Ce fichier est en Objective-C, où `a || b` est un `int` du C. clang l'encapsule donc avec `numberWithInt:`.
   - Vérifié avec l'AST de clang 18, cible `arm64-apple-ios18.0`, sur ce code :
     `BinaryOperator 'int' '||'`, puis `ObjCBoxedExpr selector=numberWithInt:`.
   - Dans un fichier `.mm` (Objective-C++), la même expression est un `bool` et passe par `numberWithBool:`. C'est
     le cas des ponts Dolphin et RPCS3, qui ne sont pas touchés.
   - Dans tout le dépôt, c'est la seule réponse de produit de cette forme (recherche sur les 64 fichiers `.m`).
3. **Le codec.** Flutter iOS 3.47.2 (`FlutterStandardCodecHelperWriteNumber`, moteur `a804b261`) n'écrit
   `true`/`false` que pour un `CFBoolean`, c'est-à-dire `@YES`/`@NO`.
   - Tout autre `NSNumber` de 4 octets part en int32.
   - Sans jeu, l'iPhone recevait `00 03 00 00 00 00` au lieu de `00 02`.
4. **Le Dart.** `invokeMethod<bool>` fait `as bool?` sur l'entier 0 et lève la `TypeError` de la vidéo.
   - Reproduit dans ce conteneur avec ces octets exacts : même message, mot pour mot.
5. **Depuis quand, et pourquoi non vu.** Le défaut est présent depuis l'intégration du moteur (`48635465`,
   9 octobre). Les tests simulaient le canal avec des booléens Dart, dont les octets (`00 01`/`00 02`) sont ceux du
   pont corrigé, ou injectaient une fonction Dart.

Les fichiers BIOS du mainteneur ne sont pas en cause : rien n'a été lu.

### Autres effets de la même cause (sources ; non observés sur iPhone)

- **Réglages de la page 3DS.** Langue, région et modèle passent par `LibretroCoreOptionStore` : ils étaient refusés
  de la même façon.
- **Moniteur de lancement.** Pendant un jeu libretro, `GameLaunchManager` sonde `isSessionActive` toutes les 2 s.
  - La `TypeError` sortait d'`EmbeddedIOSSessionStatus.isActive` (qui n'attrapait que `PlatformException` et
    `MissingPluginException`).
  - Le sondeur fermait alors la session Flutter environ 4 s après le lancement : temps de jeu enregistré d'environ
    4 s, barrière média relâchée (aperçus et musique d'ambiance pouvaient reprendre derrière le jeu), dialogue de
    lancement retiré, navigation réactivée.
  - Avec le correctif, la session Flutter dure jusqu'à la fin réelle du jeu, comme pour Dolphin et RPCS3.
- **Nettoyage du stockage.** La sonde en échec comptait comme « occupée » : les fichiers libretro étaient toujours
  exclus.

## Correctif

| Élément | Contenu |
| --- | --- |
| Pont natif | `result((self.session.active \|\| self.launching) ? @YES : @NO)` : `@YES`/`@NO` sont des `CFBoolean`, envoyés `true`/`false`. |
| Pont Dart | `LibretroInternalBridge.isSessionActive()` n'accepte qu'un booléen. Une réponse `null` ou d'un autre type lève `LibretroSessionProbeException` (« non-boolean answer (int 0) »), comme les erreurs du canal ; le `?? false` qui changeait `null` en « aucun jeu » est retiré. |
| Moniteur de lancement | `EmbeddedIOSSessionStatus.isActive` : seul un `false` explicite termine une session ; une réponse absente ou non booléenne la garde active. |
| Import 3DS | Inchangé (règles des Builds 448 à 452), sauf un point du parcours vérifié : le `nand.zip` rangé dans le dossier Azahar était refusé en rouge, « Archive non prise en charge : seules les archives ZIP sont lues ». Une archive ZIP trouvée dans le dossier ou le ZIP choisi n'est toujours pas ouverte ; elle est maintenant listée à part, avec la façon de l'importer (« choisissez-la avec « Une archive ZIP » »). Les autres archives restent refusées. |
| Textes | `system3dsIgnoredNestedZip`, douze langues. Les messages de session (`system3dsSessionUnknown`, `system3dsSessionActive`) ne changent pas. |
| Porte de livraison | Bloc `BUILD454_DELTA` : 18 entrées revues depuis `81efc210`. |

Résultats attendus de la demande :
1. Sans session, l'import fonctionne (réponse `00 02`).
2. Pendant le lancement (`launching`) ou l'exécution (fil d'émulation présent), il est refusé avec « Impossible
   pendant qu'un jeu est en cours » (réponse `00 01`) ; rien n'est écrit.
3. Une erreur du canal, une absence de plugin, une réponse `null` ou une valeur inconnue (l'int32 de la 453
   compris) donnent l'état inconnu, jamais « aucun jeu ».

## Tests

### L'encodage réel, du plugin natif à Dart (nouveau)

- **`test/libretro_channel_codec_test.py` et `test/libretro_channel_codec/main.m`** (macOS, Simulateur iOS).
  - Le vrai `LibretroInternalBridgePlugin.m` et toutes les sources du pont sont compilés avec le vrai
    `Flutter.framework` du SDK épinglé : tranche Simulateur de `Flutter.xcframework`, Flutter 3.47.2.
  - Le plugin répond dans les quatre états d'un lancement : aucune session ; session créée et `launching` ; fil
    d'émulation présent (getter réel `active`) ; fil disparu.
  - `FlutterStandardMethodCodec` encode chaque réponse comme le moteur l'envoie à Dart.
  - Les octets doivent être ceux de `test/libretro_session_envelopes.dart` : `fixedEnvelopes` pour cette source,
    `build453Envelopes` (int32) pour les sources de la 453 (`--expect unfixed`).
  - Toute différence fait échouer le test : il distingue les deux sources.
- **`test/libretro_session_probe_codec_test.dart`** : ces octets passés au vrai `MethodChannel`, avec la sonde de
  production (aucune fonction injectée).
  - Couverts : le pont, le moniteur de lancement, le service 3DS (installation, restauration, reprise), le magasin
    d'options et la garde du stockage.
  - Avec les octets de la 453, le cast de l'ancien appel donne le message exact de la vidéo.
- **`test/libretro_3ds_system_screen_test.dart`.**
  - Le canal du pont répond désormais avec ces octets dans tous les tests de la page, et plus avec des booléens
    Dart.
  - Nouveau groupe « the import of the video », jusqu'à l'inventaire actualisé :
    - la vidéo : refus avant analyse avec les octets de la 453, puis plan avec ceux de la 454 ;
    - le dossier Azahar complet, avec `nand.zip`, `mac` et `play_time.bin` ;
    - `nand` seul (titres en attente de `otp.bin`), puis `sysdata`, puis `nand` à nouveau (titres installés) ;
    - les cinq fichiers isolés de `sysdata` ;
    - `nand.zip` choisi comme ZIP, `otp.bin` déjà en place ;
    - refus pendant le lancement et le jeu, puis import une fois le jeu arrêté.
- **`test/libretro_3ds_system_data_service_test.dart`.** ZIP imbriqué : contrat remplacé et commenté. Nouveau test
  d'un dossier Azahar avec `nand.zip`, un cache de shaders et une archive 7z.
- **`test/external_display_host_plist_test.py`.** Le compte exact des étapes du job `native` de la livraison qui
  partagent les conditions libretro, après la compilation iPhone, passe de 2 à 3. Le changement est commenté, et
  l'étape du test d'encodage est exigée.

### Exécuté dans ce conteneur (Linux x86_64, Flutter 3.47.2)

| Contrôle | Résultat |
| --- | --- |
| Reproduction : octets `00 03 00 00 00 00` donnés au code Dart de la 453 | `type 'int' is not a subtype of type 'bool?' in type cast`, comme sur l'iPhone |
| AST clang 18 (`arm64-apple-ios18.0`) de l'expression, en `.m` et en `.mm` | `numberWithInt:` en Objective-C, `numberWithBool:` en Objective-C++ ; la forme corrigée donne `numberWithBool:` |
| Série `flutter test` du job `dart` de `libretro-checks`, avec le nouveau test | 534 tests réussis |
| `flutter test test/storage_*_test.dart` | 244 réussis, 1 ignoré comme avant |
| Dernière ligne `flutter test` du job `checks` de la livraison (avec le nouveau test) | 637 tests réussis |
| `flutter analyze --no-fatal-infos` | aucune erreur ni avertissement ; aucun signalement dans les fichiers modifiés |
| `verify_delivery_reuse.py --offline` (bloc `BUILD454_DELTA`) | réussie |
| Les 35 tests Python du job `checks` de la livraison | 34 réussis ; `library_cover_delivery_test.py` échoue à l'identique sans ce changement (porte du périmètre `library_covers`, échec connu des Builds 449 à 453) |

Le test d'encodage natif ne peut pas s'exécuter ici (ni Xcode ni Simulateur) : il s'exécute en CI macOS.

### CI

`libretro-checks` `38369576779`, branche `Claude`, source `5c85bc7c` (code et tests de cette build ; les commits
suivants ne changent que la version, la porte, la documentation et la mise en forme d'un test Dart, relancé par la
livraison) : réussi.
- **Job `dart`** : analyse, série Dart avec le nouveau test, contrats de sources.
- **Job `native`** : hôte, modules, shaders Metal, ponts compilés pour iPhone, puis le test d'encodage.
  - Simulateur : iPhone SE (3e génération), iOS 26.2.
  - Flutter 3.47.2, moteur `a804b261`, tranche `ios-arm64_x86_64-simulator`.
  - 71 sources du pont et 58 du kit de shaders compilées pour chaque arbre.

Réponses de `isSessionActive`, encodées par `FlutterStandardMethodCodec` :

| État | Cette source (`5c85bc7c`) | Build 453 (`81efc210`) |
| --- | --- | --- |
| aucune session | `__NSCFBoolean` `c`, `00 02` | `__NSCFNumber` `i`, `00 03 00 00 00 00` |
| lancement (`launching`) | `00 01` | `00 03 01 00 00 00` |
| jeu en cours (fil présent) | `00 01` | `00 03 01 00 00 00` |
| arrêté (fil disparu) | `00 02` | `00 03 00 00 00 00` |

- La source 453 donne « REPRODUCED … every answer is an int32, never a Dart bool ». C'est l'octet `03` qui faisait
  échouer le cast Dart sur l'iPhone.
- Preuves : artefact `libretro-channel-codec-5c85bc7c…`, ID `11798298346`.

Autres runs déclenchés par le même envoi :
- `external-display-check` `38369576889` : réussi (contrats, syntaxe iPhone, XCTest du Simulateur).
- `libretro-simulator` `38369576801` : réussi (sonde, avant correctif Vulkan, avant réservation PSP).

`libretro-checks` `38370661152` sur la source livrée `6dcdfd1a` : réussi, avec les mêmes octets pour les deux
arbres.

## Livraison

- **Run.** `retroarch-delivery.yml` `38370668542`, lancé sur `Claude` (`build_number` 454, périmètre `full`), depuis
  la source `6dcdfd1aa903c8efb28d5d4bc4cd04464f395255`, qui contient ce plan.
  - Jobs `checks`, `native` et `Release device build • cold` réussis.
  - Le job `native` comprend le test d'encodage : quatre réponses booléennes (`00 02`, `00 01`, `00 01`, `00 02`).
  - Horaires : 08:38 → 09:00 UTC, 13 octobre 2026. Compilation Xcode : 266 s.
- **Validation de l'IPA avant scellement.**
  - `NeoStation.ipa`, 206 619 559 octets, SHA-256 `29c4d0a6c1612cdc0a65ab81eec0ca5eb97cd5d61f68e92a0d3ffc41eeebb973`.
  - Version 0.0.7 (454), commit `6dcdfd1a`, validation structurelle et mentions légales réussies.
  - « Libretro IPA validation passed » pour les 14 cœurs, dont `azahar` (2127.0-alpha1, Fast Interpreter).
  - Signature de l'app vérifiée (« valid on disk », « satisfies its Designated Requirement »).
- **Artefact.** `NeoStation-Build-454-6dcdfd1aa903c8efb28d5d4bc4cd04464f395255-cold`.
  - ID `11799289148`, 211 053 981 octets.
  - SHA-256 de l'archive : `5d0cb69bad10537383b650c47604573b6a70f5f4f64c17563021e6b409c1b2d8`.
  - Conservé jusqu'au 27 octobre 2026, chiffré pour `build-utils/delivery-424-recipient.pem` (clé du PC du
    mainteneur).
- **Diagnostics chiffrés.** `…-cold-diagnostics`, ID `11799388528`, 5 171 133 octets.
- **IPA scellée.** `NeoStation-Build454-6dcdfd1aa903c8efb28d5d4bc4cd04464f395255-cold.ipa` dans l'archive, avec
  `SHA256SUMS` et `signed-payload-identity.json`.
  - Son SHA-256 est à relever après déchiffrement : le scellement pour SideStore recrée l'IPA, et l'empreinte
    `29c4d0a6…` ci-dessus n'est pas celle du fichier remis.
  - Le PC du mainteneur était hors ligne (Desktop Commander, vu pour la dernière fois deux heures avant), et ce
    conteneur ne peut pas télécharger les artefacts (politique de sortie) : aucune copie n'a été déposée dans
    `Downloads`.
- **Déchiffrement** (sur le modèle de `decrypt-452.ps1`, avec la clé privée 424) :
  1. `openssl pkeyutl -decrypt -inkey <clé 424> -in password.rsa -out password -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256` ;
  2. `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass file:password -in artifact.tar.enc -out artifact.tar` ;
  3. `tar -xf artifact.tar`, puis comparer le SHA-256 de l'IPA à `SHA256SUMS`.
- L'IPA est scellée pour la re-signature Apple et le provisioning que SideStore applique. Ne pas réutiliser le
  numéro 454.

## Ce qui n'est pas vérifié

- Aucun essai sur iPhone : ni l'import du dossier Azahar du mainteneur, ni un lancement 3DS après l'import.
- L'encodage est vérifié dans le Simulateur iOS : même code Objective-C et même `Flutter.framework` 3.47.2, mais
  tranche Simulateur. Ce n'est pas un essai sur l'iPhone.
- Les effets sur le moniteur de lancement (session Flutter fermée environ 4 s après un lancement libretro) sont
  établis dans les sources, pas observés sur l'appareil.
- Rappels des Builds 451 et 452 :
  - l'import ne peut pas vérifier que l'`otp.bin` fourni est celui de la console qui a chiffré les titres ;
  - un fichier encore dans iCloud Drive est signalé, jamais lu : télécharger d'abord le dossier Azahar sur l'iPhone.
