# Hogwarts Legacy — deuxième lot de corrections mémoire et CPU

**29 octobre 2026 — candidat local RewindBox, branche `Claude`.**

**Mise à jour après la demande de compilation :** ce lot de douze correctifs
est poussé et intégré au **Core MeloNX84**, source `5045889f`, run
`40895446303` réussi. Les deux bibliothèques NativeAOT et leur fonctionnement
sur simulateur sont vérifiés. Le présent document conserve les mesures Linux
d'origine ; les résultats Apple et leurs contreparties figurent dans le
[compte rendu du Core84](melonx-hogwarts-core-2026-10-29.md).

Douze nouveaux adaptateurs sont implémentés, intégrés à la préparation de MeloNX et couverts par douze portes de validation ciblées. Ils modifient seize fichiers C# existants et ajoutent un fichier. La bibliothèque managée complète compile en Release, avec zéro erreur. Les défauts de rétention, d'allocation temporaire et d'invalidation décrits ici sont reproduits dans des tests exécutables.

La priorité est de réduire le travail répété du moteur et de rendre les objets inutiles récupérables. Les résultats ci-dessous mesurent ces mécanismes sur l'hôte Linux x64 avec .NET 10.0.100. Ils ne mesurent pas la RAM résidente ni les FPS de Hogwarts Legacy sur iPhone. Le signalement de 2–5 FPS au menu et dans les cinématiques reste le problème à valider sur appareil ; ce lot ne démontre pas à lui seul la part de chaque mécanisme dans ce ralentissement.

## 1. Périmètre exact et provenance

| Élément | Identité ou résultat |
|---|---|
| Dépôt | `TarbleFR/RewindBox`, branche `Claude` |
| Base du patch | `c609b0d05a583d2d39f636f328830a6256439807` |
| Base du moteur préparé | Adaptations engine82 présentes dans cette révision |
| MeloNX amont | `13700519f3abc4e6d7ed8a065b118b2cc59bcd67` |
| Arbre Git amont | `82a29e6f593f6244869481e9a489b8d5154175fe` |
| Entrées de préparation | 86, dont 12 nouveaux adaptateurs ; 73 anciennes entrées inchangées et la recette de préparation mise à jour |
| Sources et projets préparés | 4 095 → 4 096 fichiers ; 16 modifiés, 1 ajouté, aucune suppression |
| Validation ciblée | 12 reçus réussis, reliés aux fichiers actuels par SHA-256 |
| Sortie gérée | `Ryujinx.Library` et ses dépendances, Release / linux-x64 |
| Validation Apple ou appareil | Non exécutée pour ce lot |

**Ce lot n'est pas une validation cumulée de vingt-trois adaptateurs.** Le précédent lot local de onze adaptateurs n'était plus accessible après le changement d'espace de travail et n'était pas présent dans la branche distante récupérée. Le présent patch contient les douze corrections de cette continuation, sur la base exacte ci-dessus. Sa combinaison avec le premier patch nécessite de récupérer ce dernier et d'examiner les chemins qui se recouvrent. Les preuves ici ne sont pas étendues à cette combinaison absente.

L'origine amont était inaccessible depuis cet environnement. Le même commit a été récupéré depuis le miroir GitHub `AzureDominus/melonx`, puis les 4 990 blobs ont été vérifiés contre l'arbre Git attendu. La version du SDK a été contrôlée avec l'empreinte officielle. Le restore public initial échouait sur `Ryujinx.LibHac 0.21.0-alpha.129` ; le paquet exact a été récupéré dans un artefact historique et réutilisé. Le run historique avait échoué dans son ensemble : seul son paquet LibHac terminé est réemployé, sans présenter ce run comme une validation globale réussie et sans reconstruire LibHac.

Références : [intégration](evidence/melonx-hogwarts-followup-20261029/integration.json), [source amont](evidence/melonx-hogwarts-followup-20261029/source-recovery.json), [SDK](evidence/melonx-hogwarts-followup-20261029/dotnet-sdk-provenance.json), [paquet LibHac](evidence/melonx-hogwarts-followup-20261029/libhac-package-provenance.json).

## 2. Rétention des anciens handles de texture

