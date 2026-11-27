# S2Arm CPU — reprise du 27 novembre 2026

- Référence initiale `da0e8f7a9` et moteur épinglé `6b6a5715`. Lots 0472–0473 sur `dd53717b` et 0474–0475 sur `65f122925`.
- Dernier correctif validé sur banc Linux et compilé pour iOS, 0476. Le contrôle de quota de mémoire de transfert réutilise le compteur natif.
- Mesures 0474–0475 sur Linux, marquage de 64 Mio neufs 23,79 → 5,71 µs et cycle attribution-fermeture à 512 handles actifs 161,91 → 10,04 ns. Avec 0476, le comptage seul passe de 4,67 µs à 2,21 ns.
- Parité ASan et UBSan, 21 216 mappages et 175 908 attributions par mode pour 0474–0475, 17 382 états pour 0476.
- Builds iPhoneOS vertes sur macOS 15 et 26. `t_svc_mem`, `t_far` et `t_thread` réussis sur macOS 26. [0472–0473](https://github.com/TarbleFR/RewindBox/actions/runs/46003441359), [0474–0475](https://github.com/TarbleFR/RewindBox/actions/runs/46004226378), [0476](https://github.com/TarbleFR/RewindBox/actions/runs/46004723336).
- Pistes rejetées, recherche binaire à 32 intervalles de permissions et premier regroupement qui ralentissait les plages entièrement mappées. Le regroupement corrigé couvre aussi ces plages.
- Dernier lot compilé, 0479. parcours circulaire de `Dispatcher.AddSession` sans modulo. NativeAOT Linux, 65 000 opérations à résultat identique. 1 882 → 653 ns sur une table presque pleine et 23,02 → 20,57 ns à vide. 128 000 allocations concurrentes à résultat identique. [CI iPhoneOS](https://github.com/TarbleFR/RewindBox/actions/runs/46008253226).
- RomFS, double curseur écarté sur banc d’indexation. Deux flux alternés gagnent, les accès aléatoires et quatre flux ralentissent. Mesurer les appels fichier et les copies séparément ensuite.
- Relire la tête distante et la numérotation avant écriture ou publication. Périmètre runtime et services. Aucune IPA.
- [0472–0473](../../docs/evidence/s2arm-runtime-0472-0473.md) · [0474–0475](../../docs/evidence/s2arm-runtime-0474-0475.md) · [0476](../../docs/evidence/s2arm-runtime-0476.md) · [0479](../../docs/evidence/s2arm-runtime-0479.md). Appareil non mesuré.
