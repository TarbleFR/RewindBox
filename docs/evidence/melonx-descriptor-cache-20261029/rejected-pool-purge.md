# Pool binding cleanup withheld

The proposed `adapt_binding_pool_lifetime.py` is rejected for this cycle. Do not apply the purge alone. `adapt_binding_data_snapshots.py` remains independently valid and is not affected.

`TextureBindingsManager.GetPools()` (TextureBindingsManager.cs:803) keeps a non-null cached pool without checking whether PoolCache has evicted and disposed it. `Rebind()` (same file:850) clears binding state only. `ForceShaderUpdate()` (StateUpdater.cs:1632) dirties shader state only. Compute dispatches tick the compute/graphics shared per-channel PoolCache (`TextureManager.cs:344`) and can evict an old graphics pool while the graphics manager still retains its pointer.

A buffer-backed binding entry can still validate when its snapshot, sequence and textures remain unchanged. Removing that entry on pool eviction forces a later graphics binding rebuild through GetForBinding on a disposed pool whose Items is null. The new purge can therefore expose a concrete crash despite passing the isolated PoolCache/cache lifetime checks.

Prerequisite for revisiting: establish a correct acquisition/reload contract for disposed texture AND sampler pools in TextureBindingsManager, and verify actual CP -> GP transitions across pool eviction. Only after that contract is proved should buffer-backed cache entries be purged by pool reference identity. Source-level backend fence release and local disposal/reentrancy tests do not prove the acquisition contract.

The preserved receipt `dist/melonx/binding-pool-lifetime-checks.json` documents only the isolated cache tests (13 scenarios), not acceptance or end-to-end game compatibility. The stale-fixture receipt, when present, is invalid proof.
