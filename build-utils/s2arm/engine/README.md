# S2Arm engine for the Switch 2 test line

Patches applied in order to S2Arm at the commit of `tools/s2arm_prototype/pin.json` by
`.github/workflows/s2arm-engine.yml`. Each patch says why it exists; the S2Arm source itself is
fetched at build time and never committed here (Apache-2.0, see `docs/s2arm-legal-notices.md`).

| Patch | Why |
| --- | --- |
| `0001-ios-sdk-older-than-27-without-scene-accessory.patch` | GitHub's macOS images carry Xcode 26.x (iOS SDK 26.2 / 26.5); S2Arm is built with the iOS 27 SDK and `ios/extdisplay.m` uses its scene-accessory API. Built with an older SDK the engine does not take over external displays, as on a device below iOS 27. |
