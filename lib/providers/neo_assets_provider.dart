import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:path/path.dart' as path;
import 'dart:async';

import '../services/neo_assets_service.dart';
import '../services/system_art/bundled_system_art.dart';
import '../services/system_art/system_art_alias_table.dart';
import '../repositories/config_repository.dart';
import '../services/logger_service.dart';
import '../services/global_notification_service.dart';
import '../l10n/system_art_update_locale.dart';

final _log = LoggerService.instance;

/// Provider responsible for managing remote and local theme assets (logos, backgrounds).
///
/// Handles theme discovery, batch downloading of assets, and persistence of the
/// active theme selection. Uses [NeoAssetsService] for network and cache I/O.
class NeoAssetsProvider extends ChangeNotifier {
  static const List<String> _videoBackgroundExtensions = ['mp4', 'm4v', 'mov'];

  /// List of available themes fetched from the remote repository.
  List<NeoAssetsTheme> _themes = [];

  /// Folder name of the currently selected theme.
  String _activeThemeFolder = '';

  /// Whether a network request to fetch themes is in progress.
  bool _loading = false;

  /// Whether a background download of theme assets is active.
  bool _downloading = false;

  /// Normalized download progress (0.0 to 1.0).
  double _downloadProgress = 0.0;

  /// Installed packs whose catalogue version differs from the local one.
  Set<String> _updatableFolders = {};

  /// Id of the bell notification announcing System Art updates.
  static const String updateNotificationId = 'system-art-updates';

  /// Internal flag to ensure initialization logic runs only once.
  bool _initialized = false;

  /// Transparent margin of each downloaded pack's own tiles, as a fraction of the tile side ([fallbackInset]).
  final Map<String, double> _fallbackInsets = {};
  final Map<String, Future<void>> _insetMeasures = {};
  bool _disposed = false;

  List<NeoAssetsTheme> get themes => _themes;
  String get activeThemeFolder => _activeThemeFolder;
  bool get loading => _loading;
  bool get downloading => _downloading;
  double get downloadProgress => _downloadProgress;
  bool get hasActiveTheme => _activeThemeFolder.isNotEmpty;
  Set<String> get updatableFolders => Set.unmodifiable(_updatableFolders);

  /// Whether the installed pack in [folder] can be updated.
  bool hasUpdate(String folder) => _updatableFolders.contains(folder);

  /// Initializes the theme cache directory and loads the active theme from the database.
  ///
  /// The System Art pack embedded in the app (RewindBox Glacier) is
  /// installed or confirmed here, without network. When it is the active
  /// pack, the selection is published only once its files are in place, so
  /// no card resolves its art against a missing folder; otherwise it is
  /// installed in the background, ready for the picker and offline use.
  Future<void> init() async {
    if (_initialized) return;
    _initialized = true;
    await NeoAssetsService.ensureCacheDirInitialized();
    final saved = await ConfigRepository.getActiveTheme();
    if (BundledSystemArt.isBundled(saved)) {
      await _ensureBundledPack();
    } else {
      unawaited(_ensureBundledPack());
    }
    _activeThemeFolder = saved;
    notifyListeners();
    await loadThemes();
  }

  Future<bool> _ensureBundledPack() async {
    final installed = await BundledSystemArt.ensureInstalled();
    // Forget a table read before (or during) the installation.
    SystemArtAliasTable.invalidate();
    return installed;
  }

  /// Test hook: selects [folder] as the active pack without the database.
  @visibleForTesting
  void debugSetActiveTheme(String folder) {
    _activeThemeFolder = folder;
    notifyListeners();
  }

