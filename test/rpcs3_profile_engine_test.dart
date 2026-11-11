import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/rpcs3_config_adapter.dart';
import 'package:neostation/services/rpcs3_game_profile_database.dart';

void main() {
  test('bundles a complete, classified and iOS-safe RPCS3 database', () {
    final source = File(
      'assets/data/rpcs3_ios_profiles.json',
    ).readAsStringSync();
    final entries = Rpcs3GameProfileDatabase.parseDatabaseForTesting(source);
    expect(entries.length, greaterThanOrEqualTo(2000));
    expect(entries['BCUS98111'], isNotNull);
    final configs = entries.values.map((entry) => entry.config).join('\n');
    expect(configs, isNot(contains('Renderer: OpenGL')));
    expect(configs, isNot(contains('Frame limit: Infinite')));
    expect(configs, isNot(contains('Frame limit: Off')));

    final root = jsonDecode(source) as Map<String, dynamic>;
    expect(root['source_url'], Rpcs3GameProfileDatabase.sourceUrl);
    expect(root['policy'], isA<Map<String, dynamic>>());
  });

  test('merges nested scalar overrides without losing lists or siblings', () {
    const source = '''
Core:
  Libraries Control:
    - libvdec.sprx:lle
  SPU Block Size: Safe
Video:
  Vulkan:
    Asynchronous Texture Streaming: false
  Write Color Buffers: true
''';
    final merged = Rpcs3ConfigAdapter.mergeScalarOverrides(source, {
      const ['Core', 'SPU Block Size']: 'Mega',
      const ['Video', 'Vulkan', 'Asynchronous Texture Streaming']: 'true',
      const ['iOS Experimental', 'RSX FIFO Read Cache']: '4 KiB',
    });
    expect(merged, contains('- libvdec.sprx:lle'));
    expect(merged, contains('SPU Block Size: Mega'));
    expect(merged, contains('Write Color Buffers: true'));
    expect(merged, contains('Asynchronous Texture Streaming: true'));
    expect(merged, contains('iOS Experimental:\n  RSX FIFO Read Cache: 4 KiB'));
  });

  test('does not apply the database\'s asynchronous texture streaming', () {
    // BCES00510 (God of War III), live GameDB shape; IPA 724 device result.
    final result = Rpcs3ConfigAdapter.sanitiseForIOS('''
Video:
  Vulkan:
    Asynchronous Texture Streaming: true
  Shader Precision: Ultra
  Write Color Buffers: true
Core:
  SPU Block Size: Mega
''');
    expect(result, isNot(contains('Asynchronous Texture Streaming')));
    expect(result, isNot(contains('Vulkan:')));
    expect(
      result,
      'Video:\n  Shader Precision: Ultra\n  Write Color Buffers: true\n'
      'Core:\n  SPU Block Size: Mega\n',
    );
    // An entry that turns it off, and a sibling Vulkan key, are kept.
    final kept = Rpcs3ConfigAdapter.sanitiseForIOS('''
Video:
  Vulkan:
    Asynchronous Texture Streaming: false
    Asynchronous Queue Scheduler: Fast
''');
    expect(kept, contains('Asynchronous Texture Streaming: false'));
    expect(kept, contains('Asynchronous Queue Scheduler: Fast'));
    // The user's own choice for a title still turns it on.
    final chosen = Rpcs3ConfigAdapter.mergeScalarOverrides(
      'Video:\n  Vulkan:\n    Asynchronous Texture Streaming: true\n',
      {
        const ['Video', 'Vulkan', 'Asynchronous Texture Streaming']: 'true',
      },
    );
    expect(chosen, contains('Asynchronous Texture Streaming: true'));
  });

  test('drops upstream-only keys the Core rejects and sections they empty', () {
    // Live GameDB shapes (1 November 2026): BCES00009 carries both VFS keys,
    // BLES00028 the Core key; the Core's strict validation refuses the whole
    // publication when any published entry contains one of them.
    const source = '''
Core:
  SPU MMIO Delay Enabled: true
  SPU Block Size: Safe
  Libraries Control:
    - libvdec.sprx:lle
VFS:
  Emulate HDD Read Speed: true
  Emulate BD-ROM Read Speed: true
Video:
  Write Color Buffers: true
''';
    final result = Rpcs3ConfigAdapter.sanitiseForIOS(source);
    expect(result, isNot(contains('SPU MMIO Delay Enabled')));
    expect(result, isNot(contains('Emulate HDD Read Speed')));
    expect(result, isNot(contains('Emulate BD-ROM Read Speed')));
    expect(result, isNot(contains('VFS:')));
    expect(result, contains('Core:\n  SPU Block Size: Safe'));
    expect(result, contains('  Libraries Control:\n    - libvdec.sprx:lle'));
    expect(result, contains('Video:\n  Write Color Buffers: true'));

    // A section with a kept sibling stays; a key of the same name in another
    // section is not touched; an entry left empty is not useful.
    final sibling = Rpcs3ConfigAdapter.sanitiseForIOS('''
VFS:
  Emulate HDD Read Speed: true
  Enable /host_root/: false
Miscellaneous:
  SPU MMIO Delay Enabled: true
''');
    expect(sibling, contains('VFS:\n  Enable /host_root/: false'));
    expect(sibling, contains('Miscellaneous:\n  SPU MMIO Delay Enabled: true'));
    final emptied = Rpcs3ConfigAdapter.sanitiseForIOS('''
VFS:
  Emulate BD-ROM Read Speed: true
''');
    expect(emptied.trim(), isEmpty);
    expect(Rpcs3ConfigAdapter.hasUsefulSetting(emptied), isFalse);
    expect(
      Rpcs3ConfigAdapter.sanitiseForIOS('Video:\n  Renderer: OpenGL\n').trim(),
      isEmpty,
    );
  });

  test('drops only desktop renderer and unbounded handheld frame limits', () {
    const source = '''
Video:
  Renderer: OpenGL
  Frame limit: Infinite
  Write Color Buffers: true
Core:
  Max SPURS Threads: 3
''';
    final result = Rpcs3ConfigAdapter.sanitiseForIOS(source);
    expect(result, isNot(contains('Renderer: OpenGL')));
    expect(result, isNot(contains('Frame limit: Infinite')));
    expect(result, contains('Write Color Buffers: true'));
    // Unlike ARMSX3, NeoStation does not strip this without Apple-SoC data.
    expect(result, contains('Max SPURS Threads: 3'));
  });
}
