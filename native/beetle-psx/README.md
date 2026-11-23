# Beetle PSX (10e4b0c6) : Lightrec avec l'interface JIT de RewindBox

Correctif `lightrec-jit-abi.patch` (17 fichiers, +534/−108), un `git diff` contre
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
| GNU Lightning (7 fichiers) | +70/−11 | `jit_set_code_exec(offset)` : le code écrit à `ptr` s'exécute à `ptr + offset`. Champ `code.exec` dans `jit_state`. aarch64 : `jmpi`/`calli` absolus convertis, repli MOVZ/MOVK + BR/BLR vers la cible absolue d'exécution, `movi` d'étiquette définie et branche MOVZ de `_patch_at` (+offset), `jit_address()` rend l'adresse d'exécution, pas de `__clear_cache` côté RW quand l'offset ≠ 0. `HAVE_MMAP 0` sous `REWINDBOX_LIBRETRO_JIT` (Lightning ne mappe plus rien) ; `jit_emit()` sans mmap rend `NULL` au lieu de boucler sans fin quand le tampon est trop petit. Offset ≠ 0 refusé hors aarch64. Apple : `jit_flush()` appelle `sys_icache_invalidate()` (le SDK iOS et Xcode n'ont pas de `__clear_cache` : édition de liens échouée au run 45191228672). |
| Lightrec (5 fichiers) | +174/−64 | `lightrec_set_code_exec_offset()` avant `lightrec_init()`. Les allocateurs (TLSF, arènes des workers) ne voient que les adresses RW ; `block->function`, LUT, `c_wrapper`, entrées du dispatcher et points d'entrée internes sont en RX ; RX → RW avant chaque libération. `with_32bit_lut` calculé sur RX. `code_inv` obligatoire avec un offset. Sans tampon de code, plus aucune émission. `isb` après l'installation des résultats des workers (recompiler.c). Code auto-modifiant : voir « Défaut amont corrigé » (`emitter.c`, `lightrec.c`, `lightrec-private.h`, +89/−59). |
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
  17 empreintes d'origine, correctif et en-tête vérifiés).
- **iOS compilé et lié** (clang 18, SDK iPhoneOS 16.5 de theos/sdks, ld64.lld, iOS 14.0, sans aucun stub) :
  `mednafen_psx_hw_libretro_ios.dylib` et `mednafen_psx_libretro_ios.dylib`, dépendances libSystem/libc++/OpenGLES,
  `_rewindbox_libretro_jit_install` et les 25 `_retro_*` exportés ; `nm -u` : pas de `___clear_cache` (aucun objet ne
  le référence), `_sys_icache_invalidate` importé ; aucun import `vm_protect`/`mach_vm_protect`/
  `pthread_jit_write_protect_np`, ni `mmap`/`mprotect` dans Lightning/Lightrec. Chemin Mach VM compilé, pas exécuté.
- **Lightning seul sous qemu-aarch64** : memfd vu deux fois (RW sans X, RX sans W, offset 512 MiB) ; appel proche
  (BL) vers une fonction émise, appel lointain C (MOVZ/MOVK + BLR), sauts `jmpi` + `jit_patch_abs` proche (B) et
  lointain (> 128 MiB, MOVZ/MOVK + BR), `movi` d'étiquette avant/arrière, réécriture au même endroit, `jit_emit()` sur
  tampon trop petit → `NULL` ; avec et sans assertions.
- **Cœur SW complet (aarch64 Linux) sous qemu**, frontend minimal implémentant l'ABI (16 KiB, capacité fixe, deux
  vues), `mmap`/`mprotect` interceptés : ROM de test + PS-EXE (CRC, récursion, tables de saut, pointeurs de
  fonction, mult/div, accès non alignés, scratchpad, GTE, syscalls, 1 536 fonctions générées) et OpenBIOS intégré.
  Avec `execute` : une seule allocation, tous les `flush` dans le bloc RX, aucun mappage exécutable ; qemu a traduit
  352 264 blocs dans la vue RX et 0 dans la vue RW ; version instrumentée (test seulement) : jusqu'à 1 035 865
  pointeurs (LUT, fonctions émises, entrées du dispatcher, points d'entrée internes) tous dans RX. Résultats de la ROM
  et de l'EXE égaux à ceux de l'interpréteur Beetle, code auto-modifiant compris ; OpenBIOS démarre (après
  300 trames, 49 mots de RAM sur 524 288 diffèrent : données et pile qui dépendent du minutage, que le dynarec compte
  autrement). Aussi : tampon 256 KiB (vidages et réemploi,
  multi-thread et mono-thread), second chargement dans la même ouverture, bascule à chaud, 22 aller-retours de
  sauvegarde d'état, sans ABI ou arène trop petite (aucun code émis), faute Lightrec (le cœur non corrigé quitte par
  `exit(1)`, le cœur corrigé passe à l'interpréteur).

## Défaut amont corrigé : code auto-modifiant

**Symptôme.** En `execute`, une boucle en RAM qui réécrit une fonction déjà compilée puis l'appelle (ici
`0xA0030000`) perd son compteur au second passage : elle ne s'arrête plus, les mots stockés débordent en code
invalide, puis le processeur part à l'adresse 0. D'autres cas (deux pages réécrites dans un même bloc, mot intérieur
d'une fonction, recopie d'un overlay) faisaient planter l'hôte : SIGSEGV en invalidation `full`, SIGILL dans le
tampon de code en `dma`. Pas de correctif ailleurs : Lightrec amont (`6dff9c7`) et pcsx_rearmed n'ont pas ce
mécanisme, ajouté dans Beetle en juin 2026, et Beetle `master` n'a rien changé à `deps/lightrec` depuis `10e4b0c6`.

