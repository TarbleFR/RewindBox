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
 'shaderConverterMissing','pairingRequired','jitAttachFailed','jitHelperIncomplete','session_menu','session_resume','session_quit',
 'importFolder','folderNoGame','executableInvalid','packageDataMissing','packageIncomplete','packageNotGame',
 'coreLoadFailed',
]

T = {
'en': ['XeniOS / Import','Import games','Xbox 360 settings','Importing {name} ({index}/{count})…','Cancel','{count} Xbox 360 game(s) imported.','{count} game(s) already in the library were skipped.','Import cancelled. No partial game was kept.','{name}: {reason}',
 'XeniOS profile, not a game','XeniOS touch layout, not a game','a loose .xex or a package header needs its whole game folder: use Import a game folder','unsupported file','file not readable','not an Xbox 360 disc image','incomplete or damaged disc image','not enough free space','copy failed',
 'Xbox 360 games require iOS 26 or later.','The XeniOS engine is not included in this version of RewindBox.','The XeniOS engine in this build does not match RewindBox.','XeniOS runs on iPhone and iPad only.','XeniOS needs JIT, which is not available to RewindBox right now.','Another game is already running.','Restart RewindBox before starting another Xbox 360 game.','The game file cannot be read.','The game could not be started in XeniOS.',
 'XeniOS settings','All Xbox 360 games','This game','Changes apply the next time a game starts.','Inherited from: {source}','engine default','all games','this game','Use inherited values','Restore engine defaults',
 'On','Off','Automatic','Unlimited','Console','Display','Audio','System',
 'Console language','Console region','PAL 50 Hz timing','Frame rate limit','Cap guest display refresh','Letterbox','Compile shaders in background','Audio buffer (frames)','Audio decoder','Cache drive',
 'Language the console reports to games. A signed-in XeniOS profile keeps its own language. Automatic follows the RewindBox language (English for Indonesian, which the Xbox 360 does not offer).','Region the console reports to games. Automatic follows the device region (United States when it is not an Xbox 360 region).','The RewindBox interface language is a separate setting.','New','Old','Master','Setting not saved: {error}','XeniOS settings for this game','No Xbox 360 games yet','Import your .iso or .zar games, or a game folder (default.xex or Games on Demand), from Files with the import button.',"This version of RewindBox contains the XeniOS engine without Apple's Metal Shader Converter, which it needs to display games.",'A RemotePairing file is required to enable JIT for XeniOS.','The JIT helper could not attach to RewindBox. Check that LocalDevVPN is connected, then try again.','The JIT helper did not finish. Restart RewindBox, then try again.','Menu','Resume','Quit game','Import a game folder (XEX/GOD)','no default.xex folder or Xbox 360 game package in this folder','default.xex is not a readable Xbox 360 executable','Games on Demand header without its .data folder','Games on Demand package incomplete: its .data folder does not hold every data file','Xbox 360 package that is not a game (save, add-on, update or original Xbox title)','The XeniOS engine of this build could not be loaded. Restart RewindBox; if it happens again, this build cannot run Xbox 360 games.'],
'fr': ['XeniOS / Importer','Importer des jeux','Réglages Xbox 360','Import de {name} ({index}/{count})…','Annuler','{count} jeu(x) Xbox 360 importé(s).','{count} jeu(x) déjà présent(s) dans la bibliothèque ignoré(s).','Import annulé. Aucun jeu partiel n’a été conservé.','{name} : {reason}',
 'profil XeniOS, pas un jeu','disposition tactile XeniOS, pas un jeu','un .xex isolé ou un en-tête de paquet a besoin de tout le dossier du jeu : utilisez Importer un dossier de jeu','fichier non pris en charge','fichier illisible','pas une image disque Xbox 360','image disque incomplète ou endommagée','espace libre insuffisant','échec de la copie',
 'Les jeux Xbox 360 nécessitent iOS 26 ou une version ultérieure.','Le moteur XeniOS n’est pas inclus dans cette version de RewindBox.','Le moteur XeniOS de cette version ne correspond pas à RewindBox.','XeniOS fonctionne uniquement sur iPhone et iPad.','XeniOS a besoin du JIT, qui n’est pas disponible pour RewindBox actuellement.','Un autre jeu est déjà en cours.','Redémarrez RewindBox avant de lancer un autre jeu Xbox 360.','Le fichier du jeu est illisible.','Le jeu n’a pas pu démarrer dans XeniOS.',
 'Réglages XeniOS','Tous les jeux Xbox 360','Ce jeu','Les changements s’appliquent au prochain lancement d’un jeu.','Hérité de : {source}','valeur par défaut du moteur','tous les jeux','ce jeu','Utiliser les valeurs héritées','Rétablir les valeurs du moteur',
 'Activé','Désactivé','Automatique','Illimitée','Console','Affichage','Audio','Système',
 'Langue de la console','Région de la console','Fréquence PAL 50 Hz','Limite d’images par seconde','Limiter le rafraîchissement de l’affichage invité','Bandes noires (letterbox)','Compiler les shaders en arrière-plan','Tampon audio (images)','Décodeur audio','Disque cache',
 'Langue que la console indique aux jeux. Un profil XeniOS connecté conserve sa propre langue. Automatique suit la langue de RewindBox (anglais pour l’indonésien, absent de la Xbox 360).','Région que la console indique aux jeux. Automatique suit la région de l’appareil (États-Unis si ce n’est pas une région Xbox 360).','La langue de l’interface RewindBox est un réglage distinct.','Nouveau','Ancien','Master','Réglage non enregistré : {error}','Réglages XeniOS de ce jeu','Aucun jeu Xbox 360 pour l’instant','Importez depuis Fichiers vos jeux .iso ou .zar, ou un dossier de jeu (default.xex ou Games on Demand), avec le bouton d’import.','Cette version de RewindBox contient le moteur XeniOS sans le Metal Shader Converter d’Apple, nécessaire à l’affichage des jeux.','Un fichier RemotePairing est nécessaire pour activer le JIT de XeniOS.','L’assistant JIT n’a pas pu s’attacher à RewindBox. Vérifiez que LocalDevVPN est connecté, puis réessayez.','L’assistant JIT n’a pas terminé. Redémarrez RewindBox, puis réessayez.','Menu','Reprendre','Quitter le jeu','Importer un dossier de jeu (XEX/GOD)','aucun dossier default.xex ni paquet de jeu Xbox 360 dans ce dossier','default.xex n’est pas un exécutable Xbox 360 lisible','en-tête Games on Demand sans son dossier .data','paquet Games on Demand incomplet : son dossier .data ne contient pas tous les fichiers de données','paquet Xbox 360 qui n’est pas un jeu (sauvegarde, extension, mise à jour ou jeu Xbox d’origine)','Le moteur XeniOS de cette version n’a pas pu être chargé. Redémarrez RewindBox ; si cela se reproduit, cette version ne peut pas lancer de jeux Xbox 360.'],
'de': ['XeniOS / Import','Spiele importieren','Xbox-360-Einstellungen','{name} wird importiert ({index}/{count})…','Abbrechen','{count} Xbox-360-Spiel(e) importiert.','{count} bereits vorhandene(s) Spiel(e) übersprungen.','Import abgebrochen. Kein unvollständiges Spiel wurde behalten.','{name}: {reason}',
 'XeniOS-Profil, kein Spiel','XeniOS-Touch-Layout, kein Spiel','eine einzelne .xex oder ein Paket-Header braucht den ganzen Spielordner: verwende Spielordner importieren','nicht unterstützte Datei','Datei nicht lesbar','kein Xbox-360-Disc-Image','unvollständiges oder beschädigtes Disc-Image','nicht genug freier Speicher','Kopieren fehlgeschlagen',
 'Xbox-360-Spiele erfordern iOS 26 oder neuer.','Die XeniOS-Engine ist in dieser RewindBox-Version nicht enthalten.','Die XeniOS-Engine dieses Builds passt nicht zu RewindBox.','XeniOS läuft nur auf iPhone und iPad.','XeniOS benötigt JIT, das RewindBox gerade nicht zur Verfügung steht.','Es läuft bereits ein anderes Spiel.','Starte RewindBox neu, bevor du ein weiteres Xbox-360-Spiel startest.','Die Spieldatei ist nicht lesbar.','Das Spiel konnte in XeniOS nicht gestartet werden.',
 'XeniOS-Einstellungen','Alle Xbox-360-Spiele','Dieses Spiel','Änderungen gelten beim nächsten Spielstart.','Übernommen von: {source}','Engine-Standard','alle Spiele','dieses Spiel','Übernommene Werte verwenden','Engine-Standards wiederherstellen',
 'Ein','Aus','Automatisch','Unbegrenzt','Konsole','Anzeige','Audio','System',
 'Konsolensprache','Konsolenregion','PAL-50-Hz-Timing','Bildratenlimit','Gast-Bildwiederholrate begrenzen','Letterbox','Shader im Hintergrund kompilieren','Audiopuffer (Frames)','Audiodecoder','Cache-Laufwerk',
 'Sprache, die die Konsole den Spielen meldet. Ein angemeldetes XeniOS-Profil behält seine eigene Sprache. Automatisch folgt der RewindBox-Sprache (Englisch für Indonesisch, das die Xbox 360 nicht anbietet).','Region, die die Konsole den Spielen meldet. Automatisch folgt der Geräteregion (USA, wenn sie keine Xbox-360-Region ist).','Die Sprache der RewindBox-Oberfläche ist eine eigene Einstellung.','Neu','Alt','Master','Einstellung nicht gespeichert: {error}','XeniOS-Einstellungen für dieses Spiel','Noch keine Xbox-360-Spiele','Importiere deine .iso- oder .zar-Spiele oder einen Spielordner (default.xex oder Games on Demand) mit der Import-Taste aus Dateien.','Diese RewindBox-Version enthält die XeniOS-Engine ohne Apples Metal Shader Converter, den sie zur Anzeige von Spielen benötigt.','Für den XeniOS-JIT wird eine RemotePairing-Datei benötigt.','Der JIT-Helfer konnte sich nicht mit RewindBox verbinden. Prüfe, ob LocalDevVPN verbunden ist, und versuche es erneut.','Der JIT-Helfer wurde nicht abgeschlossen. Starte RewindBox neu und versuche es erneut.','Menü','Fortsetzen','Spiel beenden','Spielordner importieren (XEX/GOD)','kein default.xex-Ordner und kein Xbox-360-Spielpaket in diesem Ordner','default.xex ist keine lesbare Xbox-360-Programmdatei','Games-on-Demand-Header ohne seinen .data-Ordner','Games-on-Demand-Paket unvollständig: sein .data-Ordner enthält nicht alle Datendateien','Xbox-360-Paket, das kein Spiel ist (Spielstand, Erweiterung, Update oder Spiel der ersten Xbox)','Die XeniOS-Engine dieses Builds konnte nicht geladen werden. Starte RewindBox neu; passiert es wieder, kann dieser Build keine Xbox-360-Spiele starten.'],
'es': ['XeniOS / Importar','Importar juegos','Ajustes de Xbox 360','Importando {name} ({index}/{count})…','Cancelar','{count} juego(s) de Xbox 360 importado(s).','Se omitieron {count} juego(s) que ya estaban en la biblioteca.','Importación cancelada. No se conservó ningún juego parcial.','{name}: {reason}',
 'perfil de XeniOS, no es un juego','diseño táctil de XeniOS, no es un juego','un .xex suelto o una cabecera de paquete necesita toda la carpeta del juego: usa Importar una carpeta de juego','archivo no compatible','archivo ilegible','no es una imagen de disco de Xbox 360','imagen de disco incompleta o dañada','espacio libre insuficiente','error al copiar',
 'Los juegos de Xbox 360 requieren iOS 26 o posterior.','El motor XeniOS no está incluido en esta versión de RewindBox.','El motor XeniOS de esta versión no coincide con RewindBox.','XeniOS solo funciona en iPhone y iPad.','XeniOS necesita JIT, que ahora no está disponible para RewindBox.','Ya hay otro juego en ejecución.','Reinicia RewindBox antes de iniciar otro juego de Xbox 360.','No se puede leer el archivo del juego.','No se pudo iniciar el juego en XeniOS.',
 'Ajustes de XeniOS','Todos los juegos de Xbox 360','Este juego','Los cambios se aplican la próxima vez que se inicie un juego.','Heredado de: {source}','valor predeterminado del motor','todos los juegos','este juego','Usar valores heredados','Restaurar valores del motor',
 'Activado','Desactivado','Automático','Sin límite','Consola','Pantalla','Audio','Sistema',
 'Idioma de la consola','Región de la consola','Sincronización PAL 50 Hz','Límite de fotogramas por segundo','Limitar la frecuencia de la pantalla invitada','Bandas negras (letterbox)','Compilar shaders en segundo plano','Búfer de audio (fotogramas)','Decodificador de audio','Unidad de caché',
 'Idioma que la consola indica a los juegos. Un perfil de XeniOS con sesión iniciada conserva su propio idioma. Automático sigue el idioma de RewindBox (inglés para el indonesio, que la Xbox 360 no ofrece).','Región que la consola indica a los juegos. Automático sigue la región del dispositivo (Estados Unidos si no es una región de Xbox 360).','El idioma de la interfaz de RewindBox es un ajuste aparte.','Nuevo','Antiguo','Master','Ajuste no guardado: {error}','Ajustes de XeniOS de este juego','Aún no hay juegos de Xbox 360','Importa desde Archivos tus juegos .iso o .zar, o una carpeta de juego (default.xex o Games on Demand), con el botón de importar.','Esta versión de RewindBox incluye el motor XeniOS sin el Metal Shader Converter de Apple, necesario para mostrar los juegos.','Se necesita un archivo RemotePairing para activar el JIT de XeniOS.','El asistente JIT no pudo conectarse a RewindBox. Comprueba que LocalDevVPN esté conectado y vuelve a intentarlo.','El asistente JIT no terminó. Reinicia RewindBox y vuelve a intentarlo.','Menú','Reanudar','Salir del juego','Importar una carpeta de juego (XEX/GOD)','no hay ninguna carpeta con default.xex ni paquete de juego de Xbox 360 en esta carpeta','default.xex no es un ejecutable de Xbox 360 legible','cabecera de Games on Demand sin su carpeta .data','paquete de Games on Demand incompleto: su carpeta .data no contiene todos los archivos de datos','paquete de Xbox 360 que no es un juego (partida guardada, complemento, actualización o juego de la Xbox original)','No se pudo cargar el motor XeniOS de esta versión. Reinicia RewindBox; si vuelve a ocurrir, esta versión no puede ejecutar juegos de Xbox 360.'],
'it': ['XeniOS / Importa','Importa giochi','Impostazioni Xbox 360','Importazione di {name} ({index}/{count})…','Annulla','{count} gioco/giochi Xbox 360 importato/i.','{count} gioco/giochi già presenti nella libreria saltato/i.','Importazione annullata. Nessun gioco parziale è stato conservato.','{name}: {reason}',
 'profilo XeniOS, non è un gioco','layout touch XeniOS, non è un gioco','un .xex singolo o un’intestazione di pacchetto richiede l’intera cartella del gioco: usa Importa una cartella di gioco','file non supportato','file non leggibile','non è un’immagine disco Xbox 360','immagine disco incompleta o danneggiata','spazio libero insufficiente','copia non riuscita',
 'I giochi Xbox 360 richiedono iOS 26 o versioni successive.','Il motore XeniOS non è incluso in questa versione di RewindBox.','Il motore XeniOS di questa build non corrisponde a RewindBox.','XeniOS funziona solo su iPhone e iPad.','XeniOS richiede il JIT, che al momento non è disponibile per RewindBox.','Un altro gioco è già in esecuzione.','Riavvia RewindBox prima di avviare un altro gioco Xbox 360.','Il file del gioco non è leggibile.','Impossibile avviare il gioco in XeniOS.',
 'Impostazioni XeniOS','Tutti i giochi Xbox 360','Questo gioco','Le modifiche si applicano al prossimo avvio di un gioco.','Ereditato da: {source}','predefinito del motore','tutti i giochi','questo gioco','Usa i valori ereditati','Ripristina i valori del motore',
 'Attivo','Disattivo','Automatico','Illimitato','Console','Schermo','Audio','Sistema',
 'Lingua della console','Regione della console','Temporizzazione PAL 50 Hz','Limite fotogrammi al secondo','Limita l’aggiornamento dello schermo ospite','Bande nere (letterbox)','Compila gli shader in background','Buffer audio (fotogrammi)','Decodificatore audio','Unità cache',
 'Lingua che la console comunica ai giochi. Un profilo XeniOS connesso mantiene la propria lingua. Automatico segue la lingua di RewindBox (inglese per l’indonesiano, non offerto da Xbox 360).','Regione che la console comunica ai giochi. Automatico segue la regione del dispositivo (Stati Uniti se non è una regione Xbox 360).','La lingua dell’interfaccia di RewindBox è un’impostazione separata.','Nuovo','Vecchio','Master','Impostazione non salvata: {error}','Impostazioni XeniOS di questo gioco','Ancora nessun gioco Xbox 360','Importa da File i tuoi giochi .iso o .zar, o una cartella di gioco (default.xex o Games on Demand), con il pulsante di importazione.','Questa versione di RewindBox contiene il motore XeniOS senza il Metal Shader Converter di Apple, necessario per visualizzare i giochi.','Per attivare il JIT di XeniOS serve un file RemotePairing.','L’assistente JIT non è riuscito a collegarsi a RewindBox. Verifica che LocalDevVPN sia connesso e riprova.','L’assistente JIT non ha terminato. Riavvia RewindBox e riprova.','Menu','Riprendi','Esci dal gioco','Importa una cartella di gioco (XEX/GOD)','nessuna cartella con default.xex né pacchetto di gioco Xbox 360 in questa cartella','default.xex non è un eseguibile Xbox 360 leggibile','intestazione Games on Demand senza la sua cartella .data','pacchetto Games on Demand incompleto: la sua cartella .data non contiene tutti i file di dati','pacchetto Xbox 360 che non è un gioco (salvataggio, espansione, aggiornamento o gioco della prima Xbox)','Impossibile caricare il motore XeniOS di questa build. Riavvia RewindBox; se succede di nuovo, questa build non può avviare giochi Xbox 360.'],
'pt': ['XeniOS / Importar','Importar jogos','Ajustes do Xbox 360','Importando {name} ({index}/{count})…','Cancelar','{count} jogo(s) de Xbox 360 importado(s).','{count} jogo(s) já presente(s) na biblioteca ignorado(s).','Importação cancelada. Nenhum jogo parcial foi mantido.','{name}: {reason}',
 'perfil do XeniOS, não é um jogo','layout de toque do XeniOS, não é um jogo','um .xex avulso ou um cabeçalho de pacote precisa de toda a pasta do jogo: use Importar uma pasta de jogo','arquivo não suportado','arquivo ilegível','não é uma imagem de disco de Xbox 360','imagem de disco incompleta ou danificada','espaço livre insuficiente','falha ao copiar',
 'Jogos de Xbox 360 exigem iOS 26 ou posterior.','O motor XeniOS não está incluído nesta versão do RewindBox.','O motor XeniOS desta versão não corresponde ao RewindBox.','O XeniOS funciona apenas no iPhone e no iPad.','O XeniOS precisa de JIT, que não está disponível para o RewindBox agora.','Outro jogo já está em execução.','Reinicie o RewindBox antes de iniciar outro jogo de Xbox 360.','Não é possível ler o arquivo do jogo.','Não foi possível iniciar o jogo no XeniOS.',
 'Ajustes do XeniOS','Todos os jogos de Xbox 360','Este jogo','As alterações valem na próxima vez que um jogo iniciar.','Herdado de: {source}','padrão do motor','todos os jogos','este jogo','Usar valores herdados','Restaurar padrões do motor',
 'Ativado','Desativado','Automático','Ilimitado','Console','Tela','Áudio','Sistema',
 'Idioma do console','Região do console','Temporização PAL 50 Hz','Limite de quadros por segundo','Limitar a atualização da tela convidada','Barras pretas (letterbox)','Compilar shaders em segundo plano','Buffer de áudio (quadros)','Decodificador de áudio','Unidade de cache',
 'Idioma que o console informa aos jogos. Um perfil do XeniOS conectado mantém o próprio idioma. Automático segue o idioma do RewindBox (inglês para indonésio, que o Xbox 360 não oferece).','Região que o console informa aos jogos. Automático segue a região do dispositivo (Estados Unidos se não for uma região do Xbox 360).','O idioma da interface do RewindBox é um ajuste separado.','Novo','Antigo','Master','Ajuste não salvo: {error}','Ajustes do XeniOS deste jogo','Ainda não há jogos de Xbox 360','Importe do app Arquivos seus jogos .iso ou .zar, ou uma pasta de jogo (default.xex ou Games on Demand), com o botão de importar.','Esta versão do RewindBox contém o motor XeniOS sem o Metal Shader Converter da Apple, necessário para exibir os jogos.','É necessário um arquivo RemotePairing para ativar o JIT do XeniOS.','O assistente de JIT não conseguiu se conectar ao RewindBox. Verifique se o LocalDevVPN está conectado e tente novamente.','O assistente de JIT não terminou. Reinicie o RewindBox e tente novamente.','Menu','Retomar','Sair do jogo','Importar uma pasta de jogo (XEX/GOD)','nenhuma pasta com default.xex nem pacote de jogo de Xbox 360 nesta pasta','default.xex não é um executável de Xbox 360 legível','cabeçalho Games on Demand sem sua pasta .data','pacote Games on Demand incompleto: sua pasta .data não contém todos os arquivos de dados','pacote de Xbox 360 que não é um jogo (save, complemento, atualização ou jogo do Xbox original)','Não foi possível carregar o motor XeniOS desta versão. Reinicie o RewindBox; se acontecer de novo, esta versão não pode executar jogos de Xbox 360.'],
'ru': ['XeniOS / Импорт','Импортировать игры','Настройки Xbox 360','Импорт {name} ({index}/{count})…','Отмена','Импортировано игр Xbox 360: {count}.','Пропущено игр, уже имеющихся в библиотеке: {count}.','Импорт отменён. Неполные игры не сохранены.','{name}: {reason}',
 'профиль XeniOS, а не игра','сенсорная раскладка XeniOS, а не игра','отдельному .xex или заголовку пакета нужна вся папка игры: используйте «Импортировать папку игры»','неподдерживаемый файл','файл не читается','это не образ диска Xbox 360','образ диска неполный или повреждён','недостаточно свободного места','ошибка копирования',
 'Для игр Xbox 360 требуется iOS 26 или новее.','Движок XeniOS не входит в эту версию RewindBox.','Движок XeniOS в этой сборке не соответствует RewindBox.','XeniOS работает только на iPhone и iPad.','XeniOS требуется JIT, который сейчас недоступен для RewindBox.','Уже запущена другая игра.','Перезапустите RewindBox перед запуском другой игры Xbox 360.','Не удаётся прочитать файл игры.','Не удалось запустить игру в XeniOS.',
 'Настройки XeniOS','Все игры Xbox 360','Эта игра','Изменения применяются при следующем запуске игры.','Унаследовано от: {source}','значение движка по умолчанию','все игры','эта игра','Использовать унаследованные значения','Восстановить значения движка',
 'Вкл.','Выкл.','Автоматически','Без ограничения','Консоль','Экран','Звук','Система',
 'Язык консоли','Регион консоли','Режим PAL 50 Гц','Ограничение частоты кадров','Ограничить обновление гостевого экрана','Чёрные полосы (letterbox)','Компилировать шейдеры в фоне','Аудиобуфер (кадры)','Аудиодекодер','Кэш-диск',
 'Язык, который консоль сообщает играм. Вошедший профиль XeniOS сохраняет свой язык. «Автоматически» следует языку RewindBox (английский для индонезийского, которого нет на Xbox 360).','Регион, который консоль сообщает играм. «Автоматически» следует региону устройства (США, если это не регион Xbox 360).','Язык интерфейса RewindBox — отдельная настройка.','Новый','Старый','Master','Настройка не сохранена: {error}','Настройки XeniOS для этой игры','Игр Xbox 360 пока нет','Импортируйте игры .iso или .zar либо папку игры (default.xex или Games on Demand) из «Файлов» кнопкой импорта.','Эта версия RewindBox содержит движок XeniOS без Metal Shader Converter от Apple, который нужен для вывода изображения игр.','Для включения JIT в XeniOS нужен файл RemotePairing.','Помощнику JIT не удалось подключиться к RewindBox. Убедитесь, что LocalDevVPN подключён, и повторите попытку.','Помощник JIT не завершил работу. Перезапустите RewindBox и повторите попытку.','Меню','Продолжить','Выйти из игры','Импортировать папку игры (XEX/GOD)','в этой папке нет папки с default.xex и нет игрового пакета Xbox 360','default.xex не является читаемым исполняемым файлом Xbox 360','заголовок Games on Demand без папки .data','пакет Games on Demand неполный: в папке .data не хватает файлов данных','пакет Xbox 360, который не является игрой (сохранение, дополнение, обновление или игра первой Xbox)','Не удалось загрузить движок XeniOS этой сборки. Перезапустите RewindBox; если это повторится, эта сборка не может запускать игры Xbox 360.'],
'zh': ['XeniOS / 导入','导入游戏','Xbox 360 设置','正在导入 {name}（{index}/{count}）…','取消','已导入 {count} 款 Xbox 360 游戏。','已跳过 {count} 款库中已有的游戏。','导入已取消，未保留任何不完整的游戏。','{name}：{reason}',
 'XeniOS 配置文件，不是游戏','XeniOS 触控布局，不是游戏','单独的 .xex 或游戏包头文件需要完整的游戏文件夹：请使用“导入游戏文件夹”','不支持的文件','文件无法读取','不是 Xbox 360 光盘镜像','光盘镜像不完整或已损坏','可用空间不足','复制失败',
 'Xbox 360 游戏需要 iOS 26 或更高版本。','此版本的 RewindBox 未包含 XeniOS 引擎。','此版本中的 XeniOS 引擎与 RewindBox 不匹配。','XeniOS 仅支持 iPhone 和 iPad。','XeniOS 需要 JIT，但 RewindBox 当前无法使用 JIT。','已有其他游戏正在运行。','请先重新启动 RewindBox，再启动另一款 Xbox 360 游戏。','无法读取游戏文件。','无法在 XeniOS 中启动该游戏。',
 'XeniOS 设置','所有 Xbox 360 游戏','此游戏','更改将在下次启动游戏时生效。','继承自：{source}','引擎默认值','所有游戏','此游戏','使用继承的值','恢复引擎默认值',
 '开','关','自动','不限','主机','显示','音频','系统',
 '主机语言','主机地区','PAL 50 Hz 时序','帧率上限','限制客体显示刷新率','黑边（Letterbox）','在后台编译着色器','音频缓冲（帧）','音频解码器','缓存驱动器',
 '主机向游戏报告的语言。已登录的 XeniOS 配置文件保留其自身语言。“自动”跟随 RewindBox 的语言（印尼语使用英语，因为 Xbox 360 不提供印尼语）。','主机向游戏报告的地区。“自动”跟随设备地区（若不属于 Xbox 360 地区则为美国）。','RewindBox 界面语言是单独的设置。','新','旧','Master','设置未保存：{error}','此游戏的 XeniOS 设置','还没有 Xbox 360 游戏','使用导入按钮，从“文件”导入 .iso 或 .zar 游戏，或游戏文件夹（default.xex 或 Games on Demand）。','此版本的 RewindBox 包含 XeniOS 引擎，但缺少显示游戏所需的 Apple Metal Shader Converter。','需要 RemotePairing 文件才能为 XeniOS 启用 JIT。','JIT 助手无法连接到 RewindBox。请确认 LocalDevVPN 已连接，然后重试。','JIT 助手未完成。请重新启动 RewindBox 后重试。','菜单','继续','退出游戏','导入游戏文件夹（XEX/GOD）','此文件夹中没有含 default.xex 的文件夹，也没有 Xbox 360 游戏包','default.xex 不是可读取的 Xbox 360 可执行文件','Games on Demand 头文件缺少对应的 .data 文件夹','Games on Demand 游戏包不完整：其 .data 文件夹缺少数据文件','不是游戏的 Xbox 360 包（存档、追加内容、更新或初代 Xbox 游戏）','无法加载此版本的 XeniOS 引擎。请重新启动 RewindBox；如果再次出现，此版本无法运行 Xbox 360 游戏。'],
'zh_Hant': ['XeniOS / 匯入','匯入遊戲','Xbox 360 設定','正在匯入 {name}（{index}/{count}）…','取消','已匯入 {count} 款 Xbox 360 遊戲。','已略過 {count} 款遊戲庫中已有的遊戲。','匯入已取消，未保留任何不完整的遊戲。','{name}：{reason}',
 'XeniOS 設定檔，不是遊戲','XeniOS 觸控配置，不是遊戲','單獨的 .xex 或遊戲包標頭檔需要完整的遊戲資料夾：請使用「匯入遊戲資料夾」','不支援的檔案','無法讀取檔案','不是 Xbox 360 光碟映像檔','光碟映像檔不完整或已損毀','可用空間不足','複製失敗',
 'Xbox 360 遊戲需要 iOS 26 或以上版本。','此版本的 RewindBox 未包含 XeniOS 引擎。','此版本中的 XeniOS 引擎與 RewindBox 不相符。','XeniOS 僅支援 iPhone 與 iPad。','XeniOS 需要 JIT，但 RewindBox 目前無法使用 JIT。','已有其他遊戲正在執行。','請先重新啟動 RewindBox，再啟動另一款 Xbox 360 遊戲。','無法讀取遊戲檔案。','無法在 XeniOS 中啟動此遊戲。',
 'XeniOS 設定','所有 Xbox 360 遊戲','此遊戲','變更將於下次啟動遊戲時生效。','繼承自：{source}','引擎預設值','所有遊戲','此遊戲','使用繼承的值','還原引擎預設值',
 '開','關','自動','不限','主機','顯示','音訊','系統',
 '主機語言','主機地區','PAL 50 Hz 時序','影格率上限','限制客體顯示更新率','黑邊（Letterbox）','在背景編譯著色器','音訊緩衝（影格）','音訊解碼器','快取磁碟',
 '主機向遊戲回報的語言。已登入的 XeniOS 設定檔會保留自己的語言。「自動」會跟隨 RewindBox 的語言（印尼文使用英文，因為 Xbox 360 未提供印尼文）。','主機向遊戲回報的地區。「自動」會跟隨裝置地區（若不屬於 Xbox 360 地區則為美國）。','RewindBox 介面語言是獨立的設定。','新','舊','Master','設定未儲存：{error}','此遊戲的 XeniOS 設定','尚無 Xbox 360 遊戲','使用匯入按鈕，從「檔案」匯入 .iso 或 .zar 遊戲，或遊戲資料夾（default.xex 或 Games on Demand）。','此版本的 RewindBox 包含 XeniOS 引擎，但缺少顯示遊戲所需的 Apple Metal Shader Converter。','需要 RemotePairing 檔案才能為 XeniOS 啟用 JIT。','JIT 輔助程式無法連接到 RewindBox。請確認 LocalDevVPN 已連線，然後再試一次。','JIT 輔助程式未完成。請重新啟動 RewindBox 後再試一次。','選單','繼續','結束遊戲','匯入遊戲資料夾（XEX/GOD）','此資料夾中沒有含 default.xex 的資料夾，也沒有 Xbox 360 遊戲包','default.xex 不是可讀取的 Xbox 360 執行檔','Games on Demand 標頭檔缺少對應的 .data 資料夾','Games on Demand 遊戲包不完整：其 .data 資料夾缺少資料檔案','不是遊戲的 Xbox 360 包（存檔、追加內容、更新或初代 Xbox 遊戲）','無法載入此版本的 XeniOS 引擎。請重新啟動 RewindBox；如果再次發生，此版本無法執行 Xbox 360 遊戲。'],
'ja': ['XeniOS / 読み込み','ゲームを読み込む','Xbox 360 の設定','{name} を読み込み中（{index}/{count}）…','キャンセル','Xbox 360 のゲームを {count} 本読み込みました。','ライブラリに既にある {count} 本をスキップしました。','読み込みをキャンセルしました。途中までのゲームは残していません。','{name}：{reason}',
 'XeniOS プロフィールでありゲームではありません','XeniOS タッチレイアウトでありゲームではありません','単体の .xex やパッケージのヘッダーにはゲームフォルダ全体が必要です：「ゲームフォルダを読み込む」を使ってください','対応していないファイル','ファイルを読み取れません','Xbox 360 のディスクイメージではありません','ディスクイメージが不完全か破損しています','空き容量が不足しています','コピーに失敗しました',
 'Xbox 360 のゲームには iOS 26 以降が必要です。','このバージョンの RewindBox には XeniOS エンジンが含まれていません。','このビルドの XeniOS エンジンは RewindBox と一致しません。','XeniOS は iPhone と iPad でのみ動作します。','XeniOS には JIT が必要ですが、現在 RewindBox では利用できません。','別のゲームが既に実行中です。','別の Xbox 360 ゲームを起動する前に RewindBox を再起動してください。','ゲームファイルを読み取れません。','XeniOS でゲームを起動できませんでした。',
 'XeniOS の設定','すべての Xbox 360 ゲーム','このゲーム','変更は次にゲームを起動したときに反映されます。','継承元：{source}','エンジンの既定値','すべてのゲーム','このゲーム','継承した値を使用','エンジンの既定値に戻す',
 'オン','オフ','自動','無制限','本体','表示','オーディオ','システム',
 '本体の言語','本体の地域','PAL 50 Hz タイミング','フレームレート上限','ゲスト表示のリフレッシュを制限','レターボックス','シェーダーをバックグラウンドでコンパイル','オーディオバッファ（フレーム）','オーディオデコーダ','キャッシュドライブ',
 '本体がゲームに通知する言語です。サインイン中の XeniOS プロフィールは独自の言語を保持します。「自動」は RewindBox の言語に従います（Xbox 360 にないインドネシア語の場合は英語）。','本体がゲームに通知する地域です。「自動」はデバイスの地域に従います（Xbox 360 の地域でない場合は米国）。','RewindBox のインターフェース言語は別の設定です。','新','旧','Master','設定を保存できませんでした：{error}','このゲームの XeniOS 設定','Xbox 360 のゲームはまだありません','読み込みボタンで、「ファイル」から .iso や .zar のゲーム、またはゲームフォルダ（default.xex または Games on Demand）を読み込んでください。','このバージョンの RewindBox には XeniOS エンジンが含まれていますが、ゲームの表示に必要な Apple の Metal Shader Converter がありません。','XeniOS の JIT を有効にするには RemotePairing ファイルが必要です。','JIT ヘルパーが RewindBox に接続できませんでした。LocalDevVPN が接続されていることを確認してから、もう一度お試しください。','JIT ヘルパーが完了しませんでした。RewindBox を再起動してから、もう一度お試しください。','メニュー','再開','ゲームを終了','ゲームフォルダを読み込む（XEX/GOD）','このフォルダには default.xex のフォルダも Xbox 360 のゲームパッケージもありません','default.xex は読み取れる Xbox 360 の実行ファイルではありません','.data フォルダのない Games on Demand ヘッダー','Games on Demand パッケージが不完全です：.data フォルダにすべてのデータファイルがありません','ゲームではない Xbox 360 パッケージ（セーブ、追加コンテンツ、アップデート、初代 Xbox のゲーム）','このビルドの XeniOS エンジンを読み込めませんでした。RewindBox を再起動してください。再び起きる場合、このビルドでは Xbox 360 のゲームを起動できません。'],
'ko': ['XeniOS / 가져오기','게임 가져오기','Xbox 360 설정','{name} 가져오는 중({index}/{count})…','취소','Xbox 360 게임 {count}개를 가져왔습니다.','라이브러리에 이미 있는 게임 {count}개를 건너뛰었습니다.','가져오기가 취소되었습니다. 불완전한 게임은 남기지 않았습니다.','{name}: {reason}',
 'XeniOS 프로필이며 게임이 아님','XeniOS 터치 레이아웃이며 게임이 아님','단독 .xex 또는 패키지 헤더에는 게임 폴더 전체가 필요합니다: 게임 폴더 가져오기를 사용하세요','지원되지 않는 파일','파일을 읽을 수 없음','Xbox 360 디스크 이미지가 아님','디스크 이미지가 불완전하거나 손상됨','여유 공간 부족','복사 실패',
 'Xbox 360 게임에는 iOS 26 이상이 필요합니다.','이 버전의 RewindBox에는 XeniOS 엔진이 포함되어 있지 않습니다.','이 빌드의 XeniOS 엔진이 RewindBox와 일치하지 않습니다.','XeniOS는 iPhone과 iPad에서만 실행됩니다.','XeniOS에는 JIT가 필요하지만 지금은 RewindBox에서 사용할 수 없습니다.','다른 게임이 이미 실행 중입니다.','다른 Xbox 360 게임을 시작하기 전에 RewindBox를 다시 시작하세요.','게임 파일을 읽을 수 없습니다.','XeniOS에서 게임을 시작하지 못했습니다.',
 'XeniOS 설정','모든 Xbox 360 게임','이 게임','변경 사항은 다음에 게임을 시작할 때 적용됩니다.','상속 출처: {source}','엔진 기본값','모든 게임','이 게임','상속된 값 사용','엔진 기본값 복원',
 '켬','끔','자동','제한 없음','콘솔','화면','오디오','시스템',
 '콘솔 언어','콘솔 지역','PAL 50Hz 타이밍','프레임 속도 제한','게스트 화면 새로 고침 제한','레터박스','백그라운드에서 셰이더 컴파일','오디오 버퍼(프레임)','오디오 디코더','캐시 드라이브',
 '콘솔이 게임에 알리는 언어입니다. 로그인한 XeniOS 프로필은 자체 언어를 유지합니다. 자동은 RewindBox 언어를 따릅니다(Xbox 360에 없는 인도네시아어는 영어).','콘솔이 게임에 알리는 지역입니다. 자동은 기기 지역을 따릅니다(Xbox 360 지역이 아니면 미국).','RewindBox 인터페이스 언어는 별도의 설정입니다.','신규','이전','Master','설정이 저장되지 않음: {error}','이 게임의 XeniOS 설정','아직 Xbox 360 게임이 없습니다','가져오기 버튼으로 파일 앱에서 .iso 또는 .zar 게임이나 게임 폴더(default.xex 또는 Games on Demand)를 가져오세요.','이 버전의 RewindBox에는 XeniOS 엔진이 포함되어 있지만 게임 표시에 필요한 Apple Metal Shader Converter가 없습니다.','XeniOS의 JIT를 사용하려면 RemotePairing 파일이 필요합니다.','JIT 도우미가 RewindBox에 연결하지 못했습니다. LocalDevVPN이 연결되어 있는지 확인한 후 다시 시도하세요.','JIT 도우미가 완료되지 않았습니다. RewindBox를 다시 시작한 후 다시 시도하세요.','메뉴','계속','게임 종료','게임 폴더 가져오기(XEX/GOD)','이 폴더에 default.xex 폴더나 Xbox 360 게임 패키지가 없습니다','default.xex가 읽을 수 있는 Xbox 360 실행 파일이 아닙니다','.data 폴더가 없는 Games on Demand 헤더','Games on Demand 패키지가 불완전합니다: .data 폴더에 모든 데이터 파일이 없습니다','게임이 아닌 Xbox 360 패키지(저장 데이터, 추가 콘텐츠, 업데이트 또는 초대 Xbox 게임)','이 빌드의 XeniOS 엔진을 불러올 수 없습니다. RewindBox를 다시 시작하세요. 다시 발생하면 이 빌드에서는 Xbox 360 게임을 실행할 수 없습니다.'],
'id': ['XeniOS / Impor','Impor game','Pengaturan Xbox 360','Mengimpor {name} ({index}/{count})…','Batal','{count} game Xbox 360 diimpor.','{count} game yang sudah ada di pustaka dilewati.','Impor dibatalkan. Tidak ada game sebagian yang disimpan.','{name}: {reason}',
 'profil XeniOS, bukan game','tata letak sentuh XeniOS, bukan game','.xex tunggal atau header paket memerlukan seluruh folder game: gunakan Impor folder game','file tidak didukung','file tidak dapat dibaca','bukan image disk Xbox 360','image disk tidak lengkap atau rusak','ruang kosong tidak cukup','gagal menyalin',
 'Game Xbox 360 memerlukan iOS 26 atau yang lebih baru.','Mesin XeniOS tidak disertakan di versi RewindBox ini.','Mesin XeniOS di build ini tidak cocok dengan RewindBox.','XeniOS hanya berjalan di iPhone dan iPad.','XeniOS memerlukan JIT, yang saat ini tidak tersedia untuk RewindBox.','Game lain sedang berjalan.','Mulai ulang RewindBox sebelum menjalankan game Xbox 360 lain.','File game tidak dapat dibaca.','Game tidak dapat dijalankan di XeniOS.',
 'Pengaturan XeniOS','Semua game Xbox 360','Game ini','Perubahan berlaku saat game berikutnya dijalankan.','Diwarisi dari: {source}','bawaan mesin','semua game','game ini','Gunakan nilai warisan','Pulihkan bawaan mesin',
 'Aktif','Nonaktif','Otomatis','Tanpa batas','Konsol','Tampilan','Audio','Sistem',
 'Bahasa konsol','Wilayah konsol','Pewaktuan PAL 50 Hz','Batas frame rate','Batasi penyegaran layar tamu','Letterbox','Kompilasi shader di latar belakang','Buffer audio (frame)','Dekoder audio','Drive cache',
 'Bahasa yang dilaporkan konsol ke game. Profil XeniOS yang masuk mempertahankan bahasanya sendiri. Otomatis mengikuti bahasa RewindBox (bahasa Inggris untuk bahasa Indonesia, yang tidak tersedia di Xbox 360).','Wilayah yang dilaporkan konsol ke game. Otomatis mengikuti wilayah perangkat (Amerika Serikat jika bukan wilayah Xbox 360).','Bahasa antarmuka RewindBox adalah pengaturan terpisah.','Baru','Lama','Master','Pengaturan tidak tersimpan: {error}','Pengaturan XeniOS untuk game ini','Belum ada game Xbox 360','Impor game .iso atau .zar, atau folder game (default.xex atau Games on Demand), dari File dengan tombol impor.','Versi RewindBox ini berisi mesin XeniOS tanpa Metal Shader Converter dari Apple, yang diperlukan untuk menampilkan game.','File RemotePairing diperlukan untuk mengaktifkan JIT XeniOS.','Pembantu JIT tidak dapat terhubung ke RewindBox. Pastikan LocalDevVPN tersambung, lalu coba lagi.','Pembantu JIT tidak selesai. Mulai ulang RewindBox, lalu coba lagi.','Menu','Lanjutkan','Keluar dari game','Impor folder game (XEX/GOD)','tidak ada folder default.xex maupun paket game Xbox 360 di folder ini','default.xex bukan file eksekusi Xbox 360 yang dapat dibaca','header Games on Demand tanpa folder .data-nya','paket Games on Demand tidak lengkap: folder .data-nya tidak memuat semua file data','paket Xbox 360 yang bukan game (simpanan, add-on, pembaruan, atau game Xbox orisinal)','Mesin XeniOS pada build ini tidak dapat dimuat. Mulai ulang RewindBox; jika terjadi lagi, build ini tidak dapat menjalankan game Xbox 360.'],
}

