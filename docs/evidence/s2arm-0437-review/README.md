# S2Arm 0437–0441, contre-expertise et reprise du 26 novembre 2026

La référence moteur est 0436 au commit RewindBox `8be902ac0`. L’iPhone a exécuté la 845 en 0426. Le parcours Zelda du premier export atteint 24,0 présentations moteur/s sur 124,83 s. Le parcours filmé de Mario Kart World du second export atteint 49,28 avant capture et 34,42 pendant, avec la génération coupée. Les essais avec génération active contiennent des images interpolées confirmées avant la 844, sur la 844 et sur la 845. Les journaux ne permettent pas de quantifier une éventuelle régression à parcours identique. [Mesures physiques et définitions](../s2arm-0428/README.md)

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
- **0440 expérimental** retardait certaines soumissions en cours de passe. Sur une fenêtre de 300 présentations de Zelda 845, 2 418 des 2 584 coupes sont intra-passe. Le chemin concerné décide une coupe quand le compteur de segments GPU en vol est nul. Les seuls comptes de coupes ne suffisent pas pour prévoir le temps d’inactivité GPU ou le coût des stores Metal.
- **0441 expérimental** fournit le changement retenu en 0438. **0442 expérimental** augmentait la taille des plages à 128 octets et affaiblissait certains ordres atomiques. La variante 0439 active conserve la représentation et les ordres d’origine. **0443 expérimental** fournit la géométrie de 0440. Son déroulage du contrôle de tuile vide ralentissait le cas où le premier octet est non nul, de 2,53 à 3,26 ms par million de tuiles, et a été retiré.
- **0444 expérimental** omettait de restaurer viewport et scissor en quittant la projection élargie. Le corps extrait de la fonction produit des commandes différentes. Le correctif de laboratoire et ses traces synthétiques sont décrits dans les [notes de contre-expertise](drafts/notes.md). La propagation de toutes les invalidations dans le véritable encodeur reste à établir.

## État de reprise

Les candidats modifient les copies de textures et la gestion des métadonnées CPU sans réduire la résolution de rendu, la qualité demandée ou l’horloge invitée. Les nouveaux FPS moteur et générés, le frametime, les pixels du jeu, la RAM réelle, la chauffe et la consommation attendent une mesure sur appareil. Les observations de la 845 ne démontrent ni 60 FPS stables sur Zelda ni une limite matérielle. Les pistes de soumission à GPU vide, de prélecture des pages de textures, d’encodage des arguments et de compilation en cours de partie restent ouvertes.
