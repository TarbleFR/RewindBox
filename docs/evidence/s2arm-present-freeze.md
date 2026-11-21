# Gel de présentation à la trame 3234

Mario Kart World, titre `0400C3F00006E000`, iPhone 16 Pro Max. La capture compte 282 demandes Mach, dont 251 à 15 ms et une à 30 ms. À la fenêtre de la trame 3000, la médiane de soumission et présentation atteint 16,87 ms, le p99 de présentation 50,005 ms et la cadence affichée 44,512 FPS. Le GPU est à 15,22 ms en médiane. Le watchdog relève dix secondes sans nouvelle image. L’historique borné du journal ne permet pas d’établir la perte du signal du thread 184.

## Correctifs du moteur

- **0245** fixe la demande de calcul à 2,000 ms sur le backend direct NVN2 hébergé sur iOS. Un changement de cadence 1 ↔ 2 exige au moins huit trames invitées consécutives et 250 ms à la même valeur. Les appels répétés sur une trame ne font pas avancer la confirmation. Le filtre intervient avant la déclaration Mach et le changement de plage du display link, y compris avec le réglage historique de ProMotion. Le journal Mach distingue la demande de la politique relue dans le noyau.
- **0246** échantillonne la compression du processus. Dès que celle-ci dépasse 512 Mio ou que l’appareil atteint Fair, le budget de rétention est plafonné à 96 Mio. Le plafond critique reste à 32 Mio. La sortie du régime limité exige dix secondes stables à Nominal et au plus 448 Mio compressés. Le gouverneur réduit les admissions facultatives et laisse les ressources nécessaires aux commandes en vol achever leur durée de vie.
- **0247** borne la contrainte Mach à 4 ms sur les deux threads de présentation concernés. Dans la capture, une demande de calcul de 2 ms avec une contrainte de 16,667 ms donnait 8,333 ms après relecture. Un budget de calcul de 2 ms avec une contrainte de 4 ms respecte le [plancher documenté de XNU](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/mach/thread_policy.h). Le moteur vérifie la politique effective et revient au partage de temps si le budget dépasse 3 ms ou que la relecture échoue.

## Vérification

Le rejeu des 270 écritures d’intervalle de la capture donne trois décisions Mach, initialisation comprise. Les trames 3219 à 3234 ne déclenchent aucune reconfiguration. La première mesure qui active le plafond est à la trame 773, à Nominal et 702,6 Mio compressés. Pour les neuf relevés sous pression avec la marge et la réserve PSO de ce parcours, les quotas de prélecture, uploads, textures et pipelines sont respectivement de 0, 18, 54 et 24 Mio.

Sur iPhone, répéter le même parcours au-delà de la trame 3234 et de la première transition vers Fair. Comparer la demande et la relecture Mach, les changements de plage, `[RB-MEM-GOV]` (`thermal`, `compressed_logical_bytes`, `stress_cap`, quotas), la mémoire compressée du processus, ses page-ins, le p50/p95 de soumission + présentation, le p99 de présentation et les coupures audio. Les 55 521 page-ins et 12 191 page-outs de la dernière fenêtre couvrent le système. Le processus y enregistre 30 545 page-ins.

## Qualification du moteur unifié pour l’IPA 813

Le moteur du commit `96b7e8406` a compilé sur les hôtes macOS 15 et 26, y compris les frameworks iOS arm64. Les 244 premiers patchs correspondent octet pour octet au moteur thermique intégré par `2eb206978` (run `44873287460`). Les trois derniers couvrent le réglage Mach, le gouverneur sous pression et la relecture du budget effectif. [Compilation du moteur](https://github.com/TarbleFR/RewindBox/actions/runs/44874372701)

Les tests du commit `4f606dd39` utilisent le même arbre de patchs, le même commit amont et les mêmes sources UIKit. Sur macOS arm64, les deux demandes ont donné 2 000 000 ns effectifs, pour des périodes de 16 666 667 et 33 333 333 ns. Le repli en temps partagé a été vérifié indépendamment. Avec `DM_RT_COMP=15`, le chemin NVN2 hébergé conserve la demande fixe, quelle que soit la valeur de `S2A_RB_PROMOTION_PACING` ou de l’ancien réglage `S2A_RB_RT_DEBOUNCE`. Le pont a compilé ses onze sources natives. [Tests du moteur et de Metal](https://github.com/TarbleFR/RewindBox/actions/runs/44875064838) · [Compilation et tests UIKit](https://github.com/TarbleFR/RewindBox/actions/runs/44875064920)

Le plancher PSO du profil Mario Kart s’arme à 1 500 Mio de marge et reste actif jusqu’à 1 000 Mio inclus. Dans le plan de 96 Mio du rejeu, les pipelines gardent 24 Mio et un seuil de 4 096 objets. Le test d’archive retrouve les 70 entrées après redémarrage. Les deux essais de store NVN2 produisent les mêmes 512 pixels sur le GPU virtuel. La file directe Metal 4, les FPS, le watchdog et la pagination en course restent à évaluer sur l’iPhone.
