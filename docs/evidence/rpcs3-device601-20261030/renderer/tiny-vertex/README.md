# Bounded validation of short vertex uploads

The real `weak_vertex_cache` skipped all content checks for lengths below eight
bytes. This path is reachable: `Core/RSXDrawCommands.cpp` marks stride-zero
attributes as `single_vertex` and uses `get_vertex_type_size_on_host()` for the
stride. That function permits one-/two-/four-byte `ub`, two-/four-byte `sf` and
four-byte float attributes. `interleaved_range_info::calculate_required_range()`
returns one vertex for that block. A single such persistent block is eligible
for the Vulkan upload cache. This establishes reachability in the source; the
logs do not identify such an upload during the reported BO2 visual defect.

On iOS, the cache now fingerprints the actual payload when it contains one to
seven bytes. Larger ranges retain the existing eight-byte weak prefix. The
common path uses fixed-size `memcpy(..., 8)`, preserving an unaligned-safe load
without introducing a full-range hash. The tiny path reads no bytes beyond the
range, including when it ends immediately before a protected page.

`test/rpcs3_tiny_vertex_cache_test.py` extracts the complete production cache
and uses explicit VM/map adapters. The original source produces 28 stale hits
after changing each byte of lengths one through seven. The final candidate
produces zero; 219 assertions pass in optimized and ASan/UBSan modes. The latter
includes alignment checks for the final iOS candidate. Baseline/non-iOS
sanitizer runs exclude alignment because their unchanged direct `u64` loads
are not alignment-safe. Leak detection is disabled; no LSan claim is made.

The final evidence is in `rpcs3-tiny-final-plain` and
`rpcs3-tiny-final-asan`. The first `rpcs3-tiny-*` pair records the baseline and
an intermediate candidate whose common prefix used a variable-size copy. Only
the changed iOS candidate was rerun after splitting that copy into fixed-eight
and short branches. `non-ios-reuse.json` proves the complete extracted cache
and test driver preprocess byte-identically without `RPCS3_IOS`; that branch's
recorded executions remain applicable. No GPU, Apple Core, iPhone or FPS result
is established by these host tests.

The existing wrong-range upload regression was also rerun because it extracts
the changed cache. Its results are kept separately under `range-plain` and
`range-asan`. No additional renderer diagnostics or game settings were added.
