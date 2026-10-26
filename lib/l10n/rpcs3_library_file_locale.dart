import 'package:flutter/widgets.dart';

import '../services/rpcs3_library_file_service.dart';

/// Texts of the installation of a library-folder PS3 disc image into RPCS3
/// before its first launch (Build 554). File names, sizes and RPCS3's own
/// messages are shown apart from these texts, untranslated.
abstract final class Rpcs3LibraryFileLocale {
  static const Map<String, Map<String, String>>
  values = <String, Map<String, String>>{
    'en': {
      'promptTitle': 'Install this game in RPCS3?',
      'promptBody':
          'RPCS3 runs PS3 games from its own library. Before the first launch, RewindBox copies “{file}” ({size}) into it, which needs as much free space.',
      'promptKey': 'Disc key found: {key}',
      'promptFreeSpace': 'Then delete the original file to free {size}',
      'promptFreeSpaceKey':
          'Then delete the original file and its disc key to free {size}',
      'promptCancel': 'Cancel',
      'promptInstall': 'Install and play',
      'progressTitle': 'Installing in RPCS3',
      'progressPreparing': 'Preparing RPCS3…',
      'progressKeepOpen':
          'Keep RewindBox open until the installation finishes.',
      'failFirmware':
          'Install the PS3 firmware first: open the PS3 library in RewindBox and follow the firmware step.',
      'failSpace':
          'Not enough free space to copy this game into RPCS3. Free up space on the iPhone, then launch the game again.',
      'failKey':
          'This disc image appears to be encrypted. Put its disc key (.dkey or .key, with the same name as the ISO) in the same folder, then launch the game again.',
      'failCorrupt':
          'This disc image is incomplete or damaged. Copy it again, then launch the game again.',
      'failUnidentified':
          'The game was installed in RPCS3, but RewindBox could not identify it. Launch it from the PS3 library.',
      'failGeneric': 'RPCS3 could not install this game.',
    },
    'fr': {
      'promptTitle': 'Installer ce jeu dans RPCS3 ?',
      'promptBody':
          'RPCS3 lance les jeux PS3 depuis sa propre bibliothèque. Avant le premier lancement, RewindBox y copie « {file} » ({size}) : il faut autant d’espace libre.',
      'promptKey': 'Clé de disque trouvée : {key}',
      'promptFreeSpace':
          'Supprimer ensuite le fichier d’origine pour libérer {size}',
      'promptFreeSpaceKey':
          'Supprimer ensuite le fichier d’origine et sa clé de disque pour libérer {size}',
      'promptCancel': 'Annuler',
      'promptInstall': 'Installer et jouer',
      'progressTitle': 'Installation dans RPCS3',
      'progressPreparing': 'Préparation de RPCS3…',
      'progressKeepOpen':
          'Gardez RewindBox ouvert jusqu’à la fin de l’installation.',
      'failFirmware':
          'Installez d’abord le firmware PS3 : ouvrez la bibliothèque PS3 de RewindBox et suivez l’étape du firmware.',
      'failSpace':
          'Espace libre insuffisant pour copier ce jeu dans RPCS3. Libérez de l’espace sur l’iPhone, puis relancez le jeu.',
      'failKey':
          'Cette image disque semble chiffrée. Placez sa clé de disque (.dkey ou .key, du même nom que l’ISO) dans le même dossier, puis relancez le jeu.',
      'failCorrupt':
          'Cette image disque est incomplète ou endommagée. Copiez-la de nouveau, puis relancez le jeu.',
      'failUnidentified':
          'Le jeu a été installé dans RPCS3, mais RewindBox n’a pas pu l’identifier. Lancez-le depuis la bibliothèque PS3.',
      'failGeneric': 'RPCS3 n’a pas pu installer ce jeu.',
    },
    'de': {
      'promptTitle': 'Dieses Spiel in RPCS3 installieren?',
      'promptBody':
          'RPCS3 startet PS3-Spiele aus seiner eigenen Bibliothek. Vor dem ersten Start kopiert RewindBox „{file}“ ({size}) dorthin; dafür wird genauso viel freier Speicher benötigt.',
      'promptKey': 'Disc-Schlüssel gefunden: {key}',
      'promptFreeSpace':
          'Danach die Originaldatei löschen, um {size} freizugeben',
      'promptFreeSpaceKey':
          'Danach die Originaldatei und ihren Disc-Schlüssel löschen, um {size} freizugeben',
      'promptCancel': 'Abbrechen',
      'promptInstall': 'Installieren und spielen',
      'progressTitle': 'Installation in RPCS3',
      'progressPreparing': 'RPCS3 wird vorbereitet…',
      'progressKeepOpen':
          'Lass RewindBox geöffnet, bis die Installation abgeschlossen ist.',
      'failFirmware':
          'Installiere zuerst die PS3-Firmware: Öffne die PS3-Bibliothek in RewindBox und folge dem Firmware-Schritt.',
      'failSpace':
          'Nicht genug freier Speicher, um dieses Spiel in RPCS3 zu kopieren. Gib Speicher auf dem iPhone frei und starte das Spiel erneut.',
      'failKey':
          'Dieses Disc-Image scheint verschlüsselt zu sein. Lege seinen Disc-Schlüssel (.dkey oder .key, mit demselben Namen wie die ISO) in denselben Ordner und starte das Spiel erneut.',
      'failCorrupt':
          'Dieses Disc-Image ist unvollständig oder beschädigt. Kopiere es erneut und starte das Spiel dann noch einmal.',
      'failUnidentified':
          'Das Spiel wurde in RPCS3 installiert, aber RewindBox konnte es nicht erkennen. Starte es aus der PS3-Bibliothek.',
      'failGeneric': 'RPCS3 konnte dieses Spiel nicht installieren.',
    },
    'es': {
      'promptTitle': '¿Instalar este juego en RPCS3?',
      'promptBody':
          'RPCS3 ejecuta los juegos de PS3 desde su propia biblioteca. Antes del primer inicio, RewindBox copia «{file}» ({size}) en ella, lo que requiere el mismo espacio libre.',
      'promptKey': 'Clave de disco encontrada: {key}',
      'promptFreeSpace':
          'Después, eliminar el archivo original para liberar {size}',
      'promptFreeSpaceKey':
          'Después, eliminar el archivo original y su clave de disco para liberar {size}',
      'promptCancel': 'Cancelar',
      'promptInstall': 'Instalar y jugar',
      'progressTitle': 'Instalando en RPCS3',
      'progressPreparing': 'Preparando RPCS3…',
      'progressKeepOpen':
          'Mantén RewindBox abierto hasta que termine la instalación.',
      'failFirmware':
          'Instala primero el firmware de PS3: abre la biblioteca de PS3 en RewindBox y sigue el paso del firmware.',
      'failSpace':
          'No hay espacio libre suficiente para copiar este juego en RPCS3. Libera espacio en el iPhone y vuelve a iniciar el juego.',
      'failKey':
          'Esta imagen de disco parece cifrada. Coloca su clave de disco (.dkey o .key, con el mismo nombre que la ISO) en la misma carpeta y vuelve a iniciar el juego.',
      'failCorrupt':
          'Esta imagen de disco está incompleta o dañada. Cópiala de nuevo y vuelve a iniciar el juego.',
      'failUnidentified':
          'El juego se instaló en RPCS3, pero RewindBox no pudo identificarlo. Inícialo desde la biblioteca de PS3.',
      'failGeneric': 'RPCS3 no pudo instalar este juego.',
    },
    'it': {
      'promptTitle': 'Installare questo gioco in RPCS3?',
      'promptBody':
          'RPCS3 avvia i giochi PS3 dalla propria libreria. Prima del primo avvio, RewindBox vi copia «{file}» ({size}): serve altrettanto spazio libero.',
      'promptKey': 'Chiave del disco trovata: {key}',
      'promptFreeSpace': 'Poi elimina il file originale per liberare {size}',
      'promptFreeSpaceKey':
          'Poi elimina il file originale e la sua chiave del disco per liberare {size}',
      'promptCancel': 'Annulla',
      'promptInstall': 'Installa e gioca',
      'progressTitle': 'Installazione in RPCS3',
      'progressPreparing': 'Preparazione di RPCS3…',
      'progressKeepOpen':
          'Tieni aperto RewindBox fino al termine dell’installazione.',
      'failFirmware':
          'Installa prima il firmware PS3: apri la libreria PS3 in RewindBox e segui il passaggio del firmware.',
      'failSpace':
          'Spazio libero insufficiente per copiare questo gioco in RPCS3. Libera spazio sull’iPhone, poi riavvia il gioco.',
      'failKey':
          'Questa immagine disco sembra cifrata. Metti la sua chiave del disco (.dkey o .key, con lo stesso nome della ISO) nella stessa cartella, poi riavvia il gioco.',
      'failCorrupt':
          'Questa immagine disco è incompleta o danneggiata. Copiala di nuovo, poi riavvia il gioco.',
      'failUnidentified':
          'Il gioco è stato installato in RPCS3, ma RewindBox non è riuscito a identificarlo. Avvialo dalla libreria PS3.',
      'failGeneric': 'RPCS3 non è riuscito a installare questo gioco.',
    },
    'pt': {
      'promptTitle': 'Instalar este jogo no RPCS3?',
      'promptBody':
          'O RPCS3 executa os jogos de PS3 a partir da própria biblioteca. Antes da primeira execução, o RewindBox copia “{file}” ({size}) para ela, o que exige o mesmo espaço livre.',
      'promptKey': 'Chave do disco encontrada: {key}',
      'promptFreeSpace':
          'Depois, apagar o arquivo original para liberar {size}',
      'promptFreeSpaceKey':
          'Depois, apagar o arquivo original e a chave do disco para liberar {size}',
      'promptCancel': 'Cancelar',
      'promptInstall': 'Instalar e jogar',
      'progressTitle': 'Instalando no RPCS3',
      'progressPreparing': 'Preparando o RPCS3…',
      'progressKeepOpen':
          'Mantenha o RewindBox aberto até o fim da instalação.',
      'failFirmware':
          'Instale primeiro o firmware do PS3: abra a biblioteca de PS3 no RewindBox e siga a etapa do firmware.',
      'failSpace':
          'Não há espaço livre suficiente para copiar este jogo para o RPCS3. Libere espaço no iPhone e inicie o jogo novamente.',
      'failKey':
          'Esta imagem de disco parece estar criptografada. Coloque a chave do disco (.dkey ou .key, com o mesmo nome da ISO) na mesma pasta e inicie o jogo novamente.',
      'failCorrupt':
          'Esta imagem de disco está incompleta ou danificada. Copie-a novamente e inicie o jogo outra vez.',
      'failUnidentified':
          'O jogo foi instalado no RPCS3, mas o RewindBox não conseguiu identificá-lo. Inicie-o pela biblioteca de PS3.',
      'failGeneric': 'O RPCS3 não conseguiu instalar este jogo.',
    },
    'ru': {
      'promptTitle': 'Установить эту игру в RPCS3?',
      'promptBody':
          'RPCS3 запускает игры PS3 из собственной библиотеки. Перед первым запуском RewindBox копирует туда «{file}» ({size}), для этого нужно столько же свободного места.',
      'promptKey': 'Найден ключ диска: {key}',
      'promptFreeSpace': 'Затем удалить исходный файл, чтобы освободить {size}',
      'promptFreeSpaceKey':
          'Затем удалить исходный файл и его ключ диска, чтобы освободить {size}',
      'promptCancel': 'Отмена',
      'promptInstall': 'Установить и играть',
      'progressTitle': 'Установка в RPCS3',
      'progressPreparing': 'Подготовка RPCS3…',
      'progressKeepOpen': 'Не закрывайте RewindBox до завершения установки.',
      'failFirmware':
          'Сначала установите прошивку PS3: откройте библиотеку PS3 в RewindBox и выполните шаг установки прошивки.',
      'failSpace':
          'Недостаточно свободного места, чтобы скопировать эту игру в RPCS3. Освободите место на iPhone и запустите игру снова.',
      'failKey':
          'Похоже, этот образ диска зашифрован. Положите его ключ диска (.dkey или .key, с тем же именем, что и ISO) в ту же папку и запустите игру снова.',
      'failCorrupt':
          'Этот образ диска неполный или повреждён. Скопируйте его заново и запустите игру снова.',
      'failUnidentified':
          'Игра установлена в RPCS3, но RewindBox не удалось её определить. Запустите её из библиотеки PS3.',
      'failGeneric': 'RPCS3 не удалось установить эту игру.',
    },
    'id': {
      'promptTitle': 'Pasang game ini di RPCS3?',
      'promptBody':
          'RPCS3 menjalankan game PS3 dari pustakanya sendiri. Sebelum peluncuran pertama, RewindBox menyalin “{file}” ({size}) ke sana, sehingga dibutuhkan ruang kosong sebesar itu.',
      'promptKey': 'Kunci disk ditemukan: {key}',
      'promptFreeSpace': 'Lalu hapus berkas asli untuk mengosongkan {size}',
      'promptFreeSpaceKey':
          'Lalu hapus berkas asli dan kunci disknya untuk mengosongkan {size}',
      'promptCancel': 'Batal',
      'promptInstall': 'Pasang dan mainkan',
      'progressTitle': 'Memasang di RPCS3',
      'progressPreparing': 'Menyiapkan RPCS3…',
      'progressKeepOpen':
          'Biarkan RewindBox tetap terbuka sampai pemasangan selesai.',
      'failFirmware':
          'Pasang firmware PS3 terlebih dahulu: buka pustaka PS3 di RewindBox dan ikuti langkah firmware.',
      'failSpace':
          'Ruang kosong tidak cukup untuk menyalin game ini ke RPCS3. Kosongkan ruang di iPhone, lalu jalankan game lagi.',
      'failKey':
          'Image disk ini tampaknya terenkripsi. Letakkan kunci disknya (.dkey atau .key, dengan nama yang sama seperti ISO) di folder yang sama, lalu jalankan game lagi.',
      'failCorrupt':
          'Image disk ini tidak lengkap atau rusak. Salin ulang, lalu jalankan game lagi.',
      'failUnidentified':
          'Game sudah dipasang di RPCS3, tetapi RewindBox tidak dapat mengenalinya. Jalankan dari pustaka PS3.',
      'failGeneric': 'RPCS3 tidak dapat memasang game ini.',
    },
    'ja': {
      'promptTitle': 'このゲームを RPCS3 にインストールしますか？',
      'promptBody':
          'RPCS3 は自身のライブラリから PS3 ゲームを起動します。初回起動の前に、RewindBox が「{file}」（{size}）をそこへコピーするため、同じ容量の空き領域が必要です。',
      'promptKey': 'ディスクキーが見つかりました：{key}',
      'promptFreeSpace': 'インストール後に元のファイルを削除して {size} を空ける',
      'promptFreeSpaceKey': 'インストール後に元のファイルとディスクキーを削除して {size} を空ける',
      'promptCancel': 'キャンセル',
      'promptInstall': 'インストールしてプレイ',
      'progressTitle': 'RPCS3 にインストール中',
      'progressPreparing': 'RPCS3 を準備しています…',
      'progressKeepOpen': 'インストールが終わるまで RewindBox を開いたままにしてください。',
      'failFirmware':
          '先に PS3 ファームウェアをインストールしてください。RewindBox の PS3 ライブラリを開き、ファームウェアの手順に従ってください。',
      'failSpace':
          'このゲームを RPCS3 にコピーするための空き領域が足りません。iPhone の空き領域を増やしてから、もう一度ゲームを起動してください。',
      'failKey':
          'このディスクイメージは暗号化されているようです。ISO と同じ名前のディスクキー（.dkey または .key）を同じフォルダに置いてから、もう一度ゲームを起動してください。',
      'failCorrupt': 'このディスクイメージは不完全か破損しています。もう一度コピーしてから、ゲームを再度起動してください。',
      'failUnidentified':
          'ゲームは RPCS3 にインストールされましたが、RewindBox が識別できませんでした。PS3 ライブラリから起動してください。',
      'failGeneric': 'RPCS3 はこのゲームをインストールできませんでした。',
    },
    'ko': {
      'promptTitle': '이 게임을 RPCS3에 설치할까요?',
      'promptBody':
          'RPCS3는 자체 라이브러리에서 PS3 게임을 실행합니다. 처음 실행하기 전에 RewindBox가 “{file}”({size})을(를) 그곳에 복사하므로 같은 크기의 여유 공간이 필요합니다.',
      'promptKey': '디스크 키를 찾았습니다: {key}',
      'promptFreeSpace': '설치 후 원본 파일을 삭제하여 {size} 확보',
      'promptFreeSpaceKey': '설치 후 원본 파일과 디스크 키를 삭제하여 {size} 확보',
      'promptCancel': '취소',
      'promptInstall': '설치하고 플레이',
      'progressTitle': 'RPCS3에 설치 중',
      'progressPreparing': 'RPCS3 준비 중…',
      'progressKeepOpen': '설치가 끝날 때까지 RewindBox를 열어 두세요.',
      'failFirmware':
          '먼저 PS3 펌웨어를 설치하세요. RewindBox의 PS3 라이브러리를 열고 펌웨어 단계를 따르세요.',
      'failSpace':
          '이 게임을 RPCS3에 복사할 여유 공간이 부족합니다. iPhone의 공간을 확보한 뒤 게임을 다시 실행하세요.',
      'failKey':
          '이 디스크 이미지는 암호화된 것으로 보입니다. ISO와 같은 이름의 디스크 키(.dkey 또는 .key)를 같은 폴더에 넣은 뒤 게임을 다시 실행하세요.',
      'failCorrupt': '이 디스크 이미지는 불완전하거나 손상되었습니다. 다시 복사한 뒤 게임을 다시 실행하세요.',
      'failUnidentified':
          '게임이 RPCS3에 설치되었지만 RewindBox가 식별하지 못했습니다. PS3 라이브러리에서 실행하세요.',
      'failGeneric': 'RPCS3가 이 게임을 설치하지 못했습니다.',
    },
    'zh': {
      'promptTitle': '要将此游戏安装到 RPCS3 吗？',
      'promptBody':
          'RPCS3 从自己的游戏库运行 PS3 游戏。首次启动前，RewindBox 会将“{file}”（{size}）复制到该库中，因此需要同样大小的可用空间。',
      'promptKey': '已找到光盘密钥：{key}',
      'promptFreeSpace': '安装后删除原始文件，释放 {size}',
      'promptFreeSpaceKey': '安装后删除原始文件及其光盘密钥，释放 {size}',
      'promptCancel': '取消',
      'promptInstall': '安装并开始游戏',
      'progressTitle': '正在安装到 RPCS3',
      'progressPreparing': '正在准备 RPCS3…',
      'progressKeepOpen': '安装完成前请保持 RewindBox 打开。',
      'failFirmware': '请先安装 PS3 固件：在 RewindBox 中打开 PS3 游戏库，并按照固件步骤操作。',
      'failSpace': '可用空间不足，无法将此游戏复制到 RPCS3。请释放 iPhone 空间后重新启动游戏。',
      'failKey': '此光盘映像似乎已加密。请将其光盘密钥（.dkey 或 .key，与 ISO 同名）放在同一文件夹中，然后重新启动游戏。',
      'failCorrupt': '此光盘映像不完整或已损坏。请重新复制后再启动游戏。',
      'failUnidentified': '游戏已安装到 RPCS3，但 RewindBox 无法识别它。请从 PS3 游戏库启动。',
      'failGeneric': 'RPCS3 无法安装此游戏。',
    },
    'zh_Hant': {
      'promptTitle': '要將此遊戲安裝到 RPCS3 嗎？',
      'promptBody':
          'RPCS3 從自己的遊戲庫執行 PS3 遊戲。首次啟動前，RewindBox 會將「{file}」（{size}）複製到該庫中，因此需要同樣大小的可用空間。',
      'promptKey': '已找到光碟金鑰：{key}',
      'promptFreeSpace': '安裝後刪除原始檔案，釋放 {size}',
      'promptFreeSpaceKey': '安裝後刪除原始檔案及其光碟金鑰，釋放 {size}',
      'promptCancel': '取消',
      'promptInstall': '安裝並開始遊戲',
      'progressTitle': '正在安裝到 RPCS3',
      'progressPreparing': '正在準備 RPCS3…',
      'progressKeepOpen': '安裝完成前請保持 RewindBox 開啟。',
      'failFirmware': '請先安裝 PS3 韌體：在 RewindBox 中開啟 PS3 遊戲庫，並依照韌體步驟操作。',
      'failSpace': '可用空間不足，無法將此遊戲複製到 RPCS3。請釋放 iPhone 空間後重新啟動遊戲。',
      'failKey': '此光碟映像檔似乎已加密。請將其光碟金鑰（.dkey 或 .key，與 ISO 同名）放在同一資料夾中，然後重新啟動遊戲。',
      'failCorrupt': '此光碟映像檔不完整或已損毀。請重新複製後再啟動遊戲。',
      'failUnidentified': '遊戲已安裝到 RPCS3，但 RewindBox 無法識別它。請從 PS3 遊戲庫啟動。',
      'failGeneric': 'RPCS3 無法安裝此遊戲。',
    },
  };

