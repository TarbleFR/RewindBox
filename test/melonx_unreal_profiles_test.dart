import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:neostation/services/melonx_unreal_profiles.dart';

void main() {
  late Directory root;
  late MelonxUnrealProfiles profiles;
  late Map<String, dynamic> info;
  String getOwn() => p.join((info['modRoots'] as List).first as String, MelonxUnrealProfiles.folder);
  File getIni() => File(p.join(getOwn(), 'romfs/Phoenix/Config/UserEngine.ini'));
  setUp(() {
    root = Directory.systemTemp.createTempSync('unreal-profiles-');
    profiles = MelonxUnrealProfiles(root);
    info = {'success': true, 'available': true, 'titleId': MelonxUnrealProfiles.titleId,
      'project': 'Phoenix', 'baseConfiguration': '[Original]\nkeep=true\n',
      'configurationPath': 'Phoenix/Config/UserEngine.ini',
      'modRoots': [p.join(root.path, 'mods/contents', MelonxUnrealProfiles.titleId),
        p.join(root.path, 'sdcard/atmosphere/contents', MelonxUnrealProfiles.titleId)]};
  });
  tearDown(() => root.deleteSync(recursive: true));

  test('nothing is installed by inspection or an off choice', () async {
    expect(await profiles.current(info), isNull);
    await profiles.apply(info, 'off');
    expect(await Directory(getOwn()).exists(), isFalse);
  });
  test('one experiment preserves original settings and is removed reversibly', () async {
    await profiles.apply(info, 'submitHint');
    expect(await getIni().readAsString(), contains('[Original]\nkeep=true\n'));
    expect(await getIni().readAsString(), contains('fx.NiagaraGpuSubmitCommandHint=0'));
    expect((await profiles.current(info))!['cvarSupportVerified'], isFalse);
    final bytes = await getIni().readAsBytes();
    await profiles.apply(info, 'off');
    expect(await Directory(getOwn()).exists(), isFalse);
    final backups = await Directory(p.join(root.path, 'UnrealProfileBackups')).list(recursive: true).where((e) => e is File && p.basename(e.path) == 'UserEngine.ini').toList();
    expect(backups.length, 1);expect(await File(backups.single.path).readAsBytes(), bytes);
  });
  test('switching trials retains just one active CVar', () async {
    await profiles.apply(info, 'submitHint');await profiles.apply(info, 'motionBlur');
    final ini = await getIni().readAsString();
    expect(ini, contains('r.MotionBlurQuality=0'));expect(ini, isNot(contains('fx.NiagaraGpuSubmitCommandHint')));
    expect((await profiles.current(info))!['changesVisualQuality'], isTrue);
  });
  test('existing loose mod wins refusal without being overwritten', () async {
    final file = File(p.join((info['modRoots'] as List)[1] as String, 'Other/romfs/Phoenix/Config/UserEngine.ini'));
    await file.parent.create(recursive: true);await file.writeAsString('keep exactly');
    await expectLater(profiles.apply(info, 'batchTicks'), throwsFormatException);
    expect(await file.readAsString(), 'keep exactly');expect(await Directory(getOwn()).exists(), isFalse);
  });
  test('uninspected romfs containers cannot be shadowed silently', () async {
    final file = File(p.join((info['modRoots'] as List).first as String, 'Other/romfs.bin'));
    await file.parent.create(recursive: true);await file.writeAsBytes([1,2,3]);
    await expectLater(profiles.apply(info, 'effects'), throwsFormatException);
    expect(await file.readAsBytes(), [1,2,3]);
  });
  test('edited owned files are preserved even on removal', () async {
    await profiles.apply(info, 'submitHint');await getIni().writeAsString('user edit');
    await expectLater(profiles.apply(info, 'off'), throwsFormatException);
    expect(await getIni().readAsString(), 'user edit');
  });
  test('an unowned destination is never replaced or removed', () async {
    await Directory(getOwn()).create(recursive: true);
    for (final choice in ['off','motionBlur']) { await expectLater(profiles.apply(info, choice), throwsFormatException); }
    expect(await Directory(getOwn()).exists(), isTrue);
  });
  test('unknown files added to an experiment are retained', () async {
    await profiles.apply(info, 'submitHint');final file = File(p.join(getOwn(), 'user.txt'));await file.writeAsString('keep');
    await expectLater(profiles.apply(info, 'off'), throwsFormatException);expect(await file.readAsString(), 'keep');
  });
  test('wrong title, traversal project, unknown experiment and external root are rejected', () async {
    for (final bad in [ {...info, 'titleId':'01006a800016e000'}, {...info, 'project':'../Phoenix'}, {...info, 'modRoots':['/tmp/contents/${MelonxUnrealProfiles.titleId}']}, {...info, 'configurationPath':'Phoenix/Config/../../save.dat'}]) {
      await expectLater(profiles.apply(bad, 'motionBlur'), throwsFormatException);
    }
    await expectLater(profiles.apply(info, 'unknown'), throwsFormatException);
  });
  test('a symlink cannot redirect profile writes', () async {
    final mods = Directory(p.join(root.path, 'mods'));await mods.create();
    await Link(p.join(mods.path, 'contents')).create(Directory.systemTemp.path);
    await expectLater(profiles.apply(info, 'motionBlur'), throwsFormatException);
  });
  test('ownership receipt cannot name a file outside the experiment', () async {
    await profiles.apply(info, 'submitHint');final file = File(p.join(getOwn(), MelonxUnrealProfiles.manifest));
    final receipt = jsonDecode(await file.readAsString()) as Map<String, dynamic>;receipt['files']={'../outside':'fake'};await file.writeAsString(jsonEncode(receipt));
    await expectLater(profiles.apply(info, 'off'), throwsFormatException);
  });
}
