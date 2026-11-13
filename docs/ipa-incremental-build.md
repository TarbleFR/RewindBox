# Compilation incrémentale dans la recette IPA permanente

Le cache facultatif accélère **la même recette** `standard-delivery.yml`.
Chaque livraison exécute encore `xcodebuild`, les preuves de source et de tests,
l'intégration des Cores courants, le scellement, tous les validateurs de l'IPA
signée et son chiffrement. Un cache absent, invalide ou désactivé laisse une
compilation propre. Un échec Xcode arrête la livraison ; aucun ancien `.app`
n'est utilisé pour contourner cet échec.

## Activation et retour arrière

Le responsable du dépôt doit créer un secret Actions **distinct** nommé
`REWINDBOX_BUILD_CACHE_KEY`, aléatoire et d'au moins 32 octets. Par exemple,
dans une session `gh` déjà autorisée, cette commande transmet une nouvelle clé
sans l'afficher :

```bash
openssl rand -base64 48 | gh secret set REWINDBOX_BUILD_CACHE_KEY --repo TarbleFR/RewindBox
```

Aucune clé n'est créée par la recette ou les tests. Sans ce secret, le cache est
désactivé sans erreur. Le mot de passe ScreenScraper ne sert jamais de clé.
Le secret dédié n'est injecté que dans les trois étapes du helper ; il n'entre
pas dans l'environnement de Xcode, Flutter, de la signature ou des actions de
cache. Seuls les pushs de `TarbleFR/RewindBox`, branche `Claude`, issus du
workflow permanent sont admissibles. Les PR et les autres branches sont exclues.

Pour revenir immédiatement au comportement antérieur, supprimer le secret ou
retirer les étapes facultatives du cache après revue. Une rotation du secret
crée un espace de clés différent ; elle permet aussi d'écarter un ancien cache
invalide, les entrées exactes étant immuables. Ne pas ajouter de restauration
par préfixe ni de chemin de compilation parallèle.

## Identité exacte et seules exclusions

La clé opaque est un HMAC sur les entrées effectives après génération de l'hôte :
Dart et packages, assets, sources et en-têtes iOS, projets et configurations,
Pods et dépendances externes Dart résolues, frameworks liés, dépendances natives,
StikJIT et options de compilation. Les chemins absolus sont inclus : un runner
utilisant un autre checkout provoque un manque de cache plutôt qu'une réutilisation
ambiguë. Les sorties déjà copiées dans l'hôte représentent les générateurs ;
les pins et contrats des producteurs de Cores ne sont pas des entrées du compilateur
hôte et ne sont pas inclus globalement.

L'identité comprend les révisions complètes Flutter et engine, les versions
Xcode, SDK et SDK build, Swift, Clang, Ruby, CocoaPods et macOS, les paramètres
pertinents de l'environnement et la commande Xcode. Les defines sont pris en
compte sans être imprimés. Le helper lui-même fait partie des entrées.

Deux fichiers précisément identifiés sont exclus car ils sont intégrés après
la compilation et chargés dynamiquement :

- `packages/rpcs3_internal_bridge/ios/Frameworks/libRPCS3Core.dylib` ;
- `packages/melonx_internal_bridge/ios/Frameworks/MeloNXCore.framework/MeloNXCore`.

Leurs bridges, ABI, en-têtes, nouveaux fichiers de framework et dépendances liées
restent inclus. Le helper refuse le cache si les podspecs deviennent des déclarations
`vendored_libraries/frameworks` ou si les projets/ scripts Pods générés référencent
ces deux Cores. Leurs preuves et remplacements courants continuent après Xcode.

Seul le numéro numérique de livraison est normalisé dans `pubspec.yaml`, les
variables Flutter connues et les plists de Runner/extensions connues ou du Core
MeloNX lorsqu'il correspond au build courant. La version sémantique et les versions
des frameworks tiers restent significatives. Les seuls horodatages ignorés sont
`date_created` de Flutter et `generated` de `package_config.json`, lorsqu'ils ont
le format attendu. Les autres métadonnées, dépendances et versions restent incluses.
Le seul `CURRENT_PROJECT_VERSION` normalisé est la valeur numérique courante
dans `ios/Runner.xcodeproj/project.pbxproj`, que les générateurs des helpers
écrivent à chaque livraison. Les autres projets et valeurs restent significatifs.

## Confidentialité, authenticité et publication

Le snapshot est pris immédiatement après une compilation Xcode réussie, avant
la première intégration de métadonnées ou de runtime. Il contient seulement
DerivedData et un manifeste d'identité/horodatages. Les liens internes sont
matérialisés ; un lien sortant ou cyclique refuse le snapshot. Les archives
restaurées n'acceptent que des fichiers réguliers et des répertoires, avec limites
de taille et de nombre, sans traversée de chemin, symlink, hardlink ou fichier spécial.

