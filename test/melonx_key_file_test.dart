import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:neostation/services/melonx_key_file.dart';
import 'package:neostation/services/melonx_embedded_library_service.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:neostation/l10n/melonx_transfer_locale.dart';

class _Paths extends PathProviderPlatform {
  _Paths(this.path);
  final String path;
  @override
  Future<String?> getApplicationDocumentsPath() async => path;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final line = 'header_key = ${'a' * 64}';
  test('provider aliases resolve to canonical key types without guessing arbitrary files', () {
    for (final name in ['prod.keys', 'PROD.KEYS', 'prod.keys.txt', 'prod (1).keys', 'prod(2).keys.txt']) {
      expect(MelonxKeyFile.canonicalName(name), 'prod.keys');
    }
    expect(MelonxKeyFile.canonicalName('title (2).KEYS.txt'), 'title.keys');
    for (final name in ['random.keys', 'prod.keys.zip', 'prodkeys', 'dev.keys']) {
      expect(MelonxKeyFile.canonicalName(name), isNull);
    }
  });
  test('UTF8 BOM, UTF16 LE/BE, CRLF, comments and LibHac comma delimiter normalize', () {
    final text = '# personal\r\n\r\n${line.toUpperCase().replaceFirst(' = ', ',\t')}\r\n';
    for (final bytes in [
      utf8.encode(text), [0xef, 0xbb, 0xbf, ...utf8.encode(text)],
      [0xff, 0xfe, for (final c in text.codeUnits) ...[c & 255, c >> 8]],
      [0xfe, 0xff, for (final c in text.codeUnits) ...[c >> 8, c & 255]],
    ]) {
      expect(MelonxKeyFile.normalize(bytes, 'prod.keys'), line);
    }
  });
  test('unsupported entries survive normalization for the native schema', () {
    final text = '$line\nfuture_console_key = ${'b' * 32}';
    expect(MelonxKeyFile.normalize(utf8.encode(text), 'prod.keys'), text);
  });
  test('malformed and oversized data never enters the transaction', () {
    for (final bytes in [<int>[], [0xff], [0xff, 0xfe, 1], utf8.encode('header_key = xyz'),
      utf8.encode('header_key = abc'), utf8.encode('<html>error</html>'),
      utf8.encode('header_key = ${'a' * 2048}'), List.filled(4 * 1024 * 1024 + 1, 0)]) {
      expect(() => MelonxKeyFile.normalize(bytes, 'prod.keys'), throwsFormatException);
    }
    expect(() => MelonxKeyFile.normalize(utf8.encode('ab = cd'), 'title.keys'), throwsFormatException);
  });
  test('every new refusal and compatibility notice exists in all twelve languages', () {
    expect(MelonxTransferLocale.values.length, 12);
    for (final values in MelonxTransferLocale.values.values) {
      for (final key in ['keySyntax','keySize','keyConflict','keyNoSupported','keyReadFailed','keyImportFailed','keyExtras','keyInvalidSizes']) {
        expect(values[key], isNotEmpty);
      }
    }
  });

  group('production import transaction', () {
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    late Directory temp;
    late PathProviderPlatform previous;
    var code = '';
    final staged = <String>[];
    var reloads = 0;
    var invalidSizes = 0;
    setUp(() async {
      temp = await Directory.systemTemp.createTemp('melonx-key-regression-');
      previous = PathProviderPlatform.instance;
      PathProviderPlatform.instance = _Paths(temp.path);
      code = ''; staged.clear(); reloads = 0; invalidSizes = 0;
      messenger.setMockMethodCallHandler(MelonxInternalService.channel, (call) async {
        if (call.method == 'beginLibraryMutation') return true;
        if (call.method == 'endLibraryMutation') return null;
        final path = (call.arguments as Map)['path'] as String;
        if (path.isEmpty) { reloads++; return {'success':true}; }
        staged.add(await File(path).readAsString());
        return code.isEmpty ? {'success':true,'recognizedKeys':1,'ignoredKeys':1,'invalidSizeKeys':invalidSizes} :
          {'success':false,'errorCode':code,'diagnostic':'sensitive native detail must not be displayed'};
      });
    });
    tearDown(() async {
      messenger.setMockMethodCallHandler(MelonxInternalService.channel, null);
      PathProviderPlatform.instance = previous;
      await temp.delete(recursive:true);
    });
    test('renamed UTF16 export installs canonically with extras preserved and one reload', () async {
      final text = '$line\nfuture_console_key = ${'b' * 32}';
      final source = File('${temp.path}/PROD (1).KEYS.txt');
      final bytes = [0xff,0xfe,for (final c in text.codeUnits) ...[c & 255,c >> 8]];
      await source.writeAsBytes(bytes);
      final report = await MelonxEmbeddedLibraryService.importKeyFiles([source]);
      expect(report.imported,['prod.keys']); expect(report.refused,isEmpty);
      expect(report.ignored,{'prod.keys':1}); expect(report.prodMissing,false);
      expect(await File('${temp.path}/MeloNX/system/prod.keys').readAsString(),text);
      expect(await source.readAsBytes(),bytes); expect(staged,[text]); expect(reloads,1);
    });
    test('aliases of the same type are rejected before either overwrites installed keys', () async {
      final installed = File('${temp.path}/MeloNX/system/prod.keys');
      await installed.parent.create(recursive:true); await installed.writeAsString('keep');
      final a = await File('${temp.path}/prod.keys').writeAsString(line);
      final b = await File('${temp.path}/prod (1).keys.txt').writeAsString(line);
      final report = await MelonxEmbeddedLibraryService.importKeyFiles([a,b]);
      expect(report.imported,isEmpty); expect(report.refused.values, everyElement('duplicateKey'));
      expect(await installed.readAsString(),'keep'); expect(staged,isEmpty); expect(reloads,0);
    });
    test('mixed key sizes install without altering values and expose the native warning', () async {
      invalidSizes = 1;
      final text = '$line\nmariko_master_kek_source_05 = ${'c' * 34}';
      final source = await File('${temp.path}/prod.keys').writeAsString(text);
      final report = await MelonxEmbeddedLibraryService.importKeyFiles([source]);
      expect(report.imported,['prod.keys']); expect(report.refused,isEmpty);
      expect(report.invalidSizes,{'prod.keys':1}); expect(report.prodMissing,false);
      expect(await File('${temp.path}/MeloNX/system/prod.keys').readAsString(),text);
      expect(await source.readAsString(),text); expect(reloads,1);
    });
    test('native refusal codes survive instead of becoming invalid key', () async {
      final source = await File('${temp.path}/prod.keys').writeAsString(line);
      for (final value in ['keySize','keyConflict','keyNoSupported','keyReadFailed','keyImportFailed','unrecognizedNativeError']) {
        code = value;
        final report = await MelonxEmbeddedLibraryService.importKeyFiles([source]);
        expect(report.refused['prod.keys'],value == 'unrecognizedNativeError' ? 'keyImportFailed' : value);
        expect(report.imported,isEmpty);
      }
      expect(reloads,0); expect(await File('${temp.path}/MeloNX/system/prod.keys').exists(),false);
    });
  });
}
