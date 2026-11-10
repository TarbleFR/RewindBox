# RPCS3 iOS 561 — soumission anticipée des buffers de commandes (Dragon Ball Z Budokai HD)

27 octobre 2026. Ce document part de la mesure du **build 560** sur Dragon Ball
Z Budokai HD Collection (`BLES01658`), décrite dans
[`rpcs3-cell560.md`](rpcs3-cell560.md) §9. Il décrit le Core 561 qui en
découle. **Aucun gain 561 n'est mesuré sur iPhone.**

## 1. Ce que montre le 560

Reçu : [`evidence/rpcs3-cell560-dbz-measured.json`](evidence/rpcs3-cell560-dbz-measured.json).

En combat soutenu (fenêtres 13–30) :
- ~177 dessins par image, ~42 FPS, soit ~23–24 ms par image ;
- le jeu relit **une surface couleur complète par image** par faute CPU
  (`fault_read`, 3,69 Mo), et rien n'est abandonné (`dropped` = 0) ;
- cette relecture coûte **~7,9 ms par image**, et `frame_latency` vaut
  ~8,0 ms par image : la relecture attend que le GPU ait exécuté l'image.

La relecture est nécessaire ; le 560 l'a montré. Ce qui ne l'est pas, c'est
que le GPU ne **commence** qu'au moment où on lui envoie le travail.

## 2. Le chemin de code

Le thread RSX enregistre tous les dessins d'une image dans un seul buffer de
commandes principal. Il ne le soumet qu'à deux moments :
- au flip (`queue_swap_request`) ;
- quand une faute CPU sur une zone écrite par le GPU demande un vidage
  (`on_access_violation` → `m_flush_requests` → `flush_command_queue`).

Pendant les ~10 ms d'enregistrement d'une image de combat, le GPU n'a donc
rien à faire s'il a fini l'image précédente. Il reçoit les ~7 ms de travail
d'un bloc, et la relecture qui suit attend ce bloc entier.

## 3. Le changement 561 (`CELL561_EARLY_SUBMIT`)

**Principe.** À la fin d'un dessin (`VKGSRender::end`), si :
1. au moins **32 dessins** ont été enregistrés depuis la dernière soumission
   principale ;
2. le GPU a **terminé** cette dernière soumission (test non bloquant de sa
   fence, `command_buffer_chunk::poke()`) ;
3. l'image n'a pas déjà utilisé ses **6** soumissions anticipées ;
4. aucun vidage n'est en cours, aucune récupération d'interblocage de
   l'offloader n'est active et l'enregistrement n'est pas ininterruptible,

alors le 561 soumet les dessins enregistrés avec `flush_command_queue()`, le
même appel qu'une demande de vidage utilise déjà au même endroit.

**Ce qui ne change pas.**
- Les commandes, leur ordre et leur synchronisation sont identiques. Seules
  les frontières entre buffers de commandes bougent.
- Un GPU encore occupé ne voit jamais de soumission anticipée : il a déjà du
  travail.
- Le flip remet le budget de l'image à zéro.
- Hors `RPCS3_IOS`, le renderer est inchangé.

**Coût.** Chaque soumission anticipée referme la passe de rendu et en ouvre
une nouvelle, ce qui coûte un peu de GPU. Le seuil de 32 dessins et le plafond
de 6 par image bornent ce coût.

**Réglage.**
- *Experimental → FPS Experiments → Early command buffer submission*
  (`experimental.early_submit`, clé de configuration « Early Command Buffer
  Submission »).
- Automatique : Dragon Ball Z Budokai HD Collection `BLES01658` uniquement.
- Désactivé : comportement 560 exact.
- Le réglage est lu au démarrage.

## 4. Mesure sur appareil

- **Ligne `COREPROF OPT561` par fenêtre :**
  - `early_submit` : état du réglage ;
  - `early_submits` et `early_draws` : soumissions anticipées et dessins
    qu'elles ont portés ;
  - `gpu_busy_checks` : fins de dessin où le GPU était encore occupé ;
  - `frame_capped_checks` : fins de dessin où l'image avait épuisé son
    budget ;
  - `min_draws` et `max_per_frame` : les deux bornes (32 et 6).
- **Journal de démarrage :** il ajoute `early_submit=`.

