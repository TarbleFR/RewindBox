/// Classification of a path of the container (docs/storage-audit-cleanup.md
/// § 3.4): category and deletion class, decided in this order —
///
/// 1. the never-lists: links, iCloud placeholders and unreadable entries,
///    the containers and root directories themselves, `Documents/roms`,
///    every library folder, the linked folder, the hidden library folder,
///    `Caches/NeoSwap*`, `dev_flash`, `exdata`, `savedata`, `games`,
///    `dev_hdd0/game`, `Libretro/System`, `ARMSX2/BIOS`, `StikJIT`,
///    `*.sqlite*` (except the § 3.6 backups), `config.json`,
///    `local-index.json*`, `reading-state.json`, `reading-state-extra.json`,
///    `catalogs.json`, `source-health.json`, `games.yml`, `vfs.yml`,
///    `SkinFavorites.json`, `CrashMarkers/active-session.json`, the
///    NSURLCache database `Cache.db`, `Cache.db-wal`, `Cache.db-shm` (review
///    of the storage services); then every RPCS3 root when `Data/vfs.yml`
///    redirects `dev_hdd0`; then any path no rule identifies (category
///    [StorageCategory.unknown]);
/// 2. the deepest rule of the registry;
/// 3. the name override `*.part` → temporary when idle (one hour minimum),
///    except under rules of saves, system files, NeoSwap, index, games and
///    user content (those keep their rule's class: a partial file there —
///    a download, a copy the user started — is never assumed to be ours;
///    games and user content since the review of the storage services). The
///    partial files NeoStation itself writes in such folders have their own
///    rules (`INV-10.exportPart`, `INV-12.gamePart`, `INV-15.importPart`).
library;

import 'package:path/path.dart' as p;

import 'storage_roots.dart';

export 'storage_roots.dart' show StorageEntryKind;

/// Why a path is classified [StorageDeletionClass.never].
enum StorageProtectedReason {
  /// One of the four containers.
  container,

  /// A scanned directory of a root.
  root,

  /// A never-list entry (subtree, name or exact file).
  neverList,

  /// The deepest rule of the path is never.
  rule,

  /// No rule identifies the path.
  unknown,

  /// A symbolic link (counted 0 bytes, never followed).
  link,

  /// `.<name>.icloud`.
  icloudPlaceholder,

  /// The entry could not be read.
  inaccessible,

  /// `Data/vfs.yml` redirects `dev_hdd0`: every RPCS3 root is excluded.
  rpcs3Redirected,
}

/// Result of [StorageCategorizer.classify].
class StorageClassification {
  const StorageClassification({
    required this.category,
    required this.deletionClass,
    this.ruleId,
    this.protectedReason,
    this.rule,
    this.rootId,
    this.engine,
    this.minimumAge,
    this.aggregateOnly = false,
  });

  final StorageCategory category;
  final StorageDeletionClass deletionClass;

  /// Id of the rule that decided ([StorageRule.id], `NAME.part`,
  /// `NEVER.link`, …); null for an unknown path.
  final String? ruleId;

  /// Set exactly when [deletionClass] is never.
  final StorageProtectedReason? protectedReason;

  /// The registry rule behind the decision (never-list entry or deepest
  /// rule), if any.
  final StorageRule? rule;

  /// Root owning the path (deepest scanned directory containing it).
  final String? rootId;
  final StorageEngine? engine;

  /// Age below which the planner never proposes the path.
  final Duration? minimumAge;

  /// Measured, never detailed (hidden library folder).
  final bool aggregateOnly;

  bool get isProtected => deletionClass == StorageDeletionClass.never;

  @override
  String toString() =>
      'StorageClassification(${category.name}, ${deletionClass.name}, '
      '$ruleId${protectedReason == null ? '' : ', ${protectedReason!.name}'})';
}

class StorageCategorizer {
  const StorageCategorizer(this.registry);

  final StorageRootRegistry registry;

  /// Rule id of the name override of step 3.
  static const String partOverrideRuleId = 'NAME.part';

  /// Age below which an overridden `*.part` is never proposed.
  static const Duration partMinimumAge = Duration(hours: 1);

  /// Categories whose `*.part` files keep the class of their rule. Games
  /// and user content were added by the review of the storage services: a
  /// `.part` in `ARMSX2/Games`, `Dolphin/Library`, `Library/Downloads`, the
  /// skins, cheats, themes or mods is the user's.
  static const Set<StorageCategory> partOverrideExcluded = {
    StorageCategory.saves,
    StorageCategory.systemFiles,
    StorageCategory.neoSwap,
    StorageCategory.indexFiles,
    StorageCategory.games,
    StorageCategory.userContent,
  };

