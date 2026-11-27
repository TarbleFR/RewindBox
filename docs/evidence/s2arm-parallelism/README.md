# NVN2 · préparation CPU, soumission GPU et présentation

La référence de code est `584435cb`. La mise à jour RAM documentaire `1a7ecf53` contient les mêmes sources moteur. [Carte des fils, attentes, budgets et protocole de mesure à 1×](architecture.md). [Options et lecture d’une capture](../../../tools/s2arm_a18pro/NEXT_PARALLELISM.md).

## Comparaisons sur Linux

| Charge | Témoin | Candidat | Interprétation |
| --- | ---: | ---: | --- |
| Encodeur pthread, 240 commandes, délai médian jusqu’à la première commande exécutée | 98,8 µs | 33,6 µs | Le fil peut commencer pendant la préparation des commandes suivantes. |
| Même charge, attente médiane de vidange | 108,5 µs | 86,2 µs | La durée totale médiane passe de 199,2 à 186,5 µs. Médiane des écarts appariés −5,8 %, 12/12 séries plus rapides. Le p95 total passe de 268,9 à 281,2 µs. |
| Encodeur pthread, 1 024 commandes, durée totale médiane | 550,2 µs | 567,9 µs | +1,4 % en médiane des écarts appariés. Un démarrage plus tôt peut coûter davantage sur la séquence entière. |
| Rejeu asynchrone actif, 80 soumissions avec une requête scalaire indépendante par travail | 177,12 ms | 87,45 ms | Même empreinte d’ordre. Deux travaux synthétiques d’environ 1 ms rendent l’attente visible. Le témoin attend 90,33 ms au total en médiane, le candidat 0. |

Le lot initial anticipé contient 64 enregistrements complets. Sa publication exige une réservation suivante sur le même producteur et un worker disponible à l’ouverture du lot. Les autres blocs conservent 256 enregistrements. Le lot anticipé peut demander un bloc supplémentaire de 256 enregistrements (environ 32 Kio sur arm64), avec la même file et le même mécanisme de réemploi. Chaque drain termine l’époque. La rétention indirecte des objets graphiques et le pic de mémoire physique restent à relever sur appareil. Les sept requêtes scalaires utilisent uniquement leurs arguments. Toute lecture d’objet, mutation, destruction ou dépendance reste derrière la garde existante. Ce bras ne démarre aucun worker.

[Douze séries, cinq charges et trois variantes](timing.txt) · [Sept paires de mesures de rejeu](scalar-replay.csv). Les fixtures compilent les fonctions de l’arbre moteur préparé. Les appels Metal sont remplacés dans ces deux mesures Linux. Les contrôles adverses couvrent file saturée, ordre, record encore en construction, voies secondaires, rétention, arrêt, échec du lancement du worker et repli synchrone.

```sh
python3 run_rec_early_queue.py /path/to/engine-before /path/to/engine-after --pairs 12 --frames 48 --csv timing.csv
python3 run_rec_early_queue.py /path/to/engine-before /path/to/engine-after --check-only --sanitize
python3 queue_bench.py /path/to/engine-after --pairs 7 --out samples.csv
```

## Présentation et chronologie

L’arrêt sûr Metal 3 pouvait refuser le command buffer après réservation du slot. Le refus annule désormais la réservation et permet l’acquittement du ticket logique. Aucun callback ou affichage GPU n’est inventé. Le candidat NVN2 réemploie l’un des trois slots déjà alloués quand le slot préféré est encore occupé. La suite logique des tickets et les dernières lectures GPU restent inchangées. Le jeu avec une seule fenêtre de trois textures en rotation peut ne présenter aucune occasion. Mesurer `alternatives` avant toute promotion.

