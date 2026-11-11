import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' show Locale, PlatformDispatcher;

import 'package:path/path.dart' as path;

/// The control metadata of one Switch 2 export folder.
class Switch2Control {
  const Switch2Control({required this.directory, required this.nacp});

  /// Folder that holds control.nacp (and the icon_<Language>.dat files).
  final String directory;
  final Uint8List nacp;
}

/// Reads what the library needs from a Switch 2 console export (docs/s2arm-switch2-library.md): the program id from
/// base/exefs/main.npdm, the title, publisher and display version from control.nacp, the icon. Pure Dart, synchronous
/// and bounded; it never reads a RomFS and never writes. The export layout and the lookups mirror the native
/// preparation in native/s2arm/prepare/s2arm_ns2_dump.c.
abstract final class Switch2ExportContent {
  static const int npdmLimit = 1024 * 1024;
  static const int iconLimit = 1024 * 1024;
  static const int nacpSize = 0x4000;

  static const int _titleEntrySize = 0x300;
  static const int _titleNameSize = 0x200;
  static const int _titlePublisherSize = 0x100;
  static const int _titleCount = 16;
  static const int _displayVersionOffset = 0x3060;
  static const int _displayVersionSize = 0x10;

  /// Nintendo Switch ApplicationTitle language order (index into the NACP title table) and the name used by the
  /// `icon_<Language>.dat` files.
  static const List<String> languages = <String>[
    'AmericanEnglish',
    'BritishEnglish',
    'Japanese',
    'French',
    'German',
    'LatinAmericanSpanish',
    'Spanish',
    'Italian',
    'Dutch',
    'CanadianFrench',
    'Portuguese',
    'Russian',
    'Korean',
    'TraditionalChinese',
    'SimplifiedChinese',
    'BrazilianPortuguese',
  ];

  // ---------------- library entry ----------------

  /// Whether [filePath] is the NPDM of an export's base program: `<export>/base/exefs/main.npdm`. Entries under an
  /// export's `updates/<n>/` or `dlc/<n>/` are never library entries, nor is a `base` folder without an export folder
  /// above it.
  static bool isLibraryEntry(String filePath) {
    final segments = path.split(path.normalize(filePath.replaceAll('\\', '/')));
    final count = segments.length;
    if (count < 4) return false;
    if (segments[count - 1].toLowerCase() != 'main.npdm') return false;
    if (segments[count - 2].toLowerCase() != 'exefs') return false;
    if (segments[count - 3].toLowerCase() != 'base') return false;
    final exportName = segments[count - 4].toLowerCase();
    if (exportName == 'updates' || exportName == 'dlc') return false;
    if (count >= 5) {
      final parent = segments[count - 5].toLowerCase();
      if ((parent == 'updates' || parent == 'dlc') && RegExp(r'^\d+$').hasMatch(exportName)) return false;
    }
    return true;
  }

  /// The export folder of a library entry (`<export>/base/exefs/main.npdm` -> `<export>`).
  static String exportFolder(String npdmPath) => path.dirname(path.dirname(path.dirname(npdmPath)));

  /// The `filename` stored for a library entry in `user_roms`. Every entry's file is `main.npdm`, and scraped
  /// metadata is keyed by (system, filename) (`user_screenscraper_metadata`, UNIQUE(app_system_id, filename)) while
  /// media files are named after the filename without its extension: each game gets its own name, like MeloNX's
  /// `<title id>.melonx` rows. `<title id>.npdm` when the NPDM gives one (the box art copied from the export and
  /// scraped media are then `<title id>.<ext>`), else the export folder's name with a short digest of the entry's
  /// path (two roots may hold folders of the same name).
  static String libraryFileName(String npdmPath, String? titleId) {
    final id = titleId?.trim().toLowerCase() ?? '';
    if (RegExp(r'^[0-9a-f]{16}$').hasMatch(id)) return '$id.npdm';
    final folder = path.basename(exportFolder(npdmPath)).replaceAll(RegExp(r'[^A-Za-z0-9 ._-]'), '_').trim();
    var hash = 0x811c9dc5; // FNV-1a 32 over the UTF-8 path: stable across runs, unlike String.hashCode
    for (final byte in utf8.encode(path.normalize(npdmPath))) {
      hash = ((hash ^ byte) * 0x01000193) & 0xffffffff;
    }
    final digest = hash.toRadixString(16).padLeft(8, '0');
    return '${folder.isEmpty ? 'switch2' : folder}-$digest.npdm';
  }

