#!/usr/bin/env python3
"""Shared catalogue labels and targeted real UIKit/XCTest checks.

The native target links only the new catalogue/browser and no emulator core.
It never produces an IPA. Source/translation checks run on any host; --native
requires macOS, Xcode, xcodegen and a matching iPhone Simulator runtime.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POD = ROOT / "packages/neo_cheat_catalog/ios"
CLASSES = POD / "Classes"
LIBRETRO = ROOT / "packages/libretro_internal_bridge/ios/Classes"
LANGUAGES = {"en", "es", "ru", "zh", "zh_Hant", "pt", "fr", "de", "it", "id", "ja", "ko"}

APP = r'''
#import <UIKit/UIKit.h>
@interface UnifiedCatalogueTestDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation UnifiedCatalogueTestDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController = [UIViewController new];
    [self.window makeKeyAndVisible];
    return YES;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(UnifiedCatalogueTestDelegate.class)); }
}
'''


def contracts():
    labels = json.loads((POD / "Resources/labels.json").read_text())
    assert set(labels) == LANGUAGES
    spec = importlib.util.spec_from_file_location("unified_browser_labels", ROOT / "tools/cheats/unified_browser_labels.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert labels == module.resource(), "Generated labels differ from the reviewed translations"
    keys = set(labels["en"])
    marker = re.compile(r"\{([a-z_]+)\}")
    for locale, translated in labels.items():
        assert set(translated) == keys, locale
        for key, value in translated.items():
            assert isinstance(value, str) and value.strip(), (locale, key)
            assert set(marker.findall(value)) == set(marker.findall(labels["en"][key])), (locale, key)
    source = (CLASSES / "NeoUnifiedCheatBrowser.m").read_text()
    literal_keys = set(re.findall(r'\[self text:@"([A-Za-z]+)"', source))
    literal_keys.update(re.findall(r'fbneoText:@"([A-Za-z]+)"', (LIBRETRO / "LibretroCheatMenu.m").read_text()))
    assert literal_keys <= keys, sorted(literal_keys - keys)
    assert labels["zh_Hant"]["downloadAll"] != labels["zh"]["downloadAll"]
    assert {"editionConfirmMessage", "downloadAll", "retryDownloads", "dependenciesExclusive", "cataloguePart"} <= keys
    # These focused assertions have no optional message argument. Verify their
    # real C macro arity before booting a Simulator: Objective-C dictionary and
    # array commas must be protected by parentheses at assertion boundaries.
    preprocessor = shutil.which("cpp")
    if preprocessor:
        tests = (ROOT / "test/unified_catalog_browser_ui_tests.m").read_text()
        tests = re.sub(r"^#import.*$", "", tests, flags=re.MULTILINE)
        names = sorted(set(re.findall(r"\b(XCTAssert\w+)\s*\(", tests)))
        definitions = []
        for name in names:
            count = 3 if name.endswith("WithAccuracy") else 2 if name in {
                "XCTAssertEqual", "XCTAssertEqualObjects", "XCTAssertNotEqualObjects", "XCTAssertGreaterThanOrEqual"
            } else 1
            arguments = ",".join(f"arg{index}" for index in range(count))
            definitions.append(f"#define {name}({arguments}) ((void)0)")
        subprocess.run([preprocessor, "-P", "-x", "c", "-"], input="\n".join(definitions) + "\n" + tests,
                       text=True, stdout=subprocess.DEVNULL, check=True)
    print(f"Shared catalogue: {len(keys)} complete keys in all twelve languages; placeholders preserved.", flush=True)


def native(result_path: Path | None):
    if platform.system() != "Darwin":
        raise RuntimeError("UIKit execution requires macOS with Xcode; no native pass is claimed on this host")
    sdk = subprocess.check_output(["xcrun", "--sdk", "iphonesimulator", "--show-sdk-version"], text=True).strip()
    runtime_key = "com.apple.CoreSimulator.SimRuntime.iOS-" + sdk.replace(".", "-")
    devices = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"]))["devices"]
    candidates = [device for runtime, items in devices.items() if runtime == runtime_key for device in items
                  if device["name"].startswith("iPhone") and device.get("isAvailable")]
    if not candidates:
        raise RuntimeError(f"No available iPhone Simulator matching Xcode SDK {sdk}")
    device = next((item for item in candidates if item.get("state") == "Booted"), candidates[0])
    print(f"UIKit catalogue tests: {device['name']} / iOS {sdk} / {device['udid']}", flush=True)
    if device.get("state") != "Booted":
        subprocess.run(["xcrun", "simctl", "boot", device["udid"]], check=True, timeout=60)
    subprocess.run(["xcrun", "simctl", "bootstatus", device["udid"], "-b"], check=True, timeout=180)
    with tempfile.TemporaryDirectory(prefix="neo-unified-catalogue-ui-") as folder:
        directory = Path(folder)
        (directory / "main.m").write_text(APP)
        include = directory / "include/neo_cheat_catalog"
        include.mkdir(parents=True)
        for header in (CLASSES / "Public/NeoUnifiedCheatCatalog.h", CLASSES / "NeoUnifiedCheatBrowser.h"):
            (include / header.name).write_bytes(header.read_bytes())
        frameworks = [{"sdk": item} for item in ("UIKit.framework", "Foundation.framework", "UniformTypeIdentifiers.framework", "QuartzCore.framework", "libz.tbd")]
        project = {
            "name": "UnifiedCatalogueBrowser",
            "options": {"deploymentTarget": {"iOS": "17.4"}},
            "settings": {"base": {
                "CLANG_ENABLE_OBJC_ARC": "YES", "CLANG_ENABLE_MODULES": "YES",
                "CODE_SIGNING_ALLOWED": "YES", "CODE_SIGN_IDENTITY": "-",
                "GENERATE_INFOPLIST_FILE": "YES", "HEADER_SEARCH_PATHS": f'"{CLASSES}" "{LIBRETRO}" "{include.parent}"',
                "IPHONEOS_DEPLOYMENT_TARGET": "17.4",
            }},
            "targets": {
                "UnifiedCatalogueHost": {
                    "type": "application", "platform": "iOS",
                    "sources": [str(directory / "main.m"), str(CLASSES / "NeoUnifiedCheatCatalog.m"),
                                str(CLASSES / "NeoUnifiedCheatBrowser.m"),
                                {"path": str(POD / "Resources/labels.json"), "buildPhase": "resources"}]
                                + [str(LIBRETRO / name) for name in ("LibretroCheatMenu.m", "LibretroCheats.m", "LibretroCheatCatalog.m", "LibretroSessionMenu.m", "LibretroOrientation.m")],
                    "dependencies": frameworks,
                    "settings": {"base": {"PRODUCT_BUNDLE_IDENTIFIER": "org.neostation.unifiedcheatuitest.host",
                        "INFOPLIST_KEY_UILaunchScreen_Generation": "YES"}},
                },
                "UnifiedCatalogueTests": {
                    "type": "bundle.unit-test", "platform": "iOS",
                    "sources": [str(ROOT / "test/unified_catalog_browser_ui_tests.m")],
                    "dependencies": [{"target": "UnifiedCatalogueHost"}] + frameworks,
                    "settings": {"base": {"PRODUCT_BUNDLE_IDENTIFIER": "org.neostation.unifiedcheatuitest.tests",
                        "TEST_HOST": "$(BUILT_PRODUCTS_DIR)/UnifiedCatalogueHost.app/UnifiedCatalogueHost", "BUNDLE_LOADER": "$(TEST_HOST)"}},
                },
            },
            "schemes": {"UnifiedCatalogueBrowser": {
                "build": {"targets": {"UnifiedCatalogueHost": "all", "UnifiedCatalogueTests": "test"}},
                "test": {"targets": ["UnifiedCatalogueTests"]},
            }},
        }
        spec_path = directory / "project.json"
        spec_path.write_text(json.dumps(project))
        subprocess.run(["xcodegen", "generate", "--spec", str(spec_path), "--project", str(directory)], check=True)
        command = ["xcodebuild", "test", "-project", str(directory / "UnifiedCatalogueBrowser.xcodeproj"),
                   "-scheme", "UnifiedCatalogueBrowser", "-destination", "platform=iOS Simulator,id=" + device["udid"],
                   "-destination-timeout", "60", "-parallel-testing-enabled", "NO", "-test-timeouts-enabled", "YES",
                   "-default-test-execution-time-allowance", "60", "-maximum-test-execution-time-allowance", "120"]
        if result_path:
            result_path = result_path.resolve()
            result_path.parent.mkdir(parents=True, exist_ok=True)
            command += ["-resultBundlePath", str(result_path)]
        command += ["CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_IDENTITY=-", "DEVELOPMENT_TEAM="]
        subprocess.run(command, check=True, timeout=600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--result", type=Path)
    arguments = parser.parse_args()
    contracts()
    if arguments.native:
        native(arguments.result)
