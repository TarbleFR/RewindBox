# RPCS3 : suites des essais BO2, GOW3 et Assassin’s Creed du build 601

Ce travail reprend `Claude` à `f41eb5ef4ce87cab08a18781c2e09a55a8319773`.
Le core de référence est `378509e82d360bc2cb2fcc9fb23d4d9d98787506`,
compilé et vérifié dans le run `41033511090`, livré dans 601 puis conservé
dans 602/603. L’amont reste `22f1152783cef1f7e04af7b1c895173e28fd5b03`.
Le patch canonique est `b3d70ba67af95196d44f872baf1f19ae0cc3deba9cc67a5a124e1c0098126ff2` :
325 postimages vérifiées sur un nouvel arbre propre, une modifiée et 324
strictement conservées. ABI 30, 88 exports et codegen PPU/SPU restent inchangés.
Les résultats ci-dessous ne sont pas une mesure du nouveau code sur iPhone.
Aucun push, lancement de CI, nouveau core, IPA, tag ou release n’est effectué.

## Mesures des pièces reçues

Les dix fichiers sont authentifiés dans [device-log-summary.json](evidence/rpcs3-device601-20261030/device-log-summary.json).
Le script [analyze_rpcs3_device601_logs.py](../build-utils/analyze_rpcs3_device601_logs.py)
lit les générations retenues, dédoublonne les événements miroirs et sépare
les processus, titres et fenêtres. Les anciens logs 595/597 ne sont jamais
traités comme des mesures 601. Les changements de mode internes à BO2 sont
distingués grâce aux numéros de session du core.

| Jeu / passage | Vérification sur iPhone dans les logs reçus | Limite d’attribution |
| --- | --- | --- |
| BO2, PID 55099, session 1 | Fenêtre 3 : médiane 16,679 ms, p99 266,648 ms, maximum 694,915 ms. Fenêtre 4 : p95 35,350 ms, maximum 583,611 ms. | Les images peuvent inclure une transition de phase ; ce n’est ni une moyenne de gameplay ni un gain comparé aux anciennes versions. |
| BO2, passage multijoueur | Redémarrage interne vers `t6mp_ps3f.self`, puis session 2 en préparation sans image ni activité PPU/SPU. Les demandes de compilation Metal continuent. | Un blocage définitif du lifecycle n’est pas démontré. Ne pas confondre avec les anciens stalls de compilation graphique en gameplay. |
| AC, PID 55119, session 1, fenêtre 35 | 27,240 FPS sur toute la fenêtre, p95 51,945 ms, 11/143 intervalles au-delà de 50 ms. | Aucune mesure du nouveau code, aucun temps GPU, aucun draw associé aux torches. D’autres fenêtres dépassent 30 FPS ; la scène n’est pas alignée avec les essais antérieurs. |
| GOW3, PID 55119, session 2 après AC | 101,299 s observées après le début du boot, sans retour de boot ni image. VMA existe ; 673 demandes de compilation Metal à priorité par défaut. Marge mémoire minimale proche de 5,27 Gio. | Préparation synchrone du cache pilote fortement étayée ; aucune preuve de deadlock. Le gel historique de l’introduction sur label RSX est un incident séparé. |

Références BO2 : `RPCS3-performance.1.log:2576,2617`,
`RPCS3-diagnostic.1.log:2184,2246–2254`. AC :
`RPCS3-performance.log:627–907`, `RPCS3-diagnostic.log:600–953`.
GOW3 : `RPCS3-milestones.log:415–419`, `RPCS3-diagnostic.log:1496–1511`,
`RPCS3-performance.log:1350–1994`.

AC sollicite encore la préparation des textures et des draws : environ
2 500 draws par image, textures échantillonnées autour de 6–8 ms, setup
autour de 4–5 ms. Les fenêtres lentes examinées n’ont pas de compilation de
pipeline, le préhash est inactif et le hash synchrone comptabilisé vaut zéro.
Les échantillons thermiques AC retenus valent zéro ; le headroom ne
justifie pas d’augmenter les budgets. Les temps de stages et attentes se
chevauchent et ne doivent pas s’additionner.

Les événements `RENDERCAUSE` retenus sont tous nuls pour BO2 et AC.
Ils n’établissent ni la cause des défauts visuels ni l’absence d’un défaut.

## Correction réelle : petits blocs du cache de sommets

