# Beetle PSX (10e4b0c6) : Lightrec avec l'interface JIT de RewindBox

Correctif `lightrec-jit-abi.patch` (16 fichiers, +421/−49), un `git diff` contre
[libretro/beetle-psx-libretro@10e4b0c6](https://github.com/libretro/beetle-psx-libretro/tree/10e4b0c6ceae20daa65ddf436a4445dddd0982d2).
Il active le dynarec Lightrec pour `platform=ios-arm64`, cœurs `mednafen_psx_hw` et `mednafen_psx`, sous le contrat
de `packages/libretro_internal_bridge/ios/Classes/RewindBoxLibretroJit.h` : code écrit seulement par la vue RW,
exécuté seulement à RX, `flush(rx, n)` après écriture, jamais de RWX, jamais de `mprotect` ni de mappage
exécutable par le cœur. Sans interface installée, aucun code n'est généré.

- **En-tête ABI** : hors du correctif, copié par la compilation dans `rewindbox/RewindBoxLibretroJit.h` (racine du
  cœur), inclus par `libretro.c`. Empreintes, compilation et exports : `source.json`.
- **Licences** : fichiers Beetle/Mednafen GPLv2 ou ultérieure (en-têtes « version 2 … or any later »), Lightrec
  LGPL-2.1-or-later (SPDX), GNU Lightning LGPL-3.0-or-later, en-tête ABI MIT. Avec Lightning, le binaire est
  distribué sous GPLv3 ; `libretro_source_cores.py` copie `deps/lightrec/COPYING`, `deps/lightning/COPYING.LESSER`
  et `deps/lightning/COPYING` dans `Libretro-Licenses/` et réécrit la ligne du cœur dans `LIBRETRO_CORES.txt`.

## Ce que change le correctif, et pourquoi

| Partie | Lignes | Changement |
|---|---|---|
| GNU Lightning (7 fichiers) | +59/−11 | `jit_set_code_exec(offset)` : le code écrit à `ptr` s'exécute à `ptr + offset`. Champ `code.exec` dans `jit_state`. aarch64 : `jmpi`/`calli` absolus convertis, repli MOVZ/MOVK + BR/BLR vers la cible absolue d'exécution, `movi` d'étiquette définie et branche MOVZ de `_patch_at` (+offset), `jit_address()` rend l'adresse d'exécution, pas de `__clear_cache` côté RW quand l'offset ≠ 0. `HAVE_MMAP 0` sous `REWINDBOX_LIBRETRO_JIT` (Lightning ne mappe plus rien) ; `jit_emit()` sans mmap rend `NULL` au lieu de boucler sans fin quand le tampon est trop petit. Offset ≠ 0 refusé hors aarch64. |
| Lightrec (4 fichiers) | +85/−5 | `lightrec_set_code_exec_offset()` avant `lightrec_init()`. Les allocateurs (TLSF, arènes des workers) ne voient que les adresses RW ; `block->function`, LUT, `c_wrapper`, entrées du dispatcher et points d'entrée internes sont en RX ; RX → RW avant chaque libération. `with_32bit_lut` calculé sur RX. `code_inv` obligatoire avec un offset. Sans tampon de code, plus aucune émission. `isb` après l'installation des résultats des workers (recompiler.c). |
| Glue Beetle (`libretro.c`, `cpu.c`, `cpu.h`, `Makefile`) | +263/−18 | `rewindbox_libretro_jit_install()` (exporté) : vérifie version/`structBytes`/pointeurs/page, prend **une seule fois par ouverture** 16 MiB (`LIGHTREC_CODEBUFFER_SIZE`), refuse sinon (valeur ≠ 0, aucune allocation). Le tampon ne fait plus partie de la réservation PSX et n'est jamais mappé ni libéré par le cœur ; il survit aux `retro_unload_game`. `code_inv` → `flush(rx, n)` de l'hôte. Sans interface : `beetle_psx(_hw)_cpu_dynarec` forcé à `disabled` (aussi pour `run_interpreter`, qui émet le dispatcher). Échec de `lightrec_init()`, `EXIT_NOMEM` ou `EXIT_SEGFAULT` : bascule vers l'interpréteur Beetle pour la suite du jeu au lieu de `exit(1)` ; la trame en cours est finie par l'interpréteur. `CPU_AssertIRQ` protégé (`lightrec_regs` nul). `lightrec_map` remis à zéro (miroirs, tampon) entre deux jeux. iOS : vues RAM par Mach VM (`vm_allocate` 2 MiB puis quatre `vm_remap` copy = FALSE, `VM_FLAGS_FIXED | VM_FLAGS_OVERWRITE` dans la réservation, contrôle d'alias), sans `shm_open` ; échec → repli sans miroirs (code plus lent, correct). Makefile iOS : `HAVE_LIGHTREC=1` en ligne de commande ajoute `-DREWINDBOX_LIBRETRO_JIT -DLIGHTREC_CODEBUFFER_SIZE=16777216`. Les autres plateformes gardent leur disposition mémoire. |
| Cherry-pick `ed9dabc6` (master, 18 nov. 2026) | +14/−15 | `cpu.c` + `gte.c` seulement : `lightrec_plugin_shutdown` rend le banc GTE et remet `lightrec_state`/`lightrec_regs` à `NULL` (double destruction au second chargement). |

## Compilation (macOS, Xcode)

```sh
git apply native/beetle-psx/lightrec-jit-abi.patch
mkdir -p rewindbox && cp …/RewindBoxLibretroJit.h rewindbox/
make -j"$(sysctl -n hw.ncpu)" platform=ios-arm64 HAVE_HW=1 HAVE_LIGHTREC=1 THREADED_RECOMPILER=1 LIGHTREC_CODEBUFFER_SIZE=16777216
make clean
make -j"$(sysctl -n hw.ncpu)" platform=ios-arm64 HAVE_LIGHTREC=1 THREADED_RECOMPILER=1 LIGHTREC_CODEBUFFER_SIZE=16777216
```

Dans RewindBox, `build-utils/libretro_source_cores.py` lit la liste `cores` de `source.json` : chaque cœur est
compilé dans son propre arbre (pas de `make clean`), avec `IPHONEMINVER=-miphoneos-version-min=14.0` comme Azahar
(le Makefile vise 8.0 par défaut). L'application ne prépare l'arène (16 Mio) que pour un cœur dont l'identité
embarquée porte `jitInterface: 1` ; `cpu_dynarec` vaut `disabled` sans JIT et `execute` quand l'installation a
réussi (`noJitOverrides`/`jitOverrides` du catalogue, livrés avec l'adoption).

## Vérifié localement (Linux x86-64, jamais sur iPhone)

- **Application** : le correctif s'applique proprement sur une récupération fraîche de `10e4b0c6` (flux du pin :
  16 empreintes d'origine, correctif et en-tête vérifiés).
- **iOS compilé et lié** (clang 18, SDK iPhoneOS 16.5 de theos/sdks, ld64.lld, `__clear_cache` fourni par un stub
  local faute de compiler-rt Darwin) : `mednafen_psx_hw_libretro_ios.dylib` et `mednafen_psx_libretro_ios.dylib`,
  dépendances libSystem/libc++/OpenGLES, `_rewindbox_libretro_jit_install` et les 25 `_retro_*` exportés, aucun
  import `vm_protect`/`mach_vm_protect`/`pthread_jit_write_protect_np`, ni `mmap`/`mprotect` dans Lightning/Lightrec.
  Chemin Mach VM compilé, pas exécuté.
- **Lightning seul sous qemu-aarch64** : memfd vu deux fois (RW sans X, RX sans W, offset 512 MiB) ; appel proche
  (BL) vers une fonction émise, appel lointain C (MOVZ/MOVK + BLR), sauts `jmpi` + `jit_patch_abs` proche (B) et
  lointain (> 128 MiB, MOVZ/MOVK + BR), `movi` d'étiquette avant/arrière, réécriture au même endroit, `jit_emit()` sur
  tampon trop petit → `NULL` ; avec et sans assertions.
- **Cœur SW complet (aarch64 Linux) sous qemu**, frontend minimal implémentant l'ABI (16 KiB, capacité fixe, deux
  vues), `mmap`/`mprotect` interceptés : ROM de test + PS-EXE (CRC, récursion, tables de saut, pointeurs de
  fonction, mult/div, accès non alignés, scratchpad, GTE, syscalls, 1 536 fonctions générées) et OpenBIOS intégré.
  Avec `execute` : une seule allocation, tous les `flush` dans le bloc RX, aucun mappage exécutable ; qemu a traduit
  229 960 blocs dans la vue RX et 0 dans la vue RW ; version instrumentée (test seulement) : jusqu'à 484 325
  pointeurs (LUT, fonctions émises, entrées du dispatcher, points d'entrée internes) tous dans RX. Résultats de la ROM
  et de l'EXE égaux à ceux de l'interpréteur Beetle, hormis le défaut amont ci-dessous ; OpenBIOS démarre (après
  300 trames, 49 mots de RAM sur 524 288 diffèrent : données et pile qui dépendent du minutage, que le dynarec compte
  autrement). Aussi : tampon 256 KiB (vidages et réemploi,
  multi-thread et mono-thread), second chargement dans la même ouverture, bascule à chaud, 22 aller-retours de
  sauvegarde d'état, sans ABI ou arène trop petite (aucun code émis), faute Lightrec (le cœur non corrigé quitte par
  `exit(1)`, le cœur corrigé passe à l'interpréteur).

## Défaut amont trouvé (non corrigé ici)

Lightrec à `10e4b0c6` exécute mal une boucle en RAM qui réécrit une fonction déjà compilée (adresse non cachée
`0xA0030000`) puis l'appelle aussitôt : valeurs stockées fausses, puis boucle bloquée. Identique sans le correctif,
en aarch64 sous qemu comme en x86-64 natif ; l'interpréteur Beetle et celui de Lightrec sont justes. Les jeux à code
auto-modifiant peuvent donc mal tourner en `execute`.

## Non vérifié

- Rien n'a tourné sur iPhone : arène réelle, `sys_icache_invalidate`, `isb`, vues Mach VM (adresses accordées par
  iOS, contrôle d'alias), performances, jeux commerciaux, rendu HW avec le dynarec.
- Compilation Xcode : demandée au job `source-cores` (localement, seulement clang 18 + SDK 16.5, validé à iOS 12.0).
- `libretro-common/memmap.c` importe toujours `mprotect` (RW/NONE pour `data_transfer`, inchangé) ; sa fonction RWX
  `memprotect` n'a aucun appelant.
