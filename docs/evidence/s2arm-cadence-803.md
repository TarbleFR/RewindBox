# S2Arm : cadence native, accélération ressentie et variations de charge

20 novembre 2026. Audit des nouveaux exports `engine(2).zip`, `profiles(2).zip`
et `s2arm-journal(3).jsonl`, après le retour du mainteneur sur la lenteur, les
à-coups selon le décor et une impression de vitesse 1,25× dans Fire Emblem.

## Résultat et périmètre

Le patch **0170** retire une cause établie de cadence incorrecte : un manifeste
générique `fps60_display=1` suffisait à ignorer l'intervalle demandé par le jeu,
sans table de compensation de vitesse. La correction porte sur le consommateur
du moteur : elle couvre les modules déjà préparés et futurs, sans préparation
supplémentaire ni réécriture des caches.

L'accélération exacte de la simulation n'est pas mesurée. Les variations de
charge GPU et les attentes de producteurs invités sont réelles et distinctes ;
ce correctif ne prétend pas rendre toutes les scènes à 60 FPS. À ce stade :
source corrigée et revue, compilation et livraison à authentifier, résultat sur
iPhone non mesuré. Maturité conservée à **55 %**.

## Identités et méthode

Les exports contiennent plusieurs versions ; ils ne forment pas une seule
session. La synthèse reproductible est dans
[cadence-summary.json](s2arm-cadence-803/cadence-summary.json). Elle ne contient
ni journaux bruts, ni chemins privés, ni identifiants de session ou adresses
invitées. [summarize_cadence.py](s2arm-cadence-803/summarize_cadence.py) utilise
l'analyseur existant `tools/s2arm_prototype/shader_session_metrics.py` ; c'est un
outil d'analyse des captures, pas une suite de tests du moteur.

| Capture | Identité attestée | Limite |
| --- | --- | --- |
| Mario Kart World, GID `0400C3F00006E000` | IPA 802, moteur run `44746620489`, build jeu `9e244438c3d8ef1c703a6a85ef99c4f0` | Scènes et circuits sans annotation synchronisée ; pas de comparaison contrôlée avec 801 |
| GID `04007EF01F8AE000` | Moteur run `44729718541`, livré dans la 801 | Association à Fire Emblem plausible au vu du retour, mais nom commercial absent des exports ; pas de champ appBuild propre à cette session |
| GID `040041E0212AE000` | Moteur historique run `44230830821` | Ne pas traiter cette session du 18 novembre comme une 801 ou 802 |

Les trois profils CPU récents appartiennent au second GID et au moteur de la
801. Aucun profil CPU de la session MKW 802 n'est fourni ; ses deux captures GPU
bornées sont présentes dans son journal moteur.

Empreintes des entrées :

| Fichier | SHA-256 |
| --- | --- |
| engine(2).zip | `7f9979ab2d793d5dcbf7800327ecf96ed3d89b285656e96112f034ce5a1a5b8c` |
| profiles(2).zip | `2dd97f7cef57b9de255b19578f5d0c68e82c11f8f23c9a46e8505cbc995b7225` |
| s2arm-journal(3).jsonl | `4c385e5b63fcf8e37dce0dcbe6f4640bcbbf51646a00563b75c77553c06bf810` |

## Constat : 30 demandées, près de 60 présentées

Le second GID passe à l'intervalle **2 dès la frame 7**, puis le conserve. Sur une
base 60 Hz cela demande une période de 33,33 ms. Le moteur reste cependant en
mode `display` et ne retient aucun tick pour cet intervalle. À la fenêtre F900,
les compteurs connaissent 300 demandes à 33,33 ms alors que l'affichage atteint
59,994 FPS. Aux frames 5701–6000, les 300 intervalles moteur couvrent 4,999455208 s :
**60,0065 FPS**, p95 17,21 ms et p99 17,50 ms ; l'affichage est à 59,795 FPS,
p99 16,67 ms. Le p95 écran et sa durée exacte ne sont pas enregistrés par la 801.
Le phénomène existe aussi dans des fenêtres 3D, pas seulement dans un écran vide.

