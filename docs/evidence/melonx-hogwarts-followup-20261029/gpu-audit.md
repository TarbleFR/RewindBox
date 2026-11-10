# Audit GPU supplémentaire — 29 octobre 2026

Base : MeloNX `13700519f3abc4e6d7ed8a065b118b2cc59bcd67`, intégration RewindBox `Claude` à `c609b0d05a583d2d39f636f328830a6256439807`. Aucun push, Action, build Apple ou FPS iPhone mesuré. Les quatre suites ci-dessous compilent du C# de production avec .NET 10.0.100/Linux ; les frontières natives sont doublées. Les reçus lient les sources, postimages, fixtures et méthodes extraites effectivement compilées.

## 1. Propriété des command buffers dans Auto

`adapt_auto_ownership.py` ne change que `Auto.cs` : le `BitMap` dynamique et son `long[1]` deviennent le `BitMapStruct<Array1<long>>` existant. Les 16 slots rentrent dans les 64 bits en place. Le champ doit rester mutable ; readonly provoquerait des copies défensives. Une garde refuse une modification de la capacité avant toute mutation.

Le test compile Auto, les deux bitmaps, les tableaux fixes et CommandBufferScoped complets. AddDependant est repris intégralement du pool réel. Le transport/completion natifs restent doublés. Il vérifie 16 slots, 8192 recyclages, graphe diamant, libération propriétaire avant completion, mirroring, reads/writes, refus des incréments après destruction et 2,4 millions de cycles de références atomiques concurrents. Il ne prétend pas autoriser des mutations concurrentes du bitmap lui-même.

69 861 assertions par variante. Pour 100 000 Auto<TinyPayload> : **8 800 000 → 5 600 000 octets**, soit 32 octets et un tableau séparé supprimés par owner sur ce runtime. La suppression vaut pour les créations de ressources ; aucune baisse de RSS globale ou de temps par image n'est mesurée.

Fichiers : `test/melonx_auto_ownership_test.py`, `test/melonx_auto_ownership/{Program,Boundaries}.cs`, reçu `auto-ownership-checks.json`.

## 2. Cache de buffers convertis sans entrées vides

`adapt_converted_cache.py` change `CacheByRange.cs` : TryGetValue, Remove et AddDependency ne passent plus par GetEntries quand la plage n'existe pas. Seul Add crée une entrée. Les hits avec valeur null (sentinelles de draw count), le premier résultat dans une plage, les dépendances et l'ordre clé/payload de destruction sont conservés. L'ordre d'énumération entre plages du Dictionary n'est pas un contrat préservé.

**Limite essentielle :** les conversions normales ajoutent souvent le résultat immédiatement après le miss. Le correctif ne supprime pas l'allocation nécessaire de cette vraie entrée, ni celle des valeurs. Le test mesure explicitement ce cas pour éviter d'en attribuer un gain fictif.

32 942 assertions par variante ; 12 006 requêtes, 9062 mutations, 130 cas de cycle de vie. Cache, clés et Dependency complets, payload GPU doublé. Pour 20 000 opérations après échauffement :

| Cas | Avant | Après | Plages retenues avant → après |
|---|---:|---:|---:|
| Miss sans ajout | 2 599 944 octets | 0 | 20 000 → 0 |
| Remove absent | 640 216 octets | 0 | 0 → 0 |
| Dépendance absente | 2 599 944 octets | 0 | 20 000 → 0 |
| Hit | 0 | 0 | 1 → 1 |
| Miss puis vrai Add | 4 999 944 octets | 4 999 944 octets | 20 000 → 20 000 |

Fichiers : `test/melonx_converted_cache_test.py`, `test/melonx_converted_cache/{Program,Boundaries}.cs`, reçu `converted-cache-checks.json`.

## 3. Blocs natifs dédiés et échecs avant publication

`adapt_allocator_blocks.py` change `MemoryAllocatorBlockList.cs` et contient deux corrections séparées.

### Suivi dédié

Un bloc dédié ne peut jamais servir une autre sous-allocation. Il n'a plus besoin d'être inséré dans la liste triée des pools ni d'y être recherché linéairement lors de sa libération. Une liste séparée, créée à la première allocation dédiée, conserve les blocs dédiés. Un index dans Block permet le retrait par échange du dernier élément, sous le même verrou d'écriture. Les free ranges, verrouillage, mapping, tailles, politique dédiée et libération native après les références restent inchangés. Le cas du dernier élément évite les écritures d'échange inutiles.

10 000 retraits/réinsertions, 2048 blocs dédiés vivants : **10 250 093 visites → au plus 20 000**, et 10 000 comparaisons d'insertion → 0. Dernière mesure sans probes : 13,493 → 4,765 ms. Petit ensemble de 32 blocs : 3,650 → 4,545 ms ; un seul bloc : 11,425 → 10,898 ms. Mesures hôte brèves, aucun seuil de timing utilisé pour déclarer le test réussi, aucun gain CPU universel affirmé.

Le test produit deux régimes déterministes avec 8035 allocations/libérations et 15 999 333 octets sentinelles contrôlés dans chacun. Avec poolSize16 et requêtes d'au moins16 octets (tout dédié), traces natives et pic de226834 octets sont strictement identiques. Avec poolSize4096, l'ordre relatif des pools équivalents peut changer : l'ancien BinarySearch était influencé par des blocs dédiés de taille égale. Cette différence est **explicitement conservée** dans les reçus : toujours1870 allocations natives, mais mapping924→910 et pic251260→255356 octets (+un bloc4096). Octets, alignements, absence de chevauchement et libérations restent corrects. Les identités physiques des pools ne sont pas promises identiques.