**Adaptateur : `adapt_texture_handle_dependencies.py`.**

Lors d'un remappage, `ReplaceHandles` construisait les remplaçants et leur transmettait les dépendances, puis libérait les handles de suivi CPU. Les anciens `TextureGroupHandle` restaient toutefois reliés au graphe de dépendances. Les héritages transitifs faisaient grossir ce graphe à chaque remplacement. Cela retenait des objets devenus inutiles et multipliait les notifications d'une modification.

Le correctif termine l'héritage de tous les remplaçants avant de détacher les liens réciproques des anciens handles. Il conserve les références de copies différées et les actions déjà enregistrées dans `GpuContext`. Un ancien propriétaire peut donc rester vivant tant qu'une copie ou une synchronisation l'exige, puis devenir récupérable à la fin de ce travail.

Une seconde anomalie apparaissait lors d'héritages répétés sur des régions fragmentées : le remplaçant pouvait créer une dépendance vers lui-même. Sa notification finissait par effacer son propre drapeau `Modified` via `DeferCopy(this)`. Une garde exclut ce lien sans signification.

### Résultats des scénarios de rétention et de dépendance vers soi

Les quatre premières lignes mesurent 32 remappages successifs. La dernière correspond à une reproduction explicite de création d'un lien vers soi.

| Mesure du scénario contrôlé | Avant | Après |
|---|---:|---:|
| Anciens handles retenus après récupération | 32 | 0 |
| Handles accessibles dans le graphe | 34 | 2 |
| Liens de dépendance | 1 122 | 2 |
| Notifications par modification | 33 | 1 |
| Liens vers soi, reproduction explicite | 2 | 0 |

Les 83 scénarios couvrent également huit anciens propriétaires retenus pendant leurs actions GPU, leur libération après drainage, les échecs de création de sync et un remappage vers une zone non mappée. Dans ce dernier cas, le pair conserve la copie différée, copie la valeur attendue, puis permet la récupération de l'ancien propriétaire. Les données, les compteurs de libération CPU et le digest fonctionnel sont identiques entre témoin et candidat ; le drapeau `Modified` est volontairement corrigé dans le cas de dépendance vers soi.

Le test compile `TextureGroupHandle` et `TextureDependency` complets, les méthodes réelles de remplacement/héritage et le parcours réel des actions de synchronisation. Le pilote et les frontières de suivi CPU sont simulés. Une revue indépendante a confirmé l'ordre des opérations et l'absence de lecteur actif nécessitant les liens des handles retirés.

Preuves : [test des dépendances](evidence/melonx-hogwarts-followup-20261029/texture-handle-dependencies-checks.json), [revue indépendante](evidence/melonx-hogwarts-followup-20261029/independent-texture-review.json).

## 3. Allocations temporaires sur les chemins fréquents

Les chiffres de cette section sont des **octets alloués par les opérations mesurées**, après échauffement lorsque précisé. Ils ne sont pas des octets de RAM résidente économisés dans une session de jeu et ne doivent pas être additionnés pour annoncer un gain global.

### Suivi mémoire : conserver l'instantané au bon moment

**Adaptateur : `adapt_tracking_snapshots.py`.**

`RegionHandle.Signal` créait un tableau avec `ToArray` avant de relâcher le verrou de suivi pour exécuter une préaction. Le remplacement utilise un propriétaire local de type `ref struct` : la liste reste empruntée tant que le verrou est conservé ; elle est figée à la même frontière de déverrouillage que précédemment. Un seul handle tient directement dans le propriétaire. Les tableaux de 2 à 4 096 références viennent d'un pool privé et sont rendus après réacquisition du verrou, dans un `finally`, avec effacement des références. Au-delà, un tableau temporaire reste utilisé.

Ce seuil borne la taille des tableaux réutilisés, sans imposer un plafond aux objets du jeu. Les préactions, l'ordre des signaux, les protections, la réentrance et les mutations autorisées avant le gel de la liste sont préservés. Le coût conservé est celui de la capacité du pool après échauffement.

| Handles dans l'instantané | Allocation avant par événement | Allocation après par événement |
|---:|---:|---:|
| 1 | 32 octets | 0 |
| 16 | 152 octets | 0 |
| 512 | 4 120 octets | 0 |
| 4 096 | 32 792 octets | 0 |
| 4 097 | 32 800 octets | 32 800 octets |