  // ---------------- NPDM ----------------

  /// The program id as 16 lowercase hex digits from NPDM bytes, or null: `META` magic, ACI0 offset u32 LE at 0x70,
  /// `ACI0` magic there and the program id u64 LE at ACI0 + 0x10.
  static String? programIdFromNpdm(Uint8List bytes) {
    if (bytes.length < 0x80) return null;
    if (!_magic(bytes, 0, 'META')) return null;
    final data = ByteData.sublistView(bytes);
    final aci = data.getUint32(0x70, Endian.little);
    if (aci + 0x18 > bytes.length || !_magic(bytes, aci, 'ACI0')) return null;
    final id = data.getUint64(aci + 0x10, Endian.little);
    return id.toRadixString(16).padLeft(16, '0');
  }

  /// The program id of the NPDM file at [npdmPath], or null when unreadable, oversized or not an NPDM.
  static String? titleId(String npdmPath) {
    final bytes = _readBounded(npdmPath, npdmLimit);
    return bytes == null ? null : programIdFromNpdm(bytes);
  }

  // ---------------- control.nacp ----------------

  /// The version folders the control data is looked up in: the newest `updates/<n>` first when it exists, then `base`
  /// (s2arm_ns2_dump.c, the `dirs` of the control step ~line 1528: `{upd ? upd : base, base}`).
  static List<String> controlRoots(String exportDir) {
    final roots = <String>[];
    try {
      final updates = Directory(path.join(exportDir, 'updates'));
      if (updates.existsSync()) {
        final numbered = <String>[];
        for (final entry in updates.listSync(followLinks: false)) {
          final name = path.basename(entry.path);
          if (entry is Directory && RegExp(r'^\d+$').hasMatch(name)) numbered.add(name);
        }
        if (numbered.isNotEmpty) {
          // numdirs(): by numeric value, ties by name; the newest is the last.
          numbered.sort((a, b) {
            final byValue = BigInt.parse(a).compareTo(BigInt.parse(b));
            return byValue != 0 ? byValue : a.compareTo(b);
          });
          roots.add(path.join(updates.path, numbered.last));
        }
      }
    } on FileSystemException {
      // No usable update folder; the base is still read.
    }
    roots.add(path.join(exportDir, 'base'));
    return roots;
  }

  /// Finds control.nacp as s2arm_ns2_dump.c `find_control()` (~lines 850-890) does: in a version folder or one level
  /// below it (never inside `romfs` or `exefs`), a file of exactly 0x4000 bytes, the version folders in
  /// [controlRoots] order.
  static Switch2Control? findControl(String exportDir) {
    for (final root in controlRoots(exportDir)) {
      final places = <String>[root];
      try {
        final directory = Directory(root);
        if (!directory.existsSync()) continue;
        final children = <String>[];
        for (final entry in directory.listSync(followLinks: false)) {
          final name = path.basename(entry.path);
          if (entry is Directory && name != 'romfs' && name != 'exefs') children.add(entry.path);
        }
        children.sort();
        places.addAll(children);
      } on FileSystemException {
        continue;
      }
      for (final place in places) {
        final file = File(path.join(place, 'control.nacp'));
        try {
          if (!file.existsSync() || file.lengthSync() != nacpSize) continue;
        } on FileSystemException {
          continue;
        }
        final bytes = _readBounded(file.path, nacpSize);
        if (bytes != null && bytes.length == nacpSize) return Switch2Control(directory: place, nacp: bytes);
      }
    }
    return null;
  }

  /// The NACP language indexes to try for [locale], best first, then American English, then the rest in table order.
  static List<int> languageOrder(Locale locale) {
    final country = locale.countryCode?.toUpperCase();
    final preferred = switch (locale.languageCode) {
      'en' => country == 'GB' || country == 'IE' || country == 'AU' || country == 'NZ' ? 1 : 0,
      'ja' => 2,
      'fr' => country == 'CA' ? 9 : 3,
      'de' => 4,
      'es' => country == null || country == 'ES' ? 6 : 5,
      'it' => 7,
      'nl' => 8,
      'pt' => country == 'BR' ? 15 : 10,
      'ru' => 11,
      'ko' => 12,
      'zh' =>
        locale.scriptCode?.toLowerCase() == 'hant' || const {'TW', 'HK', 'MO'}.contains(country) ? 13 : 14,
      _ => 0,
    };
    return <int>{preferred, 0, for (var index = 0; index < _titleCount; index++) index}.toList();
  }

