# Hogwarts Legacy : log complet, temporisateurs et synchronisation GPU

Le nouveau fichier du 29 octobre contient huit lancements : cinq de Hogwarts
Legacy et trois de Super Smash Bros. Ultimate. Son SHA-256 est
`3aaa4bbc8ca7325cb9e0fc7c328ecb12f206522d92a09ede30620605e8a99b3b`.
Il prolonge le fichier étudié dans le premier audit ; les anciennes mesures
restent historiques. Ni le numéro exact de l'application ni le commit du
moteur exécuté ne sont identifiés dans ce log.

## Ce que les mesures établissent

Les cinq sessions Hogwarts présentent des phases à 1–5 FPS. Dans ces phases,
la médiane de remplissage de la FIFO graphique est toujours de 100 %. La
médiane de CPU du GC .NET, lorsqu'il figure parmi les six threads les plus
actifs, varie de 39 à 60 % d'un cœur selon la session. Le pic du processus
atteint 4 258 Mio, soit 4,16 Gio, dans la deuxième session Hogwarts.

Dans les phases lentes, il reste en médiane 2 812,5 à 3 328,5 Mio de marge au
processus, alors que l'indicateur de mémoire disponible du système est de
9–10 %. Cette différence justifie de distinguer la pression globale du
téléphone, les allocations du moteur et la limite propre au processus.
Aucun échantillon ne signale un état thermique serious/critical. Ces
corrélations ne prouvent ni une cause unique ni un gain du candidat.
La FIFO est une mesure du chemin de commandes ; ce n'est pas une mesure de
l'occupation physique du GPU Apple.

Les correctifs de références de textures, snapshots, plages, caches Vulkan,
attentes, IPC et timers existent déjà dans le Core84 compilé. Ils ne sont pas
réimplémentés ni attribués à cette continuation. Les trois sessions Smash
restent distinctes et ne servent pas à chiffrer les ralentissements Hogwarts.
Le résumé expurgé est dans
`evidence/melonx-hogwarts-timer-20261029/log-summary.json` ; le log privé
n'est pas publié.

## Nouveau changement de production

`KTimeManager.UnscheduleFutureInvocation` retirait chaque armement avec
`List.RemoveAt`. Lorsqu'un même objet avait plusieurs armements avant des
survivants, le même suffixe était déplacé plusieurs fois, avec un coût
quadratique dans les cas denses. Le nouveau traitement conserve le parcours
inverse usuel quand aucun ou un seul armement correspond. À partir du second
match, il compacte les survivants et déplace le suffixe restant une seule fois.

Le verrou, les échéances, l'ordre des survivants, les identités d'armement et
la logique de réveil sont conservés. `RemoveRange` efface les références de
fin de liste. Aucun nouveau champ, cache, objet par annulation ou réglage de
jeu n'est ajouté. Le coût devient linéaire ; le log ne révèle pas le nombre
d'armements annulés par Hogwarts et ne prouve pas que cette fonction domine
le ralentissement.

## Vérification et mesures

Le test compile et exécute la classe de production complète en trois versions :
amont, Core84 exact, candidat. Le SDK est .NET 10.0.100 Linux x64 ; la
compilation par paliers est désactivée pour les micro-mesures. Les limites
simulées sont l'horloge, l'événement d'attente et le conteneur du verrou noyau.

Les trois versions passent chacune 195 scénarios et 103 769 assertions, avec
le même digest fonctionnel. Les tests incluent les annulations répétées et
partielles, l'ordre des échéances égales, la validité d'un armement capturé,
l'effacement des références de capacité, le réarmement avec débordement de
génération et 2 048 callbacks après armements concurrents. Les 24 scénarios
mesurés d'annulation n'allouent aucun octet, comme le Core84. Les 200 000
cycles d'armement/annulation conservent également zéro allocation contre
6 400 000 octets dans l'amont.

Exemples de médianes de cette expérience, **comparées au Core84** :

| Armements | Annulation | Core84 | Candidat |
|---|---|---:|---:|
| 32 | alternée | 244,4 ns | 121,9 ns |
| 256 | moitié initiale | 12 540,3 ns | 411,3 ns |
| 4 096 | alternée | 1 467 550,7 ns | 16 419,2 ns |
| 4 096 | un seul premier élément | 6 526,2 ns | 6 659,9 ns |
| 1 | seul élément | 31,6 ns | 45,0 ns |

Les petits cas peuvent donc coûter davantage. Les processus de comparaison
ne sont pas entrelacés dans un même exécutable ; les nanosecondes sont des
micro-mesures hôte, pas une promesse de vitesse globale. Ce nouveau changement
ne réduit pas davantage les allocations mesurées que le Core84 et ne démontre
aucune économie de RAM résidente. Le reçu conserve toutes les mesures et
leurs contreparties.

