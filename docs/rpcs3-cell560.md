# RPCS3 iOS 560 — relectures GPU de Dragon Ball Z Budokai HD et écriture différée des framebuffers

26 octobre 2026. Ce document part des journaux du **build 559** envoyés par le
mainteneur pour Dragon Ball Z Budokai HD Collection (`BLES01658`). Il décrit le
Core 560 qui en découle. **Aucun gain 560 n'est mesuré sur iPhone.**

## 1. Ce que montrent les journaux 559

Les journaux sont chiffrés par
[`evidence/rpcs3-cell560-dbz-observed.json`](evidence/rpcs3-cell560-dbz-observed.json),
avec leurs SHA-256 et un résumé par fenêtre.

**Périmètre des fichiers.**
- La capture vient du processus 36124. La timeline va de 22:28:50 à 22:43:30
  UTC, les journaux de performance de 22:30:00 à 22:44:46.
- Les traces de restauration fournies datent des builds 547/553.
- La partie 553 de la timeline concerne Bladestorm (`BLES00113`).
- Aucun de ces deux derniers ensembles ne décrit le processus DBZ 559.

**Constats.** Dans les 161 fenêtres de la session 2 qui portent `READBACK555` :
- chaque lot de relecture transfère **une section de 3 686 400 octets**, soit
  une surface 1280×720 en 32 bits ;
- tous les lots sont classés `unknown` ;
- les compteurs `OPT559` sont nuls partout : aucun chemin 559 n'est concerné ;
- il y a toujours exactement **une relecture par image de plus** que d'attentes
  GPU du thread RSX (site `texture`).

| Fenêtres | Relectures/image | FPS médian | Relecture ms/image | Attentes RSX/image | Attente RSX ms/image |
|---|---:|---:|---:|---:|---:|
| 92 (dont menus et scènes légères) | 2 | 40,6 | 8,83 | 1,00 | 4,01 |
| 69 (combats, 167–261 dessins/image) | 3 | 42,2 | 14,16 | 1,99 | 8,66 |

Les durées de relecture incluent l'attente du GPU et la copie. Elles se
recouvrent entre threads et ne forment pas une somme séquentielle de temps
d'image.

En combat, le thread RSX est occupé à 73 % (médiane) et passe 8,7 ms par image
à attendre le GPU, pour une image de 23,7 ms.

## 2. Le chemin de code

Write Color Buffers est désactivé, comme le montre la configuration de la
timeline (`wcb=false`).
1. `VKGSRender::prepare_rtts` appelle `commit_framebuffer_memory_region` à
   chaque liaison d'un framebuffer.
2. Cette fonction invalide la zone avec la cause `committed_as_fbo`.
3. Cette cause ignore les sections dont la base diffère de celle du
   framebuffer, mais **pas** l'écriture en mémoire. Une section relisible
   `framebuffer_storage` qui commence à la même adresse est donc relue de façon
   synchrone sur le buffer de commandes principal : `flush_set`,
   `cleanup_after_dma_transfers`, soumission, `wait_for_fence`.
4. Une telle section existe dès qu'un blit vise ce framebuffer : le code
   commente « All blit targets must be protected, regardless of WCB/RCB
   settings ».

Le thread RSX attend alors la fin de **tout** le travail GPU déjà enregistré.
Pendant ce temps, il ne prépare rien d'autre.

La relecture restante, une par image, n'a pas d'attente RSX. C'est le chemin
des fautes CPU (`on_access_violation`, buffer secondaire).

**Limite.** Les journaux 559 ne portent pas d'origine pour ces lots. Ce
chemin est déduit du code et du décompte. Le 560 les attribue (section 4).

## 3. Le changement 560 (`CELL560_DEFERRED_COMMIT`)

**Principe.** Quand un commit de framebuffer devrait relire **une seule**
section relisible `framebuffer_storage`, le 560 procède ainsi :
1. il enregistre au même endroit la même copie GPU que la relecture d'origine ;
2. il garde les pages verrouillées, sans attendre ni copier vers la mémoire
   invitée ;
3. il soumet le buffer juste après le commit, comme après une copie spéculative.
   Une écriture ultérieure n'attend donc jamais un buffer non soumis.

**Quand les octets sont écrits en mémoire :**
- sur le premier besoin réel : faute CPU en lecture ou en écriture, validation
  de sauvegarde d'état (`handle_invalidated_memory_range` relit la mémoire
  résidente GPU), ou toute autre relecture ;
- avant toute libération des pages : `unprotect`, `discard`, une section salie
  puis libérée, ou une reprotection lisible.

**Quand la copie est abandonnée.** Si le GPU recrée le contenu, par exemple
au blit suivant, alors que les pages sont restées verrouillées, la copie est
abandonnée. Personne n'a pu l'observer.

**Ce que voit le jeu.** La mémoire invitée n'est observable qu'à travers une
faute ou une libération. Le jeu lit donc **exactement les octets
d'aujourd'hui**, au même moment logique. Seule l'attente disparaît quand
personne ne lit.

**Réglage.**
- *Experimental → FPS Experiments → Deferred framebuffer write-back*
  (`experimental.deferred_fbo_writeback`).
- Automatique : Dragon Ball Z Budokai HD Collection `BLES01658` uniquement.
- Désactivé : comportement 559 exact.
- Le réglage est lu au démarrage. Il ne s'applique qu'avec WCB désactivé,
  puisque les commits ne passent par ce chemin qu'alors.

