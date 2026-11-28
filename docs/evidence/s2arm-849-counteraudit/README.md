# S2Arm : contre-expertise physique des builds 848 et 849

28 novembre 2026. Base `08d2017606e86cf2092f05b9c448ff740e451aa5`, moteur amont `6b6a5715`. Archives personnelles analysées localement : 102 journaux, 80 captures de trames et 74 profils CPU. Aucun journal brut publié.

## Résultat et identités

Les scènes 848/849, caches, température et génération d’images ne sont pas appariés : aucun gain ou recul global causalement démontré. Seul MKW possède des identités de préparation explicitement 848/849 ; Zelda reste sans attribution applicative certaine, Fire Emblem précède la livraison 849. Aucun profil CPU ne couvre les sessions du 27 novembre.

| Build | Source moteur | Empreinte native empaquetée | Dernier patch |
| --- | --- | --- | --- |
| 848 | `e64d53205f934ac8aa699fc3a8bc55fdce4cc790` | `47029c26b8b93668e2b0cfccff4d28d8dfb553fd71e0cd0436331a4b2ab3e560` | 0470 |
| 849 | `491008cffa8051913ff2ee21c6427fc3e2f19190` | `7798f065487c9977891a9dc6317800a4d7e54d5726b2610deb991f3479ac98b9` | 0529 |

MKW garde le build jeu `9e244438c3d8ef1c703a6a85ef99c4f0`, révision graphique 3. Les générations de préparation sont des identités distinctes de l’empreinte native ; les journaux seuls ne re-hachent pas le Mach-O installé. Reçus et manifestes 848/849 concordent avec leurs pins historiques.

## Causes établies et limites

| Événement | Constat vérifié | Conséquence |
| --- | --- | --- |
| MKW 4090 / 4097 | MSL sur soumission 710,622 / 427,045 ms, attente PSO 181,184 / 91,327 ms ; très peu de lectures, pas d’upload | Gels de premier usage shader, distincts du stockage. |
| MKW 129 / 327 / 1977 | Premiers uploads 136,6 / 211,4 / 125,8 Mio, pagination et attente PSO selon la trame | Plusieurs causes ; pas de preuve d’une boucle d’éviction. |
| Zelda 2694 / 2714 | Trames 3 237 / 3 917 ms, uploads 94,8 / 365,8 Mio et pagination | Attribution précise backing/RomFS/cache encore incomplète. |
| FE 976 | Attente de file présentation 1 008,6 ms ; FI active | FI ne mesurait pas `nextDrawable` : 0533 ferme ce manque. Aucun arrêt GPU observé ici. |
| Tas MKW / Zelda | Total jusqu’à 1 325 / 1 776 ms, zones seules 8,13 / 12,27 ms | Coût après les zones ou ordonnancement ; cause individuelle non établie. 0530 retire le recensement lourd par défaut. |
| Rendu soutenu MKW 8400 | GPU p50 22,64 ms, trame p50/p95/p99 32,01/41,26/47,53 ms, Serious | Budget natif 16,67 ms non atteint ; ne pas additionner les phases chevauchantes. |

MKW : 26 événements structurés >100 ms, dont 14 >200 et 5 >500, dans la session observée. Cela ne remplace pas une capture exhaustive appariée. Son relevé affiche 30,988 i/s avec FI, tandis que la vitesse invitée est 89,7 % : ce nombre ne prouve pas 60 FPS natifs. FE : GPU principal 0,90 ms mais interpolation moyenne 12,64 ms ; ne pas les confondre.

## Corrections appliquées

- **0530** : recensement lourd du tas optionnel ; heartbeat et compteurs légers conservés. Cadence, couverture partielle, temps CPU et phases explicités, entrée managée séparément optionnelle.
- **0531** : parcours des seuls ID enregistrés via l’index de séries existant quand il est moins grand, avec arrêt après preuve de rétention de tous les candidats. Mêmes racines, vues, verrous et règles de libération.
- **0532** : protection d’arrêt Metal 4 étendue au présentateur FI ; refus avant réservation et après encodage, remboursements et deux lectures préservés.
- **0533** : les deux acquisitions de drawable FI rejoignent le compteur atomique existant ; aucune nouvelle famille de journaux.

[Revue des séries et décisions conservées](review.md) · [Matrice par patch et SHA-256](patches.csv) · [Validations](validation.md). Aucun autre émulateur, réglage de qualité, JIT, sauvegarde, cache ou manifeste livré modifié. Aucun nouveau test permanent, workflow, boucle automatique ou IPA.