Le `weak_vertex_cache` ignorait entièrement les modifications des uploads
de un à sept octets. Ce chemin est atteignable avec les attributs constants
à un seul sommet. Sur iOS, une empreinte bornée vérifie maintenant tous les
octets de ces petits blocs sans dépasser leur plage. Les blocs plus grands
conservent leur préfixe de huit octets ; aucun hash intégral n’est ajouté.

Le test extrait le cache de production complet : 28 réutilisations périmées
avant correction, zéro après, 219 contrôles et pages protégées en mode normal
et ASan/UBSan. Le chemin hors iOS est inchangé. La régression existante des
plages de sommets est rejouée car son entrée a changé : 1 656 cas dans les
deux modes. Voir [les preuves et limites](evidence/rpcs3-device601-20261030/renderer/tiny-vertex/README.md).
Cela corrige un défaut de source ; le lien avec les armes de BO2 ou les
torches d’AC n’est pas établi.

## Continuité et pistes écartées

Les corrections MFC/interruptions/late-SNR, DMA/MMIO, ownership GPU,
revalidation des samplers, plages de sommets, vues temporaires et copies
de textures précédemment livrées sont conservées. La relaxation des
réservations SPU et les réglages officiels AC sont déjà actifs. Aucun gain
historique n’est présenté une seconde fois comme une nouveauté.

L’import synchrone du cache MoltenVK compile les bibliothèques Metal avant
`SHADERCFG528`. Le cache est déjà séparé par exécutable. Les notices
existantes du cache pilote sont filtrées par le pont hôte ; le dernier boot
GOW3 ne fournit pas leurs bornes début/fin. Réutiliser un `VkDevice` entre
renderers exigerait un changement de propriété et de destruction des
swapchains ; cela n’est pas retenu comme un correctif isolé prouvé. Aucun
cache n’est purgé et aucune attente invitée n’est contournée.

BO2 charge déjà ses objets SPU : 7 474 lectures, 1 931,553 ms cumulées,
7 454 chargements et seulement 19 codegens dans la fenêtre examinée.
`spu_build` inclut les lectures et l’admission ; ces durées ne s’additionnent
pas. Une expérience de réutilisation de l’inflater zlib a été rejetée :
économies de 38–339 ns sur les objets synthétiques de 3 Kio, régressions
jusqu’à 8,69 % sur d’autres cas. Elle ne justifie ni mémoire résidente
supplémentaire ni changement d’identité des caches.

Une seconde expérience a testé un masque des samplers actifs pour réduire
les parcours de vingt slots lors des invalidations. Les 2 040 084 contrôles
d’équivalence et les publications concurrentes passent, mais le cas plein
régresse de 12,01 à 24,14 ns et des scénarios mixtes ralentissent aussi.
Le helper a été restauré exactement ; aucun masque supplémentaire n’est
livré. Le prototype et les mesures défavorables sont conservés dans
[withdrawn-sampler-mask](evidence/rpcs3-device601-20261030/withdrawn-sampler-mask/).

Le hash intégral des sommets, l’activation aveugle du préhash AC, la
suppression de barrières, le forçage du label GOW3, les budgets augmentés,
le batching général des submits et la décompression réutilisée ne sont pas
réintroduits.

## Validation suivante

Le [contrat source ciblé](evidence/rpcs3-device601-20261030/gate/README.md)
vérifie les 325 postimages et rejette neuf corruptions contrôlées. Les
sources physiques des identités PPU `a987639e9f838d1c` et SPU
`477a3fa442d27917` sont conservées, ainsi que les 88 exports. Le workflow
et la recette de compilation restent inchangés ; un nouveau dispatch local
au validateur prépare seulement quatre jobs Apple concernés par ce fichier.
Ces jobs ne sont pas exécutés dans ce travail. Les 28 modes Apple historiques
restent liés à leur source d’origine. Leur résumé est authentifié localement ;
les archives brutes seront obligatoires avant un futur préflight natif.

Les essais Apple des seuls chemins modifiés, puis les mêmes parcours sur
iPhone restent nécessaires. Les tests hôtes ne résolvent pas à eux seuls le
gel multijoueur, l’introduction GOW3 ou les torches AC. Les optimisations
suivantes doivent cibler le coût de préparation actif des textures, les
chargements d’objets SPU réellement coûteux et la préparation du cache pilote
en distinguant ce boot du gel historique. Aucun FPS supplémentaire n’est
revendiqué.