Pour confirmer sur DBZ, il faut relever sur les mêmes scènes de combat en 560
et en 561 :
- `early_submits` non nul, idéalement plusieurs par image ;
- `fault_read` ms/image (`READBACK555`) et `frame_latency` en baisse ;
- le FPS et les p95/p99.

Si `early_submits` reste à zéro et que `gpu_busy_checks` est élevé, le GPU
n'est jamais à vide pendant l'enregistrement : DBZ est alors limité par le
GPU, et le 561 n'y change rien.

## 5. Validation

**Delta canonique.**
- Il est régénéré depuis l'amont `22f11527` et touche 10 fichiers Core, dont un
  nouveau (`ios/IOSEarlySubmit.h`).
- Les 288 empreintes de post-image sont vérifiées après application sur une
  source vierge. Les 278 autres sources Core sont inchangées.
- La fixture `test/fixtures/rpcs3_cell561.diff` reconstruit exactement les
  préimages 560.
- Les identités de codegen sont inchangées : PPU `a987639e9f838d1c`, SPU
  `d070cb361bdef607`. Il n'y a ni alias ni recompilation à froid.

**`test/rpcs3_cell561_test.py`.** Il exécute les vrais corps 561 contre leur
préimage 560 authentifiée, sous ASan+UBSan puis TSan :
- `ios_early_submit`, le suivi après la soumission principale et la remise à
  zéro au flip ;
- `decide()` sur 2 048 combinaisons d'entrées, de part et d'autre de chaque
  borne.

Le banc modélise le thread RSX et une file GPU en temps simulé. **Ce n'est pas
une mesure.**
- **Combat** (177 dessins, ~10 ms d'enregistrement et ~7 ms de GPU par image,
  0,2 ms supposées par soumission) : attente de relecture 7,2 → 1,4 ms par
  image, image 24,0 → 18,2 ms, 5 soumissions anticipées par image de 32
  dessins chacune.
- **Scènes légères** (26 dessins par image) : strictement identiques au 560.
- **Limité par le GPU** (sans relecture) : 2 soumissions anticipées sur tout
  le run, image 28,54 → 28,47 ms : pas pire.
- **Désactivé**, et les **trois gardes** (vidage, interblocage,
  ininterruptible) : frontières identiques au 560.
- **Ordre** des commandes préservé partout ; plafond atteint avec un GPU
  rapide ; budget remis à zéro à chaque image.
- **Mutations :** sept altérations d'une ligne de production, qui gardent
  toutes les ancres de source, sont toutes détectées par leur comportement
  (soumission avec un GPU occupé, sans seuil, sans plafond, compteur non remis
  à zéro, dernière soumission oubliée, budget jamais remis à zéro, garde
  ignorée).

**Pilote et ARM64.**
- **Pilote CI :** `rpcs3cell561_core.py` a été exécuté de bout en bout sur une
  source fraîchement matérialisée. Il authentifie l'artefact de diagnostics du
  Core 560 (`12698765197`, run `40420391683`), et `--verify-reuse` passe.
- **ARM64 :** même banc compilé par LLVM 22.1.8 pour
  `aarch64-linux-gnu -mcpu=apple-a7 -march=armv8.4-a` et exécuté sous qemu,
  avec UBSan en mode trap. Les résultats sont identiques, et l'empreinte du
  banc est celle du run hôte.
- **Syntaxe de production (ARM64, `RPCS3_IOS`, `-Werror` du projet et
  `-Wshadow`) :** `VKGSRender.cpp`, `VKDraw.cpp`, `VKTextureCache.cpp`,
  `VKPresent.cpp`, `texture_cache.cpp`, `RPCS3IOSPerformance.cpp`,
  `RPCS3IOSExperimentalPolicy.cpp` et `RPCS3IOSSettings.cpp` compilent sans
  erreur. Les 81 diagnostics sont ceux du 560, aux numéros de ligne près.
- **Tests de source existants :** les 9 tests passent.
  `neo_swap_core_pin_test.py --source-only` passe ; le mode complet échoue
  comme sur la base (pin public `cfe92344`).

Le reçu complet est dans
[`evidence/rpcs3-cell561-host-linux.json`](evidence/rpcs3-cell561-host-linux.json).

