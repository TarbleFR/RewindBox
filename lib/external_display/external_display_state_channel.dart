import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:neostation/models/secondary_display_state.dart';

/// Receiver of the TV menu states in the external display's second Flutter
/// engine (Build 447).
///
/// The native host relays `ExternalDisplayService.pushMenuState` from the
/// main engine as the JSON of `SecondaryDisplayStateData.toJson()` on the
/// `BasicMessageChannel` `neostation/external_display/menu` (`StringCodec`,
/// `NeoExternalDisplayMenuEngine.m`). This replaces the Android `sub_screen`
/// shared state: `SecondaryDisplayState.instance` is never touched here.
///
/// The handler is registered as soon as [instance] is first read, so the
/// entrypoint creates it before its first `await`: the host sends the last
/// state right after the engine exists and Flutter buffers it until a handler
/// is up.
class ExternalDisplayStateChannel {
  ExternalDisplayStateChannel._() {
    channel.setMessageHandler(_onMessage);
  }

  static final ExternalDisplayStateChannel instance =
      ExternalDisplayStateChannel._();

  /// A separate receiver for tests. It takes over the channel handler; the
  /// last one created receives the messages.
  @visibleForTesting
  factory ExternalDisplayStateChannel.forTesting() =>
      ExternalDisplayStateChannel._();

  static const String channelName = 'neostation/external_display/menu';

  static const BasicMessageChannel<String> channel = BasicMessageChannel<String>(
    channelName,
    StringCodec(),
  );

  final ValueNotifier<SecondaryDisplayStateData?> _state =
      ValueNotifier<SecondaryDisplayStateData?>(null);

  int _received = 0;
  int _rejected = 0;

  /// The last state pushed by the main engine; null before the first one.
  ValueListenable<SecondaryDisplayStateData?> get state => _state;

  /// Messages decoded into a state.
  int get received => _received;

  /// Messages that were not a JSON object of `SecondaryDisplayStateData`.
  int get rejected => _rejected;

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
}
