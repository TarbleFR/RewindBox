# RPCS3 iOS 543 — chemin de compilation RSX : audit, publication différée et attribution des coûts Metal

Candidat issu de `Claude` `3494edc9e09fb60fecc35dd6cc301bcb93bc9434` (Build 542), rebasé sans conflit après les commits MeloNX concurrents `eabc057`/`d9f35c2` (aucun fichier commun, manifeste RPCS3 inchangé). Seul le Core RPCS3 change : MeloNX, les autres émulateurs, l'hôte Flutter/iOS, `main`, les caches et les sauvegardes utilisateur ne sont pas modifiés. Aucune release. Le mode de shaders configuré par l'utilisateur n'est pas modifié et aucun draw n'est supprimé.

## 1. Audit du chemin RSX → Metal

### Ce que montrent les journaux disponibles (541, pas 542)

Les preuves 534–541 conservées dans `docs/evidence/` donnent, fenêtre par fenêtre, les compteurs `SHADERCOST534` :

| Session | Préchargement au démarrage | Pipelines construits en jeu |
|---|---|---|
| 538 (PID 29935) | 702 pipelines, 773,6 ms cumulés, max 7,1 ms | 0,3–0,8 s chacun |
| 541 (PID 30336) | 728 pipelines, 516,2 ms cumulés, max 3,3 ms | 0,2–4,0 s chacun (49 > 50 ms, 47,54 s) |

* Le cache disque RPCS3 fonctionne : il passe de 632 (534) à 702, 703 puis 728 enregistrements, et le préchargement complet coûte environ 0,7 ms par pipeline lorsque le cache système Metal est chaud.
* En jeu, la quasi-totalité des constructions coïncide avec une nouvelle compilation GLSL→SPIR-V dans la même fenêtre (53 constructions pour 53 sources dans les fenêtres 2–31 du 541). Ce sont donc surtout des shaders jamais vus, que le préchargement ne pouvait pas connaître. La normalisation de clé 542, ou toute autre, ne peut pas éviter ces compilations. La fenêtre 25 montre aussi une construction de 3,18 s sans nouveau shader (nouvel état pour une paire existante).
* Les gels de 12,1 s et 11,6 s correspondent à des rafales séquentielles de 5 et 16 nouveaux pipelines sur le thread RSX.
* Pendant les fenêtres lentes du 541 (w20–w30), le thread RSX attend (0,01–0,02 cœur), tandis que les threads SPU consomment 3,3–3,7 cœurs en boucles PUTLLC (range-wait 0,9–3,4 s par fenêtre). Le même coût unitaire était de 0,3–0,8 s en 538 avec 2,3–3,9 cœurs SPU. Le passage à 2–4 s commence avec l'événement de pression mémoire critique de 14:02:53. **Ces corrélations ne prouvent pas le mécanisme.** Le 543 ajoute les mesures qui manquaient pour trancher (§3).

### Ce que fait réellement MoltenVK 1.4.2 (source de la version liée, `db66022`)

* `vkCreateGraphicsPipelines` est synchrone. Avec un `VkPipelineCache`, la conversion SPIR-V→MSL et `newLibraryWithSource` s'exécutent **sous un unique mutex du cache** (`MVKPipelineCache::_shaderCacheLock`). La création de `MTLRenderPipelineState` (compilation backend) se fait hors de ce verrou, via une file GCD globale de priorité *default*, pendant que l'appelant attend.
* `vkCreatePipelineCache` recompile immédiatement chaque bibliothèque MSL du fichier (étape « Preparing graphics cache »).
* Aucun support de `MTLBinaryArchive` ni de `VK_EXT_graphics_pipeline_library` : rien n'est activé de ce côté. `VK_EXT_pipeline_creation_cache_control` et `VK_EXT_pipeline_creation_feedback` sont présents pour iOS. Seul le second est activé, pour mesurer.
* Le vertex shader n'est pas recompilé pour chaque nouvel ensemble d'entrées du fragment shader (hors tessellation). Les variantes ne différant que par l'état depth/stencil ne changent pas le descripteur Metal : elles coûtent une recherche dans le cache Metal, pas une compilation.
* Tous les threads RPCS3 iOS sont créés en `QOS_CLASS_USER_INTERACTIVE`. Une requête de compilation propagée depuis le thread RSX plafonne à `USER_INITIATED`. C'est une piste de contention à confirmer avec les nouvelles mesures, pas une conclusion.

