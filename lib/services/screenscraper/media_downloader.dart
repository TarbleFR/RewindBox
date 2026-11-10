import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as path;
import 'package:neostation/services/logger_service.dart';

import 'region_config.dart';
import 'rom_hasher.dart';
import 'media_placeholder.dart';
import 'media_resolver.dart';
import 'screenscraper_client.dart';

/// Media asset downloader for ScreenScraper.
///
/// ScreenScraper can legitimately return HTTP 200 with a small textual status
/// such as `NOMEDIA`, `CRCOK`, `MD5OK` or `SHA1OK`. Those responses must never
/// be written as PNG/MP4/PDF files. Every payload is therefore signature-checked
/// before it replaces an existing media file.
class ScreenscraperMediaDownloader {
  ScreenscraperMediaDownloader._();

  static final _log = LoggerService.instance;

  static Future<void> _removeCompetingImageVariants(String fullPath) async {
    final targetExt = path
        .extension(fullPath)
        .replaceFirst('.', '')
        .toLowerCase();
    if (!const {'png', 'jpg', 'jpeg', 'webp'}.contains(targetExt)) return;

    final base = path.withoutExtension(fullPath);
    for (final ext in const ['png', 'jpg', 'jpeg', 'webp']) {
      if (ext == targetExt) continue;
      final sibling = File('$base.$ext');
      try {
        if (await sibling.exists()) await sibling.delete();
      } catch (_) {
        // A stale sibling that cannot be removed must not abort a scrape.
      }
    }
  }

  static const _imageExtensions = ['png', 'jpg', 'jpeg', 'webp'];

  /// The media already on disk for [fullPath]: that file, or for a picture
  /// the same name with another image extension (a cover imported as JPEG
  /// stands for the PNG ScreenScraper would send).
  static Future<String?> _existingMediaPath(String fullPath) async {
    if (await File(fullPath).exists()) return fullPath;
    final ext = path.extension(fullPath).replaceFirst('.', '').toLowerCase();
    if (!_imageExtensions.contains(ext)) return null;
    final base = path.withoutExtension(fullPath);
    for (final other in _imageExtensions) {
      if (other == ext) continue;
      final candidate = '$base.$other';
      if (await File(candidate).exists()) return candidate;
    }
    return null;
  }

  static Future<({bool success, bool wasExisting, bool replaced})> _downloadMediaFileSmart(
    String url,
    String relativePath,
    String userDataDir, {
    required String mediaType,
    bool forceOverwrite = false,
    int? maxDailyRequests,
    String? systemFolder,
    ScreenscraperMediaVariants? variants,
  }) async {
    final fullPath = path.join(userDataDir, relativePath);
    final file = File(fullPath);

    try {
      var replacing = false;
      final existingPath = await _existingMediaPath(fullPath);
      if (existingPath != null) {
        final validExisting = await isValidMediaFile(File(existingPath), mediaType);
        if (validExisting && !forceOverwrite) {
          // Content already present is kept, unless it is an imported
          // console icon or, when the choices changed, a ScreenScraper
          // picture of another variant than the best one for them.
          final placeholder =
              systemFolder != null && ScrapeMediaPlaceholder.isPlaceholder(systemFolder, mediaType, existingPath);
          final otherVariant = !placeholder && variants != null && await variants.isOtherVariant(existingPath);
          if (!placeholder && !otherVariant) {
            if (existingPath == fullPath) await _removeCompetingImageVariants(fullPath);
            return (success: true, wasExisting: true, replaced: false);
          }
          replacing = true;
        } else if (validExisting) {
          replacing = true;
        } else if (existingPath == fullPath) {
          try {
            await file.delete();
          } catch (_) {}
        }
      }

      final response = await ScreenscraperClient.httpGetWithRetry(
        Uri.parse(url),
        timeout: const Duration(seconds: 60),
        maxRetries: 2,
        maxDailyRequests: maxDailyRequests,
      );
      if (response.statusCode != 200) {
        _log.e('Error downloading media (${response.statusCode}): $url');
        return (success: false, wasExisting: false, replaced: false);
      }

      final contentType = response.headers['content-type'] ?? '';
      if (!isValidMediaPayload(
        response.bodyBytes,
        mediaType: mediaType,
        contentType: contentType,
      )) {
        _log.w(
          'Rejected invalid ScreenScraper $mediaType payload '
          '(${response.bodyBytes.length} bytes, $contentType): '
          '${_safeBodyPrefix(response.bodyBytes)}',
        );
        return (success: false, wasExisting: false, replaced: false);
      }

      await file.parent.create(recursive: true);
      final temp = File('$fullPath.part');
      try {
        if (await temp.exists()) await temp.delete();
        await temp.writeAsBytes(response.bodyBytes, flush: true);
        if (await file.exists()) await file.delete();
        await temp.rename(fullPath);
      } finally {
        if (await temp.exists()) {
          try {
            await temp.delete();
          } catch (_) {}
        }
      }

      await _removeCompetingImageVariants(fullPath);
      return (success: true, wasExisting: false, replaced: replacing);
    } catch (e) {
      _log.e('Error downloading media: $e');
      return (success: false, wasExisting: false, replaced: false);
    }
  }

