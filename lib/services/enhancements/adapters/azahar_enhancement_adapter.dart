import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as path;

import '../../../models/game_model.dart';
import '../../libretro_internal_service.dart';
import '../enhancement_adapter.dart';
import '../enhancement_models.dart';
import '../enhancement_store.dart';

/// 3DS cheats for the embedded Azahar core.
///
/// Azahar's libretro cheat callbacks do nothing (`retro_cheat_set` is empty
/// in 2127.0-rc5): the core reads `<user>/cheats/<Title ID>.txt` itself when a
/// game loads (`System::Load` → `CheatEngine::LoadCheatFile`) and runs every
/// section marked `*citra_enabled`. RewindBox writes that file with only the
/// codes the player turned on, removes it when none is left, and never writes
/// over a file of the player's.
///
/// The identity is the Title ID of the game file (partition 0 of an NCSD, an
/// NCCH, or content 0 of a CIA): an exact match, never a title guess. 3DS codes
/// are made for one game version. A code whose name states an update
/// (`v1.5`), or that was published for the update, is incompatible while no
/// update of the game is installed in Azahar: RewindBox does not install 3DS
/// updates, and the code's addresses belong to the updated program.
class AzaharEnhancementAdapter extends EnhancementAdapter {
  AzaharEnhancementAdapter({Future<Directory> Function()? userDirectory})
    : _userDirectory = userDirectory ?? _defaultUserDirectory;

  final Future<Directory> Function() _userDirectory;

  /// Whether an update of each identified title is installed, from the last
  /// [identify].
  final _updates = <String, bool>{};

  static Future<Directory> _defaultUserDirectory() async =>
      Directory(path.join((await LibretroInternalService.savesDirectory()).path, 'Azahar', 'Azahar'));

  static const _mediaUnit = 0x200;
  static final _line = RegExp(r'^[0-9A-F]{8} [0-9A-F]{8}$');
  static final _titleId = RegExp(r'^0004000[02][0-9A-F]{8}$');

  /// Versions of a game's own release; any other version a code names is an
  /// update's.
  static const baseVersions = {'1.0', '1.00', '1.0.0'};

  @override
  EnhancementEngine get engine => EnhancementEngine.azahar;

  @override
  bool handles(String systemFolder) {
    final folder = systemFolder.toLowerCase();
    return folder == '3ds' || folder == 'n3ds';
  }

  /// The Title ID of the 3DS game at [file] (16 upper-case hex digits, an
  /// update's or add-on's mapped to its application), or the problem that
  /// prevents reading it. Compressed images (`.zcci`, `.zcxi`, `.z3dsx`) and
  /// homebrew (`.3dsx`, `.elf`, `.axf`) have none the catalogue can use.
  static Future<({String? titleId, EnhancementProblem problem})> readTitleId(String file) async {
    final extension = path.extension(file).toLowerCase();
    if (const {'.zcci', '.zcxi', '.z3dsx'}.contains(extension)) {
      return (titleId: null, problem: EnhancementProblem.imageFormat);
    }
    if (const {'.3dsx', '.elf', '.axf'}.contains(extension)) {
      return (titleId: null, problem: EnhancementProblem.identityUnavailable);
    }
    RandomAccessFile? handle;
    try {
      final opened = handle = await File(file).open();
      final length = await opened.length();
      Future<Uint8List> read(int offset, int count) async {
        if (offset < 0 || offset + count > length) return Uint8List(0);
        await opened.setPosition(offset);
        return opened.read(count);
      }

      final header = await read(0, _mediaUnit);
      String? id;
      if (_magic(header, 0x100, 'NCSD')) {
        // Partition 0 holds the game; its NCCH names the program.
        final partition = ByteData.sublistView(header).getUint32(0x120, Endian.little) * _mediaUnit;
        id = programId(await read(partition, _mediaUnit)) ?? _hex(header, 0x108, Endian.little);
      } else if (_magic(header, 0x100, 'NCCH')) {
        id = programId(header);
      } else if (extension == '.cia' || _ciaHeader(header)) {
        id = await _ciaTitleId(header, read);
      }
      final title = applicationTitleId(id);
      return title == null
          ? (titleId: null, problem: EnhancementProblem.identityUnavailable)
          : (titleId: title, problem: EnhancementProblem.none);
    } on Object {
      return (titleId: null, problem: EnhancementProblem.identityUnavailable);
    } finally {
      await handle?.close();
    }
  }

  /// The program ID of an NCCH header (`NCCH` at 0x100, ID at 0x118), or null.
  static String? programId(Uint8List ncch) =>
      ncch.length >= 0x120 && _magic(ncch, 0x100, 'NCCH') ? _hex(ncch, 0x118, Endian.little) : null;

