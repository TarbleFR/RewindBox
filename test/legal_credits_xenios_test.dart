import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// The Xbox 360 entries of Settings > Legal and credits: XeniOS (BSD-3-Clause)
/// and Apple's Metal Shader Converter (agreement EA1844, acknowledgements and
/// the headers' Apache-2.0 licence) are bundled as offline texts.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('the XeniOS licence is bundled and is its BSD-3-Clause text', () async {
    final text = await rootBundle.loadString(
      'assets/legal/XeniOS-BSD-3-Clause.txt',
    );
    expect(text, contains('Ben Vanik'));
    expect(text, contains('Redistribution and use in source and binary forms'));
  });

  test("Apple's Metal Shader Converter notices are bundled in full", () async {
    final text = await rootBundle.loadString(
      'assets/legal/Apple-Metal-Shader-Converter-NOTICES.txt',
    );
    expect(
      text,
      contains('SOFTWARE LICENSE AGREEMENT FOR METAL SHADER CONVERTER'),
    );
    expect(text, contains('Apache License'));
    expect(text.toLowerCase(), contains('acknowledgements'));
  });

  test('the DXBC checksum notices (AMD MIT, RSA MD5) are bundled', () async {
    final text = await rootBundle.loadString(
      'assets/legal/XeniOS-DXBC-notices.txt',
    );
    expect(
      text,
      contains('Copyright (c) 2016-2018 Advanced Micro Devices, Inc.'),
    );
    expect(text, contains('Copyright (C) 1990, RSA Data Security, Inc.'));
    expect(
      text,
      contains('derived from the RSA Data Security, Inc. MD5 Message Digest'),
    );
    expect(text, contains('not identical'));
  });

  test('the legal screen lists both, each with its bundled text', () {
    final source = File(
      'lib/screens/settings_screen/legal_credits_dialog.dart',
    ).readAsStringSync();
    for (final asset in const [
      "'assets/legal/XeniOS-BSD-3-Clause.txt'",
      "'assets/legal/Apple-Metal-Shader-Converter-NOTICES.txt'",
      "'assets/legal/XeniOS-DXBC-notices.txt'",
    ]) {
      expect(source, contains(asset));
    }
    expect(source, contains("'XeniOS (Xenia for iOS)'"));
    expect(source, contains("'https://github.com/xenios-jp/XeniOS'"));
    expect(source, contains('EA1844'));
  });
}