**Cause.** Le contrôle des écritures dans du code en cache (`rec_store_invalidate_blocks`, émis pour tout stockage
RAM hors créneau de retard, en `full` comme en `dma`) quittait le bloc **avant** le stockage et reprenait à ce
stockage dans un autre bloc, compilé depuis la RAM. Ce bloc relit tous les registres MIPS dans l'état de Lightrec ;
or l'optimiseur n'y garantit des valeurs à jour qu'aux points de synchronisation (branches, fin de bloc). Ici,
`move s1, zero` avait été marqué « discard » (écriture jamais rangée) parce que la propagation de constantes avait
réécrit ses lectures (`move a0, s1` → `move a0, zero`) : la reprise lisait l'ancien `s1` (`0xA0040000`). Les `lui`
différés (`movi`), les fusions `sll`/`sra` et d'autres transformations ont le même défaut. Toutes les combinaisons
étaient touchées : invalidation `full` et `dma`, recompilateur multi-thread ou non, aarch64 et x86-64, avec ou sans
la séparation RW/RX.

**Correction** (`emitter.c`, `lightrec.c`, `lightrec-private.h`). Le chemin froid ne quitte plus le bloc : il note
la plage écrite (`code_inv_lo`/`code_inv_hi`), lève `LIGHTREC_EXIT_CODE_INV` et met le budget de cycles à zéro,
comme `lightrec_set_exit_flags()`. Le stockage et la fin du bloc s'exécutent, puis le premier contrôle de cycles
(fin de bloc ou boucle locale) rend la main à `lightrec_execute()`, qui revalide les blocs de la plage avant d'en
lancer un autre. Les registres sont alors synchronisés. `rec_exit_early()` et `RFE` font `|=` sur `exit_flags` au
lieu de `=`, pour ne pas effacer une demande en attente ; `lightrec_execute()` traite chaque drapeau et rend les
autres à Beetle.

**Vérifié.** En x86-64 natif (multi-thread et mono-thread, `full` et `dma`) et sous qemu-aarch64 avec la séparation
RW/RX (cœurs instrumentés, tampon 256 KiB) : le test d'origine et quatre nouveaux cas (deux pages, mot intérieur,
overlay recopié, stockage + `syscall` dans le même bloc) donnent exactement les mots de l'interpréteur Beetle ; le
cœur non corrigé reste bloqué ou plante sur les mêmes binaires.

**Limites.** La sortie lente `$sp`/`$gp` (`LIGHTREC_EXIT_SPGP_SLOW`, seulement avec l'option « Dynarec SP GP Hit
RAM Optimization », désactivée par défaut) reprend toujours dans un autre bloc : même risque, non corrigé.
Les stockages placés dans un créneau de retard ne sont toujours pas contrôlés (seule l'entrée du mot écrit est
invalidée), comme avant.

## Triches : du code compilé réécrit par une triche

**Symptôme.** Une triche GameShark (menu de triches libretro, `retro_cheat_set`) qui réécrit une instruction déjà
compilée par Lightrec n'avait aucun effet : le bloc compilé gardait l'ancienne instruction. Les triches sur les
données (vies, argent) n'étaient pas touchées.

**Cause.** `MDFNMP_ApplyPeriodicCheats` écrit à chaque trame par `PSX_MemPoke8` → `MemPoke` → `MASMEM_WriteU8`,
hors des stockages du processeur : Lightrec n'en voyait aucun (même défaut dans Beetle amont).

**Correctif** (`libretro.c`, `PSX_MemPoke8`, sous `HAVE_LIGHTREC`). Quand le dynarec est actif et qu'un octet de la
RAM principale change réellement, `CPU_LightrecClear(mot, 1)` invalide le mot qui le contient (et tout bloc qui le
recouvre) : Lightrec recompile ce code et continue. Une triche ne fait jamais passer le jeu à l'interpréteur ; un
octet déjà à la bonne valeur ne coûte rien. `retro_cheat_reset` ne remet aucun octet (il vide seulement la liste) :
rien à invalider.

**Vérifié hors appareil** (qemu-aarch64, cœur SW aarch64 Linux, frontend du banc avec l'ABI, 80 trames, triche
posée avant la trame 31) : une fonction en RAM, compilée, renvoie 1 ; la triche `80040000 0002` remplace son
immédiat par 2.

| Cœur | `execute` (Lightrec) | `disabled` (interpréteur) |
| --- | --- | --- |
| Correctif précédent (`d630c132…`) | 1 jusqu'au bout : triche sans effet | 2 dès la trame 31 |
| Ce correctif | 2 dès la trame 31, Lightrec reste actif | 2 dès la trame 31 |

Aucun retour à l'interpréteur, aucun mauvais `flush` ; un `flush` de plus (le bloc recompilé).

## Non vérifié

- Rien n'a tourné sur iPhone : arène réelle, `sys_icache_invalidate`, `isb`, vues Mach VM (adresses accordées par
  iOS, contrôle d'alias), performances, jeux commerciaux, rendu HW avec le dynarec.
- Compilation Xcode : le job `source-cores` (run 45191228672) échouait sur `___clear_cache`, corrigé ici, pas relancé
  (localement, clang 18 + SDK 16.5, iOS 14.0, sans stub).
- `libretro-common/memmap.c` importe toujours `mprotect` (RW/NONE pour `data_transfer`, inchangé) ; sa fonction RWX
  `memprotect` n'a aucun appelant.
