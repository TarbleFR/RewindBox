import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:path/path.dart' as p;

/// One Nintendo Switch user profile of the embedded MeloNX engine.
class MelonxProfile {
  const MelonxProfile({required this.id, required this.name, this.image, this.modified = 0});

  /// 32 lowercase hex digits, the engine's `UserId`.
  final String id;
  final String name;

  /// The profile picture as the engine stores it (JPEG), when it has one.
  final Uint8List? image;

  /// Seconds since the Unix epoch.
  final int modified;

  /// The engine recreates this profile whenever it is missing, and then opens
  /// it instead of the selected one: it is never deleted here.
  bool get isDefault => id == MelonxProfilesService.defaultId;
}

class MelonxProfilesState {
  const MelonxProfilesState(this.profiles, this.activeId);
  final List<MelonxProfile> profiles;

  /// The profile games open (the engine's `last_opened`).
  final String activeId;

  MelonxProfile get active => profiles.firstWhere((profile) => profile.id == activeId, orElse: () => profiles.first);
}

/// A refusal the profiles screen translates ([code] is a locale key).
class MelonxProfilesException implements Exception {
  const MelonxProfilesException(this.code, [this.detail = '']);
  final String code;
  final String detail;
  @override
  String toString() => detail.isEmpty ? code : '$code:$detail';
}

/// Nintendo Switch user profiles, kept in the engine's own
/// `Documents/MeloNX/system/Profiles.json`.
///
/// The engine rebuilds its account manager from that file at every game
/// launch, and the standalone MeloNX app edits the same file from its own
/// profile screen, so no engine call is needed: RewindBox reads and rewrites
/// it while no game runs (callers hold `MelonxInternalService.editLibrary`).
/// Unknown fields are kept; the file is replaced atomically.
abstract final class MelonxProfilesService {
  static const defaultId = '00000000000000010000000000000000';
  static const defaultName = 'MeloNX';

  /// A Switch holds at most eight users.
  static const maxProfiles = 8;

  /// The console's own limit for a nickname.
  static const maxNameCharacters = 10;

  /// The guest reads a nickname from a 32-byte UTF-8 field; one byte stays
  /// free for its terminator.
  static const maxNameBytes = 31;

  /// The guest loads a picture into a 128 KiB buffer.
  static const maxImageBytes = 0x20000;
  static const _maxFileBytes = 8 * 1024 * 1024;
  static final _idPattern = RegExp(r'^[0-9a-f]{32}$');

  static File profilesFile(Directory root) => File(p.join(root.path, 'system', 'Profiles.json'));

  /// The profiles as the next launch will see them. Without a file the engine
  /// starts with its default profile alone, which is what this returns.
  static Future<MelonxProfilesState> load(Directory root) async => _state(await _read(root));

  static Future<MelonxProfilesState> create(
    Directory root,
    String name, {
    required Uint8List image,
    required Future<Uint8List> Function() defaultImage,
    Random? random,
  }) async {
    final clean = validateName(name);
    _validateImage(image);
    final document = await _read(root);
    final profiles = await _materialized(document, defaultImage);
    if (profiles.length >= maxProfiles) throw const MelonxProfilesException('profileLimit');
    final generator = random ?? Random.secure();
    String id;
    do {
      id = [for (var index = 0; index < 16; index++) generator.nextInt(256).toRadixString(16).padLeft(2, '0')].join();
    } while (id == defaultId || id == '0' * 32 || profiles.any((profile) => _id(profile) == id));
    profiles.add(<String, dynamic>{
      'user_id': id,
      'name': clean,
      'account_state': 'Closed',
      'online_play_state': 'Closed',
      'last_modified_timestamp': _now(),
      'image': base64Encode(image),
    });
    await _write(root, document);
    return _state(document);
  }

  static Future<MelonxProfilesState> rename(
    Directory root,
    String id,
    String name, {
    required Future<Uint8List> Function() defaultImage,
  }) async {
    final clean = validateName(name);
    final document = await _read(root);
    final profile = _find(await _materialized(document, defaultImage), id);
    profile['name'] = clean;
    profile['last_modified_timestamp'] = _now();
    await _write(root, document);
    return _state(document);
  }

