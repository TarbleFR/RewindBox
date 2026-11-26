# S2Arm 0427–0430, recherche moteur du 26 novembre 2026

Référence moteur 0426. 0427 et 0429 portent sur deux registres mémoire indépendants. 0430 complète la recherche de 0428. Les réglages de rendu, les shaders, la cadence invitée et les règles d’interpolation sont ceux de la référence.

0427 traite les effacements du registre des écritures GPU par bloc de 256 Kio et par mot de 64 bits. La génération avance du nombre exact de marques effacées. Un bloc vide est retiré sous le même verrou. Le contenu invité et les empreintes des blocs intacts ne sont pas lus.

0428 utilise un seul masque d’occupation de 48 octets pour les 384 emplacements de pipelines en attente. Sous le verrou de la file, la recherche parcourt les bits occupés en ordre croissant et compare chaque clé complète. Les états de compilation, les reprises, les délais et les descripteurs Metal suivent le chemin existant. Une première variante à un octet par entrée avec `memchr` a été écartée après une régression sur les charges à 64 et 384 entrées.

## Banc hôte

Depuis deux arbres du moteur préparés avec la série du dépôt arrêtée à 0426 et 0428, exécuter `python3 bench.py ARBRE_0426 ARBRE_0428`. Le banc compile les fonctions C extraites de chaque arbre avec Clang -O2, le vrai type de clé de pipeline et la table de hachage du moteur. Il utilise un substitut C pour les champs Objective-C de la file. Huit passages alternés sur le même hôte Linux x86-64 (Xeon Platinum 8370C, Ubuntu Clang 18.1.3). Le script vérifie le résultat de chaque passage contre la référence.

| Travail synthétique | Temps médian 0426 → candidat, ms | Résultat comparé |
| --- | ---: | --- |
| 80 000 recherches, 0 / 4 / 64 / 384 emplacements occupés | 24,29 → 0,35 / 24,90 → 1,57 / 33,26 → 19,43 / 79,98 → 76,67 | Somme des indices rendus |
| 1 200 effacements, 1 octet / 4 111 octets / 1 499 800 octets | 0,052 → 0,052 / 0,138 → 0,048 / 29,206 → 0,326 | Empreinte de chaque masque restant, génération et nombre de blocs |

Une seconde expérience emploie les **200 recettes de pipelines de la préparation MKW fournie**. Le même banc accepte `--recipes engine.zip MEMBRE`, où MEMBRE est l’un des quatre chemins finissant par `/pso_reference.tsv` dans cette archive. Il lit la clé persistée avec le lecteur C du moteur. Elle contient 129 états fixes distincts, ses pointeurs de shaders étant à zéro sur disque. Pour 80 000 recherches alternant clés de l’export et échecs imposés, les temps médians passent de **18,40 à 1,80 ms** avec 4 entrées occupées, de **29,68 à 18,01 ms** avec 64, de **56,23 à 43,69 ms** avec 200. Les indices rendus sont identiques pour chaque série. Les occupations, l’ordre de recherche et les pointeurs neutralisés sont ceux du banc. L’export ne retrace pas la file vivante de l’iPhone.

Les timings du registre excluent son remplissage et sa vérification. Le cas d’un octet est proche du coût de l’horloge. La distribution effective des tailles et des occupations sur iPhone est inconnue. FPS, temps GPU, mémoire et frametime du candidat sur appareil restent non mesurés.

## File dense et clés presque identiques (0430)

Une série de contrôle avec 384 entrées occupées et des clés ne différant qu’en fin de structure a montré un ralentissement de 0428. Quand les 64 premiers emplacements sont occupés, 0430 compare directement la première clé puis utilise des empreintes du moteur, calculées à la demande sous le verrou existant. Toute prise d’un emplacement invalide son empreinte. Une concordance déclenche la comparaison de la clé entière. Le parcours conserve le premier indice correspondant même si deux entrées sont identiques. Le tableau fixe de 384 empreintes coûte 3 Kio.

