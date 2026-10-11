#!/usr/bin/env python3
"""Source contract of the embedded-console Flutter pages (consoles, skins,
unified skin catalogs) and of their two entry points.

- No hard-coded user-visible text in lib/screens/libretro/*.dart or in the
  playlist actions: every label comes from LibretroLocale (twelve languages),
  product names and skin data come from variables.
- Every LibretroLocale key those files name exists in the English catalog
  (test/libretro_locale_test.dart checks that the twelve maps share their keys).
- Entry points (Build 440): the consoles tab of the main bar (a console with
  a "+", drawn after Systems and before Search on iOS) shows the consoles
  page, and the playlist actions keep their Skins item. The former entry,
  Settings › Folders › Embedded consoles, is gone: the directories page is
  byte-for-byte the reviewed a5650b9b version again (this replaces the
  Build 427 contract that checked the item inside `embedded_consoles`
  markers; the tab's behaviour is proven by test/nav_tabs_test.dart,
  test/main_menu_tab_strip_test.dart, test/libretro_main_menu_test.dart and
  test/libretro_consoles_tab_test.dart).
- The playlist actions keep their contract (integrated_import_tab_contract)
  and gain the Skins item.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREENS = sorted((ROOT / 'lib/screens/libretro').glob('*.dart'))
PLAYLIST = 'lib/widgets/libretro_internal_playlist_actions.dart'
DIRECTORIES = 'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart'
REVIEWED = 'a5650b9b'
MARKER = 'LIBRETRO_INTERNAL_BEGIN: embedded_consoles'


def read(relative):
    return (ROOT / relative).read_text(encoding='utf-8')


def require(condition, message):
    if not condition:
        raise SystemExit('libretro frontend UI contract: ' + message)


def strip_comments(source):
    """Removes // comments (doc comments included) so prose never counts as UI."""
    return re.sub(r'(?m)^\s*//.*$', '', source)


def english_keys():
    source = read('lib/l10n/libretro_locale.dart')
    start = source.index("    'en': {")
    end = source.index('\n    },', start)
    return set(re.findall(r"^\s*'([A-Za-z0-9_]+)':", source[start:end], re.M))


EN = english_keys()
require(len(EN) > 200, 'English LibretroLocale map not found')

# 1. Pages exist and are wired.
names = {path.name for path in SCREENS}
for expected in ('libretro_consoles_screen.dart', 'libretro_skin_manager_screen.dart',
                 'libretro_skin_catalog_screen.dart'):
    require(expected in names, expected + ' missing')

LITERAL_TEXT = re.compile(r"""\bText\(\s*r?['"]""")
LITERAL_NAMED = re.compile(
    r"""\b(tooltip|semanticsLabel|semanticLabel|labelText|hintText|helperText|errorText|"""
    r"""prefixText|suffixText|counterText|title|message|label)\s*:\s*r?['"]""")
KEY_CALL = re.compile(
    r"""(?:\b_t|\b_f|LibretroLocale\.text|LibretroLocale\.formatContext)\(\s*(?:context\s*,\s*)?'([A-Za-z0-9_]+)'""")

ui_files = [path.relative_to(ROOT).as_posix() for path in SCREENS] + [PLAYLIST]
for relative in ui_files:
    code = strip_comments(read(relative))
    require(not LITERAL_TEXT.search(code), f'{relative}: Text() with a literal string')
    hit = LITERAL_NAMED.search(code)
    require(hit is None, f'{relative}: literal string for {hit.group(1) if hit else ""}:')
    require('AppLocale.' not in code, f'{relative}: texts come from LibretroLocale')
    for key in KEY_CALL.findall(code):
        require(key in EN, f'{relative}: LibretroLocale key {key!r} is not in the English catalog')

manager = read('lib/screens/libretro/libretro_skin_manager_screen.dart')
catalog = read('lib/screens/libretro/libretro_skin_catalog_screen.dart')
consoles = read('lib/screens/libretro/libretro_consoles_screen.dart')

# Every page takes the controller from the screen underneath and gives it back.
require('GamepadNavigationManager.pushLayer(' in manager and 'GamepadNavigationManager.popLayer(' in manager,
        'pages register a gamepad navigation layer')
for name, source in (('manager', manager), ('catalog', catalog), ('consoles', consoles)):
    require(re.search(r'with\s+LibretroPageNavigation<', source), f'{name} page uses LibretroPageNavigation')
require('ActivateIntent' in manager and 'focusInDirection' in manager, 'D-pad moves the focus, A activates it')

