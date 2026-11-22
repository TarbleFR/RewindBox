# MeloNX (RSwitch) après l'IPA 820 : fermeture, saccades, mémoire entre deux jeux

22 novembre 2026. Journaux privés de l'appareil (IPA 816 à 820, 15 sessions, Super Smash Bros. Ultimate et Hogwarts
Legacy) : seuls des comptes et des durées figurent ici. Rien de ce lot n'est mesuré sur iPhone.

## Une cause commune : le chargement du cache principal ne se termine plus

À la création d'un cache de pipelines à partir de données, MoltenVK compile chaque bibliothèque Metal du fichier
(`MVKPipelineCache::readData`, un `newLibraryWithSource` par bibliothèque) avant que le cache ne serve une seule
recherche. Tant que le cache de bibliothèques de Metal (géré par iOS, dans le conteneur de l'application) est chaud,
c'est rapide : 144 Mio en 2,3 s (SSBU) et 98,5 Mio en 1,3 s (Hogwarts) sur les IPA 785 et 786. Après une réinstallation
dans un nouveau conteneur, ce cache est vide et chaque bibliothèque repasse par le compilateur.

Constats, IPA 816 à 820 :

- `primaryReady` atteint dans 0 session sur 14 pour SSBU et Hogwarts ; le fil de chargement est encore dans le pilote
  49 à 169 s après le début. Le seul chargement terminé est celui d'un petit jeu : 8,18 Mio en 3 052 ms, soit environ
  23 fois plus lent par Mio qu'en 786.
- Les workers reconvertissent et recompilent 89 à 98 % des pipelines SSBU que le fichier contient déjà (157 à 229 ms
  chacun) ; 31 à 52 % des compilations MSL d'une session sont celles du chargement, par le même compilateur que celles
  qu'un dessin attend.
- Trous d'au moins 100 ms : 7 à 47 % du temps de jeu pour SSBU, 28 à 59 % pour Hogwarts ; l'attente d'une compilation
  de pipeline est la première cause partout (jusqu'à 144,5 s sur 388 s pour Hogwarts 820).
- Après chaque fermeture de ces jeux : `Switch still reachable 1/1`, `renderer 1/1`, tas managé 468 à 570 Mo, puis 932
  à 1 273 Mo à la première image de la session suivante, qui démarre à 2,3 à 2,9 Gio d'empreinte au lieu d'environ 1,4.
  La seule session entièrement libérée est celle dont le chargement s'est terminé.

## Correctifs

| Symptôme | Cause | Correctif | Preuve hors appareil |
|---|---|---|---|
| Saccades, cache jamais prêt | MoltenVK compile toutes les bibliothèques au chargement | Recette MoltenVK, neuvième partie : une bibliothèque lue dans les données est compilée à son premier usage, une fois, et conservée | Banc macOS `test/melonx_library_share/run_mapped_cache.py` (paresseux contre contrôle) |
| Mémoire retenue entre deux jeux | L'action de libération du device confiée au fil de chargement capturait le renderer, donc la fenêtre, le Switch et la mémoire de l'invité | `adapt_deferred_release_roots` : action construite par une méthode statique, qui ne capture que ses quatre valeurs | Porte `deferred-release-roots` : 11 sessions fermées pendant leur chargement, 11 retenues avant, 0 après |
| Fermeture de 13 s à plus de 100 s | La vidange de la boucle de rendu détruit les programmes du jeu, et chaque destruction attend les compilations en file | `adapt_guest_stop_compile_cancel` : les compilations qu'aucun fil n'a prises sont annulées dès l'arrêt de l'invité | Porte `guest-stop-compile-cancel` : 220 programmes, vidange 3,4 s avant, 3 à 5 ms après |

La neuvième partie de la recette n'est pas le candidat mesuré et rejeté le 10 novembre (run 42925818096), qui compilait
une bibliothèque Metal par récupération de fonction et n'en gardait aucune.

## Durées de fermeture relevées (entre `guestStopped` et `gpuRelease`)

| Session | Durée |
|---|---|
| Session de 14 s, jeu fermé aussitôt | 7 ms |
| Hogwarts fermé pendant son chargement | 2 ms |
| SSBU, 820 | 4,5 s |
| SSBU, 818 | 13 s |
| Hogwarts, 818 | 42 s |
| SSBU, 819 | 69 s |
| Hogwarts, 816 et 820 | jamais terminée (application tuée après plus de 100 s) |

Dans chaque fermeture lente, la ligne `compilesCancelled` qui suit indique `programs 24` et aucune compilation annulée :
tous les programmes du jeu avaient été détruits pendant la vidange.

## À lire sur l'appareil avec la prochaine IPA

- `pipelineCache primaryReady` : présent dans chaque session, en quelques secondes au plus.
- `RewindBox lazy cache libraries: N compiled at first use in T ms` (journal du pilote) : le nombre de bibliothèques
  réellement utilisées et leur coût.
- `teardown guestCompilesCancelled` puis `gpuRelease` : l'écart doit rester sous la seconde.
- `sessionRetention released` et `renderer 0/1` après la fermeture ; empreinte de départ de la session suivante.
- `pipelineVariants summary` : `ready before their first draw` doit redevenir non nul.

## Non traité dans ce lot

- Hogwarts, session neuve : l'empreinte atteint 4,1 à 4,6 Gio en 60 à 90 s, avec 2,8 Gio de pages de l'invité chez les
  donneurs et une compression intense. Les trims des caches GPU ne sont pas le levier (24 trims pour 528 Mio cumulés
  pendant que l'empreinte montait). Les 22 passes de libération de textures froides n'ont rien libéré : aucune des
  quelque 8 000 textures n'était inutilisée depuis 60 s. Ce que les correctifs ci-dessus rendent n'est pas mesuré.
- La compaction du tas des grands objets (190 à 340 Mio libres) reste soumise à ses seuils actuels.
