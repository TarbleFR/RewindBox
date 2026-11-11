#!/usr/bin/env python3
"""An empty Xbox 360 or Switch 2 library on iOS is a playlist, like the Switch one: the route shows the
playlist empty state (no recursive-scan switch, whose scan root is fixed and private) and keeps its import
button. Source contract; the widget path needs Platform.isIOS, which host widget tests do not have."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'lib/screens/game_screen/my_games_list.dart').read_text()
body = source.split('Widget _buildEmptyState() {', 1)[1]
head = body.split('return SwitchPlaylistEmptyState(', 1)[0]
failures = []
for needle in ("widget.system.folderName == 'switch'", '_isXeniaLibrary', '_isS2ArmLibrary'):
    if needle not in head:
        failures.append('the playlist empty state is not used for ' + needle)
for getter, folder in (('_isXeniaLibrary', 'xbox360'), ('_isS2ArmLibrary', 'switch2')):
    if f"bool get {getter} =>\n      Platform.isIOS && widget.system.folderName.toLowerCase() == '{folder}';" not in source:
        failures.append(f'{getter} no longer names the iOS {folder} library')
for builder in ('_buildXeniaImportAction()', '_buildS2ArmImportAction()'):
    if builder not in source:
        failures.append(builder + ' is no longer shown by the route')
if failures:
    sys.exit('FAILED: ' + '; '.join(failures))
print('embedded playlist empty state: OK')
