# Hogwarts Legacy sur iPhone, incident du build 777

## Ce qui est arrivé le 17 novembre 2026

Sur l’iPhone 16 Pro Max de 8 Go, le lancement suivant a retrouvé la session Hogwarts `37D75F23-0BFF-4AD8-9945-4E889EE22B79` du PID 40796 ouverte. Son dernier état enregistré était `foreground`. Le processus n’a pas suivi le chemin de fermeture normale du journal. Les six fichiers ne contiennent ni motif de terminaison iOS associé à ce PID, ni signal fatal ou appel explicite à `exit` enregistré pour lui. La phrase « ended from outside (iOS) » de la 777 était déduite par le pont de l’absence de ces deux traces. Elle n’est pas un verdict du système.

| Heure de Paris | Événement établi |
|---|---|
| 21 h 57 min 46 à 49 s | Le pont enregistre le core `7ad86a14377d`, le titre `0100f7e00c70e000`, le mapping de 4 Gio et l’attachement de la vue au premier plan. |
| 21 h 57 min 51 à 56 s | Un worker attend 1 450 ms le cache Vulkan de 98,47 Mio chargé en arrière-plan. Le compactage du premier affichage dure 81,9 ms et ramène l’empreinte de 2 851 à 2 595 Mio. |
| 21 h 58 min 33 à 36 s | Première alerte iOS. Empreinte de 4 254 Mio, marge du processus de 2 401 Mio, indicateur appareil de 7 %. Une Gen0 dure 386,2 ms et promeut 43,9 Mio. Le relevé détaillé de l’hôte parcourt 165 442 régions en 1 510,7 ms et s’arrête incomplet. Il travaille sur une file utilitaire. Ce coût ne mesure pas une suspension du thread principal. |
| 21 h 58 min 49 s | Autre Gen0 de 253,6 ms, avec 3,8 Mio promus. |
| 21 h 59 min 20 à 23 s | Dernier relevé par seconde. Le moteur signale 18,1 FPS. L’alerte suivante relève 4 892 Mio d’empreinte, 1 763 Mio de marge du processus et 4 % pour l’appareil. |
| 21 h 59 min 38 à 40 s | Troisième alerte, 4 871 Mio et 4 %. La lecture des compteurs audio dure 1 017,2 ms. À 337 ms, les piles du thread GPU principal et du worker audio passent par `RhpWaitForGC2`. Le premier passe aussi par `RhpGcPollRare`. Le moteur enregistre encore du travail de rendu à 21 h 59 min 40,625 s. |
| 22 h 10 min 53 s | Le journal de crash est armé pour le nouveau PID 41395 et rapporte le marqueur Hogwarts du PID précédent. L’heure exacte de disparition du PID 40796 se situe après sa dernière activité observée et avant ce constat. |

L’attente du GC est identifiée à un instant de l’incident avec la carte de symboles ARM64 du binaire livré, SHA-256 `939a939ff1653f0c13788e8658c61a83d2ac8a4fe1ac0074a8051950800bb072`. Les journaux ne permettent pas d’attribuer les 1 017 ms entières à une collecte particulière ni de mesurer un silence audio de cette durée. Le dernier intervalle audio publié rapporte sept épisodes de manque de données, 18,5 ms au total, 6,5 ms au maximum. Une Gen2 `background` est une collecte concurrente du runtime.

La pression mémoire rend un Jetsam plausible. Un watchdog, un crash sans rapport capturé et une autre fin de processus restent possibles. Aucune transition UIKit en arrière-plan, exception fatale, perte de périphérique Vulkan ou révocation du donor n’est enregistrée dans cette fenêtre. Les rapports MetricKit de 17 h 49 et 19 h 58, heure de Paris, sont antérieurs. La preuve déterminante manquante est le rapport système correspondant à Runner et à l’heure de l’incident. Aucun rapport correspondant n’était disponible avec les fichiers fournis.

## Sessions et provenance

