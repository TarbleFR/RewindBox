import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The Switch 2 playlist menu is modelled on MeloNX's: import games, the one prod.keys shared with MeloNX, delete; no
/// firmware. The delete branch sits in the repository, the Manage tab refreshes the S2Arm library.
void main() {
  final menu = File('lib/widgets/s2arm_internal_playlist_actions.dart').readAsStringSync();
  final repository = File('lib/repositories/game_repository.dart').readAsStringSync();
  final manage = File('lib/screens/game_screen/game_settings_dialog/game_settings_manage_tab.dart').readAsStringSync();

  test('the menu has import games, prod.keys and delete, and no firmware item', () {
    expect(menu, contains("ValueKey('s2arm-import-folder')"));
    expect(menu, contains("ValueKey('s2arm-import-keys')"));
    expect(menu, contains("ValueKey('s2arm-delete-game')"));
    // No firmware entry (the file's doc comment says why; S2Arm uses none).
    expect(menu, isNot(contains("value: 'firmware'")));
    expect(menu.toLowerCase(), isNot(contains('import-firmware')));
    expect(menu.toLowerCase(), isNot(contains("_t('importfirmware")));
    expect(menu, contains("_t('importGamesHint')"));
    expect(menu, contains("_t('importKeysHint')"));
  });

  test('the menu opens the Switch 2 engine settings panel', () {
    expect(menu, contains("ValueKey('s2arm-settings')"));
    expect(menu, contains("value: 'settings'"));
    expect(menu, contains("Switch2SettingsLocale.text(context, 'title')"));
    expect(menu, contains('Switch2EngineSettingsPanel()'));
    expect(menu, isNot(contains("value: 'firmware'")));
  });

  test('the menu imports a save and opens the saves folder for the selected game', () {
    expect(menu, contains("ValueKey('s2arm-import-save')"));
    expect(menu, contains("value: 'importSave'"));
    expect(menu, contains('S2ArmInternalService.importSave('));
    expect(menu, contains("ValueKey('s2arm-open-saves')"));
    expect(menu, contains("value: 'openSaves'"));
    expect(menu, contains('S2ArmInternalService.openSaveFolder('));
    expect(menu, contains("_t('importSaveHint')"));
    expect(menu, contains("_t('openSavesHint')"));
    expect(menu, contains("_tf('saveRedirected'"));
    expect(menu, contains("_tf('saveRedirectedMissing'"));
  });

  test('the save items are always offered, second as in MeloNX; delete needs a selected game', () {
    final items = menu.substring(menu.indexOf('itemBuilder:'));
    for (final key in ['s2arm-import-save', 's2arm-open-saves']) {
      final item = items.lastIndexOf('PopupMenuItem(', items.indexOf("ValueKey('$key')"));
      final previousLine = items.substring(0, item).trimRight().split('\n').last.trim();
      expect(previousLine, isNot(startsWith('if (')), reason: '$key is offered with or without a selected game');
    }
    expect(items.indexOf("ValueKey('s2arm-import-folder')"), lessThan(items.indexOf("ValueKey('s2arm-import-save')")));
    expect(items.indexOf("ValueKey('s2arm-import-save')"), lessThan(items.indexOf("ValueKey('s2arm-import-keys')")));
    final delete = items.indexOf("ValueKey('s2arm-delete-game')");
    expect(items.substring(items.lastIndexOf('if (', delete), delete), contains('widget.romPath != null'));
    // Without a selected game: the game the save names, else the player's choice; the Saves folder itself.
    expect(menu, contains('romPath == null ? null : Switch2ExportContent.exportFolder(romPath)'));
    expect(menu, contains('chooseGame: (games) async {'));
    expect(menu, contains("_t('saveChooseGame')"));
    expect(menu, contains("_tf('saveImportedForId'"));
  });

  test('the Emulators tab shows the settings panel for switch2 only', () {
    final tabs = File('lib/widgets/system_emulator_settings_dialog/tabs.dart').readAsStringSync();
    expect(tabs, contains("if (console == 'switch2') const Switch2EngineSettingsPanel()"));
  });

  test('prod.keys goes through the one MeloNX import and store, with its refusal messages', () {
    expect(menu, contains('MelonxEmbeddedLibraryService.importKeys()'));
    expect(menu, contains("MelonxTransferLocale.text(context, item.value)"));
    expect(menu, isNot(contains('FilePicker')));
  });

  test('deleting a Switch 2 game has its own branch, then the library refresh', () {
    expect(repository, contains("systemFolderName.toLowerCase() == 'switch2'"));
    expect(repository, contains('S2ArmInternalService.deleteGame(romPath)'));
    expect(manage, contains("_targetSystemFolder.toLowerCase() == 'switch2'"));
    expect(manage, contains('refreshS2ArmInternalLibrary()'));
  });
}
