import 'package:flutter/widgets.dart';

abstract final class Armsx2UiLocale {
  static const Map<String, Map<String, String>> _v = {
    'en': {
      'chooseBios':'Choose PS2 BIOS','importBiosFirst':'Import one or more PS2 BIOS files first.','biosChoiceHelp':'This choice is used for games and BIOS boot. Available languages depend on the chosen BIOS.','cancel':'Cancel',
      'gamesImported':'{count} PS2 game(s) imported.','gamesRejected':'Some games were rejected.','bootBiosFailed':'Could not boot the PS2 BIOS.','biosImported':'{count} BIOS file(s) imported. Choose the BIOS to use.','biosImportFailed':'BIOS import failed.','importFailed':'ARMSX2 import failed: {error}',
      'importMenu':'ARMSX2 / Import','importGames':'Import games','importBios':'Import one or more BIOS files','bootBios':'Boot PS2 BIOS',
      'outsideRoot':'The PS2 game is outside ARMSX2/Games.','deleteFailed':'ARMSX2 deletion failed: {error}','deleteGames':'Delete PS2 games','selectedCount':'{count} game(s) selected','deselectAll':'Deselect all','selectAll':'Select all','deleting':'Deleting {done} / {total}…','deleteCount':'Delete ({count})',
      'importLine':'{name} — {reason}','importNotImported': '{count} file(s) not imported:','importMore': 'and {count} more','importAlready': '{count} file(s) already in the library: not copied again','reasonWrongType': 'wrong file type (accepted: {extensions})','reasonUnreadable': 'the file cannot be read','reasonNoSpace': 'not enough free space','reasonCopyFailed': 'the copy failed','reasonBiosTooLarge': 'too large to be a PS2 BIOS file: this looks like a game — use the game import'
    },
    'fr': {
      'chooseBios':'Choisir le BIOS PS2','importBiosFirst':'Importez d’abord un ou plusieurs BIOS PS2.','biosChoiceHelp':'Ce choix sera utilisé pour les jeux et le démarrage du BIOS. Les langues proposées dépendent du BIOS choisi.','cancel':'Annuler',
      'gamesImported':'{count} jeu(x) PS2 importé(s).','gamesRejected':'Certains jeux ont été rejetés.','bootBiosFailed':'Impossible de démarrer le BIOS PS2.','biosImported':'{count} BIOS importé(s). Choisissez le BIOS à utiliser.','biosImportFailed':'Échec de l’import du BIOS.','importFailed':'Échec de l’import ARMSX2 : {error}',
      'importMenu':'ARMSX2 / Importer','importGames':'Importer des jeux','importBios':'Importer un ou plusieurs BIOS','bootBios':'Démarrer le BIOS PS2',
      'outsideRoot':'Le jeu PS2 n’appartient pas au dossier ARMSX2/Games.','deleteFailed':'La suppression ARMSX2 a échoué : {error}','deleteGames':'Supprimer des jeux PS2','selectedCount':'{count} jeu(x) sélectionné(s)','deselectAll':'Tout désélectionner','selectAll':'Tout sélectionner','deleting':'Suppression {done} / {total}…','deleteCount':'Supprimer ({count})',
      'importLine':'{name} — {reason}','importNotImported': '{count} fichier(s) non importé(s) :','importMore': 'et {count} autre(s)','importAlready': '{count} fichier(s) déjà dans la bibliothèque : non recopié(s)','reasonWrongType': 'type de fichier incorrect (acceptés : {extensions})','reasonUnreadable': 'fichier illisible','reasonNoSpace': 'espace libre insuffisant','reasonCopyFailed': 'la copie a échoué','reasonBiosTooLarge': 'trop volumineux pour un BIOS PS2 : ressemble à un jeu — utilisez l’import de jeux'
    },
    'de': {
      'chooseBios':'PS2-BIOS auswählen','importBiosFirst':'Importiere zuerst eine oder mehrere PS2-BIOS-Dateien.','biosChoiceHelp':'Diese Auswahl wird für Spiele und den BIOS-Start verwendet. Verfügbare Sprachen hängen vom gewählten BIOS ab.','cancel':'Abbrechen',
      'gamesImported':'{count} PS2-Spiel(e) importiert.','gamesRejected':'Einige Spiele wurden abgelehnt.','bootBiosFailed':'Das PS2-BIOS konnte nicht gestartet werden.','biosImported':'{count} BIOS-Datei(en) importiert. Wähle das zu verwendende BIOS.','biosImportFailed':'BIOS-Import fehlgeschlagen.','importFailed':'ARMSX2-Import fehlgeschlagen: {error}',
      'importMenu':'ARMSX2 / Import','importGames':'Spiele importieren','importBios':'Eine oder mehrere BIOS-Dateien importieren','bootBios':'PS2-BIOS starten',
      'outsideRoot':'Das PS2-Spiel liegt außerhalb von ARMSX2/Games.','deleteFailed':'ARMSX2-Löschen fehlgeschlagen: {error}','deleteGames':'PS2-Spiele löschen','selectedCount':'{count} Spiel(e) ausgewählt','deselectAll':'Auswahl aufheben','selectAll':'Alle auswählen','deleting':'Löschen {done} / {total}…','deleteCount':'Löschen ({count})',
      'importLine':'{name} — {reason}','importNotImported': '{count} Datei(en) nicht importiert:','importMore': 'und {count} weitere','importAlready': '{count} Datei(en) bereits in der Bibliothek: nicht erneut kopiert','reasonWrongType': 'falscher Dateityp (erlaubt: {extensions})','reasonUnreadable': 'Datei nicht lesbar','reasonNoSpace': 'nicht genug freier Speicher','reasonCopyFailed': 'Kopieren fehlgeschlagen','reasonBiosTooLarge': 'zu groß für eine PS2-BIOS-Datei: sieht nach einem Spiel aus — nutze den Spielimport'
    },
    'es': {
      'chooseBios':'Elegir BIOS de PS2','importBiosFirst':'Importa primero uno o varios archivos de BIOS de PS2.','biosChoiceHelp':'Esta elección se usa para los juegos y el arranque del BIOS. Los idiomas disponibles dependen del BIOS elegido.','cancel':'Cancelar',
      'gamesImported':'{count} juego(s) de PS2 importado(s).','gamesRejected':'Algunos juegos fueron rechazados.','bootBiosFailed':'No se pudo iniciar el BIOS de PS2.','biosImported':'{count} archivo(s) de BIOS importado(s). Elige el BIOS que quieras usar.','biosImportFailed':'Error al importar el BIOS.','importFailed':'Error al importar en ARMSX2: {error}',
      'importMenu':'ARMSX2 / Importar','importGames':'Importar juegos','importBios':'Importar uno o varios archivos de BIOS','bootBios':'Iniciar BIOS de PS2',
      'outsideRoot':'El juego de PS2 está fuera de ARMSX2/Games.','deleteFailed':'Error al eliminar en ARMSX2: {error}','deleteGames':'Eliminar juegos de PS2','selectedCount':'{count} juego(s) seleccionado(s)','deselectAll':'Deseleccionar todo','selectAll':'Seleccionar todo','deleting':'Eliminando {done} / {total}…','deleteCount':'Eliminar ({count})',
      'importLine':'{name} — {reason}','importNotImported': '{count} archivo(s) no importado(s):','importMore': 'y {count} más','importAlready': '{count} archivo(s) ya en la biblioteca: no se copiaron de nuevo','reasonWrongType': 'tipo de archivo incorrecto (admitidos: {extensions})','reasonUnreadable': 'no se puede leer el archivo','reasonNoSpace': 'espacio libre insuficiente','reasonCopyFailed': 'la copia falló','reasonBiosTooLarge': 'demasiado grande para un BIOS de PS2: parece un juego — usa la importación de juegos'
    },
    'it': {
      'chooseBios':'Scegli BIOS PS2','importBiosFirst':'Importa prima uno o più file BIOS PS2.','biosChoiceHelp':'Questa scelta viene usata per i giochi e l’avvio del BIOS. Le lingue disponibili dipendono dal BIOS selezionato.','cancel':'Annulla',
      'gamesImported':'{count} gioco/i PS2 importato/i.','gamesRejected':'Alcuni giochi sono stati rifiutati.','bootBiosFailed':'Impossibile avviare il BIOS PS2.','biosImported':'{count} file BIOS importato/i. Scegli il BIOS da usare.','biosImportFailed':'Importazione BIOS non riuscita.','importFailed':'Importazione ARMSX2 non riuscita: {error}',
      'importMenu':'ARMSX2 / Importa','importGames':'Importa giochi','importBios':'Importa uno o più file BIOS','bootBios':'Avvia BIOS PS2',
      'outsideRoot':'Il gioco PS2 è fuori da ARMSX2/Games.','deleteFailed':'Eliminazione ARMSX2 non riuscita: {error}','deleteGames':'Elimina giochi PS2','selectedCount':'{count} gioco/i selezionato/i','deselectAll':'Deseleziona tutto','selectAll':'Seleziona tutto','deleting':'Eliminazione {done} / {total}…','deleteCount':'Elimina ({count})',
      'importLine':'{name} — {reason}','importNotImported': '{count} file non importato/i:','importMore': 'e altri {count}','importAlready': '{count} file già nella libreria: non copiato/i di nuovo','reasonWrongType': 'tipo di file non valido (accettati: {extensions})','reasonUnreadable': 'file non leggibile','reasonNoSpace': 'spazio libero insufficiente','reasonCopyFailed': 'copia non riuscita','reasonBiosTooLarge': 'troppo grande per un BIOS PS2: sembra un gioco — usa l’importazione dei giochi'
    },
    'pt': {
      'chooseBios':'Escolher BIOS PS2','importBiosFirst':'Importe primeiro um ou mais ficheiros BIOS PS2.','biosChoiceHelp':'Esta escolha é usada nos jogos e no arranque do BIOS. Os idiomas disponíveis dependem do BIOS escolhido.','cancel':'Cancelar',
      'gamesImported':'{count} jogo(s) PS2 importado(s).','gamesRejected':'Alguns jogos foram rejeitados.','bootBiosFailed':'Não foi possível iniciar o BIOS PS2.','biosImported':'{count} ficheiro(s) BIOS importado(s). Escolha o BIOS a usar.','biosImportFailed':'Falha ao importar o BIOS.','importFailed':'Falha na importação ARMSX2: {error}',
      'importMenu':'ARMSX2 / Importar','importGames':'Importar jogos','importBios':'Importar um ou mais ficheiros BIOS','bootBios':'Iniciar BIOS PS2',
      'outsideRoot':'O jogo PS2 está fora de ARMSX2/Games.','deleteFailed':'Falha ao eliminar no ARMSX2: {error}','deleteGames':'Eliminar jogos PS2','selectedCount':'{count} jogo(s) selecionado(s)','deselectAll':'Desmarcar tudo','selectAll':'Selecionar tudo','deleting':'A eliminar {done} / {total}…','deleteCount':'Eliminar ({count})',
      'importLine':'{name} — {reason}','importNotImported': '{count} ficheiro(s) não importado(s):','importMore': 'e mais {count}','importAlready': '{count} ficheiro(s) já na biblioteca: não copiado(s) novamente','reasonWrongType': 'tipo de ficheiro incorreto (aceites: {extensions})','reasonUnreadable': 'não é possível ler o ficheiro','reasonNoSpace': 'espaço livre insuficiente','reasonCopyFailed': 'a cópia falhou','reasonBiosTooLarge': 'demasiado grande para um BIOS PS2: parece um jogo — use a importação de jogos'
    },
    'ru': {
      'chooseBios':'Выбрать BIOS PS2','importBiosFirst':'Сначала импортируйте один или несколько файлов BIOS PS2.','biosChoiceHelp':'Этот выбор используется для игр и запуска BIOS. Доступные языки зависят от выбранного BIOS.','cancel':'Отмена',
      'gamesImported':'Импортировано игр PS2: {count}.','gamesRejected':'Некоторые игры были отклонены.','bootBiosFailed':'Не удалось запустить BIOS PS2.','biosImported':'Импортировано файлов BIOS: {count}. Выберите используемый BIOS.','biosImportFailed':'Не удалось импортировать BIOS.','importFailed':'Ошибка импорта ARMSX2: {error}',
      'importMenu':'ARMSX2 / Импорт','importGames':'Импортировать игры','importBios':'Импортировать один или несколько файлов BIOS','bootBios':'Запустить BIOS PS2',
      'outsideRoot':'Игра PS2 находится вне ARMSX2/Games.','deleteFailed':'Ошибка удаления ARMSX2: {error}','deleteGames':'Удалить игры PS2','selectedCount':'Выбрано игр: {count}','deselectAll':'Снять выделение','selectAll':'Выбрать всё','deleting':'Удаление {done} / {total}…','deleteCount':'Удалить ({count})',
      'importLine':'{name} — {reason}','importNotImported': 'Не импортировано файлов ({count}):','importMore': 'и ещё {count}','importAlready': 'Файлов уже в библиотеке: {count}. Повторно не копировались','reasonWrongType': 'неверный тип файла (допустимы: {extensions})','reasonUnreadable': 'файл не читается','reasonNoSpace': 'недостаточно свободного места','reasonCopyFailed': 'не удалось скопировать','reasonBiosTooLarge': 'слишком велик для BIOS PS2: похоже на игру — используйте импорт игр'
    },
    'id': {
      'chooseBios':'Pilih BIOS PS2','importBiosFirst':'Impor satu atau beberapa file BIOS PS2 terlebih dahulu.','biosChoiceHelp':'Pilihan ini digunakan untuk game dan boot BIOS. Bahasa yang tersedia bergantung pada BIOS yang dipilih.','cancel':'Batal',
      'gamesImported':'{count} game PS2 diimpor.','gamesRejected':'Beberapa game ditolak.','bootBiosFailed':'BIOS PS2 tidak dapat dijalankan.','biosImported':'{count} file BIOS diimpor. Pilih BIOS yang akan digunakan.','biosImportFailed':'Impor BIOS gagal.','importFailed':'Impor ARMSX2 gagal: {error}',
      'importMenu':'ARMSX2 / Impor','importGames':'Impor game','importBios':'Impor satu atau beberapa file BIOS','bootBios':'Boot BIOS PS2',
      'outsideRoot':'Game PS2 berada di luar ARMSX2/Games.','deleteFailed':'Penghapusan ARMSX2 gagal: {error}','deleteGames':'Hapus game PS2','selectedCount':'{count} game dipilih','deselectAll':'Batalkan semua pilihan','selectAll':'Pilih semua','deleting':'Menghapus {done} / {total}…','deleteCount':'Hapus ({count})',
      'importLine':'{name} — {reason}','importNotImported': '{count} berkas tidak diimpor:','importMore': 'dan {count} lainnya','importAlready': '{count} berkas sudah ada di pustaka: tidak disalin lagi','reasonWrongType': 'jenis berkas salah (diterima: {extensions})','reasonUnreadable': 'berkas tidak dapat dibaca','reasonNoSpace': 'ruang kosong tidak cukup','reasonCopyFailed': 'penyalinan gagal','reasonBiosTooLarge': 'terlalu besar untuk berkas BIOS PS2: tampaknya sebuah game — gunakan impor game'
    },
    'ja': {
      'chooseBios':'PS2 BIOS を選択','importBiosFirst':'先に 1 つ以上の PS2 BIOS ファイルをインポートしてください。','biosChoiceHelp':'この選択はゲームと BIOS 起動に使用されます。利用できる言語は選択した BIOS によって異なります。','cancel':'キャンセル',
      'gamesImported':'PS2 ゲームを {count} 件インポートしました。','gamesRejected':'一部のゲームは拒否されました。','bootBiosFailed':'PS2 BIOS を起動できませんでした。','biosImported':'BIOS ファイルを {count} 件インポートしました。使用する BIOS を選択してください。','biosImportFailed':'BIOS のインポートに失敗しました。','importFailed':'ARMSX2 のインポートに失敗しました: {error}',
      'importMenu':'ARMSX2 / インポート','importGames':'ゲームをインポート','importBios':'1 つ以上の BIOS ファイルをインポート','bootBios':'PS2 BIOS を起動',
      'outsideRoot':'PS2 ゲームは ARMSX2/Games の外にあります。','deleteFailed':'ARMSX2 の削除に失敗しました: {error}','deleteGames':'PS2 ゲームを削除','selectedCount':'{count} 件のゲームを選択','deselectAll':'すべて選択解除','selectAll':'すべて選択','deleting':'削除中 {done} / {total}…','deleteCount':'削除 ({count})',
      'importLine':'{name} — {reason}','importNotImported': '{count} 件のファイルをインポートできませんでした:','importMore': 'ほか {count} 件','importAlready': '{count} 件のファイルはすでにライブラリにあります: 再コピーしていません','reasonWrongType': 'ファイル形式が正しくありません (対応: {extensions})','reasonUnreadable': 'ファイルを読み取れません','reasonNoSpace': '空き容量が不足しています','reasonCopyFailed': 'コピーに失敗しました','reasonBiosTooLarge': 'PS2 BIOS ファイルとしては大きすぎます: ゲームのようです — ゲームのインポートを使用してください'
    },
    'ko': {
      'chooseBios':'PS2 BIOS 선택','importBiosFirst':'먼저 하나 이상의 PS2 BIOS 파일을 가져오세요.','biosChoiceHelp':'이 선택은 게임과 BIOS 부팅에 사용됩니다. 사용 가능한 언어는 선택한 BIOS에 따라 달라집니다.','cancel':'취소',
      'gamesImported':'PS2 게임 {count}개를 가져왔습니다.','gamesRejected':'일부 게임이 거부되었습니다.','bootBiosFailed':'PS2 BIOS를 부팅할 수 없습니다.','biosImported':'BIOS 파일 {count}개를 가져왔습니다. 사용할 BIOS를 선택하세요.','biosImportFailed':'BIOS 가져오기에 실패했습니다.','importFailed':'ARMSX2 가져오기 실패: {error}',
      'importMenu':'ARMSX2 / 가져오기','importGames':'게임 가져오기','importBios':'하나 이상의 BIOS 파일 가져오기','bootBios':'PS2 BIOS 부팅',
      'outsideRoot':'PS2 게임이 ARMSX2/Games 밖에 있습니다.','deleteFailed':'ARMSX2 삭제 실패: {error}','deleteGames':'PS2 게임 삭제','selectedCount':'게임 {count}개 선택됨','deselectAll':'모두 선택 해제','selectAll':'모두 선택','deleting':'삭제 중 {done} / {total}…','deleteCount':'삭제 ({count})',
      'importLine':'{name} — {reason}','importNotImported': '{count}개 파일을 가져오지 못했습니다:','importMore': '외 {count}개','importAlready': '{count}개 파일은 이미 라이브러리에 있어 다시 복사하지 않았습니다','reasonWrongType': '파일 형식이 올바르지 않습니다(허용: {extensions})','reasonUnreadable': '파일을 읽을 수 없습니다','reasonNoSpace': '여유 공간이 부족합니다','reasonCopyFailed': '복사에 실패했습니다','reasonBiosTooLarge': 'PS2 BIOS 파일로는 너무 큽니다: 게임으로 보입니다 — 게임 가져오기를 사용하세요'
    },
    'zh': {
      'chooseBios':'选择 PS2 BIOS','importBiosFirst':'请先导入一个或多个 PS2 BIOS 文件。','biosChoiceHelp':'此选择用于游戏和 BIOS 启动。可用语言取决于所选 BIOS。','cancel':'取消',
      'gamesImported':'已导入 {count} 个 PS2 游戏。','gamesRejected':'部分游戏被拒绝。','bootBiosFailed':'无法启动 PS2 BIOS。','biosImported':'已导入 {count} 个 BIOS 文件。请选择要使用的 BIOS。','biosImportFailed':'BIOS 导入失败。','importFailed':'ARMSX2 导入失败：{error}',
      'importMenu':'ARMSX2 / 导入','importGames':'导入游戏','importBios':'导入一个或多个 BIOS 文件','bootBios':'启动 PS2 BIOS',
      'outsideRoot':'PS2 游戏位于 ARMSX2/Games 之外。','deleteFailed':'ARMSX2 删除失败：{error}','deleteGames':'删除 PS2 游戏','selectedCount':'已选择 {count} 个游戏','deselectAll':'取消全选','selectAll':'全选','deleting':'正在删除 {done} / {total}…','deleteCount':'删除 ({count})',
      'importLine':'{name} — {reason}','importNotImported': '有 {count} 个文件未导入：','importMore': '另有 {count} 个','importAlready': '{count} 个文件已在库中：未重复复制','reasonWrongType': '文件类型错误（可接受：{extensions}）','reasonUnreadable': '无法读取该文件','reasonNoSpace': '可用空间不足','reasonCopyFailed': '复制失败','reasonBiosTooLarge': '对 PS2 BIOS 文件来说太大：这看起来是游戏——请使用游戏导入'
    },
    'zh_Hant': {
      'chooseBios':'選擇 PS2 BIOS','importBiosFirst':'請先匯入一個或多個 PS2 BIOS 檔案。','biosChoiceHelp':'此選擇用於遊戲與 BIOS 啟動。可用語言取決於所選 BIOS。','cancel':'取消',
      'gamesImported':'已匯入 {count} 個 PS2 遊戲。','gamesRejected':'部分遊戲遭拒。','bootBiosFailed':'無法啟動 PS2 BIOS。','biosImported':'已匯入 {count} 個 BIOS 檔案。請選擇要使用的 BIOS。','biosImportFailed':'BIOS 匯入失敗。','importFailed':'ARMSX2 匯入失敗：{error}',
      'importMenu':'ARMSX2 / 匯入','importGames':'匯入遊戲','importBios':'匯入一個或多個 BIOS 檔案','bootBios':'啟動 PS2 BIOS',
      'outsideRoot':'PS2 遊戲位於 ARMSX2/Games 之外。','deleteFailed':'ARMSX2 刪除失敗：{error}','deleteGames':'刪除 PS2 遊戲','selectedCount':'已選擇 {count} 個遊戲','deselectAll':'取消全選','selectAll':'全選','deleting':'正在刪除 {done} / {total}…','deleteCount':'刪除 ({count})',
      'importLine':'{name} — {reason}','importNotImported': '有 {count} 個檔案未匯入：','importMore': '另有 {count} 個','importAlready': '{count} 個檔案已在資料庫中：未重複複製','reasonWrongType': '檔案類型錯誤（可接受：{extensions}）','reasonUnreadable': '無法讀取該檔案','reasonNoSpace': '可用空間不足','reasonCopyFailed': '複製失敗','reasonBiosTooLarge': '對 PS2 BIOS 檔案來說太大：這看起來是遊戲——請使用遊戲匯入'
    },
  };

  /// The raw per-language tables, without the English fallback of [textFor].
  @visibleForTesting
  static Map<String, Map<String, String>> get rawValues => _v;

  /// The text of [key] in the language [code] (English when missing).
  @visibleForTesting
  static String textFor(String code, String key) =>
      _v[code]?[key] ?? _v['en']![key] ?? key;

  static String text(BuildContext context, String key) {
    final locale = Localizations.localeOf(context);
    var code = locale.languageCode;
    if (code == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' || country == 'TW' || country == 'HK' || country == 'MO') {
        code = 'zh_Hant';
      }
    }
    return _v[code]?[key] ?? _v['en']![key] ?? key;
  }

  static String format(
    BuildContext context,
    String key,
    Map<String, Object?> values,
  ) {
    var value = text(context, key);
    for (final item in values.entries) {
      value = value.replaceAll('{${item.key}}', item.value?.toString() ?? '');
    }
    return value;
  }
}
