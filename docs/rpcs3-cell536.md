# RPCS3 iOS — réservations et pauses, build privé 536

Le build privé 536 retire le profilage de la section qui bloque les PPU, prépare le défaut de page du chemin STORE128 actif avant la possession de la réservation, et conserve périodiquement le mode shader réellement appliqué. **Aucun gain de FPS ou de p95/p99 sur iPhone n'est encore mesuré pour ces changements.** Les preuves hôtes portent sur l'ordre des opérations et les cas limites, pas sur le jeu réel.

Base applicative : `35ed01854848d51a0b3f0b0f1c40a29960ad3331`, après les corrections d'import MeloNX 535. Cœur : `d712d5e9cbac256c6677adf7c161ea36b69ba835`. L'assemblage initial `e1110b8ca8390dcdb0ed5d2fe5654615d74435c6` est remplacé pour inclure la conservation des traces détaillée ci-dessous. Les sources des autres émulateurs, les ressources et les dépendances de l'application sont identiques à la base 535. Le seul changement hôte de production est le filtre du journal RPCS3 ; les changements du cœur sont dans le delta canonique reproductible, pas seulement dans un arbre généré. `main`, les tags, les releases et les sauvegardes originales ne sont pas modifiés.

Le [bilan 534](rpcs3-cell534.md) et ses preuves restent la référence historique. Le montage ISO, le retrait des `fsync` des archives temporaires, `SHADERCOST534`, le préchargement vidéo, le filtrage des petits snapshots GLSL, le suivi incrémental JIT et les optimisations NEON déjà livrées **ne sont pas des nouveautés 536**.

## Capture réellement disponible

