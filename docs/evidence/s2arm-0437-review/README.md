# S2Arm 0437–0447, contre-expertise et reprise du 26 novembre 2026

La référence de comparaison de cette série est le moteur 0436 au commit RewindBox `8be902ac0`. Les charges sont générées localement. Pour la comparaison avec le point de départ 0426, les résultats du banc d’uniformes figurent dans [les paires supplémentaires](uniform-0426-final.csv).

## Résultats des sources retenues

| Série active | Travail | Résultat vérifié |
| --- | --- | --- |
| 0437 | Copier les blocs de texture de 64 octets × 8 rangées dans l’ordre du stockage invité, pour les deux ordres GOB. Les adresses de colonne sont calculées uniquement pour les colonnes existantes. | Comparaison du chemin public dans les deux sens, y compris gardes, pitch, plusieurs couches, mips, volume, tuiles entières ou partielles. 4 912 comparaisons et 151 035 040 octets identiques, ASan et UBSan actifs. |
| 0438 | Grouper les métadonnées des soumissions pour la reconstruction des uniformes et initialiser à la première écriture les mots de validité. | Structure complète de 2 936 848 octets dans les deux versions. Le test sur 1 800 cycles de réemploi retrouve les octets attendus. Sur six charges de 26 paires, deux montrent une baisse du temps avec intervalle à 95 % excluant zéro (−3,94 % et −2,08 %). [Paires Linux](uniform-pairs.csv) |
| 0439 | Vérifier directement les handles du premier bloc et traiter une bande de pages en un accès lorsque la demande tient dans celle-ci. | Ordres atomiques conservés et 96 octets par plage dans les deux versions. Sur 1 million de requêtes à 5 000 pools, 33,05 → 31,58 ms sur Linux. Une seule petite plage de 16 pages donne 16,44 → 16,48 ms. Le contrôle concurrent avec deux producteurs passe sous ASan et UBSan. |
| 0440 | Calculer ensemble le décalage, les dimensions de blocs et l’éventuel pas de couche d’un niveau de texture. Le décodeur CPU et la soumission du décodeur GPU partagent ces valeurs. | 36 000 descripteurs comparés, y compris niveaux sentinelles, empreinte identique. Le test chronométré appelle le calcul CPU préparant les transferts. |
| 0441 | Rétablir les opérations FP32 de référence dans les noyaux du calcul de mouvement de MetalFX. Les décisions de cadence et d’amorçage de 0432 restent actives. | Sur les entrées R16Float du contrôle C, l’accumulation FP16 conserve 128 translations exactes sur 128, mais choisit un autre vecteur pour 2 des 128 blocs sans correspondance exacte. Le code MSL du candidat est identique octet par octet à celui précédant 0432. |

Le banc Linux x86-64 (Clang 18.1.3) utilise un échauffement puis douze paires par charge, avec ordre pseudo-aléatoire fixe et affinité CPU 1. Le temps médian de conversion CPU de 88 081 152 octets, contrôles et premier aller-retour inclus, passe de **50,44 à 26,35 ms**. Pour 200 000 requêtes de géométrie, les médianes sont **99,19 et 14,87 ms**. Les temps CPU sont spécifiques au banc et à l’hôte. Les comparaisons portent sur les sources de 0436 et de la série finale. [Mesures Linux par paire](linux.csv)

## Reproduction

Depuis ce dossier, passer deux arbres S2Arm préparés, arrêtés respectivement à 0436 et à 0441. Le test de parité compile séparément toutes les fonctions de copie et de géométrie de la référence pour éviter qu’elles appellent le candidat.

```sh
python3 compare.py /chemin/0436 /chemin/0441 timings.csv
clang -std=c11 -O2 motion.c -o /tmp/s2-check-motion
/tmp/s2-check-motion
```

La recette moteur peut effectuer le même contrôle sur macOS avec le marqueur explicite `[s2arm-compare-upload]` associé à `[s2arm-engine]`. Elle compile le MSL embarqué avec le SDK iPhoneOS puis, si le runner expose un GPU compatible, compile les cinq pipelines et compare les sorties du noyau de mouvement sur macOS. Le contrôle distingue indisponibilité de l’appareil et résultat incorrect. Aucun jeu ni IPA n’intervient.