# Widescreen, reported resolution and performance overlay (settings screen and
# the in-game menu texts sent at launch). Same 12 locales, one list per locale.
EXTRA_KEYS = [
 'widescreen','internal_display_resolution','performance_overlay','widescreenOn','widescreenOff','widescreenHelp','resolutionHelp','resolutionDefault','overlayOff','overlaySimple','overlayDetailed','overlayHelp',
 'session_display','session_overlay','session_overlayOff','session_overlaySimple','session_overlayDetailed','session_appliesNow','session_aspect','session_aspectWide','session_aspectStandard','session_resolution','session_letterbox','session_on','session_off','session_default','session_thisGame','session_nextLaunch','session_fps','session_frameTime','session_memory','session_thermal','session_thermalNominal','session_thermalFair','session_thermalSerious','session_thermalCritical','session_saveFailed',
]

EXTRA = {
'en': ['Aspect ratio','Resolution reported to the game','Performance overlay','16:9 (widescreen)','4:3','Aspect ratio the console reports to games. Games read it when they set their video mode, so it applies the next time a game starts.','Only games that offer several resolutions use it. Higher resolutions load the GPU more. Applies the next time a game starts.','default','Off','Simple','Detailed','Applies to all Xbox 360 games. It can also be changed in game.',
 'Display','Performance overlay','Off','Simple','Detailed','Applies now, to all Xbox 360 games.','Aspect ratio','16:9 (widescreen)','4:3','Resolution reported to the game','Letterbox','On','Off','default','This game','Aspect ratio, resolution and letterbox apply the next time this game starts. They are saved for this game.','FPS','Frame time','Memory','Temperature','Normal','Warm','Hot','Critical','Setting not saved.'],
'fr': ['Format d’image','Résolution indiquée au jeu','Surimpression de performances','16:9 (grand écran)','4:3','Format d’image que la console indique aux jeux. Les jeux le lisent au choix de leur mode vidéo : il s’applique au prochain lancement d’un jeu.','Seuls les jeux qui proposent plusieurs résolutions l’utilisent. Les résolutions élevées sollicitent davantage le GPU. S’applique au prochain lancement d’un jeu.','par défaut','Désactivée','Simple','Détaillée','S’applique à tous les jeux Xbox 360. Modifiable aussi en jeu.',
 'Affichage','Surimpression de performances','Désactivée','Simple','Détaillée','S’applique immédiatement, à tous les jeux Xbox 360.','Format d’image','16:9 (grand écran)','4:3','Résolution indiquée au jeu','Bandes noires (letterbox)','Activé','Désactivé','par défaut','Ce jeu','Le format d’image, la résolution et les bandes noires s’appliquent au prochain lancement de ce jeu. Ils sont enregistrés pour ce jeu.','FPS','Temps d’image','Mémoire','Température','Normale','Chaude','Très chaude','Critique','Réglage non enregistré.'],
'de': ['Seitenverhältnis','Dem Spiel gemeldete Auflösung','Leistungsanzeige','16:9 (Breitbild)','4:3','Seitenverhältnis, das die Konsole den Spielen meldet. Spiele lesen es beim Festlegen ihres Videomodus, daher gilt es beim nächsten Spielstart.','Nur Spiele, die mehrere Auflösungen anbieten, nutzen sie. Höhere Auflösungen belasten die GPU stärker. Gilt beim nächsten Spielstart.','Standard','Aus','Einfach','Detailliert','Gilt für alle Xbox-360-Spiele. Auch im Spiel änderbar.',
 'Anzeige','Leistungsanzeige','Aus','Einfach','Detailliert','Gilt sofort, für alle Xbox-360-Spiele.','Seitenverhältnis','16:9 (Breitbild)','4:3','Dem Spiel gemeldete Auflösung','Letterbox','Ein','Aus','Standard','Dieses Spiel','Seitenverhältnis, Auflösung und Letterbox gelten beim nächsten Start dieses Spiels. Sie werden für dieses Spiel gespeichert.','FPS','Frame-Zeit','Speicher','Temperatur','Normal','Warm','Heiß','Kritisch','Einstellung nicht gespeichert.'],
'es': ['Relación de aspecto','Resolución indicada al juego','Superposición de rendimiento','16:9 (panorámico)','4:3','Relación de aspecto que la consola indica a los juegos. Los juegos la leen al elegir su modo de vídeo, así que se aplica la próxima vez que se inicie un juego.','Solo la usan los juegos que ofrecen varias resoluciones. Las resoluciones más altas cargan más la GPU. Se aplica la próxima vez que se inicie un juego.','predeterminada','Desactivada','Simple','Detallada','Se aplica a todos los juegos de Xbox 360. También se puede cambiar durante el juego.',
 'Pantalla','Superposición de rendimiento','Desactivada','Simple','Detallada','Se aplica ahora, a todos los juegos de Xbox 360.','Relación de aspecto','16:9 (panorámico)','4:3','Resolución indicada al juego','Bandas negras (letterbox)','Activado','Desactivado','predeterminada','Este juego','La relación de aspecto, la resolución y las bandas negras se aplican la próxima vez que se inicie este juego. Se guardan para este juego.','FPS','Tiempo de fotograma','Memoria','Temperatura','Normal','Cálida','Alta','Crítica','Ajuste no guardado.'],
'it': ['Proporzioni','Risoluzione comunicata al gioco','Overlay prestazioni','16:9 (widescreen)','4:3','Proporzioni che la console comunica ai giochi. I giochi le leggono quando impostano la modalità video, quindi si applicano al prossimo avvio di un gioco.','Solo i giochi che offrono più risoluzioni la usano. Le risoluzioni più alte caricano di più la GPU. Si applica al prossimo avvio di un gioco.','predefinita','Disattivato','Semplice','Dettagliato','Vale per tutti i giochi Xbox 360. Si può cambiare anche durante il gioco.',
 'Schermo','Overlay prestazioni','Disattivato','Semplice','Dettagliato','Si applica subito, a tutti i giochi Xbox 360.','Proporzioni','16:9 (widescreen)','4:3','Risoluzione comunicata al gioco','Bande nere (letterbox)','Attivo','Disattivo','predefinita','Questo gioco','Proporzioni, risoluzione e bande nere si applicano al prossimo avvio di questo gioco. Vengono salvate per questo gioco.','FPS','Tempo di frame','Memoria','Temperatura','Normale','Calda','Alta','Critica','Impostazione non salvata.'],
'pt': ['Proporção da tela','Resolução informada ao jogo','Sobreposição de desempenho','16:9 (widescreen)','4:3','Proporção que o console informa aos jogos. Os jogos a leem ao definir o modo de vídeo, então vale na próxima vez que um jogo iniciar.','Só os jogos que oferecem várias resoluções a usam. Resoluções mais altas sobrecarregam mais a GPU. Vale na próxima vez que um jogo iniciar.','padrão','Desativada','Simples','Detalhada','Vale para todos os jogos de Xbox 360. Também pode ser alterada durante o jogo.',
 'Tela','Sobreposição de desempenho','Desativada','Simples','Detalhada','Vale agora, para todos os jogos de Xbox 360.','Proporção da tela','16:9 (widescreen)','4:3','Resolução informada ao jogo','Barras pretas (letterbox)','Ativado','Desativado','padrão','Este jogo','Proporção, resolução e barras pretas valem na próxima vez que este jogo iniciar. Ficam salvas para este jogo.','FPS','Tempo de quadro','Memória','Temperatura','Normal','Morna','Quente','Crítica','Ajuste não salvo.'],
'ru': ['Соотношение сторон','Разрешение, сообщаемое игре','Индикатор производительности','16:9 (широкоэкранный)','4:3','Соотношение сторон, которое консоль сообщает играм. Игры считывают его при выборе видеорежима, поэтому оно применяется при следующем запуске игры.','Его используют только игры, предлагающие несколько разрешений. Более высокие разрешения сильнее нагружают GPU. Применяется при следующем запуске игры.','по умолчанию','Выкл.','Простой','Подробный','Действует для всех игр Xbox 360. Можно изменить и во время игры.',
 'Экран','Индикатор производительности','Выкл.','Простой','Подробный','Применяется сразу, ко всем играм Xbox 360.','Соотношение сторон','16:9 (широкоэкранный)','4:3','Разрешение, сообщаемое игре','Чёрные полосы (letterbox)','Вкл.','Выкл.','по умолчанию','Эта игра','Соотношение сторон, разрешение и чёрные полосы применяются при следующем запуске этой игры. Они сохраняются для этой игры.','FPS','Время кадра','Память','Температура','Норма','Тёплое','Горячее','Критическая','Настройка не сохранена.'],
'zh': ['宽高比','向游戏报告的分辨率','性能显示层','16:9（宽屏）','4:3','主机向游戏报告的宽高比。游戏在设置视频模式时读取它，因此在下次启动游戏时生效。','只有提供多种分辨率的游戏才会使用。分辨率越高，GPU 负载越大。在下次启动游戏时生效。','默认','关','简单','详细','适用于所有 Xbox 360 游戏。也可以在游戏中更改。',
 '显示','性能显示层','关','简单','详细','立即生效，适用于所有 Xbox 360 游戏。','宽高比','16:9（宽屏）','4:3','向游戏报告的分辨率','黑边（Letterbox）','开','关','默认','此游戏','宽高比、分辨率和黑边在下次启动此游戏时生效，并为此游戏保存。','FPS','帧时间','内存','温度','正常','偏热','过热','严重','设置未保存。'],
'zh_Hant': ['長寬比','向遊戲回報的解析度','效能顯示層','16:9（寬螢幕）','4:3','主機向遊戲回報的長寬比。遊戲在設定視訊模式時讀取它，因此會在下次啟動遊戲時生效。','只有提供多種解析度的遊戲才會使用。解析度越高，GPU 負載越大。會在下次啟動遊戲時生效。','預設','關','簡單','詳細','適用於所有 Xbox 360 遊戲。也可以在遊戲中變更。',
 '顯示','效能顯示層','關','簡單','詳細','立即生效，適用於所有 Xbox 360 遊戲。','長寬比','16:9（寬螢幕）','4:3','向遊戲回報的解析度','黑邊（Letterbox）','開','關','預設','此遊戲','長寬比、解析度和黑邊會在下次啟動此遊戲時生效，並為此遊戲儲存。','FPS','影格時間','記憶體','溫度','正常','偏熱','過熱','嚴重','設定未儲存。'],
'ja': ['アスペクト比','ゲームに通知する解像度','パフォーマンス表示','16:9（ワイド）','4:3','本体がゲームに通知するアスペクト比です。ゲームはビデオモードを設定するときに読み取るため、次にゲームを起動したときに反映されます。','複数の解像度に対応したゲームだけが使用します。解像度が高いほど GPU の負荷が増えます。次にゲームを起動したときに反映されます。','既定','オフ','シンプル','詳細','すべての Xbox 360 ゲームに適用されます。ゲーム中にも変更できます。',
 '表示','パフォーマンス表示','オフ','シンプル','詳細','すぐに反映され、すべての Xbox 360 ゲームに適用されます。','アスペクト比','16:9（ワイド）','4:3','ゲームに通知する解像度','レターボックス','オン','オフ','既定','このゲーム','アスペクト比、解像度、レターボックスは、次にこのゲームを起動したときに反映されます。このゲーム用に保存されます。','FPS','フレーム時間','メモリ','温度','正常','やや高温','高温','危険','設定を保存できませんでした。'],
'ko': ['화면 비율','게임에 알리는 해상도','성능 오버레이','16:9(와이드)','4:3','콘솔이 게임에 알리는 화면 비율입니다. 게임은 비디오 모드를 설정할 때 이 값을 읽으므로 다음에 게임을 시작할 때 적용됩니다.','여러 해상도를 제공하는 게임만 사용합니다. 해상도가 높을수록 GPU 부하가 커집니다. 다음에 게임을 시작할 때 적용됩니다.','기본','끔','간단','자세히','모든 Xbox 360 게임에 적용됩니다. 게임 중에도 변경할 수 있습니다.',
 '화면','성능 오버레이','끔','간단','자세히','즉시 적용되며 모든 Xbox 360 게임에 적용됩니다.','화면 비율','16:9(와이드)','4:3','게임에 알리는 해상도','레터박스','켬','끔','기본','이 게임','화면 비율, 해상도, 레터박스는 다음에 이 게임을 시작할 때 적용되며 이 게임용으로 저장됩니다.','FPS','프레임 시간','메모리','온도','정상','따뜻함','뜨거움','위험','설정이 저장되지 않았습니다.'],
'id': ['Rasio aspek','Resolusi yang dilaporkan ke game','Overlay performa','16:9 (layar lebar)','4:3','Rasio aspek yang dilaporkan konsol ke game. Game membacanya saat mengatur mode video, jadi berlaku saat game dijalankan berikutnya.','Hanya game yang menawarkan beberapa resolusi yang memakainya. Resolusi lebih tinggi membebani GPU lebih besar. Berlaku saat game dijalankan berikutnya.','bawaan','Nonaktif','Sederhana','Terperinci','Berlaku untuk semua game Xbox 360. Juga dapat diubah saat bermain.',
 'Tampilan','Overlay performa','Nonaktif','Sederhana','Terperinci','Berlaku sekarang, untuk semua game Xbox 360.','Rasio aspek','16:9 (layar lebar)','4:3','Resolusi yang dilaporkan ke game','Letterbox','Aktif','Nonaktif','bawaan','Game ini','Rasio aspek, resolusi, dan letterbox berlaku saat game ini dijalankan berikutnya. Disimpan untuk game ini.','FPS','Waktu frame','Memori','Suhu','Normal','Hangat','Panas','Kritis','Pengaturan tidak tersimpan.'],
}
KEYS = KEYS + EXTRA_KEYS
for _code, _values in EXTRA.items():
    assert len(_values) == len(EXTRA_KEYS), (_code, len(_values))
    T[_code] = T[_code] + _values

