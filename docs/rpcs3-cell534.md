# RPCS3 iOS — pauses, ISO et instrumentation, candidat 534

Le correctif répare un montage ISO erroné lors d'une restauration, supprime les `fsync` par chunk du stockage NeoSwap **temporaire propre au processus**, et mesure enfin le chemin synchrone des shaders. Les caches persistants conservent leur politique de synchronisation. Aucun gain de FPS sur iPhone n'est annoncé sans essai comparable.

Base : `Claude`, `a1c7ab9bebf763b034c522363c29ce6dee6c4594` (assemblage 533). Cœur corrigé : `2fa4ad668446b9166017b434e302836287d015b0`. Les sources/configurations MeloNX 533 et celles des autres émulateurs restent identiques. Pas de modification des sauvegardes originales, des barrières mémoire invitées, du mode shader choisi ni des identités de cache PPU/SPU.

## Périmètre réel des pièces jointes

Les fichiers effectivement disponibles sont `RPCS3-diagnostic(5).log`, `RPCS3-milestones(5).log`, `NeoSwap-operations(3).jsonl`, `app(7).log`. Les deux fichiers RPCS3 portent **build 530, PID 28367**, et non le build 527 annoncé dans la demande. Le diagnostic couvre le 25 octobre 2026, **09:26:18,893–09:27:33,921 UTC** ; les milestones conservés couvrent seulement les **168 dernières millisecondes** de la restauration. Les anciennes durées de boot et les `FREEZE_DUMP` cités ne sont pas présents dans ces deux fichiers ni dans `app(7).log`. Ils restent des observations rapportées, pas des événements que cette nouvelle capture permet de recaler.

NeoSwap conserve 25 couples processus/session. L'analyse déduplique par `(pid, session, sequence)`, contrôle les doublons contradictoires et les trous, et ne somme jamais plusieurs compteurs cumulatifs de pertes. Le script `build-utils/analyze_rpcs3_cell534_logs.py` et `docs/evidence/rpcs3-cell534-observed.json` rendent l'extraction reproductible ; les journaux bruts et les chemins privés iOS ne sont pas publiés.

Les numéros de session sont propres à chaque composant : le PID 28367 a la session de performance RPCS3 **1** et la session NeoSwap **2**. Le rapprochement utilise le processus, les périodes et les ancres, jamais une égalité supposée des numéros de session.

| PID / session NeoSwap | Événements conservés | Pertes déclarées | Observation distincte |
|---|---:|---:|---|
| 25548 / 2 | 2 513 | 448 | Restauration vidéo maximale 2 037 158 µs ; chunk maximal 991 451 µs ; warning puis critical |
| 25865 / 2 | 673 | 175 | Ancienne activité GLSL ; historique incomplet |
| 25906 / 2 | 743 | 0 | 367 refus GLSL ; checkpoint maximal 115 530 µs ; aucune restauration GLSL conservée |
| 26794 / 2 | 3 309 | 0 | Autre session : 109 restaurations vidéo, maximum 13 158 µs ; trois changements de pression |
| 28367 / 2 | 599 | 0 | 106 admissions vidéo, 270 checkpoints ; aucune restauration de chunks ; 2 lectures RAM |

Les anciennes sessions 25548/25865/25906 n'ont pas d'ancre Unix/monotone native. L'heure d'export du lot ne constitue pas l'heure de ses opérations. Les sessions 26794 et 28367 ont respectivement 54 et 14 ancres conservées. Pour 28367, l'étendue observée des décalages Unix–monotone est de 1 214 µs ; elle inclut la dérive observée, sans garantir l'absence de saut d'horloge non observé. Les traces RPCS3 récentes encadrent également leur capture par deux lectures monotones. On peut rapprocher ces événements récents, pas transposer automatiquement leurs heures aux anciens processus.

## NeoSwap : dépendance réelle et politique