Sur 80 000 recherches et 12 séries en ordre variable, le cas saturé passe de 83,16 ms (0426) à 83,41 ms (0428), puis 29,79 ms (0430). Avec les différences en fin de clé, les temps sont de **187,80 / 202,17 / 26,85 ms**. Pour reproduire cette seconde charge, passer `--near-identical` à `bench.py`. Les occupations partielles ont également été rejouées, ainsi que les deux répartitions avec les recettes MKW. Avec les vraies recettes MKW et `--contiguous` (remplissage des indices libres en commençant à zéro), 80 000 recherches à 200 entrées coûtent 55,44 → 17,58 ms entre 0426 et 0430. En modifiant la fin de la clé pour provoquer les échecs, elles coûtent 57,24 → 17,50 ms. La fréquence sur appareil de ces occupations reste inconnue. Un contrôle avec remplacement d’une clé puis recherche de l’ancienne et de la nouvelle à chaque tour (80 000 tours) coûte, à 384 entrées, 157,70 / 162,85 / 65,35 ms sur 0426 / 0428 / 0430. Sur une charge où 1 023 recherches sur 1 024 aboutissent au premier emplacement, le coût pour 80 000 recherches passe de 1,20 à 1,41 ms entre 0426 et 0430 à pleine occupation, soit environ 3 ns de plus par recherche. Le gain de la file dense porte sur les recherches qui auraient parcouru plusieurs clés.

Un exercice de 10 000 cycles de libération et de reprise d’emplacements, avec duplications et anciennes clés, donne la même somme des indices (1 599 315) sur 0426, 0428, 0430 et 0430 avec collision forcée de toutes les empreintes. AddressSanitizer et UndefinedBehaviorSanitizer étaient actifs sur cet exercice et sur la fixture existante de versions UBO (recouvrements, écritures opaques, rebouclage, mémoire protégée).

## Reconstruction des tampons uniformes (0429)

La soumission reconstruit parfois une plage de constantes à partir de plusieurs écritures encore en vol. Si une lecture tient dans une page de 4 Kio, les octets demandés dans chaque tranche de 64 octets sont identiques d’une version à l’autre. Un masque local de 64 bits permet d’ignorer une tranche qu’une écriture plus récente a déjà entièrement fournie. Les vérifications des écritures GPU opaques, des transferts et des versions perdues précèdent toujours cette recherche. Les lectures traversant une page suivent le parcours existant.

Exécuter `python3 bench_uniform.py ARBRE_0428 ARBRE_0429` sous Linux avec Clang. Le banc synthétique emploie 300 images, 16 200 reconstructions par charge et jusqu’à 32 soumissions en vol. Un premier passage compare pour chaque scénario l’empreinte des résultats, de tous les octets de sortie et du masque de couverture, y compris après un refus. La série de confirmation épingle le processus au même cœur. Sur cet hôte, la commande était `taskset -c 1 python3 bench_uniform.py ARBRE_0428 ARBRE_0429 --pairs 90 --csv uniform-pairs.csv`. Les deux configurations reçoivent les mêmes données, avec ordre pseudo-aléatoire fixé à chaque paire, base alignée sur 4 Kio et binaire sans PIE. Les [90 paires par charge](uniform-pairs.csv) permettent de recalculer la médiane des ratios et son intervalle non paramétrique à 95 % par le test des signes.

| Charge | Médiane référence → 0429 (ms) | Variation médiane par paire [intervalle à 95 %] |
| --- | ---: | ---: |
| 12 pages, mises à jour concentrées | 33,01 → 19,16 | −41,48 % [−42,61 à −39,88] |
| 64 pages | 16,31 → 15,16 | −7,25 % [−11,25 à −6,09] |
| Écritures GPU et constantes qui se recouvrent | 15,35 → 14,61 | −6,88 % [−10,70 à −2,56] |
| Départs décalés de 7 octets | 49,62 → 29,55 | −38,98 % [−41,98 à −33,68] |
| Départs décalés de 3 073 octets, passages de page | 48,78 → 36,10 | −26,66 % [−29,66 à −22,46] |
| Même décalage avec recouvrements | 15,97 → 15,45 | −2,28 % [−5,15 à −0,07] |

