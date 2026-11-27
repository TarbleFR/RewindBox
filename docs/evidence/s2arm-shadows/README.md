# Ombres NVN2, 27 novembre 2026

Base RewindBox `dda1622f`, moteur amont `6b6a571553f7a687af46e03e2cdbf8ef4d77f335`. Le backend direct de l’iPhone passe par Metal 4 à partir d’iOS 27 sur GPU compatible. iOS 26.x prend Metal 3. La logique de snapshot se trouve en amont de la décision Metal 3/4.

## Charge réellement observée

Dans [le profil IPA 824 de Mario Kart World](../s2arm-pass-traffic-824.md), quatre passes de deux dessins écrivent sur l’atlas 6144² et ses niveaux jusqu’à 768². Le compteur historique donne 191 Mio chargés et 191 Mio stockés. Les passes de ce grand atlas coûtent quelques dizaines de microsecondes chacune sur cette capture. Trois passes D16 de 2048² représentent 24 Mio de stockage logique corrigé au lieu de 48. Le profil comptait aussi quatre à six copies de profondeur par image. Ces copies incluent la profondeur relue par l’éclairage de la scène. Le type de cible seul ne permet pas de les attribuer toutes aux ombres. [Fréquence et limitation de puissance sur A18 Pro](../s2arm-power-wall.md).

Une contre-mesure des exports historiques indépendants recoupe les lignes `[gpuprof]`. Sur Mario Kart World, 141 lignes pour la cible 6144² donnent 137 enregistrements uniques après déduplication par session, image et index d’encodeur. Les 137 ont deux dessins, un attachement couleur, zéro profondeur et une médiane de **89 µs**. Les journaux de création et de cibles donnent `NVN_FORMAT_RGBA8SN` et Metal 72 (`RGBA8Snorm`). La capture ne démontre pas l’usage de la texture par un shader d’ombres. Les passes depth-only sont mesurées séparément par union de leurs intervalles GPU.

| Jeu | Sessions / images profilées | Passes depth-only | Images avec ces passes | p50 de l’union depth-only |
| --- | ---: | ---: | ---: | ---: |
| Mario Kart World | 15 / 137 | 651 | 133 | 0,653 ms |
| Fire Emblem | 3 / 20 | 231 | 18 | 2,882 ms |
| Zelda | 0 / 0 dans cet export | — | — | — |

Les sessions profilées ont été déclenchées par le diagnostic. Les durées couvrent aussi les prépasses et ne décrivent pas la campagne de jeu courante. [Reproduction sur un export](history.py).

## Producteurs, consommateurs et vérification

| Étape | Source | Observations et conditions |
| --- | --- | --- |
| Cascade, carte ou atlas | `attach`, `rp_begin_ex_`, `clr_scissor` | Le moteur reçoit une texture, un format, un niveau et une couche. Un viewport ou un scissor indique au plus une zone d’un dessin ou d’un clear. Alpha test, stencil, transform feedback, stockage et rendu multicouche demandent une preuve indépendante. |
| Lumière ponctuelle et cube, spot et CSM | `p_set_rt`, `attach`, `g_rp_layered` | Même mécanisme générique pour les faces, couches et niveaux, le jeu détermine l’éclairage. Le profil disponible identifie dimensions et types. La géométrie, les lumières et les UV invités peuvent être nécessaires pour attribuer une passe à une lumière précise. |
| Clear | `OP_CLEAR_DS`, `clear_ds_tri`, `clear_tex` | Clear entier au début du pass et triangle pour une zone ou un masque partiel. Les clears différés et le regroupement de même cible ont déjà leurs gardes. 0519 reconnaît l’intervalle de couches d’un clear de texture natif validé. |
| Lecture fragment, PCF, bindless | `fb_prepare`, `rb_cont_reads_rt`, `rb_shadow_calls` | Les lecteurs d'une cible active ont besoin d’une copie isolée dans le scénario couvert. Le nombre de taps, les shaders, le biais et la précision suivent le jeu. La lecture bindless non résolue reste soumise aux gardes existantes. |
| Copie, compute et synchronisation | `copy_t2t`, `OP_DISPATCH`, `OP_WAIT_SYNC`, `rb_dsnap_rule.h` | La copie est réutilisable tant que son incarnation Metal et sa source restent valides. Compute, changements de génération, alias et fin de soumission conservent leurs invalidations. Les fences des deux backends suivent le code existant. |

