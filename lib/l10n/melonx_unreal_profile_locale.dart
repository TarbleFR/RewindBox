import 'package:flutter/widgets.dart';

/// Unreal experiment UI in all supported languages; technical CVars stay literal.
abstract final class MelonxUnrealProfileLocale {
  static const values = <String, Map<String, String>>{
  "en": {
    "title": "Unreal Engine experiments",
    "intro": "One setting at a time. These Switch CVars and their loading path are unverified; an installed profile may have no effect. Original game files, saves and other mods remain intact.",
    "project": "Inspected RomFS project: {project}",
    "off": "No experimental profile",
    "quality": "This test changes visual quality.",
    "consent": "Install this unverified experiment for the next launch",
    "removal": "Choosing no profile removes only RewindBox’s verified experiment. Edited files are preserved. Previous experiments are backed up.",
    "close": "Close",
    "apply": "Apply",
    "applying": "Applying…",
    "inspectFailed": "The game’s experimental profile could not be inspected. Check the technical details before trying again.",
    "applyFailed": "The profile change could not be completed. Check the technical details before trying again.",
    "technicalDetails": "Technical details"
  },
  "fr": {
    "title": "Expériences Unreal Engine",
    "intro": "Un réglage à la fois. Ces CVars Switch et leur chargement ne sont pas validés : le profil installé peut rester sans effet. Les fichiers du jeu, sauvegardes et autres mods sont conservés.",
    "project": "Projet RomFS inspecté : {project}",
    "off": "Aucun profil expérimental",
    "quality": "Cet essai modifie la qualité graphique.",
    "consent": "Installer cet essai non validé pour le prochain lancement",
    "removal": "Le choix « Aucun profil » retire uniquement l’essai RewindBox vérifié. Les fichiers modifiés sont préservés. Les essais précédents sont sauvegardés.",
    "close": "Fermer",
    "apply": "Appliquer",
    "applying": "Application…",
    "inspectFailed": "Impossible d’inspecter le profil expérimental du jeu. Consultez les détails techniques avant de réessayer.",
    "applyFailed": "La modification du profil n’a pas pu être terminée. Consultez les détails techniques avant de réessayer.",
    "technicalDetails": "Détails techniques"
  },
  "es": {
    "title": "Experimentos de Unreal Engine",
    "intro": "Un ajuste cada vez. Estas CVars de Switch y su ruta de carga no están verificadas; un perfil instalado puede no tener efecto. Los archivos originales del juego, las partidas y los demás mods se conservan.",
    "project": "Proyecto RomFS inspeccionado: {project}",
    "off": "Sin perfil experimental",
    "quality": "Esta prueba cambia la calidad visual.",
    "consent": "Instalar este experimento no verificado para el próximo inicio",
    "removal": "Elegir ningún perfil retira solo el experimento verificado de RewindBox. Se conservan los archivos editados y una copia de los experimentos anteriores.",
    "close": "Cerrar",
    "apply": "Aplicar",
    "applying": "Aplicando…",
    "inspectFailed": "No se pudo inspeccionar el perfil experimental del juego. Consulta los detalles técnicos antes de volver a intentarlo.",
    "applyFailed": "No se pudo completar el cambio de perfil. Consulta los detalles técnicos antes de volver a intentarlo.",
    "technicalDetails": "Detalles técnicos"
  },
  "ru": {
    "title": "Эксперименты Unreal Engine",
    "intro": "По одной настройке за раз. Поддержка этих CVar на Switch и их загрузка не проверены; установленный профиль может не дать эффекта. Исходные файлы игры, сохранения и другие моды сохраняются.",
    "project": "Проверенный проект RomFS: {project}",
    "off": "Без экспериментального профиля",
    "quality": "Этот тест меняет качество изображения.",
    "consent": "Установить этот непроверенный эксперимент для следующего запуска",
    "removal": "Выбор без профиля удаляет только проверенный эксперимент RewindBox. Изменённые файлы сохраняются. Предыдущие эксперименты остаются в резервных копиях.",
    "close": "Закрыть",
    "apply": "Применить",
    "applying": "Применение…",
    "inspectFailed": "Не удалось проверить экспериментальный профиль игры. Ознакомьтесь с техническими подробностями перед повторной попыткой.",
    "applyFailed": "Не удалось завершить изменение профиля. Ознакомьтесь с техническими подробностями перед повторной попыткой.",
    "technicalDetails": "Технические подробности"
  },
  "zh": {
    "title": "Unreal Engine 实验设置",
    "intro": "每次只测试一个设置。这些 Switch CVar 及其加载路径尚未验证，安装的配置可能不起作用。游戏原始文件、存档和其他模组均会保留。",
    "project": "已检查的 RomFS 项目：{project}",
    "off": "不使用实验配置",
    "quality": "此测试会改变画质。",
    "consent": "为下次启动安装此未经验证的实验设置",
    "removal": "选择不使用配置只会移除已验证归属的 RewindBox 实验设置。已编辑的文件会保留，之前的实验设置会备份。",
    "close": "关闭",
    "apply": "应用",
    "applying": "正在应用…",
    "inspectFailed": "无法检查游戏的实验配置。请先查看技术详情，再重试。",
    "applyFailed": "无法完成配置更改。请先查看技术详情，再重试。",
    "technicalDetails": "技术详情"
  },
  "zh_Hant": {
    "title": "Unreal Engine 實驗設定",
    "intro": "每次只測試一項設定。這些 Switch CVar 及其載入路徑尚未驗證，安裝的設定檔可能不會生效。遊戲原始檔案、存檔及其他模組皆會保留。",
    "project": "已檢查的 RomFS 專案：{project}",
    "off": "不使用實驗設定檔",
    "quality": "此測試會改變畫質。",
    "consent": "為下次啟動安裝這項未經驗證的實驗設定",
    "removal": "選擇不使用設定檔只會移除已驗證歸屬的 RewindBox 實驗設定。已編輯的檔案會保留，先前的實驗設定會備份。",
    "close": "關閉",
    "apply": "套用",
    "applying": "正在套用…",
    "inspectFailed": "無法檢查遊戲的實驗設定檔。請先查看技術詳細資訊，再重試。",
    "applyFailed": "無法完成設定檔變更。請先查看技術詳細資訊，再重試。",
    "technicalDetails": "技術詳細資訊"
  },
  "pt": {
    "title": "Experiências do Unreal Engine",
    "intro": "Uma definição de cada vez. Estas CVars da Switch e o seu carregamento não foram verificados; um perfil instalado pode não ter efeito. Os ficheiros originais do jogo, os dados guardados e os outros mods são preservados.",
    "project": "Projeto RomFS inspecionado: {project}",
    "off": "Sem perfil experimental",
    "quality": "Este teste altera a qualidade visual.",
    "consent": "Instalar esta experiência não verificada para o próximo arranque",
    "removal": "Escolher nenhum perfil remove apenas a experiência verificada do RewindBox. Os ficheiros editados são preservados. As experiências anteriores ficam numa cópia de segurança.",
    "close": "Fechar",
    "apply": "Aplicar",
    "applying": "A aplicar…",
    "inspectFailed": "Não foi possível inspecionar o perfil experimental do jogo. Consulte os detalhes técnicos antes de tentar novamente.",
    "applyFailed": "Não foi possível concluir a alteração do perfil. Consulte os detalhes técnicos antes de tentar novamente.",
    "technicalDetails": "Detalhes técnicos"
  },
  "de": {
    "title": "Unreal-Engine-Experimente",
    "intro": "Jeweils eine Einstellung testen. Diese Switch-CVars und ihr Laden sind nicht bestätigt; ein installiertes Profil kann wirkungslos bleiben. Originale Spieldateien, Spielstände und andere Mods bleiben erhalten.",
    "project": "Geprüftes RomFS-Projekt: {project}",
    "off": "Kein experimentelles Profil",
    "quality": "Dieser Test verändert die Bildqualität.",
    "consent": "Dieses unbestätigte Experiment für den nächsten Start installieren",
    "removal": "Ohne Profil wird nur das geprüfte RewindBox-Experiment entfernt. Bearbeitete Dateien bleiben erhalten. Frühere Experimente werden gesichert.",
    "close": "Schließen",
    "apply": "Anwenden",
    "applying": "Wird angewendet…",
    "inspectFailed": "Das experimentelle Spielprofil konnte nicht geprüft werden. Lies vor einem erneuten Versuch die technischen Details.",
    "applyFailed": "Die Profiländerung konnte nicht abgeschlossen werden. Lies vor einem erneuten Versuch die technischen Details.",
    "technicalDetails": "Technische Details"
  },
  "it": {
    "title": "Esperimenti Unreal Engine",
    "intro": "Un’impostazione alla volta. Queste CVar per Switch e il loro caricamento non sono verificati; un profilo installato potrebbe non avere effetto. I file originali del gioco, i salvataggi e le altre mod vengono conservati.",
    "project": "Progetto RomFS esaminato: {project}",
    "off": "Nessun profilo sperimentale",
    "quality": "Questo test modifica la qualità visiva.",
    "consent": "Installare questo esperimento non verificato per il prossimo avvio",
    "removal": "Scegliere nessun profilo rimuove solo l’esperimento verificato di RewindBox. I file modificati vengono conservati e gli esperimenti precedenti vengono salvati in una copia di sicurezza.",
    "close": "Chiudi",
    "apply": "Applica",
    "applying": "Applicazione…",
    "inspectFailed": "Impossibile esaminare il profilo sperimentale del gioco. Consulta i dettagli tecnici prima di riprovare.",
    "applyFailed": "Impossibile completare la modifica del profilo. Consulta i dettagli tecnici prima di riprovare.",
    "technicalDetails": "Dettagli tecnici"
  },
  "id": {
    "title": "Eksperimen Unreal Engine",
    "intro": "Uji satu pengaturan setiap kali. CVar Switch ini dan jalur pemuatannya belum diverifikasi; profil yang dipasang mungkin tidak berpengaruh. Berkas asli game, simpanan, dan mod lain tetap dipertahankan.",
    "project": "Proyek RomFS yang diperiksa: {project}",
    "off": "Tanpa profil eksperimental",
    "quality": "Uji ini mengubah kualitas visual.",
    "consent": "Pasang eksperimen yang belum diverifikasi ini untuk peluncuran berikutnya",
    "removal": "Memilih tanpa profil hanya menghapus eksperimen RewindBox yang telah diverifikasi. Berkas yang diedit tetap dipertahankan. Eksperimen sebelumnya dicadangkan.",
    "close": "Tutup",
    "apply": "Terapkan",
    "applying": "Menerapkan…",
    "inspectFailed": "Profil eksperimental game tidak dapat diperiksa. Periksa detail teknis sebelum mencoba lagi.",
    "applyFailed": "Perubahan profil tidak dapat diselesaikan. Periksa detail teknis sebelum mencoba lagi.",
    "technicalDetails": "Detail teknis"
  },
  "ja": {
    "title": "Unreal Engine の実験設定",
    "intro": "一度に一つの設定を試します。これらの Switch 用 CVar と読み込み経路は未検証で、プロファイルをインストールしても効果がない場合があります。元のゲームファイル、セーブデータ、他の MOD は保持されます。",
    "project": "確認した RomFS プロジェクト：{project}",
    "off": "実験用プロファイルなし",
    "quality": "このテストは画質を変更します。",
    "consent": "次回起動用にこの未検証の実験設定をインストールする",
    "removal": "プロファイルなしを選ぶと、所有確認済みの RewindBox の実験設定だけを削除します。編集済みファイルは保持され、以前の実験設定はバックアップされます。",
    "close": "閉じる",
    "apply": "適用",
    "applying": "適用中…",
    "inspectFailed": "ゲームの実験用プロファイルを確認できませんでした。技術的な詳細を確認してから、もう一度お試しください。",
    "applyFailed": "プロファイルの変更を完了できませんでした。技術的な詳細を確認してから、もう一度お試しください。",
    "technicalDetails": "技術的な詳細"
  },
  "ko": {
    "title": "Unreal Engine 실험 설정",
    "intro": "한 번에 설정 하나씩 테스트합니다. 이 Switch CVar와 로딩 경로는 검증되지 않았으므로 설치한 프로필이 효과가 없을 수 있습니다. 원본 게임 파일, 저장 데이터와 다른 모드는 유지됩니다.",
    "project": "검사한 RomFS 프로젝트: {project}",
    "off": "실험 프로필 없음",
    "quality": "이 테스트는 화질을 변경합니다.",
    "consent": "다음 실행을 위해 이 미검증 실험 설정 설치",
    "removal": "프로필 없음을 선택하면 소유가 확인된 RewindBox 실험 설정만 제거됩니다. 편집한 파일은 유지되고 이전 실험 설정은 백업됩니다.",
    "close": "닫기",
    "apply": "적용",
    "applying": "적용 중…",
    "inspectFailed": "게임의 실험 프로필을 검사하지 못했습니다. 기술 세부 정보를 확인한 후 다시 시도하세요.",
    "applyFailed": "프로필 변경을 완료하지 못했습니다. 기술 세부 정보를 확인한 후 다시 시도하세요.",
    "technicalDetails": "기술 세부 정보"
  }
};

  static String codeFor(Locale locale) {
    if (locale.languageCode == 'zh_Hant') return 'zh_Hant';
    final traditional = locale.languageCode == 'zh' &&
        (locale.scriptCode?.toLowerCase() == 'hant' ||
            const {'TW', 'HK', 'MO'}.contains(locale.countryCode?.toUpperCase()));
    final code = traditional ? 'zh_Hant' : locale.languageCode;
    return values.containsKey(code) ? code : 'en';
  }

  static String forLocale(Locale locale, String key,
      [Map<String, Object?> parameters = const {}]) {
    var value = values[codeFor(locale)]?[key] ?? values['en']![key] ?? key;
    for (final entry in parameters.entries) {
      value = value.replaceAll('{${entry.key}}', entry.value?.toString() ?? '');
    }
    return value;
  }

  static String text(BuildContext context, String key,
      [Map<String, Object?> parameters = const {}]) =>
      forLocale(Localizations.maybeLocaleOf(context) ?? const Locale('en'), key, parameters);
}
