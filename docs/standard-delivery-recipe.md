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
