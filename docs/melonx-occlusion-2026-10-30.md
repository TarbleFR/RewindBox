# RewindBox MeloNX et Hogwarts Legacy

Cette livraison source traite la publication des résultats d’occlusion, les soumissions anticipées liées aux requêtes et la sécurité de l’initialisation JIT. Elle part de `Claude` au commit `293f7feba68eddb0dc7f4a5ec3940b209cc5de35`, conserve le moteur épinglé `13700519f3abc4e6d7ed8a065b118b2cc59bcd67`, LibHac et MoltenVK. Elle ne modifie pas RPCS3 et ne produit pas d’IPA.

Les deux expériences GPU sont OFF par défaut. Leur activation passe par les champs JSON `occlusionQuerySync` et `relaxQueryFlushing` de l’ABI existante `neostation_melonx_configure_graphics`, avant création de la session. Le core lit l’identité du contenu réellement lancé et n’admet que `0100F7E00C70E000`. Le regroupement requiert également l’activation de la synchronisation. Une nouvelle configuration `{}` désactive les deux expériences. Il n’y a pas de nouvelle interface de réglage dans cette livraison de core ; le pont Swift existant transmet déjà ce dictionnaire. L’activation visible dans une future application reste à intégrer et à valider avant expérimentation sur iPhone.

Aucun gain FPS, baisse de mémoire résidente, correction de textures noires ou bon fonctionnement de Hogwarts sur iPhone n’est démontré par les tests hôte décrits ici. Les chiffres du journal du 29 octobre restent des observations historiques, pas un benchmark de ce candidat.

## Modifications du code de production

Les chemins ci-dessous sont les sources finales du moteur après préparation, distinctes des adaptateurs et des tests. Quinze fichiers changent par rapport aux sources de Core87 ; neuf deviennent membres supplémentaires de l’archive de provenance et six membres historiques changent. Les 133 autres membres historiques sont identiques.

| Fichier préparé sous `src` | Modification |
| --- | --- |
| `Ryujinx.Graphics.Gpu/Memory/DeferredCounterReport.cs` | Nouveau transfert d’un résultat scalaire du consumer au propriétaire GPU ; publication unique ; invalidation atomique ; libération unique de la référence mémoire ; aucune libération du query pool par ce wrapper. |
| `Ryujinx.Graphics.Gpu/Memory/CounterCache.cs` | Recherche de l’index zéro ; invalidation correcte des intervalles semi-ouverts, y compris les rapports de 16 octets chevauchants ; accès protégés ; attente hors verrou ; suivi et annulation des rapports différés. |
| `Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs` | Enregistrement du rapport avant sa mise en file ; référence explicite à la mémoire physique ; vérification de mappage ; publication sous le verrou de table des pages qui ordonne unmap/remap. |
| `Ryujinx.Graphics.Gpu/Engine/Threed/SemaphoreUpdater.cs` | Chemin SamplesPassed optionnel ; le callback consumer ne fait qu’enregistrer une valeur ; horodatage capturé conservé ; au plus 1 024 rapports par cache avant drainage. |
| `Ryujinx.Graphics.Gpu/GpuContext.cs` | Suivi par contexte des caches concernés, y compris plusieurs espaces mémoire/canaux ; soumission stricte avant attente ; passage synchrone par le rendu threadé ; publication GPU avant retour ; annulation avant destruction de la mémoire et du renderer. |
| `Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs` | Quand l’expérience est active, les rapports antérieurs du contexte sont publiés avant l’incrément de syncpoint. Le chemin historique est conservé sans rapports. |
| `Ryujinx.Graphics.Vulkan/Queries/CounterQueue.cs` | Un consumer unique possède l’accumulation ; un flush bloquant attend le dernier rapport, même déjà retiré de la file ; attente hors verrou ; refus d’auto-attente du consumer ; état de destruction volatile. |
| `Ryujinx.Graphics.Vulkan/Queries/CounterQueueEvent.cs` | Publication volatile de la complétion après callback ; une requête expirée sans résultat complet devient invalide et ne publie pas un compteur fictif. |
| `Ryujinx.Graphics.Vulkan/Queries/BufferedQuery.cs` | Le test non bloquant utilise aussi la sentinelle du mot haut pour refuser un résultat 64 bits partiellement écrit. |
| `Ryujinx.Graphics.Vulkan/PipelineFull.cs` | Le backend ne déclare plus un rendu conditionnel hôte dont les commandes Vulkan sont commentées ; il soumet les requêtes nécessaires et laisse le GPU invité comparer le résultat côté CPU. Aucun bypass de visibilité permanent. |
| `Ryujinx.Graphics.Vulkan/AutoFlushCounter.cs` | En mode optionnel, le seuil initial de 32 requêtes et le seuil d’attachement > 10 sont remplacés par un regroupement borné à 128 requêtes entre soumissions. Les budgets temporels de 1 et 1,5 ms et les attentes explicites sont conservés. |
| `Ryujinx.Graphics.Vulkan/VulkanRenderer.cs` | Propriété de politique appartenant à l’instance de renderer, assignée avant démarrage des threads. |
| `Ryujinx.Library/Library.cs` | Activation conditionnée au titre réel et aux options ; instanciation distincte pour chaque contexte ; le regroupement dépend du correctif d’ordre. |
| `Ryujinx.Library/EmbeddedGraphicsSettings.cs` | Deux champs JSON booléens OFF par défaut ; identification du contenu avec refus fermé en cas de lecture impossible ; ABI native inchangée. Source suivie : `native/melonx/EmbeddedGraphicsSettings.cs`. |
| `Ryujinx.Cpu/LightningJit/Cache/DualMappedNoWxCache.cs` | Initialisation unique sous verrou ; après toute exception d’allocation, aucune nouvelle tentative dans ce processus. Demandes 1 Gio Hogwarts avec mise à jour / 512 Mio TXM par défaut conservées. |

