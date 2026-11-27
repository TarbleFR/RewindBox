# Ombres NVN2, 27 novembre 2026

Base RewindBox `dda1622f`, moteur amont `6b6a571553f7a687af46e03e2cdbf8ef4d77f335`. Le backend direct de l’iPhone passe par Metal 4 à partir d’iOS 27 sur GPU compatible. iOS 26.x prend Metal 3. La logique de snapshot se trouve en amont de la décision Metal 3/4.

## Charge réellement observée

Dans [le profil IPA 824 de Mario Kart World](../s2arm-pass-traffic-824.md), quatre passes de deux dessins écrivent sur l’atlas 6144² et ses niveaux jusqu’à 768². Le compteur historique donne 191 Mio chargés et 191 Mio stockés. Les passes de ce grand atlas coûtent quelques dizaines de microsecondes chacune sur cette capture. Trois passes D16 de 2048² représentent 24 Mio de stockage logique corrigé au lieu de 48. Le profil comptait aussi quatre à six copies de profondeur par image. Ces copies incluent la profondeur relue par l’éclairage de la scène. Le type de cible seul ne permet pas de les attribuer toutes aux ombres. [Fréquence et limitation de puissance sur A18 Pro](../s2arm-power-wall.md).

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

## Campagne sur iPhone

Comparer chaque interrupteur dans un processus distinct. Tenir la résolution interne à 1×, celle des ombres à 1, et désactiver l’interpolation. Utiliser trois répétitions de 30 minutes avec caches comparables, un itinéraire déterministe sur les quatre circuits de la Coupe Champignon 150 cc, une zone ouverte de Zelda traversée avec rotation de caméra et variation d’éclairage, et une carte Fire Emblem avec déplacement des unités et changement de vue. Comparer aux minutes 1, 5, 10, 20 et 30 les FPS natifs, p50/p95/p99, temps GPU, limite de puissance, énergie si disponible et mêmes plans de l’image. Utiliser les captures instrumentées séparément pour compter copies, temps GPU depth-only et chargements logiques.

Les compteurs disponibles dans ce lot ne mesurent ni les pixels effectivement couverts par la géométrie, ni le trafic DRAM physique par atlas. Le coût CPU en jeu de la nouvelle garde, les temps et l’énergie sur Metal 4 A18 Pro ainsi que les scénarios officiels de 30 minutes restent à relever.
