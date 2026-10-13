// Answers of `isSessionActive` on `neostation/libretro_internal`, as the
// bytes Flutter 3.47.2's iOS engine sends to Dart: the success envelope of
// StandardMethodCodec, in hex (00, then the value: 01 true, 02 false, 03 and
// four little-endian bytes an int32).
//
// test/libretro_channel_codec_test.py builds the real
// LibretroInternalBridgePlugin with the real Flutter.framework, puts the
// plugin in each state of a launch and has FlutterStandardMethodCodec encode
// its answer in the iOS Simulator: the bytes must be [fixedEnvelopes] with
// this tree and [build453Envelopes] with the Build 453 sources, whose
// `@(a || b)` was boxed as an int. The Dart tests feed these bytes to the
// real MethodChannel instead of mocking it with Dart booleans, which never
// showed the defect.
//
// One entry per line, `'state': 'hex',`: the Python test reads this file.
library;

/// No session: the plugin was never asked to launch, or the last game ended
/// (its session released).
const String envelopeIdle = 'idle';

/// The session exists and presents its view; the emulation thread is not
/// started yet (`launching`).
const String envelopeLaunching = 'launching';

/// The emulation thread runs; the launch has answered.
const String envelopeRunning = 'running';

/// The emulation thread is gone (the core was unloaded and saved) while the
/// plugin still holds the session, until its view is dismissed.
const String envelopeStopped = 'stopped';

/// This tree (Build 454): `@YES` or `@NO`, sent as Dart booleans.
const Map<String, String> fixedEnvelopes = <String, String>{
  'idle': '0002',
  'launching': '0001',
  'running': '0001',
  'stopped': '0002',
};

/// Build 453 (source `81efc210`): `@(self.session.active ||
/// self.launching)`, boxed with numberWithInt: and sent as an int32 0 or 1.
const Map<String, String> build453Envelopes = <String, String>{
  'idle': '000300000000',
  'launching': '000301000000',
  'running': '000301000000',
  'stopped': '000300000000',
};
