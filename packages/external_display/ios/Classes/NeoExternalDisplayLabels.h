// SPDX-License-Identifier: GPL-3.0-or-later
// Native labels of the external display in the twelve supported languages
// (model: DolphinPacingLabels.h). Used by the bridges' in-game status lines
// (`externalOnPhone`) and native mode sheets; the Flutter settings rows use
// lib/l10n/external_display_locale.dart. Parity is checked by
// test/external_display_labels_test.py.
#pragma once
#import <Foundation/Foundation.h>

static NSString *NeoExternalDisplayText(NSString *key, NSString *locale) {
  static NSDictionary<NSString *, NSDictionary<NSString *, NSString *> *> *labels;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    labels = @{
      @"en": @{@"externalOnPhone": @"Game shown on the external display", @"modeAutomatic": @"Automatic", @"modeFit": @"Fit to screen", @"modeFill": @"Fill the screen", @"modeOriginal": @"Original format", @"modeOff": @"Off (mirror the iPhone)"},
      @"es": @{@"externalOnPhone": @"Juego mostrado en la pantalla externa", @"modeAutomatic": @"Automático", @"modeFit": @"Ajustar a la pantalla", @"modeFill": @"Rellenar la pantalla", @"modeOriginal": @"Formato original", @"modeOff": @"Desactivado (duplicar el iPhone)"},
      @"ru": @{@"externalOnPhone": @"Игра отображается на внешнем экране", @"modeAutomatic": @"Автоматически", @"modeFit": @"Вписать в экран", @"modeFill": @"Заполнить экран", @"modeOriginal": @"Исходный формат", @"modeOff": @"Выключено (повтор экрана iPhone)"},
      @"zh": @{@"externalOnPhone": @"游戏显示在外接屏幕上", @"modeAutomatic": @"自动", @"modeFit": @"适应屏幕", @"modeFill": @"填满屏幕", @"modeOriginal": @"原始比例", @"modeOff": @"关闭（镜像 iPhone）"},
      @"zh_Hant": @{@"externalOnPhone": @"遊戲顯示在外接螢幕上", @"modeAutomatic": @"自動", @"modeFit": @"符合螢幕", @"modeFill": @"填滿螢幕", @"modeOriginal": @"原始比例", @"modeOff": @"關閉（鏡像輸出 iPhone）"},
      @"pt": @{@"externalOnPhone": @"Jogo exibido na tela externa", @"modeAutomatic": @"Automático", @"modeFit": @"Ajustar à tela", @"modeFill": @"Preencher a tela", @"modeOriginal": @"Formato original", @"modeOff": @"Desativado (espelhar o iPhone)"},
      @"fr": @{@"externalOnPhone": @"Jeu affiché sur l'écran externe", @"modeAutomatic": @"Automatique", @"modeFit": @"Adapter à l'écran", @"modeFill": @"Remplir l'écran", @"modeOriginal": @"Format d'origine", @"modeOff": @"Désactivé (recopie de l'iPhone)"},
      @"de": @{@"externalOnPhone": @"Spiel wird auf dem externen Bildschirm angezeigt", @"modeAutomatic": @"Automatisch", @"modeFit": @"An Bildschirm anpassen", @"modeFill": @"Bildschirm füllen", @"modeOriginal": @"Originalformat", @"modeOff": @"Aus (iPhone spiegeln)"},
      @"it": @{@"externalOnPhone": @"Gioco mostrato sullo schermo esterno", @"modeAutomatic": @"Automatico", @"modeFit": @"Adatta allo schermo", @"modeFill": @"Riempi lo schermo", @"modeOriginal": @"Formato originale", @"modeOff": @"Disattivato (duplica l'iPhone)"},
      @"id": @{@"externalOnPhone": @"Game ditampilkan di layar eksternal", @"modeAutomatic": @"Otomatis", @"modeFit": @"Sesuaikan dengan layar", @"modeFill": @"Penuhi layar", @"modeOriginal": @"Format asli", @"modeOff": @"Nonaktif (cerminkan iPhone)"},
      @"ja": @{@"externalOnPhone": @"ゲームは外部ディスプレイに表示中", @"modeAutomatic": @"自動", @"modeFit": @"画面に合わせる", @"modeFill": @"画面いっぱいに表示", @"modeOriginal": @"元の形式", @"modeOff": @"オフ（iPhone をミラーリング）"},
      @"ko": @{@"externalOnPhone": @"게임이 외부 디스플레이에 표시됨", @"modeAutomatic": @"자동", @"modeFit": @"화면에 맞추기", @"modeFill": @"화면 채우기", @"modeOriginal": @"원본 형식", @"modeOff": @"끔(iPhone 미러링)"},
    };
  });
  NSString *normalized = [locale.lowercaseString stringByReplacingOccurrencesOfString:@"-" withString:@"_"];
  NSString *language = [normalized componentsSeparatedByString:@"_"].firstObject ?: @"en";
  if ([language isEqualToString:@"zh"] &&
      ([normalized containsString:@"hant"] || [normalized hasSuffix:@"_tw"] || [normalized hasSuffix:@"_hk"] ||
       [normalized hasSuffix:@"_mo"])) {
    language = @"zh_Hant";
  }
  return labels[language][key] ?: labels[@"en"][key] ?: key;
}
