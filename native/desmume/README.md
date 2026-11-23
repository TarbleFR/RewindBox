# DeSmuME (95b4d798) : JIT AArch64 avec l'interface JIT de RewindBox

Cœur libretro [libretro/desmume@95b4d798](https://github.com/libretro/desmume/tree/95b4d798731caa809125b6c3c11d17cc332ff6ef)
(tête de `master`, la révision des binaires buildbot livrés jusqu'ici), complété par le JIT AArch64 de l'équipe
DeSmuME, que le fork libretro n'a jamais importé, puis corrigé et branché sur
`packages/libretro_internal_bridge/ios/Classes/RewindBoxLibretroJit.h`. Conception et suites prévues :
[docs/desmume-arm64-jit-architecture.md](../../docs/desmume-arm64-jit-architecture.md) (étape 0).

## Ce que la compilation assemble

1. **Fichiers importés** (`importFiles` de `source.json`) : `desmume/src/utils/arm_jit/arm_jit_arm.cpp`,
   `emit_core.cpp` et `arm64_emit.cpp` de
   [TASEmulators/desmume@b549f71b](https://github.com/TASEmulators/desmume/tree/b549f71b83287f265b6d74b9e77ef5d98a617190),
   pris à cette révision et vérifiés par SHA-256. `arm_emit.cpp` (ARM 32 bits) n'est pas pris.
2. **Correctif** `arm64-jit-abi.patch` (11 fichiers, +310/−142), un `git diff` contre l'arbre libretro plus ces trois
   fichiers d'origine.
3. **En-tête ABI** hors du correctif, copié par la compilation dans
   `desmume/src/frontend/libretro/rewindbox/RewindBoxLibretroJit.h`.

## Ce que change le correctif

| Partie | Changement |
|---|---|
| Mémoire du code (`emit_core.cpp`) | Plus de `mmap` RWX `MAP_JIT`, de `munmap`, de `pthread_jit_write_protect_np`, de `sys_icache_invalidate` ni d'`exit(0)`. Une seule arène, reçue du frontend (`arm_jit_set_code_arena`) : chaque bloc est copié par la vue RW, `flush(rx, n)`, puis exécuté à RX. Allocation alignée sur 16 octets. Arène pleine : `arm_jit_reset` vide les tables et rembobine l'arène, comme le JIT d'origine changeait de zone (sûr : les blocs ne sont pas chaînés et ne se compilent que depuis le distributeur C). Échec de `malloc` : bloc abandonné à l'interpréteur, sans `exit`. |
| Frontend (`libretro.cpp`) | `rewindbox_libretro_jit_install()` exporté : vérifie version, `structBytes`, pointeurs et page, puis prend toute l'arène préparée (au moins 4 Mio), une fois par ouverture. Le JIT ne tourne que si `desmume_cpu_mode` vaut `jit`, que l'interface est installée et que l'hôte répond oui à `RETRO_ENVIRONMENT_GET_JIT_CAPABLE` ; sinon l'interpréteur, quoi que dise l'option. Journal `[rb-jit] desmume installed=… arena=… page=… wanted=… jit=…` au démarrage, puis `blocks used capacity flushes interpreted failures` toutes les 30 s de jeu et au déchargement. |
| Makefiles | `make DESMUME_JIT_A64=1` : `-DHAVE_JIT -DREWINDBOX_LIBRETRO_JIT` et `utils/arm_jit/arm_jit_arm.cpp` à la place du JIT x86. `IOSMINVER` (8.0 par défaut, 14.0 pour RewindBox) remplace la version iOS codée en dur. |
| Compatibilité du fork | `DESMUME_FASTCALL` → `FASTCALL` ; `cp15.setSingleRegionAccess` (méthode dans le fork libretro). |
| TASEmulators/desmume#1002 | UMLAL et UMLALS émis en SMADDL (signé) : UMADDL. SMLAWT identique à SMLAWB : demi-mot haut (`SBFX #16, #16`). Retenue d'`ASR #32` (encodé `#0`) : bit 31, en Thumb **et en ARM** (opérations de données avec S, absent du ticket). Interpréteur : NEG Thumb de `0x80000000` calculé en non signé (débordement signé indéfini). |
| TASEmulators/desmume#998 | Instruction conditionnelle exécutée, de n cycles fixes : n au lieu de 0. Écriture de r15 par une opération de données : +2 cycles comptés deux fois (`instr_cycles` et le gestionnaire), une seule fois désormais. |
| TASEmulators/desmume#997 | Un DMA armé par une écriture (`DmaController::write32`) lève `mmu_dma_event_pending`, remis à zéro après `sequencer.execHardware()`. Après chaque instruction d'écriture (STR, STRB, STRH, STRD, STM, SWP ; Thumb STR, STRB, STRH, PUSH, STMIA), le bloc teste l'indicateur et sort, état synchronisé (`instruct_adr`, `next_instruction`, cycles). La première exécution d'un bloc, interprétée pendant sa compilation, s'arrête aussi là. |

## Vérification hors appareil

Banc manuel, non livré et non automatisé (AGENTS.md) :
- cœur compilé pour Linux AArch64 (mêmes options qu'iOS, `__IOS__` compris) ;
- frontend libretro minimal sous qemu-aarch64, avec une arène memfd vue deux fois : RW, puis RX ;
- ROM DS de test écrite pour l'occasion (clang `armv5te`, en-tête NDS minimal).

La ROM couvre :
- calculs ARM et Thumb ;
- multiplications longues et DSP ;
- drapeaux des décaleurs ARM et Thumb ;
- LDM/STM ;
- code automodifiant ;
- le scénario DMA du #997 ;
- 2 500 fonctions distinctes.

Résultats, comparés à l'interpréteur :

| Configuration | Résultat |
|---|---|
| Avant les correctifs | 249 relevés sur 4 380 diffèrent : UMLAL, UMLALS, SMLAWT, `EORS … ASR #32`, `ASRS #32` Thumb, et le DMA à blocs de 100 |
| Après, blocs de 1, 12 et 100 | 4 396 relevés sur 4 396 identiques, 9 tests sur 9 |
| Arène de 4 Mio, blocs de 1 | 3 rembobinages, 61 613 blocs, résultats identiques |
| Sans interface, ou hôte sans capacité JIT | Interpréteur |

Le binaire iOS n'a pas tourné sur iPhone : à mesurer avec les lignes `[rb-jit]`.

## Limites connues

- **Cycles.** Le décompte reste celui du JIT d'origine, en dehors des deux corrections : temps de fetch
  approximé. Le ticket #1002 relève des milliers d'écarts de cycles sans effet sur l'état. Le temps
  émulé peut donc différer un peu de l'interpréteur.
- **Code modifié dans le bloc en cours.** Une écriture sur une instruction plus loin dans le bloc en cours
  d'exécution ne l'invalide qu'à la sortie du bloc, comme dans le JIT x86 d'origine. Le repli après huit
  recompilations d'une même adresse est conservé.
- **Instructions non compilées.** QADD, QSUB, QDADD, QDSUB et BKPT passent par l'interpréteur.
- **Mémoire.** Les tables `JIT_struct` occupent environ 68 Mio de BSS, sales seulement là où du code a été compilé.

## Licences

- Fichiers DeSmuME et JIT AArch64 : GPLv2 ou ultérieure.
- `arm_jit.h` : GPLv3 ou ultérieure.
- En-tête ABI : MIT.

Le binaire avec `HAVE_JIT` est donc distribué sous GPLv3. `libretro_source_cores.py` réécrit la ligne du cœur
dans `LIBRETRO_CORES.txt` et l'identité porte `GPLv3`.

## Compilation (macOS, Xcode)

```sh
# arbre libretro/desmume à 95b4d798, plus les trois fichiers de TASEmulators/desmume à b549f71b
git apply native/desmume/arm64-jit-abi.patch
mkdir -p desmume/src/frontend/libretro/rewindbox
cp …/RewindBoxLibretroJit.h desmume/src/frontend/libretro/rewindbox/
cd desmume/src/frontend/libretro
SOURCE_DATE_EPOCH=1795306701 make -f Makefile.libretro platform=ios-arm64 DESMUME_JIT_A64=1 IOSMINVER=14.0
strip -x desmume_libretro_ios.dylib
```

`build-utils/libretro_source_cores.py --cores …,desmume` fait la même chose et vérifie chaque empreinte, les
exports et les imports interdits. Il installe le binaire dans la collection avec `jitInterface: 1` et
`jitArenaBytes` (32 Mio).
