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
  byte-for-byte the reviewed a5650b9b version, with only the mounted-context
  guard already present in the reviewed 29b24945 branch before this shader
  work (e4f6c735, 13 October 2026). This replaces the
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
ORIGINAL_REVIEWED = 'a5650b9bddefbed76f941fb53735545bebcbbd39'
REVIEWED = '29b24945b2e7041f08e02d7d70e8c90ffe8a1c24'
# Latest reviewed version of the directories page: 127b527f retired the
# external MeloNX folder, 9cd71fe5 renamed the app RewindBox and 598d35d5
# (Liquid Glass, delivered in 549) migrated its chrome.
CURRENT_REVIEWED = '598d35d5da79b2638356e8e212dad9fd945725e6'
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
# Build 448: the tab lists every console of ConsoleCatalog (the 17 embedded
# libretro consoles, the other engines and the RetroArch systems) instead of
# LibretroCoreCatalog.consoles.values directly. The catalog is built from
# that map, so every embedded console stays listed; the catalog itself is
# tested by test/console_manager_test.dart, the rows by
# test/libretro_consoles_tab_test.dart.
console_catalog = read('lib/services/console_catalog.dart')
require('for (final console in LibretroCoreCatalog.consoles.values)' in console_catalog
        and 'for (final entry in ConsoleCatalog.entries)' in consoles, 'every embedded console is listed')
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
# 440): preserve the full reviewed file. The earlier e4f6c735 UI audit added
# one mounted-context check to the asynchronous scroll callback; it changes
# neither the folders nor their actions. This work preserves that accepted
# branch input rather than restoring the retired unsafe callback. Verify the
# exact sole difference from a5650b9b, then the complete 29b24945 file identity.
directories = read(DIRECTORIES)
try:
    reviewed = subprocess.run(['git', 'show', f'{REVIEWED}:{DIRECTORIES}'], cwd=ROOT, check=True,
                              capture_output=True).stdout.decode('utf-8')
    original_reviewed = subprocess.run(['git', 'show', f'{ORIGINAL_REVIEWED}:{DIRECTORIES}'], cwd=ROOT,
                                       check=True, capture_output=True).stdout.decode('utf-8')
    current_reviewed = subprocess.run(['git', 'show', f'{CURRENT_REVIEWED}:{DIRECTORIES}'], cwd=ROOT,
                                      check=True, capture_output=True).stdout.decode('utf-8')
except (OSError, subprocess.CalledProcessError) as error:
    raise SystemExit(f'libretro frontend UI contract: cannot read reviewed directories source ({error})')
old_guard = 'if (builtContext != null) {'
mounted_guard = 'if (builtContext != null && builtContext.mounted) {'
require(original_reviewed.count(old_guard) == 1,
        'the original directories scroll callback must have exactly one context guard')
require(reviewed == original_reviewed.replace(old_guard, mounted_guard, 1),
        '29b24945 directories must differ from a5650b9b only by the earlier mounted-context guard')
# Contract replaced (27 October 2026): the file identity moved from 29b24945
# to the latest reviewed version (see CURRENT_REVIEWED); the history above
# stays checked and the retired entry stays absent below.
require(reviewed != current_reviewed and MARKER not in current_reviewed,
        'the reviewed directories page has no embedded-consoles entry')
require(directories == current_reviewed,
        f'directories_settings_content.dart differs from the complete reviewed {CURRENT_REVIEWED[:8]} source')
for leftover in (MARKER, 'libretro_consoles', 'LibretroConsolesScreen', 'LibretroLocale'):
    require(leftover not in directories, f'Settings › Folders still names {leftover}')

# The consoles tab: appended to NavTab (indices are identities), drawn after
# Systems and before Search, a controller with a "+", iOS only, never hidable.
nav_tabs = read('lib/utils/nav_tabs.dart')
enum = re.search(r'enum NavTab \{([^}]*)\}', nav_tabs)
require(enum is not None, 'NavTab enum')
# 252297bf (AirPlay navigation) appended airplay after consoles: indices
# stay identities, consoles keeps index 6.
require([name.strip() for name in enum.group(1).split(',') if name.strip()]
        == ['systems', 'search', 'achievements', 'scraper', 'settings', 'library', 'consoles', 'airplay'],
        'consoles appended to NavTab, followed only by the later airplay tab')
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