Les fichiers analysés sont `RPCS3-diagnostic(6).log`, `RPCS3-milestones(6).log`, `NeoSwap-operations(4).jsonl` et `app (1)(1).log`. Le script [analyze_rpcs3_cell536_logs.py](../build-utils/analyze_rpcs3_cell536_logs.py) produit [l'extraction avec empreintes et limites](evidence/rpcs3-cell536-observed.json). Aucun journal brut ni chemin de stockage privé iOS n'est publié.

Les deux journaux RPCS3 portent **build 534, PID 28732**. Les milestones conservés couvrent le 25 octobre 2026, **10:23:11,095–10:23:13,669 UTC** : essentiellement la fin de restauration. Le diagnostic couvre **10:23:37,036–10:24:11,601 UTC**, avec 35 échantillons applicatifs, session de performance 3, époque 2. Les fenêtres 6–11 représentent environ 30,35 s d'intervalles invités. Les fenêtres antérieures, le début complet du chargement et une session prolongée ne sont pas disponibles.

NeoSwap contient **26 couples processus/session**, dont 25 historiques. Pour le PID actuel, la session NeoSwap est **2**, pas 3 : les compteurs de session ne sont pas partagés entre composants. Elle conserve trois changements de pression, deux ancres Unix/monotone, zéro perte déclarée et aucun trou de séquence. Ses événements sont : critical à **10:21:22,814 UTC**, warning environ 64 ms après, puis normal à **10:21:34,046 UTC**. L'étendue des décalages fournis par les ancres est de 65 µs ; ce n'est pas une garantie contre un saut d'horloge non observé.

Le retour à normal précède la première fenêtre d'images conservée d'environ **122,87 s**. Les deux producteurs natifs utilisent `std::chrono::steady_clock` en microsecondes ; les ancres encadrent leur conversion vers l'heure civile. Ces événements ne sont donc pas contemporains de la dégradation tardive. Les anciennes sessions 25548/2 et 25906/2 conservent leurs longues opérations déjà analysées en 534 ; leurs heures d'export ne permettent toujours pas de les attribuer à ce nouveau processus. Les pertes historiques restent dans le rapport, notamment les 448 événements de 25548/2. Elles ne sont ni effacées ni additionnées plusieurs fois à chaque export cumulatif.

## Temps d'image observés, avant 536

Ce sont les intervalles de **flips invités**, pas une mesure indépendante du temps de présentation physique. Toutes les fenêtres sont `guest_unclassified` : aucune n'est arbitrairement appelée « gameplay » ou « cinématique ».

| Fenêtre | Intervalles | p50 ms | p95 ms | p99 ms | Maximum ms | >50 ms | >100 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| 6 | 100 | 48,286 | 60,188 | 66,475 | 202,782 | 38 | 1 |
| 7 | 84 | 53,095 | 90,850 | 218,397 | 218,397 | 57 | 4 |
| 8 | 74 | 62,111 | 108,860 | 224,203 | 224,203 | 70 | 5 |
| 9 | 74 | 66,271 | 87,563 | 104,853 | 104,853 | 70 | 1 |
| 10 | 64 | 76,115 | 101,131 | 120,869 | 120,869 | 64 | 4 |
| 11 | 27 | 179,116 | 343,689 | 459,018 | 459,018 | 27 | 24 |

Au total : **423 intervalles, 326 >50 ms, 39 >100 ms, zéro >500 ms**, aucun intervalle signalé indisponible par le ring dans ces fenêtres. Les histogrammes fusionnés donnent p50 **[59 ; 59,999] ms**, p95 **[152 ; 159,999] ms**, p99 **[240 ; 247,999] ms**. Ce sont des bornes de classes, pas des percentiles exacts recalculables à partir de tous les échantillons bruts. On ne moyenne pas les p95 par fenêtre.

Il n'y a aucun `FREEZE_DUMP` dans cette capture ni échantillon à FPS nul. Cela n'exclut pas une pause avant/après la période retenue, et ne fournit pas une durée continue indépendante `no_frames`. Les anciennes pauses de 4–6,8 s ne sont pas requalifiées à partir de cet extrait.

Le plus haut footprint échantillonné est **5 048 916 848 octets**, à la fin du diagnostic. Le pic conservé par `MEMPROF527` à la fenêtre 11 est de 5 026 978 672 octets. Le niveau thermique disponible vaut **1 sur les 35 échantillons**, contre 0 dans la capture 530 précédente : ni même scène ni mêmes conditions thermiques ne sont démontrées. Aucun compteur de fréquence ou de température réelle n'est fourni. Les tailles VMA demandées, les alias et les pages compressées ne s'ajoutent pas au footprint comme des allocations physiques indépendantes.

## NeoSwap : pas d'activité de restauration actuelle à optimiser à l'aveugle

Le chemin synchrone reste `cellVdecGetPicture` → `ColdFrame::restore` → `sourceRead` → staging ou file utilitaire → `SourceArchive::read` → manager/Store → lecture, éventuelle décompression, vérification et copie. Le PPU consommateur peut attendre cette restitution avant de recevoir ses pixels. Le chronomètre de l'archive n'inclut pas toute l'attente préalable sur la file utilitaire ; un parent et ses chunks se recouvrent.

Dans **28732/2**, aucun événement d'admission, checkpoint, éviction ou restauration gérée n'est conservé. Tous les compteurs `VDECIO528` sont à zéro dans les six fenêtres. On ne peut pas attribuer les pauses actuelles à la restauration de 2,04 s du PID 25548, ni mesurer ici l'effet iPhone du retrait des `fsync` livré en 534.

Les protections des prochaines/dernières images, le préchargement borné à 8 MiB/huit objets, le partage existant de l'état du préchargement, les lectures demandées prioritaires et les checkpoints découpés restent inchangés. Ce partage ne prouve pas que toute demande froide simultanée est dédupliquée ; les traces actuelles ne permettent pas de mesurer ce cas. Aucun nouveau réservoir RAM ni file de travail non bornée n'est ajouté. Les quotas de staging et d'archive sont conservés. La durée des pages sales, le coût mémoire du cache système et les latences d'éviction sous pression **restent à mesurer sur l'iPhone avec une scène qui utilise effectivement la vidéo archivée**. Le microtest POSIX 534 n'est pas rejoué ni présenté comme une mesure gameplay nouvelle.

## Compilation et caches

`SHADERCOST534` sépare déjà la compilation GLSL/SPIR-V, les modules et les pipelines. En fenêtre 7 : 26 compilations source, total **161,690 ms**, maximum **8,776 ms** ; 26 modules, total **1,830 ms** ; 27 pipelines graphiques, total **195,369 ms**, maximum **16,446 ms**. En fenêtre 8 : 12 sources, **86,608 ms**, et 12 pipelines, **103,659 ms**. Ces totaux ne doivent pas être additionnés à ceux d'un callback parent ni être assimilés à une pause unique.

Les fenêtres 9 et 10 ne conservent aucune compilation de ces catégories. La fenêtre 11 ne conserve qu'un pipeline graphique de **5,708 ms**, alors que son p95 atteint 343,689 ms. La compilation n'explique donc pas, à elle seule, cette dégradation. Les compteurs ne contiennent pas les clés de shader nécessaires pour démontrer des recompilations identiques ; aucune politique de cache n'est modifiée sur cette hypothèse.

`CONFIG_LAYERS` et l'émission initiale `SHADERCFG528` ne sont pas retenus dans ces nouveaux fichiers. Le choix Legacy d'un ancien processus ne suffit pas pour établir celui de 28732. Le cœur conserve les modes 0/1/2/3 et le repli local vers Legacy lorsque l'interpréteur n'est pas supporté. Il ne modifie pas les réglages enregistrés.

**Nouveauté 536 : `SHADERCFG536` accompagne les rapports de cinq secondes**, avec configuration demandée, mode appliqué, support de l'interpréteur, repli et génération du renderer. Un état fixe avec propriétaire protège la publication ; une destruction ancienne ne peut effacer une configuration plus récente. Le reporter utilise une tentative de verrou et marque une capture indisponible plutôt que d'attendre. Aucun accès à un renderer détruit, allocation par frame ou changement de choix utilisateur. Les champs `captured` et `live` doivent être vérifiés avant d'interpréter les modes. Le journal de performance indépendant et sa rotation existante conservent cet état après les rafales de traces de restauration.

La vérification de ce filtre a aussi identifié deux catégories omises : `RANGELOCKPROF` et `COREPROF_RESILIENCE`. Elles sont ajoutées à l'historique indépendant existant, sans augmenter ses deux fichiers de 2 MiB. Le test Foundation utilise le vrai logger, émet les deux catégories avant 1 300 traces de restauration puis une erreur de ressource manquante, et vérifie leur conservation et la rotation bornée. Le témoin contre le logger 535 échoue précisément parce que ces deux enregistrements manquent ; le cas corrigé passe. Ce contrôle négatif et le test Foundation ont réussi dans la construction finale 40186697206. Le cœur natif compilé reste identique ; ce correctif concerne seulement l'hôte RPCS3.

Le boot de restauration charge **45 modules PPU en cache, zéro compilé, en 981,064 ms** : lecture 122,233 ms, chargement des objets 241,772 ms, finalisation 424,196 ms au total, dont un maximum de 356,469 ms. Cela confirme des hits sur cet ensemble précis, pas sur les 136 modules de l'ancienne compilation longue. `ppu_pipeline=0` signifie la variante upstream, pas l'absence de génération ARM64. Les publications JIT des fenêtres sont très courtes : maximum de total 0,057 ms, zéro en fenêtre 11. Le suivi incrémental déjà présent est conservé.

## Attentes et corrections de réservation

Les compteurs attribuent plusieurs centaines de milliers de prises de verrou PUTLLC à chaque fenêtre. En fenêtre 11 : **318 304 PUTLLC**, temps cumulé d'acquisition **2 678,095 ms**, maintien mesuré **4,159 ms** ; **83 713 STORE128**, acquisition **976,843 ms**, maintien **0,645 ms**. Les épisodes d'attente de plage totalisent **7 374,796 ms**, maximum **23 ms**. Les sommes sont multi-threads et recouvrent d'autres opérations : elles ne sont pas une pause écran de 7,37 s.

Le mécanisme est PPU en attente d'exclusion de plage → writer SPU qui doit libérer les bits et la plage → réveil PPU. Le writer peut lui-même attendre que les PPU aient reconnu l'exclusion ; les traces ne désignent pas chaque adresse de réservation ni chaque producteur individuel. En début d'extrait, RSX attend aussi des sémaphores invités ; cette attente descend de 1 716,322 ms en fenêtre 6 à zéro en fenêtre 11. Le temps GPU réel est indisponible (`gpu_time_ms=-1`). Une SPU dans `MFC_Events_read` ne prouve toujours pas une perte de réveil. Aucune barrière, réservation, attente GPU ou notification invitée n'est supprimée.

Deux problèmes structurels sont corrigés dans `SPUThread.cpp` :

- Le destructeur `vm::writer_lock` effectuait ses mises à jour de compteurs avant de libérer les bits et de notifier les PPU. Il capture désormais la même borne temporelle, libère selon le protocole existant, puis publie les compteurs. Les deux branches, le test du dernier propriétaire, les ordres atomiques et les notifications restent identiques. Les anciens temps de maintien excluaient déjà le coût du callback de profilage : leur faible valeur ne mesurait pas tout le temps de possession réel.
- STORE128 actif en mode de réservation précis pouvait traiter le défaut de page et un éventuel readback RSX **après** avoir pris la réservation exclusive. Le prétraitement iOS passe avant cette prise, tout en gardant le verrou RSX ; `fetch_op` reste responsable de l'acquisition. Le retour sans écriture, le mode relâché et le chemin initialement en pause restent présents. Si un appel initialement en pause reprend avant la branche finale, il utilise encore le défaut de page historique sous réservation : ce cas résiduel n'est pas annoncé corrigé. Le prétraitement peut aussi être effectué pour une tentative finalement abandonnée ; le bilan de cadence doit donc être vérifié sur appareil.

Les tests exécutent le destructeur et la fonction STORE128 complets, extraits des sources 534 et 536. Un callback de profilage délibérément retardé observe l'exclusion encore tenue en 534 et déjà libérée en 536. Les adaptateurs vérifient les deux modes de libération, un autre propriétaire actif, les notifications, le contenu des 128 octets, l'incrément de réservation, le retour sans écriture, le mode relâché, pause/reprise et un défaut interrompant l'opération. Ce dernier contrôle montre la réservation déjà détenue dans le témoin et non détenue dans le chemin actif corrigé. **Ces frontières CPU/VM/RSX sont contrôlées : aucun vrai readback GPU ou interblocage du jeu n'est prétendu reproduit.**

## Expérience ARM64 : candidats rejetés

Le [probe natif Apple ARM64](evidence/rpcs3-cell536-neon-probe.json), exécuté avec Apple Clang 17/Xcode 16.4, compare le véritable corps 534 à un arbre XOR/OR et à deux accumulateurs. Il vérifie 26 026 cas, dont toutes les positions de bit, puis sept essais en ordre tournant. Médianes, en ns/appel :

| Ensemble chaud | Corps 534 | XOR/OR | Deux accumulateurs |
|---|---:|---:|---:|
| 8 KiB | 2,00383 | 1,91517 | 1,99590 |
| 1 MiB | 5,07256 | 5,57390 | 5,39123 |

L'assembleur a été inspecté : Clang remplace déjà les produits de masques par des opérations entières AND/SUB et une réduction ; le candidat à deux accumulateurs aboutit à une séquence proche. Le XOR utilise moins d'instructions, mais cela ne garantit pas un gain. **Le comparateur existant est conservé** : légère amélioration sur le petit ensemble, régression sur le plus grand. Ce test mesure un composant sur Mac, pas l'A18 Pro ni un taux de FPS. Aucune transformation flottante/endianness/saturation n'est introduite.

La règle de cache conservatrice existante inclut `SPUThread.cpp` : l'identité SPU devient **`d070cb361bdef607`**, donc un premier passage peut recompiler des objets SPU. L'identité PPU **`a987639e9f838d1c`** est conservée. Aucun effacement de cache ou sauvegarde d'un autre émulateur n'est demandé.

## Restauration, validation et essai appareil

La nouvelle capture 534 atteint `finalize_run_begin`, puis `finalize_run_end`, et des images invitées suivent. L'erreur `CELL_ENOENT` sur le montage ISO ne se reproduit pas dans cet extrait. C'est un résultat observé de la correction **534**, pas une nouveauté 536 ni une validation exhaustive de l'état restauré.

Les [tests locaux ASan/UBSan](evidence/rpcs3-cell536-local-tests.json) et les tests actuels sur Mac ARM64 passent. Le [build iPhone 40185694306](https://github.com/TarbleFR/RewindBox/actions/runs/40185694306) est réussi ; son [reçu de provenance](evidence/rpcs3-cell536-core-ci.json) confirme les 88 exports, les identités de cache et les contrôles Mach-O statiques. Le SHA-256 du cœur est `eeca76e114e8c8a6c848ce758f0f02f73237bb52885766292894bb11b010b169`. La configuration est aussi soumise à 10 000 publications concurrentes et à la destruction tardive d'un ancien propriétaire. Le delta s'applique sur un upstream vierge, ses 263 postimages sont vérifiées et le patch inverse retrouve exactement les quatre fichiers 534. Le build iPhone et l'IPA sont contrôlés séparément contre ces empreintes ; les résultats antérieurs restent explicitement historiques pour les entrées inchangées, dont les imports MeloNX 535.

L'[assemblage privé final 40186697206](https://github.com/TarbleFR/RewindBox/actions/runs/40186697206), source **`5fdc4c4feb729918eb1aaa96ac50bce470dc7e6c`**, est réussi. Les [preuves de livraison](evidence/rpcs3-cell536-delivery-ci.json) lient les artefacts chiffrés, l'IPA déchiffrée et les reçus de validation. La signature conserve les sections compilées et les métadonnées ABI contrôlées. Les 87 exécutables Mach-O sont scellés, l'application et ses sept extensions portent le build 536, et aucun identifiant de chiffrement FairPlay non nul n'a été trouvé. Le CRC ZIP, les empreintes des quatre parties, leur assemblage et le contrôle local du cœur RPCS3 passent. Le contrôle complet MeloNX passe en CI sur cette même IPA ; sa répétition locale s'arrête faute de `Memory/adaptation.json`, fichier généré absent de l'environnement local, et n'est pas comptée comme un succès local.

Le fichier privé **`RewindBox-Build536.ipa`** fait **186 318 090 octets** ; SHA-256 : **`a51334d3b990eee0111f48e2ce2627591a08e38057e5fd01c8507ae2fa88b921`**. Il est déchiffré et prêt à être re-signé avec SideStore. Le scellement des exécutables ne remplace pas cette signature Apple personnelle. L'assemblage initial `e1110b8` n'est pas livré. Les commits de bilan postérieurs à `5fdc4c4` ne changent pas les sources embarquées.

Restent non mesurés pour 536 : p95/p99 et pauses après correction, latence physique de présentation, consommation et pages sales iPhone, stabilité 30 minutes, rendu avec les modes shader alternatifs, installation et restauration d'une copie de save state. L'accès au connecteur NeoStation a été refusé par le contrôle automatique en raison de sa synchronisation externe potentielle ; aucun contournement ni essai appareil n'est déclaré.

Protocole proposé : même iPhone, même scène BCES00510, résolution, limite d'images, SPURS/SPU et audio identiques ; niveau thermique de départ comparable. Conserver les originaux. Faire trois passages annotés de gameplay, puis trois d'une cinématique utilisant le décodeur, avec caches froids dédiés puis chauds. Séparer le coût du premier remplissage SPU du régime chaud. Tester ensuite une copie du save state et 30 minutes de jeu. Exporter les fichiers de performance courants et tournés, les milestones, NeoSwap et l'application avec les heures de début/fin. Comparer les histogrammes fusionnés, >50/100/500 ms, maxima, intervalles sans image, footprint, pression et qualité du rendu. Pour comparer Legacy et Async, changer seulement ce réglage explicitement et vérifier les objets manquants avant d'accepter un gain.

La priorité suivante dépend de cet essai : conserver les corrections qui réduisent les queues de distribution sans hausse mémoire ou défaut de rendu, puis profiler le producteur des réservations et les allocations textures si la dégradation persiste. Aucun objectif de 60 FPS n'est annoncé.