  /// The application a Title ID runs under: an update (0004000E) or an
  /// add-on (0004008C) maps to its application (00040000); applications and
  /// demos (00040002) are kept; anything else (system titles) is null.
  static String? applicationTitleId(String? raw) {
    final id = raw?.toUpperCase() ?? '';
    if (!RegExp(r'^[0-9A-F]{16}$').hasMatch(id)) return null;
    final category = id.substring(0, 8);
    if (category == '0004000E' || category == '0004008C') return '00040000${id.substring(8)}';
    return _titleId.hasMatch(id) ? id : null;
  }

  static bool _magic(Uint8List bytes, int offset, String magic) {
    if (bytes.length < offset + magic.length) return false;
    for (var index = 0; index < magic.length; index++) {
      if (bytes[offset + index] != magic.codeUnitAt(index)) return false;
    }
    return true;
  }

  static String? _hex(Uint8List bytes, int offset, Endian endian) {
    if (bytes.length < offset + 8) return null;
    final view = ByteData.sublistView(bytes);
    final high = view.getUint32(endian == Endian.little ? offset + 4 : offset, endian);
    final low = view.getUint32(endian == Endian.little ? offset : offset + 4, endian);
    return '${high.toRadixString(16).padLeft(8, '0')}${low.toRadixString(16).padLeft(8, '0')}'.toUpperCase();
  }

  /// A CIA header: its size field is 0x2020, type and version 0.
  static bool _ciaHeader(Uint8List header) {
    if (header.length < 0x20) return false;
    final view = ByteData.sublistView(header);
    return view.getUint32(0, Endian.little) == 0x2020 && view.getUint32(4, Endian.little) == 0;
  }

  static int _align64(int value) => (value + 63) & ~63;

  /// Content 0 of a CIA is the game's NCCH; its TMD also names the title.
  static Future<String?> _ciaTitleId(Uint8List header, Future<Uint8List> Function(int, int) read) async {
    if (!_ciaHeader(header)) return null;
    final view = ByteData.sublistView(header);
    final certificates = _align64(0x2020);
    final ticket = certificates + _align64(view.getUint32(0x08, Endian.little));
    final tmd = ticket + _align64(view.getUint32(0x0C, Endian.little));
    final content = tmd + _align64(view.getUint32(0x10, Endian.little));
    final fromContent = programId(await read(content, _mediaUnit));
    if (fromContent != null) return fromContent;
    // TMD signed with RSA-2048 (type 0x00010004): 0x140 bytes before its header; Title ID at 0x4C.
    final signed = await read(tmd, 0x140 + 0x54);
    if (signed.length < 0x140 + 0x54 || ByteData.sublistView(signed).getUint32(0, Endian.big) != 0x00010004) {
      return null;
    }
    return _hex(signed, 0x140 + 0x4C, Endian.big);
  }

  /// Whether Azahar holds an update of [titleId]
  /// (`sdmc/Nintendo 3DS/<id0>/<id1>/title/0004000e/<low>`).
  static Future<bool> updateInstalled(Directory user, String titleId) async {
    final low = titleId.substring(8).toLowerCase();
    final root = Directory(path.join(user.path, 'sdmc', 'Nintendo 3DS'));
    if (!await root.exists()) return false;
    await for (final id0 in root.list(followLinks: false)) {
      if (id0 is! Directory) continue;
      await for (final id1 in id0.list(followLinks: false)) {
        if (id1 is! Directory) continue;
        if (await Directory(path.join(id1.path, 'title', '0004000e', low)).exists()) return true;
      }
    }
    return false;
  }

  @override
  Future<EnhancementGameIdentity> identify(GameModel game, String systemFolder) async {
    final title = game.titleName ?? game.name;
    final romPath = game.romPath;
    if (romPath == null || !romPath.startsWith('/')) {
      return EnhancementGameIdentity.unavailable(engine, EnhancementProblem.identityUnavailable, title: title);
    }
    final read = await readTitleId(romPath);
    final titleId = read.titleId;
    if (titleId == null) return EnhancementGameIdentity.unavailable(engine, read.problem, title: title);
    try {
      _updates[titleId] = await updateInstalled(await _userDirectory(), titleId);
    } on Object {
      _updates[titleId] = false;
    }
    return EnhancementGameIdentity(engine: engine, key: titleId, title: title);
  }

  List<Map<String, dynamic>> _entries(Map<String, dynamic> record) => [
    for (final entry in (record['entries'] as List? ?? const []))
      if (entry is Map) Map<String, dynamic>.from(entry),
  ];

