import 'dart:typed_data';
import 'dart:ui' as ui;

import '../utils/baseline_jpeg.dart';
import 'melonx_profiles_service.dart';

/// Profile pictures in the form the Switch engine stores: a 256 x 256 JPEG of
/// at most 128 KiB.
abstract final class MelonxProfileAvatar {
  static const size = 256;

  /// Background colours offered for a generated picture (ARGB).
  static const presets = <int>[
    0xFFE60012, // red
    0xFF0AB9E6, // blue
    0xFF1EDC00, // green
    0xFFFFC700, // yellow
    0xFFFF6A00, // orange
    0xFF9B4DE0, // purple
    0xFFFF5FA2, // pink
    0xFF5A6570, // grey
  ];

  /// A plain figure on [colour]: RewindBox's own drawing, no console artwork.
  static Future<Uint8List> generated(int colour) async {
    final recorder = ui.PictureRecorder();
    final canvas = ui.Canvas(recorder);
    const extent = 256.0;
    canvas.drawRect(const ui.Rect.fromLTWH(0, 0, extent, extent), ui.Paint()..color = ui.Color(colour));
    final figure = ui.Paint()..color = const ui.Color(0xF2FFFFFF);
    canvas.drawCircle(const ui.Offset(extent / 2, 104), 46, figure);
    canvas.drawOval(const ui.Rect.fromLTWH(40, 164, 176, 168), figure);
    return _encode(await _rasterize(recorder));
  }

  /// [encoded] (any format the platform decodes) cropped to its centred square.
  static Future<Uint8List> fromImage(Uint8List encoded) async {
    final ui.Codec codec;
    try {
      codec = await ui.instantiateImageCodec(encoded);
    } on Object {
      throw const MelonxProfilesException('profileImageInvalid');
    }
    final ui.Image source;
    try {
      source = (await codec.getNextFrame()).image;
    } on Object {
      throw const MelonxProfilesException('profileImageInvalid');
    } finally {
      codec.dispose();
    }
    try {
      final side = source.width < source.height ? source.width : source.height;
      if (side < 1) throw const MelonxProfilesException('profileImageInvalid');
      final recorder = ui.PictureRecorder();
      // JPEG has no transparency: a see-through picture gets a white ground.
      ui.Canvas(recorder)
        ..drawRect(const ui.Rect.fromLTWH(0, 0, 256, 256), ui.Paint()..color = const ui.Color(0xFFFFFFFF))
        ..drawImageRect(
        source,
        ui.Rect.fromLTWH((source.width - side) / 2, (source.height - side) / 2, side.toDouble(), side.toDouble()),
        const ui.Rect.fromLTWH(0, 0, 256, 256),
        ui.Paint()..filterQuality = ui.FilterQuality.high,
      );
      return _encode(await _rasterize(recorder));
    } finally {
      source.dispose();
    }
  }

  static Future<Uint8List> _rasterize(ui.PictureRecorder recorder) async {
    final picture = recorder.endRecording();
    try {
      final image = await picture.toImage(size, size);
      try {
        final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
        if (data == null) throw const MelonxProfilesException('profileImageInvalid');
        return data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
      } finally {
        image.dispose();
      }
    } finally {
      picture.dispose();
    }
  }

  /// Lowers the quality until the picture fits the guest's buffer.
  static Uint8List _encode(Uint8List rgba) {
    for (final quality in const [90, 80, 65, 50, 35]) {
      final jpeg = BaselineJpeg.encode(rgba, size, size, quality: quality);
      if (jpeg.length <= MelonxProfilesService.maxImageBytes) return jpeg;
    }
    throw const MelonxProfilesException('profileImageInvalid');
  }
}
