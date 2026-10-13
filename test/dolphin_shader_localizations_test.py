"""Every text of the Dolphin post-processing page (Build 450), in the twelve languages.

native/dolphin_shaders/labels.json is the source; the native catalog
DOLShaderLabels.h is its canonical generation. Checked: the twelve
NeoStation languages and nothing else, the same keys everywhere, non-empty
texts, the same placeholders as English, no English text left in another
language ("OK" and the "{option} ({index})" pattern aside), a traditional Chinese
catalog of its own, the region rules of DOLShaderText (zh-TW / zh-HK /
zh-MO / zh-Hant -> traditional), and every key the bridge asks for exists.
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'
rows = json.loads((ROOT / 'native/dolphin_shaders/labels.json').read_text(encoding='utf-8'))
locales = {'en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko'}
assert set(rows) == locales, sorted(set(rows) ^ locales)
keys = set(rows['en'])
for locale, values in rows.items():
    assert set(values) == keys, (locale, sorted(set(values) ^ keys))
    for key, value in values.items():
        assert isinstance(value, str) and value.strip(), (locale, key)
        assert set(re.findall(r'\{\w+\}', value)) == set(re.findall(r'\{\w+\}', rows['en'][key])), (locale, key)
        # "OK" and the "{option} ({index})" pattern are written the same way.
        if locale != 'en' and key not in {'component', 'ok'}:
            assert value != rows['en'][key], f'{locale}: {key} is the English text'
# Texts written the same way in both scripts ("Dolphin 效果", "取消").
for key in keys - {'component', 'cancel', 'official', 'ok'}:
    assert rows['zh_Hant'][key] != rows['zh'][key], f'zh_Hant reuses the simplified text of {key}'

objc = lambda value: '@' + json.dumps(value, ensure_ascii=False)
expected = '\n'.join(objc(locale) + ': @{' + ','.join(objc(key) + ': ' + objc(value) for key, value in values.items()) + '},'
                     for locale, values in rows.items())
header = (CLASSES / 'DOLShaderLabels.h').read_text(encoding='utf-8')
assert header.split('values=@{\n', 1)[1].split('\n };});', 1)[0] == expected, 'regenerate DOLShaderLabels.h'
for region in ('zh_Hant', 'zh_TW', 'zh_HK', 'zh_MO'):
    assert f'[language hasPrefix:@"{region}"]' in header, region

# Keys the bridge asks for: DOLShaderText(@"key", ...) anywhere, and every
# string literal of the page that is a key (it passes keys through
# text:/text:values:, sometimes in a conditional expression).
used = set()
for path in sorted(CLASSES.glob('*')):
    if path.suffix in {'.h', '.mm', '.m'}:
        source = path.read_text(encoding='utf-8')
        used |= set(re.findall(r'DOLShaderText\(@"(\w+)"', source))
        if path.name == 'DOLShaderSettings.mm':
            literals = set(re.findall(r'(?:text:|\?|:)\s*@"(\w+)"', source))
            used |= literals & keys
            asked = set(re.findall(r'text:@"(\w+)"', source))
            assert asked <= keys, sorted(asked - keys)
assert used, 'the bridge uses the catalog'
assert used <= keys, sorted(used - keys)
assert keys - used == set(), f'texts nobody shows: {sorted(keys - used)}'
print(f'PASS Dolphin shader page locales: 12 catalogs, {len(keys)} keys, {len(used)} used by the bridge, '
      'matching placeholders, canonical native generation')
