# RPCS3 547 — libérer le CPU pendant les attentes GPU et les compilations bloquantes (25 octobre 2026)

Demande : phase d'optimisation profonde du RPCS3 embarqué (FPS, saccades, SPU,
RSX, shaders, mémoire), avec God of War III `BCES00510` en priorité, des
changements de code mesurés, et aucun rendu sacrifié. Base : Core 546
(`343649293c`, identités PPU/SPU `a987639e9f838d1c` / `d070cb361bdef607`).

## 1. Les cinq coûts mesurés les plus importants

Sources : journaux iPhone du build 541 (DBZ HD Collection, session 4,
fenêtres de 5 s) et mesures God of War III 538/541 consignées dans
`docs/rpcs3-cell543.md`. Aucune mesure 542–546 de GoW3 n'existe.

| Rang | Coût | Mesure | Statut |
| --- | --- | --- | --- |
| 1 | Pipelines graphiques au premier usage | DBZ : 15 pipelines, 2,47 s dans une fenêtre, unités 0,16–0,54 s. GoW3 541 : 2–4 s par pipeline avec 3,3–3,7 cœurs SPU en boucle, contre 0,3–0,8 s en 538 | 547 : pression de compilation (§2.2) |
| 2 | Attente CPU→GPU en boucle active | DBZ : 0,42–1,68 s par fenêtre sur le thread RSX, le plus chargé (0,55–0,82 cœur) | 547 : attente hybride (§2.1) |
| 3 | Contention des réservations SPU | DBZ fenêtre 25 : 868 ms de verrou de plage dont 432 ms `PUTLLC` ; GoW3 541 : 0,9–3,4 s par fenêtre | Partiellement (§2.2), sinon §4 |
| 4 | Préparation JIT à froid | 3,58 s de compression pour un objet PPU de 6,66 Mo | Corrigé en 546 |
| 5 | Journalisation sur les chemins critiques | ~0,17 ms par ligne de restauration avec `fsync` | Corrigé en 546 |

Le profil GoW3 n'est pas appliqué sur l'appareil observé : les sessions des
builds 534 à 541 chargeaient un ancien fichier de configuration complet du jeu
(`legacy_custom=1`, `database=0`), prioritaire par conception. Le mode de
shaders effectif est donc Legacy, sans draw sauté.

## 2. Modifications du Core

### 2.1 Attente de fence bornée puis passive (`vkutils/sync.cpp`)

`vk::wait_for_fence` sans délai (réutilisation d'un tampon de commandes,
`command_buffer::begin`) tournait sur `vkGetFenceStatus` pendant toute la durée
du travail GPU. Sur iOS, elle tourne désormais 100 µs, puis s'endort dans
`vkWaitForFences` : MoltenVK y attend sur une variable de condition que le
gestionnaire de fin de Metal signale. L'attente se fait par tranches de 100 ms,
sans délai global, comme avant. Le résultat, l'ordre et le traitement d'une
perte de device sont identiques. Les attentes avec délai (cache de textures) ne
changent pas.

### 2.2 Pression de compilation (`IOSCompilePressure.h`, `ProgramStateCache.h`, `SPUThread.cpp`)

Dans MoltenVK 1.4.2 (`MVKSync.mm`, `MVKMetalCompiler::compile`), le pipeline
Metal est construit sur une file GCD globale de priorité *default*, et Metal
compile hors processus. Les deux tournent sous la priorité *user-interactive*
des threads de l'émulateur, pendant que le thread RSX attend sur une
condition, sans transmission de priorité. Pendant qu'un draw attend un
pipeline, une interrogation GETLLAR confirmée d'une donnée inchangée (même
adresse, même PC, au moins 2 répétitions) prend le chemin passif qu'RPCS3
possède déjà. La SPU dort alors sur le notificateur de réservation : elle est
réveillée par toute écriture sur la ligne, ou après 100 µs. Ce choix ne fausse
pas l'historique adaptatif qui sélectionne plus tard l'attente active. Les
instructions invitées, leur ordre et le travail SPU actif ne changent pas.

`SPUThread.cpp` fait partie de l'empreinte SPU. Le code modifié est du C++
hôte appelé par les objets SPU, pas leur contenu : `JITCacheCompatibility.cmake`
associe cet instantané exact à l'empreinte 546. La vraie fonction CMake
confirme PPU `a987639e9f838d1c` et SPU `d070cb361bdef607`. Aucun cache n'est
recompilé.

### 2.3 Mesure

`COREPROF PRESSURE547` par fenêtre : nombre et durée des compilations qui
bloquent un draw, attentes SPU passées en passif, fences terminées pendant
l'attente active ou endormies. La famille `pressure` de `RPCS3-timeline.log`
reprend ces valeurs.

## 3. Mesures (sans iPhone)

`test/rpcs3_cell547_test.py` exécute les corps de production 546 et 547 de
`wait_for_fence` face à une fence modelée sur MoltenVK, sous ASan+UBSan puis
en `-O2`.

| Attente GPU | CPU du thread qui attend, 546 → 547 | Réveil médian, 546 → 547 |
| --- | --- | --- |
| macOS arm64, 8 ms (≈ 30 ms effectives, minuteur du runner) | 30 638 → 116 µs | 4,2 → 31,3 µs |
| macOS arm64, 2 ms | 9 223 → 126 µs | 2,6 → 56,1 µs |
| macOS arm64, 0,3 ms | 1 797 → 118 µs | 0,9 → 33,3 µs |
| Linux x86-64, 8 ms | 8 005 → 131 µs | 2,5 → 94,5 µs |
| Linux x86-64, 2 ms | 2 083 → 117 µs | 1,5 → 56,7 µs |

