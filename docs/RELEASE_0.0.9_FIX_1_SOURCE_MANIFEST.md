# RewindBox iOS — fix 0.0.9 / Build 530: release and source manifest

**Published: 25 October 2026.** This is a release-specific source index, not a change to the signed application or an assertion that every third-party binary has complete corresponding-source coverage.

## Published artifact and exact revisions

| Item | Recorded identity |
| --- | --- |
| GitHub release | [**fix 0.0.9**](https://github.com/TarbleFR/RewindBox/releases/tag/0.0.9-fix.1) |
| Tag | `0.0.9-fix.1` (distinct from the original `0.0.9` release) |
| Download | [RewindBox-Build530.ipa](https://github.com/TarbleFR/RewindBox/releases/download/0.0.9-fix.1/RewindBox-Build530.ipa), **186,305,438 bytes** as reported by GitHub Releases |
| iOS build number | **530**, minimum iOS **18.0** |
| Internal app version | **0.0.8** (`CFBundleShortVersionString`); `fix 0.0.9` is the **GitHub release title**, not a claim that the binary's version field was changed |
| Application/source snapshot embedded in IPA | [`3f0c706afe1d0faa635465517871a500c3289582`](https://github.com/TarbleFR/RewindBox/tree/3f0c706afe1d0faa635465517871a500c3289582) |
| Release-publishing workflow revision / tag target | [`97d68263ed64a7a7e38a715627a3851d40c679d9`](https://github.com/TarbleFR/RewindBox/commit/97d68263ed64a7a7e38a715627a3851d40c679d9); release job checks out the application snapshot above |
| Successful public release build | [GitHub Actions run **40156236364**](https://github.com/TarbleFR/RewindBox/actions/runs/40156236364); `checks`, `native`, and iPhone `cold` jobs passed |
| Development-to-main integration | [PR **#143**](https://github.com/TarbleFR/RewindBox/pull/143); the `main` branch contains the development changes |
| Earlier published baseline | [`0.0.9`, Build **527**](https://github.com/TarbleFR/RewindBox/releases/tag/0.0.9), retained as a separate release |

The IPA stores `Legal/BUILD_SOURCE_IDENTITY.json` and `Legal/Sources/BUILD_SOURCE_EVIDENCE.json`. Both identify the application source snapshot `3f0c706...`. The embedded source-evidence record points to the [immutable tracked-source archive](https://github.com/TarbleFR/RewindBox/archive/3f0c706afe1d0faa635465517871a500c3289582.tar.gz), but states **`complete_corresponding_source_attested: false`**. The public Git source archive does not itself contain every separately fetched native dependency or Git submodule.

## Included emulator sources and build evidence

| Runtime | Identity / corresponding source pointers | Validated scope |
| --- | --- | --- |
| **MeloNX (Nintendo Switch), embedded** | RewindBox patched engine source [`ab6d87ebb8b33d0151953b1b9ea7cefaab7a4b12`](https://github.com/TarbleFR/RewindBox/tree/ab6d87ebb8b33d0151953b1b9ea7cefaab7a4b12), [engine run **40152134234**](https://github.com/TarbleFR/RewindBox/actions/runs/40152134234). Pinned upstream MeloNX `13700519f3abc4e6d7ed8a065b118b2cc59bcd67`; LibHac reconstruction `23e402ebb6dedc517e34a98a033078dc0f6fd478`; Melo-Controller `c049ce88a5635bddcd88e1965c42aa8fc92fe961` in [`source.json`](../build-utils/melonx/source.json). | NativeAOT engine compilation, source-adaptation identity and ARM64 iOS simulator smoke test passed; **physical-device gameplay stability not yet confirmed**. |
| **MeloNX iOS Vulkan correction** | [`adapt_runtime.py` at the compiled engine revision](https://github.com/TarbleFR/RewindBox/blob/ab6d87ebb8b33d0151953b1b9ea7cefaab7a4b12/build-utils/melonx/adapt_runtime.py) and [regression test](../test/melonx_ios_vulkan_host_import_test.py). | On iOS, mask `VK_EXT_external_memory_host` and `SupportsHostImportedMemory` to use the engine's existing normal-buffer readback path instead of the unsupported direct host-memory import. This targets the observed `ErrorFeatureNotPresent` error; it **does not certify that every Switch game is crash-free**. |
| **RPCS3 (PlayStation 3)** | Reused source-built **Core 528**, RewindBox source [`17ee65469c39e560c91fdb6d55604ab590992f59`](https://github.com/TarbleFR/RewindBox/tree/17ee65469c39e560c91fdb6d55604ab590992f59), [run **40142369420**](https://github.com/TarbleFR/RewindBox/actions/runs/40142369420). See [canonical upstream source pin](../build-utils/rpcs3/canonical-source.json) and [source/patch audit](ENGINE_CORRESPONDING_SOURCES.md). | ABI/source/payload continuity verified; **no physical God of War III performance or FPS claim**. |
| **Libretro, 35 embedded cores** | Package-source revision `ab9361c29f7c9ab769c4263dd8b7427fc4f4c036`, [run **39455712245**](https://github.com/TarbleFR/RewindBox/actions/runs/39455712245). [Core inventory](../build-utils/libretro/cores.json), [individual license/source records](../assets/legal/libretro/LIBRETRO_CORES.md). | The Build 530 IPA contains 35 core identities. Several upstream buildbot binaries still lack exact corresponding-source attestation; see [the provenance register](EMBEDDED_RUNTIME_PROVENANCE.md). |
| **ARMSX2 (PlayStation 2)** | [Source pin and local adapter](../build-utils/armsx2/source.json), compiled host source `1343906f05e33b40f10f7026a1a6e2327c338d0e`, run `39178893158`. | Validated unchanged component reuse from the previous release. |
| **Dolphin (GameCube / Wii)** | [`OatmealDome/dolphin-ios` revision `7cac54161659421ed95c2cd1c0b0746539a4cd38`](https://github.com/OatmealDome/dolphin-ios/tree/7cac54161659421ed95c2cd1c0b0746539a4cd38) and [local integration](../build-utils/patch_dolphin_internal_core_v2.py). | Existing binary and host integration preserved by the validated release recipe. |

The old external MeloNX launcher and the Dusklight/KartPad native game ports are **not part of Build 530**. Users provide their own legal game content, firmware, and keys where needed; none are distributed with the IPA.

## Obtain the correct sources

Use the **specific application commit**, not a moving branch or an old tag, when examining this build:

```sh
git clone https://github.com/TarbleFR/RewindBox.git
cd RewindBox
git checkout 3f0c706afe1d0faa635465517871a500c3289582
flutter pub get --enforce-lockfile
flutter config --no-enable-swift-package-manager
python3 packages/dolphin_internal_bridge/ci/build_support.py scaffold
```

These commands check out the host and prepare its Flutter/iOS scaffold. **They do not alone reproduce a distributable IPA.** The [Build 530 delivery recipe](../.github/workflows/melonx-launch530-delivery.yml) and [public release-publishing recipe](../.github/workflows/publish-fix-009.yml) also require their exact native engine archives, dependency artifacts, Xcode 26.3, Flutter 3.47.2, signing and packaging inputs. The public release workflow intentionally uses the earlier fixed application-source commit; the current `main` branch is the maintained successor, not a bit-for-bit source tag for every historical binary.

For third-party source retrieval and attribution, consult [source access and dependency provenance](SOURCE_CODE_ACCESS.md), [engine source evidence](ENGINE_CORRESPONDING_SOURCES.md), [package sources and licenses](PACKAGE_SOURCES_AND_LICENSES.md), [full legal credits](LEGAL_AND_CREDITS.md), [NOTICE](../NOTICE.md), and the notices actually bundled in `Legal/` of the IPA.

## Limitations retained by this release

- The original iPhone report was traced to a Vulkan direct-host-import error after the first rendered frames. **Automated checks passed; sustained physical-iPhone gameplay has not been independently established.**
- Full matching corresponding sources are not yet attested for all distributed native artifacts and third-party SDKs. Component-level audits preserve specific gaps rather than upgrading a candidate revision or a license reference into a source-build proof.
- Third-party licenses and author permissions remain separate from the frontend license. Open items include noncommercial/fundraising terms for some cores, certain cheat/HD artwork rights, some native dependency sources, combined-work compatibility, and the recorded FFmpeg build-license discrepancy.
- The IPA is **ad-hoc signed** for appropriate re-signing with SideStore/AltStore. An entitlement embedded in a binary does not itself authorize restricted Apple capabilities on a device.
- Historical source manifests, archived drafts and older release records remain valid **for their original revisions**, not as statements about Build 530.
