import 'package:flutter/widgets.dart';
import 'melonx_locale.dart';

abstract final class MelonxLaunchFailureLocale {
  static const values = <String, Map<String, String>>{
    "en": {
      "keysMissing":
          "Import your personal prod.keys into Documents/MeloNX/system, then try again.",
      "keysInvalid":
          "The personal key files are invalid. Replace them through the Switch import menu.",
      "missingKey":
          "A key required by this game or revision is missing. Check your personal key export; the technical details name the missing entry.",
      "ncaDecryption":
          "The game could not be decrypted with the installed personal keys. Check that the keys match this game and revision.",
      "firmwareMissing":
          "No readable Switch firmware was recognized. Import your own compatible firmware, then try again.",
      "jitUnavailable":
          "JIT could not be authorized for RewindBox. Check the selected JIT method and LocalDevVPN if used, then try again.",
      "invalidContent":
          "The local game content could not be validated. See the technical details; your imported files have been preserved.",
      "quarantined":
          "MeloNX could not confirm a safe shutdown. Close and reopen RewindBox before trying again; its native resources remain protected.",
    },
    "fr": {
      "keysMissing":
          "Importez votre fichier personnel prod.keys dans Documents/MeloNX/system, puis réessayez.",
      "keysInvalid":
          "Les fichiers de clés personnels sont invalides. Remplacez-les depuis le menu d’importation Switch.",
      "missingKey":
          "Une clé nécessaire à ce jeu ou à sa révision est absente. Vérifiez votre export personnel ; l’entrée manquante est indiquée dans les détails techniques.",
      "ncaDecryption":
          "Le jeu ne peut pas être déchiffré avec les clés personnelles installées. Vérifiez leur compatibilité avec ce jeu et sa révision.",
      "firmwareMissing":
          "Aucun firmware Switch lisible n’a été reconnu. Importez votre propre firmware compatible, puis réessayez.",
      "jitUnavailable":
          "Le JIT n’a pas pu être autorisé pour RewindBox. Vérifiez la méthode JIT choisie et LocalDevVPN si vous l’utilisez, puis réessayez.",
      "invalidContent":
          "Le contenu du jeu local n’a pas pu être validé. Consultez les détails techniques ; vos fichiers importés sont conservés.",
      "quarantined":
          "MeloNX n’a pas confirmé un arrêt sûr. Fermez puis rouvrez RewindBox avant de réessayer ; ses ressources natives restent protégées.",
    },
    "es": {
      "keysMissing":
          "Importa tu archivo personal prod.keys en Documents/MeloNX/system y vuelve a intentarlo.",
      "keysInvalid":
          "Los archivos de claves personales no son válidos. Sustitúyelos desde el menú de importación de Switch.",
      "missingKey":
          "Falta una clave necesaria para este juego o revisión. Comprueba tu exportación personal; los detalles técnicos indican la entrada que falta.",
      "ncaDecryption":
          "No se pudo descifrar el juego con las claves personales instaladas. Comprueba que correspondan a este juego y revisión.",
      "firmwareMissing":
          "No se reconoció un firmware de Switch legible. Importa tu propio firmware compatible y vuelve a intentarlo.",
      "jitUnavailable":
          "No se pudo autorizar JIT para RewindBox. Comprueba el método JIT elegido y LocalDevVPN si lo usas.",
      "invalidContent":
          "No se pudo validar el contenido local del juego. Consulta los detalles técnicos; se han conservado tus archivos importados.",
      "quarantined":
          "MeloNX no pudo confirmar un cierre seguro. Cierra y vuelve a abrir RewindBox antes de reintentar; sus recursos nativos siguen protegidos.",
    },
    "de": {
      "keysMissing":
          "Importiere deine persönliche prod.keys in Documents/MeloNX/system und versuche es erneut.",
      "keysInvalid":
          "Die persönlichen Schlüsseldateien sind ungültig. Ersetze sie über das Switch-Importmenü.",
      "missingKey":
          "Ein für dieses Spiel oder diese Version erforderlicher Schlüssel fehlt. Prüfe deinen eigenen Export; die technischen Details nennen den fehlenden Eintrag.",
      "ncaDecryption":
          "Das Spiel konnte mit den installierten persönlichen Schlüsseln nicht entschlüsselt werden. Prüfe ihre Kompatibilität mit Spiel und Version.",
      "firmwareMissing":
          "Keine lesbare Switch-Firmware erkannt. Importiere deine eigene kompatible Firmware und versuche es erneut.",
      "jitUnavailable":
          "JIT konnte für RewindBox nicht autorisiert werden. Prüfe die gewählte JIT-Methode und gegebenenfalls LocalDevVPN.",
      "invalidContent":
          "Der lokale Spielinhalt konnte nicht geprüft werden. Siehe technische Details; deine importierten Dateien bleiben erhalten.",
      "quarantined":
          "MeloNX konnte das sichere Beenden nicht bestätigen. Schließe und öffne RewindBox vor einem neuen Versuch; die nativen Ressourcen bleiben geschützt.",
    },
    "it": {
      "keysMissing":
          "Importa il tuo file personale prod.keys in Documents/MeloNX/system e riprova.",
      "keysInvalid":
          "I file delle chiavi personali non sono validi. Sostituiscili dal menu di importazione Switch.",
      "missingKey":
          "Manca una chiave necessaria per questo gioco o revisione. Verifica la tua esportazione personale; i dettagli tecnici indicano la voce mancante.",
      "ncaDecryption":
          "Il gioco non può essere decifrato con le chiavi personali installate. Verifica che corrispondano al gioco e alla revisione.",
      "firmwareMissing":
          "Nessun firmware Switch leggibile riconosciuto. Importa il tuo firmware compatibile e riprova.",
      "jitUnavailable":
          "Impossibile autorizzare JIT per RewindBox. Controlla il metodo JIT scelto e LocalDevVPN, se utilizzato.",
      "invalidContent":
          "Impossibile verificare il contenuto locale del gioco. Consulta i dettagli tecnici; i file importati sono stati conservati.",
      "quarantined":
          "MeloNX non ha confermato un arresto sicuro. Chiudi e riapri RewindBox prima di riprovare; le risorse native restano protette.",
    },
    "pt": {
      "keysMissing":
          "Importe o seu ficheiro pessoal prod.keys para Documents/MeloNX/system e tente novamente.",
      "keysInvalid":
          "Os ficheiros de chaves pessoais são inválidos. Substitua-os no menu de importação Switch.",
      "missingKey":
          "Falta uma chave necessária para este jogo ou revisão. Verifique a sua exportação pessoal; os detalhes técnicos identificam a entrada em falta.",
      "ncaDecryption":
          "Não foi possível decifrar o jogo com as chaves pessoais instaladas. Verifique a compatibilidade com o jogo e a revisão.",
      "firmwareMissing":
          "Não foi reconhecido firmware Switch legível. Importe o seu próprio firmware compatível e tente novamente.",
      "jitUnavailable":
          "Não foi possível autorizar JIT para RewindBox. Verifique o método JIT escolhido e o LocalDevVPN, se utilizado.",
      "invalidContent":
          "Não foi possível validar o conteúdo local do jogo. Consulte os detalhes técnicos; os ficheiros importados foram preservados.",
      "quarantined":
          "O MeloNX não confirmou um encerramento seguro. Feche e reabra o RewindBox antes de tentar novamente; os recursos nativos continuam protegidos.",
    },
    "ru": {
      "keysMissing":
          "Импортируйте свой prod.keys в Documents/MeloNX/system и повторите попытку.",
      "keysInvalid":
          "Личные файлы ключей недействительны. Замените их через меню импорта Switch.",
      "missingKey":
          "Отсутствует ключ, необходимый для этой игры или версии. Проверьте свой экспорт; имя ключа указано в технических подробностях.",
      "ncaDecryption":
          "Не удалось расшифровать игру установленными личными ключами. Проверьте их совместимость с игрой и версией.",
      "firmwareMissing":
          "Не найдена читаемая прошивка Switch. Импортируйте свою совместимую прошивку и повторите попытку.",
      "jitUnavailable":
          "Не удалось разрешить JIT для RewindBox. Проверьте выбранный метод JIT и LocalDevVPN, если он используется.",
      "invalidContent":
          "Не удалось проверить локальные файлы игры. См. технические подробности; импортированные файлы сохранены.",
      "quarantined":
          "MeloNX не подтвердил безопасное завершение. Закройте и снова откройте RewindBox; нативные ресурсы остаются защищёнными.",
    },
    "id": {
      "keysMissing":
          "Impor prod.keys pribadi Anda ke Documents/MeloNX/system, lalu coba lagi.",
      "keysInvalid":
          "File kunci pribadi tidak valid. Ganti melalui menu impor Switch.",
      "missingKey":
          "Kunci yang diperlukan game atau revisi ini tidak ditemukan. Periksa ekspor pribadi Anda; detail teknis menyebutkan entri yang hilang.",
      "ncaDecryption":
          "Game tidak dapat didekripsi dengan kunci pribadi yang terpasang. Periksa kecocokannya dengan game dan revisi ini.",
      "firmwareMissing":
          "Firmware Switch yang dapat dibaca tidak ditemukan. Impor firmware kompatibel milik Anda, lalu coba lagi.",
      "jitUnavailable":
          "JIT tidak dapat diizinkan untuk RewindBox. Periksa metode JIT yang dipilih dan LocalDevVPN jika digunakan.",
      "invalidContent":
          "Konten game lokal tidak dapat divalidasi. Lihat detail teknis; file impor Anda tetap disimpan.",
      "quarantined":
          "MeloNX tidak dapat memastikan penghentian yang aman. Tutup dan buka kembali RewindBox; sumber daya native tetap dilindungi.",
    },
    "ja": {
      "keysMissing":
          "個人のprod.keysをDocuments/MeloNX/systemにインポートして、もう一度お試しください。",
      "keysInvalid": "個人のキーのファイルが無効です。Switchのインポートメニューから置き換えてください。",
      "missingKey":
          "このゲームまたはリビジョンに必要なキーがありません。個人のエクスポートを確認してください。不足する項目は技術情報に表示されます。",
      "ncaDecryption": "インストール済みの個人のキーではゲームを復号できません。ゲームとリビジョンに対応しているか確認してください。",
      "firmwareMissing":
          "読み取り可能なSwitchファームウェアが認識されませんでした。ご自身の互換ファームウェアをインポートしてください。",
      "jitUnavailable":
          "RewindBoxのJITを許可できませんでした。選択したJIT方式と、使用している場合はLocalDevVPNを確認してください。",
      "invalidContent":
          "ローカルのゲーム内容を検証できませんでした。技術情報を確認してください。インポート済みファイルは保持されています。",
      "quarantined":
          "MeloNXの安全な停止を確認できませんでした。RewindBoxを閉じて開き直してください。ネイティブリソースは保護されたままです。",
    },
    "ko": {
      "keysMissing": "개인 prod.keys를 Documents/MeloNX/system으로 가져온 뒤 다시 시도하세요.",
      "keysInvalid": "개인 키 파일이 올바르지 않습니다. Switch 가져오기 메뉴에서 교체하세요.",
      "missingKey":
          "이 게임 또는 버전에 필요한 키가 없습니다. 개인 내보내기 파일을 확인하세요. 기술 정보에 누락된 항목이 표시됩니다.",
      "ncaDecryption": "설치된 개인 키로 게임을 복호화할 수 없습니다. 게임 및 버전과 호환되는지 확인하세요.",
      "firmwareMissing": "읽을 수 있는 Switch 펌웨어가 인식되지 않았습니다. 본인의 호환 펌웨어를 가져오세요.",
      "jitUnavailable":
          "RewindBox의 JIT를 승인할 수 없습니다. 선택한 JIT 방식과 사용 중인 경우 LocalDevVPN을 확인하세요.",
      "invalidContent": "로컬 게임 콘텐츠를 검증할 수 없습니다. 기술 정보를 확인하세요. 가져온 파일은 보존됩니다.",
      "quarantined":
          "MeloNX의 안전한 종료를 확인하지 못했습니다. RewindBox를 닫고 다시 여세요. 네이티브 리소스는 계속 보호됩니다.",
    },
    "zh": {
      "keysMissing": "请将个人 prod.keys 导入 Documents/MeloNX/system，然后重试。",
      "keysInvalid": "个人密钥文件无效。请通过 Switch 导入菜单替换。",
      "missingKey": "缺少此游戏或版本所需的密钥。请检查个人导出文件；技术详情会指出缺少的条目。",
      "ncaDecryption": "无法使用已安装的个人密钥解密游戏。请检查其是否与游戏及版本匹配。",
      "firmwareMissing": "未识别到可读取的 Switch 固件。请导入您自己的兼容固件后重试。",
      "jitUnavailable": "无法为 RewindBox 授权 JIT。请检查所选 JIT 方式及使用中的 LocalDevVPN。",
      "invalidContent": "无法验证本地游戏内容。请查看技术详情；已导入的文件会保留。",
      "quarantined": "MeloNX 无法确认已安全停止。请关闭并重新打开 RewindBox；原生资源将继续受到保护。",
    },
    "zh_Hant": {
      "keysMissing": "請將個人 prod.keys 匯入 Documents/MeloNX/system，然後重試。",
      "keysInvalid": "個人金鑰檔案無效。請透過 Switch 匯入選單替換。",
      "missingKey": "缺少此遊戲或版本所需的金鑰。請檢查個人匯出檔案；技術詳情會指出缺少的項目。",
      "ncaDecryption": "無法使用已安裝的個人金鑰解密遊戲。請檢查其是否與遊戲及版本相符。",
      "firmwareMissing": "未辨識到可讀取的 Switch 韌體。請匯入您自己的相容韌體後重試。",
      "jitUnavailable": "無法為 RewindBox 授權 JIT。請檢查所選 JIT 方式及使用中的 LocalDevVPN。",
      "invalidContent": "無法驗證本機遊戲內容。請查看技術詳情；已匯入的檔案會保留。",
      "quarantined": "MeloNX 無法確認已安全停止。請關閉並重新開啟 RewindBox；原生資源將繼續受到保護。",
    },
  };
  static String text(Locale locale, String key) {
    final traditional =
        locale.languageCode == 'zh' &&
        (locale.scriptCode == 'Hant' ||
            const {'TW', 'HK', 'MO'}.contains(locale.countryCode));
    final messages =
        values[traditional ? 'zh_Hant' : locale.languageCode] ?? values['en']!;
    return messages[key] ?? MelonxLocale.forLocale(locale, 'launchFailed');
  }
}