Les 156 cas par variante produisent la même trace de 5 661 événements. Les 130 emprunts instrumentés sont tous rendus et effacés, y compris dans les cas imbriqués et les exceptions. Vingt classes de production de suivi/plages sont utilisées ; la protection mémoire native constitue une frontière simulée.

### Découpage des plages mémoire

**Adaptateur : `adapt_multirange_slice.py`.**

Un résultat ne contenant qu'un fragment est construit directement, sans liste intermédiaire. Pour plusieurs fragments, le suffixe utile est compté, puis copié dans un tableau privé de taille exacte. Aucun tableau appartenant à l'appelant n'est renvoyé par alias. Le comportement historique sur les trous, les tailles nulles et les calculs extrêmes est conservé ; un contrôle refuse un tableau dont le remplissage serait incomplet.

| Résultat d'une découpe | Avant | Après |
|---|---:|---:|
| Un fragment extrait d'une plage fragmentée | 120 octets | 0 |
| Deux fragments | 176 octets | 56 octets |
| 512 fragments | 24 760 octets | 8 216 octets |
| Entrée vide | 32 octets | 0 |

25 300 cas et 244 461 assertions par variante passent, avec un oracle indépendant pour les intervalles valides et des comparaisons différentielles sur les valeurs extrêmes. Les producteurs ont été examinés : ils remplissent leurs tableaux avant publication. Le correctif n'ajoute pas une garantie de snapshot atomique face à une modification concurrente non autorisée du tableau fourni par l'appelant.

Une première variante supprimait des allocations mais présentait un doute sur le coût CPU. Elle a été approfondie avec quatre implémentations, douze tours entrelacés par scénario et rotation de l'ordre dans le même exécutable. La variante retenue réduit notamment le scénario de 512 fragments de 3 675 à 1 721 ns dans cette expérience. Ces durées restent propres à l'hôte ; la preuve principale reste l'équivalence et la réduction déterministe des allocations.

### Parcours des groupes de textures

**Adaptateur : `adapt_texture_group_callbacks.py`.**

Les lambdas capturant l'état des appels deviennent des callbacks statiques génériques recevant l'état local par référence. Trois délégués propres à chaque instance sont également retirés. Les parcours restent synchrones et l'état n'est pas déplacé dans des champs temporaires partagés : un appel réentrant garde son propre état.

Sur 20 000 appels, `SynchronizeMemory` passe de 1 920 000 à 0 octet alloué, `FlushModified` de 2 080 000 à 0, et `SignalModified` ainsi que `SynchronizeDependents` de 1 280 000 à 0 chacun. Les 8 577 scénarios par variante conservent le même digest d'effets et les quinze exceptions injectées. La construction des groupes dans la fixture alloue 216 octets de moins par groupe ; cette taille dépend de la fixture et du runtime.

### Parcours des régions d'une texture

**Adaptateur : `adapt_texture_region_cursor.py`.**

Un énumérateur de type valeur est ajouté à `SizeInfo`. Il est employé dans la comparaison de régions contiguës ordonnées et dans leur validation d'ordre initiale. L'ancien `IEnumerable` reste disponible et sert d'oracle. Les replis pour les mappings fragmentés ou invalides conservent leur comportement.

Une comparaison ordonnée passe de 304 à 0 octet alloué ; le scénario froid nécessitant la validation de deux textures passe de 608 à 0. Le repli fragmenté reste à 864 octets et la sous-ressource unique reste à zéro. Les 1 199 cas de curseur, 26 311 assertions associées et 12 170 vérifications de recouvrement passent. La fixture de recouvrement historique a été réutilisée parce que ses entrées de production ont changé ; les suites historiques sans entrée modifiée n'ont pas été rejouées.

Preuves : [suivi](evidence/melonx-hogwarts-followup-20261029/tracking-snapshot-checks.json), [découpes](evidence/melonx-hogwarts-followup-20261029/multirange-slice-checks.json), [comparaison CPU approfondie](evidence/melonx-hogwarts-followup-20261029/multirange-review.json), [callbacks](evidence/melonx-hogwarts-followup-20261029/texture-group-callbacks-checks.json), [curseur](evidence/melonx-hogwarts-followup-20261029/texture-region-cursor-checks.json).

