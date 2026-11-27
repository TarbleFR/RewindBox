# S2Arm CPU — reprise du 27 novembre 2026

- Référence initiale `da0e8f7a9` et moteur épinglé `6b6a5715`. Lots 0472–0473 sur `dd53717b` et 0474–0475 sur `65f122925`.
- Dernier correctif validé sur banc Linux, 0476. Le contrôle de quota de mémoire de transfert réutilise le compteur natif.
- Mesures 0474–0475 sur Linux, marquage de 64 Mio neufs 23,79 → 5,71 µs et cycle attribution-fermeture à 512 handles actifs 161,91 → 10,04 ns. Avec 0476, le comptage seul passe de 4,67 µs à 2,21 ns.
- Parité ASan et UBSan, 21 216 mappages et 175 908 attributions par mode pour 0474–0475, 17 382 états pour 0476.
- Contrôles natifs `t_svc_mem`, `t_far` et `t_thread` via la CI moteur. Suivre les runs 46003441359 et 46004226378 ainsi que le run du dernier lot.
- Pistes rejetées, recherche binaire à 32 intervalles de permissions et premier regroupement qui ralentissait les plages entièrement mappées. Le regroupement corrigé couvre aussi ces plages.
- Chantier suivant, IPC et services. Isoler le coût de création d’une session et la contention du verrou Dispatcher. Préserver la fermeture hors verrou et la durée de vie des objets.
- Ensuite, mesurer les lectures RomFS fragmentées après 0463 pour distinguer appels de fichier, copies et temps de décompression.
- Relire la tête distante et la numérotation avant écriture ou publication. Périmètre runtime et services. Aucune IPA.
- [0472–0473](../../docs/evidence/s2arm-runtime-0472-0473.md) · [0474–0475](../../docs/evidence/s2arm-runtime-0474-0475.md) · [0476](../../docs/evidence/s2arm-runtime-0476.md). Appareil non mesuré.
