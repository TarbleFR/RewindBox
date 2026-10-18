# Build 474 — unified cheat catalogue private IPA

The maintainer authorizes the next IPA after reviewing the complete source
inventory. Candidate builds on the delivered 473 and the final catalogue
integration `2c328dfb6267245220da6162790b52542b9e2e0b` on `Claude`.

The catalogue contains 34 source/provenance attributions on 22 systems,
2,341,355 programs/variants, 43,813 identity groups, 44,955 transport parts and
851 downloadable packs. Initial network transfer is about 281 MB; the IPA
embeds the 6,574,067-byte compressed index, not the full downloadable packs.
Sources, edition limits and adaptations remain in `unified-cheats-sources.md`
and `unified-cheats-integration.md`.

The delivery composition gate requires the exact successful 473 baseline,
the final data CI and full Apple index preflight, plus successful native,
SDK, Foundation, RAM and UIKit component evidence. The earlier failed overall
jobs remain failed: only their documented successful components are reused.
All source packages equal their tested snapshots, with the separately tested
RPCS3 first-import correction and final manifest handled explicitly. No
successful unchanged suite is rerun. Xcode 26.3 / iPhone SDK 26.2 is required.

The delivery reuses the exact 34-core bundle with corrected Nestopia and all
other delivered emulator payloads. No core rebuild is authorized or needed.
The host and its new shared pod are compiled and linked as a device Release.
The actual IPA must contain the exact final resource index and the shared
catalogue/browser linked into all four consumers. All normal version,
signing, source and native payload checks remain required.

Build 474 identifies this delivery; do not reuse its number. The new public RSA recipient is
`build-utils/delivery-474-recipient.pem`; its private key stays outside Git.
No public release or installation on a physical phone is claimed. The final IPA and CI identities are recorded below.

## Preparation failure retained

Run `39096704203`, source `22cfddc6cad9d84e3db0ea47806fd3d8d3248973`,
stopped in evidence collection before any IPA compilation. The installed
GitHub CLI rejected historical ANSI-bearing logs without its explicit
`--allow-escape-sequences` flag. The reader now captures those log bytes
privately with that flag. No product, core or prior test assertion changed.

Run `39096796545`, source `ce605518c5b73cad2af3eae152339dc039997242`,
passed checks and native provenance, then stopped before host compilation.
The old RPCS3 input gate rejected the optional, separately tested patch API
declarations in the host header. The replacement verifies the exact SDK-tested
header, removes only that exact optional block in a temporary input view,
requires every remaining byte to match the published Core header, and runs
the unchanged Core pin/identity validators against that view. The authentic
artifact identity and all other Core inputs remain unchanged. The live host
header and the main ABI layout are never rewritten. Existing-symbol checks
also require all four optional exports from the actual downloaded binary.

## Verified private delivery

