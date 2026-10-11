import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/utils/frame_cadence_estimator.dart';

/// Feeds [count] frames spaced by [intervalMicros] starting at [start] and
/// returns the vsync of the last frame.
int feed(
  FrameCadenceEstimator estimator, {
  required int start,
  required int count,
  required double intervalMicros,
  int spanMicros = 4000,
}) {
  var vsync = start;
  for (var index = 0; index < count; index++) {
    vsync = start + (index * intervalMicros).round();
    estimator.add(vsyncStartMicros: vsync, totalSpanMicros: spanMicros);
  }
  return vsync;
}

void main() {
  test('8.333 ms vsyncs measure 120 Hz and 16.667 ms vsyncs measure 60 Hz', () {
    final fast = FrameCadenceEstimator();
    feed(fast, start: 1000000, count: 121, intervalMicros: 1000000 / 120);
    expect(fast.latest!.effectiveHz, 120);
    expect(fast.latest!.missedVsyncs, 0);
    expect(fast.latest!.budgetOverruns, 0);

    final slow = FrameCadenceEstimator();
    feed(slow, start: 1000000, count: 61, intervalMicros: 1000000 / 60);
    expect(slow.latest!.effectiveHz, 60);
  });

  test('jank keeps the median rate and counts skipped vsyncs and overruns', () {
    final estimator = FrameCadenceEstimator();
    var vsync = 5000000;
    estimator.add(vsyncStartMicros: vsync, totalSpanMicros: 3000);
    for (var index = 1; index <= 60; index++) {
      // Every tenth frame misses one vsync (16.7 ms instead of 8.3 ms) and
      // took longer than a 120 Hz frame budget.
      final late = index % 10 == 0;
      vsync += late ? 16667 : 8333;
      estimator.add(
        vsyncStartMicros: vsync,
        totalSpanMicros: late ? 12000 : 3000,
      );
    }
    final summary = estimator.latest!;
    expect(summary.effectiveHz, 120);
    expect(summary.intervals, 60);
    expect(summary.missedVsyncs, 6);
    expect(summary.budgetOverruns, 6);
    expect(summary.p95IntervalMicros, 16667);
  });

  test(
    'a gap over 50 ms splits bursts and idle time never lowers the rate',
    () {
      final estimator = FrameCadenceEstimator();
      final end = feed(
        estimator,
        start: 0,
        count: 61,
        intervalMicros: 1000000 / 60,
      );
      // Two seconds idle (no frames), then a 120 Hz scroll.
      feed(
        estimator,
        start: end + 2000000,
        count: 49,
        intervalMicros: 1000000 / 120,
      );
      expect(estimator.history, hasLength(1));
      expect(estimator.history.single.effectiveHz, 60);
      expect(estimator.latest!.effectiveHz, 120);
      expect(
        estimator.latest!.burstId,
        greaterThan(estimator.history.single.burstId),
      );
    },
  );

  test('fewer than 24 intervals gives no result', () {
    final estimator = FrameCadenceEstimator();
    feed(estimator, start: 0, count: 24, intervalMicros: 8333);
    expect(estimator.currentIntervalCount, 23);
    expect(estimator.latest, isNull);
    estimator.add(vsyncStartMicros: 24 * 8333, totalSpanMicros: 1000);
    expect(estimator.latest!.effectiveHz, 120);
  });

  test('memory stays bounded to the recent window and eight bursts', () {
    final estimator = FrameCadenceEstimator();
    // A long 60 Hz scroll followed, without a gap, by 120 Hz frames: only the
    // last 240 intervals count.
    var end = feed(estimator, start: 0, count: 600, intervalMicros: 16667);
    end = feed(estimator, start: end + 8333, count: 241, intervalMicros: 8333);
    expect(estimator.currentIntervalCount, FrameCadenceEstimator.maxIntervals);
    expect(estimator.latest!.effectiveHz, 120);

    for (var burst = 0; burst < 20; burst++) {
      end = feed(
        estimator,
        start: end + 1000000,
        count: 30,
        intervalMicros: 8333,
      );
    }
    expect(estimator.history, hasLength(FrameCadenceEstimator.maxHistory));
  });

  test('a split starts a new burst whose id split() announces', () {
    final estimator = FrameCadenceEstimator();
    expect(estimator.split(), 0, reason: 'no frame yet: the first burst');
    var end = feed(estimator, start: 0, count: 30, intervalMicros: 8333);
    final next = estimator.split();
    expect(next, estimator.currentBurstId + 1);
    end = feed(estimator, start: end + 8333, count: 30, intervalMicros: 16667);
    expect(estimator.currentBurstId, next);
    expect(estimator.latest!.effectiveHz, 60);
    expect(estimator.history.single.effectiveHz, 120);
  });

  test('the post-game search keeps the first measurable burst only', () {
    final estimator = FrameCadenceEstimator();
    var end = feed(estimator, start: 0, count: 61, intervalMicros: 16667);
    final armed = estimator.split();
    // A few frames (too short), a pause, then a measurable 120 Hz burst, a
    // pause and another 60 Hz burst.
    end = feed(estimator, start: end + 8333, count: 5, intervalMicros: 8333);
    end = feed(estimator, start: end + 500000, count: 40, intervalMicros: 8333);
    end = feed(
      estimator,
      start: end + 500000,
      count: 40,
      intervalMicros: 16667,
    );
    final first = estimator.firstSince(armed)!;
    expect(first.effectiveHz, 120);
    expect(first.burstId, greaterThan(armed));
    expect(estimator.latest!.effectiveHz, 60);
  });

  test('bestSince keeps the longest measurable burst of a measurement', () {
    final estimator = FrameCadenceEstimator();
    final from = estimator.split();
    var end = feed(estimator, start: 0, count: 30, intervalMicros: 16667);
    end = feed(
      estimator,
      start: end + 100000,
      count: 150,
      intervalMicros: 8333,
    );
    feed(estimator, start: end + 100000, count: 26, intervalMicros: 16667);
    final best = estimator.bestSince(from)!;
    expect(best.effectiveHz, 120);
    expect(best.intervals, 149);
    expect(estimator.bestSince(estimator.currentBurstId + 1), isNull);
  });

  test('summarize is pure and rejects short or empty input', () {
    expect(
      FrameCadenceEstimator.summarize(0, const <int>[], const <int>[]),
      isNull,
    );
    final intervals = List<int>.filled(24, 8333);
    final summary = FrameCadenceEstimator.summarize(
      3,
      intervals,
      const <int>[],
    )!;
    expect(summary.effectiveHz, 120);
    expect(summary.burstId, 3);
    expect(intervals, everyElement(8333));
  });
}