Deux séries exploratoires de 18 paires avaient montré de petites inversions sur une charge secondaire (64 pages 16,56 → 16,97 ms ou recouvrements 14,87 → 15,49 ms). L’écart est surtout reproductible sur les lectures concentrées. L’hôte, le modèle d’adresses et le compilateur conditionnent ces chiffres.

Les deux dernières charges mélangent lectures d’une page et lectures sur deux pages. Les temps comprennent aussi l’enregistrement des écritures et la vérification légère du résultat. Une seconde formulation du masque a ralenti les charges à 64 pages et avec recouvrement en traversée de page lors de la comparaison à trois variantes. Quatre autres pistes UBO ont été écartées au criblage sur hôte (comptage des octets manquants, mémorisation du dernier intervalle libre, comparaison entière de 64 octets, filtre de plages d’écriture). Par exemple le filtre gagnait sur 64 pages mais ralentissait la charge concentrée de 66,59 à 68,53 ms. Ces premières séries avaient une disposition mémoire différente et leurs temps absolus ne se comparent pas au tableau.

## Premier export iPhone avant ces modifications

Les [mesures agrégées](windows.csv) couvrent 246 fenêtres complètes de 300 présentations invitées, dans deux journaux Zelda et six journaux Mario Kart World. La session MKW du 25 au matin précède la construction de la 844. Celle du 26 au matin correspond au [relevé 844](../s2arm-844-device.md). Les identifiants de session des deux journaux MKW récents concordent avec les instantanés de préparation de la 845. Celui du 26 au matin concorde avec la 844. L’export Zelda ne contient pas cette identité de préparation. Les [captures de signatures antérieures](../s2arm-845-wave.md) s’arrêtent le 25 au soir (78 fichiers de signatures, 74 profils CPU). Elles ne rejouent pas les sessions du 26.

Empreintes SHA-256 des archives analysées, avant extraction :

| Archive privée | SHA-256 |
| --- | --- |
| engine.zip | `9263e9c229d3b5fe43b793d9dd02195c2aae689bcb9a053ee5cfa1531ec83a2a` |
| profiles.zip | `93e256675ebdd5ad950679c1016c03084211e6ffe7af1ae7957f5643dbc40687` |

Depuis ce dossier, le CSV se reproduit avec Python 3.10 ou ultérieur et Bash.

```sh
z=engine/0400486024DEC000
k=engine/0400C3F00006E000
python3 windows.py engine.zip "$z/host-20261126-123822.log" "$z/host.log" \
    "$k/host-20261125-073705.log" "$k/host-20261125-171923.log" \
    "$k/host-20261126-081747.log" "$k/host-20261126-082440.log" \
    "$k/host-20261126-124621.log" "$k/host.log" > regenerated.csv
cmp windows.csv regenerated.csv
```

`engine_fps` mesure les présentations du moteur par seconde. `generated_shown` compte les images interpolées confirmées à l’écran. Leur débit approximatif vaut `generated_shown × engine_fps / 300` avec un FPS moteur arrondi à la source. Les callbacks Metal et les présentations invitées ont des frontières distinctes. `real_shown_by_fi` concerne le seul chemin d’interpolation. La fréquence totale d’affichage demanderait de compter toutes les présentations confirmées dans la même fenêtre temporelle. Le CSV donne la couverture pour les percentiles d’affichage et le débit des images réelles dont Metal a renseigné le ticket. La durée exacte de la fenêtre moteur et les comptes au-delà de 100/200/500 ms proviennent aussi du compteur d’intervalles. Les colonnes `logged_*` comptent les événements longs effectivement journalisés. Une cellule vide indique un compteur absent. Le temps CPU correspond au fil de soumission, en partie parallèle au GPU. La dernière mesure VM valide disponible dans chaque fenêtre est associée à son numéro d’image. La compression est exprimée en octets logiques avant compression. Les vues du processus et du registre graphique se recouvrent.

### Zelda