**Core iPhone 561 construit** (run `40486026315` sur `5b033881`, macOS ARM64,
Apple clang 17, Xcode 16.4) :
- les 8 scénarios et les 2 048 décisions passent sous ASan+UBSan et TSan,
  avec exactement les chiffres du run Linux ; l'empreinte du banc est la même ;
- dylib SHA-256 `7b1e4fda…5c20cbe`, ABI 30, 88 exports, chargement passif
  vérifié, 138 entrées enregistrées ; les huit marqueurs 561 sont présents ;
- identités de codegen inchangées (PPU `a987639e9f838d1c`, SPU
  `d070cb361bdef607`) : aucune recompilation à froid ;
- artefacts : Core `12725403841`, diagnostics `12725733046`.

Reçu : [`evidence/rpcs3-cell561-macos.json`](evidence/rpcs3-cell561-macos.json).
Ce ne sont pas des mesures iPhone.

## 6. Limites

- **Rien n'est mesuré sur iPhone** pour 561 : ni FPS, ni temps d'image, ni
  attentes GPU, ni rendu.
- Le gain du modèle dépend du coût réel d'une soumission et d'une nouvelle
  passe de rendu sur le GPU Apple via MoltenVK, que seul l'appareil donne.
- Si le GPU n'est jamais à vide pendant l'enregistrement, le 561 ne fait rien.
- Le modèle remplace Vulkan, Metal et le GPU par une file simulée. Il vérifie
  les décisions, l'ordre et les frontières, pas le pilote.
- Les autres titres sont inchangés en Automatique. En particulier, `BLES01717`
  est limité par le CPU invité, et sa GameDB impose le mode SPU sûr : aucun
  levier sûr n'est ajouté pour lui.

## 7. Recette de l'IPA privée 561 (mode « Core seul »)

561 livre le produit 560 octet pour octet, qui est lui-même le produit 559 et
558. Seul le Core RPCS3 change : le 560 (`cba3fa9f`) est remplacé par le 561
(`5b033881`, run `40486026315`). C'est la première livraison qui utilise le
mode « Core seul » de [`core-swap-delivery.md`](core-swap-delivery.md) : le
job macOS part de l'application publiée `0.0.10` (build 559) au lieu de la
recompiler.

- **Arbre** (`rpcs3cell561_tree.py`) : l'arbre 560 livré, plus les fichiers de
  recette Core pris à `5b033881` et la documentation 561.
  - 5 d'entre eux étaient épinglés au 560 : le delta, le manifeste, le script
    de build, le test de pin et `rpcs3-core.yml`. Seul le commit Core
    `5b033881` les a modifiés depuis `cba3fa9f`.
  - La recette porte `build-utils/core_swap_base.py`.
  - Le travail MeloNX poussé entre-temps (`9b40129f`, clavier Switch et
    bascule L3/R3) n'entre pas dans cette IPA : le pin remet chaque fichier
    produit à sa version livrée, et un changement de fichier produit exige le
    build complet.
- **Contrôles hérités** (`rpcs3cell561_delivery.py`, `as_560()`) : la recette
  560 tourne inchangée sur l'arbre 560 livré (index de travail, fichiers 561
  dans leur version 560, modules Python de cet arbre, `BUILD_NUMBER` 560,
  identité du Core installé mise de côté). Les vues 559, 558, 557 et 554
  suivent par emboîtement.
- **Core** : l'identité 561 est liée au commit `5b033881`. Le run est vérifié
  par l'API GitHub : commit, workflow et quatre étapes requises.
- **Validateurs IPA** : `validate_rpcs3_561_ipa.py` ajoute les marqueurs 561
  (`COREPROF OPT561`, compteurs, réglage `experimental.early_submit`) aux
  marqueurs 555, 559 et 560. Interface, MeloNX et fichiers de bibliothèque :
  les validateurs 558, atteints à travers les vues 560 et 559.
- **Workflow** : `rpcs3-cell561-delivery.yml` est dérivé du workflow complet
  par `make_core_swap_workflow.py` (base `0.0.10`, SHA-256 `f16c2a35…7896480d`,
  reçu `evidence/rpcs3-cell559-delivery.json`).

## 8. IPA privée 561 livrée (premier run « Core seul »)

- **Premier essai** : run `40486995044` sur `5dd6a5ae`. Le job `checks`
  réussit ; le job macOS échoue à l'empaquetage, sur le contrôle StikJIT
  d'avant scellement. Cause et correction :
  [`core-swap-delivery.md`](core-swap-delivery.md) § 6.