Le core du build 775 a pour source `9546deb792b6e24ed29c7667abed435a82ab01f2` et l’IPA pour déclencheur `7c22aebf`. Le core du build 777 a pour source `7ad86a14377da6ce1f8ce51bfec2f3bc9cc16183` et l’IPA pour déclencheur `16653b42`. L’amont MeloNX reste `13700519f3ab`. Le delta mémoire livré en 777 comporte la garde de marge de 256 Mio avant un compactage de trou de présentation, les pages d’alias de textures à la demande, la suppression d’une copie des changements de liaisons et le plus petit buffer adéquat du pool de streaming. La comparaison de ces sources ne montre pas de nouvelle politique propre à Hogwarts, de changement de cache de pipelines ou de destruction des ressources du cycle UIKit. Le compactage de 1 914,8 ms du build 775 ne figure pas dans cette session 777.

Les historiques de performance et du moteur conservent des parties des builds 767, 771, 773 et 775. Sur la 777, les PID 41408, 41546 et 41724 concernent Super Smash Bros. Ultimate. La session de 656 s du PID 41408 passe en arrière-plan sans avertissement mémoire. Le JSON de session ouvert concerne le PID 41724, en arrière-plan à 75 s. Le fichier stderr fourni commence avec Smash et ne conserve aucune ligne Runner du PID 40796. Le signal 6 du PID 33274 appartient à une session antérieure. Aucun des trois journaux de Smash ne permet d’établir une cause commune de fermeture. Les six fichiers ne contiennent pas d’événement textuel horodaté attribuant au PID 40796 une purge explicitement classée critique. La politique du core autorise bien ce traitement sous ses conditions.

## Où se trouve la mémoire

À 21 h 59 min 27,893 s, l’inventaire du PID donne 4,69 Gio de `phys_footprint`, 1,81 Gio de marge du processus et 4 % pour l’appareil. Le maximum directement lisible aux alertes est d’au moins 4 892 Mio, soit 4,78 Gio. Il ne s’agit pas d’une mesure continue du pic.

- Le tas managé compte environ 731 Mio utilisés lors du relevé. Le dernier GC avait 859 Mio engagés. Son LOH faisait 502,3 Mio dont 207,8 Mio libres. Occupation, engagement et fragmentation décrivent des aspects différents du même tas.
- À 21 h 59 min 00 s, 1 498 buffers retiennent 48,0 Mio de copies managées. Parmi eux, 62 gros tableaux représentent 36,1 Mio. Cette part est identifiée dans le tas. Le reste du LOH n’est pas attribuable objet par objet avec ces journaux.
- À 21 h 59 min 35 s, Vulkan décrit 13 453 blocs pour 688 Mio, dont 227 Mio mappés, et 9 186 blocs d’images pour 461 Mio. Les caches logiques de textures et de buffers de l’inventaire précédent représentent respectivement 104,4 et 123,8 Mio. Additionner ces chiffres à l’empreinte ou aux compteurs graphiques iOS compterait des pages plusieurs fois.
- Les deux donors offrent un mapping invité de 4 Gio. L’arène JIT préparée offre 1 Gio d’adresses. Aucun des deux chiffres ne mesure les pages résidentes facturées à Runner. Les compteurs de compression et les adresses virtuelles ne donnent pas le volume exact de données utiles du jeu. Les échantillons ne ventilent pas l’ensemble des pages par propriétaire.
- Le nettoyage des buffers froids rapporte 61 buffers retirés en cinq passages et moins de 1 Mio cumulé à la précision de son affichage. Il protège les ressources récemment utilisées. Ce résultat ne justifie pas une purge plus agressive, un préchargement ou une réduction de résolution.
- Le dernier intervalle mémoire échantillonné rapporte 94 010 décompressions de pages, 158 732 défauts de page, 1 695 entrées de pages et une hausse de 1 685 Mio du compteur de compression. Ce sont des événements cumulés sur l’intervalle. Ils signalent du renouvellement de pages sans localiser l’objet responsable.
- Le profil natif échantillonné à 45 s estime 439 Mio vivants. La symbolication de ses piles désigne notamment la compilation de bibliothèques Metal (environ 127 Mio), la création de pipelines de rendu (36 Mio) et deux sites de création de pools de descripteurs (32 et 7 Mio). Il s’agit d’estimations d’allocation côté pilote déjà susceptibles d’être comptabilisées dans l’empreinte. Elles ne mesurent ni des fuites ni le temps d’attente d’un dessin.

## Corrections apportées

