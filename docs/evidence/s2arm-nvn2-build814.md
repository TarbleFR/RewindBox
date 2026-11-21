# NVN2 après la build 814

Sur iPhone 16 Pro Max, les relevés transmis pour Zelda comptent 1 270 PSO compilés en jeu, aucune écriture d’archive en 641,5 s et 38,3 s d’attente d’une bibliothèque déjà en construction. Les maxima de trame rapportés sont de 19 628,4 ms sur Zelda et 2 607,1 ms sur Mario Kart World. Les deux journaux bruts de cette build étaient indisponibles pour cette intégration. Ces valeurs proviennent du relevé de l’utilisateur.

| Chemin de la 814 | Changement | Observation après mise à jour |
| --- | --- | --- |
| Les descripteurs des PSO compilés attendent un créneau du préchauffage spéculatif. | `S2A_RB_ARCHIVE_WRITE_ALWAYS` autorise le worker d’écriture sous Nominal, Fair et Serious quand la marge dépasse 1 024 Mio. Un lot ne devient réutilisable qu’après écriture de l’archive et publication de son index. La fermeture propre garde une limite de temps et de mémoire. | Comparer les entrées écrites à la fin du premier lancement puis les succès de création stricte depuis l’archive sur le second. |
| Une promotion dans la liste de recettes peut rester derrière le gouverneur dès Fair. | `S2A_RB_PROMOTED_URGENT` transmet le travail promu par un programme réellement enregistré à la file de première utilisation. | Comparer les lignes promues, les PSO construits et le temps d’attente de la soumission. |
| Le premier draw pouvait consulter les stages sans déclencher leur préparation. Le filtre de réflexion utilisait aussi la forme de la géométrie. | `S2A_RB_ASYNC_FIRST_DRAW` et `S2A_RB_FIRST_DRAW_RECOVERY` activent la préparation urgente et l’omission bornée à quatre trames quand la réflexion et la passe le permettent. | Lire les omissions de draws et les motifs résiduels, notamment stockage, compute, réflexion et limite de quatre trames. |
| Une écriture de la soumission précédente marquait une page entière de 4 Kio comme indisponible pour un bloc uniforme. | `S2A_RB_UNIFORM_RANGES` conserve les bornes des écritures, puis assemble uniquement les octets lisibles et les mises à jour connues. Une collision ou un chevauchement non couvert maintient le découpage. | `[rb-uniform]`, passes interrompues, octets de load/store et p50 GPU sur la même scène. |
| Le scanner disque et le suivi thermique invité utilisaient un identifiant de jeu fixe. | `S2A_RB_NVN2_DISK_CACHE` unifie la résolution des chemins de stage et de recette en conservant le répertoire de chaque jeu. `S2A_RB_NVN2_GUEST_QOS` sélectionne les workers éligibles sur le backend direct A18 Pro. `S2A_RB_HOT_IDLE_COALESCE` espace les réveils des secondaires en polling continu sous Serious. | `[rb-shader-disk]`, `[RB-GUEST-QOS]`, transitions confirmées, réveils/s et p50 de soumission. |
| Les clears pouvaient être séparés par des commandes d’état sans lecture et les retours de sous-liste imposaient une nouvelle pièce de soumission. | `S2A_RB_SEALED_CLEAR_STATE` étend la preuve d’écrasement sur les états admis. `S2A_RB_XQ_TAIL_RETURNS` reprend sur le même command buffer uniquement après confirmation du signal et vérification des retours. | `sealed_stores`, `pieces_avoided`, temps de rejeu et pixels des cibles. |

Le producteur macOS utilise la chaîne du moteur et l’historique d’un seul titre. Le lecteur reçoit des segments metallib et leurs réflexions au format natif S2ALIB. Le pack doit correspondre au titre, au build, à la chaîne et à la signature du traducteur. Les stages absents de la capture restent à découvrir au premier passage. Un pack de bibliothèques AIR et une archive de PSO couvrent deux étapes différentes de la compilation. [Commande de génération](../../build-utils/s2arm/build_nvn2_shader_pack.py)

Les critères sur appareil s’évaluent sur les mêmes scènes après un premier passage puis après fermeture et relance, séparément à Nominal, Fair et Serious. Relever les trames de plus de 500 ms, les évictions, les budgets Mach aux deux périodes et les temps GPU. Le nombre de draws omis doit se lire avec les pixels affichés et la durée d’omission.

