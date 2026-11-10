# History purge simulation — 28 October 2026

This is a simulation only. **No force-push, ref deletion or rewrite was done
on GitHub.** The data is in
[history-purge-simulation-2026-10-28.json](history-purge-simulation-2026-10-28.json).

## Input

- **Mirror.** `git clone --mirror` of `TarbleFR/RewindBox`: 391 MiB, 5,130
  commits, 12 branches, 15 tags and 143 `refs/pull/*`. The 3 local commits of
  28 October were added as the `Claude` tip (`053dbd17`), so the simulation
  starts from the state after the catalogue withdrawals are pushed.
- **Objects to strip: 161 blobs.** None of them is in the tip of `Claude`
  after the push.

| Kind | Blobs | Content |
| --- | ---: | --- |
| Enhancements shards | 128 | MeloNX and ARMSX2 shards of `b451b10` and `1c1d1f7`, with the bodies of the unlicensed Switch and PS2 sources. The RPCS3 and Dolphin shards are licensed and kept |
| Unified catalogue packs | 30 | The 2 Pokémon France packs, the 14 packs of the first 478 layout (`88cf552f`) and the 14 packs replaced today (`940afd39` layout) |
| Files | 3 | `tools/cheats/snapshots/nds-fps-478.json`, the 478 version of `supplement478-native-rejections.json.gz` (withheld code bodies), and the `unified-curated.json` version with the Pokémon France excerpts |

## Minimal rewrite (signatures preserved)

1,025 commits have one of these blobs in their tree. Together with their
descendants, **1,026 of the 5,130 commits** must get new hashes.

| Ref | History rewritten | Tip tree loses files |
| --- | --- | --- |
| `Claude` (after the push) | yes | no |
| `main` and the 11 other branches | yes | **yes**: the 14 packs, the snapshot and the audit are still in their tips |
| tags `0.0.8`, `0.0.9`, `0.0.9-fix.1`, `0.0.10` (releases), `build-483`, `build-489`, `build-490`, `build-494` | yes | **yes** |
| tags `0.0.1` to `0.0.7` | no | no |
| `refs/pull/*` | 11 of 143 reach these objects | read-only: a force-push cannot rewrite them |

## Trial run (git 2.43, git-filter-repo 2.45)

`git filter-repo --strip-blobs-with-ids` ran on a copy of the mirror:

- None of the 161 blobs remains, and `git fsck --connectivity-only` passes.
- The `Claude` tip tree is identical before and after (`2e3b9ea6…`).
- The `main` tip tree changes (`b932d60f…` → `38ff26ba…`), because its
  catalogue still holds the packs.
- The copy went from 408 MB to 376 MB.

This git's `fast-export` cannot keep commit signatures. It dropped them, and
so rewrote 4,827 commits, all 15 tags and 139 pull refs, not the 1,026
needed. The real operation needs a git whose `fast-export` and `fast-import`
support `--signed-commits` (Git 2.50 or later).

The commits pinned by tests are all rewritten, so the tests that read them
must be updated in the same operation, without weakening their assertions:

- `test/neoplay_build397_integration_test.py`: `d3d5681c`, `fb744a8e`,
  `424a3603` and `301ff56a`. Its fifth commit, `f4b65f09`, is absent from
  the mirror today, so that test cannot pass from this repository even
  before a rewrite.
- `test/source_rights_test.py`: `8308865b` and `cb59a784`.
- `test/source_rights_fps478_test.py`: `cb59a784`.
- The Enhancements commits `b451b102` and `1c1d1f7f` are also rewritten.

The old→new map of every branch and tag is in the JSON.

## Prerequisites before asking for the force-push

1. Push the withdrawals to `Claude`, then bring them into `main` and into
   any other branch to keep. Otherwise their tip catalogue would reference
   deleted packs. Branches that are no longer needed can be deleted instead.
2. Decide what happens to the release tags `0.0.8`–`0.0.10`. Rewriting them
   changes the GitHub release source archives. The attached IPAs are not
   rewritten; they are separate assets, not inspected here.
3. Freeze pushes during the operation. Other agents and sessions must then
   reclone or reset onto the new history.
4. Ask GitHub Support to remove the 11 pull refs and the cached views. A
   force-push does not reach forks, existing clones, IPAs or caches.

The strict rule (docs/SOURCE_RIGHTS_FOLLOWUP_2026-10-28.md) may later
withdraw more sources. The purge should then be computed once with the full
list rather than twice.