# The code region below 8 GB that the Core's one-time JIT prepare needs was not
# held in this RewindBox process (docs/xenios-playlist.md § Code region).
MEMORY_KEYS = ['jitMemoryUnavailable']

MEMORY = {
'en': ['XeniOS could not get the memory it needs for JIT in this session. Close RewindBox from the app switcher, reopen it, then start the Xbox 360 game again.'],
'fr': ['XeniOS n’a pas pu obtenir la mémoire nécessaire au JIT dans cette session. Fermez RewindBox depuis le sélecteur d’apps, rouvrez-le, puis relancez le jeu Xbox 360.'],
'de': ['XeniOS konnte in dieser Sitzung nicht den Speicher erhalten, den es für JIT braucht. Schließe RewindBox im App-Umschalter, öffne es erneut und starte das Xbox-360-Spiel noch einmal.'],
'es': ['XeniOS no pudo obtener la memoria que necesita para el JIT en esta sesión. Cierra RewindBox desde el selector de apps, ábrelo de nuevo y vuelve a iniciar el juego de Xbox 360.'],
'it': ['XeniOS non ha potuto ottenere la memoria necessaria al JIT in questa sessione. Chiudi RewindBox dal selettore delle app, riaprilo e avvia di nuovo il gioco Xbox 360.'],
'pt': ['O XeniOS não conseguiu obter a memória necessária para o JIT nesta sessão. Feche o RewindBox no seletor de apps, abra-o novamente e inicie o jogo de Xbox 360 outra vez.'],
'ru': ['XeniOS не удалось получить память, нужную для JIT, в этом сеансе. Закройте RewindBox в переключателе приложений, откройте его снова и запустите игру Xbox 360 ещё раз.'],
'zh': ['XeniOS 在本次会话中无法获得 JIT 所需的内存。请在应用切换器中关闭 RewindBox，重新打开后再启动该 Xbox 360 游戏。'],
'zh_Hant': ['XeniOS 在本次工作階段中無法取得 JIT 所需的記憶體。請在 App 切換器中關閉 RewindBox，重新開啟後再啟動該 Xbox 360 遊戲。'],
'ja': ['このセッションでは、XeniOS が JIT に必要なメモリを確保できませんでした。App スイッチャーで RewindBox を終了してから再度開き、Xbox 360 ゲームをもう一度起動してください。'],
'ko': ['이번 세션에서 XeniOS가 JIT에 필요한 메모리를 확보하지 못했습니다. 앱 전환기에서 RewindBox를 닫고 다시 연 다음 Xbox 360 게임을 다시 시작하세요.'],
'id': ['XeniOS tidak dapat memperoleh memori yang diperlukan untuk JIT di sesi ini. Tutup RewindBox dari pengalih aplikasi, buka lagi, lalu jalankan kembali game Xbox 360.'],
}
# The folder import's picker could not open the picked folder with iOS's
# security-scoped access (XeniaInternalService.importFolder).
ACCESS_KEYS = ['folderAccessFailed']

