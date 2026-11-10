/// Progress of the selected files only; library discovery is a separate task.
class MelonxImportProgress {
  const MelonxImportProgress(
    this.phase, {
    this.name = '',
    this.fileIndex = 1,
    this.fileCount = 1,
    this.done = 0,
    this.total = 0,
  });
  final String phase, name;
  final int fileIndex, fileCount, done, total;
}

typedef MelonxImportObserver = void Function(MelonxImportProgress progress);

class MelonxAddonReport {
  const MelonxAddonReport(
    this.imported,
    this.refused, {
    this.targets = const {},
  });
  final List<String> imported;
  final Map<String, String> refused;
  final Map<String, String> targets;
  bool get isEmpty => imported.isEmpty && refused.isEmpty;
}