# Skins: translated import remarks and refusals, confirmed deletion and
# replacement, licence notice, previews from the native renderer.
require('LibretroLocale.skinErrorKeys' in manager and 'LibretroLocale.skinMessage(' in manager,
        'native skin codes are translated through LibretroLocale')
for key in ('skinsDeleteConfirm', 'skinsReplaceConfirm', 'skinsImportRemarks', 'skinsLicenseNotice',
            'skinsSelectedPortrait', 'skinsSelectedLandscape', 'skinsAuthorUnknown', 'skinsCredits',
            'skinsLicense', 'skinsForConsoles', 'skinsResetDefault', 'skinsUseBoth'):
    require(f"'{key}'" in manager, f'manager shows {key}')
require(manager.count('ConfirmActionDialog.show(') >= 2, 'delete and replace are confirmed')
require('skins.discard(' in manager, 'a declined replacement is discarded')
require('.preview(' in manager and 'FutureBuilder<Uint8List?>' in manager, 'previews come from the native renderer')
require('pickAndImport()' in manager, 'Files import goes through LibretroSkinService')

# Catalogs: same import pipeline, every state translated.
# Unified catalogs (October 2026): an entry whose link is not a skin file is
# no longer shown with a disabled Install button; the central iPhone filter
# (LibretroSkinCatalogs) refuses it with SKIN_COMPAT_NOT_DIRECT, the page
# hides it and shows the translated reason (catalogNotDirect) among the
# hidden entries. This replaces the former check of 'catalogNotDirect' and
# 'isDirectDownload' in the page itself; the behaviour is proven by
# test/libretro_skin_catalogs_test.dart and test/libretro_skin_manager_test.dart.
catalogs_service = read('lib/services/libretro_skin_catalogs.dart')
compatibility = read('lib/services/libretro_skin_compatibility.dart')
require('showLibretroSkinImportResult(' in catalog, 'catalog installs show the manager messages')
for key in ('catalogLoading', 'catalogFailed', 'catalogRetry', 'catalogEmpty', 'catalogSearch',
            'catalogInstall', 'catalogInstalling', 'catalogDownloads', 'catalogSourcesAll',
            'catalogOrientationAny', 'catalogFavorites', 'catalogFavoriteAdd', 'catalogFavoriteRemove',
            'catalogChecking', 'catalogHidden', 'catalogShowHidden', 'catalogHideHidden', 'catalogSource',
            'catalogSourceUnavailable', 'catalogConverted'):
    require(f"'{key}'" in catalog, f'catalog shows {key}')
require('LibretroSkinCatalogs.hidden(' in catalog and 'libretroSkinVerdictRows(' in catalog,
        'catalog entries pass the central iPhone filter and show its verdict and reasons')
require('isDirectDownload' in catalogs_service and 'LibretroSkinCompatibility.notDirect' in catalogs_service,
        'a link that is not a skin file is refused by the catalogs')
require("notDirect: 'catalogNotDirect'" in compatibility, 'that refusal is explained with catalogNotDirect')
require('errorBuilder' in catalog, 'broken thumbnails')

# Consoles: every console, import into one of the user's own library folders
# (10 October 2026: never a second library next to theirs; NeoStation's roms
# folder only when none is registered), rescan of the receiving system only,
# and NeoStation's library actions (console folders, moving a library in).
require('LibretroCoreCatalog.consoles.values' in consoles, 'every embedded console is listed')
require('LibretroInternalService.importGamesForConsole(' in consoles, 'import for a console without games')
require('chooseLibretroImportDestination(' in consoles and 'library: destination.library' in consoles,
        "imports land in one of the user's library folders")
require('addRomFolder(createdLibraryRoot, scan: false)' in consoles,
        "NeoStation's roms folder is registered only when it received the games")
require("'importLibraryUnavailable'" in consoles and "'importAlreadyPresent'" in consoles,
        'an unreachable library and games already there are announced')
require('createNeoStationConsoleFolders(' in consoles and 'moveLibraryIntoNeoStation(' in consoles,
        'console folders and library move')
require('rescanSystemSilent(' in consoles and 'result.systemFolder' in consoles, 'the receiving system is rescanned')
require("'gamesImported'" in consoles and "'gamesRejected'" in consoles and "'importFailed'" in consoles,
        'import notifications')

# 2. Entry points. Settings › Folders lost its Embedded consoles item (Build
# 440): every other Folders function is the reviewed a5650b9b file, byte for
# byte.
directories = read(DIRECTORIES)
try:
    reviewed = subprocess.run(['git', 'show', f'{REVIEWED}:{DIRECTORIES}'], cwd=ROOT, check=True,
                              capture_output=True).stdout.decode('utf-8')
