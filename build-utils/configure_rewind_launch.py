#!/usr/bin/env python3
"""Install the static, black native half of Rewind Motion after host generation."""
import argparse
import json
import plistlib
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def configure(root=ROOT):
    runner = root / 'ios/Runner'
    base = runner / 'Base.lproj'
    base.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'build-utils/rewind-motion/LaunchScreen.storyboard', base / 'LaunchScreen.storyboard')
    target = runner / 'Assets.xcassets/RewindMark.imageset'
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'build-utils/rewind-motion/RewindMark.pdf', target / 'RewindMark.pdf')
    (target / 'Contents.json').write_text(json.dumps({
        'images': [{'filename': 'RewindMark.pdf', 'idiom': 'universal'}],
        'info': {'author': 'xcode', 'version': 1},
        'properties': {'preserves-vector-representation': True},
    }, indent=2) + '\n')
    plist = runner / 'Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info['UILaunchStoryboardName'] = 'LaunchScreen'
    plist.write_bytes(plistlib.dumps(info, sort_keys=False))
    # The generated Flutter host view must not flash white before the first frame.
    main = base / 'Main.storyboard'
    if main.exists():
        tree = ET.parse(main)
        for view in tree.findall('.//view'):
            for color in view.findall("color[@key='backgroundColor']"):
                color.attrib.clear()
                color.attrib.update(key='backgroundColor', red='0', green='0', blue='0', alpha='1', colorSpace='custom', customColorSpace='sRGB')
        tree.write(main, encoding='UTF-8', xml_declaration=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    configure(parser.parse_args().root)
