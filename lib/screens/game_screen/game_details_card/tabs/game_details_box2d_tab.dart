import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import '../../../../l10n/game_box_locale.dart';
import '../../../../models/system_model.dart';
import '../../../../models/game_model.dart';
import '../../../../providers/file_provider.dart';
import '../../../../services/game_box/game_box_media.dart';
import '../../../../themes/corner_radii.dart';
import '../../../../widgets/game_box/game_box_card.dart';
import '../../../../widgets/game_box/game_box_library.dart';

class GameDetailsBox2dTab extends StatefulWidget {
  final SystemModel system;
  final GameModel game;
  final FileProvider fileProvider;

  /// Bumped when a scrape rewrites the artwork. It keys the image so a
  /// re-scraped box art is resolved again instead of being redrawn from the
  /// copy this widget already holds.
  final int imageVersion;

  /// Opens the box viewer. With it, the box is drawn in 3D like in the
  /// carousel and the grid (docs/game-box-3d.md § 3); a tap opens the viewer.
  final VoidCallback? onInspectBox;

  const GameDetailsBox2dTab({
    super.key,
    required this.system,
    required this.game,
    required this.fileProvider,
    this.imageVersion = 0,
    this.onInspectBox,
  });

  @override
  State<GameDetailsBox2dTab> createState() => _GameDetailsBox2dTabState();
}

class _GameDetailsBox2dTabState extends State<GameDetailsBox2dTab> {
  double _imageAspectRatio = 3 / 4;

  ImageStream? _currentImageStream;
  ImageStreamListener? _currentImageListener;

  void _loadImageAspectRatio(String path) {
    if (path.isEmpty) return;

    final File file = File(path);
    if (!file.existsSync()) return;

    _removeImageListener();

    final Image image = Image.file(file);
    final ImageStream stream = image.image.resolve(const ImageConfiguration());

    final listener = ImageStreamListener((
      ImageInfo info,
      bool synchronousCall,
    ) {
      if (!mounted) return;
      final double aspectRatio = info.image.width / info.image.height;
      if (aspectRatio <= 0) return;

      void update() {
        setState(() {
          _imageAspectRatio = aspectRatio;
        });
      }

      if (synchronousCall) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) update();
        });
      } else {
        update();
      }
    });

    stream.addListener(listener);
    _currentImageStream = stream;
    _currentImageListener = listener;
  }

  void _removeImageListener() {
    if (_currentImageStream != null && _currentImageListener != null) {
      _currentImageStream!.removeListener(_currentImageListener!);
      _currentImageStream = null;
      _currentImageListener = null;
    }
  }

  @override
  void dispose() {
    _removeImageListener();
    super.dispose();
  }

  /// The game's 3D box, at rest; a tap (or the 360° badge) opens the viewer.
  Widget _box3d(String frontPath) {
    final systemId = widget.system.id ?? widget.game.systemId;
    GameBoxLibrary.ensureProfile(systemId, () {
      if (mounted) setState(() {});
    });
    final folder = widget.system.primaryFolderName;
    return Positioned(
      left: 18.r,
      right: 18.r,
      top: 46.r,
      bottom: 104.r,
      child: Semantics(
        button: true,
        label: GameBoxLocale.text(context, GameBoxLocale.inspect),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: widget.onInspectBox,
          child: Stack(children: [
            Positioned.fill(
              child: GameBoxCard(
                key: ValueKey('details_box3d_${widget.game.romname}_v${widget.imageVersion}'),
                frontPath: frontPath,
                title: widget.game.name,
                systemId: systemId,
                spinePath: GameBoxLibrary.mediaPath(
                  widget.game,
                  folder,
                  GameBoxMediaFolders.spine,
                  widget.fileProvider,
                  artworkVersion: widget.imageVersion,
                ),
                decodeWidth: 768,
              ),
            ),
            Positioned(
              right: 8.r,
              bottom: 8.r,
              child: Container(
                padding: EdgeInsets.all(5.r),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.5),
                  shape: BoxShape.circle,
                ),
                child: Icon(Symbols.threed_rotation_rounded, size: 15.r, color: Colors.white),
              ),
            ),
          ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final imageSystemFolder = widget.system.primaryFolderName;
    final box2dPath = widget.game.getImagePath(
      imageSystemFolder,
      'box2d',
      widget.fileProvider,
    );
    final box2dExists = File(box2dPath).existsSync();

    if (box2dExists && widget.onInspectBox != null) {
      return _box3d(box2dPath);
    }

    if (box2dExists) {
      _loadImageAspectRatio(box2dPath);
    }

    final borderRadius =
        Theme.of(context).extension<CornerRadii>()?.radiusInternal ??
        BorderRadius.circular(14.r);

    return Positioned(
      // Slightly enlarge the usable area while keeping comfortable clearance
      // from the tab bar above and the title/footer area below.
      left: 18.r,
      right: 18.r,
      top: 46.r,
      bottom: 104.r,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final double maxWidth = constraints.maxWidth * 0.84;
          final double maxHeight = constraints.maxHeight * 0.98;

          double imageWidth = maxWidth;
          double imageHeight = imageWidth / _imageAspectRatio;

          if (imageHeight > maxHeight) {
            imageHeight = maxHeight;
            imageWidth = imageHeight * _imageAspectRatio;
          }

          return Align(
            // Keep the larger cover slightly higher so it never crowds the
            // game title below.
            alignment: Alignment.topCenter,
            child: Padding(
              padding: EdgeInsets.only(top: 4.r),
              child: Container(
                width: imageWidth,
                height: imageHeight,
                decoration: BoxDecoration(
                  borderRadius: borderRadius,
                  boxShadow: [
                    BoxShadow(
                      color: Theme.of(
                        context,
                      ).colorScheme.shadow.withValues(alpha: 0.3),
                      blurRadius: 3.r,
                      offset: Offset(3.0.r, 3.0.r),
                    ),
                  ],
                  color: Colors.transparent,
                ),
                child: ClipRRect(
                  borderRadius: borderRadius,
                  clipBehavior: Clip.antiAlias,
                  child: box2dExists
                      ? Image.file(
                          File(box2dPath),
                          key: ValueKey(
                            'box2d_${widget.game.romPath ?? widget.game.romname}'
                            '_v${widget.imageVersion}',
                          ),
                          fit: BoxFit.contain,
                          cacheWidth: 768,
                        )
                      : Center(
                          child: Icon(
                            Icons.inventory_2_outlined,
                            size: 48.r,
                            color: Colors.white24,
                          ),
                        ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