### Asynchronisme : pourquoi il n'est pas forcé

Le mode effectif est Legacy (configuré 0, appliqué 0). `async_recompiler` retourne un programme nul tant que le pipeline n'est pas prêt, et le draw est alors sauté. `async_with_interpreter` dessine avec un autre programme, dont l'équivalence n'est pas prouvée. Comme la commande Vulkan exige le `VkPipeline` au moment de l'enregistrement, aucun mécanisme ne permet de poursuivre sans pipeline sans perdre ni réordonner un draw. Le premier usage reste donc bloquant, comme demandé. Le 543 retire du chemin critique ce qui n'est pas nécessaire au draw, et rend sûre toute future construction concurrente.

### Préchauffage

Le préchargement synchrone existant compile déjà **tous** les pipelines observés lors des sessions précédentes, avant le premier draw, pour environ 0,5 s de pilote (541). Un index de priorité ne servirait que si ce préchargement devenait partiel ou asynchrone, ce qui échangerait du temps de démarrage contre un risque de saccade. Ce choix n'est pas retenu sans mesure sur l'appareil.

## 2. Modifications du Core

1. **Publication disque différée** (`rsx_cache.h`, nouveau `Common/deferred_publisher.h`). `store()` exécutait jusqu'à deux `stat` et trois écritures atomiques (`fsync` + `rename` via `fs::pending_file::commit`) sur le thread RSX pour chaque nouveau pipeline. Il copie désormais un enregistrement autonome dans une file bornée (256), écrite dans l'ordre par un thread dédié en QoS *utility*. Si la file est pleine, l'appelant écrit lui-même, comme avant. Aucune perte silencieuse. La file est vidée à `on_exit()` et à la destruction. `fsync` et l'atomicité des fichiers sont inchangés.
2. **Single-flight et reprise après échec** (`ProgramStateCache.h`). Un draw qui demandait une clé en cours de construction inline par un autre thread recevait l'espace réservé nul, et le draw était sauté. Il attend désormais le résultat partagé. Les workers de préchargement, qui n'en ont pas besoin, passent à l'entrée suivante comme avant. Un résultat nul retire l'espace réservé : la clé n'est plus empoisonnée pour le reste de la session. RPCS3 est compilé sans exceptions C++ (`-fno-exceptions`) : une erreur fatale de compilation termine toujours le processus, comme en 542. Le drapeau de miss devient propre à chaque thread : sa course avec les workers de préchargement est supprimée.
3. **Hachage de clé** : calculé une fois après validation et réutilisé par la recherche, l'insertion et la publication. Les identifiants de programme sont mélangés dans l'ordre : avec XOR, 4 096 paires (vp, fp) au même état ne donnaient que 64 valeurs. L'égalité compare toujours tous les champs ; une collision n'est jamais une preuve d'égalité.
4. **Normalisation depth/stencil** (`pipeline_key_normalization.h`), sur la clé privée uniquement. Sans attachement depth/stencil, l'état est ignoré par Vulkan. Sans aspect stencil (D16, D32F), l'état stencil ne s'observe pas. Un test de profondeur désactivé n'effectue ni comparaison ni écriture. L'état invité, les render passes réels et les barrières ne changent pas.
5. **Attribution et cache Vulkan** (`VKProgramPipeline.cpp`, `device.*`, `IOSShaderTiming.h`, `RPCS3IOSPerformance.cpp`). `VK_EXT_pipeline_creation_feedback` est activé s'il est annoncé. Chaque construction lente rapporte désormais : l'origine (nouveau VP/FP ou simple nouvel état), les bits cache-hit MSL par étage, les durées MoltenVK, le CPU consommé par le thread appelant et par le processus pendant l'appel, et le nombre de créations concurrentes. Une table bornée de 64 empreintes détecte les reconstructions redondantes. Le `VkPipelineCache` n'est réécrit (sérialisation, `fsync`, `rename` sur le thread RSX au démarrage et à l'arrêt) que si une bibliothèque a été ajoutée depuis la restauration ou la dernière sauvegarde. Sans feedback, chaque création compte comme ajout et le comportement antérieur est conservé.

Nouvelles lignes : `COREPROF SHADERFEEDBACK543`, `SHADERPUB543` (coût côté RSX, écriture, commit, file, débordements), `SHADERPIPE543` (origines, attentes single-flight, hits/compilations MSL, pipelines vivants, empreintes) et les champs `context543` de `SHADERSTALL538_EVENT`. Elles sont produites une fois par construction ou par fenêtre, jamais par draw ou opération SPU.

Identités de cache JIT préservées : PPU `a987639e9f838d1c`, SPU `d070cb361bdef607`. ABI 30 inchangée.

## 3. Validation

`test/rpcs3_cell543_test.py` assemble les corps de production réels : la recherche et le single-flight, la validation et la normalisation, `store()`, l'écrivain, l'interprétation du feedback et la sauvegarde du cache. Il les compare au corps 542, reconstruit par la fixture inverse et contrôlé par empreintes, sous ASan+UBSan puis TSan (`docs/evidence/rpcs3-cell543-local.json`). Les requêtes sont synthétiques et la latence disque est injectée : ce ne sont pas des mesures iPhone.

| Cas | 542 | 543 |
|---|---:|---:|
| 16 draws simultanés, même clé inline : retours nuls (draws perdus) | 15 | 0 |
| Échec de la 1re construction, 3 demandeurs en attente : retours nuls / clé empoisonnée ensuite | 4 / oui | 1 (l'appelant fautif) / non |
| Résultat inline nul puis nouvelle demande | nul définitif | reconstruit |
| Variantes DS sans attachement depth (119 requêtes) | 119 constructions | 1 |
| Variantes stencil sur D16 (7) / D32F (119) | 7 / 119 | 1 / 17 |
| Variantes réelles D24S8 (7) et D32S8 (17) | 7 / 17 | 7 / 17 (distinctes) |
| Valeurs de hachage distinctes, 64×64 programmes | 64 | 4 096 |
| `store()` côté appelant, fsync réel de l'hôte (48 enreg.), p50 | 1 489 µs | 17 µs |
| `store()` côté appelant, commit +10 ms injecté (24 enreg.), p50 | 34 408 µs | 27 µs |

Autres cas : 13 824 états DS contre une référence littérale de la spécification, sans fusion de comportements distincts, avec idempotence ; les 4 familles 542 restent à une construction ; 115 520 équations de blending ; 300 écritures avec file saturée (280 différées, 20 inline, 0 perte, 0 fichier temporaire ; la répartition dépend de l'ordonnancement) ; 400 écritures concurrentes ; ordre, vidage et échecs d'écriture signalés par l'écrivain (sans exception) ; 34 combinaisons de feedback ; 6 scénarios de sauvegarde (sauté seulement si restauré et inchangé ; ajouts pendant la sauvegarde conservés ; échec conservé) ; saturation et concurrence de la table d'empreintes ; contextes 542 inchangés. Les tests statiques du script de build du Core passent aussi sur l'arbre 543.

Résultat négatif conservé : le premier essai CI du Core (run `40210639364`, commit `aa7ac54`) a échoué au contrôle syntaxique iOS (`VKGSRender.cpp` : « cannot use 'try' with exceptions disabled »). RPCS3 est compilé avec `-fno-exceptions`, alors que le harnais hôte autorisait les exceptions. Les corps de production n'utilisent plus `try`/`catch`/`throw` (l'écrivain signale un échec par un booléen) et le test vérifie désormais cette absence dans les 14 corps de production. Un contrôle `clang++ -fsyntax-only -fno-exceptions -DRPCS3_IOS` de 11 unités du Core qui incluent les en-têtes modifiés passe ; sur l'arbre `aa7ac54`, le même contrôle reproduit l'erreur CI.

Non exécutable ici : le rendu Metal, `RPCS3IOSPerformance.cpp` (en-têtes Apple, compilé par le build iPhone) et deux tests historiques qui exigent des commits absents du clone superficiel (échec identique sur 542). `neo_swap_core_pin_test.py` échoue déjà sur la base (pin `cfe92344…` sans `test/rpcs3_restore_eof_test.py`), sans changement.

## 4. Limites et ce que le 543 ne peut pas promettre

* Les pipelines vraiment nouveaux restent compilés au premier usage sur le thread RSX, avec le coût Metal correspondant. Le 543 ne réduit ni la durée des compilations Metal ni la taille des rafales.
* Le gain de la publication différée sur iPhone dépend du coût réel de `fsync` sous l'activité NeoSwap ; il n'est pas mesuré. Le saut de réécriture du `VkPipelineCache` raccourcit les démarrages et arrêts à cache inchangé, sans chiffre appareil.
* Aucune amélioration FPS, p99 ou de pause n'est revendiquée sans nouveaux journaux iPhone.

## 5. Protocole de mesure demandé (541 / 542 / 543)

Mêmes sauvegardes et scènes de God of War III, mêmes réglages (Legacy), appareil refroidi, NeoSwap identique. À séparer : démarrage à cache froid (copie du dossier `shaders_cache` retirée, originaux conservés), démarrage à cache chaud, restauration de sauvegarde, cinématique, gameplay intensif, session de 30 minutes. Comparer p50/p95/p99, intervalles >50/100/500 ms et maxima (`FRAMEPROF527`), constructions et coûts (`SHADERCOST534`, `SHADERSTALL538_EVENT`), puis les nouvelles lignes 543.

Lecture des nouvelles mesures :
* `origin` montre si une pause vient d'un nouveau shader (inévitable sans préchargement) ou d'un nouvel état (normalisable).
* `feedback` et `vs/fs_library_us` montrent si la bibliothèque MSL était en cache ; le reste de `driver_us` est la compilation backend.
* Un `process_cpu_us` élevé avec un `thread_cpu_us` faible confirmerait la contention SPU. Il justifierait alors la piste suivante : faire céder les boucles SPU inactives pendant qu'une compilation bloque le RSX, après validation de l'équivalence invitée.
* `SHADERPUB543 caller` indique le coût disque retiré du RSX.
* `repeated_builds` doit rester à 0.

## 6. Pistes suivantes, par ordre de levier attendu

1. Contention CPU pendant les compilations (SPU PUTLLC à 3,3–3,7 cœurs) : décider avec `process_cpu_us`.
2. Checkpoint du `VkPipelineCache` avant une éventuelle terminaison iOS : l'hôte n'appelle aujourd'hui aucune API de pause du Core. Il faut un point d'accroche explicite et sûr vis-à-vis de la destruction du device.
3. Concurrence du préchargement à cache Metal froid (verrou unique MoltenVK) : à mesurer avant tout changement.
4. Topologie et primitive restart en état dynamique (`VK_EXT_extended_dynamic_state`, présent dans MoltenVK) : moins de `VkPipeline`, gain Metal faible.

## Livraison

### Core iPhone (CI)

* Échec conservé : run `40210639364` (commit `aa7ac54`), contrôle syntaxique iOS, voir §3.
* Succès : run `40212465374`, commit `d3689eb`. Toutes les étapes sont vertes : cas natifs 543 sur le runner macOS, compilation du Core iPhone, exports (88), chargement passif et identité 543. `libRPCS3Core.dylib` arm64, ABI 30, SHA-256 `489815d0659454d831380cb3e23b66f56d48b2195d573c6be25e7b40b7bf1a6d`, delta canonique `9ed7d2c2…`. Identités de codegen inchangées depuis 542 (PPU `a987639e9f838d1c`, SPU `d070cb361bdef607`) : aucune recompilation JIT imposée par ce changement.
* Harnais 543 sur le runner (Apple clang, ASan+UBSan puis TSan) : mêmes résultats fonctionnels qu'en local. `store()` côté appelant, p50 ASan : 751 → 1,5 µs avec le fsync réel du runner, et 110 505 → 1,5 µs avec un commit +10 ms injecté. Limite : file saturée (300 enregistrements), le pire appel reste une écriture inline payée par l'appelant (max 57–60 ms sur le runner). C'est le comportement de débordement voulu. Disque de runner, pas d'iPhone (`docs/evidence/rpcs3-cell543-ci.json`).

### IPA privée

Voir la section ajoutée après exécution du workflow de livraison. Aucune IPA n'est déclarée avant vérification du fichier téléchargé.
