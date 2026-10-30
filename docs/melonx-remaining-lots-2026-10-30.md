# Remaining Hogwarts lots: implementation after activation

The maintainer explicitly requests the missing production features, beyond
IPA599 activation. Work stays on Claude. This source lot is awaiting Apple
validation and a fresh NativeAOT core; it is not inside the intermediate599.

## Lot3: sized JIT before preparation

The existing command1 trap trampoline gains a versioned descriptor and a
null/zero capability handshake. Old helpers return zero and are refused before
being given a descriptor. Updated Hogwarts requests1024MiB; after an explicit
LLDB _M allocation error, the helper tries960,896,...,512MiB. Empty, malformed,
lost or invalid-address replies are terminal. The first successful RX allocation
is prepared exactly once. Preparation failure, exception, descriptor/register
write failure and any later alias/protection failure never cause a second arena
allocation. A process-local attempt guard and Core's existing quarantine remain.
The actual chosen size is validated by the Core and used by its aliases, code
cache and RX/RW probe. Default512MiB TXM and other titles are unchanged.

This relies on LLDB's documented _M failure contract and its debugserver
allocator cleanup before returning failure; it does not claim rollback of any
blessed/partly prepared region. Reference:
https://lldb.llvm.org/resources/lldbgdbremote.html#id1 and LLVM debugserver
MachTask::AllocateMemory/RNBRemote allocation handling. Physical TXM validation
is still required. Native VM/transport boundaries in the tests are doubled.
101 actual helper-JS checks and45 checks of the extracted production Core
validator pass locally under Node and .NET10.0.100.

## Lot4: experimental, reversible Unreal profiles

Content operation10 inspects the base game plus selected update RomFS with
personal keys, looks for an unambiguous Project/Content/Paks layout, and returns
only a bounded project/configuration inventory. It preserves a pre-existing
UserEngine.ini in the new override. The host restricts all destinations to the
MeloNX directory and exact Hogwarts contents directory, rejects links, path
traversal, changed/unowned experiment folders, conflicting loose files and
uninspected romfs.bin containers in either mods root.

The new per-game dialog starts OFF, asks explicit in-app experimental consent,
and selects exactly one CVar trial at a time: Niagara submission hint, batch
GPU ticks, effect quality, translucency, motion blur, depth of field or internal
resolution. Visual-quality changes are identified. Trials live in their own
LayeredFS folder; atomic swaps archive only verified owned prior trials. Removal
restores the original underlying game/configuration by withdrawing that folder;
user edits and other mods are never deleted or overwritten. Native mutation
gating and fresh identity inspection precede writes. Configuration loading and
individual CVar support on Hogwarts Switch remain unverified and are labelled
as such. No game, save or key is distributed.

## Lot5: independent rendering defects

The existing texture source has two reproducible defects independent of any
private fork. D32FS8 host readbacks (eight bytes/texel) exposed two or four times
the D24S8 guest length, including the stale reusable-buffer tail; rectangular
readbacks also allocated only the guest-sized host staging buffer. The fix
allocates the actual host length, packs in-place where possible and returns
exactly the guest-sized span. Full thin mip blits right-shifted a one-texel axis
to zero; boundary endpoints now retain Vulkan's minimum one-texel extent,
including flipped rectangles, while interior crop rounding is preserved.

The actual extracted methods pass20379 candidate checks against20373 control
checks, reproducing wrong legacy lengths and zero-width/height mip regions.
This does not establish that these were the cause of the user's black textures
or that Vulkan rendering/FPS improved on iPhone. No private fork binary or
replacement MoltenVK is imported. Existing source/ABI/engine tests retain their
original scope; only affected fixtures run freshly for the new core.

## Status

The complete managed Library builds in Release on Linux SDK10.0.100 after fixing
three namespace ambiguities in the new content operation. First failed build
and corrected incremental output are retained locally. Apple NativeAOT/ABI,
new Apple fixtures, Flutter host tests, simulator lifecycle and final IPA checks
must succeed before a compiled/delivered claim. No physical FPS or black-texture
resolution is claimed by this source report.
