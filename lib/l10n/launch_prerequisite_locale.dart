import 'dart:ui' show Locale;

import 'package:flutter/widgets.dart' show BuildContext, Localizations;
import 'package:flutter_localization/flutter_localization.dart';

/// What is missing before a game can start, and what to do about it, in the
/// twelve languages of the application.
///
/// One sentence per prerequisite, shared by the engines that need the same
/// thing (see `LaunchPrerequisite`): what is wrong first, then the action.
abstract final class LaunchPrerequisiteLocale {
  static const Map<String, Map<String, String>> values = <String, Map<String, String>>{
    'en': {
      'localDevVpn': 'LocalDevVPN is not connected. Open the LocalDevVPN app, connect the VPN and wait until it is connected, then come back to RewindBox and try again.',
      'pairingFile': 'The Pairing File of this iPhone is missing or cannot be read. Import it in Settings → Tools → Pairing File (a .mobiledevicepairing file made for this device), then try again.',
      'developmentSignature': 'This installation of RewindBox cannot enable JIT: it was signed without the get-task-allow entitlement. Install RewindBox with a development signature (for example with iLoader, SideStore or AltStore and your Apple ID); a distribution or enterprise certificate removes it. This cannot be changed inside the app.',
      'iosVersion': 'JIT needs iOS 17.4 or later. Update this device in Settings → General → Software Update.',
      'jitBusy': 'Another game is still starting. Wait a few seconds, then try again.',
      'jitHelper': 'JIT could not be enabled. Check that LocalDevVPN is still connected and that the Pairing File was made for this iPhone (Settings → Tools → Pairing File). If it goes on, close RewindBox completely and open it again.',
      'ps2BiosMissing': 'No PS2 BIOS is installed. A PlayStation 2 game needs the BIOS of your own console: open the PlayStation 2 list, tap Import → {action}, then try again.',
      'ps2BiosCancelled': 'No PS2 BIOS was chosen: the game was not started.',
      'gameUnreadable': 'The game file can no longer be read: it was moved, renamed or deleted. Refresh the list, or import the game again.',
      'ps2GameOutside': 'This game is not in RewindBox’s PlayStation 2 folder (Files → On My iPhone → RewindBox → ARMSX2 → Games). Import it from the PlayStation 2 list.',
    },
    'fr': {
      'localDevVpn': 'LocalDevVPN n’est pas connecté. Ouvrez l’app LocalDevVPN, connectez le VPN et attendez que la connexion soit établie, puis revenez dans RewindBox et réessayez.',
      'pairingFile': 'Le Pairing File de cet iPhone est absent ou illisible. Importez-le dans Paramètres → Outils → Pairing File (un fichier .mobiledevicepairing créé pour cet appareil), puis réessayez.',
      'developmentSignature': 'Cette installation de RewindBox ne peut pas activer le JIT : elle a été signée sans l’entitlement get-task-allow. Installez RewindBox avec une signature de développement (par exemple avec iLoader, SideStore ou AltStore et votre identifiant Apple) ; un certificat de distribution ou d’entreprise le retire. Ce droit ne peut pas être activé depuis l’application.',
      'iosVersion': 'Le JIT nécessite iOS 17.4 ou une version ultérieure. Mettez cet appareil à jour dans Réglages → Général → Mise à jour logicielle.',
      'jitBusy': 'Un autre jeu est encore en cours de démarrage. Patientez quelques secondes, puis réessayez.',
      'jitHelper': 'Le JIT n’a pas pu être activé. Vérifiez que LocalDevVPN est toujours connecté et que le Pairing File a bien été créé pour cet iPhone (Paramètres → Outils → Pairing File). Si le problème persiste, fermez complètement RewindBox puis rouvrez-le.',
      'ps2BiosMissing': 'Aucun BIOS PS2 n’est installé. Un jeu PlayStation 2 a besoin du BIOS de votre propre console : ouvrez la liste PlayStation 2, touchez Importer → {action}, puis réessayez.',
      'ps2BiosCancelled': 'Aucun BIOS PS2 n’a été choisi : le jeu n’a pas été lancé.',
      'gameUnreadable': 'Le fichier du jeu n’est plus lisible : il a été déplacé, renommé ou supprimé. Actualisez la liste ou importez de nouveau le jeu.',
      'ps2GameOutside': 'Ce jeu n’est pas dans le dossier PlayStation 2 de RewindBox (Fichiers → Sur mon iPhone → RewindBox → ARMSX2 → Games). Importez-le depuis la liste PlayStation 2.',
    },
    'de': {
      'localDevVpn': 'LocalDevVPN ist nicht verbunden. Öffne die App LocalDevVPN, verbinde das VPN und warte, bis die Verbindung steht. Kehre dann zu RewindBox zurück und versuche es erneut.',
      'pairingFile': 'Die Pairing-Datei dieses iPhones fehlt oder ist nicht lesbar. Importiere sie unter Einstellungen → Werkzeuge → Pairing-Datei (eine für dieses Gerät erstellte .mobiledevicepairing-Datei) und versuche es erneut.',
      'developmentSignature': 'Diese Installation von RewindBox kann JIT nicht aktivieren: Sie wurde ohne das Entitlement get-task-allow signiert. Installiere RewindBox mit einer Entwicklungssignatur (zum Beispiel mit iLoader, SideStore oder AltStore und deiner Apple-ID); ein Distributions- oder Enterprise-Zertifikat entfernt es. In der App lässt sich das nicht ändern.',
      'iosVersion': 'JIT benötigt iOS 17.4 oder neuer. Aktualisiere dieses Gerät unter Einstellungen → Allgemein → Softwareupdate.',
      'jitBusy': 'Ein anderes Spiel startet noch. Warte einige Sekunden und versuche es erneut.',
      'jitHelper': 'JIT konnte nicht aktiviert werden. Prüfe, ob LocalDevVPN noch verbunden ist und die Pairing-Datei für dieses iPhone erstellt wurde (Einstellungen → Werkzeuge → Pairing-Datei). Besteht das Problem weiter, beende RewindBox vollständig und öffne es erneut.',
      'ps2BiosMissing': 'Es ist kein PS2-BIOS installiert. Ein PlayStation-2-Spiel braucht das BIOS deiner eigenen Konsole: Öffne die PlayStation-2-Liste, tippe auf Importieren → {action} und versuche es erneut.',
      'ps2BiosCancelled': 'Es wurde kein PS2-BIOS ausgewählt: Das Spiel wurde nicht gestartet.',
      'gameUnreadable': 'Die Spieldatei ist nicht mehr lesbar: Sie wurde verschoben, umbenannt oder gelöscht. Aktualisiere die Liste oder importiere das Spiel erneut.',
      'ps2GameOutside': 'Dieses Spiel liegt nicht im PlayStation-2-Ordner von RewindBox (Dateien → Auf meinem iPhone → RewindBox → ARMSX2 → Games). Importiere es über die PlayStation-2-Liste.',
    },
    'es': {
      'localDevVpn': 'LocalDevVPN no está conectado. Abre la app LocalDevVPN, conecta la VPN y espera a que se conecte; después vuelve a RewindBox e inténtalo de nuevo.',
      'pairingFile': 'Falta el archivo de emparejamiento de este iPhone o no se puede leer. Impórtalo en Ajustes → Herramientas → Archivo de emparejamiento (un archivo .mobiledevicepairing creado para este dispositivo) e inténtalo de nuevo.',
      'developmentSignature': 'Esta instalación de RewindBox no puede activar JIT: se firmó sin el entitlement get-task-allow. Instala RewindBox con una firma de desarrollo (por ejemplo con iLoader, SideStore o AltStore y tu Apple ID); un certificado de distribución o de empresa lo elimina. No se puede cambiar desde la app.',
      'iosVersion': 'JIT requiere iOS 17.4 o posterior. Actualiza este dispositivo en Ajustes → General → Actualización de software.',
      'jitBusy': 'Otro juego todavía se está iniciando. Espera unos segundos e inténtalo de nuevo.',
      'jitHelper': 'No se pudo activar JIT. Comprueba que LocalDevVPN sigue conectado y que el archivo de emparejamiento se creó para este iPhone (Ajustes → Herramientas → Archivo de emparejamiento). Si continúa, cierra RewindBox por completo y vuelve a abrirlo.',
      'ps2BiosMissing': 'No hay ningún BIOS de PS2 instalado. Un juego de PlayStation 2 necesita el BIOS de tu propia consola: abre la lista de PlayStation 2, toca Importar → {action} e inténtalo de nuevo.',
      'ps2BiosCancelled': 'No se eligió ningún BIOS de PS2: el juego no se inició.',
      'gameUnreadable': 'El archivo del juego ya no se puede leer: se movió, se renombró o se eliminó. Actualiza la lista o importa el juego de nuevo.',
      'ps2GameOutside': 'Este juego no está en la carpeta de PlayStation 2 de RewindBox (Archivos → En mi iPhone → RewindBox → ARMSX2 → Games). Impórtalo desde la lista de PlayStation 2.',
    },
    'it': {
      'localDevVpn': 'LocalDevVPN non è connesso. Apri l’app LocalDevVPN, connetti la VPN e attendi la connessione, poi torna a RewindBox e riprova.',
      'pairingFile': 'Il file di abbinamento di questo iPhone manca o non è leggibile. Importalo in Impostazioni → Strumenti → File di abbinamento (un file .mobiledevicepairing creato per questo dispositivo), poi riprova.',
      'developmentSignature': 'Questa installazione di RewindBox non può attivare il JIT: è stata firmata senza l’entitlement get-task-allow. Installa RewindBox con una firma di sviluppo (ad esempio con iLoader, SideStore o AltStore e il tuo ID Apple); un certificato di distribuzione o aziendale lo rimuove. Non si può cambiare dall’app.',
      'iosVersion': 'Il JIT richiede iOS 17.4 o successivo. Aggiorna questo dispositivo in Impostazioni → Generali → Aggiornamento software.',
      'jitBusy': 'Un altro gioco è ancora in avvio. Attendi qualche secondo e riprova.',
      'jitHelper': 'Impossibile attivare il JIT. Controlla che LocalDevVPN sia ancora connesso e che il file di abbinamento sia stato creato per questo iPhone (Impostazioni → Strumenti → File di abbinamento). Se il problema continua, chiudi completamente RewindBox e riaprilo.',
      'ps2BiosMissing': 'Nessun BIOS PS2 installato. Un gioco PlayStation 2 richiede il BIOS della tua console: apri l’elenco PlayStation 2, tocca Importa → {action}, poi riprova.',
      'ps2BiosCancelled': 'Nessun BIOS PS2 scelto: il gioco non è stato avviato.',
      'gameUnreadable': 'Il file del gioco non è più leggibile: è stato spostato, rinominato o eliminato. Aggiorna l’elenco o importa di nuovo il gioco.',
      'ps2GameOutside': 'Questo gioco non è nella cartella PlayStation 2 di RewindBox (File → iPhone → RewindBox → ARMSX2 → Games). Importalo dall’elenco PlayStation 2.',
    },
    'pt': {
      'localDevVpn': 'O LocalDevVPN não está ligado. Abra a app LocalDevVPN, ligue a VPN e aguarde a ligação; depois volte ao RewindBox e tente novamente.',
      'pairingFile': 'O arquivo de emparelhamento deste iPhone está em falta ou não pode ser lido. Importe-o em Configurações → Ferramentas → Arquivo de emparelhamento (um ficheiro .mobiledevicepairing criado para este dispositivo) e tente novamente.',
      'developmentSignature': 'Esta instalação do RewindBox não pode ativar o JIT: foi assinada sem o entitlement get-task-allow. Instale o RewindBox com uma assinatura de desenvolvimento (por exemplo com iLoader, SideStore ou AltStore e o seu ID Apple); um certificado de distribuição ou empresarial remove-o. Não é possível alterar isto dentro da app.',
      'iosVersion': 'O JIT requer o iOS 17.4 ou posterior. Atualize este dispositivo em Definições → Geral → Atualização de software.',
      'jitBusy': 'Outro jogo ainda está a iniciar. Aguarde alguns segundos e tente novamente.',
      'jitHelper': 'Não foi possível ativar o JIT. Verifique se o LocalDevVPN continua ligado e se o arquivo de emparelhamento foi criado para este iPhone (Configurações → Ferramentas → Arquivo de emparelhamento). Se continuar, feche completamente o RewindBox e abra-o de novo.',
      'ps2BiosMissing': 'Nenhum BIOS PS2 instalado. Um jogo de PlayStation 2 precisa do BIOS da sua própria consola: abra a lista PlayStation 2, toque em Importar → {action} e tente novamente.',
      'ps2BiosCancelled': 'Nenhum BIOS PS2 foi escolhido: o jogo não foi iniciado.',
      'gameUnreadable': 'O ficheiro do jogo já não pode ser lido: foi movido, renomeado ou eliminado. Atualize a lista ou importe o jogo novamente.',
      'ps2GameOutside': 'Este jogo não está na pasta PlayStation 2 do RewindBox (Ficheiros → No meu iPhone → RewindBox → ARMSX2 → Games). Importe-o a partir da lista PlayStation 2.',
    },
    'ru': {
      'localDevVpn': 'LocalDevVPN не подключён. Откройте приложение LocalDevVPN, подключите VPN и дождитесь подключения, затем вернитесь в RewindBox и повторите попытку.',
      'pairingFile': 'Файл сопряжения этого iPhone отсутствует или не читается. Импортируйте его в разделе Настройки → Инструменты → Файл сопряжения (файл .mobiledevicepairing, созданный для этого устройства) и повторите попытку.',
      'developmentSignature': 'Эта установка RewindBox не может включить JIT: она подписана без права get-task-allow. Установите RewindBox с подписью разработчика (например, через iLoader, SideStore или AltStore с вашим Apple ID); сертификат распространения или корпоративный сертификат убирает это право. В приложении это изменить нельзя.',
      'iosVersion': 'Для JIT требуется iOS 17.4 или новее. Обновите устройство в разделе Настройки → Основные → Обновление ПО.',
      'jitBusy': 'Другая игра ещё запускается. Подождите несколько секунд и повторите попытку.',
      'jitHelper': 'Не удалось включить JIT. Проверьте, что LocalDevVPN всё ещё подключён и что файл сопряжения создан для этого iPhone (Настройки → Инструменты → Файл сопряжения). Если проблема сохраняется, полностью закройте RewindBox и откройте его снова.',
      'ps2BiosMissing': 'BIOS PS2 не установлен. Игре PlayStation 2 нужен BIOS вашей собственной консоли: откройте список PlayStation 2, нажмите Импорт → {action} и повторите попытку.',
      'ps2BiosCancelled': 'BIOS PS2 не выбран: игра не запущена.',
      'gameUnreadable': 'Файл игры больше не читается: он был перемещён, переименован или удалён. Обновите список или импортируйте игру снова.',
      'ps2GameOutside': 'Этой игры нет в папке PlayStation 2 приложения RewindBox (Файлы → На iPhone → RewindBox → ARMSX2 → Games). Импортируйте её из списка PlayStation 2.',
    },
    'id': {
      'localDevVpn': 'LocalDevVPN tidak terhubung. Buka aplikasi LocalDevVPN, hubungkan VPN dan tunggu hingga terhubung, lalu kembali ke RewindBox dan coba lagi.',
      'pairingFile': 'File Pairing iPhone ini tidak ada atau tidak dapat dibaca. Impor di Pengaturan → Alat → File Pairing (file .mobiledevicepairing yang dibuat untuk perangkat ini), lalu coba lagi.',
      'developmentSignature': 'Instalasi RewindBox ini tidak dapat mengaktifkan JIT: ditandatangani tanpa entitlement get-task-allow. Pasang RewindBox dengan tanda tangan pengembangan (misalnya dengan iLoader, SideStore, atau AltStore dan Apple ID Anda); sertifikat distribusi atau perusahaan menghapusnya. Ini tidak dapat diubah dari dalam aplikasi.',
      'iosVersion': 'JIT memerlukan iOS 17.4 atau lebih baru. Perbarui perangkat ini di Pengaturan → Umum → Pembaruan Perangkat Lunak.',
      'jitBusy': 'Game lain masih dimulai. Tunggu beberapa detik, lalu coba lagi.',
      'jitHelper': 'JIT tidak dapat diaktifkan. Pastikan LocalDevVPN masih terhubung dan File Pairing dibuat untuk iPhone ini (Pengaturan → Alat → File Pairing). Jika masih terjadi, tutup RewindBox sepenuhnya lalu buka lagi.',
      'ps2BiosMissing': 'Belum ada BIOS PS2 yang terpasang. Game PlayStation 2 memerlukan BIOS dari konsol Anda sendiri: buka daftar PlayStation 2, ketuk Impor → {action}, lalu coba lagi.',
      'ps2BiosCancelled': 'Tidak ada BIOS PS2 yang dipilih: game tidak dijalankan.',
      'gameUnreadable': 'File game tidak dapat dibaca lagi: file telah dipindahkan, diganti namanya, atau dihapus. Segarkan daftar atau impor game lagi.',
      'ps2GameOutside': 'Game ini tidak berada di folder PlayStation 2 RewindBox (File → Di iPhone Saya → RewindBox → ARMSX2 → Games). Impor dari daftar PlayStation 2.',
    },
    'ja': {
      'localDevVpn': 'LocalDevVPN が接続されていません。LocalDevVPN アプリを開いて VPN を接続し、接続が完了するまで待ってから RewindBox に戻り、もう一度お試しください。',
      'pairingFile': 'この iPhone のペアリングファイルがないか、読み込めません。「設定 → ツール → ペアリングファイル」で読み込み（このデバイス用に作成した .mobiledevicepairing ファイル）、もう一度お試しください。',
      'developmentSignature': 'この RewindBox のインストールでは JIT を有効にできません。get-task-allow エンタイトルメントなしで署名されています。開発用署名（Apple ID を使った iLoader、SideStore、AltStore など）で RewindBox をインストールしてください。配布用またはエンタープライズ証明書ではこの権限が外れます。アプリ内では変更できません。',
      'iosVersion': 'JIT には iOS 17.4 以降が必要です。「設定 → 一般 → ソフトウェアアップデート」でこのデバイスをアップデートしてください。',
      'jitBusy': '別のゲームがまだ起動中です。数秒待ってからもう一度お試しください。',
      'jitHelper': 'JIT を有効にできませんでした。LocalDevVPN が接続されたままか、ペアリングファイルがこの iPhone 用に作成されたものか（設定 → ツール → ペアリングファイル）を確認してください。解決しない場合は RewindBox を完全に終了して開き直してください。',
      'ps2BiosMissing': 'PS2 BIOS がインストールされていません。PlayStation 2 のゲームにはご自身の本体の BIOS が必要です。PlayStation 2 の一覧を開き、「インポート → {action}」をタップしてから、もう一度お試しください。',
      'ps2BiosCancelled': 'PS2 BIOS が選択されなかったため、ゲームは起動されませんでした。',
      'gameUnreadable': 'ゲームファイルを読み込めなくなりました。移動、名前変更、または削除されています。一覧を更新するか、ゲームをもう一度インポートしてください。',
      'ps2GameOutside': 'このゲームは RewindBox の PlayStation 2 フォルダ（ファイル → この iPhone 内 → RewindBox → ARMSX2 → Games）にありません。PlayStation 2 の一覧からインポートしてください。',
    },
    'ko': {
      'localDevVpn': 'LocalDevVPN이 연결되어 있지 않습니다. LocalDevVPN 앱을 열어 VPN을 연결하고 연결될 때까지 기다린 다음, RewindBox로 돌아와 다시 시도하세요.',
      'pairingFile': '이 iPhone의 페어링 파일이 없거나 읽을 수 없습니다. 설정 → 도구 → 페어링 파일에서 가져온 뒤(이 기기용으로 만든 .mobiledevicepairing 파일) 다시 시도하세요.',
      'developmentSignature': '이 RewindBox 설치본은 JIT를 켤 수 없습니다. get-task-allow 권한 없이 서명되었습니다. 개발용 서명(예: Apple ID를 사용하는 iLoader, SideStore 또는 AltStore)으로 RewindBox를 설치하세요. 배포용 또는 엔터프라이즈 인증서는 이 권한을 제거합니다. 앱 안에서는 변경할 수 없습니다.',
      'iosVersion': 'JIT에는 iOS 17.4 이상이 필요합니다. 설정 → 일반 → 소프트웨어 업데이트에서 이 기기를 업데이트하세요.',
      'jitBusy': '다른 게임이 아직 시작 중입니다. 몇 초 기다린 뒤 다시 시도하세요.',
      'jitHelper': 'JIT를 켤 수 없습니다. LocalDevVPN이 계속 연결되어 있는지, 페어링 파일이 이 iPhone용으로 만들어졌는지(설정 → 도구 → 페어링 파일) 확인하세요. 계속되면 RewindBox를 완전히 종료한 뒤 다시 여세요.',
      'ps2BiosMissing': '설치된 PS2 BIOS가 없습니다. PlayStation 2 게임에는 본인 콘솔의 BIOS가 필요합니다. PlayStation 2 목록을 열고 가져오기 → {action} 항목을 탭한 뒤 다시 시도하세요.',
      'ps2BiosCancelled': 'PS2 BIOS를 선택하지 않아 게임을 실행하지 않았습니다.',
      'gameUnreadable': '게임 파일을 더 이상 읽을 수 없습니다. 이동, 이름 변경 또는 삭제되었습니다. 목록을 새로 고치거나 게임을 다시 가져오세요.',
      'ps2GameOutside': '이 게임은 RewindBox의 PlayStation 2 폴더(파일 → 나의 iPhone → RewindBox → ARMSX2 → Games)에 없습니다. PlayStation 2 목록에서 가져오세요.',
    },
    'zh': {
      'localDevVpn': 'LocalDevVPN 未连接。请打开 LocalDevVPN App，连接 VPN 并等待连接完成，然后返回 RewindBox 重试。',
      'pairingFile': '缺少此 iPhone 的配对文件，或文件无法读取。请在“设置 → 工具 → 配对文件”中导入（为此设备创建的 .mobiledevicepairing 文件），然后重试。',
      'developmentSignature': '此 RewindBox 安装无法启用 JIT：签名时没有 get-task-allow 权限。请使用开发签名（例如通过 Apple ID 使用 iLoader、SideStore 或 AltStore）安装 RewindBox；分发证书或企业证书会移除该权限。无法在 App 内更改。',
      'iosVersion': 'JIT 需要 iOS 17.4 或更高版本。请在“设置 → 通用 → 软件更新”中更新此设备。',
      'jitBusy': '另一个游戏仍在启动。请等待几秒后重试。',
      'jitHelper': '无法启用 JIT。请确认 LocalDevVPN 仍处于连接状态，并且配对文件是为此 iPhone 创建的（设置 → 工具 → 配对文件）。如果问题仍然存在，请完全关闭 RewindBox 后重新打开。',
      'ps2BiosMissing': '尚未安装 PS2 BIOS。PlayStation 2 游戏需要您自己主机的 BIOS：打开 PlayStation 2 列表，轻点“导入 → {action}”，然后重试。',
      'ps2BiosCancelled': '未选择 PS2 BIOS：游戏未启动。',
      'gameUnreadable': '游戏文件已无法读取：文件已被移动、重命名或删除。请刷新列表或重新导入游戏。',
      'ps2GameOutside': '此游戏不在 RewindBox 的 PlayStation 2 文件夹中（文件 → 我的 iPhone → RewindBox → ARMSX2 → Games）。请从 PlayStation 2 列表导入。',
    },
    'zh_Hant': {
      'localDevVpn': 'LocalDevVPN 未連線。請打開 LocalDevVPN App，連接 VPN 並等待連線完成，然後返回 RewindBox 再試一次。',
      'pairingFile': '缺少此 iPhone 的配對檔案，或檔案無法讀取。請在「設定 → 工具 → 配對檔案」中匯入（為此裝置建立的 .mobiledevicepairing 檔案），然後再試一次。',
      'developmentSignature': '此 RewindBox 安裝無法啟用 JIT：簽署時沒有 get-task-allow 權限。請使用開發簽署（例如透過 Apple ID 使用 iLoader、SideStore 或 AltStore）安裝 RewindBox；發佈憑證或企業憑證會移除該權限。無法在 App 內更改。',
      'iosVersion': 'JIT 需要 iOS 17.4 或以上版本。請在「設定 → 一般 → 軟體更新」中更新此裝置。',
      'jitBusy': '另一個遊戲仍在啟動。請等待數秒後再試一次。',
      'jitHelper': '無法啟用 JIT。請確認 LocalDevVPN 仍在連線，且配對檔案是為此 iPhone 建立的（設定 → 工具 → 配對檔案）。如果問題持續，請完全關閉 RewindBox 後重新開啟。',
      'ps2BiosMissing': '尚未安裝 PS2 BIOS。PlayStation 2 遊戲需要您自己主機的 BIOS：打開 PlayStation 2 列表，點一下「匯入 → {action}」，然後再試一次。',
      'ps2BiosCancelled': '未選擇 PS2 BIOS：遊戲未啟動。',
      'gameUnreadable': '遊戲檔案已無法讀取：檔案已被移動、重新命名或刪除。請重新整理列表或重新匯入遊戲。',
      'ps2GameOutside': '此遊戲不在 RewindBox 的 PlayStation 2 資料夾中（檔案 → 我的 iPhone → RewindBox → ARMSX2 → Games）。請從 PlayStation 2 列表匯入。',
    },
  };

  /// The table key of [locale]: its language, with Traditional Chinese apart.
  static String languageOf(Locale locale) {
    if (locale.languageCode == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' || country == 'TW' || country == 'HK' || country == 'MO') return 'zh_Hant';
      return 'zh';
    }
    return values.containsKey(locale.languageCode) ? locale.languageCode : 'en';
  }

  /// The language the application shows now, for code without a context
  /// (services that record why a launch stopped).
  static String currentLanguage() {
    final locale = FlutterLocalization.instance.currentLocale;
    return locale == null ? 'en' : languageOf(locale);
  }

  /// The sentence of [key] in [language] (English when missing), with each
  /// `{name}` of [values] replaced.
  static String textFor(String language, String key, [Map<String, Object?> values = const <String, Object?>{}]) {
    var text = LaunchPrerequisiteLocale.values[language]?[key] ?? LaunchPrerequisiteLocale.values['en']![key] ?? key;
    values.forEach((name, value) => text = text.replaceAll('{$name}', '$value'));
    return text;
  }

  static String text(BuildContext context, String key, [Map<String, Object?> values = const <String, Object?>{}]) =>
      textFor(languageOf(Localizations.localeOf(context)), key, values);
}
