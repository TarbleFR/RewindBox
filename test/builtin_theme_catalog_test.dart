import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/themes/app_themes.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('the fourteen built-in palettes remain available, Glacier added last', () {
    // The saved identifiers and their order are unchanged; RewindBox Glacier's
    // palette (2 November 2026) is appended.
    const names = <String>[
      'dark', 'light', 'oled', 'valentine', 'dracula', 'nord', 'coffee',
      'tokyo_night', 'retro', 'abyss', 'cyberpunk', 'aqua', 'palenight', 'horizon',
      'glacier',
    ];
    expect(ThemeProvider.availableThemes.keys, orderedEquals(names));
    for (final name in names) {
      expect(ThemeProvider.availableThemes[name], isNotNull);
      expect(ThemeProvider.themeDisplayNames[name], isNotEmpty);
    }
    expect(ThemeProvider.availableThemes['dark'], same(AppThemes.darkTheme));
    expect(ThemeProvider.availableThemes['light'], same(AppThemes.lightTheme));
  });
}