  static Future<MelonxProfilesState> setImage(
    Directory root,
    String id,
    Uint8List image, {
    required Future<Uint8List> Function() defaultImage,
  }) async {
    _validateImage(image);
    final document = await _read(root);
    final profile = _find(await _materialized(document, defaultImage), id);
    profile['image'] = base64Encode(image);
    profile['last_modified_timestamp'] = _now();
    await _write(root, document);
    return _state(document);
  }

  /// Makes [id] the profile games open from the next launch.
  static Future<MelonxProfilesState> select(
    Directory root,
    String id, {
    required Future<Uint8List> Function() defaultImage,
  }) async {
    final document = await _read(root);
    final profiles = await _materialized(document, defaultImage);
    _find(profiles, id);
    for (final profile in profiles) {
      profile['account_state'] = _id(profile) == id ? 'Open' : 'Closed';
    }
    document['last_opened'] = id;
    await _write(root, document);
    return _state(document);
  }

  /// Removes a profile from the list. Its saves stay on the device, under its
  /// identifier; nothing is deleted from the save storage.
  ///
  /// Refused for the default profile, and for a profile a game is pinned to
  /// (`rewindboxSaveProfileId`, written when its saves were imported): that
  /// game would otherwise refuse to start.
  static Future<MelonxProfilesState> delete(
    Directory root,
    String id, {
    required Future<Uint8List> Function() defaultImage,
  }) async {
    if (id == defaultId) throw const MelonxProfilesException('profileDefault');
    final document = await _read(root);
    final profiles = await _materialized(document, defaultImage);
    final profile = _find(profiles, id);
    final pinned = await pinnedTitles(root, id);
    if (pinned.isNotEmpty) throw MelonxProfilesException('profileInUse', pinned.join(', '));
    profiles.remove(profile);
    if (document['last_opened'] == id) {
      document['last_opened'] = defaultId;
      for (final other in profiles) {
        other['account_state'] = _id(other) == defaultId ? 'Open' : 'Closed';
      }
    }
    await _write(root, document);
    return _state(document);
  }

  /// Title identifiers whose configuration opens [id] whatever the selection.
  static Future<List<String>> pinnedTitles(Directory root, String id) async {
    final titles = <String>[];
    Future<void> inspect(File file, String label) async {
      try {
        if (!await file.exists() || await file.length() > 4 * 1024 * 1024) return;
        final decoded = jsonDecode(await file.readAsString());
        if (decoded is Map && '${decoded['rewindboxSaveProfileId']}'.toLowerCase() == id) titles.add(label);
      } on Object {
        // An unreadable configuration pins nothing the engine could open.
      }
    }

    await inspect(File(p.join(root.path, 'config.json')), '*');
    final folder = Directory(p.join(root.path, 'config'));
    if (await folder.exists()) {
      await for (final entry in folder.list(followLinks: false)) {
        final name = p.basename(entry.path);
        if (entry is File && name.toLowerCase().endsWith('_config.json')) {
          await inspect(entry, name.substring(0, name.length - '_config.json'.length).toLowerCase());
        }
      }
    }
    titles.sort();
    return titles;
  }

  /// The trimmed nickname, or a refusal: empty, over ten characters, over the
  /// guest's field, or holding a control character.
  static String validateName(String name) {
    final clean = name.trim();
    if (clean.isEmpty) throw const MelonxProfilesException('profileNameEmpty');
    if (clean.runes.length > maxNameCharacters || utf8.encode(clean).length > maxNameBytes) {
      throw const MelonxProfilesException('profileNameLong');
    }
    if (clean.runes.any((rune) => rune < 0x20 || rune == 0x7F)) {
      throw const MelonxProfilesException('profileNameInvalid');
    }
    return clean;
  }

  static void _validateImage(Uint8List image) {
    // A JPEG starts with SOI and ends with EOI.
    final jpeg = image.length > 4 &&
        image[0] == 0xFF && image[1] == 0xD8 && image[image.length - 2] == 0xFF && image[image.length - 1] == 0xD9;
    if (!jpeg || image.length > maxImageBytes) throw const MelonxProfilesException('profileImageInvalid');
  }

