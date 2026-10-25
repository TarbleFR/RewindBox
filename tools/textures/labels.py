#!/usr/bin/env python3
"""Builds the twelve-language labels of the HD textures pages.

Sources: labels_en_fr.py, labels_es_de_it_pt.py, labels_ru_id.py and
labels_cjk.py (native page, packages/neo_texture_catalog/ios/Resources/
labels.json) and DART below (the Flutter rows that open the page,
lib/l10n/texture_catalog_locale.dart).

  python3 tools/textures/labels.py           writes both files
  python3 tools/textures/labels.py --check   fails when they are stale or invalid

Checks: the twelve RewindBox languages (en, es, ru, zh, zh_Hant, pt, fr, de,
it, id, ja, ko) have exactly the English keys, no empty text, the same
{placeholders} as English, and Traditional Chinese has its own text.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
NATIVE_OUT = ROOT / 'packages/neo_texture_catalog/ios/Resources/labels.json'
DART_OUT = ROOT / 'lib/l10n/texture_catalog_locale.dart'
LANGUAGES = ['en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko']

# Rows of the library and of a game's options that open the page.
DART = {
    'en': {'menuTitle': 'HD textures', 'menuSubtitle': 'Download, install and switch on HD texture packs for this game',
           'consoleSubtitle': 'HD texture packs for this console', 'openFailed': 'The HD textures page could not be opened.'},
    'es': {'menuTitle': 'Texturas HD', 'menuSubtitle': 'Descarga, instala y activa paquetes de texturas HD para este juego',
           'consoleSubtitle': 'Paquetes de texturas HD para esta consola', 'openFailed': 'No se pudo abrir la página Texturas HD.'},
    'ru': {'menuTitle': 'HD-текстуры', 'menuSubtitle': 'Загрузка, установка и включение наборов HD-текстур для этой игры',
           'consoleSubtitle': 'Наборы HD-текстур для этой консоли', 'openFailed': 'Не удалось открыть страницу HD-текстур.'},
    'zh': {'menuTitle': '高清纹理', 'menuSubtitle': '为此游戏下载、安装并启用高清纹理包',
           'consoleSubtitle': '此主机的高清纹理包', 'openFailed': '无法打开高清纹理页面。'},
    'zh_Hant': {'menuTitle': '高畫質材質', 'menuSubtitle': '為此遊戲下載、安裝並啟用高畫質材質包',
                'consoleSubtitle': '此主機的高畫質材質包', 'openFailed': '無法開啟高畫質材質頁面。'},
    'pt': {'menuTitle': 'Texturas HD', 'menuSubtitle': 'Baixe, instale e ative pacotes de texturas HD para este jogo',
           'consoleSubtitle': 'Pacotes de texturas HD para este console', 'openFailed': 'Não foi possível abrir a página Texturas HD.'},
    'fr': {'menuTitle': 'Textures HD', 'menuSubtitle': 'Télécharger, installer et activer des packs de textures HD pour ce jeu',
           'consoleSubtitle': 'Packs de textures HD pour cette console', 'openFailed': 'La page Textures HD n’a pas pu s’ouvrir.'},
    'de': {'menuTitle': 'HD-Texturen', 'menuSubtitle': 'HD-Texturpakete für dieses Spiel herunterladen, installieren und aktivieren',
           'consoleSubtitle': 'HD-Texturpakete für diese Konsole', 'openFailed': 'Die Seite HD-Texturen konnte nicht geöffnet werden.'},
    'it': {'menuTitle': 'Texture HD', 'menuSubtitle': 'Scarica, installa e attiva pacchetti di texture HD per questo gioco',
           'consoleSubtitle': 'Pacchetti di texture HD per questa console', 'openFailed': 'Impossibile aprire la pagina Texture HD.'},
    'id': {'menuTitle': 'Tekstur HD', 'menuSubtitle': 'Unduh, pasang, dan aktifkan paket tekstur HD untuk game ini',
           'consoleSubtitle': 'Paket tekstur HD untuk konsol ini', 'openFailed': 'Halaman Tekstur HD tidak dapat dibuka.'},
    'ja': {'menuTitle': 'HDテクスチャ', 'menuSubtitle': 'このゲームのHDテクスチャパックをダウンロード、インストールして有効にします',
           'consoleSubtitle': 'このゲーム機のHDテクスチャパック', 'openFailed': 'HDテクスチャのページを開けませんでした。'},
    'ko': {'menuTitle': 'HD 텍스처', 'menuSubtitle': '이 게임의 HD 텍스처 팩을 다운로드하고 설치하여 켭니다',
           'consoleSubtitle': '이 콘솔용 HD 텍스처 팩', 'openFailed': 'HD 텍스처 페이지를 열 수 없습니다.'},
}


def load(name):
    namespace = {}
    path = HERE / name
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), namespace)
    return namespace


def native_labels():
    sources = {}
    for module, mapping in (('labels_en_fr.py', {'en': 'EN', 'fr': 'FR'}),
                            ('labels_es_de_it_pt.py', {'es': 'ES', 'de': 'DE', 'it': 'IT', 'pt': 'PT'}),
                            ('labels_ru_id.py', {'ru': 'RU', 'id': 'ID'}),
                            ('labels_cjk.py', {'zh': 'ZH', 'zh_Hant': 'ZH_HANT', 'ja': 'JA', 'ko': 'KO'})):
        namespace = load(module)
        for language, variable in mapping.items():
            sources[language] = namespace[variable]
    return sources


PLACEHOLDER = re.compile(r'\{([A-Za-z]+)\}')


def check(name, labels):
    problems = []
    if sorted(labels) != sorted(LANGUAGES):
        problems.append(f'{name}: languages {sorted(labels)} != {sorted(LANGUAGES)}')
        return problems
    english = labels['en']
    for language in LANGUAGES:
        table = labels[language]
        missing, extra = set(english) - set(table), set(table) - set(english)
        if missing or extra:
            problems.append(f'{name} {language}: missing {sorted(missing)} extra {sorted(extra)}')
        for key, text in table.items():
            if not isinstance(text, str) or not text.strip():
                problems.append(f'{name} {language}.{key}: empty')
                continue
            if key in english and set(PLACEHOLDER.findall(text)) != set(PLACEHOLDER.findall(english[key])):
                problems.append(f'{name} {language}.{key}: placeholders {sorted(set(PLACEHOLDER.findall(text)))} '
                                f'!= {sorted(set(PLACEHOLDER.findall(english[key])))}')
    # Traditional Chinese is its own catalogue, not the Simplified one renamed.
    same = [key for key in english if labels['zh_Hant'].get(key) == labels['zh'].get(key) and
            re.search(r'[一-鿿]', labels['zh'].get(key, ''))]
    if len(same) > len(english) // 4:
        problems.append(f'{name} zh_Hant repeats zh for {len(same)} keys: {same[:8]}')
    return problems


def dart_source(labels):
    lines = [
        '// Generated by tools/textures/labels.py: do not edit by hand.',
        "import 'package:flutter/widgets.dart';",
        '',
        '/// Labels of the rows that open the HD textures page (twelve languages).',
        'abstract final class TextureCatalogLocale {',
        '  static const Map<String, Map<String, String>> labels = {',
    ]
    for language in LANGUAGES:
        lines.append(f"    '{language}': {{")
        for key in sorted(labels[language]):
            # A JSON string is a valid Dart string once '$' (interpolation) is escaped.
            literal = json.dumps(labels[language][key], ensure_ascii=False).replace('$', '\\$')
            lines.append(f"      '{key}': {literal},")
        lines.append('    },')
    lines += [
        '  };',
        '',
        '  /// The RewindBox catalogue key of a locale (zh_Hant for Taiwan, Hong Kong and Macao).',
        '  static String localeKey(Locale locale) {',
        '    final language = locale.languageCode.toLowerCase();',
        "    if (language == 'zh') {",
        "      final script = locale.scriptCode?.toLowerCase();",
        "      final country = locale.countryCode?.toUpperCase();",
        "      if (script == 'hant' || country == 'TW' || country == 'HK' || country == 'MO') return 'zh_Hant';",
        "      return 'zh';",
        '    }',
        "    return labels.containsKey(language) ? language : 'en';",
        '  }',
        '',
        '  static String text(Locale locale, String key) =>',
        "      labels[localeKey(locale)]?[key] ?? labels['en']![key] ?? key;",
        '',
        '  /// The locale identifier handed to the native page (zh-Hant keeps its script).',
        '  static String nativeLocale(Locale locale) {',
        '    final key = localeKey(locale);',
        "    return key == 'zh_Hant' ? 'zh-Hant' : key;",
        '  }',
        '}',
        '',
    ]
    return '\n'.join(lines)


def main():
    native = native_labels()
    problems = check('native', native) + check('dart', DART)
    if problems:
        print('\n'.join(problems))
        raise SystemExit(1)
    native_json = json.dumps(native, ensure_ascii=False, indent=1, sort_keys=True) + '\n'
    dart = dart_source(DART)
    if '--check' in sys.argv:
        stale = [str(path.relative_to(ROOT)) for path, text in ((NATIVE_OUT, native_json), (DART_OUT, dart))
                 if not path.exists() or path.read_text(encoding='utf-8') != text]
        if stale:
            print('Stale generated labels (run tools/textures/labels.py):', ', '.join(stale))
            raise SystemExit(1)
        print(f'PASS texture labels: {len(LANGUAGES)} languages, {len(native["en"])} native and {len(DART["en"])} Flutter keys')
        return
    NATIVE_OUT.parent.mkdir(parents=True, exist_ok=True)
    NATIVE_OUT.write_text(native_json, encoding='utf-8')
    DART_OUT.write_text(dart, encoding='utf-8')
    print(f'Wrote {NATIVE_OUT.relative_to(ROOT)} and {DART_OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