  /// The code lines of an entry as Azahar runs them (17-character lines of
  /// known types; an E patch with all its data lines), or null.
  static List<String>? codeLines(Map<String, dynamic> entry) {
    final lines = [for (final line in (entry['lines'] as List? ?? const [])) line.toString()];
    if (lines.isEmpty || !lines.every(_line.hasMatch)) return null;
    for (var index = 0; index < lines.length; index++) {
      final line = lines[index];
      final type = int.parse(line.startsWith('D') ? line.substring(0, 2) : line.substring(0, 1), radix: 16);
      if (!(type <= 0x0C || (type >= 0xD0 && type <= 0xDD) || type == 0x0E)) return null;
      if (type == 0x0E) {
        final data = (int.parse(line.substring(9), radix: 16) + 7) ~/ 8;
        if (index + data >= lines.length) return null;
        index += data;
      }
    }
    return lines;
  }

  /// Whether a code is for an update of the game rather than its own release.
  static bool forUpdate(Map<String, dynamic> entry) {
    if (entry['update'] == true) return true;
    final versions = [for (final version in (entry['versions'] as List? ?? const [])) version.toString()];
    return versions.isNotEmpty && !versions.any(baseVersions.contains);
  }

  /// A name Azahar reads back as written (one line, its own brackets).
  static String _sectionName(String name) => name.replaceAll(RegExp(r'[\r\n\x00]'), ' ').trim();

  @override
  List<EnhancementItem> items(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState? state,
  ) {
    final update = _updates[identity.key] ?? false;
    final items = <EnhancementItem>[];
    for (final entry in _entries(record)) {
      final id = entry['id']?.toString() ?? '';
      final name = _sectionName(entry['name']?.toString() ?? '');
      final category = EnhancementCategory.parse(entry['cat']?.toString());
      if (id.isEmpty || name.isEmpty || category == null || codeLines(entry) == null) continue;
      final versions = [for (final version in (entry['versions'] as List? ?? const [])) version.toString()];
      final matches = !forUpdate(entry) || update;
      items.add(
        EnhancementItem(
          id: id,
          engine: engine,
          category: category,
          name: name,
          sourceId: entry['source']?.toString() ?? '',
          description: entry['notes']?.toString() ?? '',
          status: !matches
              ? EnhancementStatus.incompatible
              : state?.active.contains(id) == true
              ? EnhancementStatus.active
              : EnhancementStatus.available,
          problem: matches ? EnhancementProblem.none : EnhancementProblem.versionMismatch,
          compatibility: [
            'Title ID ${identity.key}',
            if (versions.isNotEmpty) 'v${versions.join(', v')}',
            if (entry['update'] == true) 'update',
          ].join(' · '),
          version: versions.join(', '),
          exclusiveGroup: entry['group']?.toString() ?? '',
          payload: {
            if (entry['combo'] is List) 'combo': entry['combo'],
            'forUpdate': forUpdate(entry),
            ...EnhancementFlags.payload(entry),
          },
        ),
      );
    }
    return items;
  }

  @override
  List<String> credits(Map<String, dynamic> record) => [
    for (final credit in (record['credits'] as List? ?? const [])) credit.toString(),
  ];

  String _key(String titleId) => path.join('cheats', '$titleId.txt');

  Future<File> _file(String titleId) async => File(path.join((await _userDirectory()).path, _key(titleId)));

  /// The player removed RewindBox's file: nothing of it applies any more.
  @override
  Future<bool> sync(EnhancementGameIdentity identity, Map<String, dynamic> record, EnhancementGameState state) async {
    final key = _key(identity.key);
    if (state.files[key] == null || await (await _file(identity.key)).exists()) return false;
    state.files.remove(key);
    state.active.clear();
    state.installed = false;
    return true;
  }

  @override
  Future<void> apply(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
    Set<String> active,
  ) async {
    final key = _key(identity.key);
    final file = await _file(identity.key);
    final current = await EnhancementFiles.digestOf(file);
    if (current != null && current != state.files[key]) {
      throw EnhancementException('user_file_present', file.path);
    }
    final text = StringBuffer();
    for (final entry in _entries(record)) {
      final lines = codeLines(entry);
      final name = _sectionName(entry['name']?.toString() ?? '');
      if (!active.contains(entry['id']) || lines == null || name.isEmpty) continue;
      text
        ..writeln('[$name]')
        ..writeln('*citra_enabled');
      lines.forEach(text.writeln);
      text.writeln();
    }
    if (text.isEmpty) {
      final written = state.files[key];
      if (written != null && await EnhancementFiles.deleteIfOwned(file, written)) state.files.remove(key);
      state.installed = false;
      return;
    }
    state.files[key] = await EnhancementFiles.writeText(file, text.toString());
    state.installed = true;
  }

  @override
  Future<void> remove(EnhancementGameState state) async {
    final user = await _userDirectory();
    for (final entry in state.files.entries.toList()) {
      final file = File(path.join(user.path, entry.key));
      if (await EnhancementFiles.deleteIfOwned(file, entry.value)) state.files.remove(entry.key);
    }
    state.data.clear();
    state.installed = false;
    state.active.clear();
  }
}
