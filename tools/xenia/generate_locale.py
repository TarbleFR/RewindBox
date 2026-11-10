"""Generates lib/l10n/xenia_locale.dart (12 locales): python3 tools/xenia/generate_locale.py lib/l10n/xenia_locale.dart"""
import json
import sys

KEYS = [
 'importMenu','importGames','globalSettings','importing','cancel','imported','duplicates','cancelled','rejectedItem',
 'profileNotGame','touchLayoutNotGame','folderRequired','unsupported','unreadable','notXboxImage','incomplete','notEnoughSpace','copyFailed',
 'requiresIOS26','engineMissing','abiMismatch','unsupportedPlatform','jitUnavailable','sessionActive','restartRequired','gameUnreadable','launchFailed',
 'settingsTitle','globalScope','gameScope','appliesNextLaunch','inheritedFrom','sourceEngine','sourceGlobal','sourceGame','resetGame','resetGlobal',
 'on','off','automatic','unlimited','sectionConsole','sectionGraphics','sectionAudio','sectionSystem',
 'user_language','user_country','use_50Hz_mode','framerate_limit','guest_display_refresh_cap','present_letterbox','async_shader_compilation','apu_max_queued_frames','xma_decoder','mount_cache',
 'languageHelp','countryHelp','interfaceNote','decoderNew','decoderOld','decoderMaster','saveFailed','gameSettings','emptyTitle','emptyBody',
 'shaderConverterMissing','pairingRequired','jitAttachFailed','jitHelperIncomplete',
]