# The consoles page changes the main menu through LibretroMainMenu.
#
# Build 448 replaced the Build 440 contract of this block. Then the page had
# an "Add to the main menu" / "Show in the main menu" button per embedded
# console (LibretroLocale keys addToMainMenu, showInMainMenu, inMainMenu,
# hiddenInMainMenu, consoleAdded, consoleAddFailed, consoleSystemUnknown,
# consoleUnavailable) and the store never removed a detected system. Now each
# console of ConsoleCatalog has a visibility switch (showEntry / hideEntry),
# with "Show all" and "Restore defaults", its texts in ConsoleManagerLocale
# (twelve languages, test/console_manager_test.dart). "Restore defaults"
# takes back out of the main menu the consoles the tab itself added and that
# still hold no game: removeDetectedSystem, in restoreDefaults only, only for
# a console the tab pinned whose systems all have zero games — the same row
# the scanner's own pruning removes for an empty system (scanning.dart,
# SYSTEM PRUNING). A console with games is shown again, never removed
# (test/libretro_consoles_tab_test.dart, "Restore defaults keeps a console
# the tab added once it holds games").
# dart format (4973e6cd) wraps long calls and adds trailing commas: compare
# the calls without whitespace and without a comma before ')'.
def compact(text):
    return re.sub(r'\s+', '', text).replace(',)', ')')
for call in ('_mainMenu.showEntry(entry, provider)', '_mainMenu.hideEntry(entry, provider)',
             '_mainMenu.showAll(', '_mainMenu.restoreDefaults(ConsoleCatalog.entries, provider)'):
    require(compact(call) in compact(consoles), f'the switch and the bulk actions go through LibretroMainMenu: {call}')
require('LibretroMainMenu.stateOfEntry(' in consoles, 'each console shows its place in the main menu')
require('ConsoleManagerLocale.' in consoles, 'the consoles page texts come from ConsoleManagerLocale')
main_menu = read('lib/services/libretro_main_menu.dart')
require('SystemRepository.addDetectedSystem(' in main_menu and 'refreshDetectedSystems()' in main_menu,
        'consoles are added through the public detected-systems API')
require(main_menu.count('SystemRepository.removeDetectedSystem(') == 1, 'one removal, in restoreDefaults')
restore = main_menu[main_menu.index('Future<ConsoleMenuBulkResult> restoreDefaults('):]
restore = restore[:restore.index('/// Runs a change of several consoles')]
require('SystemRepository.removeDetectedSystem(' in restore
        and 'state.systems.every((system) => system.romCount == 0)' in restore
        and 'if (unpinned && pinned.contains(entry.id) && empty) {' in restore,
        'restoreDefaults removes only a console the tab pinned that holds no game')
for forbidden in ('updateDetectedSystems', 'addRomFolder', 'removeRomFolder', 'scanSystems(', 'deleteRoms', 'saveConfig'):
    require(forbidden not in main_menu, f'the main-menu store never calls {forbidden}')

# 3. Playlist actions.
playlist = read(PLAYLIST)
# Since 0a7975e3 the shared PlaylistImportButton returns the bare button in
# the tab placement (integrated_import_tab_contract_test.py checks it too).
require('return PlaylistImportButton(' in playlist and 'embedded: widget.embedded,' in playlist
        and 'if (embedded) return button;' in read('lib/widgets/playlist_import_button.dart'),
        'embedded tab action unchanged')
require("const ValueKey('libretro-internal-import-menu')" in playlist, 'menu key unchanged')
for item in ("value: 'games'", "value: 'retroarch'", "value: 'skins'"):
    require(item in playlist, f'menu item {item}')
for key in ("_t('importMenu')", "_t('importGames')", "_t('importRetroArch')", "_t('skins')"):
    require(key in playlist, f'menu label {key}')
require('LibretroCoreCatalog.bindingFor(widget.systemFolder)?.console' in playlist,
        'skins of the playlist console')
require('LibretroSkinManagerScreen(console: console)' in playlist, 'Skins opens the skin manager')

print('libretro frontend UI contract: OK')
