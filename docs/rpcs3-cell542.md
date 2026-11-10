# RPCS3 iOS 542 — réduire les constructions de pipelines redondantes

Candidat issu de `Claude` `ca5c96a021a089f3db698ffb503cea53103c9efe`, après lecture de `rpcs3-cell534.md`, des preuves et du bilan 539/541. Les corrections ISO, NeoSwap sans `fsync`, instrumentation synchrone, publication JIT incrémentale, hachage ordonné et compteurs SPU optimisés existent déjà. Elles ne sont pas présentées comme nouvelles. Le code des autres émulateurs, notamment MeloNX 540, reste inchangé. Aucune release ni modification de `main`.

## Observations sur l'iPhone : build 541, pas résultat du candidat

Les quatre pièces jointes sont identifiées par taille et SHA-256 dans `evidence/rpcs3-cell542-observed.json`. `build-utils/analyze_rpcs3_cell542_logs.py` reconstruit ces résultats. Les logs RPCS3 couvrent uniquement **541 / PID 30336**, de **14:01:18,127 à 14:03:56,555 UTC le 25 octobre 2026**. Ils commencent pendant la restauration, sans historique complet du démarrage. La session 2 reprend correctement, finalisation à 14:01:20,209 ; aucune ressource manquante n'est signalée. Les phases restent `guest_unclassified` : aucune séparation fiable gameplay/cinématique n'est inventée.

| Session 2 conservée | Mesure |
|---|---:|
| Intervalles invités | 2 073 |
| p50, bornes du bin fusionné | 51–51,999 ms |
| p95, bornes du bin fusionné | 67–67,999 ms |
| p99, bornes du bin fusionné | 296–303,999 ms |
| Maximum | 12 110,116 ms |
| >50 / >100 / >500 ms | 1 195 / 29 / 19 |
| Intervalles indisponibles déclarés | 0 |
| Pic footprint échantillonné | 5 652 519 984 octets, 5 390,66 MiB |

Les histogrammes sont fusionnés, pas leurs percentiles. Les fenêtres 2–31, première fenêtre partielle exclue, donnent 2 053 intervalles et les mêmes bins p50/p95/p99. L'autre intervalle extrême est **11 612,746 ms**. Les captures ne donnent ni tous les timestamps de flips ni une chronologie complète des présentations. Le pic compressé n'est pas ajouté au footprint. Les 159 échantillons thermiques sont à 0 ; température et fréquence ne sont pas mesurées. Cette capture de moins de trois minutes n'est pas un essai prolongé.

## Cause documentée des pauses et limites d'attribution

**49 opérations longues de stage 2 totalisent 47 537 612 µs**, maximum **4 042 701 µs**. Leurs bornes ne se recouvrent pas dans ce processus. Le coût total de toutes les constructions graphiques conservées est 48 059 278 µs ; GLSL compte 3 697 969 µs, principalement au démarrage (maximum 38 079 µs). Ces sommes ne sont pas ajoutées aux durées des callbacks ni aux temps sans image.

Le code encadre précisément `vkCreateGraphicsPipelines` dans `glsl::program::link`, à l'intérieur du chemin inline : `VKGSRender::load_program` → recherche de pipeline → `VKTraits::build_pipeline` → `pipe_compiler` → appel Vulkan/MoltenVK. Le mode effectif est **Legacy, configuré/appliqué 0, interpréteur supporté, sans repli**. `CONFIG_LAYERS` n'est pas conservé dans cette capture : l'origine de la valeur ne peut être réaffirmée à partir de ces seuls fichiers. Les paramètres utilisateur ne sont pas changés et aucun dessin n'est supprimé pour éviter une compilation.

Les captures `FREEZE_DUMP` à **14:03:10,144** (7,959 s sans image) et **14:03:46,368** (4,195 s) tombent respectivement à l'intérieur d'appels Vulkan mesurés de **1 356 740** et **4 042 701 µs**. Les horloges natives, shader et NeoSwap utilisent `std::chrono::steady_clock`. L'étendue des offsets Unix–monotone observés vaut 17,808 ms ; les ancres locales sont conservées. La capture du dump et celle du rapport shader ne sont pas l'heure d'écriture du fichier. Les images reprennent après les deux dumps.

Le RSX ne peut pas produire les commandes suivantes pendant ces compilations inline. Les SPURS/PPU attendant du travail, un événement ou une réservation ne prouvent donc pas un interblocage. Les maxima des épisodes de réservation, fence GPU et sémaphore RSX conservés sont respectivement **21,268 / 23,355 / 43,754 ms**, sans coût indépendant de plusieurs secondes démontré. Les sommes entre threads se recouvrent. Aucun changement des barrières mémoire, réservations, réveils ou événements invités n'est justifié par ces dumps.

Le cache JIT fonctionne : 45 modules PPU en cache, zéro compilation, **679,401 ms** à la restauration ; 4 933 hits et 15 misses SPU recensés. Ces nombres ne comparent pas le même ensemble que les anciens 136 modules/327 s. Les identités PPU `a987639e9f838d1c` / SPU `d070cb361bdef607` sont préservées. Aucun nouveau coût n'est ajouté aux chemins SPU.

## NeoSwap et pression mémoire