Les lignes de capacités indiquent une source générique, sans `game.tsv`, ni
table FPS ou correction dynamique de pas identifiée. `native/s2arm/prepare/s2arm_caps.c`
écrit ce drapeau quand il ne trouve ni `fps.tsv`, ni patch communautaire FPS,
ni reconnaissance du moteur. Les registres de validation par jeu ne sont pas
présents dans cette préparation sur téléphone. `runtime/src/caps.c` acceptait
ensuite ce drapeau comme une source de mode `display`.

MKW 802 utilise la même règle. Sur les frames 1–6400, le jeu demande 5289 fois
l'intervalle 1 et 1111 fois l'intervalle 2, avec 534 transitions. La demande ne
change pourtant pas sa cadence effective en mode `display`. Les comptes des
échéances écran sont différents : ils prennent le maximum des deux holds
adjacents, avec des callbacks retardés ; ne pas les confondre.

Un jeu dont la simulation avance par image peut accélérer dans ce mode. Ces
compteurs démontrent le contournement de l'intervalle ; ils ne mesurent pas un
rapport de temps de jeu égal à 1,25×, ni une vitesse double.

## Ce qui explique encore les à-coups et les décors plus lents

MKW 802 : **6400 intervalles**, sans trou interne ni perte déclarée, sur
186,11095 s ; **34,388 FPS moteur**, p95 53,137 ms, p99 101,899 ms ;
69 / 18 / 6 intervalles dépassent 100 / 200 / 500 ms. L'indice d'assets de
séquence de course couvre 4355 intervalles et donne 31,012 FPS, mais ne certifie
ni le circuit ni une conduite continue. Aucun gain 801→802 n'est attribuable
à ces seuls parcours non appariés.

| Fenêtre de 300 frames jusqu'à | FPS écran | Écran p95 / p99 | GPU médian |
| --- | ---: | ---: | ---: |
| F3300 | 38,120 | 33,336 / 66,673 ms | 10,99 ms |
| F3900 | 21,580 | 58,339 / 100,009 ms | 34,71 ms |
| F6300 | 22,037 | 66,673 / 83,341 ms | 39,58 ms |

CPU et GPU se chevauchent : leurs temps ne s'additionnent pas. Les fenêtres
GPU à 35–40 ms ne peuvent pas tenir le budget de 16,67 ms par un seul réglage
de cadence. La capture GPU F3602 comporte notamment une passe de rendu de
559 dessins à 1248×700 ; ce n'est pas seulement un filtre de présentation.
Les captures sont ponctuelles et peuvent perturber la mesure.

Sur 461 lignes de longues frames après F2046, les attentes directes de file de
présentation, drawable, fence GPU et slots d'upload sont arrondies à 0 ms. L'attente
display-link est positive seulement cinq fois (25 ms cumulées, maximum 11 ms).
Ce relevé est biaisé vers les longues frames, mais ne montre pas de sommeil
artificiel systématique expliquant les cas observés.

À F3972, l'intervalle atteint 722,399 ms, dont 714,588 ms dans l'attente invitée.
La trace sépare **714,582 ms avant le choix du réveil**, puis **0,006 ms jusqu'au
retour**. La médiane de ce second délai sur 61 traces est de 0,007 ms. Le temps
principal est donc chez le producteur avant son signal, pas dans un thread déjà
réveillé que l'ordonnanceur retiendrait longtemps. À F2814, une autre attente
atteint 999,014 ms ; les scènes peuvent inclure chargements et transitions.
Supprimer cette synchronisation ne constitue pas une correction valide.

Les 1817 retards dont le GPU termine avant l'échéance *dérivée* ne prouvent pas
une erreur de présentation : cette échéance n'est pas celle demandée au
drawable. Aucun rattrapage massif après les pauses n'est établi. Le chemin
CAMetalDisplayLink conserve `present()` : les variantes programmant une heure
ou une durée ne sont pas appropriées pour ses drawables.

