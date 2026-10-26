#!/usr/bin/env python3
"""Build 554: where a library-folder PS3 disc enters RPCS3 in the iOS router.

A user's app.log showed a PS3 ISO placed in Documents/roms/ps3 listed by the
library scan, then every launch of it ending in the RetroArch route
("RetroArchLaunch ... stage=cacheEmpty ... No persisted RetroArch export is
available"), because the router handed a PS3 row to RPCS3 only when it
carried a title ID, which a scanned file never has. Now every iOS PS3 row
takes the RPCS3 branch: a disc image of the library folder is resolved
(linked, or installed by RPCS3's own import after the user agrees) before
the session is registered, and the branch returns on every path, so no PS3
row reaches RetroArch. The behaviour is tested in Dart
(test/rpcs3_library_file_service_test.dart, test/rpcs3_disc_image_test.dart,
test/rpcs3_library_file_dialog_test.dart); this file pins the wiring.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding='utf-8')


def require(condition, message):
    if not condition:
        raise SystemExit('RPCS3 library file route contract: ' + message)


def matching(text, at, opener, closer):
    depth = 0
    for index in range(at, len(text)):
        if text[index] == opener:
            depth += 1
        elif text[index] == closer:
            depth -= 1
            if depth == 0:
                return index
    raise SystemExit('unbalanced ' + opener)


router = read('lib/services/game/game_launch_service.dart')
GATE = 'if (isPs3 && game.romPath != null) {'
require(router.count(GATE) == 1, 'one PS3 branch, taken by every iOS PS3 row')
require('isRpcs3VirtualRom || (game.titleId' not in router,
        'the title-ID gate that let scanned discs fall through is gone')
start = router.index(GATE)
end = matching(router, start + len(GATE) - 1, '{', '}')
ps3 = router[start:end + 1]

POLICY = 'EmbeddedEnginePolicy.instance.allowsSystem(system)'
order = [POLICY, 'Rpcs3LibraryFileService.needsResolution(',
         'prepareRpcs3LibraryFileForLaunch(', "'ios_rpcs3_internal'",
         'Rpcs3LaunchService.launchTitle(']
positions = [ps3.find(token) for token in order]
require(all(at >= 0 for at in positions), f'missing step: {list(zip(order, positions))}')
require(positions == sorted(positions),
        'policy, then the disc resolution, then the session, then the boot')
require('!isRpcs3VirtualRom &&' in ps3, 'RPCS3 library rows are never resolved again')
require('return GameLaunchResult.cancelled();' in ps3, 'declining is not an error')
require('Rpcs3LibraryFileLocale.failure(' in ps3 and 'prepared.details' in ps3,
        'a failure is translated and keeps RPCS3\'s own detail')
require('RetroArch' not in ps3, 'no RetroArch inside the PS3 branch')
last = ps3.rstrip()[:-1].rstrip().splitlines()[-1].strip()
body = ps3.rstrip()[:-1].rstrip()
tail = body[body.rfind('return '):]
require(re.match(r'return GameLaunchResult\.failure\(', tail) is not None and tail.rstrip().endswith(');'),
        'the branch ends with a return: a PS3 row never continues past it')
require(end < router.index('// LIBRETRO_INTERNAL_BEGIN: embedded_route') < router.index("'ios_direct_launch'")
        < router.index('RetroArchLibraryService.launchGameWithDiagnostics'),
        'the PS3 branch precedes libretro, the generic handoff and RetroArch')

result = router[router.index('class GameLaunchResult {'):router.index('class GameLaunchService {')]
require('GameLaunchResult.cancelled()' in result and 'final bool cancelled;' in result,
        'a cancelled launch is a result of its own')

flow = read('lib/screens/game_screen/my_games_list/launch_flow.dart')
failed = flow[flow.index('onLaunchFailed: (ctx, result) async {'):]
require(failed.index('rebuild(() => _isGameLaunching = false);') < failed.index('if (result.cancelled) {')
        < failed.index('await showDialog('), 'the list cleans up, then shows no error for a decline')

service = read('lib/services/rpcs3_library_file_service.dart')
require('Rpcs3InternalBridge.installIso(isoPath, keyPath: keyPath)' in service,
        'RPCS3 installs the disc with its own validated import')
for copy in ('.copy(', 'openWrite(', 'writeAsBytes(', '.rename(', '.delete('):
    require(copy not in service, 'the service never copies, moves or deletes a disc itself: ' + copy)
require('Rpcs3InternalService.hasFirmware' in service, 'no copy without the PS3 firmware')
require('Rpcs3LibraryService.linkLibraryFile' in service, 'the row is linked to the installed title')

dialog = read('lib/widgets/rpcs3_library_file_install_dialog.dart')
require(dialog.index('Rpcs3LibraryFileService.resolve(romPath)') < dialog.index('showRpcs3LibraryFileInstallPrompt(context, plan)')
        < dialog.index('Rpcs3LibraryFileService.install(plan)'), 'resolve, ask, then install')
require('canPop: false' in dialog, 'the progress dialog cannot be dismissed while RPCS3 copies')

importer = read('lib/services/rpcs3_content_import_service.dart')
require("if (extension == '.key' || extension == '.dkey') {" in importer,
        'a .dkey picked with its ISO is its disc key, not an unsupported game')
require('await Rpcs3DiscImage.findDiscKey(filePath)' in importer, 'the sibling disc key may be .dkey')
require("_log.e('RPCS3 import: $name rejected: $message');" in importer,
        'an import refusal reaches app.log, not only a snackbar')
print('RPCS3 library file route contract: ok')