Les corrections du cache, de l’accumulation de file, de reconnaissance des résultats incomplets et du rendu conditionnel non encodé sont des corrections de cohérence communes. Le retour au comparateur CPU peut ajouter une attente par rapport au chemin erroné qui dessinait sans condition ; la fidélité prime sur ce bypass. Le drainage avant syncpoint et le changement de politique des soumissions restent expérimentaux et spécifiques à Hogwarts. Aucun bypass de visibilité n’est introduit.

## Chronologie établie dans le code épinglé

Le chemin original est `ReportCounter` → callback inscrit dans `CounterQueue` → consumer asynchrone → écriture mémoire invitée. `Counters.Update()` ne fait que réveiller le consumer via `Flush(false)`. En parallèle, `GPFifoClass.Syncpointb` appelle `CreateHostSyncIfNeeded(StrictSyncpoint)` puis incrémente immédiatement le syncpoint invité. Une soumission Vulkan stricte n’attend pas la publication du callback consumer ; avec le GAL threadé, sa commande peut encore être en file. Le jeu peut donc voir le syncpoint avant le compteur. Le reproducer contrôle précisément cette interversion.

En mode expérimental, le rapport est enregistré avant l’appel au renderer. Le consumer produit seulement une valeur, puis publie le drapeau de disponibilité avec une écriture volatile. Le thread GPU force une soumission stricte et effectue un aller-retour synchrone par la file de rendu avant d’attendre le rapport. Le renderer peut donc progresser pendant l’attente. Le consumer ne déclenche aucune écriture invitée susceptible de réclamer le GPU. Le GPU écrit ensuite le compteur et son horodatage, puis incrémente le syncpoint. Les rapports déjà disponibles évitent l’attente ; les rapports invalidés ne publient rien. Une expiration sans callback complet lève une erreur avant le signalement.

Les attentes se font hors verrous du cache, de table des pages et de file. `CounterQueue.Flush(true)` ne tente plus de consommer un événement sous le verrou de file, alors que le consumer peut détenir le verrou de cet événement et attendre de rendre son query object à cette même file. `FlushTo` refuse explicitement l’auto-attente sur le consumer.

Les rapports sont liés au contexte de session, pas à une collection statique. Leur référence mémoire est rendue une seule fois après publication ou annulation. Le contexte annule ses rapports avant de détruire les mémoires physiques ; les callbacks tardifs ne font plus d’écriture invitée. Aucun query pool n’est possédé ou libéré par le wrapper. Le timeout natif existant reste borné à 5 000 ms ; cette livraison ne promet pas une interruption instantanée du pilote en cours de lecture.

## Politique de soumission

Les seuls changements de politique se trouvent dans `AutoFlushCounter.RegisterPendingQuery` et dans la branche liée aux séries de requêtes de `ShouldFlushAttachmentChange`. Le comptage historique et les prédictions de reset restent présents. `ShouldFlushQuery`, les temps limites d’attachement/draw, `Present`, les soumissions explicites, les barrières de ressources, les readbacks, les fences et les seuils de poids mémoire ne sont pas supprimés.