Le second GID termine, avec le moteur de la **801**, sur un timeout GPU à
F23941 (`MTL4CommandQueueErrorDomain`, arrêt protégé 86), avec état thermique 2.
Sa cause n'est pas établie. MKW 802 n'a pas ce timeout dans l'export ; ses
états thermiques observés sont 0 puis 1. Ne pas attribuer cet arrêt à la 802,
ni prétendre le corriger en retirant le déblocage générique.

## Correctif 0170 et compatibilité

[0170-respect-game-cadence-with-generic-fps-caps.patch](../../build-utils/s2arm/engine/patches/0170-respect-game-cadence-with-generic-fps-caps.patch)
modifie uniquement `runtime/src/caps.c` et le commentaire de `caps.h`.

- Une capacité de présentation issue du manifeste générique n'active plus le
  mode `display`. La provenance est fournie par le point d'appel, sans analyser
  un commentaire humain localisé.
- Une capacité explicite de patch `[caps]` ou `[except]` reste reconnue ; les
  priorités existantes empêchent le manifeste de l'écraser, et le reset efface
  toujours l'état de session.
- `fps60=1` reste disponible pour les tables FPS et patches qui en dépendent.
  Les profils de jeu, le frame-step, les overrides explicites, l'opt-in existant
  `fps60=0` + environnement `S2A_FPS60=1` et le plafond utilisateur sont conservés.
- Un ancien import dont la seule autorisation était `fps60_display=1`, même
  accompagné d'une mention A/B verte dans son commentaire, revient à la cadence
  native. Le format ne fournit pas de provenance structurée permettant de
  distinguer ce cas du défaut générique. Aucun import de ce type n'est établi
  dans les sessions étudiées. Les profils dérivés gardent leur politique
  existante ; ils ne sont pas tous validés par une mesure L3.

Les calculs de temps, la résolution, les barrières, les fences, les données du
joueur et le budget textures de **192 Mio** restent identiques. La période finale
est calculée une fois : intervalle 2 + plafond 30 = 33,33 ms. Le lien traduit
ensuite cette période en 2 ticks à 60 Hz ou 1 tick à 30 Hz ; pas de 30→15.
Le sommeil absolu du pacer est un repli en cas d'échec du tick, pas une seconde
attente systématique. La stabilité d'une seconde et le profil MKW 0115 évitent
de reconfigurer le lien à chacun des changements d'intervalle.

## Chronologie et vérifications

L'IPA 790 embarquait le moteur `0c02786c` / run `44321233097` (119 patches),
la 791 le moteur `575a8cc3` / run `44390398925` (120 patches). Les 119 patches
communs sont identiques par SHA-256 ; 0120 changeait le titre résolu. La règle
générique, les formules d'intervalle et le générateur natif existaient déjà en
790. Aucun coefficient 1,25 de vitesse invitée n'a été trouvé. Que l'accélération
devienne plus perceptible lorsque le moteur atteint plus souvent 60 reste une
interprétation plausible, pas un gain avant/après démontré.

Revue indépendante de la provenance, des appels, priorités, resets et chemins
de cadence : aucun blocage trouvé. Application de 0170 vérifiée sur le moteur
complet 0001–0169. Aucun nouveau test de moteur ou benchmark ajouté ; compilation
iOS et contrôles de livraison requis. Le défaut latent de fréquence de ticks
entre jeux Switch 2 puis Switch 1 n'est pas inclus : le pont actuel impose un
redémarrage pour changer de jeu, et ce défaut n'explique pas les sessions reçues.

La prochaine preuve utile est une nouvelle session du même passage avec le
moteur corrigé : cadence demandée/effective cohérente et vitesse ressentie normale.
Le budget GPU, les producteurs des attentes longues et le timeout du second GID
restent des limites distinctes, sans promesse de 60 FPS constants.
