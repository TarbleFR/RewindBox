# Livraison « Core seul » à partir d'une IPA publiée

27 octobre 2026. Ce mode raccourcit les livraisons privées qui ne changent que
le Core RPCS3, comme 559 et 560. Son premier run CI (livraison 561) a révélé
un contrôle que la validation hors CI n'avait pas couvert (§ 6) ; il est
corrigé.

## 1. Pourquoi

Une livraison « Core seul » expédie le produit précédent octet pour octet et
ne remplace que `libRPCS3Core.dylib`. Le build complet recompile pourtant
Flutter et Xcode, et reproduit ainsi le même Runner, les mêmes plugins et la
même image Dart.

**Ce qu'a changé le build complet 560 face à l'IPA 559 :**
- l'image Dart est identique ;
- dix exécutables ne diffèrent que par leur signature ;
- Runner et le pont Dolphin ne diffèrent que par leur `LC_UUID`, la chaîne de
  version Apple (`PROJECT:Runner-560`) et l'ordre non déterministe du linker
  (`__objc_stubs`, `__LINKEDIT`) ;
- il n'y a ni commit ni numéro de build compilés dans le code ;
- le reste est réécrit après la compilation : le Core, les numéros de version
  des `Info.plist`, les reçus et les signatures.

**Le Core n'est pas lu par Xcode.** `embed_rpcs3_core_lazy.py` le copie dans
l'app après l'édition des liens.

**Durées observées (run 560).** La compilation Xcode prend 5,4 minutes.
L'IPA ne peut être assemblée qu'une fois le Core prêt, et les étapes du Core
arrivent tôt dans le job, alors que la compilation du Core en prend 16.

## 2. Ce que fait le mode

`build-utils/make_core_swap_workflow.py` dérive la variante d'un workflow de
livraison complet. Il y apporte exactement trois changements, puis vérifie le
résultat contre cette description.

1. **Job `checks`** : après le pin, `core_swap_base.py --check` vérifie en
   environ une minute :
   - la release et l'empreinte de son fichier enregistrée par GitHub ;
   - la taille de ce fichier ;
   - le reçu de livraison de la base ;
   - l'égalité des arbres produit.
2. **Job macOS : compilation remplacée.** `core_swap_base.py` remplace la
   compilation Xcode :
   - il télécharge l'IPA publiée et vérifie son SHA-256 contre la valeur
     épinglée, l'empreinte GitHub et le reçu de livraison de la base ;
   - il exige que les arbres produit (`lib`, `native`, `packages`, `assets`,
     `pubspec`) de l'index épinglé soient ceux du reçu de base ;
   - il extrait l'app avec ses permissions là où Xcode la laisse
     (`…/Release-iphoneos/Runner.app`) ;
   - il passe au numéro du build toutes les versions de bundle égales au
     numéro de base ; la version courte doit être celle du `pubspec` ;
   - il retire les reçus d'identité numérotés de la base, que les étapes
     d'intégration réécrivent pour le build ;
   - il remet StikJIT dans son état d'avant scellement (§ 6) ;
   - il écrit `build/delivery/core-swap-base.json`.
3. **Job macOS : étapes du Core déplacées.** Les quatre étapes du Core RPCS3
   (attente du run, attente du composant, téléchargement, vérification et
   installation) prennent la place de la compilation, juste avant
   l'intégration du Core. Tout ce qui n'en dépend pas tourne pendant la
   compilation du Core :
   - les autres moteurs ;
   - la configuration de l'hôte ;
   - StikJIT ;
   - la base publiée.

Toutes les autres étapes restent identiques, dans le même ordre, avec les
mêmes validateurs :
- l'intégration des moteurs, des reçus et du bundle légal ;
- l'emballage ;
- le scellement, qui re-signe chaque image et prouve que la signature ne
  change aucune section de code ni de données ;
- toutes les vérifications finales ;
- le chiffrement.

## 3. Conditions d'emploi

- **Base publiée.** La base doit être une release publiée : la CI ne peut pas
  lire les livraisons privées, chiffrées pour une clé qu'elle n'a pas.
