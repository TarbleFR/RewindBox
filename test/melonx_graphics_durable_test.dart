import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/services/melonx_internal_service.dart';

class _Paths extends PathProviderPlatform {
  _Paths(this.path);
  final String path;
  @override
  Future<String?> getApplicationDocumentsPath() async => path;
}

// Build 586, 28 October 2026: Hogwarts Legacy, set to 0.75 under build 585,
// launched at 1.0 right after the update; the library and caches in Documents
// had survived it. Per-game choices are now also kept in Documents.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  late File file;
  final original = MelonxInternalService.durableGraphicsFile;

  setUp(() {
    directory = Directory.systemTemp.createTempSync('melonx_graphics');
    file = File('${directory.path}/rewindbox-graphics.json');
    MelonxInternalService.durableGraphicsFile = () async => file;
  });
  tearDown(() {
    MelonxInternalService.durableGraphicsFile = original;
    directory.deleteSync(recursive: true);
  });

  const before = '/var/mobile/Containers/Data/Application/0848F040/Documents/MeloNX/roms/switch/Hogwarts Legacy.xci';
  const after = '/var/mobile/Containers/Data/Application/B47A975B/Documents/MeloNX/roms/switch/Hogwarts Legacy.xci';
  const key = 'rewindbox.melonx.graphics.MeloNX/roms/switch/Hogwarts Legacy.xci';

  test('a choice saved before an update survives empty preferences after it', () async {
    SharedPreferences.setMockInitialValues({});
    await MelonxInternalService.saveGraphics(before, {'resolution': 0.75, 'asyncShaders': true});
    SharedPreferences.setMockInitialValues({});
    expect(await MelonxInternalService.graphicsForGame(after), {'resolution': 0.75, 'asyncShaders': true});
    // The preference is restored from Documents.
    expect((await SharedPreferences.getInstance()).getString(key), isNotNull);
  });

  test('a preference saved by an earlier build is copied to Documents when read', () async {
    SharedPreferences.setMockInitialValues({key: jsonEncode({'resolution': 0.75})});
    expect(await MelonxInternalService.graphicsForGame(before), {'resolution': 0.75});
    expect(jsonDecode(file.readAsStringSync()), {key: jsonEncode({'resolution': 0.75})});
    SharedPreferences.setMockInitialValues({});
    expect(await MelonxInternalService.graphicsForGame(after), {'resolution': 0.75});
  });

  test('the preference wins over an older Documents copy, and a later save updates both', () async {
    file.writeAsStringSync(jsonEncode({key: jsonEncode({'resolution': 1.5})}));
    SharedPreferences.setMockInitialValues({key: jsonEncode({'resolution': 0.75})});
    expect(await MelonxInternalService.graphicsForGame(after), {'resolution': 0.75});
    await MelonxInternalService.saveGraphics(after, {'resolution': 0.5});
    expect(jsonDecode(file.readAsStringSync()), {key: jsonEncode({'resolution': 0.5})});
  });

  test('an unreadable Documents copy changes nothing', () async {
    file.writeAsStringSync('{not json');
    SharedPreferences.setMockInitialValues({});
    expect(await MelonxInternalService.graphicsForGame(after), isEmpty);
    await MelonxInternalService.saveGraphics(after, {'resolution': 0.75});
    SharedPreferences.setMockInitialValues({});
    expect(await MelonxInternalService.graphicsForGame(after), {'resolution': 0.75});
  });

  test('without a Documents copy the preferences behave as before', () async {
    MelonxInternalService.durableGraphicsFile = () async => null;
    SharedPreferences.setMockInitialValues({});
    await MelonxInternalService.saveGraphics(before, {'resolution': 0.75});
    expect(await MelonxInternalService.graphicsForGame(after), {'resolution': 0.75});
    SharedPreferences.setMockInitialValues({});
    expect(await MelonxInternalService.graphicsForGame(after), isEmpty);
  });

  test('a library path from the previous container resolves under the current Documents', () async {
    final oldPaths = PathProviderPlatform.instance;
    addTearDown(() => PathProviderPlatform.instance = oldPaths);
    final documents = Directory('${directory.path}/B47A975B/Documents')..createSync(recursive: true);
    PathProviderPlatform.instance = _Paths(documents.path);
    final game = File('${documents.path}/MeloNX/roms/switch/Hogwarts Legacy.xci')
      ..createSync(recursive: true)
      ..writeAsStringSync('x');
    final stale = '${directory.path}/0848F040/Documents/MeloNX/roms/switch/Hogwarts Legacy.xci';
    expect(await MelonxInternalService.inCurrentDocuments(stale), game.path);
    // A path that exists, one outside Documents, and a file missing in both stay as they are.
    expect(await MelonxInternalService.inCurrentDocuments(game.path), game.path);
    expect(await MelonxInternalService.inCurrentDocuments('/private/var/Switch/A.nsp'), '/private/var/Switch/A.nsp');
    final missing = '${directory.path}/0848F040/Documents/MeloNX/roms/switch/Other.xci';
    expect(await MelonxInternalService.inCurrentDocuments(missing), missing);
  });
}
