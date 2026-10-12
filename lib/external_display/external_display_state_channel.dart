import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:neostation/models/secondary_display_state.dart';

/// The twelve NeoStation languages, as the `MapLocale` codes of `main.dart`
/// (`zh_Hant` for Traditional Chinese). The TV menu accepts nothing else.
const List<String> kExternalDisplayLanguageCodes = <String>[
  'en',
  'es',
  'pt',
  'ru',
  'zh',
  'zh_Hant',
  'fr',
  'de',
  'it',
  'id',
  'ja',
  'ko',
];

/// What the main engine gives the TV menu engine when it starts it
/// (`FlutterEngineGroupOptions.entrypointArgs`, built by
/// `NeoExternalDisplayMenuEngine.m`): `language=<code>` and `theme=<name>`.
///
/// The TV engine never opens the database (no `ConfigRepository`, no
/// SQLite from a second isolate, Build 447 review): the app language and
/// theme come from here, then from the language channel and the menu states.
@immutable
class ExternalDisplayMenuArgs {
  const ExternalDisplayMenuArgs({
    this.languageCode = defaultLanguageCode,
    this.themeName,
  });

  /// Arguments in any order; an unknown argument is ignored, an unsupported
  /// language is English, an empty theme is none.
  factory ExternalDisplayMenuArgs.parse(List<String> args) {
    String? language;
    String? theme;
    for (final argument in args) {
      if (argument.startsWith(languagePrefix)) {
        language = argument.substring(languagePrefix.length).trim();
      } else if (argument.startsWith(themePrefix)) {
        theme = argument.substring(themePrefix.length).trim();
      }
    }
    return ExternalDisplayMenuArgs(
      languageCode: supportedLanguage(language) ?? defaultLanguageCode,
      themeName: theme == null || theme.isEmpty ? null : theme,
    );
  }

  /// `kNeoExternalMenuLanguageArgumentPrefix` of the native host.
  static const String languagePrefix = 'language=';

  /// `kNeoExternalMenuThemeArgumentPrefix` of the native host.
  static const String themePrefix = 'theme=';

  static const String defaultLanguageCode = 'en';

  /// [code] when it is one of the twelve languages, else null.
  static String? supportedLanguage(String? code) {
    final trimmed = code?.trim();
    return trimmed != null && kExternalDisplayLanguageCodes.contains(trimmed)
        ? trimmed
        : null;
  }

  final String languageCode;
  final String? themeName;

  /// The arguments the native host builds for these values (tests).
  List<String> toEntrypointArgs() => <String>[
    '$languagePrefix$languageCode',
    if (themeName != null) '$themePrefix$themeName',
  ];

  @override
  bool operator ==(Object other) =>
      other is ExternalDisplayMenuArgs &&
      other.languageCode == languageCode &&
      other.themeName == themeName;

  @override
  int get hashCode => Object.hash(languageCode, themeName);

  @override
  String toString() =>
      'ExternalDisplayMenuArgs(language: $languageCode, theme: $themeName)';
}

/// Receiver of the TV menu states in the external display's second Flutter
/// engine (Build 447).
///
/// The native host relays `ExternalDisplayService.pushMenuState` from the
/// main engine as the JSON of `SecondaryDisplayStateData.toJson()` on the
/// `BasicMessageChannel` `neostation/external_display/menu` (`StringCodec`,
/// `NeoExternalDisplayMenuEngine.m`). This replaces the Android `sub_screen`
/// shared state: `SecondaryDisplayState.instance` is never touched here.
/// A change of the app language arrives on
/// `neostation/external_display/menu_locale` (the language code).
///
/// The handlers are registered as soon as [instance] is first read, so the
/// entrypoint creates it before its first `await`: the host sends the last
/// state right after the engine exists and Flutter buffers it until a handler
/// is up.
class ExternalDisplayStateChannel {
  ExternalDisplayStateChannel._() {
    channel.setMessageHandler(_onMessage);
    languageChannel.setMessageHandler(_onLanguage);
  }

  static final ExternalDisplayStateChannel instance =
      ExternalDisplayStateChannel._();

  /// A separate receiver for tests. It takes over the channel handlers; the
  /// last one created receives the messages.
  @visibleForTesting
  factory ExternalDisplayStateChannel.forTesting() =>
      ExternalDisplayStateChannel._();

  static const String channelName = 'neostation/external_display/menu';

  static const BasicMessageChannel<String> channel = BasicMessageChannel<String>(
    channelName,
    StringCodec(),
  );

  static const String languageChannelName =
      'neostation/external_display/menu_locale';

  static const BasicMessageChannel<String> languageChannel =
      BasicMessageChannel<String>(languageChannelName, StringCodec());

  final ValueNotifier<SecondaryDisplayStateData?> _state =
      ValueNotifier<SecondaryDisplayStateData?>(null);

  final ValueNotifier<String?> _language = ValueNotifier<String?>(null);

  int _received = 0;
  int _rejected = 0;
  int _rejectedLanguages = 0;

  /// The last state pushed by the main engine; null before the first one.
  ValueListenable<SecondaryDisplayStateData?> get state => _state;

  /// The last app language the main engine sent (one of the twelve codes);
  /// null before the first change.
  ValueListenable<String?> get language => _language;

  /// Messages decoded into a state.
  int get received => _received;

  /// Messages that were not a JSON object of `SecondaryDisplayStateData`.
  int get rejected => _rejected;

  /// Language messages that were not one of the twelve codes.
  int get rejectedLanguages => _rejectedLanguages;

  /// The reply is ignored by the native host (`sendMessage:` without a
  /// callback); the codec needs a string, so an empty one goes back.
  Future<String> _onMessage(String? message) async {
    if (message == null || message.isEmpty) {
      _rejected++;
      return '';
    }
    try {
      final decoded = jsonDecode(message);
      if (decoded is! Map) {
        _rejected++;
        return '';
      }
      _state.value = SecondaryDisplayStateData.fromJson(
        Map<String, dynamic>.from(decoded),
      );
      _received++;
    } catch (error) {
      // A malformed push never takes the TV menu down; the previous state
      // stays on screen.
      _rejected++;
      debugPrint('External display: menu state rejected: $error');
    }
    return '';
  }

  Future<String> _onLanguage(String? message) async {
    final code = ExternalDisplayMenuArgs.supportedLanguage(message);
    if (code == null) {
      _rejectedLanguages++;
      return '';
    }
    _language.value = code;
    return '';
  }
}
