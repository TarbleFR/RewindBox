# Expérience de partage des fragments bruts : retirée

`rpcs3/Emu/RSX/rsx_cache.h` a été restauré à l'empreinte de la base `a363d923` :
`0c0d35e06ca3599dffb09f272bc8e656c84ceb08b516d74abb0b5476668c9573`.
Aucune de ces variantes n'est intégrée au patch produit. Les trois changements
retenus dans les décompilateurs restent distincts et ont leurs propres preuves.

Le code charge effectivement un fichier FP par entrée de pipeline au démarrage.
L'expérience visait à réutiliser un payload immuable déjà chargé dans la même
phase, en conservant les paramètres de chaque pipeline, le vrai hash du microcode
FP, les propriétaires `lf_fifo` et la fin de vie après la jointure des workers.
Les tests utilisent de vrais fichiers temporaires ; leurs répétitions sont
construites, car les fichiers de cache des trois jeux ne sont pas disponibles.
Le compilateur GPU est une frontière adaptée : il vérifie une copie propriétaire,
il ne compile pas du GLSL. Le hash VP est aussi adapté ; le hash FP est extrait
sans modification de la production.

| Variante | Fixture | Empreinte du candidat `rsx_cache.h` | Conclusion |
| --- | --- | --- | --- |
| 64 slots partagés, mutex bloquant, validation FP répétée | `shader-raw-preload-initial.diff` | `90b9f4360b3c6aa125f013b853c5b5f40ab13b56b6d714ba2e36200c2fdb1b1f` | Réduit fortement les lectures répétées ; sérialise les collisions ; cas unique également plus lent. |
| Slots partagés avec `try_lock`, repli sans attente, preuve du hash réutilisée | `shader-raw-preload-revised.diff` | `22d50884cd9aba3009d15c493161626987bd25aee01d0defa7ba621fa09c733c` | Sept mesures alternées : médianes collisions à huit workers +8,5 %, uniques à huit workers +5,6 %. |
| 64 slots privés par invocation de worker, aucun verrou | `test/fixtures/rpcs3_shader_raw_preload_experiment.diff` | `7d84d9c83c49dfadefb406b83a1a927738b6a465ab8cd72a7cf6a7f0593220ea` | Doublons plus rapides, mais uniques à huit workers +15,5 % dans la médiane hôte ; retiré. |

Pour la dernière variante, 256 occurrences du même payload de 8 Kio passent de
256 lectures à une lecture avec un worker, à huit lectures avec huit workers
(dans la mesure conservée). Le scratch de payload passe respectivement de 2 Mio
à 8 Kio ou 64 Kio. En revanche, les 256 payloads distincts conservent 256 lectures.
La médiane à huit workers passe alors de 2,03 à 2,34 ms. Les plages de temps se
recouvrent et l'hôte est variable ; il n'existe pas ici de résultat sur iPhone.

Les tests ont vérifié 4 096 résultats d'enregistrements, les propriétés par
pipeline, les erreurs de fichier absent/tronqué/surdimensionné/hash incorrect,
les collisions, les passages répétés, l'annulation et l'équivalence desktop.
Le harnais final compile les méthodes réellement modifiées, les méthodes de
lecture et `unpack`, le hash FP et les structures de propriété. Les fonctions de
lancement des workers et la façade de fichier utilisent le C++ hôte. Aucun passage
ASan/TSan n'est revendiqué pour ces candidats retirés.

La version partagée pouvait faire davantage de lectures qu'un plafond égal au
nombre de workers : une collision sur un slot prêt suffit aussi à déclencher le
repli `try_lock`. Cette hypothèse de test a été corrigée. Les erreurs initiales
d'adaptateur (`umax` et parcours de capacité `lf_array` au lieu de taille logique
`lf_fifo`) sont également consignées dans le registre. Aucun garde produit n'a
été désactivé.

Reproduction volontaire du dernier candidat, sans modifier les sources fournies :

```sh
python test/rpcs3_shader_raw_preload_test.py /path/to/core-from-a363d923 \
  --baseline /path/to/core-from-a363d923 \
  --candidate-from-fixture test/fixtures/rpcs3_shader_raw_preload_experiment.diff \
  --report /tmp/shader-raw-preload.json
```

Le script copie ses quatre entrées dans un répertoire temporaire et y applique
la fixture. Les deux autres fixtures peuvent être fournies à la même option ;
les sources des variantes ont été reconstituées et leurs empreintes vérifiées
sans nouvelle compilation. Les rapports initiaux restent des mesures de leurs
programmes initiaux ; le harnais final ajoute les sept échantillons alternés.

La décision repose sur les mesures défavorables et l'absence d'inventaire réel
permettant de justifier le compromis. Elle ne signifie pas que toute déduplication
au démarrage est impossible. Pour rouvrir cette piste utilement, il faut connaître
la multiplicité et l'ordre des payloads du cache du jeu, puis vérifier qu'un
candidat améliore les cas uniques et répétés sur ARM64.
