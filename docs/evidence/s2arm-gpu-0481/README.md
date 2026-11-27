# S2Arm GPU, 27 novembre 2026

Base graphique 0479, identique pour ces chemins au lot runtime 0480. Pin amont `6b6a571553f7a687af46e03e2cdbf8ef4d77f335`. Le sélecteur direct force Metal 3 sous iOS 26.x et en dessous. À partir d’iOS 27, il choisit Metal 4 si le périphérique annonce la famille Metal 4 et si `NXGAL_BE=mtl3` est absent. Les trois transformations sont communes aux deux backends.

| Patch | Charge et résultat avant/après | Portée |
| --- | --- | --- |
| 0481 | Texture RGBA8 2048², une page de 16 Kio. Sortie de désentrelacement 16 777 216 → 16 384 octets. Médianes CPU 1,603 ms → 1,760 µs par appel. [12 paires alternées](pairs.csv), 8 appels par bras et paire. | Préparation CPU et espace de staging. Le blit transférait déjà la région dirty. Surfaces denses, tableaux, volumes, sparse, MSAA et conversions gardent le chemin précédent. Les pages illisibles peuvent encore demander une copie de protection. |
| 0482 | Trois shaders synthétiques, cinq points d’entrée MSL. Les deux entrées mesh alimentées par task passent de 4 à 3 barrières de groupe. Mesh autonome et task passent de 3 à 2. [Sorties du traducteur](scoped-counts.json). | Le thread qui réécrit l’identifiant possède déjà ce mot. La barrière après la copie initiale à plusieurs threads est conservée là où elle protège le payload, ainsi que celles entourant le corps invité. |
| 0483 | Un clear sans bit de profondeur ou de stencil à écrire peut conserver la passe ordinaire ouverte. | La commande invitée reste enregistrée. Le replay conserve les règles de requêtes, alias, lecture des attachements, copie différée, coupure, capture et passes spéciales. Deux plans relus pixel par pixel dans la charge dédiée. |

0481 réutilise les copies de GOB de 0437 et la réservation serrée de 0452. La limite d’admission est un quart du niveau, alignement compris. Un refus revient à la mise à jour partielle sur staging entier. [Le contrôle C](rect_ab.c) confronte 1 296 rectangles à deux oracles sur les ordres Switch et Switch 2, RGBA8, BC1 et ASTC 6×6, avec 17 refus sans écriture et six géométries rembourrées. Linux x86-64, GCC 14 avec ASan et UBSan pour les octets, -O2 séparément pour les temps.

0482 restitue le MSL antérieur octet par octet lorsque son seul interrupteur vaut zéro. Les 21 contrôles de structure passent dans chaque configuration. Les 16 combinaisons des options ont des empreintes distinctes et cohérentes entre export natif et métadonnées ([matrice](xfp-matrix.json)). L’empreinte globale de traduction de secours change. Cette mise à jour peut entraîner une recompilation, y compris pour un shader ordinaire, et la reprise de préchauffage. Aucune suppression de sauvegardes ou de fichiers cache. Les bibliothèques précompilées déjà distribuées conservent leur code jusqu’à leur régénération.

0483 conserve les 24 octets de commande observables par le jeu. Le contrôle des masques sur Linux couvre 524 288 combinaisons. Le tracé et les passes de chronométrage sont désormais séparés. Le banc contrôle désormais les répétitions, les sorties des deux plans, la concordance des commandes et l’état de dessin. Le temps de soumission à fin de file avec une image en vol mesure uniquement la latence instrumentée du banc.

## Critique du chemin de rendu

| Étape | Coût documenté et décision |
| --- | --- |
| NVN2 → traduction → PSO | Distinguer la compilation ponctuelle du coût par groupe à chaque exécution de 0482. Le banc PSO existant mesure le pilote sur le runner. |
| Préparation → encodage | Priorité aux grandes textures rarement modifiées. Sur une image de 16,67 ms contenant exactement un appel hôte à 1,603 ms sur son chemin critique, le plafond d’Amdahl serait de 1,106×. La fréquence et le recouvrement en jeu restent inconnus. |
| Soumission → exécution | Le rejeu 0477 compte 677 recherches évitées. Sur 0478, 700 liaisons complètes deviennent 32 complètes et 668 changements de décalage. Zéro liaison identique sautée sur cette charge. Chaque bras possède 12/12 répétitions, pixels finaux identiques. Le temps apparié du cache désactivé (−17,16 %, interquartile −36,50 à +10,51 %) ne détermine pas un gain. |
| GPU → présentation | Les 14 dépendances démontrées du rejeu initial sont conservées. Le trafic d’attachements est logique. DRAM, occupation, GPU inactif, présentation, énergie/image et débit soutenu physique restent à mesurer. Aucun intervalle CPU/GPU superposé additionné. |

[0477 et son artefact](https://github.com/TarbleFR/RewindBox/actions/runs/46005579324/artifacts/15200694867) et [0478 et son artefact](https://github.com/TarbleFR/RewindBox/actions/runs/46006446704/artifacts/15202697516) compilent sur macOS 15 et 26. Les 324 traces des deux runs ont les mêmes séquences draw/dispatch. Les divergences du digest historique viennent de débuts de passe additionnels. L’image est relue en fin de répétition. L’IPA 848 garde le moteur 0470.

Prochain axe à fort potentiel conditionnel : les mipmaps et tableaux de textures tuilées, après validation des décalages indépendants par niveau et couche. Puis MSAA avec resolve ou shadows multi-cibles, avec lecture explicite de chaque plan. Aucun gain physique sur A18 Pro n’est établi.
