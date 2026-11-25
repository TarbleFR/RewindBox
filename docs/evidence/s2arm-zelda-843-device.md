# Zelda 843 : compilations résiduelles et cadence à chaud

Relevé du 25 novembre 2026, titre `0400486024DEC000`, A18 Pro selon le contexte
du mainteneur. **Les gros gels de compilation sont réels ; une recompilation en
boucle de la même roulade n'est pas établie. Même sans nouvelle attente de pipeline
mesurée, une plage de 63,326 s reste à 23,687 FPS moteur.** Aucun nouveau correctif,
réglage, moteur ou IPA dans cette analyse.

Le mainteneur rapporte un gel ressenti à chaque action, notamment les roulades
déjà répétées. Ce ressenti est conservé comme observation, sans le transformer
en corrélation action/pipeline que les captures ne permettent pas d’établir.

## Sources et méthode

Archives privées fournies : `engine.zip` et `profiles.zip`, déjà extraites au moment
de la reprise. Le journal Zelda `host.log` fait 3 928 368 octets, SHA-256
`29b4af3d45bda62caeddc8c4cfb3bc5d1e7839aae24b1890f0cc6797fd18abe8`.
Les [mesures structurées](rewind843/device-observations.json) conservent les
empreintes des fichiers effectivement lus, les numéros de lignes du journal et
les 26 fenêtres d'intervalles. Aucun journal privé brut n'est ajouté au dépôt.

Le mainteneur identifie l'IPA 843 ; le journal contient le marqueur du patch 0397
et correspond à la seconde série de profils, `20261125-163104-f3586`,
`163134-f3996`, `163204-f4262`. Il ne contient pas l'empreinte du binaire installé.
La première série (`162409-f1468`, `162443-f1841`, `162545-f2081`) provient d'une
autre session ; son journal complet n'est pas présent. Les anciens journaux
de la ZIP ne sont pas utilisés comme ceux du premier lancement de la 843.
Les heures des noms sont conservées sans conversion de fuseau supposée.

Les six captures CPU durent environ quatre secondes chacune ; elles ne forment
pas six essais de 180 s. Les captures `frames.txt` sont des anneaux qui se
recouvrent : dédoublonnage par numéro d'image, champ 18 (microsecondes jusqu'à la
première commande suivante), valeurs positives seulement. Aucun conflit ni trou
entre les intervalles retenus dans chaque série :

| Série partielle | Intervalles | Durée cumulée | Plus long intervalle | >100 / >500 ms |
|---|---:|---:|---:|---:|
| Première, images 685–2320 | 1636 | 352,453 s | 91,330 s | 95 / 61 |
| Seconde, images 2803–4501 | 1699 | 87,635 s | 9,276 s | 51 / 11 |

Ces plages mélangent chargement, menus et jeu, avec des parcours non appariés.
Elles ne mesurent pas un gain avant/après. Sans journal de la première session,
la pause de 91,330 s ne peut pas être attribuée précisément à la compilation.
Les signatures de commandes ne sont pas une comparaison de pixels.

## Ce que le cache réutilise réellement

Le second lancement inventorie **1599 pipelines, 382,0 Mo** (ligne 329).
Au bilan du préchauffage (lignes 11082–11094) :

| Mesure | Observation |
|---|---:|
| Créations depuis une archive valide | 1205 / 1289, soit 93,48 % |
| Pipelines compilés | 84 |
| Archives périmées rejetées | 76 |
| Écritures au dernier instantané / encore en file | 78 / 0 |
| Évictions rapportées par `RB-PSO-CAP` | 0 sur les cinq rapports |
| Clés à retraduire depuis l'ancien traducteur | 394 |
| Appels de compilation MSL depuis la source, tous fils | 1347 ; 135 291,5 ms cumulées |
| Chargements de shaders | 5464 demandes, 3518 succès du cache mémoire, 601 attentes partagées, 1345 constructions, 0 échec |

Les 135,292 s sont une somme de durées d'appels sur plusieurs fils, **pas un gel
unique ni du temps CPU**. Les archives PSO et les bibliothèques MSL sont deux
couches différentes : une archive PSO réutilisée n'exclut pas un appel de création
de bibliothèque en amont. Le diagnostic `rb-compile-origin` n'est pas actif ;
une durée d'appel ne prouve pas à elle seule une éviction du cache système iOS.
Celui-ci est annoncé à 550,3 puis 585,2 Mo, sans preuve de saturation.

La migration du traducteur n'est donc pas achevée avant tout dessin dans cette
session à chaud. Le préchauffage reste en arrière-plan pendant 293,974 s et
des premières utilisations attendent encore ses résultats. Le journal contient
1345 chargements de traduction de secours pour 1345 clés distinctes. Les quatre
attentes de première utilisation détaillées ont quatre clés différentes ;
elles sont filtrées et ne couvrent pas les 106 événements du compteur à l'image
7500. Sans horodatage de la roulade ni journal complet de la première session,
impossible d'affirmer que cette action recompile exactement le même pipeline.

