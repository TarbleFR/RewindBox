# Recette privée 606 — dernière application livrée 605

Cette recette reste fermée tant que `build-utils/rewind606-delivery.json` porte `status: pending`. Un succès de compilation seul, un ancien Core ou une ancienne suite ne peuvent remplacer les producteurs attendus. Le delta RPCS3 concurrent revu ci-dessous est inclus dans la source du produit ; aucun nouveau Core RPCS3 n’est sélectionné.

## Baseline conservée

L’application de référence est la 605 réellement livrée : source `5de451091208c13926ccdb373a0a34f35ec2ee2d`, run `41216465880`, job `124584748706`, IPA de 189643236 octets, SHA-256 `d51a4b138f54f5bbf88ab00a09856e3915a30ab71d9849b8aeaa9a7d8fb35337`. Sa traduction des succès, son interface, ses ressources et ses composants conservés restent la base du produit. La 527 est seulement le donneur historique de ressources natives déjà utilisé dans 605.

La recette 606 dérive directement des 64 étapes de `.github/workflows/achievement-translation-ipa.yml`. Elle conserve la compilation complète de l’application, les planchers iOS 18, NeoPlay, les sept extensions, les sources/notices, le contrôle des sections Mach-O avant/après signature et les quatre morceaux chiffrés de transport. Elle n’exécute pas les anciennes suites Core ou les 103 tests RA historiques.

Le contrôle avant/après signature couvre les 89 images Mach-O, y compris les trois conteneurs à une seule tranche ARM64 omis du reçu 605. Il compare les images exportées dans le ZIP et les 89 cibles effectivement vérifiées par `codesign`. Le signataire et ses vérifications cryptographiques macOS sont conservés; le contrôle local téléchargé ne se présente pas comme une exécution de `codesign` sur Linux.

| Composant | Origine conservée ou nouvelle |
| --- | --- |
| Dolphin avec présentation RA | Producteur `af5b18e67864e6555f54b7b4b6f1452ed82f6982`, run `41209480072`, artefact `13046204173`; mêmes octets que 605 |
| RPCS3 | Core validé `a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a`, ABI 30 / 88 exports, source compilée et preuves historiques inchangées |
| MeloNX | Nouveau Core et simulateur issus du nouveau producteur exact; 4 fixtures affectées liées aux postimages finales, 2 sessions NativeAOT, libération des deux réservations et diagnostic final distinct pour chaque session |
| Hôte | Nouvel artefact `Hogwarts606-host-<source>`; logs des commandes et reçus Apple relus, sans relancer les tests dans la livraison |
| Autres composants | Pins 605 ARMSX2/libretro/StikJIT conservés |

Le wrapper RPCS3 garde les fonctions d’authentification historique. Ses trois exceptions de compatibilité source concernent les préimages/postimages revues de `Rpcs3Diagnostics.mm`, `Rpcs3EarlyLoaderDiagnostics.h` et `Rpcs3InternalBridgePlugin.mm`. Les treize frontières Core/hôte, le Store NeoSwap, l’ABI, les symboles et le binaire restent strictement contrôlés.

Le changement concurrent de `Rpcs3InternalBridgePlugin.mm` provient de `11ac3a3a9466e41a44ecfcd9f280e1e7dd20db8b` (conservé dans `7aa81cfb0ab749ebfd6c147929ca94751ea3a3ed`). Ses 39 lignes classent les messages de cache de pilote existants et les transmettent au journal avec un plafond partagé de 16 écritures par seconde. Elles ne modifient ni les appels de création/import du cache ni la sélection du Core ou de MoltenVK. La préimage est identique dans le Core a4d0 et dans 605 : `60f7140fd100aab0fab929864a171a027d05cd2d5b3523a51c471792225bce01`; la postimage exacte est `d6326d968f3552c5539d48a0933b41d3e61a3e61c0302972ec370e8df5bd3d16`. Le champ `concurrentHostDelta` et le vérificateur figent ces deux hashes, le commit et cette portée; tout autre changement du plugin est refusé. La source revue doit inclure ce commit concurrent et son delta produit depuis 605.

## Gel après les succès réels

