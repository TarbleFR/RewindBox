# Hogwarts Legacy sur MeloNX après la 817

Le journal du titre `0100f7e00c70e000` provient de Ryujinx/LightningJit et de Vulkan/MoltenVK. Le manifeste livré avec la 817 sélectionne le Core MeloNX `8988ced5`. Le commit `15df2d2` avait modifié le moteur S2Arm pour les jeux NVN2.

Les images signées des IPA 803 et 817 donnent les mêmes empreintes pour `MeloNXCore` (`1fc7f4af847f1739…`), `MeloNXJitSupport`, l’extension `MeloNXJITHelper`, StikJIT, le pont MeloNX et les deux bibliothèques MoltenVK de MeloNX. L’exécutable Runner a changé entre ces IPA. Le 30 octobre, la build 603 de Hogwarts avait déjà rencontré la garde à `0x40000003` après une réservation réussie du pool JIT de 1 024 Mio. L’offset du journal ne mesure pas l’occupation du pool de code exécutable. [Empreintes 803](rewind803/signed-payload-identity.json) · [Empreintes 817](rewind817/signed-payload-identity.json) · [Relevé de la 603](../melonx-build603-guard-crash-2026-10-30.md).

| Observation sur iPhone | Interprétation dans la source MeloNX |
| --- | --- |
| `relativeOffset=0x40000003`, `tableBytes=0x40000000`, `sizeIsSignalHint=True` | La table native encode une entrée de 8 octets par page invitée de 4 Kio. Cette table d’un Gio correspond à un espace invité de 39 bits. Le décalage désigne le quatrième octet de la garde commune aux pages absentes. La largeur de l’instruction et son PC restent inconnus. |
| `mainLoadWait=14985 ms` suivi d’un échec de recherche | Un worker pouvait attendre jusqu’à 15 secondes la publication du cache Vulkan principal, avant même de savoir si la variante s’y trouvait. Le compteur `compiled again` consulte aussi l’historique des sessions précédentes. |
| `memoryWarning`, `footprint=3658/4338` Mio | Le pont iOS écrit l’empreinte physique courante puis son pic depuis le lancement. Les deux sources de marge utilisables par le moteur sont `os_proc_available_memory` pour le processus et `kern.memorystatus_level` pour l’appareil. |

## Correctifs intégrés au Core MeloNX