Le contenu est chiffré par AES-256-CBC avec IV aléatoire et clés séparées par HKDF
pour le chiffrement et le HMAC-SHA256. Le HMAC authentifie l'en-tête, l'identité,
la provenance du producteur et tout le ciphertext avant tout déchiffrement.
L'archive est entièrement vérifiée dans un dossier temporaire avant remplacement
de DerivedData. Les mtime des entrées ne sont rétablis que si leurs **octets réels**
sont encore identiques. Un plist ou une source de version modifié garde son
horodatage courant pour que Xcode traite la nouvelle version.

L'action de cache ne reçoit que `.ci-host-cache/state.enc`, avec une clé exacte,
sans `restore-keys`. Ni `.app`, ni DerivedData, ni archive en clair ne sont envoyés.
La sauvegarde explicite n'est autorisée qu'après tous les validateurs finaux de
l'IPA signée. Le snapshot reste celui d'avant l'intégration des Cores, même si les
étapes suivantes ont modifié l'application. Une erreur du service de cache est
facultative ; elle n'affaiblit aucune étape de livraison. La conservation dépend
du service de cache et n'est pas permanente.

## Vérification et limites de mesure

`test/ipa_build_cache_test.py` vérifie hors ligne le chiffrement réel OpenSSL,
l'altération du ciphertext/en-tête/tag, une mauvaise clé, des entrées différentes,
les archives interdites, les limites, le repli propre, les restrictions de provenance,
la conservation des timestamps des versions actuelles et le remplacement des seuls
Cores exclus. Un contrôle de référence vérifie que les étapes de compilation,
preuve, signature, chiffrement et validation de la recette antérieure restent
identiques après retrait des étapes facultatives du cache.

Aucun gain macOS n'est encore mesuré. L'activation initiale, notamment la prochaine
733 si elle ne dispose pas encore d'une entrée compatible, compile intégralement.
Les sources hôte modifiées changent la clé et entraînent également une compilation
propre. Une mise à jour des seuls Cores RPCS3/MeloNX ou un nouveau numéro peut
réutiliser les intermédiaires compatibles ; Xcode s'exécute toujours et produit
l'identité de la livraison courante. Flutter AOT peut encore recompiler : son
cache de sorties `.dart_tool/flutter_build` n'est pas transporté ici.

`build/delivery/host-cache.json` indique le statut et la durée de chaque phase.
Les mesures Xcode/AOT et la durée totale de livraison existantes restent la référence.
Comparer au moins un premier manque de cache puis une livraison compatible avant
de revendiquer un gain. Toute régression constatée conduit à désactiver ou corriger
l'optimisation, avec revue et vérifications, dans cette unique recette.

## Intégration avant le prochain gel de 733

Le commit de cette optimisation doit être explicitement déclaré **revu** dans
le prochain manifeste, avant le gel de 733. Le classement actuel de la recette
considère les nouveaux helper et test Python comme des fichiers produit :
`materialize` doit donc les conserver dans l'arbre effectif. Sans cette déclaration,
la restauration de la base gelée peut les supprimer. Il ne faut pas élargir le
classement des fichiers de recette pour contourner cette étape d'intégration.
Le gel, la revue, l'identité des Cores et la demande de compilation restent sous
la responsabilité du pilote de la livraison.

## Vérifications exécutées le 13 novembre 2026

- `python test/ipa_build_cache_test.py` : **9 tests réussis**, avec OpenSSL réel.
  Les cas d'archive malveillante partent d'un manifeste et d'un payload valides,
  puis ajoutent un seul membre interdit ; le motif précis du refus est vérifié.
- Deux mutations ont été exécutées séparément : neutraliser le garde de chemin
  fait échouer le test ; neutraliser le garde de type d'archive produit une erreur
  du test. **Les deux mutants sont détectés.**
- `python test/standard_delivery_contract_test.py Workflow` : **15 tests réussis**.
- `py_compile` du helper et du test, et `git diff --check` : réussis.

Le pilote standard complet a été lancé mais **n'est pas déclaré réussi** : cinq
cas avaient réussi et le contrôle du pin MeloNX avait signalé
`ValueError: Wrong DMA-copy Core pin`. La même erreur est reproduite par le seul
cas `Components.test_melonx_pin_is_verified_and_bound_to_its_contract` dans un
checkout intact de `32d71b22695e4895e1d9cca6b6ffc81159a41bd7`. Elle préexiste
à cette optimisation, dans l'attente de la mise à jour du pin/contrat Core745.
Le pilote complet a ensuite été interrompu sans progression sur
`Components.test_retained_inputs_unchanged_since_the_base` ; aucun contrôle n'a
été affaibli pour obtenir un résultat vert. Les contrôles ciblés de workflow,
crypto, identité, archives et repli décrits ci-dessus ont été exécutés séparément.
Aucune compilation Apple ni mesure de gain CI n'a été réalisée pour cette revue.
