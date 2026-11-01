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
- **Sources produit** :
  - seul le delta revu depuis la base entre dans la build (périmètre gelé) ;
  - le travail concurrent qui n'en fait pas partie est déclaré « source seulement » et n'est jamais
    compilé en silence.
- **Tests** :
  - un groupe de tests n'est rejoué que si l'une de ses entrées a changé ;
  - sinon, sa preuve épinglée est authentifiée et réutilisée, avec le libellé « réutilisée » ;
  - le contrat de livraison, qui lit la recette, est toujours rejoué.
- **Recette** :
  - on ne copie plus une recette par build (`rewindNNN_*.py`, `rewindNNN-*.yml`) ;
  - on déclare les changements de la build dans son manifeste ;
  - on n'étend la recette standard que pour un nouveau type de changement.
- **Échec** : une livraison échouée est relancée en ne modifiant que la recette, et ses jobs de test
  réussis sont réutilisés.

## 2. Déjà en place dans la recette 610 (mesuré)

| Mécanisme | Où | Effet mesuré |
| --- | --- | --- |
| Réutilisation des tests d'une tentative précédente | `REUSED_TESTS`, `reuse_equivalence()`, opération `reuse-check` de `.github/diagnostics/rewind610_delivery.py` | Livraison 610 en **11,5 min** au lieu d'environ 27 : tests natifs 15,5 min et Flutter 2,6 min évités |
| Contrat de livraison rejoué à chaque run | contrôle préalable (`reuse-check`), authentifié par l'API dans le job application | Contrat 16/16, journal `7cbdd99c…` |
| Entrées concurrentes « source seulement » | `CONCURRENT_UNCOMPILED` de `rewind610_baseline.py`, enveloppes `_inputs_match_retained` et `melonx-materialize` | Le Core MeloNX 609 est conservé malgré les commits MeloNX concurrents ; chaque écart est consigné |

Conditions de la réutilisation :
- depuis le commit testé, seuls les chemins de recette (`RECIPE_PATHS`) ont changé ;
- le delta produit gelé est identique ;
- les jobs réutilisés ont réussi avec leurs étapes requises ;
- leurs artefacts ne sont pas expirés et correspondent aux empreintes épinglées ;
- leurs reçus lient l'exécution testée et le périmètre testé.

## 3. La recette standard (en préparation, première cible : 611)

- **Un manifeste par build** déclare :
  - la base (reçu de la dernière IPA livrée) ;
  - les composants remplacés, avec leurs identifiants de producteur ;
  - le delta source revu ;
  - les entrées concurrentes « source seulement » ;
  - les preuves de test réutilisables.
- **Un seul script et un seul workflow** stables, avec un vérificateur par type de composant
  (conserver ou remplacer).
- **Composants conservés republiés** par chaque livraison, pour que la build suivante ne dépende plus
  d'artefacts producteurs qui expirent. Les cœurs libretro conservés depuis la 608 expirent le
  3 novembre 2026, et les dépendances natives MeloNX le 5 novembre.
- **Compilation en parallèle des tests.** L'application démarre en même temps que les tests à
  rejouer, et ne les attend qu'avant d'embarquer l'identité. Gain estimé : environ 10 min quand les
  tests natifs doivent être rejoués.
- **Corrections issues de la relecture contradictoire de la recette 610 :**
  - conserver la preuve du contrat rejoué sous forme d'artefact authentifié par empreinte ;
  - remplacer le champ ambigu `freshTests` par `testsExecutedInThisRun` et `testsRun` ;
  - lire les deux périmètres depuis les commits ;
  - remplacer le test de garde des chemins de recette par une vérification des lectures réelles.

La 611 sera la première build construite ainsi :
- elle part de la 610 livrée ;
- le Core MeloNX est remplacé par le Core à lectures fragmentées ;
- le Core RPCS3 est remplacé par le Core 611, qui porte le patch RetroAchievements PS3 ;
- elle ajoute les commits RetroAchievements.

La session MeloNX déclenche l'unique livraison 611, après relecture de son manifeste par la session
RPCS3.
