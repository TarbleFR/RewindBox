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