  static int _now() => DateTime.now().millisecondsSinceEpoch ~/ 1000;
  static String _id(Map<String, dynamic> profile) => '${profile['user_id']}'.toLowerCase();

  static Map<String, dynamic> _find(List<Map<String, dynamic>> profiles, String id) {
    for (final profile in profiles) {
      if (_id(profile) == id) return profile;
    }
    throw const MelonxProfilesException('profileUnknown');
  }

  /// The document's profile list, completed with the default profile the
  /// engine requires (it would otherwise add it and open it).
  static Future<List<Map<String, dynamic>>> _materialized(
    Map<String, dynamic> document,
    Future<Uint8List> Function() defaultImage,
  ) async {
    final profiles = document['profiles'] as List<Map<String, dynamic>>;
    if (!profiles.any((profile) => _id(profile) == defaultId)) {
      final image = await defaultImage();
      _validateImage(image);
      profiles.insert(0, <String, dynamic>{
        'user_id': defaultId,
        'name': defaultName,
        'account_state': profiles.isEmpty ? 'Open' : 'Closed',
        'online_play_state': 'Closed',
        'last_modified_timestamp': _now(),
        'image': base64Encode(image),
      });
    }
    final opened = '${document['last_opened'] ?? ''}'.toLowerCase();
    if (!profiles.any((profile) => _id(profile) == opened)) document['last_opened'] = defaultId;
    return profiles;
  }

  static Future<Map<String, dynamic>> _read(Directory root) async {
    final file = profilesFile(root);
    if (!await file.exists()) {
      return <String, dynamic>{'profiles': <Map<String, dynamic>>[], 'last_opened': defaultId};
    }
    if (await file.length() > _maxFileBytes) throw const MelonxProfilesException('profilesUnreadable', 'size');
    final Object? decoded;
    try {
      decoded = jsonDecode(await file.readAsString());
    } on FormatException catch (error) {
      throw MelonxProfilesException('profilesUnreadable', error.message);
    }
    if (decoded is! Map || decoded['profiles'] is! List) {
      throw const MelonxProfilesException('profilesUnreadable', 'structure');
    }
    final document = Map<String, dynamic>.from(decoded);
    final profiles = <Map<String, dynamic>>[];
    for (final entry in decoded['profiles'] as List) {
      if (entry is! Map || !_idPattern.hasMatch('${entry['user_id']}'.toLowerCase()) || entry['name'] is! String) {
        throw const MelonxProfilesException('profilesUnreadable', 'profile');
      }
      profiles.add(Map<String, dynamic>.from(entry));
    }
    document['profiles'] = profiles;
    return document;
  }

  static MelonxProfilesState _state(Map<String, dynamic> document) {
    final profiles = <MelonxProfile>[];
    for (final entry in document['profiles'] as List<Map<String, dynamic>>) {
      Uint8List? image;
      final encoded = entry['image'];
      if (encoded is String && encoded.isNotEmpty) {
        try {
          image = base64Decode(encoded);
        } on FormatException {
          image = null;
        }
      }
      final modified = entry['last_modified_timestamp'];
      profiles.add(MelonxProfile(id: _id(entry), name: entry['name'] as String, image: image, modified: modified is int ? modified : 0));
    }
    if (!profiles.any((profile) => profile.isDefault)) {
      profiles.insert(0, const MelonxProfile(id: defaultId, name: defaultName));
    }
    final opened = '${document['last_opened'] ?? ''}'.toLowerCase();
    return MelonxProfilesState(
      List.unmodifiable(profiles),
      profiles.any((profile) => profile.id == opened) ? opened : defaultId,
    );
  }

  static Future<void> _write(Directory root, Map<String, dynamic> document) async {
    final file = profilesFile(root);
    await file.parent.create(recursive: true);
    final temporary = File('${file.path}.rewindbox-tmp');
    await temporary.writeAsString(const JsonEncoder.withIndent('  ').convert(document), flush: true);
    await temporary.rename(file.path);
  }
}
