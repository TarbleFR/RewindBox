# RPCS3 memory audit — Build 508 assembly

This candidate integrates the attached ARM64/iOS audit on top of the delivered
Build 507. Its interface, motion assets, startup, catalogues, MeloNX and every
other engine retain the delivered source. The only changed host product inputs
are the shared NeoSwap compiler coordinator and RPCS3's optional binder/log
admission. Core ABI 30 and the existing allocator/relay/storage ABIs remain.

The F1–F9 implementation and research limits are mapped in
`rpcs3-memory-audit-2026-10-23.md`. Direct bounded object loading, validated
buffer reuse, measured compiler admission, in-phase observations, data-only
free-page advice, reservation fault ordering and small-heap VMA granularity are
in the canonical source delta. Arena capacities and existing LLVM feature and
pipeline choices remain. The minimal-object linker is tested research code;
the production SPU translator does not invoke it. Further hot-block NEON
rewrites and capacity tuning require actual title/device evidence.

The immutable Core candidate is built separately by the memory-audit workflow.
Final assembly must require its successful exact source, patch, binary, recipe,
native acceptance inputs, passive initialization and new optional export. Its
artifact identity is never normalized or rewritten. The package adds
`RPCS3-memory-audit-identity.json`, binding the compiled payload before signing
to that source artifact. The final signed IPA must retain the same code/data
and ABI fingerprint and contain the shared broker and optional binder.

Existing Build 507 Flutter/native motion evidence is reused only after exact
source comparison. The final Xcode Release build compiles the changed native
host. All prior engine, lazy loading, license, entitlement, distribution,
catalogue and signing gates remain. The original motion package validator now
accepts an explicit build number, defaulting to its original 507.

No physical game session, measured FPS/RAM gain or device relaunch is claimed.
Internal app logs JITMEM/JITPAGES/JITCPU/VMAHEAP support the audit's suggested
cold/warm/second-title comparisons. The app still requires Apple signing for
installation with SideStore. No main change, public release or tag is made.

Successful build and final artifact receipts are recorded after verification.

Broad touch/cheat bridge path triggers reuse their existing proofs only for the
closed `[rpcs3-memory508]` integration. The delivery gate proves every original
command is retained and only that job condition differs; manual runs still
execute. Product-source closure proves the touch/cheat/UI inputs are unchanged.
