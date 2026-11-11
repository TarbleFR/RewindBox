# Recette de livraison standard : la même recette à chaque build

Règle du maintainer, 1er novembre 2026 : « améliore la recette pour la prochaine compilation et
enregistre qu'il faut la même recette à chaque fois, qui ne rajoute que ce qui a été modifié ».
La règle est inscrite dans [AGENTS.md](../AGENTS.md) (« Same recipe for every build »).

## 1. La règle

Chaque IPA privée est produite par **la même recette**, à partir de la dernière IPA livrée et
vérifiée. Elle n'ajoute que ce qui a changé depuis cette base.

- **Composants** (Cores RPCS3, MeloNX, Dolphin et ARMSX2, cœurs libretro, dépendances natives) :
  - un composant dont les entrées ont changé est recompilé par sa propre route productrice, puis
    remplacé ;
  - les autres sont conservés avec leur identité authentifiée : run, job, empreinte d'artefact,
    empreinte de charge utile.
- **Sources produit** : seul le delta revu depuis la base entre dans la build ; le travail concurrent
  est déclaré « source seulement » et n'est jamais compilé en silence.
- **Tests** : un groupe n'est rejoué que si l'une de ses entrées a changé ; sinon sa preuve épinglée
  est authentifiée et réutilisée, avec le libellé « réutilisée ». Le contrat de livraison est
  toujours rejoué.
- **Recette** : plus de copie par build (`rewindNNN_*.py`, `rewindNNN-*.yml`) ; les changements de la
  build sont déclarés dans son manifeste.
- **Échec** : une livraison échouée est relancée en ne modifiant que la recette, et ses jobs de test
  réussis sont réutilisés.
