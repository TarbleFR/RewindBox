// Selection tracks by Mau Ali, Lottie Simple License FL 9.13.21.
// Source archive, generated data and full attribution are bundled together.
import 'dart:convert';
import 'dart:ui';
import 'package:flutter/animation.dart';
import 'mau_ali_tab_motion_data.dart';

abstract final class MauAliTabMotion {
  static final Map<String, dynamic> data = jsonDecode(mauAliSelectionSource);
  static const duration = Duration(milliseconds: 550); // 33 frames / 60 fps.
  static const position = Cubic(.358, .965, .56, 1);
  static final Map<String, dynamic> _tracks = data['tracks'];
  static final List<dynamic> segments = data['segments'];
  static const _states = ['P', 'W', 'S', 'A', 'Pr'];

  static String segmentFor(double from, int to, int count) {
    final start = (from * 4 / (count - 1).clamp(1, 100)).round().clamp(0, 4);
    var end = (to * 4 / (count - 1).clamp(1, 100)).round().clamp(0, 4);
    if (end == start) end = (start + (to > from ? 1 : -1)).clamp(0, 4);
    if (end == start) end = start == 0 ? 1 : start - 1;
    return '${_states[start]}n${_states[end]}';
  }

  static Map<String, dynamic> segment(String name) =>
      segments.cast<Map<String, dynamic>>().firstWhere((s) => s['cm'] == name);

  static Duration durationFor(String name) => Duration(
    microseconds: ((segment(name)['dr'] as num) / 60 * 1000000).round(),
  );

  static MauAliSelectionFrame sample(String name, double t) {
    final marker = segment(name);
    final start = (marker['tm'] as num).toDouble();
    final frame = start + (marker['dr'] as num) * t.clamp(0, 1);
    List<double> vector(String track, double at) =>
        (_at(_tracks[track], at) as List)
            .map((n) => (n as num).toDouble())
            .toList();
    final p = vector('position', frame);
    final a = vector('position', start),
        b = vector('position', start + (marker['dr'] as num));
    final scale = vector('scale', frame);
    final container = vector('container', frame);
    final shape = (_at(_tracks['path'], frame) as List).first as Map;
    final rimStart = vector('rimStart', frame),
        rimEnd = vector('rimEnd', frame);
    double scalar(String name) {
      final value = _at(_tracks[name], frame);
      return ((value is List ? value.first : value) as num).toDouble() / 100;
    }

    return MauAliSelectionFrame(
      position: (b[0] - a[0]).abs() < .01
          ? t
          : ((p[0] - a[0]) / (b[0] - a[0])).clamp(0, 1),
      scaleX: scale[0] / 161.29,
      scaleY: scale[1] / 161.29,
      containerScale: container[0] / 60.909,
      shape: shape,
      rimStart: Offset(rimStart[0], rimStart[1]),
      rimEnd: Offset(rimEnd[0], rimEnd[1]),
      rimOpacity: scalar('rimOpacity'),
      fillOpacity: scalar('fillOpacity'),
    );
  }

  // Preserve the public profile accessor for callers inspecting the first hop.
  static (double, double) scale(double t) {
    final frame = sample('PnW', t);
    return (frame.scaleX, frame.scaleY);
  }

  static Object? _at(Map track, double frame) {
    if (track['a'] == 0) return track['k'];
    final keys = track['k'] as List;
    if (frame <= (keys.first['t'] as num)) return keys.first['s'];
    for (var i = 0; i < keys.length - 1; i++) {
      final a = keys[i] as Map, b = keys[i + 1] as Map;
      if (frame > (b['t'] as num)) continue;
      if (a['h'] == 1) return a['s'];
      final t =
          ((frame - (a['t'] as num)) / ((b['t'] as num) - (a['t'] as num)))
              .clamp(0.0, 1.0);
      double component(Object? value, int index) =>
          ((value is List ? value[index.clamp(0, value.length - 1)] : value)
                  as num)
              .toDouble();
      double eased(int index) => Cubic(
        component(a['o']['x'], index),
        component(a['o']['y'], index),
        component(a['i']['x'], index),
        component(a['i']['y'], index),
      ).transform(t);
      return _mix(a['s'], b['s'], eased);
    }
    return keys.last['s'];
  }

  static Object? _mix(
    Object? a,
    Object? b,
    double Function(int) t, [
    int component = 0,
  ]) {
    if (a is num && b is num) return a + (b - a) * t(component);
    if (a is List && b is List) {
      return [for (var i = 0; i < a.length; i++) _mix(a[i], b[i], t, i)];
    }
    if (a is Map && b is Map) {
      return {for (final k in a.keys) k: _mix(a[k], b[k], t)};
    }
    return a;
  }
}

class MauAliSelectionFrame {
  const MauAliSelectionFrame({
    required this.position,
    required this.scaleX,
    required this.scaleY,
    required this.containerScale,
    required this.shape,
    required this.rimStart,
    required this.rimEnd,
    required this.rimOpacity,
    required this.fillOpacity,
  });
  final double position,
      scaleX,
      scaleY,
      containerScale,
      rimOpacity,
      fillOpacity;
  final Map shape;
  final Offset rimStart, rimEnd;

  Path contour(Size size) {
    final vertices = shape['v'] as List,
        incoming = shape['i'] as List,
        outgoing = shape['o'] as List;
    Offset point(List p) =>
        Offset((p[0] as num).toDouble(), (p[1] as num).toDouble());
    Offset mapped(Offset p) => Offset(
      size.width / 2 + p.dx / 161 * size.width,
      size.height / 2 + p.dy / 100 * size.height,
    );
    final first = mapped(point(vertices.first));
    final path = Path()..moveTo(first.dx, first.dy);
    for (var i = 0; i < vertices.length; i++) {
      final next = (i + 1) % vertices.length;
      final c1 = mapped(point(vertices[i]) + point(outgoing[i]));
      final c2 = mapped(point(vertices[next]) + point(incoming[next]));
      final end = mapped(point(vertices[next]));
      path.cubicTo(c1.dx, c1.dy, c2.dx, c2.dy, end.dx, end.dy);
    }
    return path..close();
  }
}
