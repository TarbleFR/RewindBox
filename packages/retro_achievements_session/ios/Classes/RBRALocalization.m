#import "Public/RBRASession.h"

NSString *RBRALocalizedText(NSString *key, NSString *locale) {
  static NSDictionary<NSString *, NSArray<NSString *> *> *messages;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    messages = @{
      @"en": @[@"Unavailable in Hardcore mode", @"Wait before pausing the game in Hardcore mode.", @"Settings in the RetroAchievements tab"],
      @"es": @[@"No disponible en modo Hardcore", @"Espera antes de pausar el juego en modo Hardcore.", @"Ajustes en la pestaña RetroAchievements"],
      @"ru": @[@"Недоступно в режиме Hardcore", @"Подождите, прежде чем приостановить игру в режиме Hardcore.", @"Настройки на вкладке RetroAchievements"],
      @"zh": @[@"Hardcore 模式下不可用", @"请稍候再暂停 Hardcore 模式下的游戏。", @"在 RetroAchievements 标签页中设置"],
      @"zh_Hant": @[@"Hardcore 模式下無法使用", @"請稍候再暫停 Hardcore 模式下的遊戲。", @"在 RetroAchievements 分頁中設定"],
      @"pt": @[@"Indisponível no modo Hardcore", @"Aguarde antes de pausar o jogo no modo Hardcore.", @"Configurações na aba RetroAchievements"],
      @"fr": @[@"Indisponible en mode Hardcore", @"Attendez avant de mettre le jeu en pause en mode Hardcore.", @"Réglages dans l’onglet RetroAchievements"],
      @"de": @[@"Im Hardcore-Modus nicht verfügbar", @"Warte, bevor du das Spiel im Hardcore-Modus pausierst.", @"Einstellungen im Tab RetroAchievements"],
      @"it": @[@"Non disponibile in modalità Hardcore", @"Attendi prima di mettere in pausa il gioco in modalità Hardcore.", @"Impostazioni nella scheda RetroAchievements"],
      @"id": @[@"Tidak tersedia dalam mode Hardcore", @"Tunggu sebelum menjeda game dalam mode Hardcore.", @"Pengaturan di tab RetroAchievements"],
      @"ja": @[@"Hardcore モードでは利用できません", @"Hardcore モードでゲームを一時停止する前にお待ちください。", @"設定は RetroAchievements タブにあります"],
      @"ko": @[@"Hardcore 모드에서는 사용할 수 없습니다", @"Hardcore 모드에서 게임을 일시 정지하기 전에 기다려 주세요.", @"RetroAchievements 탭에서 설정"],
    };
  });
  NSString *tag = [[locale stringByReplacingOccurrencesOfString:@"_" withString:@"-"] lowercaseString];
  NSString *language = [[tag componentsSeparatedByString:@"-"] firstObject] ?: @"en";
  if ([tag hasPrefix:@"zh-hant"] || [tag hasPrefix:@"zh-tw"] || [tag hasPrefix:@"zh-hk"]) language = @"zh_Hant";
  NSArray *labels = messages[language] ?: messages[@"en"];
  if ([key isEqualToString:@"hardcorePause"]) return labels[1];
  if ([key isEqualToString:@"managedInTab"]) return labels[2];
  return labels[0];
}
