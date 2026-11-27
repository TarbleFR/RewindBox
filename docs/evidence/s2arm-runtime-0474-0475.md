# S2Arm 0474–0475 — mise à jour des pages et des handles

La référence immédiate est `dd53717b`, série jusqu’à 0473 sur le moteur épinglé `6b6a5715`. Pour les deux chemins mesurés, le code de référence est identique sur `da0e8f7a9` et `dd53717b`.

Linux x86-64, AMD EPYC 9V74, GCC 14.2.0, `-O2 -march=native`, sur un processeur logique. Médianes du temps par appel. Le banc compile les fonctions modifiées et remplace les écritures à l’adresse du jeu et le registre des permissions par des enregistrements des opérations demandées. Le banc des handles appelle l’attribution et la fermeture internes sous un verrou simulé par l’exécution sur un seul thread. Les mesures excluent les appels système et l’attente des verrous.

| Banc et charge | Référence | Candidat | Paires favorables |
| --- | ---: | ---: | ---: |
| 0474 · 1 Mio neuf | 391,06 ns | 107,91 ns | 10/10 |
| 0474 · 64 Mio neufs | 23,79 µs | 5,71 µs | 10/10 |
| 0474 · 64 Mio déjà mappés | 14,56 µs | 6,59 µs | 10/10 |
| 0474 · 64 Mio avec des groupes partiellement mappés | 41,56 µs | 40,67 µs | 5/10 |
| 0475 · table vide | 5,13 ns | 6,82 ns | 0/12 |
| 0475 · 16 handles actifs | 10,04 ns | 6,92 ns | 12/12 |
| 0475 · 128 handles actifs | 45,09 ns | 7,58 ns | 12/12 |
| 0475 · 512 handles actifs | 161,91 ns | 10,04 ns | 12/12 |
| 0475 · 1 023 handles actifs | 320,58 ns | 13,38 ns | 12/12 |

- **0474.** ASan et UBSan, 21 216 comparaisons par mode avec bornes partielles, franchissement de la fenêtre hôte, conservation des pages voisines et parité du compteur physique, du pic et des appels de remise à zéro ou de permissions. À 64 Kio avec des groupes partiels, surcoût inférieur à 1 ns sur la médiane. Le premier candidat ralentissait les plages déjà mappées de 16 %. La prise en compte de ces groupes a supprimé cette régression.
- **0475.** ASan et UBSan, 175 908 résultats d’attribution par mode avec parité des numéros, des générations, des plafonds et des partitions déterministes. Remplissage, échec, réutilisation et retrait complet comparés. Le bitmap occupe 1 Kio. Le cycle en table vide coûte 1,69 ns de plus sur le banc.
- Fuites ASan non vérifiables dans l’environnement tracé. Compilation et contrôles natifs macOS à suivre. Temps d’image, consommation et empreinte réelle sur A18 Pro non mesurés.