| Fichier préparé ou fichier du pont | Modification |
|---|---|
| `BufferHolder.cs`, `PendingWriteSpan`, `FillMirror`, `UploadPendingData`, `SetData` et `Dispose` | Une petite écriture différée sur un buffer d’au moins 85 000 octets conserve une fenêtre de 16 Kio. Elle peut se déplacer lorsque toutes les écritures précédentes sont consommées. Si des écritures simultanées ne tiennent plus dans cette fenêtre, une promotion unique conserve des octets contigus. Le nombre de transferts d’une plage vers le GPU reste identique. Le compteur existant comptabilise la capacité effectivement retenue. |
| `BufferHolder.cs` et `PipelineFull.cs` | Une écriture passant par le chemin de transfert invalide également les miroirs de staging qui la recouvrent. Auparavant, une liaison partiellement réécrite pouvait conserver un ancien instantané tant que d’autres octets restaient en attente. L’invalidation n’alloue plus de liste de clés. Un buffer ne figure qu’une fois dans les miroirs à retirer au prochain changement de command buffer. |
| `BitMapStruct.cs`, `DescriptorSetUpdater.Rebind`, `ShaderCollection` et `DescriptorSetUpdater.SetProgram` | Le parcours des liaisons uniform/storage utilise un état transmis par valeur et deux callbacks statiques. Le test de recouvrement, les invalidations push-descriptor et les marquages texture/image sont conservés. La classification des vues de buffers est calculée à la construction du programme et réutilisée lorsque le même programme est lié de nouveau. |
| `DescriptorSetManager.cs`, `TryAllocateDescriptorSets`, `CanFit`, `FreeDescriptorSets` et `Dispose` | En cas de refus Vulkan, la nouvelle tentative pouvait détruire deux fois le pool vide. La fermeture pouvait aussi détruire un pool dont des jeux de descripteurs étaient encore en vol. Le gestionnaire rend sa référence une seule fois et le dernier utilisateur libère le pool. La création d’un nouveau jeu de descripteurs et la fermeture sont sérialisées. Les liaisons en cache et les libérations différées conservent leur chemin habituel. |
| `EmbeddedSessionCoordinator.Pause` | Une deuxième demande portant le même état effectif ne relance ni le checkpoint de cache ni le délai du compactage de pause. La première pause demandée pendant le démarrage est rejouée à l’installation des contrôles. L’arrêt et la génération continuent de primer. |
| `MeloNXPerfJournal.swift`, `MeloNXMemoryBreakdown` | Le relevé d’alerte conserve les compteurs du noyau accessibles en une requête. Il évite le parcours de la carte virtuelle pendant 60 s après chaque alerte. Un parcours déjà en cours vérifie la pression toutes les 256 régions. |
| `MeloNXStandaloneParity.swift`, `MeloNXSessionExit` | Les écritures, notifications et suppressions du marqueur sont rattachées au propriétaire de la session. Un ancien journal ne peut plus effacer le marqueur de la nouvelle partie. Un rapport relu dans le processus courant est préservé. La cause est consignée comme inconnue quand aucun signal ou appel à exit n’a été capturé. |

L’adaptation des cinq sources Vulkan se trouve dans `build-utils/melonx/adapt_buffer_mirror_windows.py`, que la préparation applique sur les empreintes du core livré. Le contrat inclut également les fichiers Nextendo déjà présents sur Claude avant cette intervention. Le format des données persistantes et le cache Vulkan restent compatibles.

Le correctif distinct des pools se trouve dans `build-utils/melonx/adapt_descriptor_pool_lifetime.py`. Sur le gestionnaire de la 777, la reproduction contrôlée compte deux destructions pour le même handle après un refus et une destruction prématurée à la fermeture. Sur le candidat, elle en compte une et zéro respectivement, et le dernier jeu libéré détruit bien le pool. Cent essais concurrents de fermeture avec 40 jeux répartis sur cinq pools valident cette propriété. Le pilote de ce test est simulé. Les six journaux ne montrent pas ce refus Vulkan pour le PID 40796.

## Résultats et limites

Même temps écoulé, de 46 à 80 s inclus, sur les deux captures iPhone. Les déplacements et l’état des caches n’ont pas été contrôlés. Les percentiles sont calculés sur les intervalles de présentation arrondis du journal. Les seuils de saccades utilisent une inégalité stricte. Les 1 % et 0,1 % low de présentation sont l’inverse de la moyenne des intervalles les plus longs, arrondi au nombre entier supérieur d’intervalles.

