# Core RPCS3 : ajouts depuis l’IPA 593 — 29 octobre 2026

## Compilation et périmètre

**État de la fabrication : réussie au premier essai.** Le Core a été compilé depuis la source immuable
`fe587e27fcefadaa36315a3ddc7dc1edba17b825`, sur la branche `Claude`.
Suivi : [GitHub Actions — run 40839976736](https://github.com/TarbleFR/RewindBox/actions/runs/40839976736).
Les **24 modes de validation Apple ont réussi** sur Darwin ARM64 avec Homebrew
Clang 22.1.8. La compilation C++ et la validation du Core iPhone ont également réussi.

La référence livrée est le Core de l’IPA privée **593**, source
`c143be63f95751616f98d7bf9f1f34f297862df2`, validé par le run Apple `40814736023`.
Le reçu de livraison de l’application est `571dbc0849caa55c76be797b649c8abf79de5053`.
Ce document décrit les changements ajoutés après cette référence, sans recompter
les optimisations qui étaient déjà présentes dans l’IPA 593.

Les quatre lots suivants représentent **13 changements de comportement**, répartis
dans **23 fichiers distincts du moteur et de sa recette de compatibilité JIT**.
La compilation emploie toujours le seul patch canonique `embedded-core.patch`.

| Lot du manifeste | Contenu | Fichiers modifiés dans ce lot |
| --- | --- | ---: |
| `runtime_device593_followup_20261029` | Cohérence des textures, queue MoltenVK, lectures JIT, destruction des paquets | 13 |
| `runtime_bo2_followup_20261029` | Admission des compilateurs et réutilisation/publication des clés fragment | 3 |
| `runtime_bo2_warm_20261029` | Index des textures compressées, viewport/scissor, notifications de complétion | 8 |
| `runtime_bo2_exact_20261029` | Recherche exacte non compressée et clés de framebuffer | 2 |

Certains fichiers sont modifiés par plusieurs lots : ces nombres ne s’additionnent
donc pas pour obtenir le total distinct. Les changements MeloNX conservés par le
commit de fusion sont indépendants et ne font pas partie du binaire Core RPCS3.

## Les treize ajouts

### 1. Cohérence des textures après les écritures CPU du RSX

Les six chemins d’écriture réussie de NV308A, NV0039 et du repli CPU NV3089 font
maintenant avancer l’epoch de validation après leurs dernières écritures. Une
texture modifiée ne réutilise plus un ancien résultat de hash, y compris un résultat
préparé par le worker de prévalidation. Les échecs et opérations sans effet restent inchangés.

Cette correction concerne un défaut reproduit de cohérence. Elle est pertinente
pour les armes/avant-bras de BO2 et les torches d’Assassin’s Creed, mais leur disparition
sur iPhone n’est pas établie. Les hashes nécessaires sont rétablis, pas supprimés.

### 2. Révalidation des textures déjà liées aux samplers

Un binding déjà actif pouvait éviter entièrement la recherche de texture. Des
révisions de validation suivent désormais les **16 bindings fragment et quatre vertex**.
Les écritures ciblées invalident les plages qui se chevauchent ; les plages inconnues
ou tuilées gardent le chemin conservateur. Les bindings sans rapport restent rapides.

Les tests passent de **234 acceptations de contenu périmé et 48 payloads de sampler
périmés à zéro**, tout en conservant 19 200 passages rapides sur des samplers inchangés.
Les contrôles de contenu et les règles propres aux cibles de rendu restent actifs.

### 3. Sélection de la queue réelle de présentation MoltenVK

La queue est identifiée par sa famille et son index exacts. Le chemin précédent
retombait sur `vkQueueWaitIdle` lorsque deux queues étaient disponibles. Le marqueur
peut maintenant attendre le travail précédent de présentation sans attendre des
transferts indépendants ni le travail ajouté ensuite. Les identités ambiguës gardent le repli sûr.

Les logs GoW3 montrent 973 drains complets pour 973 frames dans une séquence.
Ils motivent la correction, sans mesurer son gain ni établir un lien avec le gel ultérieur.

### 4. Lectures du cache JIT plus directes

Les objets compressés d’au plus **4 Kio** sont lus dans un tampon de pile par I/O
positionnelle ; le pied gzip et la décompression partagent le même instantané.
Les gros objets gardent la lecture en flux, sans seeks répétés. Une lecture réussie
n’effectue plus de vérification d’existence redondante. Les messages individuels des
objets SPU déjà préchargés passent de `notice` à `trace` sur iOS.

Dans le petit cas contrôlé : deux requêtes de métadonnées, deux seeks et deux reads
deviennent **une requête, aucun seek et une lecture positionnelle**. Le cas de 1 Mio
supprime 18 seeks. Les contrôles gzip, de taille, de lecture courte et de corruption restent présents.

### 5. Destruction correcte des paquets Vulkan

Un `queue_submit_t` créé par `new` était libéré par `free`. Il est maintenant détruit
par `delete`. ASan reproduit l’erreur avant et valide le chemin corrigé. L’ordre des
soumissions, les fences et la responsabilité des payloads restent inchangés.

### 6. Suppression d’une notification perdue à l’admission de compilation

La libération d’un ticket fourni par l’hôte prend désormais le mutex du prédicat
d’attente, puis notifie après déverrouillage. Un demandeur ne peut plus manquer cette
notification juste avant de s’endormir et attendre inutilement le timeout nominal de 20 ms.

Seize entrelacements forcés reproduisent seize notifications perdues avant et aucune
après. Les limites de concurrence, les estimations mémoire et l’annulation restent
inchangées. La compilation s’effectue toujours hors de cette section critique.

### 7. Réutilisation de shaders fragment aux propriétés inutilisées différentes

La clé privée du cache normalise seulement les propriétés sans effet démontré pour
le microprogramme : coordonnées 2D/sprites d’entrées TEX non lues, ou éclairage deux
faces/interpolation plate lorsque les entrées couleur concernées ne sont pas lues.
Le programme original reste transmis au compilateur et à la sérialisation.

L’analyse est paresseuse et mémorisée. Les propriétés neutres n’entraînent aucun scan ;
les programmes indirects, à contrôle de flux ou ambigus gardent leur clé originale.
Les tests couvrent 5 400 équivalences exactes et 4 320 variantes actives distinctes.
Une trace synthétique passe de 2 048 appels de compilation à un seul ; ce n’est pas un compte BO2.

### 8. Publication d’une clé fragment immuable

Le clone du microcode a lieu sous le verrou d’écriture lors d’une nouvelle insertion.
Les lecteurs concurrents ne voient plus la clé en cours de transformation. Aucun
clone supplémentaire n’est ajouté aux hits et la compilation reste hors verrou.
La correction sécurise notamment les recherches concurrentes pendant le préchargement.

### 9. Index d’adresses pour les textures compressées

Au-delà de 16 sections par bloc, un index trié par adresse puis position du slot
sélectionne les candidats de même adresse. Les contrôles de format, dimensions,
mipmaps, état et contenu ainsi que le premier résultat accepté sont conservés.
Les petits blocs et la spécialisation de présentation sans verrou équivalent gardent leur parcours.

La maintenance couvre changements de plage, sections sans ressource GPU, seuil,
recyclage et clear. **22 753 recherches et 8 618 mutations** sont comparées.
L’index réduit les visites dispersées, mais ajoute du stockage et du travail de maintenance.

### 10. Réutilisation exacte des viewport et scissor

Le rendu RSX, les overlays, les clears d’attachment et les clears stencil emploient
les mêmes setters. Les comparaisons respectent les bits exacts des floats. Les binds
statiques/inconnus et les nouveaux enregistrements invalident correctement le cache.

Dans une trace contrôlée, 10 000 états identiques ne produisent plus qu’une commande,
pour chacun des deux états. Aucun draw ni changement requis n’est supprimé.
Le nombre de commandes évitées dans un jeu dépend de sa séquence réelle.

### 11. Suppression des notifications de complétion obsolètes

Le worker n’est réveillé que lorsque le CAS gagnant fait avancer l’EID complété.
Les anciennes complétions ne déclenchent plus de notification sans nouveau travail.
Les drains explicites, fences, barrières et soumissions conservent leurs règles.

Une trace synthétique de 1 024 notifications passe à 128 avec le même compteur final.
Les tests concurrentiels incluent une course CAS forcée, les drains et l’arrêt.

### 12. Accès direct aux textures non compressées déjà en cache

Le chemin de correspondance exacte réutilise l’index précédent au-delà de 16 sections.
Un hit évite la visite des sections sans rapport et la construction de la liste des
chevauchements. Le repli conserve exactement l’ordre historique après des validations
échouées, y compris l’effet des effacements par échange avec la dernière entrée.

Les tests passent **13 492 requêtes**, dont 3 365 cas debug, et 4 036 mutations.
Dans une charge contrôlée contenant 64 chevauchements avant le hit, 4 000 allocations
ou réallocations pour 1 000 hits deviennent zéro. Certains misses et premiers slots coûtent davantage.

### 13. Initialisation complète des clés de framebuffer

Le constructeur initialisait 33 bits de champs alors que le cache employait l’entier
complet de 64 bits. Les 31 bits restants sont maintenant explicitement initialisés.
Sous Clang 22, les mêmes paramètres 1280 × 720 préremplis avec 256 motifs produisent
256 clés avant et une après. Ce test ne mesure pas la fréquence des misses dans un jeu.

Les vérifications couvrent 103 936 constructions par version, 1 026 recherches,
1 011 hits, 15 créations et 15 destructions, ainsi que les références et invalidations.

## Mesures des recherches de textures sur Apple ARM64

Les rapports de prévalidation du [run Apple](https://github.com/TarbleFR/RewindBox/actions/runs/40839976736)
mesurent les corps de production sur hôte Darwin ARM64, Clang 22.1.8 à `-O3`.
Voici les médianes de sept répétitions, en nanosecondes par opération, pour des
succès répartis dans chaque bloc. Il ne s’agit pas de frames d’un jeu iPhone.

| Sections du bloc | Hit compressé, avant → après | Hit exact non compressé, avant → après |
| ---: | ---: | ---: |
| 64 | 76,2625 → 31,7833 ns | 88,8542 → 35,4479 ns |
| 256 | 214,66 → 72,7708 ns | 290,708 → 41,6104 ns |
| 1 024 | 992,136 → 55,025 ns | 1 329,38 → 59,7354 ns |

Les coûts défavorables restent visibles dans les mêmes rapports :

- Recherche exacte sans résultat, 1 024 sections : **2 549,27 → 3 112,6 ns**.
- Recherche exacte au premier slot, 1 024 sections : **25,0042 → 64,0812 ns**.
- Recyclage de section dans l’index compressé, 1 024 sections : **21,0917 → 1 025,5 ns**.
- Hit compressé au seuil de 17 sections : **10,7347 → 18,3083 ns**.

Avec 64 chevauchements avant une correspondance exacte, le coût passe de
**680,983 à 20,7792 ns**. Les 1 000 hits contrôlés passent de **4 000 allocations ou
réallocations à zéro**, soit 1 536 000 octets cumulés de demandes évitées dans cette
charge. Ce cumul ne représente ni la RAM résidente ni le pic mémoire d’un iPhone.

Les succès dispersés dans les grands blocs sont accélérés, mais les échecs, les
premiers slots et la maintenance peuvent coûter davantage. La distribution réelle
de ces opérations dans BO2 n’est pas connue : aucun gain net de FPS n’est extrapolé.

## Ce qui est vérifié, conservé et encore à mesurer

Les résultats chiffrés ci-dessus proviennent de fonctions de production exécutées
sur hôte, avec des adaptateurs explicites aux frontières GPU, mémoire ou plateforme.
Ils ne constituent pas des mesures de FPS, de footprint ou de disparition des saccades sur iPhone.

Les **24 modes ciblés ont réussi sur Darwin ARM64, Homebrew Clang 22.1.8** :
10 ordinaires, 10 ASan/UBSan et quatre TSan. Ils couvrent huit modes du lot device593,
six du lot admission/shaders, six du lot warm et quatre du lot exact/FBO.
Les anciennes suites du Core livré sont réutilisées. Les 190 entrées du contrat,
313 postimages canoniques et 42 suppléments natifs lient les preuves aux sources exactes.
Les 313 postimages décrivent le patch complet de RewindBox, pas 313 nouveaux fichiers de ce cycle.

Le code hôte NeoSwap est inchangé. Les sources conservent **ABI 30 et 88 exports**, les
identités PPU `a987639e9f838d1c` et SPU `d070cb361bdef607`, ainsi que les formats de cache.
La génération, l’édition de liens et les relocations JIT restent identiques ; l’alias
authentifié des seules modifications d’I/O conserve les caches existants.

L’admission sélective du prehash, les 64 hints récents par étage shader, la rétention
des autres états dynamiques Vulkan et la recherche d’allocation VM améliorée étaient
**déjà présentes dans l’IPA 593**. Elles sont préservées, sans être comptées comme nouveautés.

Les premières compilations Metal restent un problème distinct des coûts récurrents.
Le gel GoW3 reste non résolu : le producteur invité de la valeur de label manquante
n’est pas identifié. Les gains nets BO2/AC/GoW3 et la disparition des artefacts doivent
encore être évalués avec le nouveau Core sur l’iPhone. Aucun nouveau réglage joueur,
télémétrie, purge générale de cache ou approximation graphique n’est introduit.

## Résultat final de fabrication

Le run **40839976736**, tentative 1, est terminé avec succès. Le Core a été téléchargé
et vérifié indépendamment après sa production. Les 24 rapports et leurs sorties
correspondent à leurs empreintes ; les deux hooks MoltenVK et les identités PPU/SPU
attendues figurent dans le journal réel de fabrication.

| Élément | Résultat |
| --- | --- |
| Source compilée | `fe587e27fcefadaa36315a3ddc7dc1edba17b825` |
| Artefact Core | [12883027017 — RPCS3Core](https://github.com/TarbleFR/RewindBox/actions/runs/40839976736/artifacts/12883027017) |
| Binaire | `libRPCS3Core.dylib`, 77 251 592 octets, iPhone ARM64 |
| SHA-256 du binaire | `13b4c505434a7a0291abad47fa157ce0c9e20741e297f24dc2575e760e0e691b` |
| Archive ZIP | 29 108 511 octets ; SHA-256 `93c79e3eac60300711755400b3e7a9efb9c87f3c48f487a3c4fff68ca64cdd44` |
| Contrat | ABI 30, 88 exports exacts, PPU/SPU conservés |
| Validation Apple | 24 modes réussis ; contrôles statiques du chargement passif réussis |

Le [reçu Apple](evidence/rpcs3-bo2-exact-20261029/apple-core.json) conserve le run,
les artefacts et les identités. L'[identité du Core](evidence/rpcs3-bo2-exact-20261029/apple-core/identity.json),
la [preuve native](evidence/rpcs3-bo2-exact-20261029/apple-core/runtime592-proof.json)
et la [vérification du téléchargement](evidence/rpcs3-bo2-exact-20261029/apple-core/artifact-verification.json)
sont conservées avec elle. Réutiliser cet artefact pour la prochaine IPA demandée si
les entrées RPCS3 restent identiques ; ne pas refaire une compilation inchangée.

Cette fabrication ne produit pas une nouvelle IPA ni une release. Les contrôles de
chargement passif sont une analyse statique du Mach-O, pas un démarrage sur l’iPhone.

## Sources et rapports détaillés

- [Écritures RSX, samplers, présentation et I/O JIT](rpcs3-device593-followup-2026-10-29.md).
- [Admission et cache fragment](rpcs3-bo2-followup-2026-10-29.md).
- [Index compressé, viewport/scissor et complétions](rpcs3-bo2-warm-2026-10-29.md).
- [Accès exact non compressé et clés FBO](rpcs3-bo2-exact-2026-10-29.md).
- [Contrat source cumulé](evidence/rpcs3-bo2-exact-20261029/committed-contract.json).
