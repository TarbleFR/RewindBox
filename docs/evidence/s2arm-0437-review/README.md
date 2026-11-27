# S2Arm 0437–0450, contre-expertise et reprise du 26 novembre 2026

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

Le patch **0448** précise le libellé du compteur historique, qui inclut aussi les intermédiaires copiés. Une compilation de diagnostic peut distinguer les sorties MetalFX effectivement présentées des copies et des coupures. Les deux ordres de notification GPU/écran sont couverts sur Linux. La compilation ordinaire y conserve exactement le code machine des callbacks de référence. [Protocole et limites des mesures](present/observation/README.md).

## Rendu d’un homebrew public

Le fragment du triangle de switchbrew `deko_basic` est compilé avec devkitPro/uam et traduit par S2Arm à partir du bytecode Maxwell. Sur Linux, Vulkan logiciel restitue les mêmes 4 096 pixels que le GLSL compilé indépendamment. Le second fragment synthétique restitue ses 4 096 pixels et le calcul de copie retrouve 64 mots. Cinq passages avec l’entrée figée après échauffement retrouvent les mêmes 25 empreintes. La médiane de 0,795 s couvre le lancement de toute la chaîne d’outils Linux. La recette fournit le shader libre, sa provenance, les commandes et les références binaires. [Reproduction et licences](homebrew/README.md).

## Contrôle des plateformes et coût des transferts GPU

