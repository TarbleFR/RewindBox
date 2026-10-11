import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_date_format.dart';

/// The app installs an English-only Material fallback before the Global
/// delegates (lib/main.dart), so Library dates must not depend on
/// MaterialLocalizations.of(context).
class _EnglishFirstMaterial extends LocalizationsDelegate<MaterialLocalizations> {
  const _EnglishFirstMaterial();

  @override
  bool isSupported(Locale locale) => true;

  @override
  Future<MaterialLocalizations> load(Locale locale) =>
      DefaultMaterialLocalizations.load(const Locale('en'));

  @override
  bool shouldReload(covariant LocalizationsDelegate<MaterialLocalizations> old) =>
      false;
}

Future<String Function(DateTime)> _formatterFor(
  WidgetTester tester,
  Locale locale, {
  bool full = false,
}) async {
  late BuildContext captured;
  await tester.pumpWidget(
    Localizations(
      locale: locale,
      delegates: const <LocalizationsDelegate<dynamic>>[
        _EnglishFirstMaterial(),
        DefaultWidgetsLocalizations.delegate,
      ],
      child: Builder(
        builder: (context) {
          captured = context;
          return const SizedBox.shrink();
        },
      ),
    ),
  );
  await tester.runAsync(() => LibraryDateFormat.preload(captured));
  return (date) => full
      ? LibraryDateFormat.full(captured, date)
      : LibraryDateFormat.short(captured, date);
}

void main() {
  final date = DateTime(2026, 10, 9, 12);

  setUp(LibraryDateFormat.resetForTesting);

  testWidgets('dates follow the Library language, not the English fallback',
      (tester) async {
    final fr = await _formatterFor(tester, const Locale('fr'), full: true);
    expect(fr(date), contains('octobre'));
    expect(fr(date), contains('2026'));

    final de = await _formatterFor(tester, const Locale('de'), full: true);
    expect(de(date), contains('Oktober'));

    final ja = await _formatterFor(tester, const Locale('ja'), full: true);
    expect(ja(date), contains('10月'));
    expect(ja(date), isNot(contains('Oct')));
  });

  testWidgets('short dates keep the year in every Library language',
      (tester) async {
    for (final locale in const <Locale>[
      Locale('en'), Locale('es'), Locale('ru'), Locale('zh'),
      Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      Locale('pt'), Locale('fr'), Locale('de'), Locale('it'), Locale('id'),
      Locale('ja'), Locale('ko'),
    ]) {
      final format = await _formatterFor(tester, locale);
      expect(format(date), contains('2026'), reason: locale.toString());
      if (locale.languageCode != 'en') {
        expect(format(date), isNot(contains('Oct')), reason: locale.toString());
      }
    }
  });

  testWidgets('traditional Chinese is resolved like the Library catalogs',
      (tester) async {
    late BuildContext context;
    await tester.pumpWidget(
      Localizations(
        locale: const Locale('zh', 'TW'),
        delegates: const <LocalizationsDelegate<dynamic>>[
          _EnglishFirstMaterial(),
          DefaultWidgetsLocalizations.delegate,
        ],
        child: Builder(
          builder: (c) {
            context = c;
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    expect(LibraryDateFormat.codeOf(context), 'zh_Hant');
  });

  test('ISO form is used until a language is loaded', () {
    expect(LibraryDateFormat.iso(DateTime(2026, 1, 5)), '2026-01-05');
  });
}
