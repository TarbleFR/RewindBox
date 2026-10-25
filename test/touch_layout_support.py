"""Build 484 test support: the neo_touch_layout pod as other pods see it.

A pod that depends on neo_touch_layout imports its public headers as
<neo_touch_layout/Name.h>; the harnesses stage exactly those headers (the
podspec's public_header_files) under include/neo_touch_layout and compile the
pod's sources next to the code under test.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
POD = ROOT / 'packages/neo_touch_layout/ios'
CLASSES = POD / 'Classes'
PUBLIC = CLASSES / 'Public'


def public_headers():
    podspec = (POD / 'neo_touch_layout.podspec').read_text(encoding='utf-8')
    assert "s.public_header_files = 'Classes/Public/*.h'" in podspec, 'neo_touch_layout public headers moved'
    return sorted(PUBLIC.glob('*.h'))


def stage_touch_layout(include: Path) -> Path:
    staged = include / 'neo_touch_layout'
    staged.mkdir(parents=True, exist_ok=True)
    headers = public_headers()
    for header in headers:
        shutil.copyfile(header, staged / header.name)
    print(f'Staged {len(headers)} public neo_touch_layout header(s) as <neo_touch_layout/...>', flush=True)
    return include


def sources(include_plugin: bool = False):
    """The pod's Objective-C sources; the Flutter plugin needs Flutter."""
    return sorted(path for path in CLASSES.glob('*.m')
                  if include_plugin or path.name != 'NeoTouchLayoutPlugin.m')
