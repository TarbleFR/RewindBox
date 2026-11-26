# S2Arm 0427–0428, recherche moteur du 26 novembre 2026

Référence moteur 0426. Les deux changements sont indépendants. Les réglages de rendu, les shaders, la cadence invitée et les règles d’interpolation sont ceux de la référence.

0427 traite les effacements du registre des écritures GPU par bloc de 256 Kio et par mot de 64 bits. La génération avance du nombre exact de marques effacées. Un bloc vide est retiré sous le même verrou. Le contenu invité et les empreintes des blocs intacts ne sont pas lus.

0428 utilise un seul masque d’occupation de 48 octets pour les 384 emplacements de pipelines en attente. Sous le verrou de la file, la recherche parcourt les bits occupés en ordre croissant et compare chaque clé complète. Les états de compilation, les reprises, les délais et les descripteurs Metal suivent le chemin existant. Une première variante à un octet par entrée avec `memchr` a été écartée après une régression sur les charges à 64 et 384 entrées.

## Banc hôte

Depuis deux arbres du moteur préparés avec la série du dépôt arrêtée à 0426 et 0428, exécuter `python3 bench.py ARBRE_0426 ARBRE_0428`. Le banc compile les fonctions C extraites de chaque arbre avec Clang -O2, le vrai type de clé de pipeline et la table de hachage du moteur. Il utilise un substitut C pour les champs Objective-C de la file. Huit passages alternés sur le même hôte Linux x86-64. Le script vérifie le résultat de chaque passage contre la référence.

| Travail synthétique | Temps médian 0426 → candidat, ms | Résultat comparé |
| --- | ---: | --- |
| 80 000 recherches, 0 / 4 / 64 / 384 emplacements occupés | 24,29 → 0,35 / 24,90 → 1,57 / 33,26 → 19,43 / 79,98 → 76,67 | Somme des indices rendus |
| 1 200 effacements, 1 octet / 4 111 octets / 1 499 800 octets | 0,052 → 0,052 / 0,138 → 0,048 / 29,206 → 0,326 | Empreinte de chaque masque restant, génération et nombre de blocs |

Les timings du registre excluent son remplissage et sa vérification. Le cas d’un octet est proche du coût de l’horloge. La distribution effective des tailles et des occupations sur iPhone est inconnue. FPS, temps GPU, mémoire et frametime du candidat sur appareil restent non mesurés.