La trace corrèle l’ouverture du command buffer, sa remise pour soumission, le feedback GPU et le temps d’affichage effectif. Le calcul prend l’union des intervalles avant intersection. La durée d’un command buffer est une enveloppe pouvant inclure des dépendances GPU. Les trous de la file observée peuvent correspondre à d’autres files ou à une contrainte réelle du jeu. Une trace partielle conserve les dénominateurs et les réservations sans callback. La fenêtre maximale est de 600 frames, 16 384 command buffers, 4 096 tickets. Une frame peut avoir plusieurs segments. L’interpolation est exclue des tickets natifs.

Sur Linux x86-64, neuf séries alternées donnent par itération une médiane de 0,287 ns pour la boucle témoin, 0,769 ns pour la garde désactivée, 2,693 ns pour la réservation active, 317,405 ns en ajoutant quatre lectures d’horloge et 1 305,332 ns avec formatage. Ces valeurs excluent le transfert de journal et les callbacks Apple. [Mesures brutes de la sonde](overhead.csv).

## Banc Metal

Le banc hors écran compare quatre politiques de profondeur avec les mêmes trois textures de 1280 × 720. L’ordre des bras varie sur quatre blocs de 180 images par politique après préchauffage. Il compte le débit des commandes terminées, la latence soumission–callback, le temps de file, le p99 et le recouvrement des fenêtres horodatées. L’adaptation exploite le temps d’attente et l’ancienneté des travaux en cours. Les durées sur l’hôte et les horodatages GPU non disponibles gardent des dénominateurs distincts. La latence d’entrée, la cadence native des jeux, la puissance et la mémoire de l’iPhone nécessitent la campagne physique.

Après les mesures, le banc vérifie pour chaque politique 180 marqueurs distincts d’image, 179 marqueurs de la précédente et l’intégralité des trois dernières surfaces. La permutation de deux marqueurs sert de contrôle négatif. Le rejeu moteur séparé compare, dans l’ordre des dessins et dispatchs, les opérations de synchronisation et leurs masques, puis vérifie l’état et les pixels. Le nombre de quatorze publié dans la référence historique désigne sept paires attente/mise à jour. Les assertions du test inter-file constituent une vérification distincte.

[Mesures appariées par série](encode-rounds.csv) · [Durée de vie des ressources et arrêt de présentation](presentation.md). Le dernier feedback effectue les lectures diagnostiques avant de rendre le slot à son prochain utilisateur. Le choix du slot n’alloue aucune surface supplémentaire.


## Campagne de 30 minutes

L’option `S2A_RB_PARALLEL_LONG=1` accompagne un démarrage valide du Banc d’essai. Les cinq jalons enregistrent la minute écoulée et le cumul, les périodes sans notification et les bornes supérieures des quantiles par pas de 0,25 ms. Une valeur au-delà de 128 ms reste dans le compartiment de débordement et son maximum exact est conservé. Le fichier `Diagnostics/S2Arm/benchmarks/<id>-native-1800s.json` est remplacé atomiquement à chaque jalon. Une interruption explicite conserve la partie observée. Le compteur mesure les notifications de présentation invitées admissibles. Le temps d’écran confirmé est mesuré séparément. Le stockage des compteurs représente 124 592 octets, avec une copie temporaire au checkpoint. Comparer instrumentation active/inactive sur appareil. Le test portable confronte 540 quantiles et couvre 58 049 notifications avec traversées de minutes, silences et horloges invalides.

Sur Linux, neuf paires de 200 000 appels donnent 0,542 ns en médiane pour la garde désactivée et 32,534 ns avec l’horloge, le mutex non contesté et l’histogramme. [Mesure de coût du compteur 30 minutes](long-cadence-overhead.csv).

Sur la session historique MKW du 20 novembre 2026 identifiée par `host-20261120-073420.log`, la même initialisation du moteur identifie le GPU Apple A18 Pro et le backend direct Metal 4. Cette observation sur appareil précède les correctifs 0506–0512. La ligne de démarrage `direct backend: Metal 4` ou `direct backend: Metal 3` identifie le chemin réellement choisi dans une nouvelle session.
