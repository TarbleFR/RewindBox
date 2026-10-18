# Direct per-game cheats — Build 475 candidate

The maintainer reports no RPCS3 codes for God of War III and Bladestorm: The Hundred Years' War, PS2 lists dominated by widescreen patches, and limited arcade results. The requested flow is a detected game's named switches, plus one full-catalogue download and an import action. All new imports start disabled.

The shared native list now serves ARMSX2, Dolphin and RPCS3. It reads installed, compatible programs and their complete dependency closures without an import/browser step. The first explicit activation imports only that complete program and targets the exact native item returned after collision resolution. A missing edition proof requires one confirmation for the detected edition; known contradictions remain rejected. A popped or dismissed page cannot activate a code from a late callback. Libretro retains its existing direct switches with the same two catalogue/import actions.

PS2 graphical/compatibility entries are under Graphics → Patches. Gameplay entries are in the direct Cheats list. The PNACH importer now reads explicit executable CRC and disc serial tokens from the source's filename/gametitle. Repeated native headers with the same name retain all their ordered lines as one switch. Cross-group conditions and unproved pointer/copy/slide control flow are withheld, rather than turned into unrelated switches or an all-cheats bundle. The active PS2 publication has **12,609 programs**, compared with 816 in Build 474.

Arcade startup resolves the running FBNeo driver's exact exported name and stages its installed native INI before the first cheat-option declaration. Native defaults and the master remain disabled. No parent/clone or MAME-address substitution is used. Downloading while an arcade game is already running still requires reopening that game to declare newly installed native options.

## Added sources and reviewed adaptations

The original [70-source inventory and fourteen complements](unified-cheats-sources.md) remains the baseline. This update adds one independent source and two narrow adaptations of already inventoried sources:

| Input | Pin and scope | Result |
|---|---|---|
| [Luckysugar GoW3 patches](https://github.com/Luckisugar/rpcs3-gow3-patches/tree/d8437d9d4a1fd10ab2b820e6acc6aaf94c7dc665) | MIT; APP_VER 01.00, PPU `4d5c51503a81a327c2a99427390a395b8dcb3767`; BCES00510, BCES00799, BCUS98111 and BCJS37001 explicitly listed by the author | Eight complete programs per authored serial, 32 edition records; damage multipliers remain exclusive. Full MIT notice retained in the catalogue and app resource bundle. |
| [Artemis Bladestorm NCL](https://github.com/bucanero/ArtemisPS3/tree/d79b41e525e20251bd0d919100039ac0a6433956/docs/codes) | `Bladestorm The Hundred Years' War BLES00113 BLUS30070 01.00.ncl`; CodeFreak/PS3UserCheat; four type-0, 32-bit instruction writes | Money, AP, Exp and Combo for the two source serials, 01.00. The adapter preserves the exact words as `be32`; it requires the currently observed executable hash and confirmed candidate edition. No general NCL pointers, freezes or repeated-memory interpreter is claimed. |
| [Artemis GoW3 native patch collection](https://github.com/chidreams/Artemis-Patch-Collection-RPCS3/tree/21fc0ee86578f1452e42da01187eb852ab034b28) | Original BCUS98111 01.03 instruction programs; same PPU `19724fde16a5b111b7b4d2a065f5dccaf8e01962`; serial list bounded by the retained Core's explicit GoW3 same-PPU gate | 19 instruction programs for each of BCES00510, BCES00799, BCJS37001, BCAS25003 and BCKS15003. This is a hash-gated compatibility adaptation, not an assertion that every regional disc has that executable. A differing observed PPU is rejected. The author's explicitly “not working” program is excluded from these ports. |

RPCS3's retained `PPUModule.cpp` at `XITRIX/rpcs3@22f1152783cef1f7e04af7b1c895173e28fd5b03` emits `PPU executable hash:` from `ppu_load_exec`; PRX messages are distinct. The host captures that exact bounded message before its ordinary log budget, resets it at every boot, and rejects conflicting observations. It supplies the actual typed PPU identity to matching and staging. A static Bladestorm source never receives an invented source hash: the original serial/version remains intact and the observed target PPU is recorded separately.

The existing Core patch API remains stopped/next-boot only. RPCS3 switches set the requested state for the next game launch; they do not patch live JIT code. ARMSX2 and Dolphin use their existing native selection APIs. Enabling a switch while their old global master is off first clears dormant selections, so it cannot wake another code shown as off.

Manual formats: Libretro CHT, FBNeo native INI named for the actual driver, PS2 PNACH, Dolphin's existing INI/TXT/GCT editor, and a standard RPCS3 patch document encoded as YAML-compatible JSON. A raw NCL/YAML file is not silently renamed into another dialect.

## Frozen publication

- 2,353,283 complete programs/variants in typed edition groups; this is not a count of distinct gameplay effects.
- 44,789 transport parts, 43,647 identity groups, 858 packs; 37 active source/provenance producers, including the two adaptations above.
- Revision `c7f13fe845981a4fa56fa4bdd28ae03873fdc1670fee19c2307b91e16e586b82`.
- Manifest gzip SHA-256 `ff64b3b92225f5ab6960e1931fadaf4509665864a4470fb36908cc2faf22d792`.
- 424 changed chunks, 44,365 byte-identical retained chunks. All 851 prior immutable packs are reused; seven new packs carry replacements/additions. The 590 superseded members are explicitly retired, size/hash checked, excluded from the active index and never offered by the direct list. They are not counted as usable cheats.
- Pack download: 276,552,040 bytes, plus the index. No full packs are embedded in the IPA.
- The full active-pack audit passes with zero anomalies. `native/cheats/catalogue/VALIDATION.json` SHA-256: `032950997212a242fb584db4f6de72dc562522c532c8ad9336f79b2d04b4b93f`.

Reproduce the normalized build with the pinned source lock, then preserve the immutable transport baseline:

```sh
python3 tools/cheats/unified_stable_packs.py --directory native/cheats/catalogue \
  --base 4538c007c7fd66e48f423748c1ad0df4f86027b1 \
  --bundle packages/neo_cheat_catalog/ios/Resources/manifest.json.gz
python3 tools/cheats/unified_catalogue.py validate --input native/cheats/catalogue
```

## Validation provenance

`c3e690914b5103d19d9a2ab0dcc611f4b2498991`, run `39100149182`, compiled the shared pod, seven native files and complete Libretro bridge with the real iPhone SDK. Foundation identities, Host routing and native disabled stores passed. Its UIKit run executed 34 tests: 31 passed, three failed (four assertions). The late-pop activation guard was a product defect and was corrected. The two restore tests still expected a removed navigation row; they now exercise the retained production restore guard directly, retaining all atomicity/exclusivity assertions.

`b157f557fe13b077d92afdd4ef1146c60982235d`, run `39100669248`, validates the final three-engine adapters, RPCS3 runtime-binding store, exact PPU log parser, added boot-time Foundation cases, and the targeted UIKit corrections. The final edition-confirmation/UI and published-data gates are recorded by the delivery evidence reader once complete.

No emulator Core, JIT helper, NeoSwap implementation, library, firmware or user save is rebuilt or replaced for these changes. The actual IPA will be inspected for its final bundled index, new direct-list class, native PPU binding, all retained payload identities and versions. Native/Simulator checks do not constitute physical iPhone gameplay verification.
