# S2Arm 0472–0473 — coût du mappage de mémoire invitée

La référence utilise le moteur `6b6a571553f7a687af46e03e2cdbf8ef4d77f335` avec la série de `da0e8f7a9` jusqu’à 0471. Les candidats diffèrent par les chemins de comptage des pages et de lecture du répertoire d’ombres. Dans le deuxième banc, 0472 et la base exécutent le même code de référence pour le répertoire.

## Mesures de l’hôte

Linux x86-64, AMD EPYC 9V74, GCC 14.2.0, `-O2 -march=native`, un processeur logique. Dix paires avec ordre alterné. Le banc compile le code réel de comptage et de parcours du répertoire avec des données synthétiques. Les appels Mach du second banc sont simulés. Médianes par appel.

| Banc et charge | Base | Candidat | Paires favorables |
| --- | ---: | ---: | ---: |
| 0472 · bitmap mixte, 4 Kio | 2,55 ns | 3,05 ns | 1/10 |
| 0472 · bitmap mixte, 16 Kio | 5,73 ns | 3,90 ns | 10/10 |
| 0472 · bitmap mixte, 1 Mio | 235,32 ns | 10,26 ns | 10/10 |
| 0472 · bitmap mixte, 64 Mio | 14,38 µs | 0,18 µs | 10/10 |
| 0472 · bitmap mixte, 1 Gio | 229,50 µs | 2,29 µs | 10/10 |
| 0473 · répertoire mixte, 16 Kio | 5,48 ns | 6,19 ns | 1/10 |
| 0473 · répertoire vide, 2 Mio | 152,71 ns | 7,17 ns | 10/10 |
| 0473 · répertoire mixte, 128 Mio | 8,41 µs | 0,26 µs | 10/10 |
| 0473 · répertoire intégralement rempli, 128 Mio | 1,36 µs | 1,39 µs | 2/10 |

Sur un bloc vide entier, 0473 fait une lecture du répertoire au lieu de 128. La réduction mesurée concerne la préparation de la liste de protections. Le coût des appels système de mappage et la durée totale du lancement restent à mesurer.

## Contrôles

- ASan et UBSan, parité pour **109 218** comptages par mode, dont les 9 216 sous-plages possibles des deux derniers masques, et **4 500** plages de protections, dont des refus Mach simulés. Les tests désactivent et réactivent chaque correctif par sa variable d’environnement. Détection de fuites indisponible sous le traceur de l’environnement Linux.
- Sur les plages mixtes, le banc court montre un surcoût inférieur à 1 ns sur 4 Kio pour 0472 et sur 16 Kio pour 0473. Les protections et le résultat du contrôle de budget sont identiques.
- La recherche binaire expérimentale des permissions n’est pas intégrée. Sur 409 601 comparaisons par mode, la parité est vérifiée. Le temps de recherche monte de 23,13 à 31,28 ns à 32 intervalles uniformément sondés malgré un gain à 256. La cardinalité réelle nécessaire pour justifier le changement reste à établir.
- Compilation et contrôles natifs macOS à suivre. FPS, p95 d’image, empreinte, température et consommation sur A18 Pro non mesurés.