**Rectification de la piste donnée avant réception des fichiers :** le dossier
d'archives ne contient effectivement pas `xfp` dans son identité, mais les
résultats sont contrôlés par `FailOnBinaryArchiveMiss` et les entrées encore
compatibles restent utiles. Cela ne justifie pas de purger les 1205 succès.
L'analyse limitée au patch 0127 omettait le
[patch 0268](../../build-utils/s2arm/engine/patches/0268-drain-gameplay-archives-and-prioritize-registered-pipelines.patch)
(voie d'écriture jusqu'à Serious sous condition de marge mémoire) et le
[patch 0302](../../build-utils/s2arm/engine/patches/0302-serve-registered-pipeline-rows-through-thermal-holds.patch)
(préparation des programmes enregistrés malgré la suspension spéculative).
Ici, des écritures réussissent et aucune ligne de refus pour budget d'archive
n'apparaît. Les 78 écritures et la file vide sont un instantané, **pas une preuve
que les 84 compilations sont toutes persistées**, ni que six seraient perdues.
Le blocage complet du writer précédemment envisagé n'est pas confirmé.

## Les gels et les ~20 FPS ont des causes distinctes

À l'image **4134**, le journal relève **9279,0 ms** pour l'image, dont
**8541,2 ms** au poste pipelines/bibliothèques (10 pipelines et 4 bibliothèques),
aucun upload, GPU 46,5 ms (ligne 5442). Deux attentes de résultats déjà en cours
atteignent 2854,0 et 2309,5 ms. Ces postes se recouvrent : ne pas les additionner.
Les images 4068, 7292 et 7531 montrent aussi de gros gels liés aux compilations.

| Mesure | Jeu avec gels, images 3601–7500 | Plage sans nouvelle attente PSO, 4201–5700 |
|---|---:|---:|
| Intervalles / durée exacte | 3900 / 207,886157 s | 1500 / 63,325950 s |
| Cadence moteur, intervalles / durée | 18,760 FPS | **23,687 FPS** |
| Cadence présentée, rapports de 300 images | 9,4–24,7 FPS | 22,4–24,4 FPS |
| Cadence visible, rapports d'horodatages d'affichage | 8,846–24,708 FPS | 22,451–24,506 FPS |
| Vitesse `[rb-speed]` | 15,6–41,1 % | 37,3–40,7 % |
| GPU p50 des fenêtres | 28,74–32,88 ms | **29,69–32,44 ms** |
| Attente d'allocateur cumulée / par image | 42 682,489 ms / 10,944 ms | **13 931,834 ms / 9,288 ms** |
| Images >100 / >500 ms, compteurs complets | 41 / 16 | 0 / 0 |
| Nouvelles attentes PSO mesurées | 52 / 8910,8 ms | **0 / 0 ms** |

Pour la plage 4201–5700, `demand=91`, `demand_ms=8053.3` et `prepared=995`
restent constants. Les **494 images longues détaillées** de cette plage
rapportent zéro nouveau pipeline et zéro bibliothèque. Le coût de soumission
CPU reste à 19,389–20,141 ms/image ; le mode `rb-alloc-frame` est désactivé.
Les attentes d'allocateur peuvent refléter le retard du GPU : elles ne sont pas
des millisecondes à soustraire automatiquement à son temps.

L'état thermique est Serious sur cette plage, mais la sonde GPU fixe reste à
0,213–0,282 ms : le journal ne démontre pas un effondrement de fréquence comme
cause unique. La scène rapportée est 854×480, l'intervalle invité vaut 1,
l'horloge invitée 1,000 s/s, sans attente de pacing ni interpolation.
La pleine vitesse n'est pas atteinte. Réduire les compilations supprimera des
gels ; cela ne suffit pas à promettre 60 FPS avec ce budget CPU/GPU.

## Résultat et limites

L'analyse confirme deux travaux distincts : préparation des traductions,
bibliothèques et pipelines avant leur première utilisation bloquante ; réduction
du coût permanent CPU/GPU et des attentes d'allocateur. Elle ne justifie ni
suppression des caches, ni nouveau changement d'empreinte, ni activation de
plusieurs options simultanément. Les optimisations 0394–0399 restent livrées ;
leur gain causal n'est pas mesuré par ces sessions non appariées.

Documentation et données dérivées uniquement : aucun test ajouté ou exécuté,
aucune compilation, aucun nouvel essai sur iPhone. Replay pixels Zelda/MKW/Fire
Emblem et A/B 3 × 180 s non exécutés. Maturité de suivi inchangée à 50 % ;
l'observation Zelda ne valide pas le parcours Mario Kart World de référence.