Sur le scénario synthétique de 1 024 requêtes avec changement d’attachement toutes les 16 requêtes et horloge contrôlée, les soumissions anticipées passent de 64 à 8. Le scénario par défaut reste à 64. Ce chiffre mesure les décisions de la vraie classe `AutoFlushCounter` dans un banc d’essai ; il ne mesure pas le débit du GPU Metal, les soumissions d’une scène commerciale ou les FPS sur iPhone.

## Cache JIT et repli progressif

L’audit établit une limite du contrat natif : `DualMappedJitAllocator` peut échouer après obtention de la région RX, après `vm_remap` ou après `vm_protect`, sans exposer l’étape ni garantir la libération des régions partielles. Les trampolines `MeloNXJitSupport.S` transmettent une adresse et une taille au helper ; ils ne fournissent pas de statut transactionnel de rollback. Le `catch (Exception)` historique tentait alors de demander le défaut, même si la première région avait commencé à être préparée.

Ce repli automatique est retiré. Le verrou et le drapeau de tentative sont posés avant tout appel natif. En cas d’échec, les appels suivants refusent une nouvelle réservation ; le chemin hôte existant place déjà le JIT en quarantaine jusqu’au redémarrage du processus. La taille du cache et la sonde RX/RW utilisent toujours la taille réellement allouée. Les alias, la sonde protégée, les entitlements et le helper restent inchangés.

Le repli par paliers de 64 Mio reste non implémenté, faute de rollback prouvé. Une limitation sûre négociée avant toute allocation demanderait un nouveau contrat hôte/helper, pas une boucle autour du constructeur existant. Une prétendue limite universelle de 960 Mo n’est pas retenue. La contrepartie explicite est qu’un refus de 1 Gio exige un nouveau processus au lieu d’un espoir de seconde tentative à 512 Mio.

La préparation du helper pré-touche les pages de 16 Kio. Une arène de 1 Gio peut donc représenter jusqu’à 512 Mio supplémentaires de pages résidentes par rapport à 512 Mio, indépendamment du code déjà émis. Aucun bénéfice de FPS ou baisse de RAM n’est attribué à cette capacité JIT.

## Unreal et différences du fork

Aucun fichier RomFS de Hogwarts, sa version Unreal précise ni le binaire `MeloNX-fork.ipa` n’est disponible dans cette exécution. Les deux recherches du fichier facultatif n’ont pas retrouvé de candidat exploitable. Les observations de l’étude jointe sur le fork restent des observations historiques non répétées ici ; elles ne prouvent pas le code privé du fork.

Les chemins `Config/UserEngine.ini` et `Config/UserDeviceProfiles.ini` ne sont pas validés pour ce titre Switch. Aucune écriture dans les mods, fichiers du jeu, sauvegardes ou clés n’est donc installée. Les CVars suivantes restent à tester individuellement après preuve de chargement : `fx.NiagaraGpuSubmitCommandHint`, `fx.Niagara.SystemSimulation.BatchGPUTickSubmit`, budgets Niagara, translucence, `r.MotionBlurQuality`, `r.DepthOfFieldQuality`, puis résolution interne. Chaque essai doit rester OFF par défaut, préserver tout mod concurrent et pouvoir restituer exactement les fichiers antérieurs.

La revue du chemin de rendu établit aussi un défaut source indépendant du fork : `PipelineFull.TryHostConditionalRendering` réservait un compteur et renvoyait `true` malgré des appels `CmdBeginConditionalRendering` et `CmdEndConditionalRendering` commentés. Le code invité sautait alors sa comparaison CPU, sans condition GPU effective. La correction renvoie `false` après la soumission nécessaire, et le vrai `ConditionalRendering.CounterNonZero` compare la valeur publiée. Le test vérifie zéro/non-zéro avec capacité Vulkan annoncée présente et absente : le contrôle choisit à tort `Host`, le candidat décide effectivement de dessiner ou non. Cela ne démontre pas la résolution des textures noires sur iPhone.

Aucune bibliothèque du fork n’est importée, et MoltenVK reste identique. Les suites historiques de textures, shaders, barrières et mémoire conservent leurs reçus authentifiés dans leur portée inchangée. Les défauts de cache/compteurs corrigés ici ne constituent pas une preuve de résolution des textures noires signalées sur un appareil.

## Validation et provenance

