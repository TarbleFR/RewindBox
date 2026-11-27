# S2Arm CPU — reprise du 27 novembre 2026

- Référence `da0e8f7a9`, moteur épinglé `6b6a5715`, série jusqu’à 0471.
- Sur le banc Linux, 0472 compte les pages invitées par mot du bitmap, 0473 saute les blocs distants vides.
- Comptage sur 64 Mio mixte, 14,38 → 0,18 µs. Répertoire mixte sur 128 Mio, 8,41 → 0,26 µs avec Mach simulé.
- Parité vérifiée sur 109 218 comptages et 4 500 plages de protections par mode, ASan et UBSan. Contrôles natifs `t_svc_mem` et `t_far` à vérifier en CI.
- Piste écartée pour le moment, la recherche binaire des permissions à 32 intervalles, 0/10 gains sur le cas de lecture uniforme à 32. Retester seulement si la taille observée des tables justifie un seuil plus haut.
- La mise à jour du bitmap par `MapPhysicalMemory` garde un passage par 4 Kio.
- Prochain essai, traiter en une fois les groupes de 16 Kio entièrement neufs. Vérifier zéro initial, préservation des voisins, compteur physique et pic.
- Après ce banc, mesurer le coût des handles IPC et le débit de lecture des données. Enchaîner sur une piste qui gagne contre la référence et le meilleur candidat.
- Avant écriture ou publication, relire Claude et la numérotation. Périmètre runtime et services. Aucune IPA.
- [Preuves et conditions](../../docs/evidence/s2arm-runtime-0472-0473.md). Appareil non mesuré.