  /// The "box faces" setting stands for the three ScreenScraper types of the
  /// 3D box: back, spine and support (docs/game-box-3d.md § 5).
  static const List<String> boxFaceTypes = ['box-2D-back', 'box-2D-side', 'support-2D'];

  /// Media types to download for the enabled settings, in order, once each.
  static List<String> expandMediaTypes(List<String> enabled) {
    final out = <String>[];
    for (final type in enabled) {
      for (final t in type == 'boxFaces' ? boxFaceTypes : [type]) {
        if (!out.contains(t)) out.add(t);
      }
    }
    return out;
  }

  /// Downloads one media to [fullPath] with the scrape's own validation,
  /// atomic write and removal of other-extension siblings (3D box faces,
  /// docs/game-box-3d.md § 6).
  static Future<bool> downloadValidatedMedia(
    String url,
    String fullPath, {
    required String mediaType,
    bool forceOverwrite = false,
  }) async {
    final outcome = await _downloadMediaFileSmart(
      url,
      path.basename(fullPath),
      path.dirname(fullPath),
      mediaType: mediaType,
      forceOverwrite: forceOverwrite,
    );
    return outcome.success;
  }

  /// Returns whether an on-disk media file matches the expected media type.
  static Future<bool> isValidMediaFile(File file, String mediaType) async {
    try {
      if (!await file.exists()) return false;
      // The signatures sit in the first bytes: a video is not read whole.
      final raf = await file.open();
      try {
        final bytes = await raf.read(256);
        return isValidMediaPayload(bytes, mediaType: mediaType);
      } finally {
        await raf.close();
      }
    } catch (_) {
      return false;
    }
  }

  /// Signature validation shared by the normal downloader, game-id fallback
  /// and unit tests.
  static bool isValidMediaPayload(
    List<int> bytes, {
    required String mediaType,
    String contentType = '',
  }) {
    if (bytes.length < 4) return false;
    if (_isTextStatus(bytes)) return false;

    switch (mediaType) {
      case 'video':
        return _looksLikeMp4(bytes);
      case 'manuel':
        return bytes.length >= 5 &&
            bytes[0] == 0x25 &&
            bytes[1] == 0x50 &&
            bytes[2] == 0x44 &&
            bytes[3] == 0x46 &&
            bytes[4] == 0x2d;
      default:
        return _looksLikeImage(bytes);
    }
  }

  static bool _isTextStatus(List<int> bytes) {
    final prefix = _safeBodyPrefix(bytes).toUpperCase();
    return prefix.startsWith('NOMEDIA') ||
        prefix.startsWith('CRCOK') ||
        prefix.startsWith('MD5OK') ||
        prefix.startsWith('SHA1OK') ||
        prefix.startsWith('<!DOCTYPE') ||
        prefix.startsWith('<HTML') ||
        prefix.startsWith('{"ERROR"') ||
        prefix.startsWith('{"HEADER"');
  }

  static bool _looksLikeImage(List<int> bytes) {
    final isPng =
        bytes.length >= 8 &&
        bytes[0] == 0x89 &&
        bytes[1] == 0x50 &&
        bytes[2] == 0x4e &&
        bytes[3] == 0x47 &&
        bytes[4] == 0x0d &&
        bytes[5] == 0x0a &&
        bytes[6] == 0x1a &&
        bytes[7] == 0x0a;
    if (isPng) return true;

    final isJpeg =
        bytes.length >= 3 &&
        bytes[0] == 0xff &&
        bytes[1] == 0xd8 &&
        bytes[2] == 0xff;
    if (isJpeg) return true;

    final isGif =
        bytes.length >= 6 &&
        ascii
            .decode(bytes.sublist(0, 6), allowInvalid: true)
            .startsWith('GIF8');
    if (isGif) return true;

    return bytes.length >= 12 &&
        ascii.decode(bytes.sublist(0, 4), allowInvalid: true) == 'RIFF' &&
        ascii.decode(bytes.sublist(8, 12), allowInvalid: true) == 'WEBP';
  }

