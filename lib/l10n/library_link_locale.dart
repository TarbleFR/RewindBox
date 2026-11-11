import 'package:flutter/widgets.dart';

/// Texts of the library folders added with the system folder picker on iOS:
/// why a folder could not be added, and what RewindBox reads in it (which
/// console folder feeds which playlist, what is left out and why).
abstract final class LibraryLinkLocale {
  static const List<String> languages = <String>[
    'en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'id', 'ja', 'ko', 'zh', 'zh_Hant', //
  ];

  static const Map<String, Map<String, String>> _texts = <String, Map<String, String>>{
    'en': <String, String>{
      'pickerBusy': 'A folder picker is already open. Close it and try again.',
      'pickerNoScreen': 'The folder picker could not be opened. Bring RewindBox to the front and try again.',
      'bookmarkFailed': 'iOS did not let RewindBox keep access to this folder ({detail}). Choose a folder of the Files app: under “On My iPhone” or inside an app.',
      'accessLost': 'iOS no longer gives RewindBox access to this folder ({detail}). Choose it again.',
      'notReadable': 'This folder cannot be read ({detail}). Choose another folder.',
      'unknownFailure': 'The folder could not be added: {detail}',
      'folderUnavailable': 'Not accessible right now. Its games are kept. Add this folder again to restore access, or press to remove it.',
      'linkLost': 'RewindBox lost access to the linked folder, which can happen after an update. Its games are kept: link the folder again.',
      'reading': 'Reading the folder…',
      'reportTitle': 'What RewindBox found',
      'reportFolder': 'Folder: {folder}',
      'reportScanned': 'Each console folder feeds its playlist:',
      'reportConsole': '{console} ← “{folder}”: {count} game(s)',
      'reportConsoleEmpty': '{console} ← “{folder}”: no game yet',
      'reportExamples': 'for example: {names}',
      'reportImportOnly': '{console} ← “{folder}”: {count} game(s) found, but this console keeps its games inside RewindBox. Open its playlist and use Import to add them.',
      'reportUnknownTitle': 'Not read, because the folder name is not a console:',
      'reportUnknown': '“{folder}”: {count} file(s). No console uses this folder name.',
      'reportUnknownSuggest': '“{folder}”: {count} file(s). They look like {console} games: rename the folder to “{name}”.',
      'reportLoose': '{count} game file(s) lie directly in the folder and are not read: put each one in the folder of its console.',
      'reportNothing': 'No console folder was recognised here. RewindBox reads one folder per console, named after the console, for example: {examples}. Choose the folder that contains these folders, or rename yours.',
      'reportTruncated': 'This folder is very large: the counts are minimums.',
      'actionAdd': 'Add this folder',
      'actionLink': 'Link this folder',
      'actionChooseAnother': 'Choose another folder',
      'added': 'Folder added: {games} game(s) in {playlists} playlist(s).',
      'addedEmpty': 'Folder added. No game was found in it yet.',
      'restored': 'This folder was already in your library: access restored, games read again.',
    },
    'fr': <String, String>{
      'pickerBusy': 'Un sélecteur de dossier est déjà ouvert. Fermez-le et réessayez.',
      'pickerNoScreen': 'Le sélecteur de dossier n’a pas pu s’ouvrir. Ramenez RewindBox au premier plan et réessayez.',
      'bookmarkFailed': 'iOS n’a pas laissé RewindBox conserver l’accès à ce dossier ({detail}). Choisissez un dossier de l’app Fichiers : dans « Sur mon iPhone » ou dans le dossier d’une app.',
      'accessLost': 'iOS ne donne plus à RewindBox l’accès à ce dossier ({detail}). Choisissez-le de nouveau.',
      'notReadable': 'Ce dossier ne peut pas être lu ({detail}). Choisissez un autre dossier.',
      'unknownFailure': 'Le dossier n’a pas pu être ajouté : {detail}',
      'folderUnavailable': 'Inaccessible pour le moment. Ses jeux sont conservés. Ajoutez de nouveau ce dossier pour rétablir l’accès, ou appuyez pour le retirer.',
      'linkLost': 'RewindBox a perdu l’accès au dossier lié, ce qui peut arriver après une mise à jour. Ses jeux sont conservés : liez de nouveau le dossier.',
      'reading': 'Lecture du dossier…',
      'reportTitle': 'Ce que RewindBox a trouvé',
      'reportFolder': 'Dossier : {folder}',
      'reportScanned': 'Chaque dossier de console alimente sa playlist :',
      'reportConsole': '{console} ← « {folder} » : {count} jeu(x)',
      'reportConsoleEmpty': '{console} ← « {folder} » : aucun jeu pour l’instant',
      'reportExamples': 'par exemple : {names}',
      'reportImportOnly': '{console} ← « {folder} » : {count} jeu(x) trouvé(s), mais cette console garde ses jeux dans RewindBox. Ouvrez sa playlist et utilisez Importer pour les ajouter.',
      'reportUnknownTitle': 'Non lus, car le nom du dossier n’est pas celui d’une console :',
      'reportUnknown': '« {folder} » : {count} fichier(s). Aucune console n’utilise ce nom de dossier.',
      'reportUnknownSuggest': '« {folder} » : {count} fichier(s). On dirait des jeux {console} : renommez le dossier en « {name} ».',
      'reportLoose': '{count} fichier(s) de jeu sont posés directement dans le dossier et ne sont pas lus : rangez chacun dans le dossier de sa console.',
      'reportNothing': 'Aucun dossier de console n’a été reconnu ici. RewindBox lit un dossier par console, nommé comme la console, par exemple : {examples}. Choisissez le dossier qui contient ces dossiers, ou renommez les vôtres.',
      'reportTruncated': 'Ce dossier est très volumineux : les nombres sont des minimums.',
      'actionAdd': 'Ajouter ce dossier',
      'actionLink': 'Lier ce dossier',
      'actionChooseAnother': 'Choisir un autre dossier',
      'added': 'Dossier ajouté : {games} jeu(x) dans {playlists} playlist(s).',
      'addedEmpty': 'Dossier ajouté. Aucun jeu n’y a été trouvé pour l’instant.',
      'restored': 'Ce dossier était déjà dans votre bibliothèque : accès rétabli, jeux relus.',
    },
    'de': <String, String>{
      'pickerBusy': 'Eine Ordnerauswahl ist bereits geöffnet. Schließe sie und versuche es erneut.',
      'pickerNoScreen': 'Die Ordnerauswahl konnte nicht geöffnet werden. Hole RewindBox in den Vordergrund und versuche es erneut.',
      'bookmarkFailed': 'iOS hat RewindBox nicht erlaubt, den Zugriff auf diesen Ordner zu behalten ({detail}). Wähle einen Ordner der Dateien-App: unter „Auf meinem iPhone“ oder im Ordner einer App.',
      'accessLost': 'iOS gibt RewindBox keinen Zugriff mehr auf diesen Ordner ({detail}). Wähle ihn erneut aus.',
      'notReadable': 'Dieser Ordner kann nicht gelesen werden ({detail}). Wähle einen anderen Ordner.',
      'unknownFailure': 'Der Ordner konnte nicht hinzugefügt werden: {detail}',
      'folderUnavailable': 'Zurzeit nicht erreichbar. Seine Spiele bleiben erhalten. Füge diesen Ordner erneut hinzu, um den Zugriff wiederherzustellen, oder drücke, um ihn zu entfernen.',
      'linkLost': 'RewindBox hat den Zugriff auf den verknüpften Ordner verloren, was nach einem Update vorkommen kann. Seine Spiele bleiben erhalten: Verknüpfe den Ordner erneut.',
      'reading': 'Ordner wird gelesen…',
      'reportTitle': 'Was RewindBox gefunden hat',
      'reportFolder': 'Ordner: {folder}',
      'reportScanned': 'Jeder Konsolenordner füllt seine Playlist:',
      'reportConsole': '{console} ← „{folder}“: {count} Spiel(e)',
      'reportConsoleEmpty': '{console} ← „{folder}“: noch kein Spiel',
      'reportExamples': 'zum Beispiel: {names}',
      'reportImportOnly': '{console} ← „{folder}“: {count} Spiel(e) gefunden, aber diese Konsole bewahrt ihre Spiele in RewindBox auf. Öffne ihre Playlist und füge sie mit „Importieren“ hinzu.',
      'reportUnknownTitle': 'Nicht gelesen, weil der Ordnername keine Konsole ist:',
      'reportUnknown': '„{folder}“: {count} Datei(en). Keine Konsole verwendet diesen Ordnernamen.',
      'reportUnknownSuggest': '„{folder}“: {count} Datei(en). Sie sehen wie {console}-Spiele aus: Benenne den Ordner in „{name}“ um.',
      'reportLoose': '{count} Spieldatei(en) liegen direkt im Ordner und werden nicht gelesen: Lege jede in den Ordner ihrer Konsole.',
      'reportNothing': 'Hier wurde kein Konsolenordner erkannt. RewindBox liest einen Ordner pro Konsole, benannt nach der Konsole, zum Beispiel: {examples}. Wähle den Ordner, der diese Ordner enthält, oder benenne deine um.',
      'reportTruncated': 'Dieser Ordner ist sehr groß: Die Zahlen sind Mindestwerte.',
      'actionAdd': 'Diesen Ordner hinzufügen',
      'actionLink': 'Diesen Ordner verknüpfen',
      'actionChooseAnother': 'Anderen Ordner wählen',
      'added': 'Ordner hinzugefügt: {games} Spiel(e) in {playlists} Playlist(s).',
      'addedEmpty': 'Ordner hinzugefügt. Darin wurde noch kein Spiel gefunden.',
      'restored': 'Dieser Ordner war bereits in deiner Bibliothek: Zugriff wiederhergestellt, Spiele neu gelesen.',
    },
    'es': <String, String>{
      'pickerBusy': 'Ya hay un selector de carpetas abierto. Ciérralo e inténtalo de nuevo.',
      'pickerNoScreen': 'No se pudo abrir el selector de carpetas. Trae RewindBox al primer plano e inténtalo de nuevo.',
      'bookmarkFailed': 'iOS no permitió que RewindBox conservara el acceso a esta carpeta ({detail}). Elige una carpeta de la app Archivos: en «En mi iPhone» o dentro de la carpeta de una app.',
      'accessLost': 'iOS ya no da a RewindBox acceso a esta carpeta ({detail}). Elígela de nuevo.',
      'notReadable': 'Esta carpeta no se puede leer ({detail}). Elige otra carpeta.',
      'unknownFailure': 'No se pudo añadir la carpeta: {detail}',
      'folderUnavailable': 'No accesible por ahora. Sus juegos se conservan. Añade de nuevo esta carpeta para recuperar el acceso, o pulsa para quitarla.',
      'linkLost': 'RewindBox perdió el acceso a la carpeta enlazada, lo que puede ocurrir tras una actualización. Sus juegos se conservan: enlaza la carpeta de nuevo.',
      'reading': 'Leyendo la carpeta…',
      'reportTitle': 'Lo que RewindBox ha encontrado',
      'reportFolder': 'Carpeta: {folder}',
      'reportScanned': 'Cada carpeta de consola alimenta su lista:',
      'reportConsole': '{console} ← «{folder}»: {count} juego(s)',
      'reportConsoleEmpty': '{console} ← «{folder}»: ningún juego todavía',
      'reportExamples': 'por ejemplo: {names}',
      'reportImportOnly': '{console} ← «{folder}»: {count} juego(s) encontrado(s), pero esta consola guarda sus juegos dentro de RewindBox. Abre su lista y usa Importar para añadirlos.',
      'reportUnknownTitle': 'No se leen, porque el nombre de la carpeta no es una consola:',
      'reportUnknown': '«{folder}»: {count} archivo(s). Ninguna consola usa este nombre de carpeta.',
      'reportUnknownSuggest': '«{folder}»: {count} archivo(s). Parecen juegos de {console}: cambia el nombre de la carpeta a «{name}».',
      'reportLoose': '{count} archivo(s) de juego están directamente en la carpeta y no se leen: pon cada uno en la carpeta de su consola.',
      'reportNothing': 'Aquí no se reconoció ninguna carpeta de consola. RewindBox lee una carpeta por consola, con el nombre de la consola, por ejemplo: {examples}. Elige la carpeta que contiene esas carpetas, o cambia el nombre de las tuyas.',
      'reportTruncated': 'Esta carpeta es muy grande: las cifras son mínimos.',
      'actionAdd': 'Añadir esta carpeta',
      'actionLink': 'Enlazar esta carpeta',
      'actionChooseAnother': 'Elegir otra carpeta',
      'added': 'Carpeta añadida: {games} juego(s) en {playlists} lista(s).',
      'addedEmpty': 'Carpeta añadida. Todavía no se encontró ningún juego en ella.',
      'restored': 'Esta carpeta ya estaba en tu biblioteca: acceso recuperado, juegos leídos de nuevo.',
    },
    'it': <String, String>{
      'pickerBusy': 'Un selettore di cartelle è già aperto. Chiudilo e riprova.',
      'pickerNoScreen': 'Non è stato possibile aprire il selettore di cartelle. Riporta RewindBox in primo piano e riprova.',
      'bookmarkFailed': 'iOS non ha permesso a RewindBox di conservare l’accesso a questa cartella ({detail}). Scegli una cartella dell’app File: in «Sul mio iPhone» o nella cartella di un’app.',
      'accessLost': 'iOS non dà più a RewindBox l’accesso a questa cartella ({detail}). Sceglila di nuovo.',
      'notReadable': 'Questa cartella non può essere letta ({detail}). Scegli un’altra cartella.',
      'unknownFailure': 'Non è stato possibile aggiungere la cartella: {detail}',
      'folderUnavailable': 'Al momento non accessibile. I suoi giochi sono conservati. Aggiungi di nuovo questa cartella per ripristinare l’accesso, oppure premi per rimuoverla.',
      'linkLost': 'RewindBox ha perso l’accesso alla cartella collegata, cosa che può succedere dopo un aggiornamento. I suoi giochi sono conservati: collega di nuovo la cartella.',
      'reading': 'Lettura della cartella…',
      'reportTitle': 'Cosa ha trovato RewindBox',
      'reportFolder': 'Cartella: {folder}',
      'reportScanned': 'Ogni cartella di console alimenta la sua playlist:',
      'reportConsole': '{console} ← «{folder}»: {count} gioco/giochi',
      'reportConsoleEmpty': '{console} ← «{folder}»: ancora nessun gioco',
      'reportExamples': 'per esempio: {names}',
      'reportImportOnly': '{console} ← «{folder}»: {count} gioco/giochi trovati, ma questa console tiene i suoi giochi dentro RewindBox. Apri la sua playlist e usa Importa per aggiungerli.',
      'reportUnknownTitle': 'Non letti, perché il nome della cartella non è una console:',
      'reportUnknown': '«{folder}»: {count} file. Nessuna console usa questo nome di cartella.',
      'reportUnknownSuggest': '«{folder}»: {count} file. Sembrano giochi {console}: rinomina la cartella in «{name}».',
      'reportLoose': '{count} file di gioco si trovano direttamente nella cartella e non vengono letti: metti ciascuno nella cartella della sua console.',
      'reportNothing': 'Qui non è stata riconosciuta alcuna cartella di console. RewindBox legge una cartella per console, con il nome della console, per esempio: {examples}. Scegli la cartella che contiene queste cartelle, oppure rinomina le tue.',
      'reportTruncated': 'Questa cartella è molto grande: i numeri sono minimi.',
      'actionAdd': 'Aggiungi questa cartella',
      'actionLink': 'Collega questa cartella',
      'actionChooseAnother': 'Scegli un’altra cartella',
      'added': 'Cartella aggiunta: {games} gioco/giochi in {playlists} playlist.',
      'addedEmpty': 'Cartella aggiunta. Non vi è ancora stato trovato alcun gioco.',
      'restored': 'Questa cartella era già nella tua libreria: accesso ripristinato, giochi riletti.',
    },
    'pt': <String, String>{
      'pickerBusy': 'Já existe um seletor de pastas aberto. Feche-o e tente de novo.',
      'pickerNoScreen': 'Não foi possível abrir o seletor de pastas. Traga o RewindBox para primeiro plano e tente de novo.',
      'bookmarkFailed': 'O iOS não deixou o RewindBox manter o acesso a esta pasta ({detail}). Escolha uma pasta da app Ficheiros: em «No meu iPhone» ou dentro da pasta de uma app.',
      'accessLost': 'O iOS já não dá ao RewindBox acesso a esta pasta ({detail}). Escolha-a de novo.',
      'notReadable': 'Esta pasta não pode ser lida ({detail}). Escolha outra pasta.',
      'unknownFailure': 'Não foi possível adicionar a pasta: {detail}',
      'folderUnavailable': 'Inacessível de momento. Os seus jogos são mantidos. Adicione de novo esta pasta para repor o acesso, ou prima para a remover.',
      'linkLost': 'O RewindBox perdeu o acesso à pasta ligada, o que pode acontecer depois de uma atualização. Os seus jogos são mantidos: ligue a pasta de novo.',
      'reading': 'A ler a pasta…',
      'reportTitle': 'O que o RewindBox encontrou',
      'reportFolder': 'Pasta: {folder}',
      'reportScanned': 'Cada pasta de consola alimenta a sua playlist:',
      'reportConsole': '{console} ← «{folder}»: {count} jogo(s)',
      'reportConsoleEmpty': '{console} ← «{folder}»: ainda nenhum jogo',
      'reportExamples': 'por exemplo: {names}',
      'reportImportOnly': '{console} ← «{folder}»: {count} jogo(s) encontrado(s), mas esta consola guarda os seus jogos dentro do RewindBox. Abra a sua playlist e use Importar para os adicionar.',
      'reportUnknownTitle': 'Não lidos, porque o nome da pasta não é uma consola:',
      'reportUnknown': '«{folder}»: {count} ficheiro(s). Nenhuma consola usa este nome de pasta.',
      'reportUnknownSuggest': '«{folder}»: {count} ficheiro(s). Parecem jogos de {console}: mude o nome da pasta para «{name}».',
      'reportLoose': '{count} ficheiro(s) de jogo estão diretamente na pasta e não são lidos: ponha cada um na pasta da sua consola.',
      'reportNothing': 'Nenhuma pasta de consola foi reconhecida aqui. O RewindBox lê uma pasta por consola, com o nome da consola, por exemplo: {examples}. Escolha a pasta que contém essas pastas, ou mude o nome das suas.',
      'reportTruncated': 'Esta pasta é muito grande: os números são mínimos.',
      'actionAdd': 'Adicionar esta pasta',
      'actionLink': 'Ligar esta pasta',
      'actionChooseAnother': 'Escolher outra pasta',
      'added': 'Pasta adicionada: {games} jogo(s) em {playlists} playlist(s).',
      'addedEmpty': 'Pasta adicionada. Ainda não foi encontrado nenhum jogo nela.',
      'restored': 'Esta pasta já estava na sua biblioteca: acesso reposto, jogos lidos de novo.',
    },
    'ru': <String, String>{
      'pickerBusy': 'Выбор папки уже открыт. Закройте его и повторите попытку.',
      'pickerNoScreen': 'Не удалось открыть выбор папки. Верните RewindBox на передний план и повторите попытку.',
      'bookmarkFailed': 'iOS не позволила RewindBox сохранить доступ к этой папке ({detail}). Выберите папку приложения «Файлы»: в разделе «На iPhone» или в папке какого-либо приложения.',
      'accessLost': 'iOS больше не даёт RewindBox доступ к этой папке ({detail}). Выберите её снова.',
      'notReadable': 'Эту папку не удаётся прочитать ({detail}). Выберите другую папку.',
      'unknownFailure': 'Не удалось добавить папку: {detail}',
      'folderUnavailable': 'Сейчас недоступна. Её игры сохранены. Добавьте эту папку снова, чтобы восстановить доступ, или нажмите, чтобы удалить её.',
      'linkLost': 'RewindBox потерял доступ к связанной папке — так бывает после обновления. Её игры сохранены: свяжите папку снова.',
      'reading': 'Чтение папки…',
      'reportTitle': 'Что нашёл RewindBox',
      'reportFolder': 'Папка: {folder}',
      'reportScanned': 'Каждая папка консоли наполняет свой плейлист:',
      'reportConsole': '{console} ← «{folder}»: игр — {count}',
      'reportConsoleEmpty': '{console} ← «{folder}»: игр пока нет',
      'reportExamples': 'например: {names}',
      'reportImportOnly': '{console} ← «{folder}»: найдено игр — {count}, но эта консоль хранит игры внутри RewindBox. Откройте её плейлист и добавьте их через «Импорт».',
      'reportUnknownTitle': 'Не читаются, потому что имя папки не является консолью:',
      'reportUnknown': '«{folder}»: файлов — {count}. Ни одна консоль не использует такое имя папки.',
      'reportUnknownSuggest': '«{folder}»: файлов — {count}. Похоже на игры {console}: переименуйте папку в «{name}».',
      'reportLoose': 'Файлов игр, лежащих прямо в папке, — {count}; они не читаются: положите каждый в папку его консоли.',
      'reportNothing': 'Здесь не распознано ни одной папки консоли. RewindBox читает по одной папке на консоль, названной по консоли, например: {examples}. Выберите папку, в которой лежат эти папки, или переименуйте свои.',
      'reportTruncated': 'Эта папка очень большая: числа указаны как минимальные.',
      'actionAdd': 'Добавить эту папку',
      'actionLink': 'Связать эту папку',
      'actionChooseAnother': 'Выбрать другую папку',
      'added': 'Папка добавлена: игр — {games}, плейлистов — {playlists}.',
      'addedEmpty': 'Папка добавлена. Игр в ней пока не найдено.',
      'restored': 'Эта папка уже была в вашей библиотеке: доступ восстановлен, игры прочитаны заново.',
    },
    'id': <String, String>{
      'pickerBusy': 'Pemilih folder sudah terbuka. Tutup lalu coba lagi.',
      'pickerNoScreen': 'Pemilih folder tidak dapat dibuka. Bawa RewindBox ke depan lalu coba lagi.',
      'bookmarkFailed': 'iOS tidak mengizinkan RewindBox menyimpan akses ke folder ini ({detail}). Pilih folder di aplikasi File: di “Di iPhone Saya” atau di dalam folder sebuah aplikasi.',
      'accessLost': 'iOS tidak lagi memberi RewindBox akses ke folder ini ({detail}). Pilih lagi folder tersebut.',
      'notReadable': 'Folder ini tidak dapat dibaca ({detail}). Pilih folder lain.',
      'unknownFailure': 'Folder tidak dapat ditambahkan: {detail}',
      'folderUnavailable': 'Saat ini tidak dapat diakses. Game-nya tetap disimpan. Tambahkan lagi folder ini untuk memulihkan akses, atau tekan untuk menghapusnya.',
      'linkLost': 'RewindBox kehilangan akses ke folder yang ditautkan, yang bisa terjadi setelah pembaruan. Game-nya tetap disimpan: tautkan lagi foldernya.',
      'reading': 'Membaca folder…',
      'reportTitle': 'Yang ditemukan RewindBox',
      'reportFolder': 'Folder: {folder}',
      'reportScanned': 'Setiap folder konsol mengisi playlist-nya:',
      'reportConsole': '{console} ← “{folder}”: {count} game',
      'reportConsoleEmpty': '{console} ← “{folder}”: belum ada game',
      'reportExamples': 'misalnya: {names}',
      'reportImportOnly': '{console} ← “{folder}”: {count} game ditemukan, tetapi konsol ini menyimpan game-nya di dalam RewindBox. Buka playlist-nya dan gunakan Impor untuk menambahkannya.',
      'reportUnknownTitle': 'Tidak dibaca, karena nama foldernya bukan nama konsol:',
      'reportUnknown': '“{folder}”: {count} file. Tidak ada konsol yang memakai nama folder ini.',
      'reportUnknownSuggest': '“{folder}”: {count} file. Tampaknya game {console}: ganti nama folder menjadi “{name}”.',
      'reportLoose': '{count} file game berada langsung di dalam folder dan tidak dibaca: letakkan masing-masing di folder konsolnya.',
      'reportNothing': 'Tidak ada folder konsol yang dikenali di sini. RewindBox membaca satu folder per konsol, dinamai sesuai konsolnya, misalnya: {examples}. Pilih folder yang berisi folder-folder itu, atau ganti nama folder Anda.',
      'reportTruncated': 'Folder ini sangat besar: angka-angkanya adalah nilai minimum.',
      'actionAdd': 'Tambahkan folder ini',
      'actionLink': 'Tautkan folder ini',
      'actionChooseAnother': 'Pilih folder lain',
      'added': 'Folder ditambahkan: {games} game di {playlists} playlist.',
      'addedEmpty': 'Folder ditambahkan. Belum ada game yang ditemukan di dalamnya.',
      'restored': 'Folder ini sudah ada di pustaka Anda: akses dipulihkan, game dibaca ulang.',
    },
    'ja': <String, String>{
      'pickerBusy': 'フォルダの選択画面がすでに開いています。閉じてから、もう一度お試しください。',
      'pickerNoScreen': 'フォルダの選択画面を開けませんでした。RewindBox を前面に表示してから、もう一度お試しください。',
      'bookmarkFailed': 'iOS が、このフォルダへのアクセスを RewindBox が保持することを許可しませんでした（{detail}）。「ファイル」App のフォルダ（「このiPhone内」または App のフォルダ内）を選んでください。',
      'accessLost': 'iOS が、このフォルダへのアクセスを RewindBox に許可しなくなりました（{detail}）。もう一度選び直してください。',
      'notReadable': 'このフォルダを読み込めません（{detail}）。別のフォルダを選んでください。',
      'unknownFailure': 'フォルダを追加できませんでした: {detail}',
      'folderUnavailable': '現在アクセスできません。ゲームは保持されています。アクセスを復元するにはこのフォルダをもう一度追加するか、押して削除してください。',
      'linkLost': 'RewindBox はリンクしたフォルダへのアクセスを失いました（アップデート後に起こることがあります）。ゲームは保持されています。フォルダをもう一度リンクしてください。',
      'reading': 'フォルダを読み込み中…',
      'reportTitle': 'RewindBox が見つけたもの',
      'reportFolder': 'フォルダ: {folder}',
      'reportScanned': '各コンソールのフォルダが、そのプレイリストに入ります:',
      'reportConsole': '{console} ← 「{folder}」: {count} 本',
      'reportConsoleEmpty': '{console} ← 「{folder}」: まだゲームがありません',
      'reportExamples': '例: {names}',
      'reportImportOnly': '{console} ← 「{folder}」: {count} 本見つかりましたが、このコンソールのゲームは RewindBox 内に保存されます。そのプレイリストを開き、「読み込む」で追加してください。',
      'reportUnknownTitle': 'フォルダ名がコンソール名ではないため、読み込まれません:',
      'reportUnknown': '「{folder}」: {count} ファイル。このフォルダ名を使うコンソールはありません。',
      'reportUnknownSuggest': '「{folder}」: {count} ファイル。{console} のゲームのようです。フォルダ名を「{name}」に変更してください。',
      'reportLoose': 'フォルダ直下にあるゲームファイル {count} 個は読み込まれません。それぞれをコンソールのフォルダに入れてください。',
      'reportNothing': 'ここではコンソールのフォルダが見つかりませんでした。RewindBox は、コンソール名を付けたフォルダをコンソールごとに 1 つ読み込みます（例: {examples}）。それらのフォルダを含むフォルダを選ぶか、フォルダ名を変更してください。',
      'reportTruncated': 'このフォルダは非常に大きいため、数は最小値です。',
      'actionAdd': 'このフォルダを追加',
      'actionLink': 'このフォルダをリンク',
      'actionChooseAnother': '別のフォルダを選ぶ',
      'added': 'フォルダを追加しました: {playlists} 個のプレイリストに {games} 本。',
      'addedEmpty': 'フォルダを追加しました。まだゲームは見つかっていません。',
      'restored': 'このフォルダはすでにライブラリにあります。アクセスを復元し、ゲームを読み込み直しました。',
    },
    'ko': <String, String>{
      'pickerBusy': '폴더 선택 화면이 이미 열려 있습니다. 닫은 뒤 다시 시도하세요.',
      'pickerNoScreen': '폴더 선택 화면을 열 수 없습니다. RewindBox를 앞으로 가져온 뒤 다시 시도하세요.',
      'bookmarkFailed': 'iOS가 RewindBox가 이 폴더의 접근 권한을 유지하도록 허용하지 않았습니다({detail}). 파일 앱의 폴더를 선택하세요: “나의 iPhone” 또는 앱의 폴더 안.',
      'accessLost': 'iOS가 더 이상 RewindBox에 이 폴더의 접근 권한을 주지 않습니다({detail}). 폴더를 다시 선택하세요.',
      'notReadable': '이 폴더를 읽을 수 없습니다({detail}). 다른 폴더를 선택하세요.',
      'unknownFailure': '폴더를 추가할 수 없습니다: {detail}',
      'folderUnavailable': '지금은 접근할 수 없습니다. 게임은 유지됩니다. 접근 권한을 복원하려면 이 폴더를 다시 추가하거나, 눌러서 제거하세요.',
      'linkLost': 'RewindBox가 연결된 폴더의 접근 권한을 잃었습니다. 업데이트 후에 생길 수 있습니다. 게임은 유지됩니다: 폴더를 다시 연결하세요.',
      'reading': '폴더를 읽는 중…',
      'reportTitle': 'RewindBox가 찾은 내용',
      'reportFolder': '폴더: {folder}',
      'reportScanned': '각 콘솔 폴더가 해당 플레이리스트를 채웁니다:',
      'reportConsole': '{console} ← “{folder}”: 게임 {count}개',
      'reportConsoleEmpty': '{console} ← “{folder}”: 아직 게임 없음',
      'reportExamples': '예: {names}',
      'reportImportOnly': '{console} ← “{folder}”: 게임 {count}개를 찾았지만, 이 콘솔은 게임을 RewindBox 안에 보관합니다. 해당 플레이리스트를 열고 가져오기로 추가하세요.',
      'reportUnknownTitle': '폴더 이름이 콘솔 이름이 아니어서 읽지 않습니다:',
      'reportUnknown': '“{folder}”: 파일 {count}개. 이 폴더 이름을 쓰는 콘솔이 없습니다.',
      'reportUnknownSuggest': '“{folder}”: 파일 {count}개. {console} 게임으로 보입니다: 폴더 이름을 “{name}”(으)로 바꾸세요.',
      'reportLoose': '폴더 바로 아래에 있는 게임 파일 {count}개는 읽지 않습니다: 각각 해당 콘솔 폴더에 넣으세요.',
      'reportNothing': '여기서는 콘솔 폴더를 찾지 못했습니다. RewindBox는 콘솔 이름으로 된 폴더를 콘솔마다 하나씩 읽습니다. 예: {examples}. 이 폴더들이 들어 있는 폴더를 선택하거나, 폴더 이름을 바꾸세요.',
      'reportTruncated': '이 폴더는 매우 큽니다: 숫자는 최소값입니다.',
      'actionAdd': '이 폴더 추가',
      'actionLink': '이 폴더 연결',
      'actionChooseAnother': '다른 폴더 선택',
      'added': '폴더를 추가했습니다: 플레이리스트 {playlists}개에 게임 {games}개.',
      'addedEmpty': '폴더를 추가했습니다. 아직 게임을 찾지 못했습니다.',
      'restored': '이 폴더는 이미 보관함에 있습니다: 접근 권한을 복원하고 게임을 다시 읽었습니다.',
    },
    'zh': <String, String>{
      'pickerBusy': '文件夹选择器已打开。请将其关闭后重试。',
      'pickerNoScreen': '无法打开文件夹选择器。请将 RewindBox 切回前台后重试。',
      'bookmarkFailed': 'iOS 不允许 RewindBox 保留对此文件夹的访问权限（{detail}）。请选择“文件”App 中的文件夹：位于“我的 iPhone”或某个 App 的文件夹内。',
      'accessLost': 'iOS 不再向 RewindBox 提供此文件夹的访问权限（{detail}）。请重新选择该文件夹。',
      'notReadable': '无法读取此文件夹（{detail}）。请选择其他文件夹。',
      'unknownFailure': '无法添加文件夹：{detail}',
      'folderUnavailable': '目前无法访问。其中的游戏已保留。重新添加此文件夹即可恢复访问，或按下以移除。',
      'linkLost': 'RewindBox 失去了对已关联文件夹的访问权限（更新后可能出现）。其中的游戏已保留：请重新关联该文件夹。',
      'reading': '正在读取文件夹…',
      'reportTitle': 'RewindBox 找到的内容',
      'reportFolder': '文件夹：{folder}',
      'reportScanned': '每个主机文件夹对应其播放列表：',
      'reportConsole': '{console} ← “{folder}”：{count} 个游戏',
      'reportConsoleEmpty': '{console} ← “{folder}”：暂无游戏',
      'reportExamples': '例如：{names}',
      'reportImportOnly': '{console} ← “{folder}”：找到 {count} 个游戏，但此主机的游戏保存在 RewindBox 内部。请打开其播放列表并使用“导入”来添加。',
      'reportUnknownTitle': '未读取，因为文件夹名称不是主机名称：',
      'reportUnknown': '“{folder}”：{count} 个文件。没有主机使用这个文件夹名称。',
      'reportUnknownSuggest': '“{folder}”：{count} 个文件。看起来是 {console} 的游戏：请将文件夹重命名为“{name}”。',
      'reportLoose': '有 {count} 个游戏文件直接放在该文件夹中，不会被读取：请将它们分别放入各自主机的文件夹。',
      'reportNothing': '这里没有识别到任何主机文件夹。RewindBox 为每台主机读取一个以主机命名的文件夹，例如：{examples}。请选择包含这些文件夹的文件夹，或重命名您的文件夹。',
      'reportTruncated': '此文件夹非常大：数量为最小值。',
      'actionAdd': '添加此文件夹',
      'actionLink': '关联此文件夹',
      'actionChooseAnother': '选择其他文件夹',
      'added': '已添加文件夹：{playlists} 个播放列表中共 {games} 个游戏。',
      'addedEmpty': '已添加文件夹。其中暂未找到游戏。',
      'restored': '此文件夹已在您的游戏库中：已恢复访问并重新读取游戏。',
    },
    'zh_Hant': <String, String>{
      'pickerBusy': '檔案夾選擇器已開啟。請將其關閉後再試一次。',
      'pickerNoScreen': '無法開啟檔案夾選擇器。請將 RewindBox 切回前景後再試一次。',
      'bookmarkFailed': 'iOS 不允許 RewindBox 保留此檔案夾的取用權限（{detail}）。請選擇「檔案」App 中的檔案夾：位於「我的 iPhone」或某個 App 的檔案夾內。',
      'accessLost': 'iOS 不再提供 RewindBox 此檔案夾的取用權限（{detail}）。請重新選擇該檔案夾。',
      'notReadable': '無法讀取此檔案夾（{detail}）。請選擇其他檔案夾。',
      'unknownFailure': '無法加入檔案夾：{detail}',
      'folderUnavailable': '目前無法取用。其中的遊戲已保留。重新加入此檔案夾即可恢復取用，或按下以移除。',
      'linkLost': 'RewindBox 失去了已連結檔案夾的取用權限（更新後可能發生）。其中的遊戲已保留：請重新連結該檔案夾。',
      'reading': '正在讀取檔案夾…',
      'reportTitle': 'RewindBox 找到的內容',
      'reportFolder': '檔案夾：{folder}',
      'reportScanned': '每個主機檔案夾對應其播放列表：',
      'reportConsole': '{console} ← 「{folder}」：{count} 個遊戲',
      'reportConsoleEmpty': '{console} ← 「{folder}」：尚無遊戲',
      'reportExamples': '例如：{names}',
      'reportImportOnly': '{console} ← 「{folder}」：找到 {count} 個遊戲，但此主機的遊戲儲存在 RewindBox 內部。請打開其播放列表並使用「輸入」來加入。',
      'reportUnknownTitle': '未讀取，因為檔案夾名稱不是主機名稱：',
      'reportUnknown': '「{folder}」：{count} 個檔案。沒有主機使用這個檔案夾名稱。',
      'reportUnknownSuggest': '「{folder}」：{count} 個檔案。看起來是 {console} 的遊戲：請將檔案夾重新命名為「{name}」。',
      'reportLoose': '有 {count} 個遊戲檔案直接放在該檔案夾中，不會被讀取：請將它們分別放入各自主機的檔案夾。',
      'reportNothing': '這裡沒有辨識到任何主機檔案夾。RewindBox 為每台主機讀取一個以主機命名的檔案夾，例如：{examples}。請選擇包含這些檔案夾的檔案夾，或重新命名您的檔案夾。',
      'reportTruncated': '此檔案夾非常大：數量為最小值。',
      'actionAdd': '加入此檔案夾',
      'actionLink': '連結此檔案夾',
      'actionChooseAnother': '選擇其他檔案夾',
      'added': '已加入檔案夾：{playlists} 個播放列表中共 {games} 個遊戲。',
      'addedEmpty': '已加入檔案夾。其中尚未找到遊戲。',
      'restored': '此檔案夾已在您的遊戲庫中：已恢復取用並重新讀取遊戲。',
    },
  };