Sur la dernière session, les fenêtres de fin 3 900 à 6 600 contiennent 3 000 présentations en environ 124,83 s. Leur cadence globale pondérée par la durée est **24,0 FPS moteur**, avec des fenêtres entre **16,9 et 34,0**. Les dix fenêtres restent en état thermique Fair. La vitesse de jeu mesurée varie de **28,1 à 56,7 %**, le p95 moteur de **39,8 à 88,7 ms**, le GPU p50 de **22,94 à 31,53 ms** et la mémoire du processus de **3 856 à 3 996 Mio**. Les écrans légers précédents sont exclus. Le tracé contient 499 intervalles moteur d’au moins 50 ms, dont 25 au-delà de 100 ms, sept au-delà de 200 ms et trois au-delà de 500 ms. L’attribution du moteur classe 388 des 499 dans la soumission et 102 dans l’attente invitée.

| Session et fin de fenêtre | FPS moteur | Vitesse de jeu | p95 moteur / affiché | GPU p50 / CPU soumission moyen | Mémoire |
| --- | ---: | ---: | ---: | ---: | ---: |
| Premier essai, 3 600 | 13,9 | 23,2 % | 133,35 / 104,18 ms | 52,20 / 19,97 ms | 3 958 Mio |
| Dernier essai, 4 800 | 17,9 | 29,8 % | 88,67 / 83,34 ms | 29,31 / 32,17 ms | 3 889 Mio |
| Dernier essai, 6 600 | 30,6 | 51,0 % | 47,22 / 50,01 ms | 25,17 / 16,20 ms | 3 984 Mio |

- **Blocage de compilation.** L’image 3 614 dure 3 645,8 ms, dont 3 632,5 ms en soumission. Quatre compilations de bibliothèques Metal de shaders invités bloquent cette soumission pendant 2 869,97 ms. Le GPU de cette image dure 36,7 ms. Au démarrage, 1 686 des 1 699 entrées préparées sont prêtes et 13 ont échoué. Le balayage recense aussi 1 425 stages hors liste, avec zéro chargement par son worker. Celui-ci attend l’état thermique nominal. Le premier essai avait atteint le plafond de préparation frontal après 31,6 s, avec 585 entrées en attente. Relier les quatre bibliothèques à l’un de ces ensembles exige la clé de variante exacte. Des cinq identifiants de traduction à la première utilisation imprimés par le dernier essai, trois figurent dans des journaux Zelda plus anciens, aucun dans l’export du lancement immédiatement précédent.
- **Lenteur continue.** À la fenêtre de fin 4 800, la soumission bloque 0 ms sur MSL et encode en moyenne 3 530 dessins et 119 passes par image. Sur 285 intervalles d’affichage connus, 280 sont tardifs. Le moteur réemploie les textures de copie (zéro nouvelle allocation de snapshot), mais copie leur contenu 3 300 fois, soit 1 268,1 Mio en 300 images. Il reprend 3 000 textures de profondeur et 300 de couleur pour ces copies. Le temps GPU propre aux copies reste inconnu. Allonger la réutilisation exige d’identifier la vue et la dernière écriture susceptible de toucher la profondeur ou le stencil. Les captures livrées n’associent pas ces écritures aux copies. Le premier essai finit aussi sur une fenêtre à 13,9 FPS sans blocage MSL en soumission.

À la fin de la même fenêtre 4 800, l’encodeur classe 893 209 des 1 185 320 reconstructions complètes de blocs d’arguments dans une catégorie commune (75,4 %). La condition source `g->per_draw || !g->kept` réunit les blocs contenant une table propre au dessin et les shaders sans entrée que la reconstruction partielle sait conserver. Le coût de ces deux populations, leurs dispositions et la durée de vie des données seraient nécessaires pour spécialiser leur encodage. Le pourcentage seul ne donne pas le nombre de reconstructions supprimables. Pour la voie des uniformes effectivement modifiée par 0429, les compteurs par puissances de deux confirment au moins 4 096 reconstructions en vol réussies sur la dernière session Zelda et 2 048 sur MKW. Ils ne donnent pas le temps gagné par appel sur l’iPhone.