## Contre-expertise des brouillons

Les numéros des expériences antérieures à la reprise sont distincts de la série active ci-dessus. Les sources originales et les mesures exploratoires sont sauvegardées dans [drafts](drafts). Les projections de ce dossier sont des hypothèses archivées. Elles ne valident ni les performances, ni l’énergie, ni les caractéristiques physiques d’un iPhone.

- **0437 expérimental** formait un pointeur au-delà du dernier bloc à la sortie de certaines boucles. La série active le corrige. Deux noyaux plus compacts ont également été essayés sur les mêmes entrées, puis écartés après comparaison au meilleur intermédiaire.
- **0438 expérimental** changeait le sous-ensemble évincé quand plus de 16 alias se recouvrent. Sur 17 alias, l’entrée survivante passe de 1 à 9. Une écriture du dessin mesh sur le slot Metal 29 pouvait aussi rester active pour le flux vertex 13 du dessin suivant.
- **0439 expérimental** pouvait conserver une table de dimensions de texture après changement d’un handle indirect en UBO. Le contrôle existant de réutilisation partielle ne couvre pas toutes ces omissions. La sélection de textures par UBO est un cas de régression à vérifier pour toute future révision.
- **0440 expérimental** retardait certaines soumissions en cours de passe. Le chemin concerné décide une coupe quand le compteur de segments GPU en vol est nul. Les seuls comptes de coupes ne suffisent pas pour prévoir le temps d’inactivité GPU ou le coût des stores Metal.
- **0441 expérimental** fournit le changement retenu en 0438. **0442 expérimental** augmentait la taille des plages à 128 octets et affaiblissait certains ordres atomiques. La variante 0439 active conserve la représentation et les ordres d’origine. **0443 expérimental** fournit la géométrie de 0440. Son déroulage du contrôle de tuile vide ralentissait le cas où le premier octet est non nul, de 2,53 à 3,26 ms par million de tuiles, et a été retiré.
- **0444 expérimental** omettait de restaurer viewport et scissor en quittant la projection élargie. Le corps extrait de la fonction produit des commandes différentes. Le correctif de laboratoire et ses traces synthétiques sont décrits dans les [notes de contre-expertise](drafts/notes.md). La propagation de toutes les invalidations dans le véritable encodeur reste à établir.