Les trois shaders homebrew ou synthétiques ont aussi compilé pour iPhoneOS et ont chacun produit **six résultats Metal** identiques à l’oracle Vulkan sur le périphérique paravirtualisé du Mac. Un contrôle adjacent a détecté deux erreurs de compilation. Le témoin d’archive 793 tentait de compiler un test dédié à une interface ajoutée depuis. La correction laisse ses vérifications historiques actives et exécute le contrôle de cette interface sur l’implémentation courante. Le patch **0447** garde la limite de 512 Mio sur iOS et évalue sur Mac le budget Metal avant de créer une texture de stencil auxiliaire. [Sorties de lecture retour](homebrew/metal-results.txt) et [vérification ayant détecté les deux erreurs](https://github.com/TarbleFR/RewindBox/actions/runs/45854512345).

Le banc de textures soumet le shader réel et compare tout le tampon, padding compris, à l’implémentation d’adressage CPU. Sur cinq charges, 12 paires comparent un, deux, quatre et huit blocs de 512 octets par threadgroup. Les médianes favorisent parfois quatre mais les intervalles appariés incluent zéro. La confirmation garde le shader et les entrées identiques, augmente à 36 paires de 64 transferts et inclut un deuxième témoin de largeur un. Aucun changement de géométrie du moteur n’est retenu à ce stade. [240 relevés GPU de la première série](gpu-textures/macos.csv).

Le constructeur de pipelines Metal classique a mesuré douze premières utilisations pour chaque combinaison sur Mac paravirtualisé. Les médianes sont de 3,428 ms pour deux shaders encore inutilisés dans le processus, 1,175 ms quand seul le fragment est nouveau, 0,040 ms pour une nouvelle combinaison de shaders déjà utilisés et 0,046 ms pour une combinaison répétée. Elles excluent le chargement des bibliothèques. Le cache persistant du pilote au début de la mesure est inconnu. Le nouveau contrôle mesure aussi le premier usage du vertex seul, préalable à une comparaison des ordres de préchauffage à budget égal. [Relevés de compilation](pipeline/driver-mac.csv) et [exécution Apple](https://github.com/TarbleFR/RewindBox/actions/runs/45856161335).

Une deuxième série a mesuré les cinq classes avec le même pilote Metal classique. La première utilisation d’un vertex seul prend en médiane 2,057 ms et celle d’un fragment seul 1,779 ms (douze paires). Un essai de changement d’ordre choisit en priorité des shaders encore absents parmi les recettes de pipelines de même urgence. À budget de démarrage identique, ce modèle réduit l’attente cumulée dans 32 scénarios, l’allonge dans 28 et donne une égalité dans 84. La hausse atteint 6,25 ms dans le scénario le plus défavorable. Le moteur conserve son ordre actuel. [Temps Metal](pipeline/stages-mac.csv), [essai de préchauffage](pipeline/warm-order.md) et [run Apple](https://github.com/TarbleFR/RewindBox/actions/runs/45857419891).

Les quatre variantes de sélection des buffers de constantes testées sur Linux accélèrent les cas avec beaucoup de slots liés mais ont chacune une médiane plus élevée dans le cas avec un seul slot lié par étage. Elles restent dans les expériences écartées. [Treize triplets par scénario, sources et limites](drafts/widen-mask/README.md).

La compilation iPhone du moteur ordinaire et de la bibliothèque NVN avec observation FI active a réussi avec le SDK Apple sur le runner macOS 26. Le format de diagnostic a aussi été retrouvé dans la bibliothèque dédiée. [Compilation iPhoneOS](https://github.com/TarbleFR/RewindBox/actions/runs/45857941999).

Le patch **0449** évite les transpositions redondantes dans la reconnaissance des projections du mode grand écran. Sur 24 triplets NativeAOT macOS arm64, le lot de 131 072 fenêtres mixtes passe de 38,70 à 33,29 ms de temps CPU médian. La contre-expertise compare deux points d’entrée, 17 compteurs, les deux orientations, les exceptions et les cas IEEE. Les FPS et la part de ce chemin dans les jeux restent non mesurés. [Comparaison et reproduction](matrices/README.md).

La confirmation des transferts GPU a comparé quatre blocs par groupe au témoin d’un bloc et à une seconde exécution du même témoin. Sur les cinq configurations, les intervalles appariés recouvrent zéro, aussi bien face au premier qu’au second témoin. Les 540 lots de 64 dispatchs ont tous produit les octets attendus. Le moteur conserve un bloc par groupe. [Données Apple](gpu-textures/macos-confirm.csv) et [exécution](https://github.com/TarbleFR/RewindBox/actions/runs/45855847861).

Une deuxième machine Mac reproduit le gain CPU du chemin UBOLEN ordinaire dans les deux dispositions du binaire (−29,04 % et −28,74 %). Elle reproduit aussi le coût supérieur de la disposition inversée sur le cache facultatif stable (+12,94 %). Un premier candidat pour ce cas compare chaque borne effective au fur et à mesure et ralentit le cas stable sur Linux. Les contrôles renforcés distinguent désormais hits et misses et les changements de bloc dans une même génération. Une variante plus simple conserve le calcul antérieur des limites et la réutilisation des adresses d’arène. [Confirmation Mac](bounds/mac-repeat.txt) et [essai Linux](bounds/stable/README.md).

L’adaptateur iOS crée sa couche Metal une seule fois et déplace cette même couche à la rotation et au changement d’écran. Les commandes d’interpolation sont soumises avant que la présentation classique ne rende la main. La contre-expertise écarte donc le remplacement de couche comme cause démontrée des à-coups sur cet iPhone. Un hôte qui remplace réellement l’objet ou son périphérique doit tenir compte du propriétaire du drawable fourni et de l’identité exacte du jeu de ressources enregistré. [Contrat du drawable](https://developer.apple.com/documentation/quartzcore/cametaldrawable/layer) et [application du jeu de ressources aux commandes](https://developer.apple.com/documentation/metal/mtl4commandqueue/removeresidencyset(_:)).

## État de reprise

La piste de vidage des tables au changement d’image est retirée de la phase autonome après consultation d’une archive personnelle pendant son exploration. Son code et ses résultats sont exclus. La prochaine comparaison de compilation de pipelines utilise uniquement les shaders générés par le banc.

Les candidats modifient les copies de textures et la gestion des métadonnées CPU sans réduire la résolution de rendu, la qualité demandée ou l’horloge invitée. Les nouveaux FPS moteur et générés, le frametime, les pixels du jeu, la RAM réelle, la chauffe et la consommation attendent une mesure sur appareil. Les pistes de soumission à GPU vide, de prélecture des pages de textures, d’encodage des arguments et de compilation en cours de partie restent ouvertes.

Le patch **0450** corrige le placement en mémoire des écritures de régions sur une cible de rendu linéaire. Sur 288 régions portant le flag 0x40 seul, le mauvais adressage touche 208 écritures et leurs relectures avant correction, zéro après. Les 576 cas avec les deux autres configurations demeurent exacts. [Protocole sur les fonctions du moteur](linear-flags/README.md).

La copie contiguë générique des textures linéaires est écartée après la comparaison des octets sur deux vues des mêmes pages. Les durées Mac et Linux ont été conservées, avec le contre-exemple et la reproduction. [Résultats](linear-textures/README.md).

La cadence hors écran du homebrew a été mesurée sur 4 320 dessins. La file à trois commandes finit le travail plus vite sur l’hôte, mais 99 durées GPU individuelles sont indéterminées sur ce bras. Les p95 GPU ne sont pas comparables. Le banc des bornes confirme en parallèle un gain du chemin ordinaire et un surcoût du mode facultatif de réutilisation pour des capacités stables. [Cadence et mémoire](homebrew/pacing/README.md), [huit charges sur les bornes](bounds/clamp/README.md) et [expérience sur les pages de texture](linear-pages/README.md).

## Série 0451–0463 : boucle d’optimisation autonome A18 Pro et contre-expertise

Les 13 correctifs `0451–0463` prolongent `0450` sur tous les étages du moteur (transferts linéaires, hachages, état dynamique render, traducteur Dsh/SPIR-V, descripteurs HLE, thread d’encodage, chemins GPU/mesh, synchronisation noyau/VM et RomFS), sans aucune règle spécifique à un jeu et sans exploiter de mesures personnelles utilisateur.

| Patch | Portée | Mesure hôte / Metal vérifiée (avant → après) | Parité / sanitizers |
| --- | --- | --- | --- |
| 0451 | `hle_nvn.c` écritures CPU linéaires partielles | macOS arm64 (`45863044570`) + Linux : petites linéaires −78,0 % à −92,0 %, queue 1080p jusqu’à `3 527×`, tas `8,29 Mo → 0 o` | 3 024 + 79 cas d’alias/refus/OOM, 0 écart (ASan+UBSan) |
| 0452 | `nvn_mtl.m` pages sales linéaires + staging serré | Metal macOS (`45863044570`) : `bytes_encoded −66,7 %` à `−74,0 %` ; Linux `1080p-rgba-1pg` `195,19 → 0,196 ms` (`997×`), staging `8,29 Mo → 16 Kio` | `7 680/7 680` pixels Metal exacts (`bad_surfaces 5/6 → 0/6`), rollback `g_nup_blits` |
| 0453 | `nvn_hmap.h` hash8 + ILP 4 voies (`≥ 128 o`) | Linux `-O2` : 8 o `7,452 → 4,298 ms` (`−42,3 %`, `1,73×`) ; 344 o `g_pso` froid `−30,3 %`, chaud `−32,8 %` | `nvn_hm_hash` bit-exact, ordre `g_alias` 56 o conservé, `t_hmap` vert |
| 0454 | `nvn_mtl.m` `span_hash` ILP 4 voies | Linux `-O2` : GOB 512 o `19,36 → 8,14 ms` (`2,34×`), page 16 Kio `29,76 → 9,84 ms` (`3,01×`) | Bit-identique sur tous alignements (ASan+UBSan) |
| 0455 | `nvn_mtl.m`, `rt_range_check.inc` masque `g_rb_ed_dirty` | Linux `-O2` : régime établi `−80,5 %` (`5,1×`), churn 25 % `−73,7 %` (`3,7×`), churn 50 % `−56,6 %` (`2,3×`) | 200 000 dessins adversariaux SHA-256 exact, garde inconditionnelle `NVN_FACE_FRONT_AND_BACK` |
| 0456 | `S2A.Dsh` regex cache + MSL $O(L)$ + SPIR-V 1 passe | Linux .NET 10 : `Py.Rc` `4 096 → 50`, `FsLb`/`FsRd`/`FsUvx` `296,6 → 50,3 ms` (`5,89×`, alloc `−95,8 %`), `IntInputs`/`FsUint` `−69,5 %`, SPIR-V `531,4 → 145,7 ms` (`3,65×`, alloc `−92,3 %`) | `t_dsh_fn.py` `4 314/4 314`, `DirectCompiler.Tests` `328/328`, `xfp_single_source_test.sh` (`ed1bab862c12fb97`) |
| 0457 | `hle_nvn.c` `dpool_tab` sans verrou + `sh_overwrite` + `gfx_leave` | Linux `-O2` : `sh_overwrite` `7,104 → 0,964 ms` (`−86,4 %`, `7,37×`), verrous `384 000 → 3 200` (`−99,2 %`) | Corrige UAF/course `dpool_base`, ASan+UBSan+TSan propres |
| 0458 | `nvn_rec.h`, `nvn_session.inc` drainage en rafale | Linux `-O2` : `4,383 → 2,993 ms` (`−31,7 %`, `1,46×`), verrous `5 761 → 248` (`−95,7 %`), `thr_lv_take` `−91,4 %` | Somme exacte (`1 108 869 120`), `g_rb_idle_waiters` (incl. `ETIMEDOUT`), TSan propre |
| 0459 | `nvn_mtl.m` `fpd`/`mdxchk` opt-in, `draw_emit` `*avail`, `nvn_hmap`, `dispatch_enc` | Suppression barrière GPU blit par pièce hors opt-in et `objc_msgSend`/`NSData` chauds | `pool_buf_end` = `mb.length - mo`, `hm_put_id` ARC-safe, `rp_begin_ex_` appelle `args_dirty_all()` |
| 0460 | `nvn_mtl.m`, `nvn_geometry.inc`, `nvn_session.inc` cache mesh PSO + tables | Cache 1 entrée `g_cur_mtk_ps`, `zero_bank_gpu()`, `g_enc_mtk_tab`, préservation étage 1 & `g_rb_ed_dirty` | Contre-expertise : invalidation `g_cur_mtk_ps` sur dessin classique et fermeture de session |
| 0461 | `thread.c`, `loader.c` `wait_unlink` $O(1)$, `SignalToAddress`, `wq_flush`, cache MKW | Linux `-O2` : `SignalToAddress` 64 threads `61,744 → 25,864 ms` (`−58,1 %`, `2,39×`) | 200/200 cas de parité, `wq_flush` garanti sur toutes sorties (ASan+UBSan) |
| 0462 | `svc_mem.c`, `far.c` unmap fusionné + scan `g_amask` 64 bits | Linux `-O2` : `1 022` pages libérées `→ 3` appels (`−99,7 %`) ; `QueryMemory` 16 Gio `165,03 → 17,11 ms` (`−89,6 %`, `9,65×`) | 13/13 cas limites, scission `s2a_guest_in_file` et `CHUNK` (ASan+UBSan) |
| 0463 | `RomFsIndex.cs`, `Application.cs` curseur + `LazyHostFile` | Linux .NET 10 : `IndexedStorage` `14,473 → 2,077 ms` (`−85,7 %`, `6,97×`) ; `LazyHostFile` `151,99 → 138,76 ms` (`−8,7 %`), alloc GC `832,3 → 256,2 Kio` (`−69,2 %`) | 182 626 lectures parité + `S2A.Services.Tests` `--romfs-symlink` et `--romfs-read-integrity` 6/6 |

Les FPS, le temps GPU en jeu, la chauffe et la consommation sur iPhone 16 Pro Max (A18 Pro) restent **non mesurés** à ce stade ; aucune projection physique n’est convertie en FPS. Les preuves macOS arm64 / Metal du run `45863044570` sont conservées dans [`linear-region/`](linear-region/) et [`linear-pages/macos-run-45863044570.txt`](linear-pages/macos-run-45863044570.txt).

## Série 0464–0467 : reprise autonome S2Arm (encodage d’arguments, liaison sommets et soumission zéro-ARC)

Entrées utilisées exclusivement : code moteur épinglé (`6b6a571` + `0001–0463`), preuves synthétiques de ce dossier et de `tools/s2arm_a18pro`, référentiel public attribué et homebrew libre `switchbrew/deko_basic` (aucune archive ZIP, vidéo ou mesure personnelle ; piste de vidage des tables de ressources ignorée).

### Fidélité homebrew et microprogrammes (`0436` / `0450` / `0463`)

Traduction bout-en-bout (`ShaderCases.dll` + `spirv-cross` + `spirv_msl.py`) de `switchbrew/deko_basic` (`reference-guest.json`), `memory/copy17` et `attribute/reverse` sur 6 passages appariés équilibrés : **100 % de parité SHA-256** (`guest_sha256`, `spirv_sha256`, `msl_sha256`, `resources`) face à [`homebrew/reference-output.json`](homebrew/reference-output.json). Médianes hôte Linux : `366,691 ms` (`0436`) → `330,417 ms` (`0450`) → `323,713 ms` (`0463`), zéro régression. `0464–0467` ne modifient pas `S2A.Dsh` (`xfp = ed1bab862c12fb97` inchangé).

### Piste écartée avant intégration : `pc_get()` MRU + hachage 64 Kio

Le remplacement du hachage 4 Kio de `pc_get()` par un test MRU 2 entrées + hachage 64 Kio (`addr >> 16`) a été évalué sur 5 régimes (6 passages `-O2`, CPU 0) et **rejeté** : `2pool_ring` `0,683 → 0,810 ms` (`+18,6 %`), `4pool_ring` `1,014 → 1,942 / 1,477 ms` (`+45,7 %` à `+91,5 %`), `16x4KB_adj` `0,647 → 8,632 ms` (**`13,3×` plus lent**, ratés `16 → 194 148`), `64pool_rand` `14,493 → 15,045 / 15,636 ms` (`+3,8 %` à `+7,9 %`) ; seul `32pool_rand` s’améliorait (`15,143 → 12,781 ms`). Le `pc_get()` 4 Kio d’origine est conservé intact dans `nvn_mtl.m`.

### Correctifs retenus (`0464`–`0467`)

| Patch | Portée | Mesure hôte comparée (référence `0436` / intermédiaire `0463` → candidat) | Exactitude / sanitizers |
| --- | --- | --- | --- |
| 0464 | `rb_args_ubo.h`, `nvn_mtl.m`, `nvn_geometry.inc`, `nvn_session.inc`, `rt_range_check.inc` : horloges de génération par slot, `rb_args_diff` 8 o, saut `NVN_RB_CBUF` avec `ubcap`, `g_rb_ubolen_fast[6]` $O(1)$, `args_dirty_pass_begin()`, garde `rb_ab_pool_gen` | `bench_suite.py` M04 (12 passages) : `2,7961` / `2,7546` → `1,7355 ms` (`−13,49 %` vs `0436`, `−12,97 %` vs `0463`) ; 6 passages isolés : `2,1239` / `2,1191` → `1,8339 ms` (`−15,03 %` / `−11,32 %`), `full 28 800 → 80` (`−99,7 %`), `ubo_lookups 188 800 → 35 520` (`−81,2 %`), `len_fill_scans 35 200 → 40` (`−99,9 %`), Cachegrind `Ir 2 935 522 → 2 854 681` | ASan+UBSan : `t_rb_args_ubo` vert + oracle adversarial `500 000` événements `wrong=0` (A↔B↔A, inter-passes, `TEXU`/`size_abi`/`mem_gen` brouillon `0439`, serrage/déliaison `ubcap`, `g_pool_gen`) |
| 0465 | `rb_draw_fast_rule.h`, `nvn_mtl.m`, `nvn_session.inc`, `rt_range_check.inc` : masques `g_rb_vbuf_dirty`/`bound` dans `bind_vbufs()` + invalidation `enc_r_vbuf` (corrige brouillon `0438`) | Banc 4 régimes (12 paires `-O2`, 500k dessins) : `0_dirty` `7,719 → 1,324 ms` (`−82,77 %`), `1_dirty` `5,700 → 3,009 ms` (`−45,61 %`), `4_dirty` `9,644 → 7,378 ms` (`−22,67 %`), `16_dirty` `27,361 → 25,458 ms` (`−4,15 %`) ; `bench_suite.py` M03 (12 passages) : `1,6054` / `1,3375` → `0,3185 ms` (`−70,77 %` vs `0436`, `−70,51 %` vs `0463`, `slot_checks 960 000 → 15 001`, `Ir 1 637 564 → 752 767`) | ASan+UBSan : oracle adversarial `500 000` événements `0` écart (`842 105` écritures exactes, `mesh` slot 29, `tess` 20..25, `PUSH_SLOT=13`, `g_pool_gen`, pool invalide `0xbad`) |
| 0466 | `nvn_mtl.m`, `nvn_size_abi.inc`, `nvn_unnorm.inc`, `nvn_rscale_ops.inc`, `nvn_geometry.inc`, `nvn_session.inc` : `arena_alloc(n, NULL)` zéro-ARC (18 sites chauds), cache `g_ubs_cpu/gpu` + `upd_ent/ubd_ent.cpu`, `g_half_masks_gpu`, `rb_cctx_t` POD différé, `g_commit_blocks` paresseux | Banc ObjC Linux `-O2` (6 paires équilibrées) : `30,648 → 5,269 ms` (`−82,82 %` médian apparié) ; `bench_suite.py` 10 modules (12 passages `0436` vs `0463` vs `0466`) : 0 régression, 10/10 parité exacte | ASan+UBSan : parité `cctx` `10 000/10 000` chaînes exactes + repli `cpu==NULL` (`t_nvn_ubd_index.m`), `compare_ubolen.py` (`0436` vs `0466`), 14/14 tests C NVN portables, `s2arm_engine_exports_test.py` 4/4 |
| 0467 | `runtime/src/svc_mem.c` : comptabilisation `AMASK_PROBE_N(7)` sous `S2A_UNIT_TEST` pour les lectures 64 bits de `g_amask` introduites par `0462` | Coût nul en production (`((void)0)`), gain `9,65×` de `0462` intégralement préservé | Corrige l’échec `t_svc_mem` `212/213` découvert lors de `thermal_gpu_checks` (run `45943660501`) → **`213/213`** sur macOS-26 (`45945441918`) |

### Compilation iOS et mesures Metal macOS-26 (run [`45945441918`](https://github.com/TarbleFR/RewindBox/actions/runs/45945441918), commit `89c0fc3aa`)

- **Compilation moteur seul (sans IPA)** : **vert** sur `macos-15` (`make ios` `542 s`, `make ios-guest` `25 s`) et `macos-26` (`Xcode 26.6`, `make ios` `683 s`, `make ios-guest` `39 s`, `463` patchs `0001–0467`, `153` symboles exportés, `0` glslang, `0` `_s2a_rb_` indéfini, `S2ArmDirectChain = 0be3f28548fd`, `S2ArmEngine.framework.zip` `9a3f70d6…cbe5`, `NS2Pro.framework.zip` `8fbe5d8c…d6af`).
- **Compilation Metal de shaders synthétiques (`pipeline_driver`, 48 stages iPhoneOS, 12 paires × 5 classes sur Mac paravirtualisé)** : médianes `fresh 4,0322 ms`, `one_fresh 2,0553 ms`, `vertex_fresh 1,7619 ms`, `crossed 0,0662 ms`, `repeated 0,1189 ms`.
- **Fidélité homebrew sur GPU Metal (`homebrew/metal_readback.py`)** : 3 programmes MSL compilés en AIR iPhoneOS, **6/6 relectures Metal exactes chacun** face à l’oracle Vulkan (`256 o`, `16 384 o`, `16 384 o`).
- **Cadence hors écran 720p (`homebrew/pacing/measure.py`, 12 paires × 4 320 dessins)** : `limit=1` (`slot_wait_p50 0,8870 ms`, `encode_wall_p95 0,0940 ms`, `encode_cpu_p95 0,0904 ms`, `gpu_p50 0,7774 ms`, `gpu_p95 1,1857 ms`, `0` durée GPU indéterminée, `936,6` complétions/s hôte) ; `limit=3` (`slot_wait_p50 0,2770 ms`, `encode_wall_p95 0,0885 ms`, `encode_cpu_p95 0,0830 ms`, `56` durées GPU indéterminées — p50/p95 GPU non comparables).
- **Suite `thermal_gpu_checks` macOS-26** : 16 tests C `-Werror`, `rb_dirty_range`, `t_rb_ubo_versions`, `t_nvn_ubd_index` (`--rb-uniform-ranges` et `--inflight` 0/1), `t_nvn_pso_batch` (`15/15`), `t_rb_clear_batch_metal`, `t_nvn_xqueue` (`14/14` × 4 modes), `t_thread`, `t_crash` (`15/15`), `t_svc_mem` (`213/213`), `t_far` (`111/111`), `t_nvn2` (`199/199`), `t_tdump_stress` (`300/300`) — **tous verts**.

Les FPS, le temps GPU en jeu, la chauffe et la consommation sur iPhone 16 Pro Max (A18 Pro) restent **non mesurés** ; aucune extrapolation physique n’est produite. Prochain axe enregistré : audit du fil d’encodage Metal (`nvn_rec.h` mise en cache IMP / lots `rec_flush`) et des coûts CPU de pré-analyse des soumissions (`sdx_walk`, `udc`/`fb`/`defer`) + temps d’image GPU.

## 0468 : répartition des appels du fil d’encodage

Axe : coût Objective-C du fil d’encodage Metal (`nvn_rec.h`).

- **Brouillon retiré.** Le gain combiné de `−23,58 %` du brouillon `bench_0468_rec.c` ne compte pas : il opposait un `objc_msgSend` simulé sous Linux et un `malloc` par proxy à des appels directs et à un pool.
- **Rejeté : une seule section critique dans `rec_put`.** Verrous `4 800 → 2 700`, mais aucun gain reproductible : banc isolé [`bench_0468_lock.c`](dispatch/bench_0468_lock.c), 12 paires alternées, deux séries, médianes appariées `+2,98 %` / `+6,89 %` puis `−0,93 %` / `−4,05 %`, écarts interquartiles traversant zéro. ASan+UBSan et TSan : parité vérifiée.
- **Retenu : `0468`, IMP mise en cache par type d’enregistrement et classe.** Mesure sur le runtime Apple (runner macOS 26 arm64, run [`45952496588`](https://github.com/TarbleFR/RewindBox/actions/runs/45952496588), [`rec_bench.m`](../../../build-utils/s2arm/engine/benchmarks/rec_bench.m), [CSV](dispatch/rec-dispatch-45952496588.csv)) : `7,735 → 4,653 ns` par enregistrement, médiane appariée `−34,73 %` (p25 `−48,42 %`, p75 `−29,02 %`), hachages identiques à chaque paire. Les corps de méthodes sont triviaux : la mesure borne la part de répartition, pas le travail Metal.
- **Laissé de côté : réutiliser les remplaçants `DmRecEnc`.** `34,97` contre `0,38 ns`, soit environ 35 ns par encodeur ; le changement de propriété ne vaut pas le risque.
- **Compilation.** Moteur compilé sur macOS 15 et 26 (run [`45953045391`](https://github.com/TarbleFR/RewindBox/actions/runs/45953045391)). Interrupteur `S2A_RB_REC_IMP=0`.

Temps d’image, FPS et chauffe sur iPhone : non mesurés. Échecs consécutifs : 0 après `0468` (1 rejet dans le cycle). Prochain axe : coût CPU des pré-analyses de soumission (`sdx_walk`, `udc`/`fb`/`defer`) et temps d’image GPU.

### Suite : pré-analyses de soumission (`0469`, non retenu)

- **Rejeté : garder le compartiment de chaque événement de l’index de stockage.** Le compartiment trouvé dans `sdx_ev_add` est gardé au lieu de deux recherches de plus par événement dans le tri. L’index reste identique octet pour octet (ASan+UBSan, 3 régimes), mais le gain est nul : [`bench_0469_sdx.c`](dispatch/bench_0469_sdx.c), 12 paires sur un seul cœur, médianes `−0,79 %`, `−0,43 %`, `+0,49 %` pour 729, 4 177 et 11 553 événements par soumission, avec des écarts qui traversent zéro ou restent positifs. Le parcours domine.
- **Écarté après analyse : restaurer l’état « sale » des arguments après les pré-analyses** (`pso_predict_rest_`, `pass_color_unwritten`, `fz_probe_cov2`). `args_dirty_all` avance les horloges monotones de `0464` ; les remettre en arrière réutiliserait des valeurs déjà comparées. Ces pré-analyses ne tournent qu’aux défauts de pipeline. Il faut d’abord un test Metal moteur qui compte les liaisons réencodées, avec interrupteur A/B, dans un même run.
- **Mesure à ne pas comparer.** Le banc de rythme homebrew, indépendant du moteur, donne un temps GPU médian de `0,78 ms` dans le run `45945441918` et de `0,38 ms` dans le run `45953045391`. C’est la variance entre runners : seules les paires mesurées dans un même run comptent.

Échecs consécutifs : 1. Prochain axe : coût de reliaison après la pré-analyse des pipelines, mesuré par un test Metal A/B dans un même run, puis compilation des pipelines au premier usage en A/B.

### Fil de soumission : enregistrements écrits sans message (`0469`, rejeté)

- **Idée.** Quand l’encodeur est un remplaçant `DmRecEnc`, les enveloppes `enc_r_*` / `enc_c_*` écriraient l’enregistrement elles-mêmes, sans passer par la méthode du remplaçant.
- **Mesure sur le runtime Apple** ([`rec_bench.m`](../../../build-utils/s2arm/engine/benchmarks/rec_bench.m), côté soumission, 12 paires, enregistrements identiques) :
  - test de classe à chaque appel : `+30,00 %` (run [`45956794549`](https://github.com/TarbleFR/RewindBox/actions/runs/45956794549), [CSV](dispatch/rec-dispatch-45956794549.csv)) ;
  - test mis en cache par destinataire : `+11,26 %` (run [`45957340416`](https://github.com/TarbleFR/RewindBox/actions/runs/45957340416), [CSV](dispatch/rec-dispatch-45957340416.csv)).
- **Verdict.** Le message au remplaçant n’est pas plus lent. Patch retiré, compilation `45956522519` annulée.
- **0468 confirmé.** Les mêmes runs redonnent `−42,77 %`, `−39,76 %` et `−46,84 %` sur la répartition côté encodage.

Échecs consécutifs : 2.

## 0470 : index de stockage, emplacements vivants par étage

Axe précédent (coût de reliaison après `pso_predict_rest_`) **clos par analyse, sans code** : `args_dirty_all` force au plus un encodage complet des arguments du dessin en cours par pré-analyse (banc `0465` : `51 ns` par dessin pour 16 tampons de sommets sales), alors que la pré-analyse rejoue elle-même `state_op` sur tout le reste de la soumission et ne tourne qu’aux défauts de pipeline. La part de la reliaison reste sous le bruit ; toucher aux horloges de `0464` exposerait l’exactitude sans gain mesurable. Non compté comme échec.

- **Retenu : `0470` (`nvn_mtl.m`, `sdx_walk`).** Un dessin dont le programme n’est pas encore chargé parcourait les `6 × 288` emplacements de `g_pp_slot`. Chaque étage garde la liste croissante de ses emplacements occupés, refaite après une liaison de cet étage. Mêmes événements, même ordre ; `S2A_RB_SDX_LIVE=0` rétablit l’ancien balayage.
- **Mesure** ([`bench_0470_sdx_slots.c`](dispatch/bench_0470_sdx_slots.c), Linux `-O2`, 2 000 dessins par soumission, 200 soumissions, 12 paires alternées, deux séries sur deux cœurs, hachage des événements identique à chaque paire, ASan+UBSan) :

| Dessins sans programme chargé | Série 1 (médiane appariée, p25 / p75) | Série 2 |
| --- | --- | --- |
| 0 % (régime stable) | `−0,24 %` (`−2,71` / `+1,47`) | `−1,00 %` (`−2,00` / `+0,41`) |
| 2 % | `−0,48 %` (`−1,10` / `+0,02`) | `−0,30 %` (`−1,08` / `+3,93`) |
| 10 % | `−3,37 %` (`−3,87` / `−2,56`) | `−3,56 %` (`−4,52` / `−3,21`) |
| 100 % | `−9,92 %` (`−13,91` / `−9,38`) | `−10,28 %` (`−11,76` / `−8,18`) |

  La référence `0426` et le meilleur intermédiaire `0468` ont le même code sur ce chemin. Aucune dégradation mesurée en régime stable (écarts traversant zéro). Le gain ne vaut que pendant les chargements de shaders ; ce sont les ajouts d’événements, pas le balayage, qui dominent ensuite.
- **Compilation moteur seul** : run [`45958486174`](https://github.com/TarbleFR/RewindBox/actions/runs/45958486174) (commit `d451b0074`), vert sur macOS 15 et 26 ; `153` exports, `S2ArmDirectChain 0be3f28548fd`, `thermal_gpu_checks` verts (`t_svc_mem 213/213`, `t_far 111/111`, `t_nvn_xqueue 14/14`, `t_crash`, `t_tdump_stress 300/300`).
- **Shaders synthétiques et homebrew, même run** : `pipeline_driver` (48 stages iPhoneOS, 12 paires) `fresh 3,584`, `one_fresh 1,569`, `vertex_fresh 1,898`, `crossed 0,049`, `repeated 0,053 ms` ; run `0468` (`45953045391`) : `1,566`, `1,017`, `1,224`, `0,052`, `0,049 ms`. Ce banc n’exécute pas le code moteur : l’écart vient du runner. Homebrew : 3 programmes, **6/6 relectures Metal exactes** chacun dans les deux runs.

Temps d’image, FPS et chauffe sur iPhone : non mesurés. Échecs consécutifs : 0 après `0470`. Prochain axe : clés texte de `prog_peek_jobs` (formatage hexadécimal, `NSString`, recherches sous `g_shader_lock`) par dessin tant qu’un programme combiné n’est pas résolu, dans `sdx_walk` et `pso_predict_rest_`, en A/B synthétique à résultats identiques ; puis cadence GPU du homebrew dans un même run.
