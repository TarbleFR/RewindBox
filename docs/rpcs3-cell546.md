# RPCS3 546 — journaux build 541 : écriture JIT et diagnostics bornés (25 octobre 2026)

Demande : analyser les journaux joints, relier les problèmes au code, corriger,
ajouter une instrumentation légère et bornée qui survit aux erreurs de
restauration, livrer une IPA privée. Base : Core 545 (`39ad9725`, run
40223313523), identités PPU/SPU `a987639e9f838d1c` / `d070cb361bdef607`.

## 1. Journaux fournis (faits)

Build observé : **541** dans les quatre fichiers (pas 527). Les faits du texte de
la demande absents de ces fichiers (pids 25548/25865/25906, restauration vdec de
2,04 s, `quota_refused`, `FREEZE_DUMP`, erreur 0x80010006) ne sont attribués à
aucun jeu.

| Processus | Jeu | Contenu |
| --- | --- | --- |
| 31056 | Bladestorm `BLES00113` | Restauration d'état **réussie** (`ppu_exec_end loaded=1`, `SAVESTATE_BOOT`, `finalize_run`) ; 75 objets PPU chargés du cache |
| 31524 | — | `process_start` seul |
| 31545 | Dragon Ball Z HD Collection `BLES01658` | 4 sessions JIT (lanceur puis jeu par `exitspawn`), fenêtres 11 à 38 de la session 4 |

God of War III `BCES00510` a été lancé (app.log, 15:12) puis fermé ; aucune
ligne de son Core ne subsiste. `RPCS3-milestones.log` commence au milieu de la
restauration de Bladestorm, 2,73 s après son début : le fichier de 512 Kio était
**vidé d'un coup** dès qu'il était plein, et les ~768 lignes de trace par
restauration l'ont rempli. Les jalons de GoW3 ont été perdus ainsi.

## 2. Causes mesurées (DBZ, session 4, fenêtres de ~5 s)

- **Pauses sans image = shaders graphiques jamais vus.** Fenêtre 21 : 15
  pipelines construits en 2 474,7 ms (max 540,6 ms), 10 événements
  `SHADERSTALL538` stage 2 consécutifs ; p99 = max = 2 536,5 ms. Les trames de
  201 à 445 ms des fenêtres 13, 17, 19, 22, 23 correspondent chacune à une
  construction de 173 à 405 ms. Le cache shader répond par ailleurs (5 797
  succès, 15 échecs).
- **Mode réellement appliqué** : `Legacy Recompiler (single-threaded)`,
  `configured=0 applied=0` : c'est le défaut iOS du Core
  (`RPCS3IOSGPUDefaults.h`), DBZ n'ayant pas d'entrée GameDB (`database=0`). Le
  profil individuel de GoW3 demande `Async Recompiler (multi-threaded)` ; ce n'est
  pas vérifiable dans ces journaux. Le défaut global n'est pas changé ici (choix
  de rendu, voir 547).
- **Ralentissement soutenu, fenêtre 25** (22,2 fps) : verrou de plage 868,7 ms,
  dont 431,6 ms de `PUTLLC` SPU ; `spu_ms` 75. Contention, pas compilation.
- **Attente CPU→GPU** : `cpu_gpu_fence` 0,42 à 1,68 s par fenêtre (fenêtres
  22–35). Coût récurrent, traité en 547.
- **Mémoire** : aucune pression (marge 4,5 Gio, `memory_pressure_peak=0`).
- **Préparation JIT** : `notifyObjectCompiled` (écriture) est appelé pendant
  `generateCodeForModule`, mais `JITPROF` compte des temps **exclusifs**
  (`JITPhaseProfile.h` soustrait les phases imbriquées) : les 3 578,6 ms
  d'écriture d'un objet PPU de 6 665 088 octets (session 4) **s'ajoutent** aux
  6 927,3 ms de génération, soit ≈ 10,5 s pour ce module dont 34 % de
  compression. Session 2 : 21 objets, 8 502,7 ms d'écriture pour 178 767 ms de
  génération cumulée sur les threads. Cause : niveau zlib 9. Les sessions ne
  sont pas comparées entre elles : chacune correspond à un exécutable différent
  (autres modules). `ppu_pipeline=0` est le réglage « PPU LLVM Pipeline » =
  `upstream` (aucune passe IR sur ARM64) et `spu_pipeline=1` le pipeline SPU
  `upstream` (avec InstCombine) : des réglages, pas des compteurs. (Le
  commentaire de `unzip.cpp` et l'enregistrement `cell546` du manifeste disent
  « inside » : lecture corrigée ici, texte corrigé dans le prochain Core.)
- **Message « GameDB publication unavailable »** : publication anticipée lors
  du scan de la bibliothèque, avant le chargement du Core ; la publication
  suivante, après initialisation, réussissait sans laisser de ligne.

## 3. Correctifs

Core (`343649293c`, run 40230183096, delta canonique `5e07bf2f…`) :

1. `zip()` écrit les objets LLVM PPU/SPU au **niveau zlib 1** sur iOS. Même
   format gzip et même lecteur : aucun cache invalidé, identités PPU/SPU
   inchangées (calculées par la vraie fonction CMake). Les sauvegardes d'état,
   les caches shader et les autres plateformes gardent les niveaux amont.
2. La trace de restauration ne s'exécute que sur le thread qui a commencé une
   restauration : un `exitspawn` écrivait une fausse restauration dont
   `elapsed_us` était l'uptime de l'appareil.

