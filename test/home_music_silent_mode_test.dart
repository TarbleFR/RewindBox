import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Build 448 replaced the main-menu-only music by the frontend-wide ambient
/// music. The former contract — Themes reported "not the main menu" before
/// initialization so that entering the panel could not restart the menu
/// music (`_mainMenuActive = value;` before `if (!_initialized)`, and
/// `homeMusic.setMainMenuActive(false)` in Themes) — is retired with that
/// gating: the ambience now plays in every section, Themes included, and
/// its behavior is tested in ambient_music_service_test.dart.
///
/// What stays: the silent-mode policy. The ambience starts through the SFX
/// engine path, reasserts NeoStation's `.ambient` category at each start,
/// and never arbitrates the audio session itself.
void main() {
  test('the ambient music keeps the silent-mode audio policy', () {
    final ambient = File(
      'lib/services/home_music_service.dart',
    ).readAsStringSync();

    expect(ambient, contains('await SfxService().init();'));
    expect(ambient, contains('SoLoud.instance.play('));
    expect(ambient, contains('AudioPolicyService'));
    expect(ambient, contains("reason: 'main-menu-music'"));
    expect(ambient, isNot(contains('prepareForPlayback')));
    expect(ambient, isNot(contains('afterPlaybackStarted')));
    expect(ambient, isNot(contains('mixWithOthers')));
    // The policy is reasserted before the voice is created, at every start.
    final policy = ambient.indexOf("reason: 'main-menu-music'");
    final prepare = ambient.indexOf('await _backend.prepareEngine();');
    final play = ambient.indexOf('_backend.play(source');
    expect(policy, greaterThanOrEqualTo(0));
    expect(prepare, greaterThan(0));
    expect(play, greaterThan(prepare));

    // Themes no longer gates the music: it only reads the stored track.
    final themeSettings = File(
      'lib/screens/settings_screen/new_settings_options/'
      'themes_settings_content.dart',
    ).readAsStringSync();
    expect(themeSettings, isNot(contains('setMainMenuActive')));
    expect(themeSettings, contains('homeMusic.init()'));

    final sfx = File('lib/services/sfx_service.dart').readAsStringSync();
    expect(sfx, contains('SoLoud.instance.play(source, volume: _volume);'));
    expect(sfx, isNot(contains('_sfxStartSerial')));
  });
}