  static bool _looksLikeMp4(List<int> bytes) {
    if (bytes.length < 12) return false;
    final limit = bytes.length < 96 ? bytes.length - 4 : 92;
    for (var index = 4; index <= limit; index++) {
      if (bytes[index] == 0x66 &&
          bytes[index + 1] == 0x74 &&
          bytes[index + 2] == 0x79 &&
          bytes[index + 3] == 0x70) {
        return true;
      }
    }
    return false;
  }

  static String _safeBodyPrefix(List<int> bytes) {
    if (bytes.isEmpty) return '<empty>';
    final take = bytes.length > 48 ? 48 : bytes.length;
    return utf8
        .decode(bytes.sublist(0, take), allowMalformed: true)
        .replaceAll(RegExp(r'[\r\n\t]+'), ' ')
        .trim();
  }

  /// Downloads the media of one game for the enabled settings.
  ///
  /// Media already present are kept unless [forceOverwrite] ("All content"),
  /// except an imported console icon, always replaced. [protectedTypes] are
  /// never written: faces chosen by hand or by the box-media sources
  /// (docs/game-box-3d.md § 18). With [replaceOtherVariants] ("New content
  /// only" after the choices changed), a picture or a manual proven to be
  /// another ScreenScraper variant (same MD5 as one ScreenScraper lists) is
  /// replaced by the best one for the current regions and language (§ 19).
  static Future<Map<String, dynamic>> downloadGameMedia(
    String systemFolder,
    String romName,
    List<dynamic> medias,
    int maxThreads, {
    String? appSystemId,
    String? preferredLanguage,
    bool Function()? shouldCancel,
    Function(double progress)? onProgress,
    List<String>? allowedMediaTypes,
    bool forceOverwrite = false,
    int? maxDailyRequests,
    Set<String> protectedTypes = const {},
    bool replaceOtherVariants = false,
  }) async {
    final mediaTypes = expandMediaTypes(
      allowedMediaTypes ?? ['fanart', 'ss', 'video', 'wheel', 'box2D'],
    );
    final protectedEnabled = [
      for (final t in mediaTypes)
        if (protectedTypes.contains(t)) t,
    ];
    if (medias.isEmpty) {
      return {
        'success': true,
        'downloadedTypes': <String>[],
        'existingTypes': protectedEnabled,
        'replacedTypes': <String>[],
        'protectedTypes': protectedEnabled,
        'cancelled': false,
      };
    }

    final userDataDir = await ScreenscraperMediaResolver.getMediaDirectory();
    final regionPriority = await ScreenscraperRegionConfig.getRegionPriority();

    final downloadTasks = <Map<String, dynamic>>[];
    for (final mediaType in mediaTypes) {
      if (protectedTypes.contains(mediaType)) continue;
      final bestMedia = ScreenscraperMediaResolver.selectBestMedia(
        medias,
        mediaType,
        preferredLanguage: preferredLanguage,
        regionPriority: regionPriority,
      );
      if (bestMedia == null) continue;

      final folderName = ScreenscraperMediaResolver.mapMediaTypeToFolder(
        mediaType,
      );
      final romBaseName = await ScreenscraperRomHasher.getCleanRomName(
        romName,
        appSystemId,
      );
      final rawFormat = bestMedia['format']?.toString().toLowerCase();
      final fileFormat = switch (mediaType) {
        'video' => 'mp4',
        'manuel' => 'pdf',
        _ => (rawFormat == null || rawFormat.isEmpty) ? 'png' : rawFormat,
      };
      downloadTasks.add({
        'url': bestMedia['url'].toString(),
        'relativePath': '$systemFolder/$folderName/$romBaseName.$fileFormat',
        'mediaType': mediaType,
        // A manual is replaced too: a new language brings its own print.
        if (replaceOtherVariants && mediaType != 'video')
          'variants': ScreenscraperMediaVariants.of(
            bestMedia,
            ScreenscraperMediaResolver.candidatesOf(medias, mediaType),
          ),
      });
    }

    if (downloadTasks.isEmpty) {
      return {
        'success': true,
        'downloadedTypes': <String>[],
        'existingTypes': protectedEnabled,
        'replacedTypes': <String>[],
        'protectedTypes': protectedEnabled,
        'cancelled': false,
      };
    }

    final batches = <List<Map<String, dynamic>>>[];
    for (var i = 0; i < downloadTasks.length; i += maxThreads) {
      final end = (i + maxThreads < downloadTasks.length)
          ? i + maxThreads
          : downloadTasks.length;
      batches.add(downloadTasks.sublist(i, end));
    }

    final downloadedTypes = <String>[];
    final existingTypes = <String>[...protectedEnabled];
    final replacedTypes = <String>[];
    var wasCancelled = false;
    var completedTasks = 0;

    for (final batch in batches) {
      if (shouldCancel != null && shouldCancel()) {
        wasCancelled = true;
        break;
      }

      final results = await Future.wait(
        batch.map((task) async {
          final outcome = await _downloadMediaFileSmart(
            task['url'] as String,
            task['relativePath'] as String,
            userDataDir,
            mediaType: task['mediaType'] as String,
            forceOverwrite: forceOverwrite,
            maxDailyRequests: maxDailyRequests,
            systemFolder: systemFolder,
            variants: task['variants'] as ScreenscraperMediaVariants?,
          );
          return {
            'mediaType': task['mediaType'],
            'success': outcome.success,
            'wasExisting': outcome.wasExisting,
            'replaced': outcome.replaced,
          };
        }),
      );

      for (final result in results) {
        if (result['success'] != true) continue;
        final mediaType = result['mediaType'] as String;
        if (result['wasExisting'] == true) {
          existingTypes.add(mediaType);
        } else {
          downloadedTypes.add(mediaType);
          if (result['replaced'] == true) replacedTypes.add(mediaType);
        }
      }

      completedTasks += batch.length;
      onProgress?.call(completedTasks / downloadTasks.length);
      if (batches.length > 1) {
        await Future.delayed(const Duration(milliseconds: 100));
      }
    }

    final totalAvailable = downloadedTypes.length + existingTypes.length;
    return {
      'success': totalAvailable == downloadTasks.length + protectedEnabled.length && !wasCancelled,
      'downloadedTypes': downloadedTypes,
      'existingTypes': existingTypes,
      'replacedTypes': replacedTypes,
      'protectedTypes': protectedEnabled,
      'cancelled': wasCancelled,
    };
  }
}