Le chemin de lecture est `cellVdecGetPicture` → `ColdFrame::restore` → API hôte `sourceRead` → lecture immédiate du staging si disponible, sinon `dispatch_sync` vers la file utilitaire → `SourceArchive::read` → `Manager::read_chunk` → `Store::request`/attente du worker, lecture, décompression éventuelle, CRC et copie. Une demande qui arrive sans préchargement prêt bloque donc le PPU appelant avant la remise des pixels à l'invité. Un préchargement peut aussi faire attendre le décodeur, ou le consommateur si le chargement est encore en cours. Cela peut retarder une cinématique ou une dépendance du jeu ; ce n'est pas une mesure directe d'attente du thread de présentation.

Le chronomètre `restored_from_managed_chunks` commence **dans** `Archive::read` : il ne contient pas l'attente préalable dans la file utilitaire hôte. Ses enfants peuvent inclure attente du manager/worker, I/O, décompression et vérification, sans les séparer. Les compteurs hôtes existants `demandUtilityQueueWaitUsCumulative/MaxUs` et `demandReadUsCumulative/MaxUs` distinguent cette attente préalable du travail de lecture. La suppression du `fsync` vise les évictions et la contention qu'elles peuvent créer ; elle ne démontre pas que le `fsync` explique les 2,04 s du parent de lecture ancien.

Dans 25548/2, objet 105, les séquences 1818–1828 sont les enfants de la séquence 1829. Le parent commence à `464391610285` µs et dure 2 037 158 µs. Les deux premiers enfants durent 991 451 et 901 529 µs : **ils sont inclus dans le parent**. Warning/critical précèdent le début du parent d'environ 31 s. L'objet avait été admis environ 77,17 s avant la lecture et entièrement évincé à `464314526623` µs, soit **77,08 s avant la lecture et 46,05 s avant warning**. Ces transitions de pression ne peuvent donc expliquer le déclenchement de cette éviction déjà terminée. Ce cas ne montre pas une réutilisation après quelques millisecondes ; conserver toutes les images pendant 77 s serait une politique mémoire disproportionnée. Aucun même objet n'est restauré plusieurs fois dans les événements conservés ; les 448 pertes interdisent de conclure à l'absence générale de cycles. On ne peut attribuer ce parent à un `FREEZE_DUMP` de 4–6,8 s sans ancre commune.

Le code déjà livré depuis 528 protège les huit prochaines et huit dernières images de la file, refuse le refroidissement des buffers encore référencés, attend 250 ms et une file d'au moins 24 images. Le préchargement existant est limité à **8 MiB / huit objets**, hors verrou de file et de conversion. Il est préférable à une réserve supplémentaire non mesurée. La granularité déjà passée à 256 KiB ramène une image de 691 200 octets de onze à trois chunks. Ces mécanismes sont conservés.

Dans 28367/2, le plus long checkpoint, objet 57/chunk 1, s'étend de `504430701070` à `504431558976` µs (857,906 ms). Le suivant dure 369,600 ms. Le premier chevauche les fenêtres RPCS3 43 et 44 ; tous deux finissent dans la fenêtre 44. Ils écrivent sur la file utilitaire. Le compteur VDEC conserve un seul préchargement réussi de 232 µs, zéro demande synchrone et zéro attente du consommateur sur l'extrait. **Aucun blocage vidéo direct n'est démontré pour cette dégradation.** Une concurrence d'I/O ou de mémoire reste plausible.

Le checkpoint fait une copie bornée, publie le blob, attend le worker, élimine le cache RAM du Store, relit, vérifie le CRC et compare les octets avant l'éviction. Il retenait auparavant la file utilitaire et un verrou du manager pendant un `fsync` par chunk. Le fichier appartient à une session et n'est jamais réutilisable après la mort du processus : exiger sa durabilité sur le support à chaque chunk ne sert pas sa durée de vie.

