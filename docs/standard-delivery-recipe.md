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
- **Arbre effectif** : le gel rejoue `base..HEAD` depuis l'arbre de la base et n'applique que les
  chemins produit des commits revus. Un commit revu doit partir des octets déjà présents dans l'arbre
  effectif (sinon refus) ; un commit « source seulement » est différé ; un commit non classé qui
  touche le produit est refusé. Le manifeste enregistre les écarts avec la base, la liste à restaurer
  par rapport au HEAD gelé et `effectiveDigest`. En CI, l'opération `materialize` est la première
  étape après le checkout de chaque job : elle vérifie que les commits postérieurs au gel ne touchent
  que des chemins de recette, restaure les chemins (modes, liens, suppressions) depuis les objets git
  et recalcule l'empreinte depuis les fichiers. Aucun checkout ultérieur.
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
   manifeste gelé avec le sujet `… [ipa-delivery:<N>]` (pas de `[skip ci]`). Un sujet sans balise ne
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