- Source `b3c83af81e362718a63c73b048d797d8c21654cf`, branch `Claude`.
- Run [39097173122](https://github.com/TarbleFR/neostation-ios/actions/runs/39097173122)
  succeeded: checks `117585927072`, native provenance `117585927052`, cold
  Release `117586058233`. The optional warm build was skipped. The earlier
  preparation failures above remain failures; neither reached host compilation.
- Exactly one Build 474 device IPA was compiled. Actual AOT/Xcode compilation
  ran from 04:32:00 to 04:37:05 UTC, **305 seconds**. Checks/native compose the
  recorded successful evidence; they do not claim fresh execution of those
  historical test suites on this delivery commit.
- Final IPA **0.0.7 (474)**: `NeoStation-Build474-b3c83af8.ipa`,
  **225,395,532 bytes**. SHA-256:
  `d752791907aeffbab0a70e679b5d3e51e6e4168c8f81a015ab564835276c0dce`.
- Encrypted artifact `12125610664`, **225,609,629 bytes**, ZIP SHA-256
  `5e0aa74c19c3921898af8004cfc345e8c6fa59a257eb49d44214d7a881f73696`.
  Download completed and its exact size/hash passed before decryption.
  The temporary AES password was removed. Private keys are outside Git and
  are excluded from reports and deliverables.
- Independent inspection passed ZIP integrity, the two final CI checksum
  records, source identity, all **six** app/extension versions, and **77**
  actual thin Mach-O code/data/ABI fingerprints against the CI seal.
  CI verified **80** ad hoc signatures and the on-disk extracted final ZIP;
  codesign was not rerun on the Linux inspection host.
- The final resource bundle contains the exact Apple-tested gzip index:
  `cf8959bfd6b20b4ef2516e1e235723b1a5048b2fc2c98033d05ad0d48cf84e57`,
  6,574,067 bytes. The shared catalogue implementation and all four native
  consumers are present in the actual IPA. The 851 downloadable packs are
  absent from the IPA as intended.
- All emulator/core artifact pins equal delivered 473. CI checked actual
  pinned Core identities before embedding; the final compiled sections and
  ABI ledger match the seal after signing. The corrected Nestopia and the
  other 33 Libretro cores, RPCS3, Dolphin, ARMSX2 and MoltenVK are retained.
- The optional RPCS3 header view passed its real pin validator locally.
  Negative controls changing the main ABI header or a storage ABI input in
  that temporary view were both rejected by the unchanged validator.
- The verified IPA was saved for the maintainer as a downloadable file.
  SideStore/AltStore must apply Apple provisioning. No physical iPhone,
  actual commercial-ROM cheat effect, or public GitHub release is claimed.

## Sealed image evidence

SHA-256 of the original CI `signed-payload-identity.json`:
`b1d31041f8173e455aa81571d0c684b795706d1e10408283b08415bf94e73338`.
Every fingerprint below was recomputed from the delivered IPA and matched.
These fingerprint values cover code/data sections and ABI metadata while
excluding mutable code-signature bytes. The fat Dart AOT wrapper is covered
by the exact whole-IPA SHA-256, not counted as a thin image here.

| Image relative to the app | Code/data/ABI fingerprint |
|---|---|
| `Frameworks/ARMSX2Core.framework/ARMSX2Core` | `fb16a28d7807d7e1442fb3ce03546ff488b1d8974ba6356ff17d1b9152c8bb8c` |
| `Frameworks/DolphinCore.framework/DolphinCore` | `4c9573a7de3d97683d5d4e4f075d7a84b273343aee4452ad01718c41a795fba0` |
| `Frameworks/DusklightCore.framework/DusklightCore` | `4463d7f48939218fea92352135c82a700b144034b873fae82c367d7ffa784655` |
| `Frameworks/Flutter.framework/Flutter` | `e2e4e0b9b6a52e5076e5596d65ff99df3ac654938d4dbcb47f69bbdc0dbf7194` |
| `Frameworks/GTMSessionFetcher.framework/GTMSessionFetcher` | `02339ef6854598cf072ddace06510150fe6ee060e116416cf76ec5f6c016bad9` |
| `Frameworks/KartPadCore.framework/KartPadCore` | `b3857da6839d586dbf2e873b494a94c4fccd656c5d8de062eca4a3bfb4a828aa` |
| `Frameworks/KartPadRuntime.framework/KartPadRuntime` | `126199be5a77d5465bbed62a73837c96e4cb4c0d81497a291528cafbc231dd99` |
| `Frameworks/MoltenVK.framework/MoltenVK` | `7cbd35be66c78e741768528c7b0fbf3cf20f5b468dc5361893033d4924741520` |
| `Frameworks/PDFium.framework/PDFium` | `5f41c44f13da07f6705ab25f1336b9c8f6ae1dd02f99210cbb7fb66a7d7717f5` |
| `Frameworks/StikJIT.framework/StikJIT` | `57e75fbd4ee836e209772cb3a0f732626b1e7becdf7654d4f0f05111926542f6` |
| `Frameworks/a5200_libretro.framework/a5200_libretro` | `cfa6fedeb2b2ae954565491f0e103c67d62c0168edf3480fc08a301a9ca1a19b` |
| `Frameworks/ardens_libretro.framework/ardens_libretro` | `5b1b62c69036580263c57d482cb8be16faa793a42614b556b5a32c7ff08ababc` |
| `Frameworks/armsx2_internal_bridge.framework/armsx2_internal_bridge` | `dbd582c73bb3c7ed8dc0d6efe2f513bfd8e3ec496d3e3b2d106baff5db685ed8` |
| `Frameworks/azahar_libretro.framework/azahar_libretro` | `65545169819d1c1270bf3d54a9f4dbabfb445affb54ccab8b27fbc615c7845fc` |
| `Frameworks/battery_plus.framework/battery_plus` | `d1cf2c07f366d9bed11bdf691e43b63777386628b4d04626b258b9055b5134c8` |
| `Frameworks/desmume_libretro.framework/desmume_libretro` | `bd20ed434cc857b52dfdc9c3a5cdbd001bf15b4854c5ccdc162a653bbef5d12c` |
| `Frameworks/device_info_plus.framework/device_info_plus` | `1fed69ccf6856da70c0a22d66192f76c3556b15afccac3a640f94b50c0943d3c` |
| `Frameworks/dolphin_internal_bridge.framework/dolphin_internal_bridge` | `fdf168919d161a6fdaf903c870b8f21f59e37c68792287544fb82a72008d34c5` |
| `Frameworks/dusklight_internal_bridge.framework/dusklight_internal_bridge` | `4e14034b08d1b15ffdf5a878c12b2f8c74225954b128c03545b7a75279b1fd2a` |
| `Frameworks/external_display.framework/external_display` | `452bc96b9543ee4e531e0368869fffdfb08723584f1f1d203a507be1052ae470` |
| `Frameworks/external_folder_access.framework/external_folder_access` | `2ca6e717f1e76454944a8bf52f3fb1ed250c2ba9bbaaaf6697e1a9a999b94fa5` |
| `Frameworks/fbneo_libretro.framework/fbneo_libretro` | `18102405bbe565cbba25fc822871ba87bee1db7dda5cf1da02302f6904ce5aec` |
| `Frameworks/file_picker.framework/file_picker` | `92ccfe734b09f99e8d4aa0c2de5e95a4987ac0a1655f56c59453606b42e05b92` |
| `Frameworks/flutter_7zip.framework/flutter_7zip` | `a23619efbff2d9c1c9411ef39a35ead40154e488a1905df28c2324ad18105e7e` |
| `Frameworks/flutter_localization.framework/flutter_localization` | `d0e101cc9c513614e319fca07b30d869be7bbb9ca39daf6f509611966e05534f` |
| `Frameworks/flutter_secure_storage_darwin.framework/flutter_secure_storage_darwin` | `5b4e6c00ca523f3386850f266136eb53e1b538a6627b9f9afb6fdcfce1144666` |
| `Frameworks/freechaf_libretro.framework/freechaf_libretro` | `fd60db6eac893840535a18cf3e025730a5682814120f4aacf339f437c37aab1c` |
| `Frameworks/freeintv_libretro.framework/freeintv_libretro` | `dcccda5d6ca628c30dea61694cbe3115f4d35e04eef1615875b69ed02d15b9c1` |
| `Frameworks/gambatte_libretro.framework/gambatte_libretro` | `3e803dca4a105e7d8469c3cd1ec79c41c5fe5d87137ebe3a91afbafc25957e30` |
| `Frameworks/gamepads_darwin.framework/gamepads_darwin` | `db696938860db88aa87680935052469824c6d786b343d8a66e89e3f94ce0b368` |
| `Frameworks/gearcoleco_libretro.framework/gearcoleco_libretro` | `9f5496ac38b3b464ac3dfe0b2d90c0ac5a1a365fe6c160e07d5f67be0b8a276e` |
| `Frameworks/genesis_plus_gx_libretro.framework/genesis_plus_gx_libretro` | `e732f8a67cce93ad7bf2a3ad0c27bd8c6444882cb6ab67855b2354f1e838c7c1` |
| `Frameworks/genesis_plus_gx_wide_libretro.framework/genesis_plus_gx_wide_libretro` | `145e71994f9cf2d7b72bd8e30ba49a348099aebb805450e7736619dee916b904` |
| `Frameworks/gw_libretro.framework/gw_libretro` | `1561851ab719f3c1063bce1059d93982bd6fd0ad7ed8fa99144961ccd8fbd7c0` |
| `Frameworks/handy_libretro.framework/handy_libretro` | `7a46ec1712e3e0f95db8a2c04c6626cc0882c374d904c4e1673d9e7781fcad31` |
| `Frameworks/kartpad_internal_bridge.framework/kartpad_internal_bridge` | `7cfd5553f7c995fdfced6503b461724193ec662192e2e7b4c4b8eb674f269dcd` |
| `Frameworks/libRPCS3Core.dylib` | `416924d5da2895e888667578d773117f219ade8cfecb858e0db08790fd1d94a4` |
| `Frameworks/libretro_internal_bridge.framework/libretro_internal_bridge` | `66fe1fa3978d906761b759ec7d8511f40c1ad97505c71c73c31680d712e52b4a` |
| `Frameworks/mednafen_ngp_libretro.framework/mednafen_ngp_libretro` | `7a22292d47f0d92c7fcc75c9b4b72b71172edd0f11132d5edc20afc11ae36c3f` |
| `Frameworks/mednafen_pce_fast_libretro.framework/mednafen_pce_fast_libretro` | `e9f0abcb0f5b71111a6631e4e29f3ee0387325af3804e20a2a7a2717ec51a354` |
| `Frameworks/mednafen_pcfx_libretro.framework/mednafen_pcfx_libretro` | `ad5aa730fb7862d5185da7b4c66fea236bbbdeb981d83f1be856800e5d675887` |
| `Frameworks/mednafen_psx_hw_libretro.framework/mednafen_psx_hw_libretro` | `20febed54a2e7e53db2652fadcdf4fd7294c057f313225f9c89b01a7f1d8f5fb` |
| `Frameworks/mednafen_psx_libretro.framework/mednafen_psx_libretro` | `21e108a787d92761ea6b49dbed20ae098b0e5dd94692e21377e19d866d3853b3` |
| `Frameworks/mednafen_vb_libretro.framework/mednafen_vb_libretro` | `8eb3437fa0c5e247c15c959a18a9d3179f7646d1c616f6d6d6dc07ad59d70d16` |
| `Frameworks/mednafen_wswan_libretro.framework/mednafen_wswan_libretro` | `29cce20057b765de6d99d962ea5e55a1a4a47e86cee83255e6d16b0e1ba0c545` |
| `Frameworks/mgba_libretro.framework/mgba_libretro` | `a8f8613a1895d58cbac8effd04ccd84bb6dbb4c59a60cbc18efc2bf268a6d181` |
| `Frameworks/mupen64plus_next_libretro.framework/mupen64plus_next_libretro` | `ba845fc8a78edf87639a750203b2d09eb0fd294cd7969473115ad816f9280286` |
| `Frameworks/neo_cheat_catalog.framework/neo_cheat_catalog` | `f8324bd4a2d7422fb2c044e0bb3ba3109bc880784cbcd1e6b499fbc230574dca` |
| `Frameworks/neo_shader_kit.framework/neo_shader_kit` | `1a3e84cc227507a89ffafdf7c517e57fdd8816c4e5f2eec1388c55c27f5842a5` |
| `Frameworks/neo_swap.framework/neo_swap` | `61f51b14584672ea89efe9eaec07bae6cae01fd87352ae4bd78285c0a8012b5d` |
| `Frameworks/nestopia_libretro.framework/nestopia_libretro` | `847be8672c95558feebe0be55bdf3264e7e241009451b11a023a835b44d3e0ef` |
| `Frameworks/o2em_libretro.framework/o2em_libretro` | `535cdf027548eab1117dff0522d9a589ac403d996e8fc569b81996c5bc3f1209` |
| `Frameworks/package_info_plus.framework/package_info_plus` | `226edc0cfc9e2bc475a10410b7c0ce7a1146472b6d08e36c3ce280eb58f77b4b` |
| `Frameworks/pdfium_flutter.framework/pdfium_flutter` | `f8b69b0c5db6615cb7eb409169d238a7bf7be5b89aa2759a6f0b4668c404c0fe` |
| `Frameworks/picodrive_libretro.framework/picodrive_libretro` | `65d6dc5a241efda5ea1965443b3c9fe1e763538a36e14ca290d9ec571377d9e1` |
| `Frameworks/pokemini_libretro.framework/pokemini_libretro` | `c1c03e755afc328ba64bfce2f8491f8838d224e6f9685a73f2bd060c67b4ff6e` |
| `Frameworks/potator_libretro.framework/potator_libretro` | `19a67f1d4f65a819cc87cb1576d7348a8eb1451e1b509aad25d7d73636fea681` |
| `Frameworks/ppsspp_libretro.framework/ppsspp_libretro` | `ada78a039631ba27a4731e33a451797f0d2169761e8f7884281d66b3db6f979c` |
| `Frameworks/prosystem_libretro.framework/prosystem_libretro` | `82b4af35d8c61093d1e7edb0f6c3eeca361acb4b8c96d3e83ddf3ffbad5150af` |
| `Frameworks/rpcs3_internal_bridge.framework/rpcs3_internal_bridge` | `c0f369b997c1426cbaec47aabde781153e0e5cb89b4a979aa8f47e4974298dce` |
| `Frameworks/sameduck_libretro.framework/sameduck_libretro` | `f648c6efc1455c280441c1f70dd62d3f2451a6e36b57268f3acf7ed6ff2256cb` |
| `Frameworks/share_plus.framework/share_plus` | `61c249aab903a51c4589eb9b9e5d84f51187fb87cba80ec7ae581ca6ec6607bb` |
| `Frameworks/shared_preferences_foundation.framework/shared_preferences_foundation` | `9454e9308d59d4af6675e2a5473fddab6c72a560ccafa558520f3decf0f5d0b5` |
| `Frameworks/snes9x_libretro.framework/snes9x_libretro` | `e0326b241edce3f8860b85e3a08684806e611e292a21204534456b3af08ba788` |
| `Frameworks/stella_libretro.framework/stella_libretro` | `a44e78a4e58dc481233737681fa3547ecebdfef0178219de8213aa067e8cf368` |
| `Frameworks/stikjit_bridge.framework/stikjit_bridge` | `026a45208e08511ae5b3d0e191b7ef98274f0f62a815bdeb2ad1aa1eef564bd2` |
| `Frameworks/url_launcher_ios.framework/url_launcher_ios` | `30c6a3196045d9f26a033a5ce34de897379672e6b42b245c3b4c3f0cd57124e3` |
| `Frameworks/uzem_libretro.framework/uzem_libretro` | `ae053a29eff0b1490f7cedd6af8a79d0df45950ef71fd604a93703ceaa039d93` |
| `Frameworks/video_player_avfoundation.framework/video_player_avfoundation` | `19d020b4ef646c50e78fd98c18ff41497c4164ad2dbc76857de6251e885a1aa2` |
| `Frameworks/wakelock_plus.framework/wakelock_plus` | `d80050230bafdff7725a634cb9e7dc8e24907f05bddd8c37d1cc2ad1e1892389` |
| `Frameworks/wasm4_libretro.framework/wasm4_libretro` | `41dec5ccf2fdb0153db049f027424f42993ae0c83df61e4bd1db24b0cf9a4dde` |
| `PlugIns/ARMSX2JITHelper.appex/ARMSX2JITHelper` | `3578854229f11f67d7b1fb0e94ac8396b0dc4ae32cbbf56cbfe0c0599c3e26a9` |
| `PlugIns/DolphinJITHelper.appex/DolphinJITHelper` | `5b9a1ce77f53f4527c91912e2d8839748878163ceea454c58b33b1b99614c828` |
| `PlugIns/NeoSwapDonor.appex/NeoSwapDonor` | `8c9c7a6228b4e8f6e64bcb3b493d4caadedf3c77a4455a8b93b0ce3ea50dc8aa` |
| `PlugIns/NeoSwapPageRelay.appex/NeoSwapPageRelay` | `5080e7987821d08131c9e86b362b0426230048fdb98147ce9b7df3cd61431f57` |
| `PlugIns/RPCS3JITHelper.appex/RPCS3JITHelper` | `19658a7e78f220b622115f6cf5398946d7bf2fd55e35fd423e1f675ed62b2581` |
| `Runner` | `5286667fab14ae965df10158ddb3a6dc78ef8083dd26870fc01fde8a5436867a` |