534 ajoute `Config::sync_writes`, **vrai par défaut**, et le désactive seulement dans `SourceArchive::Config`. L'écriture complète, les erreurs POSIX, la relecture vérifiée, la comparaison et la conservation du staging en cas d'échec restent en place. La vérification prouve la restitution par le système de fichiers, pas la résistance du fichier temporaire à une coupure électrique. Aucune politique de sauvegarde invité ou de cache persistant n'est modifiée.

Les limites ne croissent pas : enveloppe gérée 8 MiB, staging d'admission 4 MiB, fichier/logique 128 MiB, débit 16 MiB/s. Le Store de 1 MiB et la réserve codec/worker sont **inclus dans l'enveloppe gérée**, pas à ajouter une seconde fois. Le préchargement 8 MiB reste distinct. Les pages sales du cache système peuvent séjourner plus longtemps sans `fsync` ; leur effet physique sur iOS doit être mesuré. Les nouveaux champs `sourceDeviceSyncCalls/Us/MaxUs/Skipped` rendent vérifiable la politique appliquée.

## Shaders et couches de configuration

`legacy_custom=1`, `database=0`, `sparse_overrides=0`, `shader_mode=Legacy Recompiler (single-threaded)` décrivent une ancienne configuration complète, qui fait autorité. `async_tex=false` concerne les textures et ne prouve rien sur le mode de compilation shader. L'ordre est configuration globale, profil GameDB si applicable, puis réglages individuels clairsemés ; un ancien fichier complet supprime GameDB et ces derniers. La découverte de bibliothèque peut tenter une publication avant l'initialisation, d'où les **527 messages historiques** de `app(7).log`. `_ensureRuntime` initialise le cœur puis appelle `publishDetectedProfilesForReadyRuntime` avant l'état prêt. La présence d'avertissements anciens ne démontre donc pas que le profil a été perdu au lancement observé.

Les modes réellement présents sont Legacy (0), Async Recompiler (1), Async avec interpréteur (2), interpréteur (3). La compatibilité Vulkan de l'interpréteur dépend notamment du support des 64 samplers ; le cœur peut rabattre 2/3 sur Legacy. `SHADERCFG528` décrit le mode configuré et appliqué, mais son émission initiale n'est pas conservée dans cet extrait. On ne remplace pas silencieusement le choix Legacy par un autre mode : évaluer explicitement 1 sur la même scène, en vérifiant les objets manquants, le rendu et les pauses.

Le total des 367 refus GLSL de 25906/2 est **80 µs**, maximum **2 µs** ; ce ne sont pas 367 pauses disque. Les 94 snapshots acceptés représentent environ 2,31 Mo et leurs checkpoints totalisent 598,544 ms, maximum 115,530 ms. Les 461 tentatives portaient sur des textes inférieurs à 64 KiB. Depuis 528, ces petits textes restent dans leur objet shader existant et n'entrent plus dans l'archive. Pas de nouvelle réserve ni recompilation causée par ce choix. La dernière session NeoSwap ne conserve plus d'opération GLSL, mais elle n'est pas une scène de comparaison contrôlée.

Les 367 refus se concentrent dans **322 197 µs**, une rafale d'environ 1 139/s sur cette seule période. Le refus d'admission précède les I/O et peut refléter la limite de travaux en attente, pas l'épuisement de la RAM physique. Leur `object=0` ne permet pas de les attribuer à un même shader ; le code appelle l'admission une fois après la création du module, sans boucle de réessai à cet endroit. Les 80 µs chronométrés ne comprennent pas tout le coût du caller et ne constituent pas une mesure de compilation.