- **Enchaînement Core puis IPA** (ajout du 10 novembre 2026, demande du mainteneur : livrer plus vite sans
  retirer de contrôle ; durées mesurées sur les Cores 921 à 923 et l'IPA 723) :
  - **un seul Core par livraison** : les corrections prêtes avant une livraison sont regroupées dans le même
    Core ; un Core intermédiaire compilé n'est ni épinglé ni livré (le 922, remplacé par le 923) ;
  - **la demande de compilation part dès que les contrôles ciblés passent** (clôture des sources, tests
    nouveaux ou modifiés, audit des identités de code généré, chaîne de repli, route, gardes : environ
    1 min) ; le pilote historique complet (environ 23 min) tourne en parallèle, en local et dans le job
    Apple du run ; un pilote rouge interdit l'épinglage, il ne retarde plus la demande ;
  - **l'IPA n'est demandée qu'une fois tous ses Cores épinglés** ; pendant leur compilation, la clé de
    destinataire, la spécification et le brouillon sont préparés, jamais déclenchés ;
  - **une seule compilation à la fois** par route ; une demande n'est pas doublée pour « rattraper » une
    file d'attente de runners ;
  - **ce qui reste incompressible** : compilation du Core (19 min) et tests hôte Apple (28 min) en
    parallèle, livraison (environ 25 min), files d'attente macOS. Piste non appliquée : exécuter en
    parallèle, dans le pilote, les tests d'incréments indépendants (hors tests sensibles au temps) ; à
    mesurer sur un Core avant d'en faire la règle.

## 2. Ce qui est en place (première cible : 611)

| Élément | Fichier |
| --- | --- |
| Workflow unique, sans constante de build | `.github/workflows/standard-delivery.yml` |
| Script unique d'opérations (fusion des 610 `rewind610_delivery`, `_baseline`, `_checks`) | `.github/diagnostics/standard_delivery.py` |
| Core RPCS3 remplacé (constantes dans le pin) | `.github/diagnostics/rpcs3_core_component.py`, `build-utils/rpcs3/core-pin.json` |
| Core MeloNX remplacé | `.github/diagnostics/melonx_reads_core_component.py`, `build-utils/melonx/reads-core-pin.json` |
| Composants conservés (Dolphin/ARMSX2 608, archives libretro et dépendances MeloNX) et republication | `.github/diagnostics/retained_components.py` |
| Manifeste de build (brouillon, puis gelé localement) | `build-utils/delivery/<N>.json` |
| Contrat hors ligne (Linux) | `test/standard_delivery_contract_test.py` |
| Vérification du fichier téléchargé | `build-utils/verify_downloaded_delivery.py` |

- **Manifeste** : base (reçus 610 liés par empreinte, 16 fichiers de preuve, 90 images), composants
  (remplacer, conserver, archive conservée, source épinglée, release épinglée), produit (commits revus
  et « source seulement »), images (doivent changer, remplacées = empreinte du pin, conservées =
  empreinte de la base, autres écarts signalés), tests (frais ou réutilisés, commandes figées),
  destinataire, archives à republier.
- **Arbre effectif** : le gel rejoue `base..HEAD` depuis l'arbre que la base a réellement compilé et
  n'applique que les chemins produit des commits revus. Pour une base livrée par cette recette, c'est
  son arbre source auquel on applique les restaurations de son manifeste gelé (lu au commit source de
  la base). Il est reconstruit depuis les objets git et lié à son `effectiveDigest`. Pour une base
  livrée par une recette antérieure (610), c'est son arbre source. Ainsi, un travail que la base avait
  différé reste différé (hérité) tant qu'une build ne le classe pas. Le manifeste gelé enregistre
  `baseEffectiveDigest` et `inheritedDeferredPaths` ; en CI, les chemins de la base sont recalculés
  de la même façon. Un commit revu doit partir des octets déjà présents dans l'arbre
  effectif (sinon refus) ; un commit « source seulement » est différé ; un commit non classé qui
  touche le produit est refusé. Le manifeste enregistre les écarts avec la base, la liste à restaurer
  par rapport au HEAD gelé et `effectiveDigest`. En CI, l'opération `materialize` est la première
  étape après le checkout de chaque job : elle vérifie que les commits postérieurs au gel ne touchent
  que des chemins de recette, restaure les chemins (modes, liens, suppressions) depuis les objets git
  et recalcule l'empreinte depuis les fichiers. Aucun checkout ultérieur.
- **Travail différé promu** (614) : `product.promotedCommits` liste, dans l'ordre de l'historique, des
  commits antérieurs à la base dont la livraison de base avait différé les chemins produit (ils figurent
  dans ses enregistrements de restauration). Le gel les applique à l'arbre effectif de la base avant de
  rejouer `base..HEAD`, avec la règle d'un commit revu (chaque changement part des octets déjà dans
  l'arbre effectif) ; `paths` limite un commit à certains de ses chemins, les autres restent différés.
  Exemple 614 : les 13 fichiers de traduction de `b06888a9` (sur lesquels `35afb4c9` a été écrit), puis
  `35afb4c9`, `d7f069b8` et les commits MeloNX que 613 avait différés.
- **Vérificateur MeloNX nommé par le manifeste** (614) : `components.melonx.verifier` choisit, dans une
  liste fermée, `melonx_reads_core_component.py` ou `melonx_arrays_core_component.py`, dont le pin
  doit être celui du manifeste.
- **Composant épinglé inchangé** : une build qui garde le Core RPCS3 ou MeloNX de sa base déclare
  `components.<rpcs3|melonx>.unchangedFromBase: true` avec le même pin que la base. Le Core est
  réinstallé depuis son pin. Son image est déclarée sous `images.retained.<clé>` et non sous
  `images.replaced`. Le gel exige que l'empreinte du pin soit celle de l'image de la base et que le
  fichier pin soit celui du manifeste de base ; `expected()` exige l'égalité au lieu de la différence.
- **Entrées conservées modifiées et déclarées** : un composant conservé (`retain`, `retain-archive`,
  `pinned-source` avec `inputs`) peut déclarer `changedInputs: [{path, baseBlob, newBlob, commit}]`
  pour un fichier de ses entrées qu'un commit revu de la ligne first-parent a changé sans toucher au
  Core compilé (ex. le conditionnel d'identité de `verify_ipa.py` de Dolphin). Le gel et le contrat
  source acceptent exactement les octets `newBlob` de ce chemin. Restent refusés : tout autre
  changement d'octets, un changement non déclaré, un `baseBlob` qui n'est pas celui de la base, une
  entrée dont le fichier n'a pas changé, un chemin hors des entrées du composant, un commit absent de
  `product.reviewedCommits`, hors de la ligne first-parent ou dont l'arbre ne contient pas `newBlob`.
  Sans le champ, la règle est inchangée octet pour octet.
- **Chemins de recette** (jamais compilés) : `.github/**`, `docs/**`, `*.md` à la racine,
  `.claude/**`, `build-utils/delivery/**`, `build-utils/delivery-*-recipient.pem`, les deux pins de
  Core, le contrat et le vérificateur. Exception liée par le gel : les fichiers de ce type que l'IPA
  embarque (notices légales, déclarations de sources, `LICENSE.md`, `NOTICE.md`).
- **Parallélisme** : le job application ne dépend que du preflight ; il compile tout de suite et,
  juste avant d'embarquer l'identité de test, l'opération `await-tests` attend les jobs `flutter` et
  `native` du même run, authentifie leurs étapes requises, leur artefact (empreinte API et ligne
  d'upload du journal du job) et leurs reçus. Le contrat rejoué par le preflight est authentifié par
  l'empreinte de son journal. L'IPA n'est scellée et chiffrée qu'ensuite.
- **Réutilisation** : même `effectiveDigest`, mêmes commandes, et mêmes octets pour chaque fichier de
  recette que les commandes lisent réellement (scripts, modules importés, chemins cités) ; les deux
  manifestes sont lus depuis les commits.
- **Republication** : après la livraison chiffrée, les archives de composants authentifiées sont
  republiées une par une (rétention 90 jours) avec `republication.json` qui les lie au producteur
  d'origine ; une build suivante les accepte comme origine si l'enregistrement et l'empreinte du
  contenu sont ceux de l'original.
- **Contrôles conservés de la 610** : base authentifiée, contrat source, composants, installation et
  ABI du Core RPCS3, Dolphin/ARMSX2, libretro, MeloNX, signature, inventaire des images, validateurs,
  chiffrement, 4 pièces, rétention 14 jours ; ajoutés : KartPad/Dusklight en CI, dépendances Pods de
  `rpcs3_internal_bridge`, `DELIVERY_RECIPIENT` obligatoire (sinon repli silencieux sur la clé 422).

## 3. Mode d'emploi

1. **Brouillon** : `build-utils/delivery/<N>.json` (`status: draft`) déclare base, composants,
   commits revus et « source seulement », images, tests et destinataire.
2. **Contrôle** : `python3 -B test/standard_delivery_contract_test.py`, puis
   `python3 -B .github/diagnostics/standard_delivery.py contract <N>` (ajoute les contrôles API ;
   `--offline` pour s'en passer).
3. **Gel** (local, checkout `Claude` propre et à jour) :
   `python3 -B .github/diagnostics/standard_delivery.py freeze <N> --dry-run` liste ce qui bloque,
   la restauration et `effectiveDigest` ; sans `--dry-run`, le manifeste gelé est écrit. Le gel refuse
   un pin en attente, un commit non classé et un arbre effectif que le contrôle légal de
   l'application (`embed_legal_bundle.py --validate-only`) refuse.
4. **Commit déclencheur** : vérifier ses chemins avec
   `python3 -B .github/diagnostics/standard_delivery.py trigger-paths <N> build-utils/delivery/<N>.json`
   (refuse tout chemin produit et tout autre workflow qui lancerait un job), puis committer le
   manifeste gelé avec le sujet `[ipa-delivery:<N>] …` (la balise ouvre le sujet) (pas de `[skip ci]`). Un sujet sans balise ne
   lance rien.
5. **Après le run** : télécharger les 4 pièces et les métadonnées API, lancer
   `build-utils/verify_downloaded_delivery.py` (clé privée hors Git). **Avant de supprimer la clé**, copier
   depuis le dossier déchiffré vers `docs/evidence/rewind<N>/` les huit reçus `signed-payload-identity.json`,
   `signature.json`, `standard-embedded.json`, `standard-ipa-validation.json`, `standard-tests.json`,
   `version-validation.json`, `environment.json` et `observed-timings.json`. Puis
   `standard_delivery.py record <N> --run <ID> --verification … --api …` écrit
   `docs/evidence/rewind<N>/delivery.json` au schéma 610 ; depuis la 719 il refuse d'écrire un reçu sans
   l'inventaire signé des images (règle § 3.8). Supprimer la clé privée.
6. **Relance** : ne changer que la recette ; pour réutiliser un groupe, passer `tests.<groupe>.mode`
   à `reuse` avec ses épingles (source, run, job, artefact, empreinte) et regeler.
7. **Commandes des groupes** (depuis la 718) : une commande n'est exécutée qu'une fois par groupe
   (`expand_commands` refuse un argv identique, de base ou ajouté) ; ne pas ajouter au groupe natif
   une commande que le groupe Flutter exécute déjà, sauf pour une vraie différence de plate-forme ou de
   chaîne d'outils ; une commande native fraîche n'importe pas PIL (le job natif ne fournit pas Pillow,
   garde du contrat). Le job natif démarre une fois le simulateur des XCTests avant l'installation de
   Flutter et l'attend juste avant le groupe (mesures : `docs/delivery-speed.md` § 5).

8. **Un reçu sans inventaire signé n'est pas une base** (718). `verify_base` authentifie la base par son
   `signed-payload-identity.json` (90 images, lié à l'IPA par son empreinte). Ce fichier n'existe que dans la
   livraison chiffrée ; une fois la clé du destinataire supprimée, il n'est plus récupérable. Le reçu de la 718
   n'en a pas (quatre fichiers de preuve) : la build suivante repart de la 694, dernière base complète, et rejoue
   les commits de la 718 avec la même classification.
9. **Ligne de livraison après une synchronisation de `main`.** Le gel et le contrat rejouent `base..HEAD` sur la
   ligne « premier parent » de `Claude`. Une fusion « Claude dans main » dont le premier parent est `main`, suivie
   de l'avancement de `Claude` sur cette fusion, fait passer cette ligne par l'historique de `main` : la base n'y
   est plus et un brouillon échoue sur « The base is not on the first-parent line of HEAD ». Remède sans réécriture
   ni push forcé : un commit de fusion dont l'arbre est celui de la tête, le premier parent la tête de `Claude`
   d'avant la synchronisation et le second parent la tête actuelle
   (`git commit-tree <arbre> -p <tête d'avant> -p HEAD`, puis avance rapide). Il est classé comme un seul
   changement revu, avec dans sa note la liste de ce qu'il apporte (719 : `d506a8ed`).
10. **Une image changée sans être déclarée s'explique avant l'enregistrement** (719). Le rapport de vérification
   liste sous `undeclaredImageChanges` les images ni retenues ni remplacées ni « doit changer » dont la charge
   diffère de la base. Ce n'est pas un échec : une extension Flutter est reliée à chaque build. Avant d'écrire le
   reçu, comparer l'image à celle de la build précédente section par section : une différence dans le code compilé
   ou les données se classe (commit revu, image déclarée) ; une différence limitée à ce que l'éditeur de liens
   fabrique se note dans l'état de la build.
11. **Le Swift d'un pont n'est compilé en entier que par le job application** (720). Les runs des Cores exécutent
   leurs gates, le run simulateur des skins compile les tests Objective-C des ponts et le groupe natif ne compile
   que des extraits ou des fichiers isolés (arbitrage des sticks, parité autonome) ; aucun ne compile les fichiers
   Swift d'un pont contre l'interface que Swift tire de ses en-têtes Objective-C. Une remise qui ajoute ou modifie
   un appel Swift vers un sélecteur Objective-C (Swift renomme `+syncNowAndWhenUncovered:stillWanted:sync:` en
   `syncNowAnd(whenUncovered:stillWanted:sync:)`) arrive avec la preuve d'une compilation du pont sur macOS ;
   sinon c'est la première demande de livraison qui la compile, et un échec y coûte un correctif revu, un regel
   et les deux groupes de tests (§ 21).

## 4. État de la 611 (1er novembre 2026)

Le manifeste `build-utils/delivery/611.json` est un **brouillon**. `freeze 611 --dry-run` sur
`feaaeea3` + la recette : aucun conflit, aucun commit non classé ; 83 chemins produit de `b06888a9`
(612) restaurés (52 supprimés, dont libchdr ; 31 remis aux octets revus, dont `lib/l10n/app_locale*`
et `Rpcs3Achievements.mm` de `6f4244a0`) ; empreinte effective `334b9bb3…`, 6651 fichiers produit.
Bloquants :
- pin du Core RPCS3 611 en attente (aucun run producteur) ; les commits de la route Core 611 (pli
  du patch RetroAchievements, gate) devront être ajoutés aux commits revus avant le gel ;
- `packages/rpcs3_internal_bridge/ios/rpcs3_internal_bridge.podspec`, modifié par `57eb301e`
  (rcheevos vendu, nouvelles dépendances), n'est couvert par aucune revue de déclarations de sources
  (`collect_build_source_evidence.py`) : il faut un commit produit revu avant le gel ;
- archives conservées qui expirent : libretro le 3 novembre 2026 à 16:19Z, dépendances MeloNX le
  5 novembre ; Dolphin/ARMSX2 et le Core MeloNX le 15 novembre.

## 5. État de la 612 (2 novembre 2026)

Première build sur une base livrée par la recette standard (611). Deux extensions ont été nécessaires
(section 2 : « Arbre effectif » et « Composant épinglé inchangé »), ainsi qu'une correction :
`verify_base()` accepte le reçu d'une base standard, qui liste aussi ses jobs republish et de tests
(ignorés quand leurs preuves ont été réutilisées).

Gel de la 612 sur `83c0d6aa` :
- base effective 611 `62414e99…` ;
- 83 chemins différés hérités (`b06888a9`), 16 différences produit ;
- empreinte effective `a88d478b…`, 6656 fichiers produit ;
- composants :
  - Core RPCS3 612 remplacé (pin vérifié, run 41384244220) ;
  - Core MeloNX de la 611 conservé (`unchangedFromBase`) ;
  - Dolphin/ARMSX2, libretro et dépendances MeloNX conservés par la republication de la 611
    (run 41380039319) ;
- tests frais dans les deux groupes ;
- contrôle légal réussi.

## 6. État de la 613 (2 novembre 2026)

Livrée sur la 612 par la même recette, sans extension.
- Gel sur `55dd975d` : base effective 612 `a88d478b…`, empreinte effective `fd90ad9d…`.
- Un premier gel (`a3a95e2f`) a été refait : un commit produit d'une autre session (`d7f069b8`) est
  arrivé sur la branche avant le déclencheur ; il est classé « source seulement » comme `e424bc9f`,
  `05ab4b1b`, `a5a64217` et `35afb4c9` (cible 614).
- Composants : Core RPCS3 613 remplacé ; ses harnais Apple viennent d'un second run
  (`41438526095`, `[rpcs3-core-build-apple]`) sur le même delta canonique, accepté par
  `same_core_sources`. MeloNX de la 611 conservé ; Dolphin/ARMSX2, libretro et dépendances MeloNX
  conservés par la republication de la 612 (run 41386771013).
- Run de livraison 41440020469 réussi en ~19 min ; IPA vérifiée hors ligne (90 images, 4 changées
  et déclarées, Core embarqué à l'empreinte du pin) ; reçu `docs/evidence/rewind613/delivery.json`.
- Hors CI, les métadonnées API et les archives ont été lues par le serveur GitHub MCP et les URL
  signées des artefacts (octets égaux aux digests de l'API) ; la CI les authentifie elle-même.


## 6. État de la 614 (2 novembre 2026)

Livrée sur la 613 (run `41446700372`, IPA `fbfab991…`). Deux extensions (section 2) : le vérificateur
MeloNX nommé par le manifeste (Core arrays) et le travail différé promu (`promotedCommits`). Gel sur
`6c377f97` : base effective 613 `fd90ad9d…`, 6 commits promus (dont 13 fichiers seulement de
`b06888a9`), 5 revus, 50 différences produit, 70 chemins différés hérités, empreinte effective
`90495b43…`, 6673 fichiers produit ; tests frais dans les deux groupes ; contrôle légal réussi.
L'image `rpcs3_internal_bridge` a changé sans changement de ses sources (signalée, non bloquante).

## 7. État de la 615 (2 novembre 2026)

Livrée sur la 614 (run `41464449025`, IPA `9afe1120…`, 194138031 octets), sans extension de la
recette. Gel sur `062b96ef` : base effective 614 `90495b43…`, 2 commits revus (`fe37a2da` RewindBox
Glacier, `f9408633` correctif RetroAchievements), 180 différences produit, 70 chemins différés
hérités, empreinte effective `b2d6eb0e…`, 6822 fichiers produit ; contrôle légal réussi.
- `38c07fd2` modifiait aussi `lib/services/retro_achievements_session_service.dart`, dont les octets
  livrés (614) excluent encore `b06888a9` : le gel l'a refusé comme commit revu (conflit). Il a été
  annulé (`1440c666`), les deux classés « source seulement » (effet produit nul), puis réappliqué sans
  ce fichier (`f9408633`), sans réécrire l'historique.
- La déclaration de sources Glacier (`docs/evidence/rewindbox-glacier-declarations-2026-11-02.json`)
  rejoint `EMBEDDED_RECIPE_FILES`.
- Composants : Cores RPCS3 (613) et MeloNX arrays (614) `unchangedFromBase` ; Dolphin/ARMSX2,
  libretro et dépendances MeloNX conservés par la republication de la 614. Images changées : App,
  `retro_achievements_session`, Runner, et `rpcs3_internal_bridge` sans changement de ses sources
  (signalé, non bloquant, comme en 614). Tests frais dans les deux groupes (~22 min de bout en bout).
- Hors CI : métadonnées API lues par l'API REST publique, pièces téléchargées par les URL signées du
  serveur GitHub MCP (octets égaux aux digests de l'API) ; IPA vérifiée hors ligne, clé privée
  supprimée.

## 8. État de la 617 (2 novembre 2026)

Livrée sur la 616 (run `41481225616`, IPA `777c2cc1…`, 194191724 octets). Une extension de la
recette : le vérificateur MeloNX `melonx_dma_core_component.py` (Core DMA Hogwarts, pin
`dma-core-pin.json`) rejoint `MELONX_VERIFIERS`, et son pin `RECIPE_FILES` ; le Core arrays 614 qu'il
remplace est authentifié par son archive, son contrat et son pin. Gel sur `4575db36` : base effective
616 `f30fee4c…`, 7 commits promus (que la 616 avait classés « source seulement » pour la 617 : route
MeloNX DMA `58fa9f35`…`88c4cb85`, scraper `6e636e9d`, Glacier `97d8a38f`), 1 commit revu (`dd8ab919`,
plan de nettoyage Actions du mainteneur, un chemin produit hors application), 40 différences produit,
70 chemins différés hérités, empreinte effective `f27e6e4b…`, 6835 fichiers produit ; contrôle légal
réussi.
- La première 616 (run `41472161135`) s'était arrêtée sur le Core arrays conservé : la route
  `melonx-core.yml`, chemin de recette lu au checkout, pointait déjà vers le Core DMA. Correctif de la
  session RPCS3 (`a293cfdd`) : une fois la route déplacée, ce seul workflow est lu au commit producteur.
  Leçon : pousser une route Core qui remplace celle d'un Core conservé change la preuve d'une livraison
  concurrente ; prévenir les autres sessions avant.
- `api/artifacts.json` de la 616 ne garde que les pièces de l'IPA : les archives republiées
  (composants conservés) se lisent dans la liste complète des artefacts du run (API publique).
- Composants : MeloNX remplacé (Core DMA, `ace2ef6b…`), RPCS3 Core 616 `unchangedFromBase` ;
  Dolphin/ARMSX2, libretro et dépendances MeloNX conservés par la republication de la 616. Images
  changées : App, MeloNXCore, Runner, et `armsx2_internal_bridge` sans changement de ses sources
  (signalé, non bloquant). Tests frais dans les deux groupes (~28 min de bout en bout).
- Hors CI : métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub MCP
  (octets égaux aux digests de l'API) ; IPA vérifiée hors ligne, clé privée supprimée.

## 9. État de la 618 (2 novembre 2026)

Livrée sur la 617 (run `41504526945`, IPA `47351d9a…`, 194193557 octets), sans extension de la
recette. Gel sur `0fd3ab04` : base effective 617 `f27e6e4b…`, 4 commits revus (mise à jour de région
DMA pour Hogwarts `750a4077`, son correctif de revue `1e7dc4f2`, deux regels du contrat du Core
`27fd5064`, `9ce5822c`), 4 différences produit, 70 chemins différés hérités, empreinte effective
`95f1ecc9…`, 6835 fichiers produit ; contrôle légal réussi.
- Le Core MeloNX remplacé est un regel de la route DMA (même vérificateur, même base de route : le Core
  arrays 614) : la référence épinglée `dma-core-pin.json` change, et `components.melonx.replaces` nomme
  le Core DMA de la 617. Entre le regel du contrat et la nouvelle référence, le contrôle de la référence
  MeloNX de `standard_delivery_contract_test.py` a échoué (transitoire, annoncé aux autres sessions).
- Composants : MeloNX remplacé (`dfe3bb56…`), RPCS3 Core 616 `unchangedFromBase` ; Dolphin/ARMSX2,
  libretro et dépendances MeloNX conservés par la republication de la 617. Images changées : MeloNXCore,
  Runner, et `armsx2_internal_bridge`, `melonx_internal_bridge` sans changement de leurs sources
  (signalé, non bloquant). Tests frais dans les deux groupes (~24 min de bout en bout).
- Hors CI : métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub MCP
  (octets égaux aux digests de l'API) ; IPA vérifiée hors ligne, clé privée supprimée.

## 10. État de la 619 (2 novembre 2026)

Livrée sur la 618 (run `41516165812`, IPA `2e570645…`, 194221111 octets), sans extension de la
recette. Gel sur `45943c9b` : base effective 618 `95f1ecc9…`, 4 commits revus (delta du Core RPCS3 619
`602f4512`, sa révision après revue `43f16353`, deux correctifs de minutage des tests hôtes `c5c265dc`,
`5ecf779e`), 9 différences produit (enregistrements du delta et tests hôtes), 70 chemins différés
hérités, empreinte effective `4fbdfe3e…`, 6840 fichiers produit ; contrôle légal réussi.
- Le Core RPCS3 619 vient de deux runs de la route Core : la compilation (run `41509883194`, job Core
  réussi) et les harnais Apple relancés seuls (`[rpcs3-core-build-apple]`, run `41514477410`) après deux
  correctifs de minutage d'un scénario de test, comme pour le Core 613. Entre le push des sources 619 et
  l'épingle, `test_rpcs3_pin` échouait (transitoire, annoncé).
- Composants : RPCS3 remplacé (Core 619, `44fc928e…`, remplace le Core 616), MeloNX `unchangedFromBase`
  (Core de la 618, image conservée) ; Dolphin/ARMSX2, libretro et dépendances MeloNX conservés par la
  republication de la 618. Images changées : libRPCS3Core, Runner, et `armsx2_internal_bridge`,
  `dolphin_internal_bridge`, `melonx_internal_bridge` sans changement de leurs sources (signalé, non
  bloquant). Tests frais dans les deux groupes (~25 min de bout en bout).
- Hors CI : métadonnées API par le serveur GitHub MCP, pièces par ses URL signées (octets égaux aux
  digests de l'API) ; IPA vérifiée hors ligne, clé privée supprimée.

## 11. État de la 620 (2 novembre 2026)

Livrée sur la 619 (run `41527072487`, IPA `8cf47853…`, 194238627 octets), sans extension de la
recette. Gel sur `4eedd6fc` : base effective 619 `4fbdfe3e…`, 9 commits revus (copie GPU des sources
DMA linéaires pour Hogwarts `6d6e7eac` et sa révision après revue `f2478545`, deux regels du contrat du
Core `cd019876`, `1c836557`, intervalles de présentation du journal `490b19f5` et le correctif de son test
hôte `56bb0478`, `tools/melonx/frame_report.py` `3facc1fe`, correctif de connexion RA `c00bdca6`,
correctif PS3 « non reconnu » `8a3dd9cf`), `b06888a9` promu pour le seul `Rpcs3Achievements.mm`,
69 chemins différés hérités, empreinte effective `bf6ee0b0…`, 6842 fichiers produit ; contrôle légal
réussi.
- Premier déclencheur (run `41523517233`) : échec du job natif sur un seuil de CPU du test hôte du
  journal (fil occupé à 39 % d'un échantillon de 0,25 s pour un plancher de 40 %, charge du runner). Le
  seuil devient « le fil le plus occupé listé, au moins 10 % » (`56bb0478`), commit revu, regel, nouveau
  déclencheur. Le changement touche l'arbre effectif : les deux groupes de tests sont rejoués frais.
- Le brouillon doit déclarer dans `images.mustChange` les images dérivées des chemins revus (App,
  ponts MeloNX/RA/RPCS3, Runner) : `test_images` refuse sinon le brouillon avant le gel.
- Composants : MeloNX remplacé (`c5627b99…`, remplace le Core de la 618 `dfe3bb56…`), RPCS3 Core 619
  `unchangedFromBase` ; Dolphin/ARMSX2, libretro et dépendances MeloNX conservés par la republication de
  la 619. Images changées : App, MeloNXCore, `melonx_internal_bridge`, `retro_achievements_session`,
  `rpcs3_internal_bridge`, Runner, et `armsx2_internal_bridge`, `dolphin_internal_bridge` sans changement
  de leurs sources (signalé, non bloquant). Tests frais dans les deux groupes (~26 min de bout en bout).
- Hors CI : métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub MCP
  (octets égaux aux digests de l'API) ; IPA vérifiée hors ligne, clé privée supprimée.

## 12. État de la 621 (3 novembre 2026)

Livrée sur la 620 (run `41555079757`, IPA `1521e25b…`, 194334617 octets, ~19 min de bout en bout).
Gel sur `7d88bfe0` : base effective 620 `bf6ee0b0…`, empreinte effective `cdfed832…`, 6855 fichiers
produit ; contrôle légal réussi.
- **Numéro de build.** Décision du mainteneur : la 621 est la build MeloNX et jaquettes. Le Core 621 de
  la session RPCS3 passe à la 622. Ses 16 commits sont « source seulement » (`targetBuild` 622) ; son
  premier brouillon 621 et sa clé de destinataire sont remplacés.
- **Commits revus (9).** MeloNX : `403dc3c5`, `816930fe`, `4295b522`, `4ad8814e`. Jaquettes et
  notices d'une autre session : `ef1ddfee`, `05b5a5df`, `cf87abdc`, `400d1f34`, `09eeb75b`.
- **Composants.**
  - MeloNX : remplacé par le Core du run `41552490728` (`07e9d695…`), qui remplace `c5627b99…`.
  - RPCS3 : Core 619 `unchangedFromBase`.
  - Dolphin/ARMSX2, libretro et dépendances MeloNX : republiés de la 620.
- **Extension de la recette (`7d88bfe0`).** Le gel et `test_rpcs3_pin` vérifient maintenant l'épingle
  RPCS3 contre l'arbre effectif, comme la CI, qui matérialise cet arbre avant de la vérifier.
  - **Pourquoi.** Des commits « source seulement » touchaient les entrées de l'épingle (source hôte,
    source canonique, patch). La CI les restaure, mais le gel local lisait le checkout et refusait
    l'épingle Core 619.
  - **Lecteur.** `rpcs3_core_component.pinned` prend le même lecteur optionnel, et lit le checkout par
    défaut.
  - **Fichier d'épingle.** C'est un chemin de recette, lu à HEAD. La 621 y a remis les octets de
    l'épingle livrée (`2212d1dc`), à la place de l'épingle 621 en attente de l'autre session.
- **Vérificateur MeloNX.** `melonx_dma_core_component.FRESH_GATES = 6` (`e7b2cabe`), comme
  `verify_dma_core`. La vérification hors ligne du Core refusait l'épingle avec 5 ; l'étape MeloNX de
  la livraison l'aurait refusée aussi.
- **Images changées.** App, MeloNXCore, `melonx_internal_bridge` et Runner. `armsx2_internal_bridge`,
  `dolphin_internal_bridge` et `rpcs3_internal_bridge` ont aussi changé sans changement de leurs
  sources effectives (signalé, non bloquant). Tests frais dans les deux groupes.
- **Hors CI.** Métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub
  MCP (octets égaux aux digests de l'API). IPA vérifiée hors ligne, clé privée supprimée.

## 13. État de la 622 (3 novembre 2026)

Livrée sur la 621 (run `41562838932`, IPA `48598405…`, 194494511 octets, ~25 min de bout en bout).
Gel sur `b91cd085` : base effective 621 `cdfed832…`, empreinte effective `43e0b078…` ; contrôle légal
réussi ; aucun conflit, aucun commit non classé.
- **Travail promu.** Les commits RPCS3 Core 621 que la 621 avait laissés « source seulement » la
  précèdent : ils passent par `promotedCommits` (ordre de l'historique) et non par `reviewedCommits`.
  Seuls ceux qui ont des chemins produit y figurent (`5feba2a9`, `0b7c0e38`, `89f57fb7`, `1b483577`,
  `34089b8d`, `a701a650`) ; les autres ne touchent que la recette.
- **Commits revus (2).** `e59ee305` (test) et `04df260a` (correctifs de la revue contradictoire du
  Core 621). Les jaquettes et skins Dolphin d'une autre session (`9bb35531`, `1745b3e6`) restent
  « source seulement » (`targetBuild` 623).
- **Composants.**
  - RPCS3 : remplacé par le Core 621 du run `41560325311` (`43c43aa3…`), qui remplace le Core 619
    `44fc928e…`. L'épingle vérifiée est poussée dans le même push que le brouillon 622 :
    `test_rpcs3_pin` refuse un brouillon courant dont l'épingle à HEAD ne correspond pas à l'arbre
    effectif.
  - MeloNX : Core 621 `unchangedFromBase`.
  - Dolphin/ARMSX2, libretro et dépendances MeloNX : republiés de la 621.
- **Images changées.** `libRPCS3Core.dylib`, `rpcs3_internal_bridge` et Runner.
  `armsx2_internal_bridge` a aussi changé sans changement de ses sources effectives (signalé, non
  bloquant). Tests frais dans les deux groupes.
- **Preuves.** Le reçu reprend les huit rapports de la livraison déchiffrée (identité signée,
  signature, validations, tests, environnement, durées) avant `record`, comme la 621 : 12 fichiers.
- **Hors CI.** Métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub
  MCP (octets égaux aux digests de l'API). IPA vérifiée hors ligne, clé privée supprimée.

## 14. État de la 623 (3 novembre 2026)

Livrée sur la 622 (run `41569913763`, IPA `c80911de…`, 194506776 octets, ~24 min de bout en bout).
Gel sur `2c8350f8` : base effective 622 `43e0b078…`, empreinte effective `79ec3b3c…`, 6881 fichiers
produit ; contrôle légal réussi ; aucun conflit, aucun commit non classé.
- **Commits revus (2).** `5c20e0cb` (Core MeloNX 623) et `824612ab` (son épingle vérifiée).
- **Travail promu.** `1745b3e6`, les tranches de jaquettes d'une autre session (« source seulement »
  dans la 622 pour cette build).
- **Reporté à la 624.** `9bb35531` (skins GameCube/Wii) :
  - le contrôle légal refuse son podspec (« Session source/license declaration changed since review ») ;
    il lui faut sa propre revue de déclaration, chaînée sur celle de Glacier ;
  - son overlay natif n'a pas encore été compilé avec le SDK iOS.
  - Un commit qui précède la base ne se liste pas en « source seulement » : la relecture le signale
    `missing`. Il reste différé par héritage de la base (83 chemins hérités).
- **Composants.**
  - MeloNX : remplacé par le Core 623 du run `41567689813` (`27f1afa1…`), qui remplace le Core 621
    `07e9d695…`.
  - RPCS3 : Core 621 `unchangedFromBase`.
  - Dolphin/ARMSX2, libretro et dépendances MeloNX : republiés de la 622.
- **Images changées.** App, MeloNXCore et Runner. `melonx_internal_bridge` a aussi changé sans changement de ses sources effectives (signalé, non bloquant).
  Tests frais dans les deux groupes.
- **Preuves.** Le reçu reprend les huit rapports de la livraison déchiffrée avant `record`, comme la
  622 : 12 fichiers.
- **Hors CI.** Métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub
  MCP (octets égaux aux digests de l'API). IPA vérifiée hors ligne, clé privée supprimée.

## 15. État de la 624 (3 novembre 2026)

Livrée sur la 623 (run `41574628897`, IPA `582cedd5…`, 194514240 octets). Gel sur `2b8cc703` :
base effective 623 `79ec3b3c…`, empreinte effective `9ad87ae1…` ; aucun conflit, aucun commit non classé.
- **Commit revu.** `f4338fd4` (RPCS3 Core 624, sources de la recette Core et tests). Le correctif de podspec
  des skins Dolphin d'une autre session (`a7e3ef22`, arrivé après le déclenchement de la 623) reste
  « source seulement » (`targetBuild` 625) avec les skins (`9bb35531`, report hérité).
- **Composants.**
  - RPCS3 : remplacé par le Core 624 du run `41572306405` (`e906fbd5…`), qui remplace le Core 621 `43c43aa3…`
    que la 623 gardait. L'épingle vérifiée part dans le même push que le brouillon 624.
  - MeloNX : Core 623 `unchangedFromBase`.
  - Dolphin/ARMSX2, libretro et dépendances MeloNX : republiés de la 623.
- **Images changées.** `libRPCS3Core.dylib` et Runner seulement (`mustChange` du brouillon), aucun changement
  non déclaré.
- **Test de contrat.** `test_no_build_number_literal` cherchait le numéro de build comme sous-chaîne du workflow :
  624 apparaît dans l'arbre MeloNX `82a29e6f593f6244869481e9…` que le workflow nomme. Il compare maintenant
  les littéraux de nombre qu'il relève déjà (`2b8cc703`).
- **Hors CI.** Métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub MCP
  (octets égaux aux digests de l'API). IPA vérifiée hors ligne, clé privée supprimée.

## 16. État de la 625 (3 novembre 2026)

Livrée sur la 624 (run `41591090457`, IPA `c149a6bf…`, 194552486 octets, ~21 min de bout en bout).
Gel sur `34fb75f0` : base effective 624 `9ad87ae1…`, empreinte effective `7e921879…`, 6891 fichiers
produit ; contrôle légal réussi ; aucun conflit, aucun commit non classé.
- **Commits revus (2).** `cba3441b` (Core MeloNX 625) et `6c15ed68` (son épingle vérifiée).
- **Travail promu.** Les skins GameCube/Wii d'une autre session :
  - `9bb35531`, différé depuis la 622 ;
  - `a7e3ef22`, « source seulement » dans la 624 pour cette build.
- **Promotion partielle (`paths`).** Le podspec du pont Dolphin est laissé hors des deux commits :
  - `a7e3ef22` le remet aux octets revus, que la base a déjà ;
  - la base ne l'a donc jamais différé, et le gel refuse un chemin promu non différé (« A promoted path
    was not deferred by the base delivery »).
- **Composants.**
  - MeloNX : remplacé par le Core 625 du run `41589061374` (`dd3fe017…`), qui remplace le Core 623
    `27f1afa1…`.
  - RPCS3 : Core 624 `unchangedFromBase`.
  - Dolphin/ARMSX2, libretro et dépendances MeloNX : republiés de la 624.
- **Images changées.** App, MeloNXCore, `dolphin_internal_bridge` et Runner. C'est la première
  compilation, avec le SDK iOS, de l'overlay natif des skins. `rpcs3_internal_bridge` a aussi changé sans changement de ses sources effectives (signalé, non bloquant).
- **Hors CI.** Métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub
  MCP (octets égaux aux digests de l'API). IPA vérifiée hors ligne, clé privée supprimée.

## 17. État de la 626 (3 novembre 2026)

Livrée sur la 625 (run `41598013782`, IPA `bf4b324a…`, 194553035 octets, ~25 min de bout en bout).
Gel sur `7d6f6fbb` : base effective 625 `7e921879…`, empreinte effective `b8403d43…`, 6891 fichiers
produit ; contrôle légal réussi ; aucun conflit, aucun commit non classé.
- **Commits revus (2).** `17eabf03` (Core MeloNX 626) et `cabef0aa` (son épingle vérifiée).
- **Composants.**
  - MeloNX : remplacé par le Core 626 du run `41596390897` (`18fbb04c…`), qui remplace le Core 625
    `dd3fe017…`.
  - RPCS3 : Core 624 `unchangedFromBase`.
  - Les autres composants sont republiés de la 625.
- **Images changées.** MeloNXCore et Runner. `libretro_internal_bridge` et `rpcs3_internal_bridge` ont aussi
  changé sans changement de leurs sources effectives (signalé, non bloquant).
- **Hors CI.** Métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub
  MCP. IPA vérifiée hors ligne, clé privée supprimée.

## 18. État de la 629 (3 novembre 2026)

Livrée sur la 626 (run `41622115556`, IPA `952b2641…`, 194618465 octets, ~21 min de bout en bout). Le numéro 627 est
celui du Core RPCS3 627, livré ici ; la 628 n'a pas été livrée.
Gel sur `79d866ef` : base effective 626 `b8403d43…`, empreinte effective `140e5707…`, 6897 fichiers produit ;
contrôle légal réussi ; aucun conflit, aucun commit non classé.
- **Commits revus (3).** `e34dccf9` et `1ce1cd14` (Core MeloNX 628) et `2620d011` (son épingle vérifiée).
- **Commits RPCS3 revus (7).** `40c6502a`..`8e68bdee`, `2abb1ac2` (Core RPCS3 627 de la session 012mUASm) et `021a15e4`
  (son épingle, vérifiée hors ligne avec le vérificateur du dépôt).
- **Composants.**
  - MeloNX : remplacé par le Core 628 du run `41614833262` (`dfd9061e…`), qui remplace le Core 626 `18fbb04c…`.
  - RPCS3 : remplacé par le Core 627 du run `41610162888` (`eccf8535…`), qui remplace le Core 624 `e906fbd5…`.
  - Les autres composants sont republiés de la 626.
- **Images changées.** MeloNXCore, libRPCS3Core, rpcs3_internal_bridge et Runner. `libretro_internal_bridge` a
  aussi changé sans changement de ses sources effectives (signalé, non bloquant).
- **Première tentative.** Run `41618683768` en échec au contrôle d'installation du Core RPCS3 : la liste figée de
  marqueurs demandait le canari des Cores 587 à 624, que le Core 627 renomme exprès. Le correctif de recette
  `79d866ef` accepte le canari nommé d'après son Core ; regel sur la même empreinte produit.
- **Hors CI.** Métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub
  MCP. IPA vérifiée hors ligne, clé privée supprimée.

## 19. État de la 718 (10 novembre 2026)

IPA commune privée livrée sur la 694 (consigne du mainteneur du 10 novembre) : run `42747501121`,
déclencheur `34fbf8eb`, IPA `001957b9…c29a`, 263465367 octets, ~22,6 min de bout en bout
([reçu](evidence/rewind718/delivery.json)). RPCS3 Core 914 et MeloNX Core 717 téléchargés et authentifiés,
non recompilés ; PR #164 et PR #165.
- **Gel.** Premier gel sur `0c8c0a43`, regel sur `6ad78af6` (recette seule) : empreinte effective `af020701…`,
  7440 fichiers produit, 49 commits revus, 10 « source seulement », contrôle légal réussi.
- **Première tentative.** Run `42741950414` en échec dans le seul groupe natif : `pocket-skin-input-chain`,
  « No module named 'PIL' », doublon d'une commande du groupe Flutter (réussie là). L'application avait
  compilé le binaire Release et s'est arrêtée à l'attente des tests.
- **Relance.** Correctif `6ad78af6` : doublon natif et second passage identique de
  `test/rpcs3_diagnostics546_native_test.py` retirés, garde d'argv unique par groupe, garde PIL native,
  simulateur démarré une fois avant le groupe (règle § 3.7). Preuve Flutter réutilisée du run
  `42741950414` (artefact `13729494334`) ; natif frais, 19 commandes ; contrat de livraison frais.
- **Durées.** Tableau avant/après dans `docs/delivery-speed.md` § 5.
- **Hors CI.** Métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub
  MCP. IPA vérifiée hors ligne, clé privée supprimée. Aucun test sur iPhone.

## 20. État de la 719 (10 novembre 2026)

IPA commune privée livrée sur la 694 : run `42779263525`, déclencheur `3b4b4d02`, cinq jobs verts au premier
essai, IPA `2446e86d…4c56`, 263643764 octets, 25,5 min de bout en bout
([reçu](evidence/rewind719/delivery.json), douze fichiers de preuve dont l'inventaire signé des 90 images : ce
reçu peut servir de base). Contenu de la 718 avec RPCS3 Core 918 (pin `3d8ec315`, charge `78f2defd…f9d3`) ;
MeloNX Core 717 inchangé.
- **Gel.** `78811d59` : empreinte effective `46d8fc5c…`, 7465 fichiers produit, 52 commits revus (les 49 de
  la 718, la fusion de réalignement `d506a8ed` § 3.9, `cd325180`, `66760ea8`), 10 « source seulement », contrôle
  légal réussi. Base 694 parce que le reçu de la 718 n'a pas d'inventaire signé (§ 3.8).
- **Tests.** Flutter et natif frais : la preuve Flutter de la 718 porte le nom d'artefact et l'empreinte
  effective de la 718, elle ne se réutilise pas d'une build à l'autre.
- **Durées des jobs.** Contrôle 0,9 min ; Flutter 7,5 min ; natif 20,4 min ; republication 1,0 min ;
  application 24,4 min, dont compilation Xcode 240 s et signature/export 43 s.
- **Image non déclarée.** `dolphin_internal_bridge` diffère de la base (elle lui était identique dans la 718).
  Comparée à celle de la 718 : mêmes 38 sections de code et de données (même empreinte), mêmes liaisons ;
  seuls diffèrent les stubs fabriqués par l'éditeur de liens, qui lisent l'adresse de `objc_msgSend` dans
  l'une ou l'autre de deux cases voisines de la table des symboles importés, toutes deux liées à ce même
  symbole. Aucune différence de comportement ; rien à classer (§ 3.10).
- **Enregistrement.** Les huit reçus copiés avant la suppression de la clé (§ 3.5). `record` s'arrêtait sur la
  copie du rapport sur lui-même quand le vérificateur l'avait écrit dans le dossier de preuves : corrigé, avec
  un test qui rejoue le reçu le plus récent (rapport dans le dossier ou ailleurs) et deux contrôles négatifs
  (inventaire absent, inventaire d'une autre IPA).
- **Hors CI.** Métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub MCP. IPA
  vérifiée hors ligne (`passed-offline-checks`), clé privée supprimée. Aucun test sur iPhone.

## 21. État de la 720 (10 novembre 2026)

IPA commune privée livrée sur la 719, première base munie d'un reçu à inventaire signé depuis la 694 : run
`42798677772`, déclencheur `8a1884a9`, cinq jobs verts, IPA `e7ad0a2a…5b64`, 266993445 octets, 26,4 min de bout en
bout ([reçu](evidence/rewind720/delivery.json), douze fichiers de preuve dont l'inventaire signé des 90 images).
Contenu de la 719 avec les remises restées en file pendant sa construction : lot 9 de MeloNX (`a8198f79`, fusion
`7d0ca6c1`), PR #166 (`32fd5309`, fusion `80aa7ac7`) et PR #167 (`66c129b9`, fusion `b6a9deee`) des skins. RPCS3
Core 918 inchangé (`unchangedFromBase`, charge `78f2defd…f9d3` retenue).
- **Composants.** MeloNX remplacé par le « Core 719 » de son propriétaire (run `42787755406`, 50 min, 76 gates
  Apple frais ; artefact `13753428009`, bibliothèque iPhone `1b2d434b…2f4b`, charge `1336c87b…f38a`, contrat
  `38b3a5b7`, pin `864dc08c`) à la place du Core 717. Ce libellé est celui du contrat gelé du propriétaire ;
  l'IPA 719 contient le Core 717. MoltenVK 1.4.2 avec le patch de propriété du drawable (`9a6867b7`) : artefact
  `13736999411` du run `42760131591`, binaire `6d3a8d03`, vérifié hors ligne puis épinglé. L'empaqueteur refusait
  toute source patchée et sa notice disait « non modifié » (la livraison se serait arrêtée à cette étape) :
  corrigé par `b179a080`, avec une notice de modification et la copie du patch à côté de la licence ; test de
  parité à 64 contrôles dont six refus.
- **Revues.** Deux lectures indépendantes, en lecture seule. Skins : rien à corriger (masque sur le calque du
  corps seulement, test de contact intact, découpe absente ou invalide = rectangle précédent) ; remarque mineure
  transmise : un skin Delta « portrait seul » sans écran, ouvert à l'horizontale, garde de fines bandes latérales
  (marges de zone sûre non tournées dans `screenFrameForBounds:`), aucun skin Pocket concerné. MeloNX : aucun
  défaut démontré ; remarque transmise : après un saut « fragmenté » de plus de 16 s, le maintien du GC reste muet
  jusqu'au prochain gen2 d'arrière-plan du runtime, sans compteur ni ligne de journal. Décision du propriétaire
  (09:07 UTC) : pas de correctif avant la 720, la dormance existant aussi dans le Core 717 ; prochain Core : une
  ligne bornée « gcKeepAlive dormant » et un compte « Missed » séparé, avec la reproduction de main comme gate.
- **Déclarations.** La chaîne de déclarations refusait l'arbre effectif (« Pocket board Originals added packs
  differ from the review ») : six packs reconstruits sur place. Revue de révision
  `evidence/pocket-skins-framing-press-declarations-2026-11-10.json` et sa règle (`c6cb5837`) : une revue antérieure
  n'accepte un pack reconstruit qu'à l'identité que la révision lui donne, quand la révision nomme l'identité que
  cette revue avait enregistrée. Test de contrat sur l'arbre effectif, six contrôles négatifs.
- **Gel.** Premier gel `b5be6a97` (empreinte effective `36a27ff5…b2ad`, six commits revus) ; regel `e53126a6` après
  le correctif : empreinte `be9afa4f…05e9`, sept commits revus (trois fusions, pin et empaquetage MoltenVK, revue
  de révision des skins, test hôte libretro, nom d'appel Swift), aucun « source seulement », 78 chemins différés
  hérités, 7476 fichiers produit, contrôle légal réussi. Images « doit changer » : `Runner`, `MeloNXCore`,
  `MeloNXMoltenVKStandalone`, ponts armsx2, dolphin et melonx.
- **Première tentative.** Run `42795453604` (déclencheur `ff3edb7e`, 10:00:33 UTC) en échec ; contrôle,
  republication et natif (19 commandes) verts. Deux jobs rouges, tous deux sur `6ddc96fd` (contacts du skin après
  le menu), qu'aucun job n'avait compilé ni exécuté auparavant. Application (job `129759822347`, 10:11:32),
  xcodebuild code 65, une erreur : `MeloNXMetalSessionViewController.swift:339:32:
  'syncNowAndWhenUncovered(_:stillWanted:sync:)' has been renamed to 'syncNowAnd(whenUncovered:stillWanted:sync:)'`.
  Flutter (job `129759822227`), 979 réussis, 1 échec : `test/melonx_skins_test.dart` attendait encore l'unique
  `skinSession?.sync()` après `router?.suspend(...)`. Correctif `65a9e633` : l'appel porte le nom que Swift donne
  au sélecteur Objective-C ; le contrat Dart attend la forme du lot 9 et refuse l'écriture qui ne compile pas. Les
  deux groupes de tests sont rejoués, le correctif changeant l'arbre effectif. Seconde demande à 10:23:06.
- **Leçon (règle § 3.11).** Ni le run du Core MeloNX (gates), ni le run simulateur des skins (tests Objective-C
  des ponts) ne compilent `MeloNXMetalSessionViewController.swift` : la première demande de livraison a servi de
  compilateur. Coût ici : 22,5 min entre les deux demandes, un regel et deux groupes de tests rejoués.
- **Durées des jobs.** Contrôle 0,9 min ; Flutter 7,9 min ; natif 20,2 min ; republication 1,6 min ; application
  25,4 min, dont compilation Xcode 323 s et signature/export 60 s.
- **Images non déclarées.** `libretro_internal_bridge` et `rpcs3_internal_bridge`, sans aucun changement de source
  entre `3b4b4d02` et `8a1884a9`, diffèrent de la 719 par un octet de `__stubs` et un octet par bouchon de
  `__objc_stubs` (2055 et 834 bouchons). Dans la 719, les bouchons Objective-C lisent l'adresse de `objc_msgSend`
  dans la première de deux cases voisines de la table des symboles importés et le bouchon ordinaire dans la
  seconde ; dans la 720, c'est l'inverse. Les deux cases sont liées au même symbole ; toutes les autres sections,
  la table `__got` et les liaisons (3337 et 3773) sont identiques. Aucune différence de comportement ; rien à
  classer (§ 3.10). `dolphin_internal_bridge`, dans le même cas pour la 719, change ici pour une raison déclarée
  (PR #166 et PR #167).
- **Contenu relu dans le fichier livré.** `libRPCS3Core.dylib` : charge `78f2defd`, ligne SCHED918. `MeloNXCore` :
  charge `1336c87b`. `MeloNXMoltenVKStandalone` : sections de code et de données identiques au binaire épinglé
  (seul `__LINKEDIT` diffère, par la signature), marqueur « RewindBox drawable ownership », notice de modification
  et copie du patch (`9a6867b7`) dans `Legal/MeloNX/StandaloneMoltenVK/`. Pont MeloNX : sélecteur
  `syncNowAndWhenUncovered:stillWanted:sync:` et littéral `mgd=`, absent de la 719. 82 des 90 images gardent la
  charge de la 719.
- **Échecs préexistants, hors des groupes de livraison.** Frontend libretro, `diagnostic_routing_test.m` (le
  lanceur passe deux arguments depuis la PR #152, le test en exigeait un) : corrigé par `bad024ec`, 22 fichiers
  sur 22 au run `42795464202`. Banc de session Dolphin (SessionMenuTests 13 tests / 21 échecs,
  RecordingControllerTests) : tests périmés depuis les changements de `DolphinSessionMenu.mm` du 18 octobre au
  1er novembre ; ouvert, propriétaire main. `test/melonx_capture_journal_test.py` : échec sous Linux, identique
  sur `3b4b4d02` ; signalé au propriétaire MeloNX. `DolphinSkinOverlayTests testWiiButtonsLandscape` : un échec au
  run `42795464202` (`DolphinSkinOverlayTests.mm:233`, compte du Menu 0 puis 2 au lieu de 1) sur des sources qui
  passent au run `42787761020` (36/36) ; attente fixe de 20 ms ; signalé au propriétaire des skins, qui l'a
  corrigée dans les trois bancs (PR #168, `c9e3f26c` : attente de l'événement bornée à 2 s, puis 30 ms pour qu'une
  seconde livraison fasse encore échouer le « une fois ») ; relue et fusionnée par main (`11ee0f5a`), run
  `42800736698` vert. Un run vert ne prouve pas la disparition de l'instabilité. Cette fusion touche des chemins
  de test : elle se classe dans le manifeste de la build suivante.
- **Hors CI.** Métadonnées API par l'API REST publique, pièces par les URL signées du serveur GitHub MCP. IPA
  vérifiée hors ligne (`passed-offline-checks`), huit reçus copiés avant la suppression de la clé (§ 3.5), clé
  privée supprimée, envoi privé en fichier. Aucun test sur iPhone.

## 22. État de la 721 (10 novembre 2026)

IPA commune privée livrée sur la 720 : run `42822649775`, déclencheur `cfb56420`, cinq jobs verts, IPA `bc640a83…c0d7`,
267033667 octets, 19,5 min de bout en bout ([reçu](evidence/rewind721/delivery.json), douze fichiers de preuve dont
l'inventaire signé). Contenu de la 720 avec RPCS3 Core 919 (pin `44527c61`, charge `a74a9cf6`), la fusion de la PR 168
(tests seulement) et une correction de test ; MeloNX Core 719 et `MeloNXMoltenVKStandalone` retenus de la base.
- **Première tentative.** Run `42819476474` (déclencheur `587abef9`) : contrôle, republication et Flutter verts,
  l'application compilée ; le groupe natif échoue dans `test/melonx_perf_journal_test.py` sur un plancher de 10 % d'un
  échantillon de 0,25 s du thread occupé (7 % sur le runner partagé ; sources identiques à la 720, où il passait).
  Correctif `653bb484` : le thread est contrôlé par son rang et une part mesurée (> 0 et au moins celle de chaque autre
  thread listé) ; regel (empreinte effective `e66096fe`), les deux groupes rejoués.
- **Images non déclarées.** Les ponts libretro et RPCS3, sources inchangées, diffèrent de la 720 par les seuls bouchons
  de l'éditeur de liens (les deux cases d'import d'`objc_msgSend` échangées de nouveau) ; rien à classer (§ 3.10).
- **Durées.** Application 18,5 min, dont compilation Xcode 341 s et signature/export 62 s ; natif 12,6 min.
- **Hors CI.** Métadonnées par l'API REST publique, pièces par les URL signées du serveur GitHub MCP, IPA vérifiée hors
  ligne, huit reçus copiés avant la suppression de la clé, clé supprimée. Aucun test sur iPhone.

## 23. État de la 722 (10 novembre 2026)

IPA commune privée livrée sur la 721 : run `42852972508`, déclencheur `c7ca5d37`, cinq jobs verts, IPA `e9aad8d2…f245d`,
271385645 octets ([reçu](evidence/rewind722/delivery.json), douze fichiers de preuve dont l'inventaire signé, 90
images). Contenu de la 721 avec RPCS3 Core 920 (pin `f9f2b478`), MeloNX Core 721 (pin `784fcc5d`) avec
`MeloNXMoltenVKStandalone` reconstruit (MoltenVK v1.4.2 et le correctif RewindBox en trois parties, binaire
`6f65b2a6`), le stall watch du journal MeloNX et les fenêtres Pocket au ratio du jeu (PR 169).
- **Première tentative.** Run `42848698413` (déclencheur `7a7a2eee`) : contrôle, republication, Flutter et natif verts,
  l'application compilée et scellée ; `split_encrypted_delivery.py` refuse alors la charge chiffrée au-delà de 4 × 64 Mio
  (la 721 en occupait déjà 99,5 % ; la PR 169 ajoute environ 3,9 Mo d'archives). Correctif `ea8152d9` (chemin produit) :
  quatre pièces d'au plus 96 Mio, test d'une charge de plus de 256 Mio (l'ancien découpeur la refuse, le nouveau
  l'accepte) ; regel (empreinte effective `2528a3dc`), les deux groupes rejoués. Pièces de 68068462 octets.
- **Chaîne légale des skins.** La seconde revue de révision des packs Pocket est liée à la première
  (`collect_build_source_evidence.py`, revues de révision en chaîne, seule la dernière comparée au catalogue).
- **Images non déclarées.** `rpcs3_internal_bridge`, sources inchangées, diffère de la 721 par les seuls bouchons de
  l'éditeur de liens (les deux cases d'`objc_msgSend` échangées de nouveau ; tables de liaison et GOT identiques).
- **Piège évité.** Les huit reçus se copient depuis `work/delivery/` du vérificateur, jamais par une recherche sur tout
  `work/` : l'arbre effectif décompressé y contient les reçus des livraisons précédentes ; `record` a refusé le premier
  exemplaire copié (celui de la 616) avant toute écriture.
- **Durées.** Compilation Xcode 345 s, signature/export 57 s ; application 20,8 min, natif 15,7 min.
- **Hors CI.** Métadonnées par l'API REST publique, pièces par les URL signées du serveur GitHub MCP, IPA vérifiée hors
  ligne, huit reçus copiés avant la suppression de la clé, clé supprimée. Aucun test sur iPhone.


## 24. État de la 726 (11 novembre 2026)

IPA commune privée livrée sur la 725 : run `43106533461` (tentative 2), déclencheur `bd99e8b7`, gel `8fb2ee39`, cinq jobs
verts, IPA `ac9612b4…d618`, 272927734 octets, 91 images ([reçu](evidence/rewind726/delivery.json), douze fichiers de
preuve dont l'inventaire signé). RPCS3 Core 933, MeloNX Core 735, PR 172 (plugin `xenia_internal_bridge`, nouvelle image
déclarée sous `images.added`), PR 176 et 177, couche bibliothèque Switch 2, corrections de messages de la revue 725.
- **Ligne de livraison rétablie** (§ 3.9) : la fusion `d769ef7c` de la session MeloNX mettait son propre commit en premier
  parent ; `c8f39557` (arbre de `eb7a88c4`, premier parent `594e1d31`) rend à chaque commit de `Claude` sa classification.
- **Portage** des deux corrections de messages qui touchent des fichiers portant les lignes différées de `b06888a9`
  (`2293b563`, `ecf6ace6`, `86970b20`), comme en 725.
- **Groupe Flutter rejoué sur l'arbre effectif avant le gel** : la commande de base `translation-source` échouait (appels
  `setLanguage` reformatés par la PR 172) ; corrigé dans `a5acf378`. Les commandes qui lisent l'historique git se jouent dans
  le checkout avec l'arbre effectif appliqué, pas dans un export.
- **Panne GitHub Actions** : le run du premier déclencheur `0fbb5ac8` (`43098367088`, créé à 20:50 UTC pendant la panne) n'a
  jamais démarré et son annulation a été refusée (409) ; second déclencheur après un nouveau gel (même arbre effectif).
  Tentative 1 : `republish` en échec sur `gh: HTTP 503` (archive Dolphin retenue) ; run annulé puis rejoué en entier.
- **Image non déclarée** : `armsx2_internal_bridge`, sources inchangées, ne diffère de la 725 que par les bouchons de
  l'éditeur de liens (`__stubs`, `__objc_stubs`) ; rien à classer (§ 3.10).
- **Hors CI.** Métadonnées par l'API REST publique, pièces par les URL signées du serveur GitHub MCP, IPA vérifiée hors
  ligne, huit reçus copiés avant la suppression de la clé, clé supprimée. Aucun test sur iPhone.