### Mario Kart World

| Session et fin de fenêtre | FPS moteur | Images générées vues / 300 présentations | Générées vues/s, env. | Vitesse de jeu | p95 affiché |
| --- | ---: | ---: | ---: | ---: | ---: |
| Antérieure à la 844, 26 400 | 18,1 | 98 | 5,91 | 59,9 % | 83,34 ms |
| 844, 3 900 | 21,2 | 157 | 11,09 | 70,8 % | 104,18 ms |
| 26 novembre, 12 h 46, 5 100 | 21,3 | 181 | 12,85 | 62,7 % | 70,84 ms |
| Dernière session, 3 600 | 25,6 | 161 | 13,74 | 82,7 % | 62,51 ms |
| Fenêtre suivante, 3 900 | 36,4 | 38 | 4,61 | 79,0 % | 66,67 ms |

**Référence sans interpolation.** Le mainteneur rapporte environ 50 FPS avec la génération désactivée et quelques chutes à 30–40 FPS. L’archive contient indépendamment un exemple sur Mario Kart World dont l’initialisation confirme l’interpolation coupée. Dans le journal du 25 à 17 h 19, de 8 401 à 10 200, **1 800 présentations en 34,507 s donnent 52,16 FPS moteur et zéro image générée**. Le débit des six fenêtres est de 48,9 à 54,6 FPS, avec 1 217 à 1 717 dessins par image, un p95 moteur de 22,26 à 31,77 ms, un p95 affiché de 33,34 ms et une vitesse de jeu de 85,3 à 96,8 %. La fenêtre de fin 7 800 atteint 33,2 FPS dans cette même session. Ce précédent date du 25. Le [second export](#mario-kart-world-du-26-novembre-avec-vidéo) permet de vérifier directement l’essai du 26.

Dans cette séquence à 52,16 FPS, le jeu demande l’intervalle 1 sur 1 723 des 1 800 présentations. Sur la session récente avec génération, cette répartition et la charge varient fortement. Sur l’autre essai du 26 au matin, génération coupée, les trois fenêtres de fin 5 100 à 5 700 demandent toutes l’intervalle 2 sur 300 présentations et n’atteignent que 22,2, 25,1 et 23,4 FPS. La coupure du Frame Gen n’est donc pas à elle seule une garantie de 50 FPS. Ce sont le même trajet à 1× et la même préférence de cadence qui permettront de chiffrer son coût net.

Le compteur système confirme l’interpolation avant la 844, sur la 844 et sur la 845. Le changement moteur 0405 présent dans la 844 avait effectivement déplacé MetalFX et la présentation sur une file GPU dédiée. Le journal 844 confirme sa création. Sur la 845, 0418 remet cette file en option et le chemin par défaut utilise la file de rendu partagée. L’interpolation visible dans les deux configurations écarte une désactivation générale liée à ce changement. Ces sessions n’isolent pas son effet sur le débit ni la latence. Dans les deux dernières fenêtres, la période invitée vaut deux rafraîchissements pour 282 puis 91 présentations sur 300. Le chemin DisplayLink classique prend 37 puis 232 présentations. Au point de contrôle de 600 images prises en charge par le chemin d’interpolation, le moteur en a interpolé 263, en a refusé 336 selon la cadence ou le retard, et compte zéro échec de paire. iOS avait déjà confirmé 261 de ces images générées. Le mode classique réserve MetalFX aux périodes déclarées d’au moins 1/45 s et aux images arrivant dans 1,25 période. Le mode adaptatif ajouté par 0421 est une option distincte. La trace regroupe les refus pour cadence et pour retard et ne donne pas le réglage adaptatif de chaque image. Les quatre fichiers de préparation MKW comparés (référence, avancement, archives et récupération de stages) sont identiques octet pour octet entre les quatre instantanés, avec 200 recettes de pipelines et 298 entrées de stages dans la référence. Le contenu effectif des objets Metal en mémoire reste inconnu.

Les deux dernières fenêtres contiennent 70 intervalles journalisés d’au moins 50 ms, dont 63 classés en attente invitée et sept en soumission. Le GPU p50 descend de 17,88 à 11,49 ms, mais le p95 affiché reste au-dessus de 60 ms. Les deux fenêtres sont en état thermique Serious et le processus occupe 4 122 puis 4 059 Mio. Aux images 3 532 et 3 876, le registre graphique impute respectivement 2 820 et 2 548 Mio résidents au footprint, avec 772 puis 762 Mio de compression logique pour tout le processus. Les deux groupes instrumentés comptent 291 puis 294 traitements GPU MetalFX chronométrés à 11,57 puis 16,20 ms en moyenne, pour 263 images intermédiaires produites au total au second relevé. Dans `fi_job`, certaines paires arrivées trop tard sont calculées pour maintenir l’historique alors qu’aucune image intermédiaire n’est présentée. À 50 FPS natifs, une image arrive toutes les 20 ms. Ces durées mesurent les commandes de la voie d’interpolation et ne s’ajoutent pas intégralement au frametime du jeu. Ces observations expliquent une interpolation intermittente et désignent l’attente invitée comme piste pour les à-coups. Le code peut détailler certains appels de synchronisation longs. Dans la dernière session, ses 38 échantillons montrent tous un `WaitForAddress` (SVC 0x34) réveillé par un `SignalToAddress` (0x35). Le délai médian jusqu’à la sélection du thread à réveiller est de 62,498 ms. Après cette sélection, le retour de l’implémentation prend 0,009 ms en médiane. Pour les dix échantillons entre les images 3 301 et 3 900, ces deux médianes sont de 63,815 ms et 0,010 ms. L’image 3 521 en illustre le mécanisme sur le même numéro d’image que le compteur de compilation, avec 117,717 ms avant sélection, 0,013 ms après, et 0 ms d’attente pipeline ou MSL. Le sous-ensemble instrumenté est biaisé vers les longues attentes. Le travail du thread qui produit le signal, ou ce qu’il attend lui-même, reste à identifier. Raccourcir le réveil après sélection n’agirait que sur la dernière fraction mesurée. Une baisse à circuit et réglages identiques depuis la 844 reste à établir.

## Mario Kart World du 26 novembre avec vidéo

Le dernier journal MKW du second export correspond à l’identité de préparation de la 845. Dans le lancement précédent (13 h 22), le moteur confirme des images interpolées à l’écran, puis enregistre la désactivation par le joueur entre les présentations 6 815 et 6 830. Au lancement de la course filmée, l’interpolation démarre désactivée. Le jeu reste dans ce mode sur toutes les fenêtres exportées. La vidéo montre le deuxième tour sur trois, en tête, sur une piste de sable de nuit. Aucun nom de circuit n’est affiché. Le [compteur RewindBox](../../../build-utils/s2arm/engine/patches/0068-guest-display-pacing-latency-and-timing-lines.patch) en haut à droite compte les présentations de la dernière seconde et leur intervalle maximal. Il indique notamment 57, 51, 42 et 29 FPS, avec un intervalle maximal affiché de 205 ms sur l’un des échantillons.

| Portion de la dernière session 845 | Mesure | FPS moteur | Images générées vues | p95 moteur par fenêtre complète |
| --- | ---: | ---: | ---: | ---: |
| Avant capture, présentations 3 901 à 5 100 | 1 200 en 24,350 s | **49,28** | 0 | 25,95 à 31,99 ms |
| Même portion prolongée jusqu’à 5 400 | 1 500 en 29,545 s | **50,77** | 0 | 24,46 à 31,99 ms |
| Entre les deux notifications système, 5 607 à 8 184 | 2 577 en 74,86 s | **34,42** | 0 | 28,04 à 39,62 ms sur les huit fenêtres entièrement incluses |

Les quatre premières fenêtres avant capture donnent 45,2 / 48,4 / 51,1 / 53,0 FPS avec 1 295 à 2 057 dessins par image. Leur vitesse de jeu va de 78,4 à 92,6 %, leur GPU p50 de 10,68 à 14,05 ms, le temps CPU moyen en soumission de 11,87 à 15,77 ms et l’empreinte du processus de 4 020 à 4 139 Mio. La cinquième fenêtre est plus légère (525 dessins et 57,8 FPS). L’état thermique déclaré est Serious avant et pendant la capture. Les cinq fenêtres de fin 6 000 à 7 200 donnent 35,0 à 42,4 FPS. La moyenne sur les 74,86 s comprend aussi une pause de 10,06 s. La charge de dessin et la cadence demandée changent pendant le parcours. L’écart entre les deux périodes ne chiffre pas isolément le coût de l’enregistreur ou du Frame Gen.

Le journal situe les notifications à 13 h 28 min 48,689 s et 13 h 30 min 03,549 s locales. Il associe la nouvelle capture de signatures aux présentations 7 169 à 8 192 dans `profiles/20261126-133004-rec/frames.txt`. Le MOV partagé dure **18,955 s** et contient 676 images encodées (35,66/s). Le débit du fichier vidéo dépend de l’enregistreur. Les cadences moteur du tableau sont calculées sur les horloges des présentations dans le ZIP.

| Présentation pendant la capture | Intervalle moteur | Où passe le temps |
| --- | ---: | --- |
| 6 090 | 176,3 ms | 175 premières mises en mémoire de textures, 53,3 Mio en 109,405 ms sur le chemin CPU. Les lectures de textures rencontrent 1 230 pages absentes de la mémoire. GPU 22,2 ms et attente pipeline nulle. |
| 7 286 | 10 055,1 ms | 10 043,716 ms avant que le thread invité 180 signale l’adresse attendue, puis 0,018 ms jusqu’au retour de l’implémentation. GPU 16,8 ms et attente pipeline nulle. Le déclencheur de cette longue pause est inconnu. |
| 7 746 | 149,3 ms | 136 premières mises en mémoire de textures, 49,4 Mio en 110,612 ms sur le chemin CPU. Les lectures de textures rencontrent 3 363 pages absentes de la mémoire. Le GPU dure 17,7 ms et l’attente pipeline est nulle. |
| 7 954 | 204,6 ms | 184,273 ms d’attente pour un pipeline de rendu demandé au premier dessin. Le GPU dure 23,5 ms. Les compteurs de compilation et d’attente de bibliothèque MSL sont à zéro. L’intervalle s’arrondit aux 205 ms visibles sur le compteur. |

Les lignes détaillées `RewindBox cup frame` contiennent 23 intervalles d’au moins 50 ms entre les deux notifications. Quatre consacrent au moins 5 ms à l’attente pipeline et deux au moins 5 ms aux chargements de textures sur le chemin CPU. Sur les 23 lignes, les compteurs correspondants totalisent respectivement 328,8 et 225,8 ms. Entre les relevés 7 500 et 7 800, les lectures de textures rencontrent 3 820 pages supplémentaires absentes de la mémoire, dont 3 363 sur la seule image 7 746. Le moteur avait demandé une prélecture dès l’enregistrement de 14 890 textures au premier relevé. Ce compteur conserve la même valeur au second. Le moteur ne donne pas la correspondance entre chaque texture de cette image et un préchargement antérieur. La disponibilité des pages source au premier usage est donc mesurable indépendamment du temps de compilation, tandis que l’efficacité d’un autre moment de prélecture reste à évaluer.

La préparation de départ signale 1 429 entrées prêtes sur 1 429 en 2,751 s. La recette complète du pipeline de l’image 7 954 est absente des 200 recettes de référence de cette session lors d’une comparaison octet par octet. Sa clé apparaissait dans dix journaux MKW antérieurs, sept fois dans des sessions avec recherche à la demande et trois fois comme préparée. Ces journaux antérieurs ne publient pas la ligne sérialisée de cette clé. Le moteur maintient aussi un historique utilisateur et une liste prioritaire, dont l’état complet de ce lancement manque.

Une simulation a réservé le dernier lancement pour l’évaluation, en construisant les listes uniquement avec les 48 journaux MKW datés antérieurs. Pour chaque clé de rendu et chaque session, elle retient l’attente maximale au premier dessin à la demande, à partir de 5 ms. Au total, 3 532 clés distinctes remplissaient cette condition auparavant. Dans la dernière session, 20 clés cumulent 5 803,4 ms selon cette mesure. Parmi les 32 clés classées par nombre de sessions antérieures puis durée cumulée, une seule réapparaît, celle de l’image 7 954 (184,3 ms). Avec 64 ou 256 places, deux réapparaissent (193,7 ms). Le classement par occurrence récente couvre zéro clé à ces trois tailles. Le classement par durée d’attente cumulée en couvre respectivement zéro, zéro et une (6,1 ms). Parmi les 20 clés du lancement tenu à part, quatre seulement disposent d’une recette sérialisée dans les lignes de capture des 48 journaux antérieurs, pour 151,5 ms d’attentes associées au total. La couverture inclut des journaux de plusieurs versions et suppose les recettes exactes disponibles. Elle mesure un recoupement de clés, sans chronométrer la compilation anticipée. Les résultats ne justifient pas d’allonger globalement la préparation au lancement.

**Reproduction du second export.** Les [52 fenêtres](recording-windows.csv) couvrent les trois nouveaux journaux MKW. L’analyse et le tableau de couverture se reproduisent avec les fichiers reçus, sans ajouter de journal privé ni de recette au dépôt.

```sh
k=engine/0400C3F00006E000
python3 windows.py engine.zip "$k/host-20261126-131749.log" "$k/host-20261126-132220.log" "$k/host.log" > regenerated.csv
cmp recording-windows.csv regenerated.csv
python3 pipeline_history.py engine.zip
ffprobe -v error -select_streams v:0 -show_entries stream=duration,nb_frames,avg_frame_rate 'ScreenRecording_11-26-2026 13-28-48_1.mov'
```

| Fichier du second envoi | SHA-256 |
| --- | --- |
| engine.zip | `780b302a0e0620de3b86db4fca71e18d5e1c6648a32e0cb428d6686e6a4c2aad` |
| profiles.zip | `39854ce51960622ce52cf97d270ca25d353465ae23cd698e77c32c36ffab073f` |
| Vidéo MOV | `299066fc937befa784ee2721a057c03bf47458d129b07a67880308370c06fda4` |

## Vérification du moteur iOS

Les trois révisions successives ont passé `make ios`, l’inventaire des images et symboles, les contrôles des points d’entrée et des licences sur macOS 15 et 26. La chaîne a compilé le moteur sans jeu et sans nouvelle IPA. La référence 845 installée reste en 0426. [0427–0428 · e5c529689](https://github.com/TarbleFR/RewindBox/actions/runs/45816355035) · [0429 · db2dc765b](https://github.com/TarbleFR/RewindBox/actions/runs/45817878462) · [0430 · 17d04c5d7](https://github.com/TarbleFR/RewindBox/actions/runs/45820002605).

## Validation sur appareil

Pour attribuer un effet aux changements 0427 à 0430, il manque les mêmes parcours à 1×, à qualité et horloge invitées identiques, avec état des caches et état thermique appariés. Le [protocole existant](../../s2arm-benchmark-protocol.md) prévoit trois passages de 180 s par variante, ordre alterné, médianes et dispersion. Les parcours chauds et les premières rencontres constituent des essais distincts. Sur Mario Kart, utiliser la génération désactivée pour comparer les révisions du moteur. Mesurer ensuite son coût sur la même révision et le même parcours, d’abord en mode classique et, s’il est utilisé, séparément en mode adaptatif. Conserver côte à côte cadence moteur et vitesse du jeu, images générées confirmées, distribution des intervalles demandés et temps MetalFX. Pour les écritures et copies de textures, il manque également un replay de référence avec sorties couleur, profondeur et stencil comparables. Le gain de FPS, l’empreinte mémoire du candidat, la vitesse obtenue et la fidélité de ses images sur iPhone restent non mesurés.