Trois adaptateurs idempotents à contrat intégral avant/après sont ajoutés et enregistrés à la fin de `prepare_embedded.py` : `adapt_occlusion_reports.py`, `adapt_query_batching.py`, `adapt_jit_single_attempt.py`. Leurs trois inventaires refusent tout état inattendu avant une écriture. Le contrat Apple supplémentaire, `occlusion-core-contract.json`, authentifie 108 entrées et 148 membres préparés. L’ancien contrat GPU et ses validateurs restent inchangés ; le nouveau vérificateur authentifie les anciennes entrées avec une liste exacte de trois différences revues : recette, réglages natifs et workflow.

Les tests sont distincts du code de production :

- `test/melonx_occlusion_test.py` et ses deux fichiers C# compilent les vrais rapports/cache/queue et extraient les méthodes de sémaphore/FIFO/table des pages : 274 scénarios candidat, 16 432 vérifications ; le contrôle reproduit deux publications tardives, avec et sans thread de rendu. Les tests couvrent résultat retardé, disponible, invalidé, timeout, teardown, intervalle d’unmap et événement déjà pris par le consumer. Les frontières Vulkan natives sont doublées.
- `test/melonx_query_policy_test.py` compile la vraie classe de flush avec horloge injectée, le rendu conditionnel hôte et son comparateur invité, les méthodes de lecture de résultat et l’initialisation JIT de production : 58 vérifications candidat ; 64 → 8 décisions de soumission ; sentinelles 32/64 bits ; défaillances natives simulées à cinq étapes ; refus d’une seconde tentative ; budget par défaut ; 64 appels concurrents pour une seule allocation. Ce test ne prouve pas un rollback natif, qu’il évite précisément d’utiliser.
- `test/melonx_display_native_test.py` exécute 77 cas, dont options OFF, retour à `{}`, identité réelle Hogwarts, autre titre, identité absente et erreur de lecture ; les cas existants de configuration, génération, mémoire donnée et FPS restent conservés.
- `test/melonx_occlusion_contract_test.py` vérifie les inventaires et les refus d’entrées modifiées sans compilation.

La compilation managée complète Release Linux x64 réussit avec SDK 10.0.100, zéro erreur et 27 avertissements, en 184,79 secondes. Les 147 postimages de ce premier lot correspondent à sa préparation fraîche ; la composition finale comporte 148 postimages après ajout du correctif de rendu conditionnel. Deux essais hôte de restauration parallèle avaient échoué sans diagnostic d’erreur ; leurs journaux sont conservés. Le passage sériel n’a requis aucun changement de code de production. Une compilation incrémentale complète après correction du rendu conditionnel passe également ; son journal `managed-conditional.log` et la nouvelle préparation sont conservés.

Une première compilation Apple intermédiaire `24b1ad9a` a réussi dans le run `40997549028` (artefact `12951728490`), avant la correction supplémentaire du rendu conditionnel. Elle n’est pas la livraison finale. Sa suite Apple de configuration/affichage, dont les entrées sont inchangées, est réutilisée avec son empreinte, le SHA de l’archive et les métadonnées GitHub ; elle n’est pas exécutée une seconde fois. Les deux suites affectées par l’adaptateur et le rendu conditionnel sont réexécutées.

Le workflow `.github/workflows/melonx-core.yml` conserve `build_core.sh`, macOS ARM64, .NET 10.0.100 et les cibles iOS/simulateur ARM64. Il réutilise les dépendances authentifiées et les 29 reçus historiques inchangés de Core87/Core85 et le reçu Apple d’affichage intermédiaire, exécute les deux suites affectées, puis compile les deux bibliothèques NativeAOT avec l’ABI 2 et les 47 exports attendus. Le smoke exécute à nouveau deux sessions homebrew SVC, ferme les sessions et vérifie la restitution des backings sur le nouveau binaire simulateur.

L’état Apple et les empreintes finales doivent être lus dans `core-validation/result.json` du nouvel artefact. Cette version du rapport, rédigée avant lancement CI, ne revendique pas de compilation NativeAOT achevée. Un reçu de livraison séparé fournira le commit, le run et les SHA256 effectivement contrôlés.

## Validation physique restante

Tester séparément le mode OFF, la synchronisation seule, puis le regroupement, avec la même version de Hogwarts, la même mise à jour, les mêmes caches et paramètres. Mesurer menu, cinématique et scène jouable, frametimes médian/p95, mémoire résidente, pauses GC et durée avant épuisement éventuel du JIT. Contrôler visibilité, flickering, textures, résultat après syncpoint, perte/reprise du focus et fermeture/reprise en rendu threadé puis non threadé. Un test hôte ou le smoke homebrew simulateur ne remplace aucune de ces mesures.
