# Build 476 — PS2/PS3 catalogue follow-up

The maintainer reports empty PS2 and PS3 direct cheat lists and a download action without useful feedback in delivered 475. The supplied screenshots show an empty direct list and the PS2 library; they do not establish the exact serial, executable CRC or PS3 executable hash of each running game.

Confirmed PS2 defect: the native snapshot reports a formatted serial such as `SLUS-20655`, while the reviewed PNACH publication stores `SLUS20655`. The catalogue's generic equality check treated them as conflicting even with the same executable CRC. The correction normalizes only valid PS2 disc-serial spellings in both the fast prefilter and the semantic matcher. Different serials, executable CRCs, revisions and PS3 hashes remain conflicting.

The in-game download now uses the verified disk/bundled index, prioritizes matching game packs and reuses verified local chunks/packs without an unnecessary remote-index request. The separate catalogue update operation retains remote refresh. Progress and failures appear in the download row itself, including when a host hides the navigation bar. Matching codes refresh during a bulk download and remain usable while unrelated packs finish. Missing extracted chunks can be recovered from a locally cached, subsequently hash-verified pack.

The shared list no longer equates an unavailable native mutation route with no matching catalogue. Matching installed PS3 programs remain visible with disabled switches and the existing translated explanation when a personal patch file is protected or the native route is unavailable. No personal patch is overwritten and no cheat is activated by a download, discovery or import.

Targeted evidence is recorded after execution: exact 475 negative reproduction, real Foundation download/index/offline behaviors for PS2 and PS3, changed iPhone SDK compilation, and seven UIKit cases. The twelve existing translations are reused. All published catalogue data, emulator cores, native helpers, skins, library and NeoSwap inputs remain unchanged. Existing successful checks of those inputs are reused.

Coverage remains edition-specific. The delivered index has no gameplay catalogue titled Budokai 2 or Dynasty Warriors 5, and its GoW/Hobbit PS2 entries do not cover every region. This runtime fix must not invent missing codes or apply another edition's addresses. No physical iPhone gameplay validation or public release is claimed.