/// The ScreenScraper variants of one media setting, to tell a picture
/// ScreenScraper sent earlier (its MD5 is listed) from any other picture —
/// imported, chosen by hand or from another scraper — which is never
/// replaced by "New content only".
class ScreenscraperMediaVariants {
  ScreenscraperMediaVariants._(this.bestMd5, this.knownMd5, this.knownSizes);

  /// Null when ScreenScraper lists no MD5 for the best variant.
  static ScreenscraperMediaVariants? of(Map<String, dynamic> best, List<Map<String, dynamic>> all) {
    String? md5Of(Map<String, dynamic> m) {
      final v = m['md5']?.toString().trim().toLowerCase() ?? '';
      return v.isEmpty ? null : v;
    }

    final bestMd5 = md5Of(best);
    if (bestMd5 == null) return null;
    final known = <String>{};
    final sizes = <int>{};
    var everySized = true;
    for (final m in all) {
      final h = md5Of(m);
      if (h == null) continue;
      known.add(h);
      final size = int.tryParse(m['size']?.toString() ?? '');
      if (size != null && size > 0) {
        sizes.add(size);
      } else {
        everySized = false;
      }
    }
    return ScreenscraperMediaVariants._(bestMd5, known, everySized ? sizes : const {});
  }

  final String bestMd5;
  final Set<String> knownMd5;

  /// Sizes ScreenScraper lists, when it lists them for every variant: a file
  /// of another length was not sent by ScreenScraper and is not even hashed.
  final Set<int> knownSizes;

  /// Whether [path] holds a ScreenScraper variant other than the best one.
  Future<bool> isOtherVariant(String path) async {
    try {
      final file = File(path);
      if (knownSizes.isNotEmpty && !knownSizes.contains(await file.length())) return false;
      final digest = (await md5.bind(file.openRead()).first).toString();
      return digest != bestMd5 && knownMd5.contains(digest);
    } catch (_) {
      return false;
    }
  }
}
