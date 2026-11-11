# S2Arm engine for the Switch 2 test line

Patches applied in order to S2Arm at the commit of `tools/s2arm_prototype/pin.json` by
`.github/workflows/s2arm-engine.yml`. Each patch says why it exists; the S2Arm source itself is
fetched at build time and never committed here (Apache-2.0, see `docs/s2arm-legal-notices.md`).

| Patch | Why |
| --- | --- |
| `0001-ios-sdk-older-than-27-without-scene-accessory.patch` | GitHub's macOS images carry Xcode 26.x (iOS SDK 26.2 / 26.5); S2Arm is built with the iOS 27 SDK and `ios/extdisplay.m` uses its scene-accessory API. Built with an older SDK the engine does not take over external displays, as on a device below iOS 27. |
| `0002-engine-image-header-without-mh-execute-header.patch` | Linked as `S2ArmEngine.framework` (a dylib) the engine cannot reference `_mh_execute_header` (run 43030882887: the only undefined symbol). Seven uses read the engine's own registration sections (`__DATA,swnvn/swhle/swgl/swglb/swvkb`) or `__TEXT` range, which live in the framework: they now take the header of the image that holds the code (`runtime/src/rb_selfimg.c`, `dladdr`). The entitlement fallback of `ios/iml_probe.m` reads the process's main executable (`_dyld_get_image_header(0)`). In the S2Arm.app executable both give the executable's header, so its behaviour is unchanged. Apple platforms only. |
