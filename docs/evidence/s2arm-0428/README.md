# S2Arm 0427–0429, recherche moteur du 26 novembre 2026

Référence moteur 0426. Les trois changements sont indépendants. Les réglages de rendu, les shaders, la cadence invitée et les règles d’interpolation sont ceux de la référence.

0427 traite les effacements du registre des écritures GPU par bloc de 256 Kio et par mot de 64 bits. La génération avance du nombre exact de marques effacées. Un bloc vide est retiré sous le même verrou. Le contenu invité et les empreintes des blocs intacts ne sont pas lus.

0428 utilise un seul masque d’occupation de 48 octets pour les 384 emplacements de pipelines en attente. Sous le verrou de la file, la recherche parcourt les bits occupés en ordre croissant et compare chaque clé complète. Les états de compilation, les reprises, les délais et les descripteurs Metal suivent le chemin existant. Une première variante à un octet par entrée avec `memchr` a été écartée après une régression sur les charges à 64 et 384 entrées.

## Banc hôte

Depuis deux arbres du moteur préparés avec la série du dépôt arrêtée à 0426 et 0428, exécuter `python3 bench.py ARBRE_0426 ARBRE_0428`. Le banc compile les fonctions C extraites de chaque arbre avec Clang -O2, le vrai type de clé de pipeline et la table de hachage du moteur. Il utilise un substitut C pour les champs Objective-C de la file. Huit passages alternés sur le même hôte Linux x86-64. Le script vérifie le résultat de chaque passage contre la référence.

| Travail synthétique | Temps médian 0426 → candidat, ms | Résultat comparé |
| --- | ---: | --- |
| 80 000 recherches, 0 / 4 / 64 / 384 emplacements occupés | 24,29 → 0,35 / 24,90 → 1,57 / 33,26 → 19,43 / 79,98 → 76,67 | Somme des indices rendus |
| 1 200 effacements, 1 octet / 4 111 octets / 1 499 800 octets | 0,052 → 0,052 / 0,138 → 0,048 / 29,206 → 0,326 | Empreinte de chaque masque restant, génération et nombre de blocs |

Les timings du registre excluent son remplissage et sa vérification. Le cas d’un octet est proche du coût de l’horloge. La distribution effective des tailles et des occupations sur iPhone est inconnue. FPS, temps GPU, mémoire et frametime du candidat sur appareil restent non mesurés.

## Reconstruction des tampons uniformes (0429)

La soumission reconstruit parfois une plage de constantes à partir de plusieurs écritures encore en vol. Si une lecture tient dans une page de 4 Kio, les octets demandés dans chaque tranche de 64 octets sont identiques d’une version à l’autre. Un masque local de 64 bits permet d’ignorer une tranche qu’une écriture plus récente a déjà entièrement fournie. Les vérifications des écritures GPU opaques, des transferts et des versions perdues précèdent toujours cette recherche. Les lectures traversant une page suivent le parcours existant.

Exécuter `python3 bench_uniform.py ARBRE_0428 ARBRE_0429` sous Linux avec Clang. Le banc synthétique emploie 300 images, 16 200 reconstructions par charge et jusqu’à 32 soumissions en vol. Un premier passage compare pour chaque scénario l’empreinte des résultats, de tous les octets de sortie et du masque de couverture, y compris après un refus. Les 18 passages chronométrés par variante utilisent les mêmes données avec ordre pseudo-aléatoire fixé, une base alignée sur 4 Kio et un binaire sans PIE.

| Charge | Médiane référence → 0429 (ms) |
| --- | ---: |
| 12 pages, mises à jour concentrées | 39,74 → 19,31 |
| 64 pages | 18,14 → 16,13 |
| Écritures GPU et constantes qui se recouvrent | 17,11 → 15,42 |
| Départs décalés de 7 octets | 47,32 → 35,03 |
| Départs décalés de 3 073 octets, passages de page | 54,44 → 39,69 |
| Même décalage avec recouvrements | 16,52 → 15,77 |

Les deux dernières charges mélangent lectures d’une page et lectures sur deux pages. Les temps comprennent aussi l’enregistrement des écritures et la vérification légère du résultat. Une seconde formulation du masque a ralenti les charges à 64 pages et avec recouvrement en traversée de page lors de la comparaison à trois variantes. Quatre autres pistes UBO ont été écartées au criblage sur hôte (comptage des octets manquants, mémorisation du dernier intervalle libre, comparaison entière de 64 octets, filtre de plages d’écriture). Par exemple le filtre gagnait sur 64 pages mais ralentissait la charge concentrée de 66,59 à 68,53 ms. Ces premières séries avaient une disposition mémoire différente et leurs temps absolus ne se comparent pas au tableau.