Sur ce runtime64bits, le champ index tient dans la disposition existante de Block : 176 octets alloués par construction avec ses dépendances avant/après. L'objet collection prend8 octets de plus, puis une liste dédiée paresseuse et sa capacité propre. Ce n'est pas une réduction globale de mémoire native, mais une réduction de travail sur le chemin d'allocation fréquent. La capacité séparée des deux listes a également un coût de références arrondies.

### Nettoyage des échecs

Un vkAllocateMemory réussi crée une allocation qui appartient à la méthode jusqu'au succès d'InsertBlock. Le finally libère toute allocation non publiée ; il n'unmap que si MapMemory a réussi. Les mêmes erreurs continuent de remonter. La libération après publication reste à la charge du bloc et des références normales.

Quatre scénarios, 16 tentatives chacun : erreur retournée par MapMemory, exception du binding MapMemory, échec injecté avant construction du Block, échec injecté avant publication. Les quatre laissaient16 handles chacun (et16 mappings pour les deux derniers) dans le témoin. **Zéro handle/mapping perdu dans la candidate.** Le rejet par AllocateMemory lui-même ne créait déjà aucun handle et reste inchangé. Les deux points de défaillance managée sont des injections explicites, sans prétendre reproduire un OOM physique.

La suite compile les classes complètes MemoryAllocatorBlockList, MemoryAllocation, les helpers d'alignement et l'exception Vulkan. Elle couvre aussi arène importée fixe, fragmentation, épuisement sans croissance, mapping incompatible, invalid alignment et deux régimes de concurrence (8 workers,10 240 allocations chacun). Le driver Vulkan est un double strict ; aucune GPU commande/fence n'a été supprimée.

Fichiers : `test/melonx_allocator_blocks_test.py`, `test/melonx_allocator_blocks/{Program,Boundaries}.cs`, reçu final `allocator-blocks-checks.json`. Le reçu `allocator-lifetime-only-checks.json` est intermédiaire, **ne pas le présenter comme preuve du code final**.

Postimage finale : `bb57d6943937c038bdcc7866a6da14ae5ceb6771d836e63403da519c6fc255ae`.

## 4. Invalidation des conversions indirectes

`adapt_indirect_cache_key.py` change aussi `CacheByRange.cs`, après le correctif2. TopologyConversionIndirectCacheKey et son champ _baseKey étaient readonly ; SetBuffer mutait une copie défensive de la clé imbriquée. La clé stockée gardait null, puis Dispose passait null à DirtyIndexBuffer au lieu de la vraie conversion. Deux qualifiers readonly sont supprimés. L'égalité structurelle ignore toujours l'identité du buffer converti.

Le test part du cache déjà corrigé2 et compile la méthode de production GetBufferTopologyConversionIndirect **entière**, les quatre wrappers cache de BufferHolder, le CacheByRange complet, DirtyIndexBuffer et BoundEquals. Le passage SetBuffer avant boxing et mise en cache est donc exécuté par le vrai appelant. La conversion shader, allocation et binding natifs restent doublés. Trois causes d'invalidation (source index, indirect, compteur), tailles d'index1/2/4 et offsets variés : **75 invalidations du buffer lié manquées → 0**, 1177 assertions par variante. Identité des hits, recréation, valeurs null et destruction unique préservées. Correction de cohérence, aucun gain FPS revendiqué.

Fichiers : `test/melonx_indirect_cache_key_test.py`, `test/melonx_indirect_cache_key/{Program,Boundaries}.cs`, reçu `indirect-cache-key-checks.json`.

## Pistes écartées et sources

- Une recherche bornée par taille dans la liste d'allocations aurait surtout amélioré la sous-allocation. La piste a été remplacée par le suivi dédié, plus pertinent pour la configuration MoltenVK probable.
- **Pas de réactivation aveugle du pooling.** Le pin contient EnableSuballocationPooling=false. L'historique l'introduit dans le commit massif `2889267834c7581ad5e2753de6dbda6f5ae3b5fa`, sans justification détaillée du choix. On ne prétend pas connaître l'intention de l'auteur.
- [Historique exact de l'allocateur](https://github.com/AzureDominus/melonx/commit/2889267834c7581ad5e2753de6dbda6f5ae3b5fa).
- [MoltenVK v1.4.0 MVKDevice.mm](https://github.com/KhronosGroup/MoltenVK/blob/v1.4.0/MoltenVK/MoltenVK/GPUObjects/MVKDevice.mm), maxMemoryAllocationCount attribué à kMVKUndefinedLargeUInt32.
- [Constante MoltenVK](https://github.com/KhronosGroup/MoltenVK/blob/v1.4.0/MoltenVK/MoltenVK/Utility/MVKFoundation.h), constante obtenue à partir d'une très grande puissance de deux. Avec la formule de MeloNX16GiB/limite, la taille du pool devient minuscule : ceci soutient le régime dédié comme cible pertinente, **sans authentifier le dylib de l'iPhone**.
- Aucune modification de maxMemoryAllocationCount, du budget natif, du cache texture, du GC, des fences ni des réglages du joueur.
