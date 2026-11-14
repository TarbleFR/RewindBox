// A frame of the interface of 250 ms or more is written to the log with where
// its time went (waiting for the UI thread, building, rasterizing), at most
// one line a second, so the freezes reported on a device can be placed from
// its app.log (DS playlist video, 14 November 2026).
import 'dart:io';
import 'dart:ui' show FrameTiming;

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/ui_refresh_rate_service.dart';
import 'package:ui_refresh_rate/ui_refresh_rate.dart';

FrameTiming _frame(int start, {required int waitMs, required int buildMs, required int rasterMs}) {
  final buildStart = start + waitMs * 1000;
  final buildFinish = buildStart + buildMs * 1000;
  final rasterFinish = buildFinish + rasterMs * 1000;
  return FrameTiming(
    vsyncStart: start,
    buildStart: buildStart,
    buildFinish: buildFinish,
    rasterStart: buildFinish,
    rasterFinish: rasterFinish,
    rasterFinishWallTime: rasterFinish,
  );
}

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();

  test('long frames are logged with their split, at most once a second', () async {
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      UiRefreshRateChannel.channel,
      (_) async => null,
    );
    addTearDown(() => binding.defaultBinaryMessenger
        .setMockMethodCallHandler(UiRefreshRateChannel.channel, null));
    final dir = Directory.systemTemp.createTempSync('long_frame_log');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = File('${dir.path}/app.log');
    LoggerService.instance.attachFileForTesting(file);

    var now = DateTime(2026, 11, 14, 17);
    final service = UiRefreshRateService.forTesting(
      gate: FrontendMediaGate(),
      clock: () => now,
    );
    addTearDown(service.dispose);
    service.startProbe();

    binding.platformDispatcher.onReportTimings!([
      _frame(0, waitMs: 1, buildMs: 3, rasterMs: 4),
      _frame(16000, waitMs: 300, buildMs: 50, rasterMs: 48),
    ]);
    // Another one within the second: counted, not written.
    binding.platformDispatcher.onReportTimings!([
      _frame(500000, waitMs: 2, buildMs: 20, rasterMs: 600),
    ]);
    now = now.add(const Duration(seconds: 2));
    binding.platformDispatcher.onReportTimings!([
      _frame(3000000, waitMs: 2, buildMs: 10, rasterMs: 400),
    ]);
    await Future<void>.delayed(const Duration(milliseconds: 100));

    final lines = file.readAsLinesSync().where((l) => l.contains('UI long frame')).toList();
    expect(lines, hasLength(2), reason: lines.join('\n'));
    expect(lines[0], contains('total 398 ms, waiting 300 ms, build 50 ms, raster 48 ms'));
    expect(lines[1], contains('raster 400 ms'));
    expect(lines[1], contains('(+1 long frames in the last second)'));
  });
}
