# RPCS3 Core 925 — mémoire graphique de Black Ops II : les blocs de l'allocateur ne gardent plus des centaines de Mo inutilisés

Core 925 = Core 924 (gel de Black Ops II, compilé vert par le run 42926781861, non épinglé) + une correction de placement des
allocations GPU. **Aucune mesure iPhone n'a encore été faite avec ce Core.**

## 1. Données d'entrée (export de l'appareil, build 724, PID 50194, Black Ops II, session 8)

`JITMEM`, un relevé toutes les 5 s, en Mio :

| Temps de jeu | Alloué (`vma_allocated`) | Blocs (`vma_block_bytes`) | Inutilisé (`vma_unused`) |
|---|---|---|---|
| 24 s | 556 | 648 | 92 |
| 60 s | 697 | 840 | 143 |
| 91 s | 745 | 1 032 | 287 |
| 117 s | 802 | 1 096 | 294 |
| 163 s | 806 | 1 096 | 290 |
| 173 s | 775 | 1 136 | 360 |

L'alloué plafonne (777-813) ; les blocs continuent de monter par pas de 64 Mio. `MEMPARTS923` (nouveau dans le Core 923) :
la part graphique du registre du noyau suit les blocs, pas l'alloué (registre − blocs : 198, 209, 250-290 Mio ; registre −
alloué : 293, 448, 580 Mio). L'empreinte du processus passe de 3,40 à 4,06 Go sur les mêmes deux minutes.

## 2. Cause (code)

- L'allocateur Vulkan (VMA 3.3.0) découpe toute allocation de moins d'un demi-bloc dans des blocs de 64 Mio
  (`VRAMBudgetPolicy.h`). Sur un GPU Apple, MoltenVK adosse chaque bloc à un `MTLHeap` de placement de cette taille : un bloc
  est de la mémoire physique tant qu'il contient une allocation.
- `vk::vmm_determine_memory_load_severity` garde la stratégie « au plus rapide » de VMA tant que la charge est sous 50 % du
  tas, et le tas annoncé par MoltenVK est la mémoire unifiée de l'appareil (7,4 Gio) : iOS n'en est jamais sorti.
- Black Ops II alloue et libère ses textures en continu, de toutes tailles ; chaque libération laisse un trou que seule une
  allocation de cette taille ou plus petite peut reprendre.

## 3. Correction (`REWINDBOX_GPU_MEMORY_PACKING_925`, réglage « GPU memory packing », Automatic = tous les jeux)

- une allocation de 1 Mio ou plus reçoit sa propre mémoire (mémoire dédiée de VMA, ce qu'il fait déjà seul au-dessus d'un
  demi-bloc) : elle est rendue au système à la libération et ne laisse pas de trou ;
- les plus petites sont placées dans le plus petit espace libre qui convient (stratégie « mémoire minimale », celle que
  l'amont adopte sous pression) au lieu du premier trouvé.

Ce qui est alloué, quand, et son contenu ne changent pas. `COREPROF GPUPACK925` compte ce que le levier a placé seul ;
`JITMEM vma_block_bytes / vma_allocated / vma_unused` portent le résultat.

## 4. Contrôle (hôte)

`test/rpcs3_gpu_memory_packing925_test.py` vérifie le câblage et compile `test/native/rpcs3_gpu_memory_packing925_model.cpp` :
le **vrai VMA 3.3.0** derrière un périphérique Vulkan factice (un tas de 7 989 460 992 octets, blocs de 64 Mio), la règle de
l'en-tête de production, une charge à la forme de Black Ops II (521 Mio qui restent, puis des textures de 16 Kio à 4 Mio
allouées et libérées au hasard jusqu'à 290 Mio vivants).

| Mélange de tailles | Vivant | Avant : périphérique / inutilisé | Après : périphérique / inutilisé |
|---|---|---|---|
| biais 2 (moyenne 421 Kio) | 812 Mio | 981 / 169 Mio | 843 / 31 Mio |
| biais 3 (moyenne 301 Kio) | 813 Mio | 1 023 / 210 Mio | 863 / 50 Mio |

Essais écartés, sur le même modèle : changer seulement de stratégie (−40 à −110 Mio), réduire les blocs à 32 ou 16 Mio
(peu d'effet), mémoire dédiée seulement à partir de 4 Mio (peu d'effet). Le modèle sous-estime l'appareil (169-210 Mio
inutilisés contre 360) : le mélange de tailles réel n'est pas connu. Le modèle ne tourne pas dans le pilote Apple (il lui
faut les en-têtes VMA et Vulkan) : là, seul le câblage est vérifié.

## 5. Bilan

- **Coût supprimé** : la mémoire physique des trous dans les blocs de 64 Mio (360 Mio inutilisés à 173 s de jeu sur l'appareil ;
  169-210 → 31-50 Mio dans le modèle).
- **Coût restant** : la fragmentation des allocations de moins de 1 Mio ; la croissance de la part « interne » de l'empreinte
  (2,44 → 2,54 Go), non traitée ici.
- **Chemin critique** : aucun changement des images par seconde n'est attendu ni revendiqué.
- **Mémoire** : c'est l'objet du correctif ; gain non mesuré sur l'iPhone.
- **Risques** : chaque allocation de 1 Mio ou plus crée son propre tas Metal ; le temps de cette création n'est pas modélisé
  et pourrait causer des saccades au chargement de textures. Le réglage « GPU memory packing » sur Disabled rétablit le
  comportement précédent. Aucune réservation, attente, résolution, précision, limite d'images, SPU ni option LLVM modifiée ;
  aucun fichier d'entrée des identités de code généré : caches du joueur valides.

## 6. Protocole iPhone

Black Ops II, 3 minutes de jeu ou plus, export : `GPUPACK925 enabled=1 dedicated=…`, puis `JITMEM vma_unused` (360 Mio à 173 s
sur la build 724), `MEMPARTS923 graphics` et l'empreinte. Signaler toute saccade nouvelle à l'apparition de textures.
