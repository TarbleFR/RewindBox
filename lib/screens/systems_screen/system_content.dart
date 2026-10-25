import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:provider/provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/services/home_music_service.dart';
import 'package:neostation/widgets/rewind_startup.dart';
import 'my_systems_section/my_systems_grid.dart';
import 'my_systems_section/initial_setup_widget.dart';

/// Orchestrator for the 'Systems' tab content.
///
/// The optional user-selected custom background is deliberately rendered only
/// behind the primary systems grid/carousel. Game playlists are pushed as new
/// routes and therefore keep their existing backgrounds unchanged.
class SystemContent extends StatefulWidget {
  const SystemContent({super.key, this.selectedIndex = 0, this.onCardTapped});

  final int selectedIndex;
  final Function(int index)? onCardTapped;

  @override
  State<SystemContent> createState() => _SystemContentState();
}

class _SystemContentState extends State<SystemContent> {
  bool? _lastHomeMusicActive;

  @override
  void dispose() {
    unawaited(HomeMusicService().setMainMenuActive(false));
    super.dispose();
  }

  /// Keeps audio side effects outside build while still following route
  /// visibility. A pushed game library leaves this widget mounted underneath,
  /// so checking [ModalRoute.isCurrent] is what prevents ambience from leaking
  /// beyond the main console-selection screen.
  void _syncHomeMusic(bool active) {
    if (_lastHomeMusicActive == active) return;
    _lastHomeMusicActive = active;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted && active) return;
      unawaited(HomeMusicService().setMainMenuActive(active));
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SqliteConfigProvider>(
      builder: (context, configProvider, child) {
        final isLoading = configProvider.isLoading || configProvider.isScanning;
        final showSplash = isLoading;

        final showInitialSetup =
            !showSplash &&
            !configProvider.hasDetectedSystems &&
            configProvider.scanCompleted;

        final showContent =
            !showSplash && configProvider.scanCompleted && !showInitialSetup;

        final routeIsCurrent = ModalRoute.of(context)?.isCurrent ?? true;
        _syncHomeMusic(showContent && routeIsCurrent);
        final safePadding = MediaQuery.viewPaddingOf(context);
        final isIOS = defaultTargetPlatform == TargetPlatform.iOS;
        final safeLeft = isIOS ? safePadding.left : 0.0;
        final safeRight = isIOS ? safePadding.right : 0.0;

        final Widget phase;
        if (showSplash) {
          phase = KeyedSubtree(
            key: const ValueKey('splash'),
            child: _buildSplash(context, configProvider),
          );
        } else if (showInitialSetup) {
          phase = const KeyedSubtree(
            key: ValueKey('setup'),
            child: InitialSetupWidget(),
          );
        } else if (showContent) {
          phase = KeyedSubtree(
            key: const ValueKey('content'),
            child: MySystems(
              selectedIndex: widget.selectedIndex,
              onCardTapped: widget.onCardTapped,
            ),
          );
        } else if (configProvider.error != null) {
          phase = Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text(configProvider.error!, textAlign: TextAlign.center),
            ),
          );
        } else {
          phase = const SizedBox.shrink(key: ValueKey('empty'));
        }

        final content = AnimatedSwitcher(
          duration: RewindStartupReady.pending(context)
              ? Duration.zero
              : const Duration(milliseconds: 400),
          child:
              !showSplash &&
                  (showInitialSetup ||
                      showContent ||
                      configProvider.error != null)
              ? RewindStartupReady(key: phase.key, child: phase)
              : phase,
        );

        // AppScreen owns the custom background so it stays mounted across
        // top-level tab changes. During splash/setup phases, cover that
        // persistent layer with the normal theme background. The actual
        // Systems content remains transparent so the custom image shows through.
        if (showContent) {
          return Padding(
            padding: EdgeInsets.only(left: safeLeft, right: safeRight),
            child: content,
          );
        }
        return ColoredBox(
          color: Theme.of(context).scaffoldBackgroundColor,
          child: content,
        );
      },
    );
  }

  Widget _buildSplash(
    BuildContext context,
    SqliteConfigProvider configProvider,
  ) {
    return Stack(
      children: [
        if (!configProvider.isScanning)
          const Center(
            child: SizedBox.square(
              dimension: 20,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
        if (configProvider.isScanning)
          Align(
            alignment: const Alignment(0, 0.55),
            child: Container(
              constraints: const BoxConstraints(maxWidth: 480),
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 220,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(2),
                      child: LinearProgressIndicator(
                        value: configProvider.scanProgress,
                        minHeight: 3,
                        backgroundColor: Theme.of(
                          context,
                        ).colorScheme.onSurface.withValues(alpha: 0.12),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    configProvider.scanStatus.isNotEmpty
                        ? configProvider.scanStatus
                        : AppLocale.scanningSystemsRoms.getString(context),
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      fontSize: 17,
                      color: Theme.of(
                        context,
                      ).colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                    textAlign: TextAlign.center,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}
