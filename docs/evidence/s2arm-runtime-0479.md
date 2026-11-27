# S2Arm 0479 — allocation des sessions IPC

Le curseur de `Dispatcher.AddSession` désigne la prochaine position de départ. Le parcours visite ensuite le tableau une seule fois et repart au début à la fin du tableau. La sélection du premier emplacement libre, les cookies, le verrou et le redimensionnement restent conformes à la référence. Le code de référence est identique entre `da0e8f7a9`, `067bc2347` et `09a2aa490` pour cette méthode.

Banc synthétique Linux x86-64 sur AMD EPYC 9V74. NativeAOT .NET 10.0.15 (SDK 10.0.404). Les méthodes du moteur ont été compilées avec un objet de session synthétique. Un fil et 12 paires avec ordre alterné. Temps médian par ouverture suivie de la fermeture. La vérification a comparé **65 000 opérations**, les cookies et la position des sessions pendant le redimensionnement, puis le retrait complet.

| Sessions initiales sur 1 024 | Référence | Candidat | Paires favorables |
| --- | ---: | ---: | ---: |
| 0 | 23,02 ns | 20,57 ns | 10/12 |
| 512 | 26,67 ns | 21,67 ns | 12/12 |
| 960 | 60,59 ns | 36,94 ns | 12/12 |
| 1 023 | 1 882,27 ns | 652,76 ns | 12/12 |

Les variantes JIT avec un masque et avec `Array.IndexOf` ralentissaient les tables vides sur ce banc. Le parcours retenu a aussi donné 1 805,83 → 909,27 ns à 1 023 sessions en JIT et 23,14 → 22,67 ns à vide. Le banc couvre le cycle du tableau et du verrou, avec fermeture simulée. Il ne chronomètre pas une requête IPC ni le lancement d’un jeu.

Compilation iPhoneOS à suivre. Temps d’image, empreinte et énergie de l’iPhone 16 Pro Max non mesurés.
