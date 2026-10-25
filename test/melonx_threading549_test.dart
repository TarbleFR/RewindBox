import 'dart:ui';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/l10n/melonx_library_locale.dart';
import 'package:neostation/services/melonx_internal_service.dart';

// Build 549: the per-game backend-threading switch. The Core default is On
// (EmbeddedSession.cs); the app only stores an explicit choice.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('imported standalone BackendThreading enum maps to the per-game switch', () {
    // Ryujinx BackendThreading: 0 Auto, 1 Off, 2 On. Auto is On for Vulkan.
    expect(MelonxInternalService.migratedGraphics({'backendThreading': 0}), {'backendThreading': true});
    expect(MelonxInternalService.migratedGraphics({'backendThreading': 1}), {'backendThreading': false});
    expect(MelonxInternalService.migratedGraphics({'backendThreading': 2}), {'backendThreading': true});
    for (final invalid in ['2', true, null, 1.0]) {
      expect(MelonxInternalService.migratedGraphics({'backendThreading': invalid}), isEmpty);
    }
    expect(MelonxInternalService.migratedGraphics({}), isEmpty);
  });
  test('an explicit per-game choice persists and an absent one stays absent', () async {
    SharedPreferences.setMockInitialValues({});
    const a = '/private/OLD/Documents/Switch/A.nsp';
    const b = '/private/OLD/Documents/Switch/B.nsp';
    await MelonxInternalService.saveGraphics(a, {'backendThreading': false, 'aspectRatio': 1});
    await MelonxInternalService.saveGraphics(b, {'aspectRatio': 1});
    expect(await MelonxInternalService.graphicsForGame(a.replaceFirst('OLD', 'NEW')),
        {'backendThreading': false, 'aspectRatio': 1});
    expect((await MelonxInternalService.graphicsForGame(b)).containsKey('backendThreading'), isFalse);
  });
  test('the switch label exists in all twelve languages', () {
    final english = MelonxLibraryLocale.values['en']!['Backend threading'];
    expect(english, 'Backend threading');
    for (final entry in MelonxLibraryLocale.values.entries) {
      expect(entry.value['Backend threading'], isNotEmpty, reason: entry.key);
    }
    expect(MelonxLibraryLocale.values.length, 12);
    expect(MelonxLibraryLocale.text(const Locale('fr'), 'Backend threading'), 'Multithreading du backend');
  });
}
