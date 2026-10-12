/// Imports in progress, process-wide (docs/storage-audit-cleanup.md § 3.7,
/// review of phase 5d). Every import that follows a Files pick runs inside
/// [StorageImportActivity.run], from the pick to the end of its processing:
/// the picker's copies under `tmp/`, the `*.part` files and the staging
/// folders it writes meanwhile belong to it. While one runs, the cleanup
/// planner refuses the whole plan and the deletion manager stops, both with
/// `sessionActive` (« un jeu ou un import est en cours »).
///
/// A counter, not a flag: imports may overlap (two pages, a picker opened
/// while another import finishes). Nothing here touches the file system.
library;

import 'package:flutter/foundation.dart' show visibleForTesting;

abstract final class StorageImportActivity {
  static int _running = 0;

  /// Imports running now.
  static int get running => _running;

  /// At least one import runs.
  static bool get active => _running > 0;

  /// Runs [body] as one import, counted from its start to its end whatever
  /// it returns or throws (the count is released in a `finally`).
  static Future<T> run<T>(Future<T> Function() body) async {
    _running++;
    try {
      return await body();
    } finally {
      _running--;
    }
  }

  /// Forgets every import (a test whose import never ends).
  @visibleForTesting
  static void reset() => _running = 0;
}