Calcul concurrent pendant une attente (tous les cœurs occupés) : 194 →
157–161 ms sur macOS arm64 (3 cœurs), 136–139 → 86–87 ms sur Linux (4 cœurs).

Contrepartie mesurée : 30 à 100 µs de latence de réveil par attente bloquée.
Sur DBZ (150 à 390 attentes par fenêtre de 5 s), cela représente au plus
≈ 40 ms par fenêtre, contre 0,4 à 1,7 s de CPU libéré. Ce bilan est une
projection, pas une mesure iPhone.

La pression de compilation n'est pas mesurable hors appareil : son effet
dépend de l'ordonnanceur iOS et du service de compilation Metal. Le test
vérifie l'en-tête réel (portées imbriquées et concurrentes, compteurs) et les
deltas exacts du code SPU et du cache de pipelines.

**Aucun gain de FPS n'est revendiqué.** Ces changements libèrent du CPU. Ils ne
deviennent des images supplémentaires que si le CPU limite la scène.

## 4. Ce qui n'est pas fait, et pourquoi

| Piste | Raison |
| --- | --- |
| Mode de shaders asynchrone par défaut | `async_recompiler` saute des draws ; l'interpréteur n'est pas prouvé équivalent. Exclu par la demande |
| Soumissions MoltenVK asynchrones (`MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS=0`) | L'encodage Metal quitterait le thread RSX, mais irait sur une file *user-initiated* inférieure aux threads RSX/SPU. C'est un pari : à évaluer par un test A/B sur iPhone |
| MoltenVK recompilé avec une QoS de compilation plus haute | Patch possible (`MVKMetalCompiler::compile`), mais il faudrait construire MoltenVK depuis les sources (aujourd'hui binaire épinglé). À décider avec `PRESSURE547` et `SHADERFEEDBACK543` (`thread_cpu_us` contre `process_cpu_us`) |
| `MTLBinaryArchive`, `VK_EXT_graphics_pipeline_library` | Absents de MoltenVK 1.4.2 |
| Attente FIFO RSX (`Yield` par défaut) | La cellule 487 a gardé ce défaut ; « Bounded sleep » reste une option |
| Code SPU/PPU généré (NEON) | Changerait les empreintes (recompilation de tous les caches) ; demande LLVM 22 et des preuves d'équivalence. Hors de cette étape |

## 5. Protocole iPhone (547 contre 546)

Même jeu, même scène, même sauvegarde, appareil refroidi, caches identiques.
Exporter `RPCS3-timeline*.log`. Comparer par fenêtre :

1. `wait_ms.cpu_gpu_fence` et `pressure.fence_blocked` : le temps d'attente
   reste comparable, le CPU du thread RSX (`summary`) doit baisser.
2. Shaders froids : `pressure.blocking_builds` (durée max et totale) et
   `shader_stall_events.max_us` ; `pressure.spu_passive_waits` > 0 montre que
   le mécanisme s'est déclenché.
3. Gameplay chaud et cinématiques : `frame_ms.p95_ms`, `p99_ms`, `max_ms`,
   `summary.avg_fps`.
4. Session de plus de 30 minutes : `host.thermal_max` et évolution des FPS.

## 6. Livraison privée 547

IPA de test : arbre hôte de la livraison 546 (`6c6c6241`) et Core RPCS3 547.
Les 93 chemins validés ailleurs depuis (interface Liquid Glass, notes MeloNX)
sont restaurés dans le runner seulement ; l'historique Git est intact.
L'interface Liquid Glass prend le numéro 548. Aucune release, aucun tag, aucune
fusion vers `main`.

- Core : source `1b5c278c`, run 40232640441 (journaliseur Foundation, tests
  natifs 547 sur arm64, compilation, exports, chargement passif, identités
  inchangées). Premier essai `b77fb8e0`, run 40232300288, en échec sur un seul
  contrôle du harnais (sommeil simulé de 387 ms au lieu de 250 ms) : corrigé
  dans le test, pas dans le Core.
- IPA : source `08f2f7fa`, run 40233140957, tous les validateurs réussis, dont
  `validate_rpcs3_547_ipa.py` (marqueurs `PRESSURE547` du Core et du pont,
  preuves du journaliseur réexécutées par la livraison).
- Fichier remis : `RewindBox-Build547.ipa`, version 0.0.8 (547), iOS 18
  minimum, **186 395 394 octets**, SHA-256
  `09030d12519e6815850a546fcaddc6cbaacd18da943e4e4bcdcf8704d1d9e4e6`, égal à
  `SHA256SUMS` et à `signed-payload-identity.json` ; 87 signatures. Artefact
  chiffré `12614695376` pour `build-utils/delivery-547-recipient.pem` (clé
  privée hors Git), conservé jusqu'au 8 novembre 2026. Déchiffré et revérifié ;
  `validate_rpcs3_diag487_ipa.py` rejoué localement.
- S'installe par-dessus la 546 après re-signature SideStore. Aucune validation
  sur iPhone. Ne pas réutiliser le numéro 547. Preuve :
  `docs/evidence/rpcs3-cell547-delivery.json`.
