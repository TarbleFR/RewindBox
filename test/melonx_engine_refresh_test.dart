import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The launch graphics of a game with an FPS code on: the engine refresh
/// (`vsyncFps`) is added for the launch only, never stored, so the graphics
/// dialog and the in-game menu keep the player's own VSync choice.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  final durable = MelonxInternalService.durableGraphicsFile;
  final refresh = MelonxInternalService.engineRefresh;
  const game = '/var/mobile/Containers/Data/Application/A/Documents/MeloNX/roms/switch/Fighter.nsp';
  const key = 'rewindbox.melonx.graphics.MeloNX/roms/switch/Fighter.nsp';

  setUp(() {
    directory = Directory.systemTemp.createTempSync('melonx_refresh');
    MelonxInternalService.durableGraphicsFile = () async => File('${directory.path}/rewindbox-graphics.json');
    SharedPreferences.setMockInitialValues({});
  });
  tearDown(() {
    MelonxInternalService.durableGraphicsFile = durable;
    MelonxInternalService.engineRefresh = refresh;
    directory.deleteSync(recursive: true);
  });

  test('a launch carries the refresh of an active FPS code; the dialog never sees it', () async {
    await MelonxInternalService.saveGraphics(game, {'vsync': false, 'resolution': 1.0});
    MelonxInternalService.engineRefresh = (path) async => path == game ? 120 : null;
    expect(await MelonxInternalService.graphicsForGame(game, forLaunch: true), {'vsync': false, 'resolution': 1.0, 'vsyncFps': 120});
    expect(await MelonxInternalService.graphicsForGame(game), {'vsync': false, 'resolution': 1.0});
  });

  test('without an active FPS code the launch keeps the player choice', () async {
    await MelonxInternalService.saveGraphics(game, {'vsync': true});
    MelonxInternalService.engineRefresh = (_) async => null;
    expect(await MelonxInternalService.graphicsForGame(game, forLaunch: true), {'vsync': true});
  });

  test('the session settings saved back from the in-game menu do not keep the refresh', () async {
    await MelonxInternalService.saveGraphics(game, {'vsync': true, 'vsyncFps': 120, 'aspectRatio': 1});
    final prefs = await SharedPreferences.getInstance();
    expect(jsonDecode(prefs.getString(key)!), {'vsync': true, 'aspectRatio': 1});
    // A stored value of any origin is never read back as the player's choice.
    await prefs.setString(key, jsonEncode({'vsync': false, 'vsyncFps': 90}));
    MelonxInternalService.engineRefresh = (_) async => null;
    expect(await MelonxInternalService.graphicsForGame(game), {'vsync': false});
    expect(await MelonxInternalService.graphicsForGame(game, forLaunch: true), {'vsync': false});
  });

  test('the default refresh lookup never fails a launch off the device', () async {
    expect(await MelonxInternalService.graphicsForGame(game, forLaunch: true), isEmpty);
  });
}