ACCESS = {
'en': ['iOS did not give RewindBox access to this folder: pick it again'],
'fr': ['iOS n’a pas ouvert ce dossier à RewindBox : choisissez-le à nouveau'],
'de': ['iOS hat RewindBox keinen Zugriff auf diesen Ordner gegeben: wähle ihn erneut'],
'es': ['iOS no dio a RewindBox acceso a esta carpeta: vuelve a elegirla'],
'it': ['iOS non ha dato a RewindBox l’accesso a questa cartella: sceglila di nuovo'],
'pt': ['o iOS não deu ao RewindBox acesso a esta pasta: escolha-a de novo'],
'ru': ['iOS не предоставила RewindBox доступ к этой папке: выберите её снова'],
'zh': ['iOS 未向 RewindBox 开放此文件夹：请重新选择'],
'zh_Hant': ['iOS 未向 RewindBox 開放此資料夾：請重新選擇'],
'ja': ['iOS がこのフォルダへのアクセスを RewindBox に許可しませんでした。もう一度選択してください'],
'ko': ['iOS가 RewindBox에 이 폴더에 대한 접근을 허용하지 않았습니다. 다시 선택하세요'],
'id': ['iOS tidak memberi RewindBox akses ke folder ini: pilih lagi'],
}
# The StikJIT the XeniOS helper would load does not write full 64-bit
# addresses (XeniaJitService.toolUnsupported): Xbox 360 games are blocked.
TOOL_KEYS = ['jitToolUnsupported']

