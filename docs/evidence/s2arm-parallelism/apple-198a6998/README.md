# Seconde série · GPU Apple paravirtualisé

Le [deuxième run Apple](https://github.com/TarbleFR/RewindBox/actions/runs/46027760908) a répété les 2 880 images et la vérification des 720 marqueurs d’image hors chronométrage. Les deux séries emploient la même charge graphique. La variation entre hôtes est assez forte pour écarter le choix d’une profondeur de jeu à partir de ces seules mesures.

| Profondeur | Images GPU terminées/s | Préparation CPU recouverte par du travail GPU antérieur | Demande à callback p95 / p99 |
| --- | ---: | ---: | ---: |
| 1 | 1 034 | 0 % | 3,06 / 9,60 ms |
| 2 | 2 236 | 76,03 % | 2,57 / 6,12 ms |
| 3 | 3 117 | 90,51–90,59 % | 2,89 / 4,47 ms |
| Adaptative | 3 179 | 91,19–91,46 % | 2,04 / 5,45 ms |

Les 16 lots indiquent à nouveau 23 166 976 octets alloués par Metal en fin de mesure. Les bras incluent tous les mêmes trois surfaces. [Échantillons](frames.csv.gz) · [Synthèse des 16 lots](summary.csv) · [Couverture avec toutes les commandes antérieures](any-prior.csv).

## Rejeu moteur

Avec le découpage dynamique habituel, les 35 processus obtiennent les mêmes empreintes de pixels et d’état des dessins. Les sept traces de diagnostic détaillées conservent exactement les mêmes dessins, dispatchs et opérations de synchronisation. Un des quatre tours chronométrés avec worker seul a rouvert une passe de rendu, déclenchant deux opérations de synchronisation supplémentaires sur trois images. L’assertion de stabilité du compte brut a donc échoué. Cette variation est conservée dans le rapport. Le test d’arrêt GPU a réussi sur une vraie file Metal 3 et le test de l’encodeur a réussi ses sept assertions avec et sans publication anticipée.

[Temps de rejeu, quatre tours par bras](replay-quantiles.csv) · [Trace de référence](trace-baseline.json) · [Trace des options combinées](trace-combined.json). Les deux traces peuvent être ouvertes dans Perfetto. Les trois images mesurées sont séparées par un `QueueFinish` invité. Le GPU de N ne chevauche pas la préparation de N+1 dans les paires résolues de ces traces.

Dans le bras de référence avec instrumentation, le p99 interpolé atteint 687 ms sur seulement douze images chronométrées. Conserver le témoin sans trace dans chaque essai physique et publier les observations individuelles. Le coût du formatage sur Linux exclut le délai des callbacks et de sortie du journal sur Apple.

La répétition 2 du témoin instrumenté contient deux images à 740,019 et 261,952 ms. Les intervalles de command buffers GPU en couvrent respectivement 649,936 et 253,875 ms, soit 87,8 % et 96,9 %. La préparation du fil soumissionnaire y compte 2,948 et 2,327 ms de temps CPU. La troisième image revient à 5,658 ms. Ces timestamps ne séparent pas une pause du GPU virtuel, l’ordonnancement de l’hôte et le coût d’écriture du journal. Le pic reste dans les quantiles publiés.