| Mesure observée | Build 775 | Build 777 |
|---|---:|---:|
| Médiane des FPS du moteur, relevés valides | 27,9 sur 18 relevés | 23,9 sur 29 relevés |
| Intervalles de présentation consignés | 706 | 806 |
| FPS de présentation sur les intervalles | 20,02 | 23,58 |
| Frametime de présentation P95 / P99 | 67 / 167 ms | 67 / 133 ms |
| Saccades de présentation > 50 / 100 / 250 ms | 82 / 13 / 4 | 98 / 13 / 2 |
| Pire intervalle de présentation | 3 984 ms | 1 383 ms |
| 1 % low / 0,1 % low de présentation | 1,05 / 0,25 FPS | 3,29 / 0,72 FPS |
| Allocations managées approximatives, fenêtres du core finissant pendant ce segment | 35,27 Mio/s | 38,17 Mio/s |

Les gains des sources préparées ci-dessus restent à mesurer sur iPhone. À titre de comparaison, durant les 45 premières secondes, les compteurs donnaient environ 281 et 282 Mio/s sur les deux builds. La 777 finit sa dernière fenêtre avec 58 présentations en 5,026 s, 90 696 préparations de dessins, 896,9 ms de descripteurs graphiques, 298,0 ms de descripteurs compute et zéro dessin attendant une compilation de pipeline. Les soumissions occupent 483,5 ms et le GPU est occupé à 26 % sur le relevé associé. Les durées de sous-étapes se recouvrent. La source de la charge comporte donc aussi du travail CPU de préparation et de soumission Vulkan.

Vérifications effectuées sur Linux x64 avec .NET 10.0.100, en Release. Les assemblages Vulkan et Ryujinx.Library ont compilé. La sonde différentielle compare les méthodes préparées de la 777 et du candidat. Avec la compilation à paliers désactivée pour les deux variantes, 100 000 `Rebind` allouent 16 800 000 octets avant et zéro après, après échauffement. Une écriture mobile de 128 octets dans un buffer de 1 Mio garde 1 048 576 octets avant et 16 384 après. Deux écritures éloignées qui doivent rester simultanément valides font remonter ce cas à 1 Mio. Ces chiffres concernent le stockage managé de ce buffer et cette méthode.

Le test vérifie 18 000 comparaisons de miroirs avec un modèle octet par octet, 524 288 comparaisons d’état de liaisons, les masques de vues de buffers et l’invalidation partielle de staging. Les 25 cas existants du cycle du core passent. Le marqueur Swift compilé a subi 100 recouvrements de sessions avec des mises à jour concurrentes, plus deux cas d’issue antérieure. Le contrôle du pont compte 67 vérifications sur l’hôte. Les 102 vérifications de la fixture Nextendo passent sur la composition conservée. Le diagnostic détaillé Mach, l’affichage et les textures exigent une validation sous iOS.

Un deuxième essai hôte fait tourner les mêmes méthodes de miroirs pendant 120 secondes, sur deux processus .NET 10, avec 7 200 itérations cadencées et 64 buffers de 1 Mio. Chaque itération modifie quatre buffers, dont un quart demandent deux écritures espacées, et le test remplace un buffer toutes les 120 itérations. À 30, 60, 90 et 120 s, la capacité managée des miroirs est de 64 Mio sur la 777 et 16,75 Mio sur le candidat. À la fin, le compteur d’allocation du processus de test passe de 129 161 784 à 33 651 744 octets. Les deux processus exécutent la même instrumentation. Le rythme imposé est indépendant des FPS d’un jeu.

La préparation commune conserve aussi les changements de métadonnées de cheats et de fréquence d’émulation arrivés sur `Claude` durant la compilation. Ils ne participent pas aux résultats ci-dessus.

Par ordre d’impact, il reste à attribuer l’arrêt avec le rapport système du 17 novembre, à éprouver le candidat sur une longue exploration du même trajet et à mesurer le coût des descripteurs, soumissions et créations de buffers qui subsiste. Une comparaison exploitable utilisera la même sauvegarde, la même résolution, la même version du jeu et le même état initial du cache, avec un relevé séparé du lancement et au moins 20 minutes de jardin et de transitions intérieur/extérieur. Les FPS 1 % et 0,1 % du jeu exigent les durées individuelles de ses images. Les relevés de FPS agrégés du moteur ne permettent pas de les reconstruire.
