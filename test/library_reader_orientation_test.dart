import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:neostation/services/library_reader_orientation.dart';

/// Records the calls in the order they reach the platform.
class _RecordingPlatform implements LibraryReaderOrientationPlatform {
  _RecordingPlatform({this.nativeGrants = true});

  bool nativeGrants;
  final List<String> calls = <String>[];

  @override
  Future<bool> setNativePortraitAllowed(bool allowed) async {
    calls.add('native:$allowed');
    return allowed ? nativeGrants : true;
  }

  @override
  Future<void> setPreferredOrientations(
    List<DeviceOrientation> orientations,
  ) async {
    calls.add(
      orientations.contains(DeviceOrientation.portraitUp)
          ? 'flutter:portrait+landscape'
          : 'flutter:landscape',
    );
  }
}

/// The native allow call answers only when [nativeReply] completes.
class _SlowPlatform implements LibraryReaderOrientationPlatform {
  final List<String> calls = <String>[];
  final Completer<bool> nativeReply = Completer<bool>();

  @override
  Future<bool> setNativePortraitAllowed(bool allowed) {
    calls.add('native:$allowed');
    return allowed ? nativeReply.future : Future<bool>.value(true);
  }

  @override
  Future<void> setPreferredOrientations(
    List<DeviceOrientation> orientations,
  ) async {
    calls.add(
      orientations.contains(DeviceOrientation.portraitUp)
          ? 'flutter:portrait+landscape'
          : 'flutter:landscape',
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('LibraryReaderOrientation', () {
    test(
      'enter allows the native mask before Flutter asks for portrait',
      () async {
        final platform = _RecordingPlatform();
        final orientation = LibraryReaderOrientation(
          platform: platform,
          isIOS: true,
        );

        await orientation.enter(allowRotation: true);
        expect(platform.calls, <String>[
          'native:true',
          'flutter:portrait+landscape',
        ]);
        expect(orientation.portraitActive, isTrue);

        await orientation.exit();
        expect(platform.calls, <String>[
          'native:true',
          'flutter:portrait+landscape',
          'flutter:landscape',
          'native:false',
        ]);
        expect(orientation.portraitActive, isFalse);
      },
    );

    test(
      'Flutter never asks for portrait when the native side refuses',
      () async {
        final platform = _RecordingPlatform(nativeGrants: false);
        final orientation = LibraryReaderOrientation(
          platform: platform,
          isIOS: true,
        );

        await orientation.enter(allowRotation: true);
        expect(platform.calls, <String>['native:true']);
        expect(orientation.portraitActive, isFalse);

        // Nothing was changed, so nothing is restored.
        await orientation.exit();
        expect(platform.calls, <String>['native:true']);
      },
    );

    test(
      'nothing happens outside iOS or when rotation is not allowed',
      () async {
        final android = _RecordingPlatform();
        final notIos = LibraryReaderOrientation(
          platform: android,
          isIOS: false,
        );
        await notIos.enter(allowRotation: true);
        await notIos.exit();
        expect(android.calls, isEmpty);

        final locked = _RecordingPlatform();
        final noRotation = LibraryReaderOrientation(
          platform: locked,
          isIOS: true,
        );
        await noRotation.enter(allowRotation: false);
        await noRotation.exit();
        expect(locked.calls, isEmpty);
      },
    );

    test(
      'nested readers: only the first enter and the last exit act',
      () async {
        final platform = _RecordingPlatform();
        final orientation = LibraryReaderOrientation(
          platform: platform,
          isIOS: true,
        );

        await orientation.enter(allowRotation: true);
        await orientation.enter(allowRotation: true);
        expect(orientation.depth, 2);
        expect(platform.calls, <String>[
          'native:true',
          'flutter:portrait+landscape',
        ]);

        await orientation.exit();
        expect(orientation.portraitActive, isTrue);
        expect(platform.calls.length, 2);

        await orientation.exit();
        expect(platform.calls.sublist(2), <String>[
          'flutter:landscape',
          'native:false',
        ]);
        expect(orientation.depth, 0);

        // An extra exit is ignored.
        await orientation.exit();
        expect(platform.calls.length, 4);
      },
    );

    test('an enter and exit with nothing in between change nothing', () async {
      final platform = _RecordingPlatform();
      final orientation = LibraryReaderOrientation(
        platform: platform,
        isIOS: true,
      );
      final entering = orientation.enter(allowRotation: true);
      final leaving = orientation.exit();
      await Future.wait(<Future<void>>[entering, leaving]);
      expect(platform.calls, isEmpty);
      expect(orientation.portraitActive, isFalse);
    });

    test('an exit during a pending enter runs after it (serialized)', () async {
      final platform = _SlowPlatform();
      final orientation = LibraryReaderOrientation(
        platform: platform,
        isIOS: true,
      );
      final entering = orientation.enter(allowRotation: true);
      await Future<void>.delayed(Duration.zero);
      // The native call of enter is still pending when the reader closes.
      expect(platform.calls, <String>['native:true']);
      final leaving = orientation.exit();
      platform.nativeReply.complete(true);
      await Future.wait(<Future<void>>[entering, leaving]);
      expect(platform.calls, <String>[
        'native:true',
        'flutter:portrait+landscape',
        'flutter:landscape',
        'native:false',
      ]);
      expect(orientation.portraitActive, isFalse);
    });

    test(
      'turning rotation off in the settings restores landscape at once',
      () async {
        final platform = _RecordingPlatform();
        final orientation = LibraryReaderOrientation(
          platform: platform,
          isIOS: true,
        );
        await orientation.enter(allowRotation: true);
        await orientation.setAllowRotation(false);
        expect(platform.calls.sublist(2), <String>[
          'flutter:landscape',
          'native:false',
        ]);
        await orientation.setAllowRotation(true);
        expect(platform.calls.sublist(4), <String>[
          'native:true',
          'flutter:portrait+landscape',
        ]);
        await orientation.exit();
        expect(platform.calls.sublist(6), <String>[
          'flutter:landscape',
          'native:false',
        ]);
      },
    );
  });

  group('platform channels', () {
    const bridge = MethodChannel('neostation/libretro_internal');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    late List<String> calls;
    late bool nativeAnswer;

    setUp(() {
      calls = <String>[];
      nativeAnswer = true;
      messenger.setMockMethodCallHandler(bridge, (call) async {
        if (call.method == 'setReaderOrientation') {
          final allow = (call.arguments as Map)['allowPortrait'] as bool;
          calls.add('bridge:setReaderOrientation:$allow');
          return allow ? nativeAnswer : true;
        }
        return null;
      });
      messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
        if (call.method == 'SystemChrome.setPreferredOrientations') {
          final list = (call.arguments as List).cast<String>();
          calls.add('chrome:${list.join(',')}');
        }
        return null;
      });
    });

    tearDown(() {
      messenger.setMockMethodCallHandler(bridge, null);
      messenger.setMockMethodCallHandler(SystemChannels.platform, null);
    });

    test(
      'enter and exit go through the bridge and SystemChrome in order',
      () async {
        final orientation = LibraryReaderOrientation(isIOS: true);
        await orientation.enter(allowRotation: true);
        await orientation.exit();
        expect(calls, <String>[
          'bridge:setReaderOrientation:true',
          'chrome:DeviceOrientation.portraitUp,DeviceOrientation.landscapeLeft,'
              'DeviceOrientation.landscapeRight',
          'chrome:DeviceOrientation.landscapeLeft,DeviceOrientation.landscapeRight',
          'bridge:setReaderOrientation:false',
        ]);
      },
    );

    test(
      'a refusal of the bridge (game running) keeps Flutter landscape',
      () async {
        nativeAnswer = false;
        final orientation = LibraryReaderOrientation(isIOS: true);
        await orientation.enter(allowRotation: true);
        await orientation.exit();
        expect(calls, <String>['bridge:setReaderOrientation:true']);
      },
    );

    test('the bridge reports false when the plugin is missing', () async {
      messenger.setMockMethodCallHandler(bridge, null);
      expect(
        await LibretroInternalBridge.setReaderOrientation(allowPortrait: true),
        isFalse,
      );
    });

    test('the bridge reports false on a platform error', () async {
      messenger.setMockMethodCallHandler(bridge, (call) async {
        throw PlatformException(code: 'boom');
      });
      expect(
        await LibretroInternalBridge.setReaderOrientation(allowPortrait: true),
        isFalse,
      );
    });
  });
}
