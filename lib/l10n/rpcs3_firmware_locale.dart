import 'package:flutter/widgets.dart';

/// Texts of the information shown before a PS3 firmware installation or
/// reinstallation (Build 482): the Get More RAM app, its procedure and the
/// distinction with the PS3UPDAT.PUP firmware file. Product names, the
/// capability label as its app shows it, file names and the repository
/// address stay untranslated and are shown apart from these texts.
abstract final class Rpcs3FirmwareLocale {
  /// Verified official repository of the Get More RAM app (hugeBlack).
  static const String getMoreRamUrl = 'https://github.com/hugeBlack/GetMoreRam';

  static const Map<String, Map<String, String>>
  values = <String, Map<String, String>>{
    'en': {
      'preflightTitleInstall': 'Before installing the PS3 firmware',
      'preflightTitleReinstall': 'Before reinstalling the PS3 firmware',
      'preflightLead':
          'Before installing the PS3 firmware in RewindBox, install the Get More RAM app, or reinstall it if necessary, then follow its procedure. Then return to RewindBox to continue the firmware installation.',
      'preflightWhy':
          'RPCS3 needs more memory than iOS grants a sideloaded app by default. Get More RAM adds the “Increased Memory Limit” capability to the App ID RewindBox is signed with; RewindBox already requests it, but only the signing profile can grant it.',
      'preflightStepsTitle': 'Procedure of the Get More RAM app',
      'preflightStep1':
          'Install Get More RAM with the same sideloading tool that installed RewindBox (SideStore or AltStore). Reinstall it if it is already installed but no longer opens.',
      'preflightStep2':
          'In Get More RAM, open Settings and sign in with the Apple account used to sign RewindBox.',
      'preflightStep3':
          'Open App IDs, tap Refresh, choose RewindBox, then tap “Add Increased Memory Limit”.',
      'preflightStep4':
          'Reinstall RewindBox from SideStore or AltStore so the new capability is applied to the installed app.',
      'preflightStep5':
          'Come back to RewindBox and continue here with the firmware installation.',
      'preflightDistinction':
          'Get More RAM is a separate app, not the PS3 firmware. The firmware itself is the official PS3UPDAT.PUP file, which RewindBox asks for in the next step.',
      'preflightNoCheck':
          'RewindBox cannot verify here whether the capability is active on this iPhone. Continuing only confirms that you have read these steps.',
      'preflightOpenPage': 'Open the Get More RAM page',
      'preflightOpenPageFailed': 'The page could not be opened. Address: {url}',
      'preflightContinue': 'Continue to the firmware file',
      'preflightBack': 'Back',
    },
    'fr': {
      'preflightTitleInstall': 'Avant d’installer le firmware PS3',
      'preflightTitleReinstall': 'Avant de réinstaller le firmware PS3',
      'preflightLead':
          'Avant d’installer le firmware PS3 dans RewindBox, installez l’application Get More RAM, ou réinstallez-la si nécessaire, puis suivez sa procédure. Revenez ensuite dans RewindBox pour poursuivre l’installation du firmware.',
      'preflightWhy':
          'RPCS3 a besoin de plus de mémoire qu’iOS n’en accorde par défaut à une application installée par sideload. Get More RAM ajoute la capacité « Increased Memory Limit » à l’App ID avec lequel RewindBox est signée ; RewindBox la demande déjà, mais seul le profil de signature peut l’accorder.',
      'preflightStepsTitle': 'Procédure de l’application Get More RAM',
      'preflightStep1':
          'Installez Get More RAM avec le même outil de sideload que RewindBox (SideStore ou AltStore). Réinstallez-la si elle est déjà présente mais ne s’ouvre plus.',
      'preflightStep2':
          'Dans Get More RAM, ouvrez Settings et connectez-vous avec le compte Apple qui sert à signer RewindBox.',
      'preflightStep3':
          'Ouvrez App IDs, touchez Refresh, choisissez RewindBox, puis touchez « Add Increased Memory Limit ».',
      'preflightStep4':
          'Réinstallez RewindBox depuis SideStore ou AltStore pour que la nouvelle capacité soit appliquée à l’application installée.',
      'preflightStep5':
          'Revenez dans RewindBox et poursuivez ici l’installation du firmware.',
      'preflightDistinction':
          'Get More RAM est une application distincte, pas le firmware PS3. Le firmware lui-même est le fichier officiel PS3UPDAT.PUP, que RewindBox demande à l’étape suivante.',
      'preflightNoCheck':
          'RewindBox ne peut pas vérifier ici si la capacité est active sur cet iPhone. Poursuivre confirme seulement que vous avez lu ces étapes.',
      'preflightOpenPage': 'Ouvrir la page de Get More RAM',
      'preflightOpenPageFailed': 'La page n’a pas pu être ouverte. Adresse : {url}',
      'preflightContinue': 'Continuer vers le fichier du firmware',
      'preflightBack': 'Retour',
    },
    'de': {
      'preflightTitleInstall': 'Vor der Installation der PS3-Firmware',
      'preflightTitleReinstall': 'Vor der Neuinstallation der PS3-Firmware',
      'preflightLead':
          'Installiere vor der PS3-Firmware in RewindBox die App Get More RAM, oder installiere sie bei Bedarf neu, und folge ihrer Anleitung. Kehre danach zu RewindBox zurück, um die Firmware-Installation fortzusetzen.',
      'preflightWhy':
          'RPCS3 braucht mehr Speicher, als iOS einer per Sideload installierten App standardmäßig gewährt. Get More RAM fügt der App-ID, mit der RewindBox signiert ist, die Fähigkeit „Increased Memory Limit“ hinzu; RewindBox fordert sie bereits an, doch nur das Signaturprofil kann sie gewähren.',
      'preflightStepsTitle': 'Anleitung der App Get More RAM',
      'preflightStep1':
          'Installiere Get More RAM mit demselben Sideload-Werkzeug wie RewindBox (SideStore oder AltStore). Installiere sie neu, wenn sie bereits vorhanden ist, sich aber nicht mehr öffnet.',
      'preflightStep2':
          'Öffne in Get More RAM die Einstellungen (Settings) und melde dich mit dem Apple-Konto an, mit dem RewindBox signiert wird.',
      'preflightStep3':
          'Öffne App IDs, tippe auf Refresh, wähle RewindBox und tippe dann auf „Add Increased Memory Limit“.',
      'preflightStep4':
          'Installiere RewindBox aus SideStore oder AltStore neu, damit die neue Fähigkeit auf die installierte App angewendet wird.',
      'preflightStep5':
          'Kehre zu RewindBox zurück und setze hier die Firmware-Installation fort.',
      'preflightDistinction':
          'Get More RAM ist eine eigene App, nicht die PS3-Firmware. Die Firmware selbst ist die offizielle Datei PS3UPDAT.PUP, nach der RewindBox im nächsten Schritt fragt.',
      'preflightNoCheck':
          'RewindBox kann hier nicht prüfen, ob die Fähigkeit auf diesem iPhone aktiv ist. Fortfahren bestätigt nur, dass du diese Schritte gelesen hast.',
      'preflightOpenPage': 'Seite von Get More RAM öffnen',
      'preflightOpenPageFailed': 'Die Seite konnte nicht geöffnet werden. Adresse: {url}',
      'preflightContinue': 'Weiter zur Firmware-Datei',
      'preflightBack': 'Zurück',
    },
    'es': {
      'preflightTitleInstall': 'Antes de instalar el firmware de PS3',
      'preflightTitleReinstall': 'Antes de reinstalar el firmware de PS3',
      'preflightLead':
          'Antes de instalar el firmware de PS3 en RewindBox, instala la app Get More RAM, o reinstálala si es necesario, y sigue su procedimiento. Después vuelve a RewindBox para continuar la instalación del firmware.',
      'preflightWhy':
          'RPCS3 necesita más memoria de la que iOS concede por defecto a una app instalada por sideload. Get More RAM añade la capacidad «Increased Memory Limit» al App ID con el que se firma RewindBox; RewindBox ya la solicita, pero solo el perfil de firma puede concederla.',
      'preflightStepsTitle': 'Procedimiento de la app Get More RAM',
      'preflightStep1':
          'Instala Get More RAM con la misma herramienta de sideload que instaló RewindBox (SideStore o AltStore). Reinstálala si ya está instalada pero ya no se abre.',
      'preflightStep2':
          'En Get More RAM, abre Settings e inicia sesión con la cuenta de Apple usada para firmar RewindBox.',
      'preflightStep3':
          'Abre App IDs, toca Refresh, elige RewindBox y luego toca «Add Increased Memory Limit».',
      'preflightStep4':
          'Reinstala RewindBox desde SideStore o AltStore para que la nueva capacidad se aplique a la app instalada.',
      'preflightStep5':
          'Vuelve a RewindBox y continúa aquí con la instalación del firmware.',
      'preflightDistinction':
          'Get More RAM es una app aparte, no el firmware de PS3. El firmware en sí es el archivo oficial PS3UPDAT.PUP, que RewindBox pide en el siguiente paso.',
      'preflightNoCheck':
          'RewindBox no puede comprobar aquí si la capacidad está activa en este iPhone. Continuar solo confirma que has leído estos pasos.',
      'preflightOpenPage': 'Abrir la página de Get More RAM',
      'preflightOpenPageFailed': 'No se pudo abrir la página. Dirección: {url}',
      'preflightContinue': 'Continuar al archivo del firmware',
      'preflightBack': 'Atrás',
    },
    'it': {
      'preflightTitleInstall': 'Prima di installare il firmware PS3',
      'preflightTitleReinstall': 'Prima di reinstallare il firmware PS3',
      'preflightLead':
          'Prima di installare il firmware PS3 in RewindBox, installa l’app Get More RAM, o reinstallala se necessario, poi segui la sua procedura. Torna quindi in RewindBox per continuare l’installazione del firmware.',
      'preflightWhy':
          'RPCS3 ha bisogno di più memoria di quanta iOS ne conceda per impostazione predefinita a un’app installata via sideload. Get More RAM aggiunge la capacità «Increased Memory Limit» all’App ID con cui RewindBox è firmata; RewindBox la richiede già, ma solo il profilo di firma può concederla.',
      'preflightStepsTitle': 'Procedura dell’app Get More RAM',
      'preflightStep1':
          'Installa Get More RAM con lo stesso strumento di sideload che ha installato RewindBox (SideStore o AltStore). Reinstallala se è già presente ma non si apre più.',
      'preflightStep2':
          'In Get More RAM apri Settings e accedi con l’account Apple usato per firmare RewindBox.',
      'preflightStep3':
          'Apri App IDs, tocca Refresh, scegli RewindBox e poi tocca «Add Increased Memory Limit».',
      'preflightStep4':
          'Reinstalla RewindBox da SideStore o AltStore perché la nuova capacità venga applicata all’app installata.',
      'preflightStep5':
          'Torna in RewindBox e continua qui l’installazione del firmware.',
      'preflightDistinction':
          'Get More RAM è un’app separata, non il firmware PS3. Il firmware è il file ufficiale PS3UPDAT.PUP, che RewindBox chiede nel passaggio successivo.',
      'preflightNoCheck':
          'RewindBox non può verificare qui se la capacità è attiva su questo iPhone. Continuare conferma soltanto di aver letto questi passaggi.',
      'preflightOpenPage': 'Apri la pagina di Get More RAM',
      'preflightOpenPageFailed': 'Impossibile aprire la pagina. Indirizzo: {url}',
      'preflightContinue': 'Continua al file del firmware',
      'preflightBack': 'Indietro',
    },
    'pt': {
      'preflightTitleInstall': 'Antes de instalar o firmware da PS3',
      'preflightTitleReinstall': 'Antes de reinstalar o firmware da PS3',
      'preflightLead':
          'Antes de instalar o firmware da PS3 no RewindBox, instale a app Get More RAM, ou reinstale-a se necessário, e siga o seu procedimento. Depois volte ao RewindBox para continuar a instalação do firmware.',
      'preflightWhy':
          'O RPCS3 precisa de mais memória do que o iOS concede por padrão a uma app instalada por sideload. O Get More RAM adiciona a capacidade “Increased Memory Limit” ao App ID com que o RewindBox é assinado; o RewindBox já a solicita, mas só o perfil de assinatura pode concedê-la.',
      'preflightStepsTitle': 'Procedimento da app Get More RAM',
      'preflightStep1':
          'Instale o Get More RAM com a mesma ferramenta de sideload que instalou o RewindBox (SideStore ou AltStore). Reinstale-o se já estiver instalado mas não abrir mais.',
      'preflightStep2':
          'No Get More RAM, abra Settings e inicie sessão com a conta Apple usada para assinar o RewindBox.',
      'preflightStep3':
          'Abra App IDs, toque em Refresh, escolha RewindBox e depois toque em “Add Increased Memory Limit”.',
      'preflightStep4':
          'Reinstale o RewindBox a partir do SideStore ou AltStore para que a nova capacidade seja aplicada à app instalada.',
      'preflightStep5':
          'Volte ao RewindBox e continue aqui a instalação do firmware.',
      'preflightDistinction':
          'O Get More RAM é uma app separada, não o firmware da PS3. O firmware em si é o ficheiro oficial PS3UPDAT.PUP, que o RewindBox pede no passo seguinte.',
      'preflightNoCheck':
          'O RewindBox não consegue verificar aqui se a capacidade está ativa neste iPhone. Continuar apenas confirma que leu estes passos.',
      'preflightOpenPage': 'Abrir a página do Get More RAM',
      'preflightOpenPageFailed': 'Não foi possível abrir a página. Endereço: {url}',
      'preflightContinue': 'Continuar para o ficheiro do firmware',
      'preflightBack': 'Voltar',
    },
    'ru': {
      'preflightTitleInstall': 'Перед установкой прошивки PS3',
      'preflightTitleReinstall': 'Перед переустановкой прошивки PS3',
      'preflightLead':
          'Перед установкой прошивки PS3 в RewindBox установите приложение Get More RAM (или переустановите его при необходимости) и выполните его процедуру. Затем вернитесь в RewindBox, чтобы продолжить установку прошивки.',
      'preflightWhy':
          'RPCS3 требуется больше памяти, чем iOS по умолчанию выделяет приложению, установленному через sideload. Get More RAM добавляет возможность «Increased Memory Limit» к App ID, которым подписан RewindBox; RewindBox уже запрашивает её, но предоставить её может только профиль подписи.',
      'preflightStepsTitle': 'Процедура приложения Get More RAM',
      'preflightStep1':
          'Установите Get More RAM тем же инструментом sideload, которым был установлен RewindBox (SideStore или AltStore). Переустановите его, если оно уже есть, но больше не открывается.',
      'preflightStep2':
          'В Get More RAM откройте Settings и войдите в учётную запись Apple, которой подписывается RewindBox.',
      'preflightStep3':
          'Откройте App IDs, нажмите Refresh, выберите RewindBox, затем нажмите «Add Increased Memory Limit».',
      'preflightStep4':
          'Переустановите RewindBox из SideStore или AltStore, чтобы новая возможность применилась к установленному приложению.',
      'preflightStep5':
          'Вернитесь в RewindBox и продолжите здесь установку прошивки.',
      'preflightDistinction':
          'Get More RAM — отдельное приложение, а не прошивка PS3. Сама прошивка — это официальный файл PS3UPDAT.PUP, который RewindBox запросит на следующем шаге.',
      'preflightNoCheck':
          'RewindBox не может проверить здесь, активна ли эта возможность на данном iPhone. Продолжение лишь подтверждает, что вы прочитали эти шаги.',
      'preflightOpenPage': 'Открыть страницу Get More RAM',
      'preflightOpenPageFailed': 'Не удалось открыть страницу. Адрес: {url}',
      'preflightContinue': 'Перейти к файлу прошивки',
      'preflightBack': 'Назад',
    },
    'id': {
      'preflightTitleInstall': 'Sebelum memasang firmware PS3',
      'preflightTitleReinstall': 'Sebelum memasang ulang firmware PS3',
      'preflightLead':
          'Sebelum memasang firmware PS3 di RewindBox, pasang aplikasi Get More RAM, atau pasang ulang jika perlu, lalu ikuti prosedurnya. Setelah itu kembali ke RewindBox untuk melanjutkan pemasangan firmware.',
      'preflightWhy':
          'RPCS3 membutuhkan memori lebih besar daripada yang diberikan iOS secara bawaan kepada aplikasi yang dipasang lewat sideload. Get More RAM menambahkan kemampuan “Increased Memory Limit” ke App ID yang digunakan untuk menandatangani RewindBox; RewindBox sudah memintanya, tetapi hanya profil penandatanganan yang dapat memberikannya.',
      'preflightStepsTitle': 'Prosedur aplikasi Get More RAM',
      'preflightStep1':
          'Pasang Get More RAM dengan alat sideload yang sama dengan RewindBox (SideStore atau AltStore). Pasang ulang jika sudah ada tetapi tidak bisa dibuka lagi.',
      'preflightStep2':
          'Di Get More RAM, buka Settings dan masuk dengan akun Apple yang digunakan untuk menandatangani RewindBox.',
      'preflightStep3':
          'Buka App IDs, ketuk Refresh, pilih RewindBox, lalu ketuk “Add Increased Memory Limit”.',
      'preflightStep4':
          'Pasang ulang RewindBox dari SideStore atau AltStore agar kemampuan baru diterapkan pada aplikasi yang terpasang.',
      'preflightStep5':
          'Kembali ke RewindBox dan lanjutkan pemasangan firmware di sini.',
      'preflightDistinction':
          'Get More RAM adalah aplikasi terpisah, bukan firmware PS3. Firmware itu sendiri adalah berkas resmi PS3UPDAT.PUP yang akan diminta RewindBox pada langkah berikutnya.',
      'preflightNoCheck':
          'RewindBox tidak dapat memeriksa di sini apakah kemampuan tersebut aktif di iPhone ini. Melanjutkan hanya menegaskan bahwa Anda telah membaca langkah-langkah ini.',
      'preflightOpenPage': 'Buka halaman Get More RAM',
      'preflightOpenPageFailed': 'Halaman tidak dapat dibuka. Alamat: {url}',
      'preflightContinue': 'Lanjut ke berkas firmware',
      'preflightBack': 'Kembali',
    },
    'ja': {
      'preflightTitleInstall': 'PS3 ファームウェアをインストールする前に',
      'preflightTitleReinstall': 'PS3 ファームウェアを再インストールする前に',
      'preflightLead':
          'RewindBox に PS3 ファームウェアをインストールする前に、Get More RAM アプリをインストール（必要なら再インストール）し、その手順に従ってください。その後 RewindBox に戻り、ファームウェアのインストールを続けてください。',
      'preflightWhy':
          'RPCS3 には、サイドロードしたアプリに iOS が既定で与えるより多くのメモリが必要です。Get More RAM は RewindBox の署名に使う App ID に「Increased Memory Limit」の権限を追加します。RewindBox はすでにこの権限を要求していますが、付与できるのは署名プロファイルだけです。',
      'preflightStepsTitle': 'Get More RAM アプリの手順',
      'preflightStep1':
          'RewindBox をインストールしたのと同じサイドロードツール（SideStore または AltStore）で Get More RAM をインストールします。すでにあるのに開けない場合は再インストールしてください。',
      'preflightStep2':
          'Get More RAM で Settings を開き、RewindBox の署名に使っている Apple アカウントでサインインします。',
      'preflightStep3':
          'App IDs を開いて Refresh をタップし、RewindBox を選んでから「Add Increased Memory Limit」をタップします。',
      'preflightStep4':
          'SideStore または AltStore から RewindBox を再インストールし、新しい権限をインストール済みのアプリに適用します。',
      'preflightStep5':
          'RewindBox に戻り、ここでファームウェアのインストールを続けます。',
      'preflightDistinction':
          'Get More RAM は別のアプリであり、PS3 ファームウェアではありません。ファームウェア本体は公式の PS3UPDAT.PUP ファイルで、次のステップで RewindBox が選択を求めます。',
      'preflightNoCheck':
          'RewindBox はこの iPhone で権限が有効かどうかをここで確認できません。続行は、これらの手順を読んだことの確認にすぎません。',
      'preflightOpenPage': 'Get More RAM のページを開く',
      'preflightOpenPageFailed': 'ページを開けませんでした。アドレス: {url}',
      'preflightContinue': 'ファームウェアファイルへ進む',
      'preflightBack': '戻る',
    },
    'ko': {
      'preflightTitleInstall': 'PS3 펌웨어를 설치하기 전에',
      'preflightTitleReinstall': 'PS3 펌웨어를 다시 설치하기 전에',
      'preflightLead':
          'RewindBox에 PS3 펌웨어를 설치하기 전에 Get More RAM 앱을 설치하거나 필요하면 다시 설치한 뒤 그 절차를 따르세요. 그다음 RewindBox으로 돌아와 펌웨어 설치를 계속하세요.',
      'preflightWhy':
          'RPCS3에는 iOS가 사이드로드된 앱에 기본으로 허용하는 것보다 많은 메모리가 필요합니다. Get More RAM은 RewindBox 서명에 사용되는 App ID에 “Increased Memory Limit” 기능을 추가합니다. RewindBox은 이미 이 기능을 요청하지만, 서명 프로필만이 이를 부여할 수 있습니다.',
      'preflightStepsTitle': 'Get More RAM 앱 절차',
      'preflightStep1':
          'RewindBox을 설치한 것과 같은 사이드로드 도구(SideStore 또는 AltStore)로 Get More RAM을 설치하세요. 이미 설치되어 있지만 열리지 않으면 다시 설치하세요.',
      'preflightStep2':
          'Get More RAM에서 Settings를 열고 RewindBox 서명에 사용하는 Apple 계정으로 로그인하세요.',
      'preflightStep3':
          'App IDs를 열고 Refresh를 누른 뒤 RewindBox을 선택하고 “Add Increased Memory Limit”를 누르세요.',
      'preflightStep4':
          '새 기능이 설치된 앱에 적용되도록 SideStore 또는 AltStore에서 RewindBox을 다시 설치하세요.',
      'preflightStep5':
          'RewindBox으로 돌아와 여기에서 펌웨어 설치를 계속하세요.',
      'preflightDistinction':
          'Get More RAM은 별도의 앱이며 PS3 펌웨어가 아닙니다. 펌웨어 자체는 공식 PS3UPDAT.PUP 파일이며, 다음 단계에서 RewindBox이 이 파일을 요청합니다.',
      'preflightNoCheck':
          'RewindBox은 이 iPhone에서 해당 기능이 활성화되었는지 여기에서 확인할 수 없습니다. 계속하기는 이 단계를 읽었음을 확인하는 것일 뿐입니다.',
      'preflightOpenPage': 'Get More RAM 페이지 열기',
      'preflightOpenPageFailed': '페이지를 열 수 없습니다. 주소: {url}',
      'preflightContinue': '펌웨어 파일로 계속',
      'preflightBack': '뒤로',
    },
    'zh': {
      'preflightTitleInstall': '安装 PS3 固件之前',
      'preflightTitleReinstall': '重新安装 PS3 固件之前',
      'preflightLead':
          '在 RewindBox 中安装 PS3 固件之前，请先安装 Get More RAM 应用（如有必要请重新安装），并按照其步骤操作。然后回到 RewindBox 继续安装固件。',
      'preflightWhy':
          'RPCS3 需要的内存超过 iOS 默认授予侧载应用的上限。Get More RAM 会为签名 RewindBox 所用的 App ID 添加“Increased Memory Limit”能力；RewindBox 已经申请了该能力，但只有签名配置文件才能授予它。',
      'preflightStepsTitle': 'Get More RAM 应用的步骤',
      'preflightStep1':
          '使用安装 RewindBox 的同一侧载工具（SideStore 或 AltStore）安装 Get More RAM。如果已安装但无法打开，请重新安装。',
      'preflightStep2':
          '在 Get More RAM 中打开 Settings，并使用签名 RewindBox 的 Apple 账户登录。',
      'preflightStep3':
          '打开 App IDs，点按 Refresh，选择 RewindBox，然后点按“Add Increased Memory Limit”。',
      'preflightStep4':
          '从 SideStore 或 AltStore 重新安装 RewindBox，使新能力应用到已安装的应用。',
      'preflightStep5':
          '回到 RewindBox，在这里继续安装固件。',
      'preflightDistinction':
          'Get More RAM 是一个独立的应用，不是 PS3 固件。固件本身是官方的 PS3UPDAT.PUP 文件，RewindBox 会在下一步要求选择它。',
      'preflightNoCheck':
          'RewindBox 无法在此检查该能力是否已在这台 iPhone 上生效。继续仅表示你已阅读这些步骤。',
      'preflightOpenPage': '打开 Get More RAM 页面',
      'preflightOpenPageFailed': '无法打开该页面。地址：{url}',
      'preflightContinue': '继续选择固件文件',
      'preflightBack': '返回',
    },
    'zh_Hant': {
      'preflightTitleInstall': '安裝 PS3 韌體之前',
      'preflightTitleReinstall': '重新安裝 PS3 韌體之前',
      'preflightLead':
          '在 RewindBox 中安裝 PS3 韌體之前，請先安裝 Get More RAM 應用程式（必要時重新安裝），並依照其步驤操作。然後回到 RewindBox 繼續安裝韌體。',
      'preflightWhy':
          'RPCS3 需要的記憶體超過 iOS 預設給側載應用程式的上限。Get More RAM 會為簽署 RewindBox 所用的 App ID 加入「Increased Memory Limit」能力；RewindBox 已經要求此能力，但只有簽署描述檔才能授予它。',
      'preflightStepsTitle': 'Get More RAM 應用程式的步驟',
      'preflightStep1':
          '使用安裝 RewindBox 的同一側載工具（SideStore 或 AltStore）安裝 Get More RAM。若已安裝但無法開啟，請重新安裝。',
      'preflightStep2':
          '在 Get More RAM 中開啟 Settings，並以簽署 RewindBox 的 Apple 帳號登入。',
      'preflightStep3':
          '開啟 App IDs，點一下 Refresh，選擇 RewindBox，然後點一下「Add Increased Memory Limit」。',
      'preflightStep4':
          '從 SideStore 或 AltStore 重新安裝 RewindBox，讓新能力套用到已安裝的應用程式。',
      'preflightStep5':
          '回到 RewindBox，在這裡繼續安裝韌體。',
      'preflightDistinction':
          'Get More RAM 是獨立的應用程式，不是 PS3 韌體。韌體本身是官方的 PS3UPDAT.PUP 檔案，RewindBox 會在下一步要求選取它。',
      'preflightNoCheck':
          'RewindBox 無法在此檢查該能力是否已在這部 iPhone 上生效。繼續只表示你已閱讀這些步驟。',
      'preflightOpenPage': '開啟 Get More RAM 頁面',
      'preflightOpenPageFailed': '無法開啟該頁面。網址：{url}',
      'preflightContinue': '繼續選取韌體檔案',
      'preflightBack': '返回',
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