T = {
'en': ['XeniOS / Import','Import games','Xbox 360 settings','Importing {name} ({index}/{count})…','Cancel','{count} Xbox 360 game(s) imported.','{count} game(s) already in the library were skipped.','Import cancelled. No partial game was kept.','{name}: {reason}',
 'XeniOS profile, not a game','XeniOS touch layout, not a game','a loose .xex needs its whole game folder, which cannot be imported yet','unsupported file','file not readable','not an Xbox 360 disc image','incomplete or damaged disc image','not enough free space','copy failed',
 'Xbox 360 games require iOS 26 or later.','The XeniOS engine is not included in this version of RewindBox.','The XeniOS engine in this build does not match RewindBox.','XeniOS runs on iPhone and iPad only.','XeniOS needs JIT, which is not available to RewindBox right now.','Another game is already running.','Restart RewindBox before starting another Xbox 360 game.','The game file cannot be read.','The game could not be started in XeniOS.',
 'XeniOS settings','All Xbox 360 games','This game','Changes apply the next time a game starts.','Inherited from: {source}','engine default','all games','this game','Use inherited values','Restore engine defaults',
 'On','Off','Automatic','Unlimited','Console','Display','Audio','System',
 'Console language','Console region','PAL 50 Hz timing','Frame rate limit','Cap guest display refresh','Letterbox','Compile shaders in background','Audio buffer (frames)','Audio decoder','Cache drive',
 'Language the console reports to games. A signed-in XeniOS profile keeps its own language. Automatic follows the RewindBox language (English for Indonesian, which the Xbox 360 does not offer).','Region the console reports to games. Automatic follows the device region (United States when it is not an Xbox 360 region).','The RewindBox interface language is a separate setting.','New','Old','Master','Setting not saved: {error}','XeniOS settings for this game','No Xbox 360 games yet','Import your .iso or .zar games from Files with the import button.',"This version of RewindBox contains the XeniOS engine without Apple's Metal Shader Converter, which it needs to display games.",'A RemotePairing file is required to enable JIT for XeniOS.','The JIT helper could not attach to RewindBox. Check that LocalDevVPN is connected, then try again.','The JIT helper did not finish. Restart RewindBox, then try again.'],
'fr': ['XeniOS / Importer','Importer des jeux','Réglages Xbox 360','Import de {name} ({index}/{count})…','Annuler','{count} jeu(x) Xbox 360 importé(s).','{count} jeu(x) déjà présent(s) dans la bibliothèque ignoré(s).','Import annulé. Aucun jeu partiel n’a été conservé.','{name} : {reason}',
 'profil XeniOS, pas un jeu','disposition tactile XeniOS, pas un jeu','un .xex isolé a besoin de tout le dossier du jeu, dont l’import n’est pas encore disponible','fichier non pris en charge','fichier illisible','pas une image disque Xbox 360','image disque incomplète ou endommagée','espace libre insuffisant','échec de la copie',
 'Les jeux Xbox 360 nécessitent iOS 26 ou une version ultérieure.','Le moteur XeniOS n’est pas inclus dans cette version de RewindBox.','Le moteur XeniOS de cette version ne correspond pas à RewindBox.','XeniOS fonctionne uniquement sur iPhone et iPad.','XeniOS a besoin du JIT, qui n’est pas disponible pour RewindBox actuellement.','Un autre jeu est déjà en cours.','Redémarrez RewindBox avant de lancer un autre jeu Xbox 360.','Le fichier du jeu est illisible.','Le jeu n’a pas pu démarrer dans XeniOS.',
 'Réglages XeniOS','Tous les jeux Xbox 360','Ce jeu','Les changements s’appliquent au prochain lancement d’un jeu.','Hérité de : {source}','valeur par défaut du moteur','tous les jeux','ce jeu','Utiliser les valeurs héritées','Rétablir les valeurs du moteur',
 'Activé','Désactivé','Automatique','Illimitée','Console','Affichage','Audio','Système',
 'Langue de la console','Région de la console','Fréquence PAL 50 Hz','Limite d’images par seconde','Limiter le rafraîchissement de l’affichage invité','Bandes noires (letterbox)','Compiler les shaders en arrière-plan','Tampon audio (images)','Décodeur audio','Disque cache',
 'Langue que la console indique aux jeux. Un profil XeniOS connecté conserve sa propre langue. Automatique suit la langue de RewindBox (anglais pour l’indonésien, absent de la Xbox 360).','Région que la console indique aux jeux. Automatique suit la région de l’appareil (États-Unis si ce n’est pas une région Xbox 360).','La langue de l’interface RewindBox est un réglage distinct.','Nouveau','Ancien','Master','Réglage non enregistré : {error}','Réglages XeniOS de ce jeu','Aucun jeu Xbox 360 pour l’instant','Importez vos jeux .iso ou .zar depuis Fichiers avec le bouton d’import.','Cette version de RewindBox contient le moteur XeniOS sans le Metal Shader Converter d’Apple, nécessaire à l’affichage des jeux.','Un fichier RemotePairing est nécessaire pour activer le JIT de XeniOS.','L’assistant JIT n’a pas pu s’attacher à RewindBox. Vérifiez que LocalDevVPN est connecté, puis réessayez.','L’assistant JIT n’a pas terminé. Redémarrez RewindBox, puis réessayez.'],
'de': ['XeniOS / Import','Spiele importieren','Xbox-360-Einstellungen','{name} wird importiert ({index}/{count})…','Abbrechen','{count} Xbox-360-Spiel(e) importiert.','{count} bereits vorhandene(s) Spiel(e) übersprungen.','Import abgebrochen. Kein unvollständiges Spiel wurde behalten.','{name}: {reason}',
 'XeniOS-Profil, kein Spiel','XeniOS-Touch-Layout, kein Spiel','eine einzelne .xex braucht ihren ganzen Spielordner, der noch nicht importiert werden kann','nicht unterstützte Datei','Datei nicht lesbar','kein Xbox-360-Disc-Image','unvollständiges oder beschädigtes Disc-Image','nicht genug freier Speicher','Kopieren fehlgeschlagen',
 'Xbox-360-Spiele erfordern iOS 26 oder neuer.','Die XeniOS-Engine ist in dieser RewindBox-Version nicht enthalten.','Die XeniOS-Engine dieses Builds passt nicht zu RewindBox.','XeniOS läuft nur auf iPhone und iPad.','XeniOS benötigt JIT, das RewindBox gerade nicht zur Verfügung steht.','Es läuft bereits ein anderes Spiel.','Starte RewindBox neu, bevor du ein weiteres Xbox-360-Spiel startest.','Die Spieldatei ist nicht lesbar.','Das Spiel konnte in XeniOS nicht gestartet werden.',
 'XeniOS-Einstellungen','Alle Xbox-360-Spiele','Dieses Spiel','Änderungen gelten beim nächsten Spielstart.','Übernommen von: {source}','Engine-Standard','alle Spiele','dieses Spiel','Übernommene Werte verwenden','Engine-Standards wiederherstellen',
 'Ein','Aus','Automatisch','Unbegrenzt','Konsole','Anzeige','Audio','System',
 'Konsolensprache','Konsolenregion','PAL-50-Hz-Timing','Bildratenlimit','Gast-Bildwiederholrate begrenzen','Letterbox','Shader im Hintergrund kompilieren','Audiopuffer (Frames)','Audiodecoder','Cache-Laufwerk',
 'Sprache, die die Konsole den Spielen meldet. Ein angemeldetes XeniOS-Profil behält seine eigene Sprache. Automatisch folgt der RewindBox-Sprache (Englisch für Indonesisch, das die Xbox 360 nicht anbietet).','Region, die die Konsole den Spielen meldet. Automatisch folgt der Geräteregion (USA, wenn sie keine Xbox-360-Region ist).','Die Sprache der RewindBox-Oberfläche ist eine eigene Einstellung.','Neu','Alt','Master','Einstellung nicht gespeichert: {error}','XeniOS-Einstellungen für dieses Spiel','Noch keine Xbox-360-Spiele','Importiere deine .iso- oder .zar-Spiele mit der Import-Taste aus Dateien.','Diese RewindBox-Version enthält die XeniOS-Engine ohne Apples Metal Shader Converter, den sie zur Anzeige von Spielen benötigt.','Für den XeniOS-JIT wird eine RemotePairing-Datei benötigt.','Der JIT-Helfer konnte sich nicht mit RewindBox verbinden. Prüfe, ob LocalDevVPN verbunden ist, und versuche es erneut.','Der JIT-Helfer wurde nicht abgeschlossen. Starte RewindBox neu und versuche es erneut.'],
'es': ['XeniOS / Importar','Importar juegos','Ajustes de Xbox 360','Importando {name} ({index}/{count})…','Cancelar','{count} juego(s) de Xbox 360 importado(s).','Se omitieron {count} juego(s) que ya estaban en la biblioteca.','Importación cancelada. No se conservó ningún juego parcial.','{name}: {reason}',
 'perfil de XeniOS, no es un juego','diseño táctil de XeniOS, no es un juego','un .xex suelto necesita toda la carpeta del juego, que aún no se puede importar','archivo no compatible','archivo ilegible','no es una imagen de disco de Xbox 360','imagen de disco incompleta o dañada','espacio libre insuficiente','error al copiar',
 'Los juegos de Xbox 360 requieren iOS 26 o posterior.','El motor XeniOS no está incluido en esta versión de RewindBox.','El motor XeniOS de esta versión no coincide con RewindBox.','XeniOS solo funciona en iPhone y iPad.','XeniOS necesita JIT, que ahora no está disponible para RewindBox.','Ya hay otro juego en ejecución.','Reinicia RewindBox antes de iniciar otro juego de Xbox 360.','No se puede leer el archivo del juego.','No se pudo iniciar el juego en XeniOS.',
 'Ajustes de XeniOS','Todos los juegos de Xbox 360','Este juego','Los cambios se aplican la próxima vez que se inicie un juego.','Heredado de: {source}','valor predeterminado del motor','todos los juegos','este juego','Usar valores heredados','Restaurar valores del motor',
 'Activado','Desactivado','Automático','Sin límite','Consola','Pantalla','Audio','Sistema',
 'Idioma de la consola','Región de la consola','Sincronización PAL 50 Hz','Límite de fotogramas por segundo','Limitar la frecuencia de la pantalla invitada','Bandas negras (letterbox)','Compilar shaders en segundo plano','Búfer de audio (fotogramas)','Decodificador de audio','Unidad de caché',
 'Idioma que la consola indica a los juegos. Un perfil de XeniOS con sesión iniciada conserva su propio idioma. Automático sigue el idioma de RewindBox (inglés para el indonesio, que la Xbox 360 no ofrece).','Región que la consola indica a los juegos. Automático sigue la región del dispositivo (Estados Unidos si no es una región de Xbox 360).','El idioma de la interfaz de RewindBox es un ajuste aparte.','Nuevo','Antiguo','Master','Ajuste no guardado: {error}','Ajustes de XeniOS de este juego','Aún no hay juegos de Xbox 360','Importa tus juegos .iso o .zar desde Archivos con el botón de importar.','Esta versión de RewindBox incluye el motor XeniOS sin el Metal Shader Converter de Apple, necesario para mostrar los juegos.','Se necesita un archivo RemotePairing para activar el JIT de XeniOS.','El asistente JIT no pudo conectarse a RewindBox. Comprueba que LocalDevVPN esté conectado y vuelve a intentarlo.','El asistente JIT no terminó. Reinicia RewindBox y vuelve a intentarlo.'],
'it': ['XeniOS / Importa','Importa giochi','Impostazioni Xbox 360','Importazione di {name} ({index}/{count})…','Annulla','{count} gioco/giochi Xbox 360 importato/i.','{count} gioco/giochi già presenti nella libreria saltato/i.','Importazione annullata. Nessun gioco parziale è stato conservato.','{name}: {reason}',
 'profilo XeniOS, non è un gioco','layout touch XeniOS, non è un gioco','un .xex singolo richiede l’intera cartella del gioco, che non può ancora essere importata','file non supportato','file non leggibile','non è un’immagine disco Xbox 360','immagine disco incompleta o danneggiata','spazio libero insufficiente','copia non riuscita',
 'I giochi Xbox 360 richiedono iOS 26 o versioni successive.','Il motore XeniOS non è incluso in questa versione di RewindBox.','Il motore XeniOS di questa build non corrisponde a RewindBox.','XeniOS funziona solo su iPhone e iPad.','XeniOS richiede il JIT, che al momento non è disponibile per RewindBox.','Un altro gioco è già in esecuzione.','Riavvia RewindBox prima di avviare un altro gioco Xbox 360.','Il file del gioco non è leggibile.','Impossibile avviare il gioco in XeniOS.',
 'Impostazioni XeniOS','Tutti i giochi Xbox 360','Questo gioco','Le modifiche si applicano al prossimo avvio di un gioco.','Ereditato da: {source}','predefinito del motore','tutti i giochi','questo gioco','Usa i valori ereditati','Ripristina i valori del motore',
 'Attivo','Disattivo','Automatico','Illimitato','Console','Schermo','Audio','Sistema',
 'Lingua della console','Regione della console','Temporizzazione PAL 50 Hz','Limite fotogrammi al secondo','Limita l’aggiornamento dello schermo ospite','Bande nere (letterbox)','Compila gli shader in background','Buffer audio (fotogrammi)','Decodificatore audio','Unità cache',
 'Lingua che la console comunica ai giochi. Un profilo XeniOS connesso mantiene la propria lingua. Automatico segue la lingua di RewindBox (inglese per l’indonesiano, non offerto da Xbox 360).','Regione che la console comunica ai giochi. Automatico segue la regione del dispositivo (Stati Uniti se non è una regione Xbox 360).','La lingua dell’interfaccia di RewindBox è un’impostazione separata.','Nuovo','Vecchio','Master','Impostazione non salvata: {error}','Impostazioni XeniOS di questo gioco','Ancora nessun gioco Xbox 360','Importa i tuoi giochi .iso o .zar da File con il pulsante di importazione.','Questa versione di RewindBox contiene il motore XeniOS senza il Metal Shader Converter di Apple, necessario per visualizzare i giochi.','Per attivare il JIT di XeniOS serve un file RemotePairing.','L’assistente JIT non è riuscito a collegarsi a RewindBox. Verifica che LocalDevVPN sia connesso e riprova.','L’assistente JIT non ha terminato. Riavvia RewindBox e riprova.'],
'pt': ['XeniOS / Importar','Importar jogos','Ajustes do Xbox 360','Importando {name} ({index}/{count})…','Cancelar','{count} jogo(s) de Xbox 360 importado(s).','{count} jogo(s) já presente(s) na biblioteca ignorado(s).','Importação cancelada. Nenhum jogo parcial foi mantido.','{name}: {reason}',
 'perfil do XeniOS, não é um jogo','layout de toque do XeniOS, não é um jogo','um .xex avulso precisa de toda a pasta do jogo, que ainda não pode ser importada','arquivo não suportado','arquivo ilegível','não é uma imagem de disco de Xbox 360','imagem de disco incompleta ou danificada','espaço livre insuficiente','falha ao copiar',
 'Jogos de Xbox 360 exigem iOS 26 ou posterior.','O motor XeniOS não está incluído nesta versão do RewindBox.','O motor XeniOS desta versão não corresponde ao RewindBox.','O XeniOS funciona apenas no iPhone e no iPad.','O XeniOS precisa de JIT, que não está disponível para o RewindBox agora.','Outro jogo já está em execução.','Reinicie o RewindBox antes de iniciar outro jogo de Xbox 360.','Não é possível ler o arquivo do jogo.','Não foi possível iniciar o jogo no XeniOS.',
 'Ajustes do XeniOS','Todos os jogos de Xbox 360','Este jogo','As alterações valem na próxima vez que um jogo iniciar.','Herdado de: {source}','padrão do motor','todos os jogos','este jogo','Usar valores herdados','Restaurar padrões do motor',
 'Ativado','Desativado','Automático','Ilimitado','Console','Tela','Áudio','Sistema',
 'Idioma do console','Região do console','Temporização PAL 50 Hz','Limite de quadros por segundo','Limitar a atualização da tela convidada','Barras pretas (letterbox)','Compilar shaders em segundo plano','Buffer de áudio (quadros)','Decodificador de áudio','Unidade de cache',
 'Idioma que o console informa aos jogos. Um perfil do XeniOS conectado mantém o próprio idioma. Automático segue o idioma do RewindBox (inglês para indonésio, que o Xbox 360 não oferece).','Região que o console informa aos jogos. Automático segue a região do dispositivo (Estados Unidos se não for uma região do Xbox 360).','O idioma da interface do RewindBox é um ajuste separado.','Novo','Antigo','Master','Ajuste não salvo: {error}','Ajustes do XeniOS deste jogo','Ainda não há jogos de Xbox 360','Importe seus jogos .iso ou .zar do app Arquivos com o botão de importar.','Esta versão do RewindBox contém o motor XeniOS sem o Metal Shader Converter da Apple, necessário para exibir os jogos.','É necessário um arquivo RemotePairing para ativar o JIT do XeniOS.','O assistente de JIT não conseguiu se conectar ao RewindBox. Verifique se o LocalDevVPN está conectado e tente novamente.','O assistente de JIT não terminou. Reinicie o RewindBox e tente novamente.'],
'ru': ['XeniOS / Импорт','Импортировать игры','Настройки Xbox 360','Импорт {name} ({index}/{count})…','Отмена','Импортировано игр Xbox 360: {count}.','Пропущено игр, уже имеющихся в библиотеке: {count}.','Импорт отменён. Неполные игры не сохранены.','{name}: {reason}',
 'профиль XeniOS, а не игра','сенсорная раскладка XeniOS, а не игра','отдельному .xex нужна вся папка игры, импорт которой пока недоступен','неподдерживаемый файл','файл не читается','это не образ диска Xbox 360','образ диска неполный или повреждён','недостаточно свободного места','ошибка копирования',
 'Для игр Xbox 360 требуется iOS 26 или новее.','Движок XeniOS не входит в эту версию RewindBox.','Движок XeniOS в этой сборке не соответствует RewindBox.','XeniOS работает только на iPhone и iPad.','XeniOS требуется JIT, который сейчас недоступен для RewindBox.','Уже запущена другая игра.','Перезапустите RewindBox перед запуском другой игры Xbox 360.','Не удаётся прочитать файл игры.','Не удалось запустить игру в XeniOS.',
 'Настройки XeniOS','Все игры Xbox 360','Эта игра','Изменения применяются при следующем запуске игры.','Унаследовано от: {source}','значение движка по умолчанию','все игры','эта игра','Использовать унаследованные значения','Восстановить значения движка',
 'Вкл.','Выкл.','Автоматически','Без ограничения','Консоль','Экран','Звук','Система',
 'Язык консоли','Регион консоли','Режим PAL 50 Гц','Ограничение частоты кадров','Ограничить обновление гостевого экрана','Чёрные полосы (letterbox)','Компилировать шейдеры в фоне','Аудиобуфер (кадры)','Аудиодекодер','Кэш-диск',
 'Язык, который консоль сообщает играм. Вошедший профиль XeniOS сохраняет свой язык. «Автоматически» следует языку RewindBox (английский для индонезийского, которого нет на Xbox 360).','Регион, который консоль сообщает играм. «Автоматически» следует региону устройства (США, если это не регион Xbox 360).','Язык интерфейса RewindBox — отдельная настройка.','Новый','Старый','Master','Настройка не сохранена: {error}','Настройки XeniOS для этой игры','Игр Xbox 360 пока нет','Импортируйте игры .iso или .zar из «Файлов» кнопкой импорта.','Эта версия RewindBox содержит движок XeniOS без Metal Shader Converter от Apple, который нужен для вывода изображения игр.','Для включения JIT в XeniOS нужен файл RemotePairing.','Помощнику JIT не удалось подключиться к RewindBox. Убедитесь, что LocalDevVPN подключён, и повторите попытку.','Помощник JIT не завершил работу. Перезапустите RewindBox и повторите попытку.'],
'zh': ['XeniOS / 导入','导入游戏','Xbox 360 设置','正在导入 {name}（{index}/{count}）…','取消','已导入 {count} 款 Xbox 360 游戏。','已跳过 {count} 款库中已有的游戏。','导入已取消，未保留任何不完整的游戏。','{name}：{reason}',
 'XeniOS 配置文件，不是游戏','XeniOS 触控布局，不是游戏','单独的 .xex 需要完整的游戏文件夹，目前尚不支持导入文件夹','不支持的文件','文件无法读取','不是 Xbox 360 光盘镜像','光盘镜像不完整或已损坏','可用空间不足','复制失败',
 'Xbox 360 游戏需要 iOS 26 或更高版本。','此版本的 RewindBox 未包含 XeniOS 引擎。','此版本中的 XeniOS 引擎与 RewindBox 不匹配。','XeniOS 仅支持 iPhone 和 iPad。','XeniOS 需要 JIT，但 RewindBox 当前无法使用 JIT。','已有其他游戏正在运行。','请先重新启动 RewindBox，再启动另一款 Xbox 360 游戏。','无法读取游戏文件。','无法在 XeniOS 中启动该游戏。',
 'XeniOS 设置','所有 Xbox 360 游戏','此游戏','更改将在下次启动游戏时生效。','继承自：{source}','引擎默认值','所有游戏','此游戏','使用继承的值','恢复引擎默认值',
 '开','关','自动','不限','主机','显示','音频','系统',
 '主机语言','主机地区','PAL 50 Hz 时序','帧率上限','限制客体显示刷新率','黑边（Letterbox）','在后台编译着色器','音频缓冲（帧）','音频解码器','缓存驱动器',
 '主机向游戏报告的语言。已登录的 XeniOS 配置文件保留其自身语言。“自动”跟随 RewindBox 的语言（印尼语使用英语，因为 Xbox 360 不提供印尼语）。','主机向游戏报告的地区。“自动”跟随设备地区（若不属于 Xbox 360 地区则为美国）。','RewindBox 界面语言是单独的设置。','新','旧','Master','设置未保存：{error}','此游戏的 XeniOS 设置','还没有 Xbox 360 游戏','使用导入按钮从“文件”导入你的 .iso 或 .zar 游戏。','此版本的 RewindBox 包含 XeniOS 引擎，但缺少显示游戏所需的 Apple Metal Shader Converter。','需要 RemotePairing 文件才能为 XeniOS 启用 JIT。','JIT 助手无法连接到 RewindBox。请确认 LocalDevVPN 已连接，然后重试。','JIT 助手未完成。请重新启动 RewindBox 后重试。'],
'zh_Hant': ['XeniOS / 匯入','匯入遊戲','Xbox 360 設定','正在匯入 {name}（{index}/{count}）…','取消','已匯入 {count} 款 Xbox 360 遊戲。','已略過 {count} 款遊戲庫中已有的遊戲。','匯入已取消，未保留任何不完整的遊戲。','{name}：{reason}',
 'XeniOS 設定檔，不是遊戲','XeniOS 觸控配置，不是遊戲','單獨的 .xex 需要完整的遊戲資料夾，目前尚不支援匯入資料夾','不支援的檔案','無法讀取檔案','不是 Xbox 360 光碟映像檔','光碟映像檔不完整或已損毀','可用空間不足','複製失敗',
 'Xbox 360 遊戲需要 iOS 26 或以上版本。','此版本的 RewindBox 未包含 XeniOS 引擎。','此版本中的 XeniOS 引擎與 RewindBox 不相符。','XeniOS 僅支援 iPhone 與 iPad。','XeniOS 需要 JIT，但 RewindBox 目前無法使用 JIT。','已有其他遊戲正在執行。','請先重新啟動 RewindBox，再啟動另一款 Xbox 360 遊戲。','無法讀取遊戲檔案。','無法在 XeniOS 中啟動此遊戲。',
 'XeniOS 設定','所有 Xbox 360 遊戲','此遊戲','變更將於下次啟動遊戲時生效。','繼承自：{source}','引擎預設值','所有遊戲','此遊戲','使用繼承的值','還原引擎預設值',
 '開','關','自動','不限','主機','顯示','音訊','系統',
 '主機語言','主機地區','PAL 50 Hz 時序','影格率上限','限制客體顯示更新率','黑邊（Letterbox）','在背景編譯著色器','音訊緩衝（影格）','音訊解碼器','快取磁碟',
 '主機向遊戲回報的語言。已登入的 XeniOS 設定檔會保留自己的語言。「自動」會跟隨 RewindBox 的語言（印尼文使用英文，因為 Xbox 360 未提供印尼文）。','主機向遊戲回報的地區。「自動」會跟隨裝置地區（若不屬於 Xbox 360 地區則為美國）。','RewindBox 介面語言是獨立的設定。','新','舊','Master','設定未儲存：{error}','此遊戲的 XeniOS 設定','尚無 Xbox 360 遊戲','使用匯入按鈕從「檔案」匯入你的 .iso 或 .zar 遊戲。','此版本的 RewindBox 包含 XeniOS 引擎，但缺少顯示遊戲所需的 Apple Metal Shader Converter。','需要 RemotePairing 檔案才能為 XeniOS 啟用 JIT。','JIT 輔助程式無法連接到 RewindBox。請確認 LocalDevVPN 已連線，然後再試一次。','JIT 輔助程式未完成。請重新啟動 RewindBox 後再試一次。'],
'ja': ['XeniOS / 読み込み','ゲームを読み込む','Xbox 360 の設定','{name} を読み込み中（{index}/{count}）…','キャンセル','Xbox 360 のゲームを {count} 本読み込みました。','ライブラリに既にある {count} 本をスキップしました。','読み込みをキャンセルしました。途中までのゲームは残していません。','{name}：{reason}',
 'XeniOS プロフィールでありゲームではありません','XeniOS タッチレイアウトでありゲームではありません','単体の .xex にはゲームフォルダ全体が必要ですが、フォルダの読み込みにはまだ対応していません','対応していないファイル','ファイルを読み取れません','Xbox 360 のディスクイメージではありません','ディスクイメージが不完全か破損しています','空き容量が不足しています','コピーに失敗しました',
 'Xbox 360 のゲームには iOS 26 以降が必要です。','このバージョンの RewindBox には XeniOS エンジンが含まれていません。','このビルドの XeniOS エンジンは RewindBox と一致しません。','XeniOS は iPhone と iPad でのみ動作します。','XeniOS には JIT が必要ですが、現在 RewindBox では利用できません。','別のゲームが既に実行中です。','別の Xbox 360 ゲームを起動する前に RewindBox を再起動してください。','ゲームファイルを読み取れません。','XeniOS でゲームを起動できませんでした。',
 'XeniOS の設定','すべての Xbox 360 ゲーム','このゲーム','変更は次にゲームを起動したときに反映されます。','継承元：{source}','エンジンの既定値','すべてのゲーム','このゲーム','継承した値を使用','エンジンの既定値に戻す',
 'オン','オフ','自動','無制限','本体','表示','オーディオ','システム',
 '本体の言語','本体の地域','PAL 50 Hz タイミング','フレームレート上限','ゲスト表示のリフレッシュを制限','レターボックス','シェーダーをバックグラウンドでコンパイル','オーディオバッファ（フレーム）','オーディオデコーダ','キャッシュドライブ',
 '本体がゲームに通知する言語です。サインイン中の XeniOS プロフィールは独自の言語を保持します。「自動」は RewindBox の言語に従います（Xbox 360 にないインドネシア語の場合は英語）。','本体がゲームに通知する地域です。「自動」はデバイスの地域に従います（Xbox 360 の地域でない場合は米国）。','RewindBox のインターフェース言語は別の設定です。','新','旧','Master','設定を保存できませんでした：{error}','このゲームの XeniOS 設定','Xbox 360 のゲームはまだありません','読み込みボタンで「ファイル」から .iso または .zar のゲームを読み込んでください。','このバージョンの RewindBox には XeniOS エンジンが含まれていますが、ゲームの表示に必要な Apple の Metal Shader Converter がありません。','XeniOS の JIT を有効にするには RemotePairing ファイルが必要です。','JIT ヘルパーが RewindBox に接続できませんでした。LocalDevVPN が接続されていることを確認してから、もう一度お試しください。','JIT ヘルパーが完了しませんでした。RewindBox を再起動してから、もう一度お試しください。'],
'ko': ['XeniOS / 가져오기','게임 가져오기','Xbox 360 설정','{name} 가져오는 중({index}/{count})…','취소','Xbox 360 게임 {count}개를 가져왔습니다.','라이브러리에 이미 있는 게임 {count}개를 건너뛰었습니다.','가져오기가 취소되었습니다. 불완전한 게임은 남기지 않았습니다.','{name}: {reason}',
 'XeniOS 프로필이며 게임이 아님','XeniOS 터치 레이아웃이며 게임이 아님','단독 .xex에는 게임 폴더 전체가 필요하지만 폴더 가져오기는 아직 지원되지 않음','지원되지 않는 파일','파일을 읽을 수 없음','Xbox 360 디스크 이미지가 아님','디스크 이미지가 불완전하거나 손상됨','여유 공간 부족','복사 실패',
 'Xbox 360 게임에는 iOS 26 이상이 필요합니다.','이 버전의 RewindBox에는 XeniOS 엔진이 포함되어 있지 않습니다.','이 빌드의 XeniOS 엔진이 RewindBox와 일치하지 않습니다.','XeniOS는 iPhone과 iPad에서만 실행됩니다.','XeniOS에는 JIT가 필요하지만 지금은 RewindBox에서 사용할 수 없습니다.','다른 게임이 이미 실행 중입니다.','다른 Xbox 360 게임을 시작하기 전에 RewindBox를 다시 시작하세요.','게임 파일을 읽을 수 없습니다.','XeniOS에서 게임을 시작하지 못했습니다.',
 'XeniOS 설정','모든 Xbox 360 게임','이 게임','변경 사항은 다음에 게임을 시작할 때 적용됩니다.','상속 출처: {source}','엔진 기본값','모든 게임','이 게임','상속된 값 사용','엔진 기본값 복원',
 '켬','끔','자동','제한 없음','콘솔','화면','오디오','시스템',
 '콘솔 언어','콘솔 지역','PAL 50Hz 타이밍','프레임 속도 제한','게스트 화면 새로 고침 제한','레터박스','백그라운드에서 셰이더 컴파일','오디오 버퍼(프레임)','오디오 디코더','캐시 드라이브',
 '콘솔이 게임에 알리는 언어입니다. 로그인한 XeniOS 프로필은 자체 언어를 유지합니다. 자동은 RewindBox 언어를 따릅니다(Xbox 360에 없는 인도네시아어는 영어).','콘솔이 게임에 알리는 지역입니다. 자동은 기기 지역을 따릅니다(Xbox 360 지역이 아니면 미국).','RewindBox 인터페이스 언어는 별도의 설정입니다.','신규','이전','Master','설정이 저장되지 않음: {error}','이 게임의 XeniOS 설정','아직 Xbox 360 게임이 없습니다','가져오기 버튼으로 파일 앱에서 .iso 또는 .zar 게임을 가져오세요.','이 버전의 RewindBox에는 XeniOS 엔진이 포함되어 있지만 게임 표시에 필요한 Apple Metal Shader Converter가 없습니다.','XeniOS의 JIT를 사용하려면 RemotePairing 파일이 필요합니다.','JIT 도우미가 RewindBox에 연결하지 못했습니다. LocalDevVPN이 연결되어 있는지 확인한 후 다시 시도하세요.','JIT 도우미가 완료되지 않았습니다. RewindBox를 다시 시작한 후 다시 시도하세요.'],
'id': ['XeniOS / Impor','Impor game','Pengaturan Xbox 360','Mengimpor {name} ({index}/{count})…','Batal','{count} game Xbox 360 diimpor.','{count} game yang sudah ada di pustaka dilewati.','Impor dibatalkan. Tidak ada game sebagian yang disimpan.','{name}: {reason}',
 'profil XeniOS, bukan game','tata letak sentuh XeniOS, bukan game','.xex terpisah memerlukan seluruh folder gamenya, yang belum dapat diimpor','file tidak didukung','file tidak dapat dibaca','bukan image disk Xbox 360','image disk tidak lengkap atau rusak','ruang kosong tidak cukup','gagal menyalin',
 'Game Xbox 360 memerlukan iOS 26 atau yang lebih baru.','Mesin XeniOS tidak disertakan di versi RewindBox ini.','Mesin XeniOS di build ini tidak cocok dengan RewindBox.','XeniOS hanya berjalan di iPhone dan iPad.','XeniOS memerlukan JIT, yang saat ini tidak tersedia untuk RewindBox.','Game lain sedang berjalan.','Mulai ulang RewindBox sebelum menjalankan game Xbox 360 lain.','File game tidak dapat dibaca.','Game tidak dapat dijalankan di XeniOS.',
 'Pengaturan XeniOS','Semua game Xbox 360','Game ini','Perubahan berlaku saat game berikutnya dijalankan.','Diwarisi dari: {source}','bawaan mesin','semua game','game ini','Gunakan nilai warisan','Pulihkan bawaan mesin',
 'Aktif','Nonaktif','Otomatis','Tanpa batas','Konsol','Tampilan','Audio','Sistem',
 'Bahasa konsol','Wilayah konsol','Pewaktuan PAL 50 Hz','Batas frame rate','Batasi penyegaran layar tamu','Letterbox','Kompilasi shader di latar belakang','Buffer audio (frame)','Dekoder audio','Drive cache',
 'Bahasa yang dilaporkan konsol ke game. Profil XeniOS yang masuk mempertahankan bahasanya sendiri. Otomatis mengikuti bahasa RewindBox (bahasa Inggris untuk bahasa Indonesia, yang tidak tersedia di Xbox 360).','Wilayah yang dilaporkan konsol ke game. Otomatis mengikuti wilayah perangkat (Amerika Serikat jika bukan wilayah Xbox 360).','Bahasa antarmuka RewindBox adalah pengaturan terpisah.','Baru','Lama','Master','Pengaturan tidak tersimpan: {error}','Pengaturan XeniOS untuk game ini','Belum ada game Xbox 360','Impor game .iso atau .zar dari Files dengan tombol impor.','Versi RewindBox ini berisi mesin XeniOS tanpa Metal Shader Converter dari Apple, yang diperlukan untuk menampilkan game.','File RemotePairing diperlukan untuk mengaktifkan JIT XeniOS.','Pembantu JIT tidak dapat terhubung ke RewindBox. Pastikan LocalDevVPN tersambung, lalu coba lagi.','Pembantu JIT tidak selesai. Mulai ulang RewindBox, lalu coba lagi.'],
}

