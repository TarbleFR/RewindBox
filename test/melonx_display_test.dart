import 'dart:convert';
import 'dart:io';
import 'dart:ui';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/l10n/melonx_library_locale.dart';
import 'package:neostation/services/melonx_internal_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('display, memory and old graphics persist independently per game', () async {
    SharedPreferences.setMockInitialValues({});
    const a = '/private/OLD/Documents/Switch/A.nsp';
    const b = '/private/OLD/Documents/Switch/B.nsp';
    final settings = {'aspectRatio': 5, 'showRamGraph': false, 'resolution': 0.75,
      'textureRecompression': true, 'hostMemoryBudget': false, 'donateMemory': false, 'vsync': true};
    await MelonxInternalService.saveGraphics(a, settings);
    await MelonxInternalService.saveGraphics(b, {'aspectRatio': 0});
    expect(await MelonxInternalService.graphicsForGame(a.replaceFirst('OLD', 'NEW')), settings);
    expect(await MelonxInternalService.graphicsForGame(b), {'aspectRatio': 0});
  });
  test('imported upstream ratios and memory flags preserve explicit choices', () {
    for (var aspect = 0; aspect <= 5; aspect++) {
      expect(MelonxInternalService.migratedGraphics({'aspectRatio': aspect,
        'enableHostMemoryBudgetTracking': false, 'enableTextureRecompression': true, 'donateGuestMemory': true}),
        {'aspectRatio': aspect, 'hostMemoryBudget': false, 'textureRecompression': true, 'donateMemory': true});
    }
    for (final invalid in [-1, 6, '5', null, 1.2]) {
      expect(MelonxInternalService.migratedGraphics({'aspectRatio': invalid}), isEmpty);
    }
    expect(MelonxInternalService.migratedGraphics({'enableHostMemoryBudgetTracking': 'true'}), isEmpty);
  });
  test('native menu changes reach the same durable per-game preferences', () async {
    SharedPreferences.setMockInitialValues({});
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, (call) async => {'available': true});
    addTearDown(() => messenger.setMockMethodCallHandler(MelonxInternalService.channel, null));
    await MelonxInternalService.runtimeAvailable();
    const codec = StandardMethodCodec();
    const game = '/private/OLD/Documents/Switch/A.nsp';
    Object? reply;
    await messenger.handlePlatformMessage(MelonxInternalService.channel.name,
      codec.encodeMethodCall(const MethodCall('saveGameGraphics', {'gamePath': game,
        'settings': {'aspectRatio': 5, 'showRamGraph': false, 'resolution': 1.5}})),
      (data) => reply = codec.decodeEnvelope(data!));
    expect(reply, true);
    await messenger.handlePlatformMessage(MelonxInternalService.channel.name,
      codec.encodeMethodCall(const MethodCall('launchDiagnostic', {'stage': 'memory', 'status': 'retained'})), (_) {});
    expect(MelonxInternalService.nativeQuarantined, true);
    MelonxInternalService.nativeQuarantined = false;
    expect(await MelonxInternalService.graphicsForGame(game),
      {'aspectRatio': 5, 'showRamGraph': false, 'resolution': 1.5});
  });
  test('native and Flutter labels match in all twelve languages', () {
    final data = jsonDecode(File('build-utils/melonx/ui-strings.json').readAsStringSync()) as Map;
    final locales = (data['locales'] as List).cast<String>();
    final rows = data['rows'] as Map;
    final keys = MelonxLibraryLocale.values['en']!.keys.toSet();
    for (var i = 0; i < locales.length; i++) {
      final values = MelonxLibraryLocale.values[locales[i]]!;
      expect(values.keys.toSet(), keys);
      for (final key in ['Screen format', 'Original (16:9)', 'Stretch', 'RAM graph',
        'Track available memory', 'Texture recompression', 'Memory status', 'Use RamDonor',
        'Settings could not be saved.', 'RewindBox RAM', 'App headroom', 'Last 60 s']) {
        expect(values[key], (rows[key] as List)[i]);
        expect(values[key], isNotEmpty);
      }
    }
    expect(MelonxLibraryLocale.text(const Locale.fromSubtags(languageCode:'zh',scriptCode:'Hant'), 'RAM graph'), '記憶體圖表');
  });
}