Les anciens compteurs `pipeline_queue` et `pipeline_build_callback` concernent le worker **asynchrone**. Leur valeur zéro n'exclut pas une compilation synchrone. 534 ajoute cinq compteurs fixes (120 octets) aux véritables appels : GLSL→SPIR-V, création du module Vulkan, création du pipeline graphique, compute, et recompilation pour export/debug. `COREPROF SHADERCOST534` fournit nombre, durée totale et maximum toutes les cinq secondes. Pas de log/allocation par compilation. Les événements à cheval sur une vidange peuvent être répartis entre fenêtres ; les totaux se conservent après vidanges terminées. Les durées peuvent recouvrir le callback asynchrone : ne pas les sommer comme des pauses distinctes.

## Pauses et dépendances PPU/SPU/RSX

Les attentes normales `MFC_Events_read` se terminent quand l'événement MFC attendu apparaît ; SPURS peut attendre du travail ou une dépendance publiée par le PPU. Le PPU peut attendre une réservation protégée par un writer SPU ; RSX peut attendre des commandes/sémaphores invités, un shader ou le GPU. Un instantané ne dit pas lequel de ces producteurs ne progresse plus.

Dans les fenêtres 41–52 de 28367, des images continuent d'arriver. La fenêtre 44 compte 14 891 épisodes de verrou de plages (6 107,640 ms cumulées entre threads, maximum 20,032 ms), et la fenêtre 50 5 134 épisodes (7 162,079 ms, maximum 21,798 ms). Ces sommes multi-thread ne sont pas des durées murales. La compilation SPU consulte très majoritairement ses objets en cache ; la fenêtre 41 compte 181 hits/181 tentatives, la 42 480 hits/482. La fenêtre 50 n'a aucune compilation JIT recensée. Cela oriente vers la charge et les réservations SPU, la mémoire et les shaders synchrones encore non mesurés ; cela ne prouve pas un interblocage.

`vm::_register_lock`, les writers de réservation et leur `notify_all` ont été examinés. Aucun réveil perdu n'est démontré. Les conditions atomiques, barrières et événements invités sont conservés ; aucun raccourcissement arbitraire de timeout ni suppression de synchronisation n'est livré.

## JIT et ARM64/NEON

Les 136 modules/327 s et 40 modules en cache/0,6–0,7 s cités couvrent des ensembles différents et ne figurent pas dans les nouvelles captures : aucun ratio d'accélération n'en est calculé. Le cold boot compile les modules sans objet compatible (identité source/CPU/options/codegen), tandis que les hits chargent et relocalisent les objets. Une petite durée sur 40 hits ne prouve pas la couverture des 136 modules. Il faut comparer les listes et identités de cache de deux boots complets.

La publication incrémentale du JIT est déjà présente depuis 527. `history_ranges` mesure l'historique évité, `dirty_ranges` le travail publié. Dans la fenêtre 41 récente, 181 plages sales et 315 928 octets sont publiés en **0,532 ms au total**, maximum 0,039 ms. Ce n'est pas un parcours de tout l'historique à chaque publication. `ppu_pipeline=0` signifie la variante **upstream**, sans passe IR PPU supplémentaire sur ARM64 ; cela ne signifie pas absence de sélection d'instructions native ou de lowering NEON. Les conversions/permutations natives déjà validées restent présentes.

Aucune transformation entière ou flottante supplémentaire n'est justifiée par ces traces sans profil d'instructions fréquent. Les identités **PPU `a987639e9f838d1c` / SPU `e1335a5d6dcd86be`** sont conservées et vérifiées lors du build, pour ne pas imposer une recompilation froide sans changement de sémantique. Les résultats antérieurs sont réutilisés uniquement pour leurs entrées restées identiques ; les chemins modifiés ont des exécutions actuelles.

## Save state : cause précise

`0x80010006` est `CELL_ENOENT`. La capture récente identifie le descripteur **5**, fichier indispensable **`/dev_bdvd/PS3_GAME/USRDIR/GAME.PSARC`**, et donne le chemin réel fautif : **`…/BCES00510/disc.isoPS3_GAME/USRDIR/GAME.PSARC`**. Le chemin de restauration résout le numéro de disque vers l'ISO dans le conteneur iOS courant, appelle `load_iso`, puis conservait le **nom du fichier ISO** dans `disc`. Le montage final traitait cette variable comme un répertoire et concaténait directement `PS3_GAME`, sans séparateur, au fichier ISO. La trace confirme donc le défaut de résolution reproduit par le test ; elle ne démontre pas que le fichier est absent de l'image.

