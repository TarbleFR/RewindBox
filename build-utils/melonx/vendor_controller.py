#!/usr/bin/env python3
"""Adapt the pinned original controller/editor and mapping data model only."""
import hashlib
import json
import re
from pathlib import Path
import shutil
import sys
from generate_ui_strings import generate

root = Path(__file__).resolve().parents[2]
controller, engine = [Path(p).resolve() for p in sys.argv[1:]]
target = root / 'packages/melonx_internal_bridge/ios/Controller'
assert not target.exists(), 'Refuse to overwrite an existing vendor directory'
shutil.copytree(controller / 'Sources/Melo-Controller', target)
layout = target / 'Layout/LayoutManager.swift'
text = layout.read_text()
old = 'return docDir.appendingPathComponent("controller_layouts")'
assert text.count(old) == 1
text = text.replace(old, 'return docDir.appendingPathComponent("MeloNX/controller_layouts")')
layout.write_text(text)
view = target / 'ControllerView.swift'
text = view.read_text()
for key in ['On-ScreenControllerScale', 'stickButton']:
    assert text.count('@AppStorage("' + key + '")') == 1
    text = text.replace('@AppStorage("' + key + '")', '@AppStorage("rewindbox.melonx.' + key + '")')
view.write_text(text)
for source in ['Core/Models/ControllerMapping.swift', 'Core/Models/VirtualControllerButton.swift']:
    original = engine / 'src/MeloNX/MeloNX' / source
    text = original.read_text().replace('import Melo_Controller\n', '')
    # Swift uses basenames as private declaration discriminators; the upstream
    # model already has a VirtualControllerButton.swift in its Models folder.
    (target / ('MeloNX' + original.name)).write_text(text)
# Isolate all of the original preference keys, not only the top-level scale.
for path in target.rglob('*.swift'):
    text = path.read_text()
    text = re.sub(r'@AppStorage\("(?!rewindbox\.melonx\.)([^"\n]+)"\)', r'@AppStorage("rewindbox.melonx.\1")', text)
    text = text.replace('forKey: "joystickDpad-', 'forKey: "rewindbox.melonx.joystickDpad-')
    path.write_text(text)
# Optional Codable properties preserve previously exported original layouts.
# Opacity and hit-testing change together; hidden controls cannot press games.
model = target / 'Models/Layout.swift'
text = model.read_text()
assert text.count('    var hidden: Bool = false') == 2
text = text.replace('    var hidden: Bool = false', '    var hidden: Bool = false\n    var opacity: CGFloat? = nil')
model.write_text(text)
button = target / 'Layout/CopyLayoutView.swift'
text = button.read_text()
assert text.count('.opacity(0)') == 1
text = text.replace('.opacity(0)', '.opacity(0)\n                        .allowsHitTesting(false)')
old = '                        .offset(layout.buttons[button.id]?.offset ?? .zero)'
assert text.count(old) == 2
text = text.replace(old, old + '\n                        .opacity(Double(layout.buttons[button.id]?.opacity ?? 1))')
button.write_text(text)
joystick = target / 'Joystick/JoystickView.swift'
text = joystick.read_text()
old = '                .offset(layout.joysticks[id]?.offset ?? .zero)'
assert text.count(old) == 1
text = text.replace(old, old + '''
                .opacity(layout.joysticks[id]?.hidden == true ? 0 : Double(layout.joysticks[id]?.opacity ?? 1))
                .allowsHitTesting(layout.joysticks[id]?.hidden != true)''')
joystick.write_text(text)
editor = target / 'Layout/LayoutEditorView.swift'
text = editor.read_text()
for kind, identifier, value in [('buttons', 'buttonId', 'ButtonLayout'), ('joysticks', 'joystickId', 'JoystickLayout')]:
    anchor = f'            EditorToggleRow(\n                title: "Hide {"Button" if kind == "buttons" else "Stick"}",'
    assert text.count(anchor) == 1
    opacity = f'''            EditorSliderRow(
                title: "Opacity",
                value: Binding(get: {{ layout.{kind}[{identifier}]?.opacity ?? 1 }},
                               set: {{ layout.{kind}[{identifier}, default: {value}()].opacity = $0 }}),
                range: 0.1...1.0, step: 0.05
            )

'''
    text = text.replace(anchor, opacity + anchor)
editor.write_text(text)
for path in target.rglob('*.swift'):
    text = path.read_text()
    # UI literals only: leave SF Symbols, identifiers, URLs and persistence
    # keys intact. Shared row labels are translated when rendered as well.
    text = re.sub(r'(Text|Button|Label|Picker|Toggle|\.navigationTitle|\.alert)\("([^"\\]*)"',
                  lambda m: m[1] + '(MeloNXText("' + m[2] + '")', text)
    text = re.sub(r'(title|subtitle): "([^"\\]*)"', lambda m: m[1] + ': MeloNXText("' + m[2] + '")', text)
    text = re.sub(r'String\(localized: "([^"\\]*)"\)', lambda m: 'MeloNXText("' + m[1] + '")', text)
    text = text.replace('Text(title)', 'Text(MeloNXText(title))').replace('Text(subtitle)', 'Text(MeloNXText(subtitle))')
    text = text.replace('Text(iscool ? "Right Stick" : "Left Stick")', 'Text(MeloNXText(iscool ? "Right Stick" : "Left Stick"))')
    path.write_text(text)
generate(root, target / 'MeloNXStrings.swift')
# Corresponding unmodified sources and original notices are retained in the
# source artifact. The generated directory is an input to packaging/typecheck.
receipt = {'controller': json.loads((root / 'build-utils/melonx/source.json').read_text())['controller'],
           'engine': json.loads((root / 'build-utils/melonx/source.json').read_text())['revision'],
           'files': {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*.swift'))}}
(target / 'adaptation.json').write_text(json.dumps(receipt, indent=2) + '\n')

from vendor_memory import generate as generate_memory
generate_memory(root, Path(sys.argv[2]).resolve())