- **Adresses invitées.** Dans `InstEmitMemory.cs`, le chemin ARM64 vérifie le premier et le dernier octet avant la recherche de l’entrée de page et préserve les drapeaux NZCV. Une adresse invalide rejoint la garde. `NativePageTable.cs` valide les intervalles avant le calcul des indices et ne retente qu’une lecture d’entrée de table alignée, entièrement comprise dans la table. `MemoryManagerHostTracked.cs` valide les intervalles virtuels et physiques avant de modifier les mappings. La taille du pool JIT et sa politique d’allocation restent celles de la 817. La trace de l’iPhone ne contient pas l’instruction fautive. Les vérifications ciblées portent sur la garde, les charges littérales, les largeurs scalaires et la préservation des drapeaux, notamment près des bornes.
- **Cache Vulkan.** L’attente de 15 secondes était présente dans le Core du [8 novembre](https://github.com/TarbleFR/RewindBox/commit/7d3ba9c6068af74da609549965f22679b7b29bb3). `PipelineCacheManager.cs` lance l’ouverture et le chargement du cache principal et de ses fichiers secondaires dès l’initialisation du renderer. Un worker qui arrive pendant cette opération peut compiler dans son cache privé. `PipelineState.cs` et `ShaderCollection.cs` partagent une création en cours entre demandeurs de la même variante et libèrent la réservation après un échec. Les variantes distinctes peuvent progresser en parallèle. La lecture du journal de télémétrie `.builds` conserve son fonctionnement précédent.
- **Marge mémoire iOS.** `HostMemoryBudget.cs` et `GpuContext.cs` distinguent une marge inconnue d’une marge nulle. Pour Hogwarts, une marge processus ou appareil inférieure à 20 % déclenche la récupération et le retour à 25 % la termine. `TexturePool.cs` ne libère que des textures froides et propres, détenues uniquement par le pool. `MemoryOwner.cs` limite les tableaux d’upload conservés. `ThreadedRenderer.cs`, `VulkanRenderer.cs`, `BufferManager.cs` et `StagingBuffer.cs` permettent de restituer l’anneau temporaire de texture de 16 Mio après inactivité et confirmation de fin des copies, sans attendre de fence sur le thread de rendu. Les actions de chargement et de stockage des passes bindless restent préservées.

Ces changements touchent le Core Switch 1. Les vérifications sur sources préparées et pilote simulé couvrent les conditions aux limites, la concurrence et la récupération sous pression. La disparition du crash et des gels ainsi que l’objectif de 3,1 Go nécessitent une nouvelle mesure du jeu sur l’iPhone A18 Pro.

## Compilation pour la 818

Le [producteur MeloNX](https://github.com/TarbleFR/RewindBox/actions/runs/44983505128/job/137088932701) a compilé la [source 445896a0](https://github.com/TarbleFR/RewindBox/commit/445896a07bc071c0999de80f490fd1f93a9fc0ff) pour iOS arm64 et le simulateur arm64. Le binaire iOS mesure 39 212 168 octets. Son SHA-256 brut est `4a97317f69fdf2e716b2659fc9047103d57d3e9e2800676808335d244684b42c`. Son empreinte normalisée, qui permet de contrôler la même image après empaquetage et signature, est `8367f3d3c48ee62fbeeb9f26f3aed07c1fb6f55203fcf28d1f6958088e16a1a4`. Deux sessions NativeAOT sur simulateur ont exécuté le programme de test et restitué son backing mémoire.

Sur les sources préparées, les sondes ont passé 669 vérifications de garde et 12 351 vérifications de charges littérales et de traduction bornée. Le chargement du cache a passé 33 vérifications, la comptabilisation de son ancien délai 49 et le replay de variantes 154 sur six processeurs. Ce dernier test est sensible à l’ordre de démarrage des workers sur neuf processeurs. Dans l’essai de deux spécialisations compute simultanées, les 25 paires ont transmis leurs données propres au pilote simulé ; le témoin antérieur transmettait une valeur incorrecte dans les 25 paires.

## IPA privée 818

La [livraison 818](https://github.com/TarbleFR/RewindBox/actions/runs/44984443009) a produit une IPA de 333 784 213 octets, SHA-256 `b80b618a9441c1a48554856f4d67c57588ff4e458ccb28aea9e5ab06750df636`. Les quatre pièces téléchargées, les dix bundles et les 97 images ont été contrôlés. Les six validateurs hors ligne ont réussi. L’image MeloNX empaquetée correspond à l’empreinte publiée ci-dessus. Le helper JIT MeloNX, MeloNXJitSupport, StikJIT, leurs ponts et les deux images MoltenVK de MeloNX conservent leurs empreintes entre la 817 et la 818. Le lanceur et S2Arm embarquent les changements prévus. Une quatrième image, le pont Dolphin recompilé par Xcode, présente l’empreinte déjà livrée dans la 815. La source du pont et l’empreinte du Core Dolphin sont identiques à celles de la 817. [Comparaison signée](rewind818/signed-payload-identity.json) · [Rapport de vérification](rewind818/download818-verification.json).

## Retour au Core 8988ced5 (22 novembre)

À la demande du mainteneur, la Core `445896a0` de la 818 est retirée. Les sources et le pin reviennent à `8988ced5` (run 44753917742, artefact 14638435340, empreinte `1fc7f4af`, contrat `bd3b429d`), soit l'état des livraisons 803 à 817. Aucune recompilation n'est nécessaire.

Ce que montrent les journaux iPhone 816, 817 et 818 :

- La 818 contrôle les bornes à chaque accès mémoire de l'invité, pour tous les jeux.
- Le thread de rendu de la 818 attend les compilations des workers, dans `Dispose` comme au premier usage.
- Première session SSBU en 818 : `queueBackpressure` à 13,2 % du temps, contre 1,2 % en 817.
- Aucune session SSBU n'écrit de cache de pipelines en 818, contre 16 écritures en 817.

Les corrections Hogwarts de la 818 partent avec ce retour. Le plantage Hogwarts observé en 817 (`FHeartBeatThread`) est donc de nouveau attendu.

La boucle de recompilation SSBU existait déjà avec cette Core : 181 recompilations sur 208 compilations en 816, 325 sur 337 en 817. Le cache principal n'atteint jamais `primaryReady` dans ces sessions. Ce retour ne la corrige pas.

## Retour de l'attente du cache principal à Hogwarts (22 novembre)

Le commit `4086c77f` (Core `cf6396a2`, IPA 787) a étendu à tous les titres l'attente du cache principal avant le rejeu des variantes, qui ne valait que pour Hogwarts (`EncodingPolicy.IncrementalArrayDescriptors`). Il a aussi ajouté un `_primaryCacheReady.Reset()` avant la construction du journal. Depuis, SSBU n'atteint plus `primaryReady`, recompile environ 90 % de ses pipelines à chaque session, et sa fermeture dure 14 à 70 s (819 : 69,8 s entre `close begin` et `sessionResult`). L'IPA 786 (Core `6d8cb068`, juste avant ce commit) est la dernière où le cache principal SSBU se rechargeait (144 Mio en 2,3 s) et où les fermetures étaient propres.

L'adaptateur `adapt_hogwarts_pipeline_replay.py` revient à son état d'avant `4086c77f` (`efe6c1da`). La sortie `PipelineCacheManager.cs` retrouve donc l'empreinte `1d370731` : aucun autre adaptateur n'a modifié ce fichier depuis. Le tri différé des variantes, ajouté par le même commit, part avec ce retour. Les correctifs Nextendo (443, 60005, compatibilité consentie) ne sont pas touchés.
