# S2Arm — contre-expertise CPU et mémoire, 27 novembre

Référence `5b7263243`, série jusqu’à 0479, moteur épinglé `6b6a5715`. Périmètre revu, patchs 0472–0476 et 0479.

## Défaut reproduit et corrigé

`CreateTransferMemory` relâchait `G` après le contrôle du quota, puis empruntait la plage mémoire avant d’attribuer le handle. Deux appels sur des plages distinctes pouvaient tous deux voir 127 objets et créer chacun un objet, portant le total à 129. Ce défaut était déjà présent dans le parcours linéaire précédant 0476.

0480 recontrôle le compteur de type sous le verrou de l’attribution. Si un autre appel a rempli le quota, le perdant rend son prêt hors de `G`, libère l’objet temporaire et renvoie `0x10801`. Le contrôle rapide avant le prêt et les erreurs de validation restent en place.

Banc Linux compilant le bloc `case 0x15` et les fonctions réelles d’attribution. Barrière dans le substitut de prêt pour imposer l’entrelacement. Avant, `127 → 129`, deux succès. Après, `127 → 128`, un succès et un refus avec restitution. ASan/UBSan, 100 répétitions de chacune des charges suivantes.

| Quota initial | Appels concurrents | Limites | Succès | Prêts rendus |
| ---: | ---: | --- | ---: | ---: |
| 127 | 2 | actives | 1 | 1 |
| 120 | 16 | actives | 8 | 8 |
| 127 | 16 | désactivées | 16 | 0 |

300 courses et 3 400 créations, suivi des handles, bitmap et restitution hors verrou. Quota déjà plein, prêt refusé et table de handles pleine vérifiés. Aucun handle ni bit d’occupation restant après retrait. Les appels Mach du prêt restent simulés. Les preuves appareil restent à établir.

Compilation iPhoneOS à suivre. FPS, mémoire résidente, température et consommation sur iPhone non mesurés.


## Pic mémoire déclaré au jeu

Le marquage des pages comparait `g_phys` au pic total incluant aussi le tas et les charges fixes. Si le pic était déjà supérieur à la seule mémoire physique, des allocations nouvelles ne le relevaient pas. La lecture du pic utilisait l’usage courant tant que les pages existaient, puis perdait cette information après libération. Le défaut est antérieur au regroupement 0474.

Cas reproduit, charge fixe de 33 Mio, puis mappage et libération de 64 Kio. Le pic attendu est de 34 668 544 octets, la référence conserve 34 603 008 octets, soit 65 536 octets manquants.

0484 relève le pic à partir de l’usage total une fois en fin d’opération sous `g_mu`. L’usage physique croît pendant le marquage, donc sa valeur finale est le maximum de cette opération. ASan/UBSan, **26 432 plages par mode** avec vrais octets dans un tampon de 192 Kio, comparaison des pages voisines, des masques, des compteurs et des opérations de permissions. Le pic est vérifié par rapport au résultat attendu et conservé après libération. Les appels de mappage restent simulés.

Le parcours des ombres 0473 passe également sur **4 500 plages par mode** dans un répertoire de 32 768 entrées couvrant 64 Gio, avec des blocs non contigus, des entrées absentes et des erreurs Mach simulées.

Compilation iPhoneOS de 0484 à suivre. FPS, empreinte physique et énergie sur iPhone non mesurés.