  /// The keys of the reference language.
  static Iterable<String> get keys => _texts['en']!.keys;

  /// Whether [language] has a text for [key].
  static bool has(String language, String key) => _texts[language]?.containsKey(key) ?? false;

  static String languageOf(Locale locale) {
    if (locale.languageCode == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' || country == 'TW' || country == 'HK' || country == 'MO') return 'zh_Hant';
      return 'zh';
    }
    return _texts.containsKey(locale.languageCode) ? locale.languageCode : 'en';
  }

  /// The text of [key] in [language] (English when missing), with each
  /// `{name}` of [values] replaced.
  static String textFor(String language, String key, [Map<String, Object?> values = const <String, Object?>{}]) {
    var text = _texts[language]?[key] ?? _texts['en']![key] ?? key;
    values.forEach((name, value) => text = text.replaceAll('{$name}', '$value'));
    return text;
  }

  static String text(BuildContext context, String key, [Map<String, Object?> values = const <String, Object?>{}]) =>
      textFor(languageOf(Localizations.localeOf(context)), key, values);

  /// The sentence that tells the user why a folder could not be added or
  /// reopened. [error] is an `ExternalFolderAccessException` (matched by its
  /// native code), a `FileSystemException`, or anything else.
  static String failureFor(String language, Object error) {
    final description = '$error';
    String detail(String fallback) {
      final message = _messageOf(error);
      return message == null || message.isEmpty ? fallback : message;
    }

    final code = _codeOf(error);
    switch (code) {
      case 'NO_ROOT_VC':
        return textFor(language, 'pickerNoScreen');
      case 'PICKER_BUSY':
        return textFor(language, 'pickerBusy');
      case 'BOOKMARK_FAILED':
        return textFor(language, 'bookmarkFailed', {'detail': detail(code!)});
      case 'RESOLVE_FAILED' || 'ACCESS_DENIED' || 'NOT_ACTIVATED' || 'NO_BOOKMARK':
        return textFor(language, 'accessLost', {'detail': detail(code!)});
    }
    if (description.startsWith('FileSystemException') || description.startsWith('PathAccessException')) {
      return textFor(language, 'notReadable', {'detail': detail(description)});
    }
    return textFor(language, 'unknownFailure', {'detail': description});
  }

  static String failure(BuildContext context, Object error) =>
      failureFor(languageOf(Localizations.localeOf(context)), error);

  static String? _codeOf(Object error) {
    try {
      final code = (error as dynamic).code;
      return code is String ? code : null;
    } catch (_) {
      return null;
    }
  }

  static String? _messageOf(Object error) {
    try {
      final message = (error as dynamic).message;
      return message is String ? message : null;
    } catch (_) {
      return null;
    }
  }
}
