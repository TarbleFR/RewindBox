"""Native/Flutter logo parity and repeatable launch-host resource installation."""
from pathlib import Path
import hashlib
import importlib.util
import json
import plistlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
import fitz
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / 'build-utils/rewind-motion'
spec = importlib.util.spec_from_file_location('launch', ROOT / 'build-utils/configure_rewind_launch.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)

class RewindLaunch(unittest.TestCase):
    def test_supplied_geometry_matches_pdf_and_flutter(self):
        mark = json.loads((ASSET / 'mark.json').read_text())
        self.assertEqual(hashlib.sha256((ASSET / 'official-logo.jpg').read_bytes()).hexdigest(), mark['source_sha256'])
        source = np.pad(np.asarray(Image.open(ASSET / 'official-logo.jpg').convert('L')) > 127.5, ((0, 0), (0, 1)))
        doc = fitz.open(ASSET / 'RewindMark.pdf')
        pix = doc[0].get_pixmap(alpha=True)
        mask = np.frombuffer(pix.samples, dtype=np.uint8).reshape(2048, 2048, 4)[:, :, 3] > 127
        overlap = (mask & source).sum() / (mask | source).sum()
        self.assertGreater(overlap, .999, f'Official white-contour overlap: {overlap}')
        dart = (ROOT / 'lib/widgets/rewind_mark_path.dart').read_text()
        for points in mark['paths']:
            for index, (x, y) in enumerate(points):
                self.assertIn(f"..{'moveTo' if index == 0 else 'lineTo'}({x}, {y})", dart)
        self.assertEqual(dart.count('..close()'), 2)

    def test_static_launch_contains_no_text_and_matches_flutter_constraints(self):
        tree = ET.parse(ASSET / 'LaunchScreen.storyboard')
        self.assertEqual(tree.getroot().get('launchScreen'), 'YES')
        self.assertEqual(tree.findall('.//label'), [])
        self.assertEqual(len(tree.findall('.//imageView')), 1)
        constraints = {c.get('id'): c for c in tree.findall('.//constraint')}
        self.assertEqual(constraints['mark-cap'].get('constant'), '232')
        self.assertEqual(constraints['mark-width'].get('multiplier'), '0.58')
        self.assertEqual(constraints['mark-height'].get('multiplier'), '0.58')
        for c in ['mark-center-x', 'mark-center-y']:
            self.assertEqual(constraints[c].get('secondItem'), 'rewind-background')
        self.assertNotIn('safeArea', (ASSET / 'LaunchScreen.storyboard').read_text())

    def test_install_is_idempotent_and_keeps_other_host_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); runner = root / 'ios/Runner'; base = runner / 'Base.lproj'
            base.mkdir(parents=True)
            (runner / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.neogamelab.neostation', 'Other': 42}))
            (base / 'Main.storyboard').write_text('<document><view><color key="backgroundColor" white="1" alpha="1"/></view></document>')
            launch.configure(root)
            first = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            launch.configure(root)
            self.assertEqual(first, {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            info = plistlib.loads((runner / 'Info.plist').read_bytes())
            self.assertEqual(info, {'CFBundleIdentifier': 'com.neogamelab.neostation', 'Other': 42, 'UILaunchStoryboardName': 'LaunchScreen'})
            color = ET.parse(base / 'Main.storyboard').find('.//color')
            self.assertEqual(color.get('red'), '0')
            self.assertEqual((runner / 'Assets.xcassets/RewindMark.imageset/RewindMark.pdf').read_bytes(), (ASSET / 'RewindMark.pdf').read_bytes())

if __name__ == '__main__':
    unittest.main(verbosity=2)
