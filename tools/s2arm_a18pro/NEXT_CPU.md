# S2Arm CPU — reprise du 27 novembre 2026

- Référence initiale `da0e8f7a9` et moteur épinglé `6b6a5715`. Lot 0472–0473 sur `dd53717b`, CI 46003441359.
- Dernier lot validé sur banc Linux, 0474–0475. Groupes de 16 Kio uniformes et bitmap des handles natifs.
- Mesures à 64 Mio de pages neuves, 23,79 → 5,71 µs. À 512 handles actifs, 161,91 → 10,04 ns par cycle attribution-fermeture.
- Parité ASan et UBSan sur 21 216 mappages et 175 908 attributions par mode. Contrôles macOS `t_svc_mem`, `t_far` et `t_thread` dans la CI moteur.
- Rejetées pour le moment, la recherche binaire à 32 intervalles de permissions et la première version des groupes qui ralentissait les plages entièrement mappées. La version retenue accélère ces plages.
- Chantier suivant, IPC et services. Isoler le coût d’ouverture/fermeture d’une session et la contention du verrou Dispatcher avant de proposer un changement.
- Ensuite, mesurer les lectures RomFS fragmentées après 0463 pour distinguer appels de fichier, copies et temps de décompression.
- Relire la tête distante et la numérotation avant écriture ou publication. Périmètre runtime et services. Aucune IPA.
- [Lot 0472–0473](../../docs/evidence/s2arm-runtime-0472-0473.md) · [Lot 0474–0475](../../docs/evidence/s2arm-runtime-0474-0475.md). Appareil non mesuré.
