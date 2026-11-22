import 'logger_service.dart';

/// Startup timeline written to app.log.
///
/// app.log lines carry no time of their own, so the launch could not be
/// measured from the log. Each mark here writes one line,
/// `Startup: <step> <ms> ms (t=<ms> ms)`: the time the step took since the
/// previous mark, and the time since `main()` began. The last line,
/// `Startup: interactive`, is written when the startup overlay has faded
/// out and the interface takes input. Nothing else changes: marks only log.
class StartupTimeline {
  StartupTimeline._();

  static final Stopwatch _clock = Stopwatch();
  static int _last = 0;

  /// Starts the clock; called first thing in `main()`.
  static void start() {
    _clock
      ..reset()
      ..start();
    _last = 0;
  }

  /// Logs the time since the previous mark under [step]. No-op once the
  /// interface is interactive (later work is not startup any more).
  static void mark(String step) {
    if (!_clock.isRunning) return;
    final now = _clock.elapsedMilliseconds;
    final took = now - _last;
    _last = now;
    LoggerService.instance.i('Startup: $step $took ms (t=$now ms)');
  }

  /// Logs a step that started at [startedAt] (a value of [elapsed]) and may
  /// overlap other steps, such as the startup ROM scan.
  static void span(String step, int startedAt) {
    if (!_clock.isRunning) return;
    final now = _clock.elapsedMilliseconds;
    LoggerService.instance.i(
      'Startup: $step ${now - startedAt} ms (t=$now ms)',
    );
  }

  /// Milliseconds since `main()` began, for [span].
  static int get elapsed => _clock.elapsedMilliseconds;

  /// The startup overlay is gone: the last mark, then the clock stops.
  static void interactive() {
    if (!_clock.isRunning) return;
    mark('interactive');
    _clock.stop();
  }
}