**Hors périmètre.**
- Plusieurs sections relisibles dans la même invalidation : l'ordre, les
  exclusions et l'héritage entre elles restent ceux du 559.
- Les sections `blit_engine_dst`.
- Les relectures des fautes CPU elles-mêmes, qui restent nécessaires.

## 4. Mesure sur appareil

- **Ligne `COREPROF OPT560` par fenêtre :**
  - état du réglage ;
  - commits différés et leurs octets ;
  - écritures différées (nombre, total, maximum en ms) et leurs octets ;
  - écritures forcées par une libération ;
  - copies abandonnées et leurs octets ;
  - soumissions.
- **`READBACK555`** gagne trois origines ajoutées en fin de ligne, sans changer
  l'ordre des champs 555 : `fbo_commit` (relecture synchrone d'un commit, si le
  réglage est désactivé ou inapplicable), `fault_read` et `fault_write`.
- **Journal de démarrage :** il ajoute `deferred_fbo_writeback=`.

Pour confirmer sur DBZ, il faut relever :
- `deferrals` proche de 1 à 2 par image ;
- l'attente `texture` du RSX en forte baisse ;
- `writebacks` comparé à `dropped`, pour savoir si le jeu lit vraiment ces
  zones ;
- le FPS et les p95/p99 sur les mêmes scènes en 559 et en 560.

Si `deferrals` reste à zéro, l'hypothèse de la section 2 est fausse. Les
origines `READBACK555` diront alors d'où viennent ces relectures.

## 5. Validation

**Delta canonique.**
- Il est régénéré depuis l'amont `22f11527` et touche 11 fichiers Core, dont un
  nouveau (`ios/IOSDeferredCommit.h`).
- Les 287 empreintes de post-image sont vérifiées après application sur une
  source vierge.
- La fixture `test/fixtures/rpcs3_cell560.diff` reconstruit exactement les
  préimages 559.
- Les identités de codegen sont inchangées : PPU `a987639e9f838d1c`, SPU
  `d070cb361bdef607`. Il n'y a ni alias ni recompilation à froid.

**`test/rpcs3_cell560_test.py`.** Il exécute les vrais corps 560 contre leur
préimage 559 authentifiée, sous ASan+UBSan puis TSan :
- `flush`, `unprotect`, `discard` et `reprotect` ;
- les auxiliaires du commit différé ;
- la remise à zéro de `create()` Vulkan ;
- la branche relisible d'`invalidate_range_impl_base` et sa décision ;
- `invalidation_cause` et sa table.

Résultats :
- **12 scénarios**, tous identiques au 559 pour ce que lit le jeu : lecture
  après dessin, nouveau blit avant lecture, cinq images sans lecture, écriture
  partielle, surface remplacée, sauvegarde d'état, section salie puis faute,
  reprotection en lecture seule, libération par `unprotect`, lecture avant
  commit, lecture immédiate, deux sections (non différées).
- **Attentes GPU :** 17 → 3. Pour cinq images sans lecture : 5 → 0, avec 4
  copies abandonnées.
- **Sûreté :** aucune attente sur un buffer non soumis, et aucune page libérée
  avec des octets dus. Sans la soumission après commit, le contrôle négatif
  attend sur un buffer non soumis.
- **Désactivé :** strictement le 559.
- **Mutations :** six altérations d'une ligne de production sont toutes
  détectées (écriture oubliée dans `discard`, `unprotect`, la libération salie
  ou la reprotection, différé sans copie, `create()` qui garde la dette).

**Pilote et ARM64.**
- **Pilote CI :** `rpcs3cell560_core.py` a été exécuté de bout en bout sur une
  source fraîchement matérialisée. Il authentifie l'artefact de diagnostics du
  Core 559 (`12690536391`, run `40403710130`), et `--verify-reuse` passe.
- **ARM64 :** même banc compilé par LLVM 22.1.8 pour
  `aarch64-linux-gnu -mcpu=apple-a7 -march=armv8.4-a` et exécuté sous qemu,
  avec UBSan en mode trap. Les résultats sont identiques, et l'empreinte du
  banc est celle du run hôte.
- **Syntaxe de production (ARM64, `RPCS3_IOS`, `-Werror` du projet et
  `-Wshadow`) :** `VKGSRender.cpp`, `VKTextureCache.cpp`, `VKPresent.cpp`,
  `texture_cache.cpp`, `RPCS3IOSPerformance.cpp`,
  `RPCS3IOSExperimentalPolicy.cpp` et `RPCS3IOSSettings.cpp` compilent sans
  erreur. Les diagnostics sont identiques à ceux du 559.
- **Tests de source existants :** les 9 tests passent.
  `neo_swap_core_pin_test.py` échoue comme sur la base (pin public `cfe92344`).

Le reçu complet est dans
[`evidence/rpcs3-cell560-host-linux.json`](evidence/rpcs3-cell560-host-linux.json).

## 6. Limites

- **Rien n'est mesuré sur iPhone** pour 560 : ni FPS, ni temps d'image, ni
  attentes GPU, ni rendu.
- Le gain attendu en combat est au plus les ~8,7 ms/image d'attente RSX
  observés en 559, si le jeu ne lit pas ces zones. S'il les lit, l'attente se
  déplace vers le thread qui lit, et y est plus courte puisque la copie a été
  soumise plus tôt.
- La relecture par faute CPU (environ 1 par image) n'est pas traitée. Elle est
  nécessaire.
- Le modèle de test remplace Vulkan, Metal et le GPU par des adaptateurs. Il
  vérifie les états du cache et ce que lit le jeu, pas le pilote.