Le correctif normalise `disc` vers la racine du périphérique ISO virtuel lorsqu'un montage d'archive est actif et que `disc` n'est pas vide. `m_path_real`/`disc_info` conservent le vrai fichier hôte. Les boots frais qui gardent `disc` vide suivent encore la validation SFB/titre existante. Les dossiers, PSN et chemins multi-jeux sont couverts par les tests. Le témoin exact 533 reproduit l'échec ; les fragments de production corrigés rouvrent le fichier. Ce test utilise un adaptateur VFS/ISO : il ne prétend pas avoir restauré le jeu réel.

Un véritable fichier manquant, un disque démonté ou un état incompatible ne deviennent pas valides par ce correctif. L'abandon récupérable déjà livré en 528 reste actif : aucune reprise des threads invités ni callbacks FXO partiels ; message avec chemin invité et action de remonter le disque ; état original conservé. Le PID 28367 atteint déjà cet abandon propre, au lieu d'une reprise partielle.

## Mesures disponibles et limites

| PID 28367, fenêtre | Intervalles | Médiane ms | p95 ms | p99 ms | Maximum ms |
|---|---:|---:|---:|---:|---:|
| 39 | 301 | 16,652 | 17,708 | 17,879 | 18,090 |
| 41 | 95 | 58,209 | 96,534 | 102,664 | 102,664 |
| 42 | 70 | 62,106 | 93,730 | 894,928 | 894,928 |
| 44 | 55 | 76,835 | 262,399 | 342,834 | 342,834 |
| 50 | 29 | 138,370 | 402,671 | 571,591 | 571,591 |

Les phases sont `guest_unclassified` : on ne rebaptise pas les fenêtres à 60 FPS « cinématique » ni les lentes « gameplay » sans annotation du testeur. Les 69 échantillons thermiques disponibles indiquent 0, sans mesure de température ni exclusion d'un changement de fréquence. Le pic de footprint échantillonné atteint **5 119 662 360 octets** dans la fenêtre 50 ; le nombre de pages compressées n'est pas à ajouter une seconde fois au footprint. La capture est courte, ne comprend pas tout le boot et ne vaut pas une session prolongée.

Test Linux local, ASan/UBSan, dix images identiques de 691 200 octets, compression et limitation de débit désactivées : 30→0 `fsync`, 6 912 000 octets correctement restitués dans les deux cas, staging et pic de mapping identiques (**692 224 octets** sur cet hôte). Durée totale **91,143→55,106 ms**, dont 38,839 ms de `fsync` dans le témoin. Ordre fixe et cache de fichiers de l'hôte : mécanisme validé, pas estimation de latence NAND iPhone ni de gain FPS. Les contrôles d'écriture partielle, ENOSPC, CRC, troncature, pression, quota, fin de session et préchargement conservent l'original en cas d'échec. Les compteurs de shaders sont vérifiés avec 40 000 événements concurrents et un abandon de portée.

Les métriques internes bornées déjà présentes (`FRAMEPROF527`, `WAITPROF527`, `MEMPROF527`, `JITPUB527`, `VDECIO528`) sont conservées. Le journal indépendant `RPCS3-performance.log` et sa rotation de 2 MiB chacun préservent l'historique utile lorsque la restauration émet des centaines de traces détaillées. Les nouveaux compteurs utilisent ce même chemin. Toute analyse doit conserver les compteurs d'événements perdus et les fichiers tournés.