## 4. Durées de vie du noyau émulé

### Attentes terminées

**Adaptateur : `adapt_kernel_wait_lifetime.py`.**

Trois références managées restaient vivantes après leur période utile : la valeur d'un nœud remis dans le pool de listes d'attente, les cases du tableau d'objets attendus du thread, et l'objet signalé après extraction de son index. Elles sont maintenant effacées au terme de leur usage. Les décréments de références natives acquis par l'attente restent à leur emplacement logique ; le nettoyage du tableau est protégé par `finally`.

181 scénarios, 4 000 cycles concurrents du pool et trois reproductions avec références faibles montrent les rétentions avant correction et leur disparition après. L'algorithme d'attente, les objets de synchronisation, le refcount et le pool sont ceux de production ; l'ordonnanceur complet ne s'exécute pas dans la fixture. Ce changement ne prétend pas corriger toutes les exceptions possibles du noyau : les interruptions préexistantes du nettoyage si `Destroy` lève une exception restent une limite distincte.

### Requêtes IPC recyclées

**Adaptateur : `adapt_ipc_request_lifetime.py`.**

Avant chacun des cinq retours existants au pool, `KSessionRequest` efface `ClientThread`, `ServerProcess` et `AsyncEvent`. Les descripteurs restent réutilisables et les étapes de complétion, réveil, unmapping et refcount conservent leur ordre. Les 136 scénarios et 4 000 cycles concurrents passent ; les trois participants retenus dans la reproduction deviennent récupérables. Le transport IPC natif et le scheduler complet ne sont pas exécutés.

### Armement des temporisateurs

**Adaptateur : `adapt_kernel_timer_allocations.py`.**

L'enveloppe immuable allouée à chaque armement devient une structure stockée dans la liste existante. Une génération et une identité d'époque distinguent deux armements successifs du même objet à la même échéance, y compris lors d'un débordement forcé du compteur. L'ordre des échéances, le verrou et le worker existants sont conservés.

200 000 armements/annulations après échauffement passent de 6 400 000 à 0 octet alloué. Les 139 scénarios, 20 019 assertions par variante et 2 048 callbacks délivrés par le worker unique après des armements/annulations concurrents passent avec une horloge/frontière d'attente contrôlée. **Compromis :** une case de capacité de liste passe de 8 à 32 octets, soit 24 octets supplémentaires par case réservée, en échange de la suppression de l'objet de 32 octets à chaque armement. Un nouvel objet d'époque n'est créé qu'au débordement du compteur.

Preuves : [attentes](evidence/melonx-hogwarts-followup-20261029/kernel-wait-lifetime-checks.json), [IPC](evidence/melonx-hogwarts-followup-20261029/ipc-request-lifetime-checks.json), [temporisateurs](evidence/melonx-hogwarts-followup-20261029/kernel-timer-allocations-checks.json).

## 5. Ressources, caches et allocations Vulkan

### Ownership des ressources

**Adaptateur : `adapt_auto_ownership.py`.**

Le bitmap des command buffers devient le `BitMapStruct<Array1<long>>` existant. Les seize slots tiennent dans ses 64 bits, sans tableau séparé. Le champ reste mutable afin que les opérations ne s'appliquent pas à des copies défensives. Une garde de préparation refuse une dérive de capacité. Les opérations atomiques de refcount et les liens de dépendance restent les mêmes.

100 000 propriétaires allouent 8 800 000 → 5 600 000 octets, soit 32 octets de moins chacun sur cet hôte. Les 69 861 assertions par variante incluent 8 192 recyclages de slots et 2,4 millions de cycles concurrents de refcount. La concurrence testée porte sur les références atomiques, pas sur des mutations simultanées du bitmap qui n'étaient déjà pas garanties.

### Cache de conversions

**Adaptateur : `adapt_converted_cache.py`.**

Les recherches, suppressions et dépendances visant une plage absente ne créent plus une liste et une entrée de dictionnaire. Seul l'ajout réel les crée. Sur 20 000 recherches sans ajout ultérieur, les allocations passent de 2 599 944 à 0 octet et les plages retenues de 20 000 à zéro.

