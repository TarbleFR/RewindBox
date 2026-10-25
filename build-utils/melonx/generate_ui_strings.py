"""Reuse RewindBox's twelve translations and add Melo-Controller's labels."""
import json
from pathlib import Path


def generate(root, output):
    shared = json.loads((root / 'tools/touch_layout/strings.json').read_text())
    extra = json.loads((root / 'build-utils/melonx/ui-strings.json').read_text())
    assert extra['locales'] == shared['locales']
    aliases = {
        'Edit touch controls': 'editTouchControls', 'Hide touch controls when a controller is connected': 'hideWithController',
        'On': 'on', 'Off': 'off', 'Save': 'save', 'Cancel': 'cancel', 'Size': 'size', 'Opacity': 'opacity',
        'Reset': 'resetControl', 'Reset All': 'resetLayout', 'Reset This Layout?': 'resetLayout',
        'Default Layout': 'stockLayout', 'Current Game': 'scopeThisGame', 'Custom Layout': 'customized',
        'Using Default': 'stockLayout', 'Reset to Default Layout': 'resetLayout',
        'Delete Custom Layout': 'useGeneralLayout', 'Whole Controller': 'touchControls',
        'Controller Size': 'size', 'Layout Options': 'touchControls', 'Layout Actions': 'elements',
        'Available Layouts': 'generalLayout', 'Left Stick': 'leftStick', 'Right Stick': 'rightStick',
        'Tap a button or stick to edit it, drag it to move it.': 'hint',
        'Every button and stick goes back to its default position, size and options.': 'resetLayout',
        'This will delete the custom layout for this game and revert to the default layout.': 'useGeneralLayout',
    }
    values = {}
    for index, locale in enumerate(extra['locales']):
        values[locale] = {key: shared['values'][locale][value] for key, value in aliases.items()}
        for key, row in extra['rows'].items():
            assert len(row) == 12 and all(isinstance(v,str) and v.strip() for v in row), key
            values[locale][key] = row[index]
        values[locale]['Copy Layout From…'] = values[locale]['Copy Layout']
        for symbol in ['A','B','X','Y','L','R','ZL','ZR','Minus','Plus','Home','OK']:
            values[locale][symbol] = {'Minus':'−','Plus':'+','Home':'HOME'}.get(symbol,symbol)
        for key, symbol in [('D-Pad Up','↑'),('D-Pad Down','↓'),('D-Pad Left','←'),('D-Pad Right','→')]:
            values[locale][key] = shared['values'][locale]['dpad'] + ' ' + symbol
        for key, label in [('Left Shoulder','L1 / LB'),('Right Shoulder','R1 / RB'),('Left Trigger','L2 / LT'),('Right Trigger','R2 / RT')]:
            values[locale][key] = label
        for key, base in [('Left Stick Button','leftStick'),('Right Stick Button','rightStick'),('Stick Button','controlStick')]:
            values[locale][key] = shared['values'][locale][base]
    quote = lambda x: json.dumps(x,ensure_ascii=False)
    dictionary = '[\n' + ',\n'.join('  '+quote(locale)+': [\n'+',\n'.join('    '+quote(k)+': '+quote(v) for k,v in sorted(texts.items()))+'\n  ]' for locale,texts in values.items()) + '\n]'
    output.write_text('''// Generated from RewindBox twelve-language sources. Do not edit.
import Foundation
enum MeloNXStrings {
    static var locale = "en"
    static let values: [String: [String: String]] = ''' + dictionary + '''
    static func canonical(_ value: String) -> String {
        let lower = value.replacingOccurrences(of:"-",with:"_").lowercased()
        if lower.hasPrefix("zh") { return lower.contains("hant") || lower.hasSuffix("_tw") || lower.hasSuffix("_hk") || lower.hasSuffix("_mo") ? "zh_Hant" : "zh" }
        let language = String(lower.split(separator:"_").first ?? "en")
        return values[language] == nil ? "en" : language
    }
}
func MeloNXText(_ key: String) -> String {
    MeloNXStrings.values[MeloNXStrings.canonical(MeloNXStrings.locale)]?[key] ?? MeloNXStrings.values["en"]?[key] ?? key
}
''')