Le [build natif iPhone 40181634906](https://github.com/TarbleFR/RewindBox/actions/runs/40181634906) a réussi, avec les quatre suites actuelles exécutées sur Mac ARM64. Le même microtest POSIX y mesure **75,331→13,093 ms**, 30→0 synchronisations et **704 512 octets** de pic mappé/staging dans les deux variantes. Les 6 912 000 octets restitués sont identiques. Cette différence dépend du cache de fichiers et de l'ordre fixe ; la baisse totale ne s'attribue pas intégralement aux seuls appels `fsync` mesurés (19,731 ms). Elle n'est ni une distribution de temps d'image ni une preuve de gain sur NAND iPhone. Le reçu détaillé, les empreintes, les limites du test et les résultats actuels sont dans `docs/evidence/rpcs3-cell534-core-ci.json`.

## Validation sur l'iPhone à effectuer

Sur le même iPhone 16 Pro Max et le même disque BCES00510, conserver le build précédent et ses caches avant essai. Garder résolution, limite d'images, SPURS/SPU, audio et shader identiques ; partir d'un état thermique comparable. Tester séparément le lancement normal et la restauration d'une **copie** de l'état d'origine. Un échec de restauration ne doit pas être utilisé pour mesurer le gameplay.

Faire au moins trois passages d'une même scène jouable et trois d'une même cinématique, caches froids dédiés puis chauds. Noter les heures de début/fin et la catégorie. Ne pas effacer les caches ou sauvegardes originaux. Pour l'évaluation shader, changer explicitement Legacy→Async Recompiler (1), vérifier le rendu puis revenir au choix initial ; ne changer aucun autre paramètre pendant ce test.

Comparer histogrammes fusionnés (pas la moyenne des p95), p95/p99, maxima, nombres d'intervalles >50/100/500 ms, temps sans image, coût shader synchrone, appels/attentes VDEC, checkpoints, pics de footprint et pression. Faire ensuite une session de 30 minutes, avec export des journaux de performance courants et tournés, des opérations NeoSwap et du journal applicatif. Une régression mémoire ou de rendu annule le bénéfice apparent de FPS. **Les cases avant/après gameplay, stabilité prolongée et restauration réelle restent non mesurées jusqu'à cet essai.**

## Construction privée

Le build du cœur et ses tests sont liés au même arbre de sources par empreintes et reconstruction du delta canonique. L'ancien cache hôte 523 n'étant plus disponible, le job d'IPA reconstruit l'hôte courant avec Xcode 26.3 ; il réutilise les moteurs tiers épinglés et les validations inchangées. Le contrôle final exige les marqueurs du nouveau cœur et de la politique NeoSwap dans les binaires réellement empaquetés, ainsi que les signatures, exports, versions d'extensions et notices de sources. L'IPA est transportée chiffrée, sans publication de release ni changement de `main`.

La [construction privée 40181996501](https://github.com/TarbleFR/RewindBox/actions/runs/40181996501) a **réussi** depuis `b2598823eb3c3b3752f786730b97f35bb93f1dab`. L'IPA récupérée fait **186 307 806 octets** ; son SHA-256 est `5bb87bcd6e94446b2b68c2524c12b70c2cccd8f9a94cf35df056119030a44650`. Le contrôle local retrouve le cœur compilé, les marqueurs ISO/shader et la politique NeoSwap, vérifie le CRC de l'archive et le build 534 de l'application et des sept extensions. Les 87 signatures ad hoc sont validées par macOS en CI. Le moteur MeloNX 533 provient toujours de `77388b61cbd265559ae79f4748fdf7b12df33928`.

Le reçu `docs/evidence/rpcs3-cell534-delivery-ci.json` conserve la provenance des composants et les résultats du paquet livré. L'installation nécessite la **re-signature SideStore** ; ni installation sur l'appareil ni session de gameplay ne sont déclarées réussies par ces contrôles de construction. Les changements de bilan et d'analyse après cette construction ne modifient pas le code de l'application empaquetée.
