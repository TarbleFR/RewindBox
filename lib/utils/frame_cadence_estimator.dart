/// Measured cadence of one burst of consecutive Flutter frames.
///
/// Built from `FrameTiming` vsync timestamps only: it describes the rate at
/// which NeoStation's interface actually produced frames, not the panel's
/// scan-out nor any game's frame rate.
class FrameCadenceSummary {
  const FrameCadenceSummary({
    required this.burstId,
    required this.intervals,
    required this.medianIntervalMicros,
    required this.p95IntervalMicros,
    required this.effectiveHz,
    required this.missedVsyncs,
    required this.budgetOverruns,
  });

  /// Identifier of the burst (increasing; a new burst gets a higher id).
  final int burstId;

  /// Number of vsync intervals the summary is based on.
  final int intervals;

  final double medianIntervalMicros;

  /// 95th percentile (nearest rank) of the intervals.
  final int p95IntervalMicros;

  /// `round(1 000 000 / median interval)`.
  final int effectiveHz;

  /// Intervals longer than 1.5 × the median (at least one vsync skipped).
  final int missedVsyncs;

  /// Frames whose build + raster span exceeded the median interval.
  final int budgetOverruns;

  @override
  String toString() =>
      '${effectiveHz}Hz (median ${(medianIntervalMicros / 1000).toStringAsFixed(2)} ms, '
      'p95 ${(p95IntervalMicros / 1000).toStringAsFixed(2)} ms, n=$intervals, '
      'missed=$missedVsyncs, overruns=$budgetOverruns, burst=$burstId)';
}

/// Pure, bounded estimator of the interface frame cadence.
///
/// Frames are fed in reporting order. A gap longer than [burstGapMicros]
/// between two vsyncs (or an explicit [split]) starts a new burst: an idle
/// interface produces no frames, so idle time never lowers the result. A
/// burst is measurable once it holds [minIntervals] intervals. Memory is
/// bounded: the last [maxIntervals] intervals of the current burst and the
/// summaries of the last [maxHistory] measurable bursts.
class FrameCadenceEstimator {
  FrameCadenceEstimator();

  static const int burstGapMicros = 50000;
  static const int minIntervals = 24;
  static const int maxIntervals = 240;
  static const int maxHistory = 8;

  int? _lastVsyncMicros;
  int _burstId = 0;
  bool _splitRequested = false;
  final List<int> _intervals = <int>[];
  final List<int> _spans = <int>[];
  final List<FrameCadenceSummary> _history = <FrameCadenceSummary>[];

  /// Identifier of the burst the next continuous frame belongs to.
  int get currentBurstId => _burstId;

  /// Summaries of closed measurable bursts, oldest first.
  List<FrameCadenceSummary> get history =>
      List<FrameCadenceSummary>.unmodifiable(_history);

  /// Number of intervals kept for the current burst (bounded).
  int get currentIntervalCount => _intervals.length;

  /// Adds one frame. [vsyncStartMicros] is
  /// `FrameTiming.timestampInMicroseconds(FramePhase.vsyncStart)` and
  /// [totalSpanMicros] is `FrameTiming.totalSpan` in microseconds.
  void add({required int vsyncStartMicros, required int totalSpanMicros}) {
    final last = _lastVsyncMicros;
    final delta = last == null ? null : vsyncStartMicros - last;
    if (delta == null ||
        _splitRequested ||
        delta <= 0 ||
        delta > burstGapMicros) {
      _startBurst();
    } else {
      _intervals.add(delta);
      if (_intervals.length > maxIntervals) _intervals.removeAt(0);
    }
    _spans.add(totalSpanMicros < 0 ? 0 : totalSpanMicros);
    if (_spans.length > maxIntervals + 1) _spans.removeAt(0);
    _lastVsyncMicros = vsyncStartMicros;
  }

  /// The next frame starts a new burst (used when a game starts or ends, and
  /// before a requested measurement). Returns the id that burst will get.
  int split() {
    _splitRequested = true;
    return _lastVsyncMicros == null ? _burstId : _burstId + 1;
  }

  /// Summary of the current burst, or null while it is too short.
  FrameCadenceSummary? get current => summarize(_burstId, _intervals, _spans);

  /// Most recent measurable burst (the current one first).
  FrameCadenceSummary? get latest =>
      current ?? (_history.isEmpty ? null : _history.last);

  /// The measurable burst with the most intervals among bursts whose id is
  /// at least [burstId] (the current one included).
  FrameCadenceSummary? bestSince(int burstId) {
    FrameCadenceSummary? best;
    for (final summary in <FrameCadenceSummary?>[..._history, current]) {
      if (summary == null || summary.burstId < burstId) continue;
      if (best == null || summary.intervals > best.intervals) best = summary;
    }
    return best;
  }

  /// The first measurable burst whose id is at least [burstId].
  FrameCadenceSummary? firstSince(int burstId) {
    for (final summary in <FrameCadenceSummary?>[..._history, current]) {
      if (summary != null && summary.burstId >= burstId) return summary;
    }
    return null;
  }

  void _startBurst() {
    final closing = current;
    if (closing != null) {
      _history.add(closing);
      if (_history.length > maxHistory) _history.removeAt(0);
    }
    if (_lastVsyncMicros != null) _burstId++;
    _splitRequested = false;
    _intervals.clear();
    _spans.clear();
  }

  /// Pure summary of [intervals] (vsync deltas in µs) and [spans] (frame
  /// build + raster durations in µs). Null below [minIntervals].
  static FrameCadenceSummary? summarize(
    int burstId,
    List<int> intervals,
    List<int> spans,
  ) {
    if (intervals.length < minIntervals) return null;
    final sorted = List<int>.of(intervals)..sort();
    final count = sorted.length;
    final middle = count ~/ 2;
    final median = count.isOdd
        ? sorted[middle].toDouble()
        : (sorted[middle - 1] + sorted[middle]) / 2;
    if (median <= 0) return null;
    final rank = (count * 95 + 99) ~/ 100; // ceil(0.95 × n)
    final p95 = sorted[(rank - 1).clamp(0, count - 1)];
    final missed = intervals.where((value) => value > median * 1.5).length;
    final overruns = spans.where((value) => value > median).length;
    return FrameCadenceSummary(
      burstId: burstId,
      intervals: count,
      medianIntervalMicros: median,
      p95IntervalMicros: p95,
      effectiveHz: (1000000 / median).round(),
      missedVsyncs: missed,
      budgetOverruns: overruns,
    );
  }
}