  /// The (name, publisher) of the title entry [language] of [nacp]; empty strings when it is unset.
  static ({String name, String publisher}) titleEntry(Uint8List nacp, int language) {
    if (nacp.length < nacpSize || language < 0 || language >= _titleCount) return (name: '', publisher: '');
    final start = language * _titleEntrySize;
    return (
      name: _cString(nacp, start, _titleNameSize),
      publisher: _cString(nacp, start + _titleNameSize, _titlePublisherSize),
    );
  }

  /// The best (name, publisher) of [nacp] for [locale], or null when no entry has a name.
  static ({String name, String publisher})? bestTitle(Uint8List nacp, Locale locale) {
    for (final language in languageOrder(locale)) {
      final entry = titleEntry(nacp, language);
      if (entry.name.isNotEmpty) return entry;
    }
    return null;
  }

  /// DisplayVersion (0x10 bytes at 0x3060), empty when unset.
  static String displayVersion(Uint8List nacp) =>
      nacp.length < nacpSize ? '' : _cString(nacp, _displayVersionOffset, _displayVersionSize);

  /// The library title of the export whose base NPDM is [npdmPath]: the NACP title for the device locale, else the
  /// export folder name.
  static String libraryTitle(String npdmPath, {Locale? locale}) {
    final folder = exportFolder(npdmPath);
    final control = findControl(folder);
    if (control != null) {
      final best = bestTitle(control.nacp, locale ?? PlatformDispatcher.instance.locale);
      if (best != null) return best.name;
    }
    return path.basename(folder);
  }

  // ---------------- icon ----------------

  /// The `icon_<Language>.dat` JPEG next to control.nacp: the one of the best language for [locale], else the first
  /// by name (the C port takes the first it lists). Null when there is none or it exceeds [iconLimit].
  static File? iconFile(String exportDir, {Locale? locale}) {
    final control = findControl(exportDir);
    if (control == null) return null;
    final files = <File>[];
    try {
      for (final entry in Directory(control.directory).listSync(followLinks: false)) {
        final name = path.basename(entry.path);
        if (entry is File && name.startsWith('icon_') && name.endsWith('.dat')) files.add(entry);
      }
    } on FileSystemException {
      return null;
    }
    if (files.isEmpty) return null;
    files.sort((a, b) => path.basename(a.path).compareTo(path.basename(b.path)));
    File? chosen;
    for (final language in languageOrder(locale ?? PlatformDispatcher.instance.locale)) {
      final wanted = 'icon_${languages[language]}.dat';
      for (final file in files) {
        if (path.basename(file.path) == wanted) {
          chosen = file;
          break;
        }
      }
      if (chosen != null) break;
    }
    chosen ??= files.first;
    try {
      return chosen.lengthSync() <= iconLimit ? chosen : null;
    } on FileSystemException {
      return null;
    }
  }

  // ---------------- helpers ----------------

  static bool _magic(Uint8List bytes, int offset, String magic) {
    if (offset < 0 || offset + magic.length > bytes.length) return false;
    for (var index = 0; index < magic.length; index++) {
      if (bytes[offset + index] != magic.codeUnitAt(index)) return false;
    }
    return true;
  }

  /// UTF-8, NUL-terminated within [size] bytes, undecodable bytes replaced.
  static String _cString(Uint8List bytes, int offset, int size) {
    var end = offset;
    final limit = offset + size;
    while (end < limit && end < bytes.length && bytes[end] != 0) {
      end++;
    }
    return utf8.decode(bytes.sublist(offset, end), allowMalformed: true).trim();
  }

  /// The whole file when it is at most [limit] bytes; null when it is larger, missing or unreadable.
  static Uint8List? _readBounded(String filePath, int limit) {
    RandomAccessFile? handle;
    try {
      handle = File(filePath).openSync();
      if (handle.lengthSync() > limit) return null;
      return handle.readSync(limit + 1);
    } on FileSystemException {
      return null;
    } finally {
      handle?.closeSync();
    }
  }
}