1. Intégrer les changements produit et leurs fixtures, puis geler le contrat `performance-core-contract.json`. Authentifier les preuves Core et host sur leurs sources exactes, y compris les validations séparées décrites ci-dessous lorsque le producteur initial a échoué. Conserver les logs originaux, les métadonnées GitHub et les archives téléchargées.
2. Choisir `reviewedSource`, descendant de la source 605 et ancêtre de la recette finale. `productTrees` contient les objets Git de `lib`, `native`, `packages`, `assets`, `pubspec.yaml` et `pubspec.lock`. `productDelta` contient chaque chemin produit modifié entre 605 et la source revue, avec SHA-256 `before`/`after` (`null` pour une absence). `sourceDelta` contient tous les chemins modifiés entre ces deux commits avec leur SHA-256 à la source revue (`null` si supprimé). `rpcHostRouting` reprend exactement les trois entrées correspondantes de `productDelta`.
3. Remplir les deux objets producteur ci-dessous à partir des métadonnées et des octets réellement authentifiés. Le `source` du producteur peut précéder `reviewedSource` seulement si chacun de ses inputs est strictement identique au checkout final. Ne pas inventer les comptes, les digests ou une réussite anticipée.
4. Ajouter seulement la clé publique `build-utils/delivery-606-recipient.pem`; garder la clé privée hors dépôt. Passer `status` à `verified-producers` uniquement après vérification indépendante des deux succès. Les seules différences autorisées après `reviewedSource` concernent la recette explicitement listée, `AGENTS.md` et la documentation.
5. Lancer le workflow 606 avec le message `[rewind606-delivery]` ou par dispatch. Le job Ubuntu vérifie 605, les producteurs exacts et le host avant de réserver le job macOS. Le job application compile l’hôte, embarque le nouveau Core et valide l’IPA finale signée. L’absence de pins valides arrête le travail avant cette compilation.

### Objet `core`

| Champ | Valeur à prendre |
| --- | --- |
| `source`, `run`, `job`, `attempt` | Commit, run, job et tentative du producteur natif original ; son échec de finaliseur reste explicite en cas de récupération |
| `workflow` | `.github/workflows/melonx-core.yml` |
| `artifact`, `name`, `bytes`, `sha256` | Métadonnées exactes de `MeloNX-engine-<source>` et SHA-256 calculé sur le ZIP complet |
| `resultSha256` | SHA-256 de `core-validation/result.json` uniquement pour un producteur entièrement réussi ; absent du producteur original échoué |
| `contractSha256` | SHA-256 du contrat original compilé, relu au commit producteur |
| `binaries` | Dictionnaire exact du résultat : `ios-arm64` et `iossimulator-arm64`, chacun avec `sha256` et `bytes` |
| `identities` | Dictionnaire exact des SHA-256 des deux `identity.json` |
| `packagedFingerprint` | `rewind596_engine.normalized_payload_fingerprint` sur le vrai `ios-arm64/Ryujinx.Library.dylib` |

La compilation `ae78b4be6aa3fbc2db3537fd0a17c9aad75b2284`, run `41239330287`, a produit ses deux bibliothèques et exécuté ses quatre fixtures et deux sessions NativeAOT. Son finaliseur Python a ensuite rejeté à tort le tableau valide `managed.collections`. Le run reste en échec, sans `core-validation/result.json` ajouté après coup.

Dans ce cas, `core.validation` désigne le producteur réussi distinct `.github/workflows/melonx-performance-finalize.yml`, avec `source`, `run`, `job`, `attempt`, `artifact`, `name`, `bytes`, `sha256`, `resultPath: finalization-validation/result.json` et `resultSha256`. L’archive contient les 412 membres originaux inchangés et exactement six nouveaux reçus de validation. La livraison réauthentifie le ZIP original et ses métadonnées, puis exige les mêmes octets pour chaque membre. Les 26 régressions du validateur doivent reproduire l’erreur initiale et vérifier le vrai rapport sauvegardé ; elles ne réexécutent aucun code natif.