## Trois ajustements supplémentaires de la synchronisation GPU

Le mainteneur demande ensuite de chercher d'autres améliorations.
`adapt_sync_allocations.py` ajoute deux sources de production à la préparation.

**Attentes sans demande de flush.** Le callback de `SyncManager.Wait` capturait
une variable locale : le compilateur créait son objet de capture même si aucun
callback n'était finalement nécessaire. La construction du callback est déplacée
dans une méthode privée appelée uniquement lors d'une vraie demande. Le callback
garde son propriétaire et son handle et revérifie le numéro de flush au moment
de son exécution, y compris lorsqu'il est différé.

20 000 attentes d'un handle absent, retiré ou déjà signalé passent chacune de
640 000 à zéro octet alloué dans la fixture. Une demande d'interruption réelle
conserve ses allocations nécessaires : 1 920 000 octets pour 20 000 demandes
dans les deux versions. Aucun verrou, délai de fence ou signal requis n'est retiré.

**Retrait FIFO.** Les handles ne sont ajoutés qu'en fin et retirés qu'en tête.
Une `Queue<SyncHandle>` remplace donc la liste et ses `RemoveAt(0)`. L'ordre,
les deux niveaux de verrou, le retour du tableau de fences effacé au pool et
la frontière du premier handle non terminé restent les mêmes. Le retrait d'un
lot de 256 handles passe de 21,5 à 9,4 µs dans cette mesure hôte ; celui de
4 096 handles passe de 1 830,8 à 157,7 µs. Aucun octet n'est alloué pendant
le nettoyage mesuré, dans les deux versions. Les réservations internes de la
queue restent des allocations nécessaires à sa croissance, hors de cette mesure.

**Vérification des plages utilisées.** `BufferUsageBitmap.OverlapsWith` calcule
les bornes de pages une fois, puis consulte toujours les seize bitmaps. Les
divisions ne sont plus répétées pour chaque command buffer. Une requête sans
overlap passe de 61,60 à 38,00 ns dans cette mesure ; un hit sur le dernier slot
de 62,27 à 37,28 ns. Le hit sur le premier slot régresse de 3,55 à 4,97 ns.
La disposition des bitmaps, leurs bits de lecture/écriture, les calculs entiers
et les invalidations ne changent pas.

Le nouveau corpus compile `SyncManager`, `BufferUsageBitmap` et `BitMap`
complets, avec des frontières de fences/Vulkan simulées. Les deux variantes
passent chacune 219 scénarios et 120 566 assertions avec le même digest.
Un oracle indépendant couvre les pages et les seize slots ; les valeurs
extrêmes sont comparées différentiellement. Les cas incluent interruptions
différées, délais égaux, FIFO après croissance et bouclage, fence en erreur,
attentes concurrentes et nettoyage. Ces expériences n'exécutent pas Metal.

Une préparation fraîche confirme désormais 129 membres adaptés : 126 sont
strictement identiques au Core84 ; les trois sources revues sont
`KTimeManager.cs`, `SyncManager.cs` et `BufferUsageBitmap.cs`. Les 87 entrées
de préparation comprennent un nouvel adaptateur et deux entrées mises à jour
(timer et orchestrateur). Les classes modifiées ont été recompilées et
exécutées dans les tests. La bibliothèque complète et les binaires NativeAOT
Apple ne sont pas encore reconstruits à ce stade du lot source.

## Prochaine compilation du cœur

La recette ne rejoue pas les douze corpus Apple dont les sources sont
inchangées. Elle authentifie leurs reçus contre le contrôle indépendant du
Core84, les empreintes de leurs fichiers et leurs entrées amont. Le corpus
timer modifié et le nouveau corpus de synchronisation seront exécutés sur Apple, suivis de la compilation des
deux bibliothèques, du contrôle des postimages/ABI et des deux sessions SVC.
Neuf contrôles négatifs passent pour le mécanisme de réutilisation : preuve,
index et reçu modifiés, adaptateur, fixture ou source amont modifiés, mauvaise
origine, deuxième changement de préparation et sortie préexistante.

Les anciennes preuves restent intactes. Le Core84 compilé ne contient pas
le nouveau traitement d'annulation. Aucun nouveau cœur Apple, résultat
Hogwarts sur iPhone, IPA ou release n'est annoncé par ce lot source. Les autres
moteurs, notamment RPCS3, ne sont pas modifiés.

Preuves : `evidence/melonx-hogwarts-timer-20261029/`.
