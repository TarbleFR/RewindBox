import 'package:flutter/widgets.dart';

/// Whether the system asks for reduced motion (Build 447,
/// docs/library-books-3d-plan.md § 3.12).
///
/// True when `MediaQuery.disableAnimations` is set (Android's "Remove
/// animations", tests), or when iOS's "Reduce Motion" is on: the engine
/// reports that setting only as
/// `PlatformDispatcher.accessibilityFeatures.reduceMotion`, it never sets
/// `disableAnimations` on iOS, and `MediaQueryData` has no field for it.
///
/// A change of the iOS flag alone therefore notifies no MediaQuery
/// dependent: a widget that must follow it while shown observes
/// `WidgetsBindingObserver.didChangeAccessibilityFeatures` and reads this
/// again (the readers), or reads it each time an animation would start
/// (the book covers of a grid, which need no observer each).
bool libraryReduceMotion(BuildContext context) {
  if (MediaQuery.maybeDisableAnimationsOf(context) ?? false) return true;
  final dispatcher =
      View.maybeOf(context)?.platformDispatcher ??
      WidgetsBinding.instance.platformDispatcher;
  return dispatcher.accessibilityFeatures.reduceMotion;
}