## Compléments au moteur 0273

Le lecteur de packs accepte les sources exportées sous les extensions .metal et .msl. Le producteur de recettes promues attend une place dans la file urgente quand les 32 places sont occupées. Cette attente appartient au worker de préchauffage. Un draw en lecture seule qui suit une prépasse de profondeur sur une cible monocouleur neuve peut différer son premier pipeline pendant quatre trames. Le test garde une bibliothèque en cours de construction sur un autre thread pendant la soumission.

La preuve par intervalles de la 0272 reste prioritaire pour les uniformes. Le moteur conserve également des versions bornées des octets connus de cinq soumissions et peut reconstruire une lecture sur une écriture inline antérieure. Une écriture GPU dont la valeur est inconnue garde la synchronisation habituelle. Le test Metal compare le rendu de deux draws avec le même uniforme et deux valeurs différentes.

En Fair, les grandes cibles réductibles peuvent passer à 0,85× sur chaque axe lorsque le réglage utilisateur est à 1×. Le retour à la résolution native attend 30 s en Nominal. Les lectures de texture incompatibles, les cibles de présentation et les attachements impossibles à redimensionner ensemble suivent les protections du moteur. La QoS est initialisée à nouveau sur la première soumission NVN2 si le périphérique Metal a été créé avant la configuration du titre. Le propriétaire d’une réservation Mach révoquée peut réessayer une fois après vérification sur son propre thread, avec les plafonds de 2 et 4 ms.

Un signal GPU futur conserve son ordre. Si une nouvelle soumission commence par la seule attente d’un événement exclusivement écrit par le GPU, la file peut stationner avant d’ouvrir un command buffer vide. Le compteur empty_prefixes compte ces opérations. Les copies virtuelles sont prises en compte à l’entrée de la file. Une texture sale pouvant nécessiter un upload interdit cette optimisation.

Pour une comparaison sur appareil, repartir du même fichier env.txt et du même niveau de chauffe. La limite de quatre trames peut conduire à une attente exacte à la cinquième. Les recettes et les stages non capturés restent à découvrir. Les seuils de 500 ms, 40 passes et 60 FPS demandent des mesures sur iPhone.

~~~ini
S2A_RB_ARCHIVE_WRITE_ALWAYS=1
S2A_RB_PROMOTED_URGENT=1
S2A_RB_NVN2_DISK_CACHE=1
S2A_RB_STAGE_BINARIES=1
S2A_RB_STAGE_DISK_WARM=1
S2A_RB_CAPTURE_PACK=1
S2A_RB_URGENT_WORKERS=1
S2A_RB_ASYNC_FIRST_DRAW=1
S2A_RB_FIRST_DRAW_RECOVERY=1
S2A_RB_UNIFORM_RANGES=1
S2A_RB_INPASS_UBO_RING=1
S2A_RB_NVN2_GUEST_QOS=1
S2A_RB_GUEST_QOS_THERMAL=1
S2A_RB_HOT_IDLE_COALESCE=1
S2A_RB_RT_RECHECK=1
S2A_RB_FAIR_SCALE=0.85
S2A_RB_ALL_NVN2_TILES=1
S2A_RB_NVN2_MRT_CLEARS=1
S2A_RB_MRT_REPEATED_CLEARS=1
S2A_RB_SEALED_CLEAR_STATE=1
S2A_RB_XQ_RESUME=1
S2A_RB_XQ_TAIL_RETURNS=1
S2A_RB_XQ_WAIT_PREFIX=1
~~~

## Identité AIR et budget PSO

L’en-tête de `lib.idx` lie le pack capturé aux identifiants du titre, du build, de la chaîne et du traducteur. Le moteur vérifie cette identité à la lecture de la table et de l’index. Une empreinte discordante écarte le pack capturé. Un repli vers le source MSL indique la clé et la cause dans le journal.

`S2A_RB_NVN2_PSO_BUDGET=1` étend à tous les titres la réserve PSO du gouverneur, dans la même enveloppe mémoire totale. En Fair, un programme déjà demandé peut faire passer sa recette sur la file urgente. Si le nombre ou la taille des PSO résidents approche du plafond, le worker laisse la recette dans la file. Le premier draw conserve son accès au worker urgent. `S2A_RB_PSO_HEADROOM=0` désactive la réserve.