Hôte (IPA) :

3. Étapes détaillées de restauration (constructeurs, fichiers) dans
   `RPCS3-restore-trace.log` (1 Mio + `.1`), écrites dans l'ordre sans `fsync`
   (≈ 0,17 ms par ligne auparavant, ≈ 0,13 s par restauration) ; phases, limites
   et erreurs restent des jalons.
4. `RPCS3-milestones.log` tourne vers `RPCS3-milestones.1.log` au lieu d'être
   vidé ; chaque nouvelle génération commence par une ligne `LOG_ROTATION`.
5. `RPCS3-timeline.log` : une ligne JSON par fenêtre du Core (temps d'image
   p95/p99/max, shaders et pauses, attentes, JIT, mémoire, échantillons hôte,
   lignes perdues et rotations), calculée sur la file de diagnostic existante.
   ≈ 1,9 Kio par fenêtre, 2 Mio par génération : ≈ 3 h avec la précédente. Les
   familles gardent leur portée ; leurs durées ne s'additionnent pas.
6. Les lignes refusées par le budget de 128 lignes/s sont comptées
   (`LOG_BUDGET dropped=`).
7. Le journal de l'app distingue « publication reportée » et « publiée ».

## 4. Mesures (sans iPhone)

| Mesure | Résultat |
| --- | --- |
| Compression d'un échantillon de 6 665 088 octets de code ARM64 (runner macOS arm64, clang de Xcode) | niveau 9 : 565,7 ms ; niveau 1 : 128,2 ms (**4,4×**) ; +7,0 % d'octets |
| Même mesure, code x86-64 (Linux local) | 687,5 → 119,8 ms (5,7×) ; +7,7 % |
| Relecture par le lecteur de production `jit_object_buffer` | identique, niveaux 1 et 9 |
| Projection sur l'objet de 3,58 s (hypothèse : même rapport sur l'iPhone) | ≈ 0,8 s, soit ≈ 2,8 s de moins sur les ≈ 10,5 s de ce module |
| Journaliseur Foundation (macOS) | 701 jalons sur une rotation : l'enregistrement antérieur est conservé (le 545 le perd) ; 1 000 étapes de restauration sans toucher aux autres fichiers ; lignes de chronologie complètes et incomplètes |

`test/rpcs3_cell546_test.py` exécute les corps de production 546 et 545 sous
ASan+UBSan ; le contrôle 545 reproduit la ligne à l'uptime. Preuves :
`docs/evidence/rpcs3-cell546-local.json`. **Aucun test sur iPhone, aucun gain de
FPS revendiqué** : la compression ne touche que la préparation JIT, pas les
images en jeu.

## 5. Protocole de comparaison sur iPhone

Même jeu, même scène, même sauvegarde, appareil refroidi, puis exporter
`RPCS3-timeline*.log`, `RPCS3-milestones*.log` et `RPCS3-restore-trace*.log` :

1. **Cache JIT froid** (premier lancement d'un titre) : comparer
   `ppu_cache_write` et `ppu_codegen` (`JITPROF_BOOT`) avec ceux du 541.
2. **Cache chaud** : `ppu_cache_write` doit être nul ; aucun gain attendu.
3. **Shaders froids / chauds** : `shader_stall_events` et `frame_ms.max_ms`
   par fenêtre ; 546 ne les change pas.
4. **Session longue (> 30 min)** : p95/p99 par fenêtre, `host.available_min_bytes`,
   `lost.rotations`.
5. **Restauration** : durée `vm_begin` → `finalize_run_end` (jalons) avant/après.

## 6. Livraison privée 546

IPA cumulative : hôte 542 validé, correctif MeloNX de fermeture (544), Core
RPCS3 546 et ses quatre fichiers hôte. Aucune release, aucun tag, aucune fusion
vers `main`.

- Core : source `343649293c`, run 40230183096 (journaliseur Foundation, tests
  natifs 546, compilation, exports, chargement passif, identités inchangées).
  Delta canonique SHA-256 `5e07bf2f…a24d1`.
- IPA : source `6c6c6241`, run 40231210331. Le journaliseur modifié a été
  réexécuté par la livraison (536 : 545 → −6, 546 → 0 ; 546 : contrôle 545 → −6,
  546 → 0) et lié au validateur `validate_rpcs3_546_ipa.py`.
- Fichier remis : `RewindBox-Build546.ipa`, version 0.0.8 (546), iOS 18
  minimum, **186 395 032 octets**, SHA-256
  `4ae646904b20b0ff76d6d6667ec3df77622b248d20d7a602ef9bbf249e942742`, égal à
  `SHA256SUMS` et à `signed-payload-identity.json` ; 87 signatures. Artefact
  chiffré `12613457207` pour `build-utils/delivery-546-recipient.pem` (clé
  privée hors Git), conservé jusqu'au 8 novembre 2026. Déchiffré et revérifié :
  marqueurs du Core et du pont (`RPCS3-restore-trace.log`, `RPCS3-timeline.log`,
  `LOG_BUDGET`, `LOG_ROTATION`) ; `validate_rpcs3_diag487_ipa.py` rejoué
  localement.
- S'installe par-dessus la 545 (même identifiant, numéro supérieur), après
  re-signature SideStore. Aucune validation sur iPhone. Ne pas réutiliser le
  numéro 546. Preuve : `docs/evidence/rpcs3-cell546-delivery.json`.
