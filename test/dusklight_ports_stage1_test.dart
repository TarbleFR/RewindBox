import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Ports keeps Dusklight as its only embedded port', () {
    final root = jsonDecode(File('assets/systems/ports.json').readAsStringSync())
        as Map<String, dynamic>;
    final system = Map<String, dynamic>.from(root['system'] as Map);
    final emulators = (root['emulators'] as List).cast<Map>();

    expect(system['id'], 'ports');
    expect(
      (system['details'] as Map)['notable_games'],
      <String>['The Legend of Zelda: Twilight Princess'],
    );
    // KartPad left NeoStation on 19 October 2026: players build it themselves.
    expect(emulators, hasLength(1));
    expect(emulators.single['unique_id'], 'ports.ios.dusklight');
    expect(emulators.single['name'], 'Dusklight');
    expect(
      ((emulators.single['platforms'] as Map)['ios'] as Map)['embedded'],
      isTrue,
    );
    expect(File('lib/services/kartpad_internal_service.dart').existsSync(),
        isFalse);
  });

  test('Ports exposes one Import menu with DuskLight only', () {
    final widget =
        File('lib/widgets/ports_internal_playlist_actions.dart')
            .readAsStringSync();
    expect(widget, contains("ValueKey('ports-internal-import')"));
    expect(widget, contains("'import'"));
    expect(widget, contains("'dusklight'"));
    expect(widget, contains('DusklightInternalService.importGames()'));
    expect(widget.toLowerCase(), isNot(contains('kartpad')));
  });

  test('Ports scraper resolves Dusklight identities only', () {
    final identity =
        File('lib/services/ports_game_identity.dart').readAsStringSync();
    final scraper =
        File('lib/services/screenscraper_service.dart').readAsStringSync();

    expect(identity, contains('DusklightGameIdentity.read'));
    expect(identity, contains('PortGameIdentity'));
    expect(identity.toLowerCase(), isNot(contains('kartpad')));
    expect(scraper, contains('PortGameIdentity.read'));
    expect(scraper, isNot(contains('DusklightGameIdentity.read')));
  });

  test('Ports deletion refreshes the private library immediately', () {
    final manage = File(
      'lib/screens/game_screen/game_settings_dialog/game_settings_manage_tab.dart',
    ).readAsStringSync();
    expect(manage, contains("toLowerCase() == 'ports'"));
    expect(manage, contains('refreshPortsInternalLibrary'));
  });

  test('Ports scan reads Dusklight only and launch refuses the old KartPad folder',
      () {
    final scanning =
        File('lib/providers/sqlite_config_provider/scanning.dart')
            .readAsStringSync();
    final launcher =
        File('lib/services/game/game_launch_service.dart').readAsStringSync();
    final playlist =
        File('lib/screens/game_screen/my_games_list.dart').readAsStringSync();

    expect(scanning, contains('refreshPortsInternalLibrary'));
    expect(scanning, contains('DusklightInternalService.rootDirectory'));
    expect(scanning, contains('nativeScanRoots = <String>[dusklightRoot];'));
    expect(scanning, isNot(contains('KartPad')));

    final portsRoute =
        launcher.indexOf("system.folderName.toLowerCase() == 'ports'");
    final removedRefusal =
        launcher.indexOf('isRemovedKartPadGamePath(gamePath)', portsRoute);
    final dusklightLaunch =
        launcher.indexOf('DusklightInternalService.launch', portsRoute);
    expect(portsRoute, greaterThanOrEqualTo(0));
    expect(removedRefusal, greaterThan(portsRoute));
    expect(dusklightLaunch, greaterThan(removedRefusal));
    expect(launcher, isNot(contains('KartPadInternalService')));

    expect(playlist, contains('PortsInternalPlaylistActions'));
    expect(playlist, contains('_buildPortsImportAction'));
    expect(playlist, contains('_buildEmbeddedPortsImportAction'));
  });
}