Le contrat compilé original `8ce7bd8dad3cabd739772fd4e099c24a6d45b09e895d984bdbdcb3417dbdfcbf` reste l’autorité pour les sources préparées. Le contrat courant n’en diffère que par les deux hashes de `verify_performance_core.py` et de son test, tels que figés par `finalization-recovery.json`. Les 125 inputs de préparation, les 163 membres adaptés, les 4 nouvelles fixtures et les 32 preuves historiques encore applicables restent inchangés. L’ancien et le nouveau contrat, l’échec initial et la validation distincte figurent séparément dans le reçu livré.

Les identités et les sources adaptées sont conservées telles que produites. L’ancien échec Ada et la validation runtime 510 réussie restent deux événements distincts. Les 40 reçus historiques ne sont pas tous présentés comme preuve actuelle : `retainedDisposition` et `retainedChangedDependencies` délimitent les dépendances encore inchangées. `compiledBindings.reportPath` accepte les listes de clés; une dépendance non adaptée doit venir de `untouchedFixtureMembers` authentifié.

### Objet `host`

| Champ | Valeur à prendre |
| --- | --- |
| `source`, `run`, `job`, `attempt`, `workflow` | Métadonnées exactes du workflow host réussi, normal ou `.github/workflows/hogwarts606-host-recovery.yml` |
| `requiredSteps` | Noms des étapes effectivement obligatoires du job host, tous réussis |
| `artifact`, `name`, `bytes`, `sha256` | Métadonnées exactes de `Hogwarts606-host-<source>` et SHA-256 du ZIP complet |
| `resultPath` | Chemin réel du résultat à l’intérieur du ZIP, sans supposer que le préfixe local `build/hogwarts606-host` est conservé par upload-artifact |
| `resultSha256` | SHA-256 des octets de ce résultat |
| `inputsSHA256` | Dictionnaire `inputs` du résultat; mêmes hashes dans le preflight, le commit testé et le checkout final |

La livraison lit le `preflight.json`, les `*.execution.json`, les sorties `*.stdout`/`*.stderr` et les reçus présents à côté du résultat, puis appelle `hogwarts606_host.result_from_outputs`. Elle exige l’égalité complète avec le résultat signé par l’artefact authentifié. Un simple `result: passed` ne suffit pas. L’analyseur doit avoir couvert les fichiers Dart affectés et les six fichiers de tests prévus; les sorties Flutter doivent être complètes, sans échec ni test ignoré.

Le host initial `41239330429` reste en échec UIKit. La récupération réutilise seulement les cinq commandes réussies : Flutter, analyseur, routage Foundation, parité et journal de performances. Elle exécute actuellement la présentation UIKit et l’intégration des succès conservés. Le ZIP original complet, ses métadonnées et les sorties de ses commandes accompagnent le nouvel artefact. La livraison authentifie également l’origine initiale, lie tous ses inputs au commit `ae78b4be`, reconstitue `preflight.recovery` et exige les mêmes octets pour chaque sortie réutilisée. Le delta d’inputs est fermé aux deux fixtures UIKit corrigées et aux deux tests Python du validateur Core ; aucun changement produit n’est permis entre ces producteurs.

## Vérifications locales de recette

```sh
python3 test/hogwarts606_delivery_contract_test.py
python3 test/hogwarts606_rpcs3_compatibility_test.py
```

Ces tests vérifient des refus concrets : source/run/artefact incorrect, manque de smoke, ZIP ambigu ou dangereux, postimage de fixture préliminaire, binding compilé incorrect, dépendance amont non authentifiée, pins encore pending, élargissement de l’exception RPCS3, récupération qui modifie un membre original, effacement d’un échec initial et commande réutilisée dont les octets ont changé. Les tests de signature rejettent aussi les conteneurs ARM64 mal formés et les changements de code masqués par un inventaire incomplet. Ils ne compilent pas le moteur et ne constituent pas une mesure de FPS.

Les preuves RA 605 restent historiques. Le plugin et ses inputs inchangés sont listés séparément; les consommateurs natifs modifiés passent le contrôle d’intégration actuel et la vérification de l’IPA. Le reçu n’affirme pas que toute l’application actuelle est identique aux inputs de la suite 605. Aucun gain en jeu, aucun modèle Apple Translation téléchargé et aucun essai sur iPhone physique ne sont affirmés avant mesure réelle.