  StorageClassification classify(String absolutePath, StorageEntryKind kind) {
    final canonical = storageCanonicalPath(absolutePath);
    return classifyMatch(
      registry.matchPath(canonical),
      p.basename(canonical),
      kind,
    );
  }

  /// [classify] of the child [name] of the directory described by
  /// [parent] (the scanner's constant-time path; same decision).
  StorageClassification classifyChild(
    StorageMatchContext parent,
    String name,
    StorageEntryKind kind,
  ) => classifyMatch(registry.matchChild(parent, name), name, kind);

  /// Decision for an entry named [name] whose registry knowledge is
  /// [match].
  StorageClassification classifyMatch(
    StorageRuleMatch match,
    String name,
    StorageEntryKind kind,
  ) {
    final rule = match.rule;
    final never = match.never;
    final ruleCategory = rule?.category ?? StorageCategory.unknown;
    StorageEngine? engineOf(StorageRule? decisive) =>
        decisive?.engine ??
        rule?.engine ??
        (match.rootId == null
            ? null
            : registry.rootById(match.rootId!)?.engine);

    StorageClassification protect(
      StorageProtectedReason reason, {
      StorageRule? decisive,
      String? ruleId,
      StorageCategory? category,
    }) {
      return StorageClassification(
        category:
            category ??
            (decisive == null || decisive.category == StorageCategory.unknown
                ? ruleCategory
                : decisive.category),
        deletionClass: StorageDeletionClass.never,
        ruleId: ruleId ?? decisive?.id,
        protectedReason: reason,
        rule: decisive ?? rule,
        rootId: match.rootId,
        engine: engineOf(decisive),
        aggregateOnly: match.aggregate,
      );
    }

    // 1. Never-lists.
    final exact = match.exact;
    if (exact != null) {
      return protect(switch (exact) {
        StorageExactMatch.container => StorageProtectedReason.container,
        StorageExactMatch.root => StorageProtectedReason.root,
        StorageExactMatch.marker => StorageProtectedReason.neverList,
      }, decisive: never);
    }
    switch (kind) {
      case StorageEntryKind.link:
        return protect(StorageProtectedReason.link, ruleId: 'NEVER.link');
      case StorageEntryKind.icloudPlaceholder:
        return protect(
          StorageProtectedReason.icloudPlaceholder,
          ruleId: 'NEVER.icloud',
        );
      case StorageEntryKind.inaccessible:
        return protect(
          StorageProtectedReason.inaccessible,
          ruleId: 'NEVER.inaccessible',
        );
      case StorageEntryKind.file:
      case StorageEntryKind.directory:
        break;
    }
    if (never != null) {
      return protect(
        never.id == 'NEVER.icloud'
            ? StorageProtectedReason.icloudPlaceholder
            : StorageProtectedReason.neverList,
        decisive: never,
      );
    }
    if (registry.rpcs3Redirected && match.rpcs3) {
      return protect(StorageProtectedReason.rpcs3Redirected, decisive: rule);
    }
    if (rule == null) {
      return protect(
        StorageProtectedReason.unknown,
        category: StorageCategory.unknown,
      );
    }

    // 3. Name override, before falling back on the rule's own class.
    if (name.endsWith('.part') &&
        rule.deletionClass != StorageDeletionClass.temporaryWhenIdle &&
        !partOverrideExcluded.contains(rule.category)) {
      return StorageClassification(
        category: StorageCategory.temporary,
        deletionClass: StorageDeletionClass.temporaryWhenIdle,
        ruleId: partOverrideRuleId,
        rule: rule,
        rootId: match.rootId,
        engine: engineOf(rule),
        minimumAge: partMinimumAge,
        aggregateOnly: match.aggregate,
      );
    }

    // 2. Deepest rule.
    final protected = rule.deletionClass == StorageDeletionClass.never;
    return StorageClassification(
      category: rule.category,
      deletionClass: rule.deletionClass,
      ruleId: rule.id,
      protectedReason: protected ? StorageProtectedReason.rule : null,
      rule: rule,
      rootId: match.rootId,
      engine: engineOf(rule),
      minimumAge: rule.minimumAge,
      aggregateOnly: match.aggregate,
    );
  }
}