Le fichier NeoSwap mélange 28 processus historiques. **PID 30336/session 2 ne conserve que trois changements de pression** : critical à **14:02:53,546**, warning à **14:02:54,818**, normal à **14:03:05,227**, calculés depuis l'heure monotone de l'événement, pas l'heure d'export du lot. Aucun événement géré perdu ni en attente n'est déclaré dans ces trois lots. La restauration vidéo demandée/préchargée reste à zéro dans `VDECIO528`.

Les anciennes restaurations de 2,04 s du PID 25548 et refus de quota du PID 25906 ne sont pas attribués à 541. Les pertes historiques sont conservées par processus/session dans le rapport. La pression accompagne le début d'une série de compilations lentes ; elle peut renchérir le travail du pilote mais cette trace ne prouve pas le mécanisme interne Metal, une restauration NeoSwap ni des entrées-sorties de shaders. Des appels de plusieurs secondes persistent après le retour à normal. Aucune réserve mémoire ni agressivité d'éviction n'est augmentée. L'effet des anciennes suppressions de `fsync` sur les pages sales de l'iPhone reste non mesuré.

## Nouvelles corrections

1. **Clé de pipeline fondée sur un render pass compatible.** Le cache distinguait `GENERAL` et les dispositions optimales d'attachements, alors que ces différences de layout ne changent pas la compatibilité Vulkan. La copie privée de la clé normalise ces dispositions, conservant présence/nombre des attachements, formats, échantillons, références d'entrée, bits réservés et encodage de feedback. Le render pass réellement utilisé pour dessiner, les transitions d'images et les barrières restent ceux de l'état invité. Le pipeline est créé avec un render pass compatible. Les anciens enregistrements disque restent lisibles et passent par la même validation.
2. **Clé de mélange réduite aux opérations effectives.** Après intersection des sorties définies par le fragment shader et du masque invité, le cache neutralise le mélange des canaux non écrits, celui désactivé par une opération logique, et les facteurs ignorés par MIN/MAX. Les sorties du shader ne sont pas supprimées : une couleur peut toujours dépendre de l'alpha source. Les paramètres actifs, l'ordre des attachements et les masques restent distincts. Le hash ordonné de 539 est conservé, sans retour au XOR.
3. **Identification bornée des compilations lentes.** Les événements existants reçoivent un hash des propriétés, le render pass, les handles des deux modules et les flags de construction. Handles locaux au processus, pas identifiants persistants. Le contexte RAII est posé une fois par construction réelle et restauré après exception/imbriquement ; aucun pointeur de renderer n'est conservé. La capacité reste 32, ajout fixe de 1 280 octets pour les événements, compteurs de pertes conservés, aucune allocation ni log sur le chemin des draws ou des SPU.

Ces défauts de clé sont reproduits dans les tests. **Le log 541 ne contient pas les clés des appels et ne permet pas de compter combien de ses 49 constructions auraient été évitées.** Le gain de gameplay du candidat reste à mesurer. Les nouveaux identifiants servent à établir cette preuve sans transformer les microtests en promesse de FPS.

Références normatives consultées : [compatibilité des render passes](https://docs.vulkan.org/spec/latest/chapters/renderpass.html#renderpass-compatibility), [mélange et masques d'écriture](https://docs.vulkan.org/spec/latest/chapters/framebuffer.html). Les optimisations n'exigent aucune nouvelle extension Vulkan.

## Validation et livraison

Le delta canonique, sa fixture réversible et les tests source-bound sont suivis dans le dépôt. Les tests hôtes exécutent les corps réels de recherche, validation, hash et création des descriptions de render pass, avec adaptateurs de compilation/GPU. Des séquences synthétiques de 32 variantes de layout et trois familles de 16 variantes de mélange passent chacune à **une seule construction**, contre respectivement 32/16/16/16. Ce ne sont pas des replays du jeu. Les descriptions produites par le code réel conservent la compatibilité dans **1 364 cas**. La référence indépendante des équations de mélange couvre **115 520 cas**, avec contrôles de masques, alpha utilisé par RGB, opérations actives distinctes et idempotence. Publication asynchrone mutualisée, exceptions, réutilisation de threads et saturation du recorder sont contrôlées sous ASan/UBSan.

Le contrôle général `neo_swap_core_pin_test.py` échoue déjà sur la base ca5c : ancien pin `cfe92344…` sans `test/rpcs3_restore_eof_test.py`. Le résultat n'est pas présenté comme passant. Le workflow dédié 542 authentifie le cœur 539 réellement livré, ses preuves et les entrées inchangées, exécute les cas modifiés puis reconstruit le cœur iPhone actuel. L'IPA doit être validée sur les empreintes de ce nouveau cœur, pas sur ce pin historique.

La construction native et la livraison privée sont en cours de préparation. Aucun IPA ni test physique du candidat n'est encore déclaré ici. À effectuer : mêmes scènes annotées du build 541, mêmes réglages et état thermique, caches froids dédiés puis chauds, cinématique séparée du gameplay, restauration d'une copie de save state et session de 30 minutes. Comparer p95/p99, pauses >50/100/500 ms, maxima, constructions de pipelines, footprint/pression et rendu. Les sauvegardes et caches originaux sont conservés.