La série 0441 a compilé pour iOS sur les deux runners macOS. Sur macOS arm64, douze paires donnent **60,475 → 22,770 ms** pour la conversion de textures et **76,561 → 10,112 ms** pour la géométrie. Le compilateur iPhoneOS produit l’AIR du shader embarqué. Le périphérique « Apple Paravirtual device » crée les cinq pipelines dans chaque version et exécute les deux niveaux du calcul de mouvement. Sur trois scènes, la version FP16 change deux vecteurs. Sur 387 blocs, le candidat retrouve chaque vecteur et chaque score FP32. [Résultats du banc](macos-0441.txt) et [compilation 0441](https://github.com/TarbleFR/RewindBox/actions/runs/45851312226).

## Tables de bornes, substitutions et clés des pipelines

Les références sont le point de départ 0426, la série 0436 et les fonctions de 0441 avant chaque modification isolée. Les mesures ci-dessous utilisent Clang sur Linux x86-64. La valeur p95 porte sur un lot de travail CPU. Le coût de compilation Metal, l’image présentée et le délai de présentation sont des mesures distinctes.

| Patch | Charge synthétique et exactitude | Résultat CPU |
| --- | --- | --- |
| 0442 | Tables de bornes des uniformes et des buffers de stockage. L’arène conserve déjà l’adresse CPU et GPU de chaque tampon. Vérification de l’adresse et des 256 octets à chaque appel, pour 8 192 appels avec rotations, adresses nulles, limites de capacité et longueurs extrêmes. | Sur 64 paires de 500 000 reconstructions d’uniformes, médiane des différences relatives de −23,6 % face aux fonctions précédentes et de −20,5 % face à 0426. Les ordres de compilation inversés confirment le sens. Le témoin A/A a un biais et le cas cache stable reste indécidable. [Comparaison sur 0441](bounds/results/summary.txt) et [paires sur 0426](bounds/results-0426/forward.tsv). |
| 0443 | Actualiser en place les substitutions de textures de lecture du fragment. La comparaison couvre les identités source, destination et ressource, les six drapeaux d’invalidation, les compteurs et la sortie du chemin de substitution. Une empreinte porte sur tous les états intermédiaires de 200 000 transitions. | Pour 1 048 576 appels sans substitution, médianes 6,98 / 6,96 / 3,96 ms sur 0426 / 0436 / candidat. Avec quatre substitutions changeantes, 11,94 / 11,96 / 10,80 ms. Deux variantes intermédiaires pénalisaient ce cas. [26 paires par charge](feedback/three-source.csv). |
| 0444 | La clé créée à zéro contient déjà les seuls attributs et flux lus par le vertex shader. Supprimer le second balayage pour une clé fraîche. Conserver la normalisation des clés persistées. Empreinte fixe sur 65 792 clés de 344 octets, comparaison des recherches, des ratés et des objets retournés. | À cache froid, la médiane du p95 par lot de 256 requêtes CPU est de 0,174 / 0,184 / 0,131 ms sur 0426 / 0436 / candidat. À chaud, 0,141 / 0,134 / 0,093 ms. Le filtrage supplémentaire des copies de mélange est écarté après ralentissement par rapport à 0444. [29 paires par charge](pipeline/three-source.csv) et [variante écartée](pipeline/blend-samples.csv). |

Les sources du banc extraient les fonctions de chaque arbre préparé. Les index de `three-source.csv` correspondent dans l’ordre à 0426, 0436, puis au candidat. Les quatre colonnes d’identité du programme de pipelines et les sept paires de fixtures de commandes NVN sont entièrement synthétiques. Les sept paires buffer, clear, triangle, texture, profondeur, MRT et dispatch ont été régénérées à l’identique avec `CC=clang bash android/tests/replay_fixture/run_test.sh` et le convertisseur de textures du candidat. Cette dernière épreuve vérifie un format et des commandes attendues, sans exécution GPU.

```sh
python3 bounds/compare_ubolen.py /chemin/0441 /chemin/candidat resultats-bornes
python3 bounds/report.py resultats-bornes/{forward,reverse,control}.tsv
python3 feedback/replay.py /chemin/0426 /chemin/0436 /chemin/candidat --csv feedback.csv
python3 pipeline/replay.py /chemin/0426 /chemin/0436 /chemin/candidat --csv pipeline.csv
```

Le [référentiel matériel autonome](../../../tools/s2arm_a18pro/referentiel_a18pro_autonome.json) relie chaque caractéristique aux publications d’Apple ou au résultat public identifié. Le [banc Linux](../../../tools/s2arm_a18pro/bench_suite.py) conserve les délais bruts et les compteurs Cachegrind, avec la portée de chaque module. Les paramètres A18 Pro insuffisamment documentés restent inconnus.

Sur Mac arm64, la médiane du p95 du lot CPU de 256 recherches passe de **0,244 à 0,206 ms à froid et de 0,193 à 0,158 ms à chaud**. La charge de feedback à quatre substitutions changeantes est sensiblement neutre (19,77 / 20,03 ms). Les reconstructions UBOLEN ordinaires s’améliorent dans les deux dispositions de code. Pour le cache facultatif stable, la disposition inversée donne un ralentissement et le témoin A/A est dispersé. Ce résultat motive une deuxième comparaison sur un autre runner. [Sorties Mac 0444](macos-0444.txt) et [compilation](https://github.com/TarbleFR/RewindBox/actions/runs/45852944537).

## Synchronisation de la présentation et Frame Gen

Les deux manifestes livrés 843 et 844 permettent de reconstruire le code du sélecteur et la trajectoire de présentation. Il prend les mêmes décisions sur **1 412 190 entrées synthétiques**, dont 165 632 admissibles. La 844 peut utiliser une file Metal dédiée. Le code exposait alors un défaut de durée de vie de l’image, même lorsque le sélecteur prenait la bonne décision.

- **0445.** En cas d’échec de la seconde présentation après soumission de la première, le moteur rendait le ticket trop tôt. Chaque lecture soumise conserve désormais la source jusqu’à son propre retour GPU. La file vérifie à nouveau sa capacité quand deux producteurs reprennent le mutex. Sur 1 920 scénarios de l’hôte simulant ces retours, les divergences passent de 681 à zéro. Sur 8 000 tickets, l’ordre de libération et la limite de huit sont respectés. Le banc couvre aussi l’arrêt et l’expiration du délai de vidage. Le lien entre ce défaut et les FPS d’un jeu n’est pas établi. [Source, protocole et données](present/README.md).
- **0446.** À la fermeture d’une session, le moteur retire le jeu de ressources de la couche de la même file Metal que celle utilisée pour son inscription. Sur cinq séries de 300 sessions, 100 inscriptions par série restaient actives dans le témoin à file dédiée, contre zéro après correction. Le contrôle porte sur le dernier jeu inscrit par session. Les octets résidents chez le pilote et le comportement lors de changements successifs de couche pendant une session restent à établir. [Résultats pour les deux files](present/results/residency.tsv).

## Rendu d’un homebrew public

Le fragment du triangle de switchbrew `deko_basic` est compilé avec devkitPro/uam et traduit par S2Arm à partir du bytecode Maxwell. Sur Linux, Vulkan logiciel restitue les mêmes 4 096 pixels que le GLSL compilé indépendamment. Le second fragment synthétique restitue ses 4 096 pixels et le calcul de copie retrouve 64 mots. Cinq passages avec l’entrée figée après échauffement retrouvent les mêmes 25 empreintes. La médiane de 0,795 s couvre le lancement de toute la chaîne d’outils Linux. La recette fournit le shader libre, sa provenance, les commandes et les références binaires. [Reproduction et licences](homebrew/README.md).

## Contrôle des plateformes et coût des transferts GPU

Les trois shaders homebrew ou synthétiques ont aussi compilé pour iPhoneOS et ont chacun produit **six résultats Metal** identiques à l’oracle Vulkan sur le périphérique paravirtualisé du Mac. Un contrôle adjacent a détecté deux erreurs de compilation. Le témoin d’archive 793 tentait de compiler un test dédié à une interface ajoutée depuis. La correction laisse ses vérifications historiques actives et exécute le contrôle de cette interface sur l’implémentation courante. Le patch **0447** garde la limite de 512 Mio sur iOS et évalue sur Mac le budget Metal avant de créer une texture de stencil auxiliaire. [Sorties de lecture retour](homebrew/metal-results.txt) et [vérification ayant détecté les deux erreurs](https://github.com/TarbleFR/RewindBox/actions/runs/45854512345).

Le banc de textures soumet le shader réel et compare tout le tampon, padding compris, à l’implémentation d’adressage CPU. Sur cinq charges, 12 paires comparent un, deux, quatre et huit blocs de 512 octets par threadgroup. Les médianes favorisent parfois quatre mais les intervalles appariés incluent zéro. La confirmation garde le shader et les entrées identiques, augmente à 36 paires de 64 transferts et inclut un deuxième témoin de largeur un. Aucun changement de géométrie du moteur n’est retenu à ce stade. [240 relevés GPU de la première série](gpu-textures/macos.csv).

## État de reprise

La piste de vidage des tables au changement d’image est retirée de la phase autonome après consultation d’une archive personnelle pendant son exploration. Son code et ses résultats sont exclus. La prochaine comparaison de compilation de pipelines utilise uniquement les shaders générés par le banc.

Les candidats modifient les copies de textures et la gestion des métadonnées CPU sans réduire la résolution de rendu, la qualité demandée ou l’horloge invitée. Les nouveaux FPS moteur et générés, le frametime, les pixels du jeu, la RAM réelle, la chauffe et la consommation attendent une mesure sur appareil. Les pistes de soumission à GPU vide, de prélecture des pages de textures, d’encodage des arguments et de compilation en cours de partie restent ouvertes.