  static String localeKey(Locale locale) {
    final script = locale.scriptCode?.toLowerCase();
    final region = locale.countryCode?.toUpperCase();
    final language = locale.languageCode.toLowerCase();
    if (language == 'zh_hant' || language == 'zh-hant') return 'zh_Hant';
    if (language == 'zh') {
      if (script == 'hant') return 'zh_Hant';
      if (script == null &&
          (region == 'TW' || region == 'HK' || region == 'MO')) {
        return 'zh_Hant';
      }
      return 'zh';
    }
    return values.containsKey(language) ? language : 'en';
  }

  static String forLocale(Locale locale, String key) =>
      values[localeKey(locale)]?[key] ?? values['en']![key] ?? key;

  static String format(
    Locale locale,
    String key,
    Map<String, Object?> arguments,
  ) {
    var text = forLocale(locale, key);
    for (final entry in arguments.entries) {
      text = text.replaceAll('{${entry.key}}', entry.value?.toString() ?? '');
    }
    return text;
  }

  /// The message shown when a library-folder disc could not be prepared.
  static String failure(Locale locale, Rpcs3LibraryFileFailure failure) =>
      forLocale(locale, switch (failure) {
        Rpcs3LibraryFileFailure.firmwareMissing => 'failFirmware',
        Rpcs3LibraryFileFailure.notEnoughSpace => 'failSpace',
        Rpcs3LibraryFileFailure.discKeyRequired => 'failKey',
        Rpcs3LibraryFileFailure.corruptImage => 'failCorrupt',
        Rpcs3LibraryFileFailure.unidentified => 'failUnidentified',
        Rpcs3LibraryFileFailure.installFailed => 'failGeneric',
      });

  static Locale _locale(BuildContext context) =>
      Localizations.maybeLocaleOf(context) ?? const Locale('en');

  static String text(BuildContext context, String key) =>
      forLocale(_locale(context), key);

  static String formatContext(
    BuildContext context,
    String key,
    Map<String, Object?> arguments,
  ) => format(_locale(context), key, arguments);
}
