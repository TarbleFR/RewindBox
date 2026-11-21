# Gel de présentation à la trame 3234

Mario Kart World, titre `0400C3F00006E000`, iPhone 16 Pro Max. La capture compte 282 demandes Mach, dont 251 à 15 ms et une à 30 ms. À la fenêtre de la trame 3000, la médiane de soumission et présentation atteint 16,87 ms, le p99 de présentation 50,005 ms et la cadence affichée 44,512 FPS. Le GPU est à 15,22 ms en médiane. Le watchdog relève dix secondes sans nouvelle image. L’historique borné du journal ne permet pas d’établir la perte du signal du thread 184.

## Correctifs du moteur

- **0245** fixe la demande de calcul à 2,000 ms sur le backend direct NVN2 hébergé sur iOS. Un changement de cadence 1 ↔ 2 exige au moins huit trames invitées consécutives et 250 ms à la même valeur. Les appels répétés sur une trame ne font pas avancer la confirmation. Le filtre intervient avant la déclaration Mach et le changement de plage du display link, y compris avec le réglage historique de ProMotion. Le journal Mach distingue la demande de la politique relue dans le noyau.
- **0246** échantillonne la compression du processus. Dès que celle-ci dépasse 512 Mio ou que l’appareil atteint Fair, le budget de rétention est plafonné à 96 Mio. Le plafond critique reste à 32 Mio. La sortie du régime limité exige dix secondes stables à Nominal et au plus 448 Mio compressés. Le gouverneur réduit les admissions facultatives et laisse les ressources nécessaires aux commandes en vol achever leur durée de vie.

## Vérification

Le rejeu des 270 écritures d’intervalle de la capture donne trois décisions Mach, initialisation comprise. Les trames 3219 à 3234 ne déclenchent aucune reconfiguration. La première mesure qui active le plafond est à la trame 773, à Nominal et 702,6 Mio compressés. Pour les neuf relevés sous pression avec la marge et la réserve PSO de ce parcours, les quotas de prélecture, uploads, textures et pipelines sont respectivement de 0, 18, 54 et 24 Mio.

Sur iPhone, répéter le même parcours au-delà de la trame 3234 et de la première transition vers Fair. Comparer la demande et la relecture Mach, les changements de plage, `[RB-MEM-GOV]` (`thermal`, `compressed_logical_bytes`, `stress_cap`, quotas), la mémoire compressée du processus, ses page-ins, le p50/p95 de soumission + présentation, le p99 de présentation et les coupures audio. Les 55 521 page-ins et 12 191 page-outs de la dernière fenêtre couvrent le système. Le processus y enregistre 30 545 page-ins.