La nuance est essentielle : un miss suivi d'un véritable ajout conserve son allocation nécessaire, mesurée à 4 999 944 octets dans les deux versions. Le correctif ne supprime donc pas la mémoire des conversions utiles. Les sentinelles nulles, le premier match et les effets de destruction au sein d'une entrée sont conservés. L'ordre entre plages distinctes du dictionnaire n'est pas garanti. La suite exécute 12 006 requêtes, 9 062 mutations et 130 cas de cycle de vie par variante.

### Invalidation des indices indirects

**Adaptateur : `adapt_indirect_cache_key.py`.**

`TopologyConversionIndirectCacheKey` et son champ `_baseKey` étaient `readonly`. L'appel `SetBuffer` modifiait une copie défensive de la structure imbriquée ; la clé réellement mise en cache conservait un buffer nul. Sa destruction n'invalidait donc pas le vrai buffer d'indices lié. Les deux qualifications `readonly` sont retirées ; l'égalité structurelle conserve ses critères.

Le test exécute la méthode complète de conversion de production : `SetBuffer` précède effectivement le boxing de la clé et sa mise en cache. Il utilise ensuite les vraies méthodes `DirtyIndexBuffer` et `BoundEquals`. Les 75 invalidations manquées du témoin deviennent zéro dans le candidat, sur 75 scénarios et 1 177 assertions par variante. Le shader et les frontières GPU sont simulés. Il s'agit d'une correction de cohérence, sans promesse de gain de FPS.

### Allocateur natif

**Adaptateur : `adapt_allocator_blocks.py`, deux mécanismes.**

Les blocs dédiés sont suivis dans une liste séparée créée à la demande. Un index permet leur retrait par échange avec le dernier élément sous le verrou d'écriture existant. Ils ne participent plus au tri ni aux recherches dans les pools dont ils ne peuvent servir les sous-allocations.

Pour 10 000 retraits/réinsertions avec 2 048 blocs dédiés vivants, les visites passent de **10 250 093 à 20 000**, les comparaisons d'insertion de 10 000 à zéro, et le temps hôte observé de 13,49 à 4,77 ms. À 32 blocs, le même reçu mesure **3,65 à 4,54 ms** : le gain CPU n'est pas universel. La cause exacte de cet écart de durée n'est pas isolée par ce microbenchmark ; la création initiale de la liste et l'échauffement précèdent le chronométrage.

Le second mécanisme garde la responsabilité d'une allocation native réussie jusqu'à sa publication dans l'allocateur. Un échec de mapping, de construction managée ou de publication déclenche le nettoyage ; le mapping n'est retiré que s'il avait réussi. Les quatre familles de seize échecs contrôlés passent de 64 handles natifs perdus à zéro, avec disparition des mappings perdus correspondants. Les échecs de construction/publication sont explicitement injectés, sans prétendre reproduire un OOM physique.

Le régime tout dédié conserve exactement traces et pic natif. Dans le régime mixte avec pools de 4 096 octets, l'ordre des blocs équivalents peut changer : le test conserve 1 870 allocations natives, réduit les mappings de 924 à 910, mais son pic monte de **251 260 à 255 356 octets**, soit **4 096 octets supplémentaires**. L'absence de chevauchement, les alignements et les données sentinelles restent corrects. La collection prend aussi une référence supplémentaire et une capacité de liste dédiée ; ce correctif ne constitue pas une baisse générale de mémoire native.

Une recherche par taille a été étudiée puis abandonnée au profit du suivi dédié. Le pooling amont reste désactivé : son activation générale sans preuve sur appareil n'est pas retenue. Les budgets natifs et les paramètres de GC ne sont pas modifiés.

Preuves : [ownership](evidence/melonx-hogwarts-followup-20261029/auto-ownership-checks.json), [cache](evidence/melonx-hogwarts-followup-20261029/converted-cache-checks.json), [clé indirecte](evidence/melonx-hogwarts-followup-20261029/indirect-cache-key-checks.json), [allocateur](evidence/melonx-hogwarts-followup-20261029/allocator-blocks-checks.json), [audit détaillé](evidence/melonx-hogwarts-followup-20261029/gpu-audit.md), [revue indépendante](evidence/melonx-hogwarts-followup-20261029/independent-gpu-review.json).