  /// Fetches the list of available themes from the remote server.
  Future<void> loadThemes() async {
    _loading = true;
    notifyListeners();
    try {
      _themes = await NeoAssetsService.fetchThemes();
      _updatableFolders = await NeoAssetsService.foldersWithUpdates(_themes);
      publishUpdateNotification();
    } catch (e) {
      _log.e('Error loading themes: $e');
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  /// Shows (or withdraws) the bell notification listing updatable packs.
  @visibleForTesting
  void publishUpdateNotification() {
    final notifications = GlobalNotificationService();
    final names = [
      for (final t in _themes)
        if (_updatableFolders.contains(t.folder)) t.name,
    ];
    if (names.isEmpty) {
      notifications.dismiss(updateNotificationId);
      return;
    }
    notifications.show(
      id: updateNotificationId,
      title: SystemArtUpdateLocale.title(),
      message: SystemArtUpdateLocale.message(names),
      icon: Icons.system_update_alt,
      type: GlobalNotificationType.info,
    );
  }

  /// Test hook: sets the catalogue and the updatable packs without network.
  @visibleForTesting
  void debugSetThemes(List<NeoAssetsTheme> themes, Set<String> updatable) {
    _themes = themes;
    _updatableFolders = {...updatable};
    publishUpdateNotification();
    notifyListeners();
  }

  /// Deselects the current theme and resets the active selection.
  Future<void> clearTheme() async {
    _activeThemeFolder = '';
    await ConfigRepository.updateActiveTheme('');
    notifyListeners();
  }

  /// Downloads all required assets for the specified theme and applies it.
  ///
  /// Existing WebP/GIF packs keep the normal bulk path. Video backgrounds stay
  /// supported as an on-demand fallback through [getBackgroundForSystem], but
  /// are deliberately not probed here after the bulk download reaches 100%.
  /// Eagerly probing mp4/m4v/mov for every system made the first-run art-pack
  /// screen appear frozen at 100% while sequential 404/network requests were
  /// still running in the background.
  Future<void> downloadAndApplyTheme(
    String themeFolder,
    List<String> systemFolderNames,
  ) async {
    // The embedded pack never touches the network: it is installed from the
    // application, and the previous selection stays if that fails.
    if (BundledSystemArt.isBundled(themeFolder)) {
      await applyBundledTheme();
      return;
    }
    try {
      final plan = await NeoAssetsService.buildThemeDownloadPlan(
        themeFolder,
        systemFolderNames,
      );

      if (plan.totalAssetsToDownload > 0) {
        _downloading = true;
        _downloadProgress = 0.0;
        notifyListeners();

        if (plan.forceRedownload) {
          await NeoAssetsService.downloadAllThemeAssets(
            themeFolder,
            plan.systemsToDownload,
            forceRedownload: true,
            onProgress: (done, t) {
              _downloadProgress = t == 0 ? 1.0 : done / t;
              notifyListeners();
            },
          );
        } else {
          await NeoAssetsService.downloadMissingThemeAssets(
            themeFolder,
            plan.systemsToDownload,
            missingTotal: plan.totalAssetsToDownload,
            onProgress: (done, t) {
              _downloadProgress = t == 0 ? 1.0 : done / t;
              notifyListeners();
            },
          );
        }
      }

      // A pack is not installed merely because all HTTP attempts completed.
      // Never replace the active selection with an empty or unavailable pack.
      if (NeoAssetsService.isNeoAssetsPack(themeFolder) &&
          !await NeoAssetsService.hasCachedThemeArt(
            themeFolder,
            plan.systemsToDownload,
          )) {
        throw StateError('No NeoAssets artwork was downloaded');
      }

      if (plan.remoteMetadata != null) {
        await NeoAssetsService.writeLocalThemeMetadata(
          themeFolder,
          plan.remoteMetadata!,
        );
      }

      _activeThemeFolder = themeFolder;
      // Its tiles may have changed with the download: measure their margin again.
      _fallbackInsets.remove(themeFolder);
      await ConfigRepository.updateActiveTheme(themeFolder);
      if (_updatableFolders.remove(themeFolder)) publishUpdateNotification();

      // /download is the official counting endpoint. A catalog/preview
      // request must never increment statistics or redownload an old pack.
      if (NeoAssetsService.isNeoAssetsPack(themeFolder) &&
          plan.localVersion == null &&
          plan.totalAssetsToDownload > 0) {
        await NeoAssetsService.registerSuccessfulNeoAssetsInstall(themeFolder);
      }
    } catch (e) {
      _log.e('Error downloading theme: $e');
    } finally {
      _downloading = false;
      _downloadProgress = 0.0;
      notifyListeners();
    }
  }

  /// Installs (or confirms) RewindBox Glacier from the application and
  /// makes it the active System Art. Returns false, keeping the current
  /// selection, when the embedded pack could not be installed.
  Future<bool> applyBundledTheme() async {
    _downloading = true;
    _downloadProgress = 0.0;
    notifyListeners();
    try {
      if (!await _ensureBundledPack()) return false;
      _activeThemeFolder = BundledSystemArt.folder;
      await ConfigRepository.updateActiveTheme(BundledSystemArt.folder);
      return true;
    } catch (e) {
      _log.e('Error applying the embedded System Art: $e');
      return _activeThemeFolder == BundledSystemArt.folder;
    } finally {
      _downloading = false;
      _downloadProgress = 0.0;
      notifyListeners();
    }
  }

  String? _resolveCachedVideoBackgroundSync(
    String themeFolder,
    String systemFolderName,
  ) {
    for (final ext in _videoBackgroundExtensions) {
      final localPath = NeoAssetsService.backgroundCachePathSync(
        themeFolder,
        systemFolderName,
        ext: ext,
      );
      if (localPath != null && File(localPath).existsSync()) return localPath;
    }
    return null;
  }

  /// Synchronous variant for resolving background paths.
  /// Preserves WebP/GIF precedence, then falls back to cached video media.
  ///
  /// A downloaded pack rarely covers every system (no Switch 2 art in most
  /// of them). Rather than an empty card, a system the active pack lacks
  /// shows its default image: the one of RewindBox Glacier, the pack
  /// embedded in the app and installed at launch. "None" keeps no art.
  String? getBackgroundForSystemSync(String systemFolderName) {
    if (!hasActiveTheme) return null;
    final image = NeoAssetsService.resolveBackgroundPathSync(
      _activeThemeFolder,
      systemFolderName,
    );
    if (image != null && File(image).existsSync()) return image;

    final video = _resolveCachedVideoBackgroundSync(
      _activeThemeFolder,
      systemFolderName,
    );
    if (video != null) return video;

    return defaultBackgroundForSystemSync(systemFolderName) ?? image;
  }

  /// The embedded pack's image for [systemFolderName] (its aliases
  /// included), or null when it has none or is not installed yet.
  String? defaultBackgroundForSystemSync(String systemFolderName) {
    if (BundledSystemArt.isBundled(_activeThemeFolder)) return null;
    final fallback = NeoAssetsService.resolveBackgroundPathSync(
      BundledSystemArt.folder,
      systemFolderName,
    );
    if (fallback == null || !File(fallback).existsSync()) return null;
    return fallback;
  }

  /// How far the embedded fallback image ([defaultBackgroundForSystemSync]) is
  /// inset under the active pack, as a fraction of the tile side, so that it
  /// is the size of the pack's own tiles. Some downloaded packs draw their
  /// capsules inside a transparent margin, with their own rounded card and
  /// shadow. The full-bleed fallback then read about 7 % larger than its
  /// neighbours (IPA 727, the Switch 2 tile under such a pack).
  ///
  /// It is 0 for the embedded pack, for "None", while the measure is pending,
  /// after any read or decode error, and for opaque packs (Glacier, Canvas,
  /// RiiSU). A pack's own tiles are never inset.
  double get fallbackInset {
    final folder = _activeThemeFolder;
    if (folder.isEmpty || BundledSystemArt.isBundled(folder)) return 0;
    return _fallbackInsets[folder] ?? 0;
  }

  /// Measures [fallbackInset] for the active pack, once per pack folder.
  ///
  /// The work starts after the current frame: a zero-length timer, then
  /// asynchronous reads and decodes. Listeners are told only when the margin
  /// is above 0. A pack that is not installed is not measured yet.
  Future<void> ensureFallbackInsetMeasured() {
    final folder = _activeThemeFolder;
    if (folder.isEmpty || BundledSystemArt.isBundled(folder)) {
      return Future<void>.value();
    }
    final pending = _insetMeasures[folder];
    if (pending != null) return pending;
    if (_fallbackInsets.containsKey(folder)) return Future<void>.value();
    final probe = NeoAssetsService.backgroundCachePathSync(folder, '_');
    if (probe == null) return Future<void>.value();
    final backgrounds = Directory(path.dirname(probe));
    if (!backgrounds.existsSync()) return Future<void>.value();
    return _insetMeasures[folder] = Future<void>(() async {
      var inset = 0.0;
      try {
        inset = await measureTileInset(await _sampleTiles(backgrounds));
      } catch (error) {
        _log.w('System Art tile margin not measured for $folder: $error');
      }
      _insetMeasures.remove(folder);
      _fallbackInsets[folder] = inset;
      if (!_disposed && inset > 0 && folder == _activeThemeFolder) {
        notifyListeners();
      }
    });
  }

  /// Test hook: the measured margin of [folder]'s tiles, without decoding.
  @visibleForTesting
  void debugSetFallbackInset(String folder, double inset) {
    _fallbackInsets[folder] = inset;
    notifyListeners();
  }

  /// Up to [count] of a pack's still tiles (WebP, PNG, JPEG), by file name.
  static Future<List<File>> _sampleTiles(
    Directory backgrounds, {
    int count = 4,
  }) async {
    final tiles = <File>[];
    await for (final entry in backgrounds.list(followLinks: false)) {
      if (entry is! File) continue;
      final extension = path.extension(entry.path).toLowerCase();
      if (const ['.webp', '.png', '.jpg', '.jpeg'].contains(extension)) {
        tiles.add(entry);
      }
    }
    tiles.sort((a, b) => a.path.compareTo(b.path));
    return tiles.take(count).toList();
  }

  /// The transparent margin of a pack's tiles. Each tile is decoded 96 px
  /// wide and measured by [tileInsetFromRgba], and the median is kept. Any
  /// read or decode error gives 0, and so does an empty list. Visible for
  /// tests.
  @visibleForTesting
  static Future<double> measureTileInset(List<File> tiles) async {
    if (tiles.isEmpty) return 0;
    final insets = <double>[];
    try {
      for (final tile in tiles) {
        final codec = await ui.instantiateImageCodec(
          await tile.readAsBytes(),
          targetWidth: 96,
        );
        try {
          final image = (await codec.getNextFrame()).image;
          try {
            final data = await image.toByteData(
              format: ui.ImageByteFormat.rawRgba,
            );
            if (data == null) return 0;
            insets.add(
              tileInsetFromRgba(
                data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
                image.width,
                image.height,
              ),
            );
          } finally {
            image.dispose();
          }
        } finally {
          codec.dispose();
        }
      }
    } catch (error) {
      _log.w('System Art tile not decoded: $error');
      return 0;
    }
    return medianInset(insets);
  }

  /// The smallest distance from an edge of an RGBA tile to its first pixel
  /// with alpha above 128, over the tile side. An opaque tile gives 0, and so
  /// does a fully transparent one (it is not a tile). Visible for tests.
  @visibleForTesting
  static double tileInsetFromRgba(Uint8List rgba, int width, int height) {
    if (width <= 0 || height <= 0 || rgba.length < width * height * 4) {
      return 0;
    }
    var top = -1, bottom = -1, left = width, right = -1;
    for (var y = 0; y < height; y++) {
      final row = y * width * 4;
      var opaque = false;
      for (var x = 0; x < width; x++) {
        if (rgba[row + x * 4 + 3] > 128) {
          opaque = true;
          if (x < left) left = x;
          if (x > right) right = x;
        }
      }
      if (opaque) {
        if (top < 0) top = y;
        bottom = y;
      }
    }
    if (top < 0) return 0;
    return [
      left / width,
      top / height,
      (width - 1 - right) / width,
      (height - 1 - bottom) / height,
    ].reduce(math.min);
  }

  /// The median of [insets], clamped to 0–12 %; 0 for none. Visible for tests.
  @visibleForTesting
  static double medianInset(List<double> insets) {
    if (insets.isEmpty) return 0;
    final sorted = [...insets]..sort();
    final middle = sorted.length ~/ 2;
    final median = sorted.length.isOdd
        ? sorted[middle]
        : (sorted[middle - 1] + sorted[middle]) / 2;
    return median.clamp(0.0, 0.12);
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