order = ['en','es','ru','zh','zh_Hant','pt','fr','de','it','id','ja','ko']
for code in order:
    assert len(T[code]) == len(KEYS), (code, len(T[code]), len(KEYS))

def dart(s):
    return json.dumps(s, ensure_ascii=False).replace('$', '\\$')

out = ["// Generated by the XeniOS playlist work (12 project locales). Edit the",
       "// values here; keep every key in every locale (test/xenia_locale_test.dart).",
       "import 'package:flutter/widgets.dart';", "",
       "abstract final class XeniaLocale {",
       "  static const Map<String, Map<String, String>> values = <String, Map<String, String>>{"]
for code in order:
    out.append(f"    '{code}': <String, String>{{")
    for k, v in zip(KEYS, T[code]):
        out.append(f"      '{k}': {dart(v)},")
    out.append("    },")
out.append("  };")
out.append('''
  /// `zh_Hant` for Traditional Chinese (script Hant, or Taiwan, Hong Kong,
  /// Macao); English for languages outside the 12 project locales.
  static String codeFor(Locale locale) {
    var code = locale.languageCode;
    if (code == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' || country == 'TW' || country == 'HK' || country == 'MO') {
        code = 'zh_Hant';
      }
    }
    return values.containsKey(code) ? code : 'en';
  }

  /// Localized key for a launch failure of XeniaInternalService.launch:
  /// the stable error itself when it has a message, otherwise the generic
  /// failure (technical stages stay in the diagnostic details).
  static String launchErrorKey(String? error) => switch (error) {
    'requiresIOS26' ||
    'engineMissing' ||
    'abiMismatch' ||
    'unsupportedPlatform' ||
    'jitUnavailable' ||
    'sessionActive' ||
    'restartRequired' ||
    'gameUnreadable' ||
    'shaderConverterMissing' ||
    'pairingRequired' ||
    'jitAttachFailed' ||
    'jitHelperIncomplete' => error!,
    'jitHandshakeFailed' => 'jitAttachFailed',
    'jitDetachFailed' => 'jitHelperIncomplete',
    _ => 'launchFailed',
  };

  static String forLocale(Locale locale, String key) =>
      values[codeFor(locale)]?[key] ?? values['en']![key] ?? key;

  static String format(Locale locale, String key, Map<String, Object?> parameters) {
    var value = forLocale(locale, key);
    for (final entry in parameters.entries) {
      value = value.replaceAll('{${entry.key}}', entry.value?.toString() ?? '');
    }
    return value;
  }

  static String text(BuildContext context, String key) =>
      forLocale(Localizations.maybeLocaleOf(context) ?? const Locale('en'), key);

  static String textf(BuildContext context, String key, Map<String, Object?> parameters) =>
      format(Localizations.maybeLocaleOf(context) ?? const Locale('en'), key, parameters);
}''')
open(sys.argv[1], 'w').write('\n'.join(out) + '\n')