## 6. Vérification de l'assemblage final

La vérification finale relie les résultats aux sources effectivement compilées :

- Les 86 entrées de préparation correspondent aux fichiers du dépôt ; les 73 anciennes entrées hors recette restent identiques.
- Les 54 entrées déclarées par les douze reçus et leurs 83 entrées amont correspondent aux fichiers actuels.
- Les 4 096 sources/projets du répertoire de compilation correspondent exactement à une préparation fraîche. Le delta comporte dix-sept chemins et les 127 membres de l'archive de sources adaptées correspondent également à cet arbre.
- Les postimages complètes correspondent lorsqu'aucun autre adaptateur n'agit dans le fichier. Pour les cinq écarts attendus, les méthodes compilées sont reliées par empreinte et la composition est explicitée : deux changements `readonly` du cache, anciens diagnostics `ExitProcess`, changements de durée de vie préexistants et combinaison des adaptateurs de textures.
- Le contrôle principal vérifie vingt-et-une méthodes exactes. Les revues indépendantes vérifient aussi `AddDependant`, la conversion indirecte, l'invalidation et ses quatre wrappers. Le header extrait de `TextureGroup` diffère seulement par l'import de logging et le champ `_disposed` préexistants dans engine82 ; ses méthodes et son constructeur utile restent conformes.
- Les huit assemblies examinées dans la sortie `Ryujinx.Library` sont identiques à celles produites par leurs projets respectifs.
- Le YAML est analysé, les douze nouvelles portes sont câblées une fois chacune, les vingt-cinq fichiers Python concernés passent l'analyse syntaxique et `git diff --check` réussit.

La première compilation complète, sur les neuf premiers adaptateurs, prend 98,57 s côté MSBuild : zéro erreur, vingt-sept avertissements provenant de fichiers inchangés par le lot. La première sortie de compilation finale s'arrête sans résumé terminal : elle est conservée comme incomplète, pas comme succès. Une passe incrémentale explicite termine ensuite la bibliothèque avec les douze adaptateurs : zéro erreur, zéro avertissement dans cette passe, 5,96 s côté MSBuild. Les avertissements de la première compilation ne sont pas effacés du bilan.

Les exécutions hôte compilent les classes ou méthodes réelles annoncées ; leurs doubles de pilote, scheduler et ressources sont décrits dans chaque reçu. Aucune exécution n'est présentée comme un test graphique complet du jeu. Les suites natives historiques inchangées n'ont pas été rejouées, et aucun moteur Apple validé précédemment n'a été reconstruit.

Preuves : [intégration finale](evidence/melonx-hogwarts-followup-20261029/integration.json), [compilation et tentatives conservées](evidence/melonx-hogwarts-followup-20261029/managed-library-build.json), [composition des textures](evidence/melonx-hogwarts-followup-20261029/texture-integration-review.json).

## 7. Livraison locale et validation restante

Le patch exporte les douze adaptateurs, leur câblage, les fixtures, les reçus et ce rapport. Il est contrôlé par application dans une copie des fichiers concernés de sa base exacte puis comparaison octet pour octet des fichiers produits. La preuve de transport du patch est fournie à côté de celui-ci ; elle n'est pas incluse dans le patch pour éviter une référence circulaire à sa propre empreinte.

Le prochain résultat utile est une validation Apple du candidat qui sera effectivement retenu, puis une comparaison sur le même appareil, avec les mêmes réglages, dans le menu et la même cinématique. Les éléments à comparer sont le temps d'image, la mémoire résidente et le comportement du GC disponibles dans les journaux de l'application. Aucun nouveau dispositif de télémétrie ni réglage joueur n'a été ajouté à cette fin.

Le candidat conserve les barrières, les références nécessaires aux travaux GPU en cours et les replis de compatibilité. Le travail restant concerne la compilation NativeAOT et le comportement sur appareil, ainsi que la combinaison avec le précédent patch s'il est récupéré. Aucun push, GitHub Action, numéro de livraison, IPA ou release n'a été produit dans cette continuation.