- **Run** `40491394767` sur `9a805c6c` : `checks` (5,2 min) et `cold`
  (21,0 min, contre 24,9 min pour le build complet 560) réussis.
- **Artefact** `12730102171`, chiffré pour `build-utils/delivery-561-recipient.pem`
  (la clé privée n'est pas dans Git).
- **IPA** `RewindBox-Build561-9a805c6c…-cold.ipa` : 0.0.8 (561), 188 062 278
  octets, SHA-256 `d92f314bce6d140e2d12962c552cd25e395fc329fbb312f704ada827b3f5a18d`,
  égal à `SHA256SUMS` et à `signed-payload-identity.json`.
- **Comparée à l'IPA publiée 0.0.10** (build 559, 4 599 fichiers) :
  - sur 85 images Mach-O, 73 sont identiques à l'octet ;
  - 11 exécutables (dont `Runner`) ne diffèrent que par leur signature, parce
    que l'`Info.plist` de leur bundle porte le nouveau numéro ;
  - seul `libRPCS3Core.dylib` change de code : c'est le Core 561, dont
    l'empreinte de code et de données est celle de l'artefact du run Core ;
  - le reste : versions des `Info.plist`, signatures, reçus de source et
    d'identité (les quatre reçus 559 deviennent 561).
- **Revalidation locale** sur `9a805c6c` épinglé : les rapports RPCS3,
  interface et fichiers de bibliothèque sont identiques octet pour octet à
  ceux de la CI.

Reçu : [`evidence/rpcs3-cell561-delivery.json`](evidence/rpcs3-cell561-delivery.json).
Elle s'installe par-dessus la 559 ou la 560 après re-signature SideStore.
Aucune release GitHub, aucune mesure sur iPhone.

La 562 (autre session, run `40490382532`) porte ce même Core 561 avec le
clavier Switch et la bascule L3/R3 de MeloNX ; voir `docs/melonx-keyboard562.md`.

## 9. Mesure sur DBZ (journaux de la 562, Core 561)

27 octobre 2026. Le mainteneur a fourni les journaux de la **562** (autre
session : Core 561 et clavier MeloNX) sur Dragon Ball Z Budokai HD Collection.
Le fichier de performance contient aussi la session DBZ 560 déjà mesurée.
Reçu : [`evidence/rpcs3-cell561-dbz-measured.json`](evidence/rpcs3-cell561-dbz-measured.json).
Mêmes réglages dans les deux sessions ; état thermique nominal en 562.

| Phase (médianes) | 560 | 562 |
|---|---:|---:|
| Combat (~200 dessins/image) : FPS / temps d'image | 41,7 / 24,0 ms | 35,4 / 28,2 ms |
| Combat : attente de relecture (`fault_read`) | 8,0 ms/image | 6,2 ms/image |
| Combat : `frame_latency` | 8,1 ms/image | 6,4 ms/image |
| Combat : soumissions / soumissions anticipées | 3 / 0 | 5 / 2,1 par image |
| Menus sans soumission anticipée (fenêtres 3, 4, 6, 7) : FPS | 51,9 | 43,0 |

**Ce que montrent les journaux.**
- Le 561 fait ce qui était prévu là où il agit : environ deux soumissions
  anticipées par image en combat, et l'attente de relecture baisse de
  ~1,8 ms par image.
- Aucun gain de FPS n'apparaît. Le GPU est encore occupé à ~118 des ~208 fins
  de dessin de chaque image : il est proche de la saturation, et couper l'image
  en plus de morceaux lui ajoute du travail.
- **Le ralentissement de la 562 existe aussi sans le 561** : dans les menus où
  aucune soumission anticipée n'a eu lieu, donc sur le chemin de code exact du
  560, la 562 perd 17 %. Les coûts CPU du thread RSX sont égaux ou plus bas :
  le CPU n'est pas plus lent. La session 562 tourne dans un nouveau conteneur
  d'application. Ces journaux ne permettent donc pas d'attribuer la baisse au
  561.

**Conclusion.** Le 561 n'apporte aucun gain mesurable sur DBZ. Son effet
propre (neutre ou légèrement négatif) ne peut être isolé qu'en alternant le
réglage fenêtre par fenêtre dans une même session.