- **Chaîne « Core seul ».** Chaque livraison entre la base et le build doit
  être « Core seul ». Le contrat source de chaque recette le prouve déjà
  (`changed ⊆ CELL ∪ RECIPE` face à l'arbre livré précédent). Les arbres
  produit sont revérifiés contre le reçu de base.
- **Script dans la recette.** Le module d'arbre du build doit lister
  `build-utils/core_swap_base.py` dans sa recette, sinon le pin le retire. Le
  contrôle du job `checks` échoue alors en moins d'une minute.
- **Repli.** Dès qu'un fichier produit change, `core_swap_base.py` refuse :
  il faut le build complet.

**Base disponible.** C'est la release `0.0.10`, publiée par le mainteneur le
26 octobre 2026. Elle porte la build 559 : fichier `RewindBox-.0.0.10.ipa`,
SHA-256 `f16c2a3529537bfbaa933972ed63f6ce96bb2a9ca176f1e2d1726dcd7896480d`,
égal à l'IPA livrée de
[`evidence/rpcs3-cell559-delivery.json`](evidence/rpcs3-cell559-delivery.json).

## 4. Validation hors CI

**Sur la vraie release 0.0.10**, `core_swap_base.py` :
- vérifie l'empreinte et les arbres produit ;
- tamponne exactement les 11 `Info.plist` et retire exactement les 4 reçus que
  le build complet 560 avait changés.

**L'app préparée en 560**, comparée à l'IPA 560 compilée, ne diffère que par
ce que les étapes suivantes réécrivent :
- le Core, les reçus et les signatures ;
- Runner et le pont Dolphin, à cause de l'ordre du linker ;
- 2 `Info.plist`, identiques en contenu (encodage binaire différent).

Les 9 autres `Info.plist` sont identiques à l'octet.

**`test/core_swap_base_test.py`** couvre :
- le tamponnage (plists binaires et XML) et les reçus ;
- 7 refus de la préparation ;
- la variante de workflow tirée de `rpcs3-cell560-delivery.yml`, et 3 refus de
  sources altérées.

## 5. Gain attendu

Ce sont des estimations tirées des runs 559 et 560, pas des mesures du mode
lui-même.

| Livraison « Core seul » | Durée |
|---|---|
| Aujourd'hui : Core puis IPA, l'une après l'autre | ~50 min |
| Core et recette poussés ensemble, build complet | ~36 min |
| Core et recette poussés ensemble, Core seul | ~24 min |

Le premier run réel est à surveiller. En cas d'échec, la recette complète
sert de repli, au prix d'un run de plus.

## 6. Premier run CI (livraison 561) et correction StikJIT

- **Run `40486995044`** sur `5dd6a5ae` : le job `checks` réussit, contrôle
  core-swap compris. Le job macOS échoue à « Package and validate RewindBox
  IPA » : `StikJIT binary does not match tested native artifact`.
- **Cause.** Xcode intègre StikJIT depuis le framework testé que les étapes
  StikJIT installent (binaire `224325cc…`, le même artefact en cache pour
  559, 560 et 561). `validate_stikjit_ipa.py` compare ce binaire octet pour
  octet **avant** le scellement. L'app publiée porte le même binaire, mais
  déjà signé par le scellement de la 559 (`5e37408c…`).
- **Correction.** `core_swap_base.py` remet le binaire testé à la place du
  binaire publié, après avoir exigé la même empreinte `payload_fingerprint`
  que celle du scellement : sections de code et de données, symboles,
  dépendances, run paths, plateforme, OS minimum et nom d'installation.
  Seule la signature diffère, et le scellement la réécrit. Le reçu de
  scellement de la 559 enregistre pour ce binaire non signé l'empreinte
  `57e75fbd…`, qui est aussi celle du binaire publié.
- **Autres images.** Les autres binaires issus d'artefacts testés (ARMSX2,
  libretro, MoltenVK, MeloNX, Core RPCS3) sont recopiés par les étapes
  d'intégration, comme dans le build complet. StikJIT est le seul qu'Xcode
  intègre lui-même.
- `make_core_swap_workflow.py` ajoute `core_swap_base.py` aux chemins de
  déclenchement de la variante : le script fait partie de la recette.
- `test/core_swap_base_test.py` couvre la remise en place du binaire testé et
  deux refus : un code différent, et un artefact qui n'est pas celui de son
  identité.
