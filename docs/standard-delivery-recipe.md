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
   `build-utils/verify_downloaded_delivery.py` (clé privée hors Git), puis
   `standard_delivery.py record <N> --run <ID> --verification … --api …` écrit
   `docs/evidence/rewind<N>/delivery.json` au schéma 610. Supprimer la clé privée.
6. **Relance** : ne changer que la recette ; pour réutiliser un groupe, passer `tests.<groupe>.mode`
   à `reuse` avec ses épingles (source, run, job, artefact, empreinte) et regeler.

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