TOOL = {
'en': ['This RewindBox build has a JIT tool that cannot prepare memory for XeniOS safely, so Xbox 360 games are blocked. Install a complete RewindBox build.'],
'fr': ['Cette version de RewindBox contient un outil JIT qui ne peut pas préparer la mémoire de XeniOS en toute sécurité : les jeux Xbox 360 sont bloqués. Installez une version complète de RewindBox.'],
'de': ['Dieser RewindBox-Build enthält ein JIT-Werkzeug, das den Speicher für XeniOS nicht sicher vorbereiten kann; Xbox-360-Spiele sind daher gesperrt. Installiere einen vollständigen RewindBox-Build.'],
'es': ['Esta versión de RewindBox tiene una herramienta JIT que no puede preparar la memoria de XeniOS con seguridad, así que los juegos de Xbox 360 están bloqueados. Instala una versión completa de RewindBox.'],
'it': ['Questa versione di RewindBox ha uno strumento JIT che non può preparare la memoria di XeniOS in sicurezza, quindi i giochi Xbox 360 sono bloccati. Installa una versione completa di RewindBox.'],
'pt': ['Esta versão do RewindBox tem uma ferramenta JIT que não consegue preparar a memória do XeniOS com segurança, por isso os jogos de Xbox 360 estão bloqueados. Instale uma versão completa do RewindBox.'],
'ru': ['В этой сборке RewindBox инструмент JIT не может безопасно подготовить память для XeniOS, поэтому игры Xbox 360 заблокированы. Установите полную сборку RewindBox.'],
'zh': ['此 RewindBox 版本中的 JIT 工具无法安全地为 XeniOS 准备内存，因此 Xbox 360 游戏已被阻止。请安装完整的 RewindBox 版本。'],
'zh_Hant': ['此 RewindBox 版本中的 JIT 工具無法安全地為 XeniOS 準備記憶體，因此 Xbox 360 遊戲已被阻擋。請安裝完整的 RewindBox 版本。'],
'ja': ['この RewindBox ビルドの JIT ツールは XeniOS のメモリを安全に準備できないため、Xbox 360 ゲームはブロックされています。完全な RewindBox ビルドをインストールしてください。'],
'ko': ['이 RewindBox 빌드의 JIT 도구는 XeniOS용 메모리를 안전하게 준비할 수 없어 Xbox 360 게임이 차단되었습니다. 완전한 RewindBox 빌드를 설치하세요.'],
'id': ['Build RewindBox ini memiliki alat JIT yang tidak dapat menyiapkan memori XeniOS dengan aman, sehingga game Xbox 360 diblokir. Instal build RewindBox yang lengkap.'],
}
KEYS = KEYS + MEMORY_KEYS + ACCESS_KEYS + TOOL_KEYS
for _code, _values in TOOL.items():
    assert len(_values) == len(TOOL_KEYS), (_code, len(_values))
for _code, _values in ACCESS.items():
    assert len(_values) == len(ACCESS_KEYS), (_code, len(_values))
for _code, _values in MEMORY.items():
    assert len(_values) == len(MEMORY_KEYS), (_code, len(_values))
    T[_code] = T[_code] + _values + ACCESS[_code] + TOOL[_code]

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
    'coreLoadFailed' ||
    'unsupportedPlatform' ||
    'jitUnavailable' ||
    'sessionActive' ||
    'restartRequired' ||
    'gameUnreadable' ||
    'shaderConverterMissing' ||
    'pairingRequired' ||
    'jitAttachFailed' ||
    'jitHelperIncomplete' ||
    'jitMemoryUnavailable' ||
    'jitToolUnsupported' => error!,
    'jitToolUnverified' => 'restartRequired',
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