Une rotation d’atlas fondée sur la seule caméra, des `DontCare` globaux après un scissor et la suppression de fragments dépourvus de sortie couleur ne satisfont pas les preuves nécessaires. Sur Metal, `Load` préserve les pixels antérieurs et `DontCare` exige que leur contenu soit sans effet. [Actions de chargement et de stockage, Apple](https://developer.apple.com/documentation/metal/setting-load-and-store-actions/).

## Changements et mesures

- **0518** compte deux octets par texel D16, et indépendamment quatre pour la profondeur et un pour le stencil d’une cible combinée D32S8. Le volume des snapshots est la taille logique des deux plans encodés. Le profil `DM_NVN_GPUPROF` marque les encodeurs de rendu sans couleur `guest-depth-only` et `guest-depth-only-clear`. La durée vient des compteurs GPU quand ils sont disponibles. Ces marqueurs incluent les prépasses.
- **0519** conserve un snapshot d’un niveau ou d’une couche disjointe lors d’un clear explicite. Comparaison sur texture et stockage Metal identiques, niveau et intervalle de couches bornés. Une conversion de format, une texture redimensionnée, un clear différé, un alias, un resolve et une écriture compute suivent le chemin historique. Les rectangles d’un même mip n’autorisent aucune réutilisation supplémentaire. Le candidat ne garde ni nouvelle texture ni masque de pixels.
- **0520** corrige la sortie prématurée de la protection de lecture lorsqu’un fragment lit la profondeur de sa passe et que le jeu n’a attaché aucune couleur. Cette correction peut ajouter une copie requise. La scène de contrôle utilise un fragment pouvant éliminer un pixel.
- **0521** étend le banc de cohérence à 9 450 cas mip/couche et deux contrôles d’identité par cas. Linux avec ASan et UBSan réussit. La scène Metal vérifie le nombre de copies pour 16 clears disjoints, une écriture chevauchante, la séparation du binding et relit les deux plans de l’atlas et du snapshot. Les mesures de cette scène sont rattachées au run Apple.
- **0522** rétablit l’invalidation entière avant vidange si la file porte un clear différé, une barrière, une passe multicouche ou un producteur pouvant écrire en mémoire. Les lectures de vérification respectent un pas de ligne de 256 octets pour chaque plan.

### Coût de la décision sur Linux

Neuf paires alternées de 2 097 152 opérations donnent une médiane de 9,516 ns en invalidation entière et 10,773 ns avec la comparaison de sous-ressource. Les deux bras remettent la même structure à deux entrées avant chaque opération. Sur 4 194 304 entrées examinées par bras, 1 048 576 restent valides dans le témoin et 2 621 440 avec le candidat. La différence concerne le niveau disjoint du même objet. Tous les alias qui recouvrent l’écriture sont invalidés dans les deux bras. Cette mesure isole le calcul C et exclut le temps de profilage, la lecture de propriétés Metal et la bande passante GPU. [Source](cache-cost.c) · [Neuf paires](cache-cost.csv).

### Exécution des bancs Apple

Les premiers hôtes Metal 3 refusent les ensembles de résidence dont le banc historique dépend au démarrage. Le rendu est testé avec les ressources réelles déclarées auprès de chaque encodeur, comme dans le banc de rejeu NVN2 existant. Cette adaptation est limitée à la fixture. Le premier contrôle avec cette adaptation a révélé un cast ARC manquant dans le banc. Le [contrôle corrigé](https://github.com/TarbleFR/RewindBox/actions/runs/46035174782/job/140628639844) a réussi sur Apple Paravirtual Device en Metal 3.

| Après 16 clears disjoints dans une scène D32S8 à deux mips | Témoin | Cache par sous-ressource |
| --- | ---: | ---: |
| Copies de profondeur | 17 | 1 |
| Charge logique des snapshots | 1 360 octets | 80 octets |
| Nouvelle copie après le clear chevauchant | 1 | 1 |
| Contrôles indépendants réussis | 6/6 | 6/6 |

Le test vérifie l’identifiant réellement utilisé par le fragment, puis chaque texel des deux plans du snapshot et des deux niveaux de l’atlas. Il confirme 16 copies évitées et la copie obligatoire pour le clear chevauchant. La durée et le débit GPU de cette scène n’ont pas été chronométrés. [Archive des preuves Apple](https://github.com/TarbleFR/RewindBox/actions/runs/46035174782/artifacts/15217180126).

La [compilation et les contrôles d’export iPhoneOS](https://github.com/TarbleFR/RewindBox/actions/runs/46033595156/job/140623283698) ont réussi pour `a9513516` sur macOS 15. Le patch ultérieur 0523 modifie uniquement le banc macOS.

## Campagne sur iPhone

Comparer chaque interrupteur dans un processus distinct. Tenir la résolution interne à 1×, celle des ombres à 1, et désactiver l’interpolation. Utiliser trois répétitions de 30 minutes avec caches comparables, un itinéraire déterministe sur les quatre circuits de la Coupe Champignon 150 cc, une zone ouverte de Zelda traversée avec rotation de caméra et variation d’éclairage, et une carte Fire Emblem avec déplacement des unités et changement de vue. Comparer aux minutes 1, 5, 10, 20 et 30 les FPS natifs, p50/p95/p99, temps GPU, limite de puissance, énergie si disponible et mêmes plans de l’image. Utiliser les captures instrumentées séparément pour compter copies, temps GPU depth-only et chargements logiques.

Les compteurs disponibles dans ce lot ne mesurent ni les pixels effectivement couverts par la géométrie, ni le trafic DRAM physique par atlas. Le coût CPU en jeu de la nouvelle garde, les temps et l’énergie sur Metal 4 A18 Pro ainsi que les scénarios officiels de 30 minutes restent à relever.
