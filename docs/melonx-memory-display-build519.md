# MeloNX memory donor and display — candidate 519

The maintainer explicitly requested connecting MeloNX's original RAM donor,
showing measured RAM during gameplay, and adding per-game screen formats.
Build 518 launches on the maintainer's iPhone; this continuation preserves its
key import and UIKit/JIT retry fixes. Work remains on Claude, with a private
IPA only. No release, tag or main update is authorized.

The pinned MeloNX donor (13700519f3) supplies mapped chunks through its original
extension and XPC transport. A process-owned Swift lease offers the actual
mapped prefix to the actual Core allocator before a session. Normal allocation
remains the fallback when the extension is unavailable or refuses the loan.
The donor stays alive while memory is borrowed. A failed withdrawal or unmap
retains ownership and requires process restart instead of freeing live memory.
The original allocator refuses replacement/withdrawal while allocations remain;
Core exports also require an idle session. Late donor connections are isolated
by a fresh endpoint per acquisition. Partial mappings and scratch aliases retain
cleanup ownership. RPCS3-active sessions block MeloNX donor acquisition; the
frontend's existing single game route remains the session admission boundary.

A 120-sample, 2 Hz HUD reports TASK_VM_INFO.phys_footprint, available app memory,
peak footprint, mapped donor capacity and actual allocator usage separately.
Mapped capacity is not resident RAM, additional physical memory or evidence that
iOS memory limits have been removed. Invalid readings leave gaps. Sampling stops
when hidden, backgrounded or closed. Screen formats use the upstream renderer's
AspectRatio setting: 4:3, original 16:9, 16:10, 21:9, 32:9 and stretched. Changes
are generation-bound and saved per game, with rollback on save failure.

Validation targets: actual allocator ownership and zeroed reuse; production
Swift lease fault cases; complete iPhone SDK compilation; actual UIKit plugin
presentation/retry and RAM graph/timer checks; original extension compilation;
Flutter persistence/localization/import-disposal regression; rebuilt NativeAOT
ARM64 simulator with two homebrew sessions consuming supplied memory. The smoke
backing is a local mmap, not a donor process. Actual iPhone donor activation,
footprint benefit, commercial gameplay and FPS remain unverified until testing.