except (OSError, subprocess.CalledProcessError) as error:
    raise SystemExit(f'libretro frontend UI contract: cannot read {REVIEWED}:{DIRECTORIES} ({error})')
require(directories == reviewed, 'directories_settings_content.dart differs from a5650b9b')
for leftover in (MARKER, 'libretro_consoles', 'LibretroConsolesScreen', 'LibretroLocale'):
    require(leftover not in directories, f'Settings › Folders still names {leftover}')

# The consoles tab: appended to NavTab (indices are identities), drawn after
# Systems and before Search, a controller with a "+", iOS only, never hidable.
nav_tabs = read('lib/utils/nav_tabs.dart')
enum = re.search(r'enum NavTab \{([^}]*)\}', nav_tabs)
require(enum is not None, 'NavTab enum')
require([name.strip() for name in enum.group(1).split(',') if name.strip()]
        == ['systems', 'search', 'achievements', 'scraper', 'settings', 'library', 'consoles'],
        'consoles appended last to NavTab')
display = re.search(r'navTabDisplayOrder = \[([^\]]*)\]', nav_tabs)
require(display is not None and re.findall(r'NavTab\.(\w+)', display.group(1))[:3]
        == ['systems', 'consoles', 'search'], 'consoles drawn after Systems and before Search')
spec = nav_tabs[nav_tabs.index('NavTab.consoles: NavTabSpec('):]
spec = spec[:spec.index('),')]
for part in ("labelKey: 'consolesTab'", 'NavTabLabelCatalog.libretro', 'Symbols.sports_esports_rounded',
             'badgeIconData: Symbols.add_rounded', 'available: _isIOS'):
    require(part in spec, f'consoles tab spec: {part}')
require('hidden:' not in spec, 'the consoles tab cannot be hidden')
require("'consolesTab'" in nav_tabs and 'consolesTab' in EN, 'tab name translated')

app = read('lib/screens/app_screen.dart')
require(re.search(r'case AppTabs\.consoles:\s*(//[^\n]*\n\s*)*return LibretroConsolesScreen\(\s*inMainBar: true,', app),
        'the tab body is the consoles page in main-bar mode')
require('LibretroMainMenu.instance.attach(' in app and 'LibretroMainMenu.instance.detach(' in app,
        'the app screen keeps the added consoles in the main menu')
require('UiRefreshRateService.instance.startProbe()' in app, 'Build 440 refresh-rate hook kept')
header = read('lib/widgets/header.dart')
require('NavTabIcon(spec: navTabSpec(tab), tint: tint)' in header and 'navTabLabel(context, tab)' in header,
        'the header draws every tab, consoles included, with the same icon box, tint and label')

# The consoles page adds consoles to the main menu through LibretroMainMenu.
require('_mainMenu.add(console, provider)' in consoles, 'Add goes through LibretroMainMenu')
require('LibretroMainMenu.stateOf(' in consoles, 'each console shows its place in the main menu')
for key in ('addToMainMenu', 'showInMainMenu', 'inMainMenu', 'hiddenInMainMenu', 'consoleAdded',
            'consoleAddFailed', 'consoleSystemUnknown', 'consoleUnavailable'):
    require(f"'{key}'" in consoles, f'consoles page shows {key}')
main_menu = read('lib/services/libretro_main_menu.dart')
require('SystemRepository.addDetectedSystem(' in main_menu and 'refreshDetectedSystems()' in main_menu,
        'consoles are added through the public detected-systems API')
for forbidden in ('removeDetectedSystem', 'updateDetectedSystems', 'addRomFolder', 'removeRomFolder', 'scanSystems(',
                  'deleteRoms', 'saveConfig'):
    require(forbidden not in main_menu, f'the main-menu store never calls {forbidden}')

# 3. Playlist actions.
playlist = read(PLAYLIST)
require('if (widget.embedded) return button' in playlist, 'embedded tab action unchanged')
require("const ValueKey('libretro-internal-import-menu')" in playlist, 'menu key unchanged')
for item in ("value: 'games'", "value: 'retroarch'", "value: 'skins'"):
    require(item in playlist, f'menu item {item}')
for key in ("_t('importMenu')", "_t('importGames')", "_t('importRetroArch')", "_t('skins')"):
    require(key in playlist, f'menu label {key}')
require('LibretroCoreCatalog.bindingFor(widget.systemFolder)?.console' in playlist,
        'skins of the playlist console')
require('LibretroSkinManagerScreen(console: console)' in playlist, 'Skins opens the skin manager')

print('libretro frontend UI contract: OK')
