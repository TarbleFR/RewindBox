#!/usr/bin/env python3
"""Generate the shared native catalogue's twelve-language resource.

Keep positional strings together: the build check verifies complete keys and
named placeholders for every officially supported language.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYS = """title downloadAll updateAll retryDownloads downloading loading readyCount
progressPacks progressBytes downloadExplanation partialFailure installedReady
loadFailed downloadFailed lookupFailed importFailed technicalDetails close
searchPlaceholder searchHelp searching noMatches noCompatible editionConfirmTitle
editionConfirmMessage cancel chooseEdition exactMatch candidateMatch regions languages
revision unknown provenance compatible unavailable invalid unresolved requiresEngine
unsupported parametersRequired dependenciesMissing dependenciesCycle dependencies
importDisabled importDoneTitle importDoneMessage noAutoEnable programs edition code
importing notInstalled group exclusiveGroup emptyCatalog downloadRequired
downloadRequiredMessage downloadNow availableCount backToEngine""".split()

STRINGS = {
"en": [
"RewindBox cheats", "Download all catalogues", "Update all catalogues", "Retry failed downloads", "Downloading…", "Loading…", "{games} games available offline",
"{done} / {total} catalogues processed", "{done} / {total}", "One download for all supported emulators. Codes remain disabled.", "{count} catalogues could not be downloaded. Completed downloads are kept.", "Catalogues are ready for offline use.",
"The catalogue could not be loaded.", "Some catalogues could not be downloaded.", "The game search could not be completed.", "The codes could not be imported.", "Technical details", "Close",
"Search for a game", "Search the unified catalogue for this console. Confirm the exact edition before importing.", "Searching…", "No matching edition was found.", "No complete code is compatible with this emulator. Other formats need an engine adapter or unresolved parameters.", "Confirm game edition",
"The catalogue has not established an exact match. Confirm that this is your game's edition:\n\n{edition}", "Cancel", "Use this edition", "Exact identity", "Edition to confirm", "Region", "Language",
"Revision", "Not specified", "Sources and authors", "Compatible", "Not available", "Invalid program", "Incomplete program", "Requires another engine",
"This emulator cannot import this program's format.", "This program still contains parameters to resolve.", "A required program is missing or incompatible.", "The required programs contain a circular dependency.", "Required programs",
"Import disabled", "Codes imported", "The complete programs were imported disabled. Return to the emulator's Cheats menu to enable them individually.", "Importing does not enable codes.", "Codes", "Game edition", "Complete program",
"Importing…", "Download required", "Category", "Exclusive choice group", "No catalogue is available yet.", "Download the catalogues",
"Download the unified catalogues, then select this edition again.", "Download all", "{count} compatible programs", "Back to the emulator menu"],
"fr": [
"Cheats RewindBox", "Télécharger tous les catalogues", "Mettre tous les catalogues à jour", "Relancer les téléchargements échoués", "Téléchargement…", "Chargement…", "{games} jeux disponibles hors ligne",
"{done} / {total} catalogues traités", "{done} / {total}", "Un téléchargement pour tous les émulateurs pris en charge. Les codes restent désactivés.", "{count} catalogues n’ont pas pu être téléchargés. Les téléchargements terminés sont conservés.", "Les catalogues sont prêts à être utilisés hors ligne.",
"Impossible de charger le catalogue.", "Certains catalogues n’ont pas pu être téléchargés.", "Impossible de terminer la recherche du jeu.", "Impossible d’importer les codes.", "Détails techniques", "Fermer",
"Rechercher un jeu", "Recherchez dans le catalogue unifié de cette console. Confirmez l’édition exacte avant l’import.", "Recherche…", "Aucune édition correspondante trouvée.", "Aucun code complet n’est compatible avec cet émulateur. Les autres formats nécessitent un adaptateur moteur ou des paramètres à résoudre.", "Confirmer l’édition du jeu",
"Le catalogue n’a pas établi de correspondance exacte. Confirmez qu’il s’agit de l’édition de votre jeu :\n\n{edition}", "Annuler", "Utiliser cette édition", "Identité exacte", "Édition à confirmer", "Région", "Langue",
"Révision", "Non précisée", "Sources et auteurs", "Compatible", "Indisponible", "Programme invalide", "Programme incomplet", "Nécessite un autre moteur",
"Cet émulateur ne peut pas importer le format de ce programme.", "Ce programme contient encore des paramètres à résoudre.", "Un programme requis est absent ou incompatible.", "Les programmes requis contiennent une dépendance circulaire.", "Programmes requis",
"Importer désactivés", "Codes importés", "Les programmes complets ont été importés désactivés. Revenez au menu Cheats de l’émulateur pour les activer individuellement.", "L’import n’active pas les codes.", "Codes", "Édition du jeu", "Programme complet",
"Import en cours…", "Téléchargement requis", "Catégorie", "Groupe de choix exclusifs", "Aucun catalogue n’est disponible pour le moment.", "Télécharger les catalogues",
"Téléchargez les catalogues unifiés, puis sélectionnez à nouveau cette édition.", "Tout télécharger", "{count} programmes compatibles", "Revenir au menu de l’émulateur"],
"es": [
"Trucos de RewindBox", "Descargar todos los catálogos", "Actualizar todos los catálogos", "Reintentar descargas fallidas", "Descargando…", "Cargando…", "{games} juegos disponibles sin conexión",
"{done} / {total} catálogos procesados", "{done} / {total}", "Una descarga para todos los emuladores compatibles. Los códigos permanecen desactivados.", "No se pudieron descargar {count} catálogos. Se conservan las descargas completadas.", "Los catálogos están listos para usarse sin conexión.",
"No se pudo cargar el catálogo.", "No se pudieron descargar algunos catálogos.", "No se pudo completar la búsqueda del juego.", "No se pudieron importar los códigos.", "Detalles técnicos", "Cerrar",
"Buscar un juego", "Busca en el catálogo unificado de esta consola. Confirma la edición exacta antes de importar.", "Buscando…", "No se encontró ninguna edición coincidente.", "Ningún código completo es compatible con este emulador. Otros formatos necesitan un adaptador del motor o parámetros pendientes.", "Confirmar edición del juego",
"El catálogo no ha establecido una coincidencia exacta. Confirma que esta es la edición de tu juego:\n\n{edition}", "Cancelar", "Usar esta edición", "Identidad exacta", "Edición por confirmar", "Región", "Idioma",
"Revisión", "Sin especificar", "Fuentes y autores", "Compatible", "No disponible", "Programa no válido", "Programa incompleto", "Requiere otro motor",
"Este emulador no puede importar el formato de este programa.", "Este programa aún contiene parámetros pendientes.", "Falta un programa necesario o es incompatible.", "Los programas necesarios contienen una dependencia circular.", "Programas necesarios",
"Importar desactivados", "Códigos importados", "Los programas completos se importaron desactivados. Vuelve al menú de trucos del emulador para activarlos individualmente.", "La importación no activa los códigos.", "Códigos", "Edición del juego", "Programa completo",
"Importando…", "Descarga necesaria", "Categoría", "Grupo de opciones excluyentes", "Todavía no hay ningún catálogo disponible.", "Descargar los catálogos",
"Descarga los catálogos unificados y vuelve a seleccionar esta edición.", "Descargar todo", "{count} programas compatibles", "Volver al menú del emulador"],
"de": [
"RewindBox-Cheats", "Alle Kataloge herunterladen", "Alle Kataloge aktualisieren", "Fehlgeschlagene Downloads wiederholen", "Wird heruntergeladen…", "Wird geladen…", "{games} Spiele offline verfügbar",
"{done} / {total} Kataloge verarbeitet", "{done} / {total}", "Ein Download für alle unterstützten Emulatoren. Die Codes bleiben deaktiviert.", "{count} Kataloge konnten nicht heruntergeladen werden. Abgeschlossene Downloads bleiben erhalten.", "Die Kataloge sind offline verfügbar.",
"Der Katalog konnte nicht geladen werden.", "Einige Kataloge konnten nicht heruntergeladen werden.", "Die Spielsuche konnte nicht abgeschlossen werden.", "Die Codes konnten nicht importiert werden.", "Technische Details", "Schließen",
"Spiel suchen", "Suche im gemeinsamen Katalog dieser Konsole. Bestätige vor dem Import die genaue Ausgabe.", "Suche…", "Keine passende Ausgabe gefunden.", "Kein vollständiger Code ist mit diesem Emulator kompatibel. Andere Formate benötigen einen Engine-Adapter oder noch aufzulösende Parameter.", "Spielausgabe bestätigen",
"Der Katalog hat keine genaue Übereinstimmung festgestellt. Bestätige, dass dies die Ausgabe deines Spiels ist:\n\n{edition}", "Abbrechen", "Diese Ausgabe verwenden", "Genaue Identität", "Ausgabe bestätigen", "Region", "Sprache",
"Revision", "Nicht angegeben", "Quellen und Autoren", "Kompatibel", "Nicht verfügbar", "Ungültiges Programm", "Unvollständiges Programm", "Andere Engine erforderlich",
"Dieser Emulator kann das Format dieses Programms nicht importieren.", "Dieses Programm enthält noch aufzulösende Parameter.", "Ein erforderliches Programm fehlt oder ist inkompatibel.", "Die erforderlichen Programme enthalten eine zyklische Abhängigkeit.", "Erforderliche Programme",
"Deaktiviert importieren", "Codes importiert", "Die vollständigen Programme wurden deaktiviert importiert. Aktiviere sie einzeln im Cheat-Menü des Emulators.", "Der Import aktiviert keine Codes.", "Codes", "Spielausgabe", "Vollständiges Programm",
"Wird importiert…", "Download erforderlich", "Kategorie", "Gruppe sich ausschließender Optionen", "Noch kein Katalog verfügbar.", "Kataloge herunterladen",
"Lade die gemeinsamen Kataloge herunter und wähle diese Ausgabe erneut aus.", "Alle herunterladen", "{count} kompatible Programme", "Zurück zum Emulator-Menü"],
"it": [
"Trucchi RewindBox", "Scarica tutti i cataloghi", "Aggiorna tutti i cataloghi", "Riprova i download non riusciti", "Download…", "Caricamento…", "{games} giochi disponibili offline",
"{done} / {total} cataloghi elaborati", "{done} / {total}", "Un solo download per tutti gli emulatori supportati. I codici restano disattivati.", "Impossibile scaricare {count} cataloghi. I download completati vengono conservati.", "I cataloghi sono pronti per l’uso offline.",
"Impossibile caricare il catalogo.", "Impossibile scaricare alcuni cataloghi.", "Impossibile completare la ricerca del gioco.", "Impossibile importare i codici.", "Dettagli tecnici", "Chiudi",
"Cerca un gioco", "Cerca nel catalogo unificato di questa console. Conferma l’edizione esatta prima dell’importazione.", "Ricerca…", "Nessuna edizione corrispondente trovata.", "Nessun codice completo è compatibile con questo emulatore. Gli altri formati richiedono un adattatore del motore o parametri da risolvere.", "Conferma edizione del gioco",
"Il catalogo non ha stabilito una corrispondenza esatta. Conferma che questa è l’edizione del tuo gioco:\n\n{edition}", "Annulla", "Usa questa edizione", "Identità esatta", "Edizione da confermare", "Regione", "Lingua",
"Revisione", "Non specificata", "Fonti e autori", "Compatibile", "Non disponibile", "Programma non valido", "Programma incompleto", "Richiede un altro motore",
"Questo emulatore non può importare il formato di questo programma.", "Questo programma contiene ancora parametri da risolvere.", "Un programma richiesto è assente o incompatibile.", "I programmi richiesti contengono una dipendenza circolare.", "Programmi richiesti",
"Importa disattivati", "Codici importati", "I programmi completi sono stati importati disattivati. Torna al menu Trucchi dell’emulatore per attivarli singolarmente.", "L’importazione non attiva i codici.", "Codici", "Edizione del gioco", "Programma completo",
"Importazione…", "Download richiesto", "Categoria", "Gruppo di scelte esclusive", "Nessun catalogo è ancora disponibile.", "Scarica i cataloghi",
"Scarica i cataloghi unificati, poi seleziona di nuovo questa edizione.", "Scarica tutto", "{count} programmi compatibili", "Torna al menu dell’emulatore"],
"pt": [
"Cheats do RewindBox", "Baixar todos os catálogos", "Atualizar todos os catálogos", "Tentar novamente os downloads com falha", "Baixando…", "Carregando…", "{games} jogos disponíveis offline",
"{done} / {total} catálogos processados", "{done} / {total}", "Um download para todos os emuladores compatíveis. Os códigos permanecem desativados.", "Não foi possível baixar {count} catálogos. Os downloads concluídos são mantidos.", "Os catálogos estão prontos para uso offline.",
"Não foi possível carregar o catálogo.", "Não foi possível baixar alguns catálogos.", "Não foi possível concluir a busca pelo jogo.", "Não foi possível importar os códigos.", "Detalhes técnicos", "Fechar",
"Buscar um jogo", "Busque no catálogo unificado deste console. Confirme a edição exata antes de importar.", "Buscando…", "Nenhuma edição correspondente encontrada.", "Nenhum código completo é compatível com este emulador. Outros formatos exigem um adaptador do motor ou parâmetros a resolver.", "Confirmar edição do jogo",
"O catálogo não estabeleceu uma correspondência exata. Confirme que esta é a edição do seu jogo:\n\n{edition}", "Cancelar", "Usar esta edição", "Identidade exata", "Edição a confirmar", "Região", "Idioma",
"Revisão", "Não especificada", "Fontes e autores", "Compatível", "Indisponível", "Programa inválido", "Programa incompleto", "Exige outro motor",
"Este emulador não pode importar o formato deste programa.", "Este programa ainda contém parâmetros a resolver.", "Um programa necessário está ausente ou é incompatível.", "Os programas necessários contêm uma dependência circular.", "Programas necessários",
"Importar desativados", "Códigos importados", "Os programas completos foram importados desativados. Volte ao menu Cheats do emulador para ativá-los individualmente.", "A importação não ativa os códigos.", "Códigos", "Edição do jogo", "Programa completo",
"Importando…", "Download necessário", "Categoria", "Grupo de escolhas exclusivas", "Nenhum catálogo está disponível ainda.", "Baixar os catálogos",
"Baixe os catálogos unificados e selecione esta edição novamente.", "Baixar tudo", "{count} programas compatíveis", "Voltar ao menu do emulador"],
"ru": [
"Читы RewindBox", "Скачать все каталоги", "Обновить все каталоги", "Повторить неудачные загрузки", "Загрузка…", "Загрузка…", "Игр доступно без сети: {games}",
"Обработано каталогов: {done} / {total}", "{done} / {total}", "Одна загрузка для всех поддерживаемых эмуляторов. Коды остаются выключенными.", "Не удалось скачать каталогов: {count}. Завершённые загрузки сохранены.", "Каталоги готовы к использованию без сети.",
"Не удалось загрузить каталог.", "Не удалось скачать некоторые каталоги.", "Не удалось завершить поиск игры.", "Не удалось импортировать коды.", "Технические сведения", "Закрыть",
"Поиск игры", "Поиск в общем каталоге этой консоли. Перед импортом подтвердите точное издание.", "Поиск…", "Подходящее издание не найдено.", "Для этого эмулятора нет совместимых полных кодов. Другим форматам нужен адаптер движка или уточнение параметров.", "Подтвердите издание игры",
"Каталог не установил точное совпадение. Подтвердите, что это издание вашей игры:\n\n{edition}", "Отмена", "Выбрать это издание", "Точная идентификация", "Требуется подтверждение", "Регион", "Язык",
"Ревизия", "Не указана", "Источники и авторы", "Совместим", "Недоступен", "Недопустимая программа", "Неполная программа", "Требуется другой движок",
"Этот эмулятор не может импортировать формат данной программы.", "В программе ещё остались неуточнённые параметры.", "Необходимая программа отсутствует или несовместима.", "Необходимые программы содержат циклическую зависимость.", "Необходимые программы",
"Импортировать выключенными", "Коды импортированы", "Полные программы импортированы выключенными. Вернитесь в меню читов эмулятора и включите нужные коды по отдельности.", "Импорт не включает коды.", "Коды", "Издание игры", "Полная программа",
"Импорт…", "Требуется загрузка", "Категория", "Группа взаимоисключающих вариантов", "Каталоги пока недоступны.", "Скачать каталоги",
"Скачайте общие каталоги, затем снова выберите это издание.", "Скачать всё", "Совместимых программ: {count}", "Вернуться в меню эмулятора"],
"id": [
"Cheat RewindBox", "Unduh semua katalog", "Perbarui semua katalog", "Ulangi unduhan yang gagal", "Mengunduh…", "Memuat…", "{games} game tersedia offline",
"{done} / {total} katalog diproses", "{done} / {total}", "Satu unduhan untuk semua emulator yang didukung. Kode tetap nonaktif.", "{count} katalog tidak dapat diunduh. Unduhan yang selesai tetap disimpan.", "Katalog siap digunakan offline.",
"Katalog tidak dapat dimuat.", "Beberapa katalog tidak dapat diunduh.", "Pencarian game tidak dapat diselesaikan.", "Kode tidak dapat diimpor.", "Detail teknis", "Tutup",
"Cari game", "Cari di katalog terpadu untuk konsol ini. Konfirmasikan edisi yang tepat sebelum mengimpor.", "Mencari…", "Tidak ditemukan edisi yang sesuai.", "Tidak ada kode lengkap yang kompatibel dengan emulator ini. Format lain memerlukan adaptor mesin atau parameter yang belum diselesaikan.", "Konfirmasi edisi game",
"Katalog belum memastikan kecocokan tepat. Konfirmasikan bahwa ini edisi game Anda:\n\n{edition}", "Batal", "Gunakan edisi ini", "Identitas tepat", "Edisi perlu dikonfirmasi", "Wilayah", "Bahasa",
"Revisi", "Tidak disebutkan", "Sumber dan penulis", "Kompatibel", "Tidak tersedia", "Program tidak valid", "Program tidak lengkap", "Memerlukan mesin lain",
"Emulator ini tidak dapat mengimpor format program ini.", "Program ini masih memiliki parameter yang harus diselesaikan.", "Program yang diperlukan tidak ada atau tidak kompatibel.", "Program yang diperlukan memiliki dependensi melingkar.", "Program yang diperlukan",
"Impor dalam keadaan nonaktif", "Kode diimpor", "Program lengkap diimpor dalam keadaan nonaktif. Kembali ke menu Cheat emulator untuk mengaktifkannya satu per satu.", "Mengimpor tidak mengaktifkan kode.", "Kode", "Edisi game", "Program lengkap",
"Mengimpor…", "Perlu diunduh", "Kategori", "Grup pilihan eksklusif", "Belum ada katalog yang tersedia.", "Unduh katalog",
"Unduh katalog terpadu, lalu pilih edisi ini kembali.", "Unduh semua", "{count} program kompatibel", "Kembali ke menu emulator"],
"zh": [
"RewindBox 金手指", "下载全部目录", "更新全部目录", "重试失败的下载", "正在下载…", "正在加载…", "{games} 款游戏可离线使用",
"已处理 {done} / {total} 个目录", "{done} / {total}", "一次下载所有受支持模拟器的目录。代码保持禁用。", "{count} 个目录未能下载。已完成的下载将保留。", "目录已可离线使用。",
"无法加载目录。", "部分目录未能下载。", "无法完成游戏搜索。", "无法导入代码。", "技术详情", "关闭",
"搜索游戏", "在此主机的统一目录中搜索。导入前请确认确切版本。", "正在搜索…", "未找到匹配的游戏版本。", "没有完整代码与此模拟器兼容。其他格式需要引擎适配器或尚待确定的参数。", "确认游戏版本",
"目录尚未确定完全匹配。请确认这是您所用游戏的版本：\n\n{edition}", "取消", "使用此版本", "精确识别", "需要确认版本", "地区", "语言",
"修订版", "未注明", "来源和作者", "兼容", "不可用", "无效程序", "不完整的程序", "需要其他引擎",
"此模拟器无法导入该程序的格式。", "此程序仍包含待确定的参数。", "缺少所需程序或其不兼容。", "所需程序包含循环依赖。", "所需程序",
"以禁用状态导入", "代码已导入", "完整程序已以禁用状态导入。请返回模拟器的金手指菜单逐项启用。", "导入不会启用代码。", "代码", "游戏版本", "完整程序",
"正在导入…", "需要下载", "类别", "互斥选项组", "目前没有可用目录。", "下载目录",
"下载统一目录后，请再次选择此版本。", "全部下载", "{count} 个兼容程序", "返回模拟器菜单"],
"zh_Hant": [
"RewindBox 金手指", "下載全部目錄", "更新全部目錄", "重試失敗的下載", "正在下載…", "正在載入…", "{games} 款遊戲可離線使用",
"已處理 {done} / {total} 個目錄", "{done} / {total}", "一次下載所有支援模擬器的目錄。代碼保持停用。", "{count} 個目錄未能下載。已完成的下載將保留。", "目錄已可離線使用。",
"無法載入目錄。", "部分目錄未能下載。", "無法完成遊戲搜尋。", "無法匯入代碼。", "技術詳細資訊", "關閉",
"搜尋遊戲", "在此主機的統一目錄中搜尋。匯入前請確認確切版本。", "正在搜尋…", "找不到相符的遊戲版本。", "沒有完整代碼與此模擬器相容。其他格式需要引擎配接器或尚待確定的參數。", "確認遊戲版本",
"目錄尚未確定完全相符。請確認這是您使用的遊戲版本：\n\n{edition}", "取消", "使用此版本", "精確識別", "需要確認版本", "地區", "語言",
"修訂版", "未註明", "來源和作者", "相容", "無法使用", "無效程式", "不完整的程式", "需要其他引擎",
"此模擬器無法匯入該程式的格式。", "此程式仍包含待確定的參數。", "缺少所需程式或其不相容。", "所需程式包含循環相依性。", "所需程式",
"以停用狀態匯入", "代碼已匯入", "完整程式已以停用狀態匯入。請返回模擬器的金手指選單逐項啟用。", "匯入不會啟用代碼。", "代碼", "遊戲版本", "完整程式",
"正在匯入…", "需要下載", "類別", "互斥選項群組", "目前沒有可用目錄。", "下載目錄",
"下載統一目錄後，請再次選擇此版本。", "全部下載", "{count} 個相容程式", "返回模擬器選單"],
"ja": [
"RewindBox チート", "すべてのカタログをダウンロード", "すべてのカタログを更新", "失敗したダウンロードを再試行", "ダウンロード中…", "読み込み中…", "{games} 本のゲームをオフラインで利用可能",
"処理済みカタログ：{done} / {total}", "{done} / {total}", "すべての対応エミュレーターのカタログを一度にダウンロードします。コードは無効のままです。", "{count} 個のカタログをダウンロードできませんでした。完了した分は保持されます。", "カタログをオフラインで利用できます。",
"カタログを読み込めませんでした。", "一部のカタログをダウンロードできませんでした。", "ゲームの検索を完了できませんでした。", "コードをインポートできませんでした。", "技術的な詳細", "閉じる",
"ゲームを検索", "このゲーム機の統合カタログを検索します。インポート前に正確な版を確認してください。", "検索中…", "一致する版が見つかりませんでした。", "このエミュレーターに対応する完全なコードはありません。ほかの形式にはエンジンアダプターや未確定パラメーターの解決が必要です。", "ゲームの版を確認",
"カタログでは完全一致を確認できませんでした。お使いのゲームが次の版であることを確認してください：\n\n{edition}", "キャンセル", "この版を使用", "正確な識別", "版の確認が必要", "地域", "言語",
"リビジョン", "記載なし", "出典と作者", "対応", "利用不可", "無効なプログラム", "不完全なプログラム", "別のエンジンが必要",
"このエミュレーターではこのプログラムの形式をインポートできません。", "このプログラムには未確定のパラメーターがあります。", "必要なプログラムがないか、対応していません。", "必要なプログラムに循環依存があります。", "必要なプログラム",
"無効のままインポート", "コードをインポートしました", "完全なプログラムを無効のままインポートしました。エミュレーターのチートメニューに戻り、個別に有効にしてください。", "インポートしてもコードは有効になりません。", "コード", "ゲームの版", "完全なプログラム",
"インポート中…", "ダウンロードが必要", "カテゴリー", "排他選択グループ", "利用できるカタログはまだありません。", "カタログをダウンロード",
"統合カタログをダウンロードしてから、この版をもう一度選択してください。", "すべてダウンロード", "{count} 個の対応プログラム", "エミュレーターのメニューへ戻る"],
"ko": [
"RewindBox 치트", "모든 카탈로그 다운로드", "모든 카탈로그 업데이트", "실패한 다운로드 재시도", "다운로드 중…", "불러오는 중…", "게임 {games}개 오프라인 사용 가능",
"처리한 카탈로그 {done} / {total}", "{done} / {total}", "지원되는 모든 에뮬레이터의 카탈로그를 한 번에 다운로드합니다. 코드는 비활성 상태로 유지됩니다.", "카탈로그 {count}개를 다운로드하지 못했습니다. 완료된 다운로드는 유지됩니다.", "카탈로그를 오프라인에서 사용할 수 있습니다.",
"카탈로그를 불러올 수 없습니다.", "일부 카탈로그를 다운로드할 수 없습니다.", "게임 검색을 완료할 수 없습니다.", "코드를 가져올 수 없습니다.", "기술 세부 정보", "닫기",
"게임 검색", "이 콘솔의 통합 카탈로그를 검색합니다. 가져오기 전에 정확한 판본을 확인하세요.", "검색 중…", "일치하는 판본을 찾지 못했습니다.", "이 에뮬레이터와 호환되는 완전한 코드가 없습니다. 다른 형식에는 엔진 어댑터 또는 미해결 매개변수 처리가 필요합니다.", "게임 판본 확인",
"카탈로그에서 정확한 일치를 확인하지 못했습니다. 다음이 사용 중인 게임의 판본인지 확인하세요:\n\n{edition}", "취소", "이 판본 사용", "정확한 식별", "판본 확인 필요", "지역", "언어",
"리비전", "명시되지 않음", "출처 및 작성자", "호환됨", "사용 불가", "잘못된 프로그램", "불완전한 프로그램", "다른 엔진 필요",
"이 에뮬레이터는 이 프로그램의 형식을 가져올 수 없습니다.", "이 프로그램에는 아직 해결할 매개변수가 있습니다.", "필수 프로그램이 없거나 호환되지 않습니다.", "필수 프로그램에 순환 의존성이 있습니다.", "필수 프로그램",
"비활성 상태로 가져오기", "코드를 가져옴", "완전한 프로그램을 비활성 상태로 가져왔습니다. 에뮬레이터의 치트 메뉴로 돌아가 개별적으로 활성화하세요.", "가져오기는 코드를 활성화하지 않습니다.", "코드", "게임 판본", "전체 프로그램",
"가져오는 중…", "다운로드 필요", "범주", "상호 배타적 선택 그룹", "아직 사용 가능한 카탈로그가 없습니다.", "카탈로그 다운로드",
"통합 카탈로그를 다운로드한 후 이 판본을 다시 선택하세요.", "모두 다운로드", "호환 프로그램 {count}개", "에뮬레이터 메뉴로 돌아가기"],
}


ENTRY_LABELS = {
    "en": ("Unified cheat catalogue", "No additional program required"),
    "fr": ("Catalogue de cheats unifié", "Aucun programme supplémentaire requis"),
    "es": ("Catálogo unificado de trucos", "No se necesita ningún programa adicional"),
    "de": ("Gemeinsamer Cheat-Katalog", "Kein zusätzliches Programm erforderlich"),
    "it": ("Catalogo unificato dei trucchi", "Non è richiesto alcun programma aggiuntivo"),
    "pt": ("Catálogo unificado de cheats", "Nenhum programa adicional necessário"),
    "ru": ("Общий каталог читов", "Дополнительные программы не нужны"),
    "id": ("Katalog cheat terpadu", "Tidak perlu program tambahan"),
    "zh": ("统一金手指目录", "无需额外程序"),
    "zh_Hant": ("統一金手指目錄", "無需額外程式"),
    "ja": ("統合チートカタログ", "追加のプログラムは不要です"),
    "ko": ("통합 치트 카탈로그", "추가 프로그램이 필요하지 않습니다"),
}

EXCLUSIVE_ERRORS = {
    "en": "The required programs contain mutually exclusive choices.",
    "fr": "Les programmes requis contiennent des choix incompatibles entre eux.",
    "es": "Los programas necesarios contienen opciones mutuamente excluyentes.",
    "de": "Die erforderlichen Programme enthalten sich gegenseitig ausschließende Optionen.",
    "it": "I programmi richiesti contengono scelte che si escludono a vicenda.",
    "pt": "Os programas necessários contêm escolhas mutuamente exclusivas.",
    "ru": "Необходимые программы содержат взаимоисключающие варианты.",
    "id": "Program yang diperlukan memiliki pilihan yang saling meniadakan.",
    "zh": "所需程序包含互斥选项。", "zh_Hant": "所需程式包含互斥選項。",
    "ja": "必要なプログラムに同時使用できない選択肢が含まれています。",
    "ko": "필수 프로그램에 상호 배타적인 선택 사항이 포함되어 있습니다.",
}

NOTES_LABELS = {
    "en": "Author's notes", "fr": "Notes de l’auteur", "es": "Notas del autor",
    "de": "Hinweise des Autors", "it": "Note dell’autore", "pt": "Notas do autor",
    "ru": "Примечания автора", "id": "Catatan penulis", "zh": "作者说明",
    "zh_Hant": "作者說明", "ja": "作者の説明", "ko": "작성자 참고 사항",
}

PART_LABELS = {
    "en": "Catalogue part {part} / {parts}", "fr": "Partie du catalogue {part} / {parts}",
    "es": "Parte del catálogo {part} / {parts}", "de": "Katalogteil {part} / {parts}",
    "it": "Parte del catalogo {part} / {parts}", "pt": "Parte do catálogo {part} / {parts}",
    "ru": "Часть каталога {part} / {parts}", "id": "Bagian katalog {part} / {parts}",
    "zh": "目录分卷 {part} / {parts}", "zh_Hant": "目錄分卷 {part} / {parts}",
    "ja": "カタログの分割 {part} / {parts}", "ko": "카탈로그 부분 {part} / {parts}",
}

SIZE_LABELS = {
    "en": ("Full download: {size}", "Estimated offline storage: {size}"),
    "fr": ("Téléchargement complet : {size}", "Stockage hors ligne estimé : {size}"),
    "es": ("Descarga completa: {size}", "Almacenamiento sin conexión estimado: {size}"),
    "de": ("Vollständiger Download: {size}", "Geschätzter Offline-Speicherbedarf: {size}"),
    "it": ("Download completo: {size}", "Spazio offline stimato: {size}"),
    "pt": ("Download completo: {size}", "Armazenamento offline estimado: {size}"),
    "ru": ("Полная загрузка: {size}", "Примерный объём для работы без сети: {size}"),
    "id": ("Unduhan lengkap: {size}", "Perkiraan penyimpanan offline: {size}"),
    "zh": ("完整下载：{size}", "预计离线存储：{size}"),
    "zh_Hant": ("完整下載：{size}", "預計離線儲存空間：{size}"),
    "ja": ("全体のダウンロード容量：{size}", "オフライン保存の推定容量：{size}"),
    "ko": ("전체 다운로드: {size}", "예상 오프라인 저장 공간: {size}"),
}

EDITION_MISMATCH_LABELS = {
    "en": "This catalogue edition conflicts with the current game's region, language, revision or identity. You can view its codes, but cannot import them.",
    "fr": "Cette édition du catalogue ne correspond pas à la région, à la langue, à la révision ou à l’identité du jeu en cours. Ses codes sont consultables, mais leur import est bloqué.",
    "es": "Esta edición del catálogo no coincide con la región, el idioma, la revisión o la identidad del juego actual. Puedes consultar sus códigos, pero no importarlos.",
    "de": "Diese Katalogausgabe widerspricht der Region, Sprache, Revision oder Identität des aktuellen Spiels. Die Codes können angezeigt, aber nicht importiert werden.",
    "it": "Questa edizione del catalogo non corrisponde alla regione, alla lingua, alla revisione o all’identità del gioco attuale. Puoi consultare i codici, ma non importarli.",
    "pt": "Esta edição do catálogo não corresponde à região, ao idioma, à revisão ou à identidade do jogo atual. Os códigos podem ser consultados, mas não importados.",
    "ru": "Это издание каталога не соответствует региону, языку, ревизии или идентификатору текущей игры. Коды можно просматривать, но нельзя импортировать.",
    "id": "Edisi katalog ini tidak sesuai dengan wilayah, bahasa, revisi, atau identitas game saat ini. Kodenya dapat dilihat, tetapi tidak dapat diimpor.",
    "zh": "此目录版本与当前游戏的地区、语言、修订版或身份信息冲突。可以查看代码，但无法导入。",
    "zh_Hant": "此目錄版本與目前遊戲的地區、語言、修訂版或識別資訊衝突。可以檢視代碼，但無法匯入。",
    "ja": "このカタログの版は、現在のゲームの地域、言語、リビジョンまたは識別情報と一致しません。コードは閲覧できますが、インポートできません。",
    "ko": "이 카탈로그 판본은 현재 게임의 지역, 언어, 리비전 또는 식별 정보와 충돌합니다. 코드를 볼 수는 있지만 가져올 수는 없습니다.",
}

FBNEO_KEYS = ("fbneoSessionHelp", "fbneoRestartHelp", "fbneoRefresh", "fbneoNoCodes",
              "fbneoImportDoneMessage", "fbneoCommandFailed", "fbneoDisabled", "fbneoRestartRequired")
FBNEO_LABELS = {
    "en": (
        "Choose codes explicitly here. Choices last only for this session; codes start disabled whenever the game opens.",
        "Newly imported codes load after closing and reopening this game.", "Refresh native cheats",
        "No native codes are loaded. Import from the unified catalogue, then reopen the game.",
        "The complete programs were installed disabled. Close and reopen this game, then enable the required codes in this menu.",
        "The native cheat command could not be completed.", "Disabled", "Restart required"),
    "fr": (
        "Choisissez explicitement les codes ici. Les choix durent uniquement cette session ; les codes sont désactivés à chaque ouverture du jeu.",
        "Les codes nouvellement importés se chargent après avoir fermé puis rouvert ce jeu.", "Actualiser les cheats natifs",
        "Aucun code natif n’est chargé. Importez depuis le catalogue unifié, puis rouvrez le jeu.",
        "Les programmes complets ont été installés désactivés. Fermez puis rouvrez ce jeu et activez ensuite les codes souhaités dans ce menu.",
        "Impossible de terminer la commande de cheats natifs.", "Désactivé", "Relancement requis"),
    "es": (
        "Elige los códigos explícitamente aquí. Las opciones duran solo esta sesión; los códigos se desactivan cada vez que se abre el juego.",
        "Los códigos recién importados se cargan después de cerrar y volver a abrir este juego.", "Actualizar trucos nativos",
        "No hay códigos nativos cargados. Importa desde el catálogo unificado y vuelve a abrir el juego.",
        "Los programas completos se instalaron desactivados. Cierra y vuelve a abrir este juego, y activa después los códigos deseados en este menú.",
        "No se pudo completar la orden de trucos nativos.", "Desactivado", "Es necesario reiniciar el juego"),
    "de": (
        "Wähle die Codes hier ausdrücklich aus. Die Auswahl gilt nur für diese Sitzung; bei jedem Spielstart sind die Codes deaktiviert.",
        "Neu importierte Codes werden nach dem Schließen und erneuten Öffnen dieses Spiels geladen.", "Native Cheats aktualisieren",
        "Keine nativen Codes geladen. Importiere sie aus dem gemeinsamen Katalog und öffne das Spiel erneut.",
        "Die vollständigen Programme wurden deaktiviert installiert. Schließe und öffne das Spiel erneut und aktiviere dann die gewünschten Codes in diesem Menü.",
        "Der native Cheat-Befehl konnte nicht abgeschlossen werden.", "Deaktiviert", "Neustart des Spiels erforderlich"),
    "it": (
        "Scegli esplicitamente i codici qui. Le scelte valgono solo per questa sessione; i codici sono disattivati a ogni apertura del gioco.",
        "I codici appena importati vengono caricati dopo aver chiuso e riaperto questo gioco.", "Aggiorna i trucchi nativi",
        "Nessun codice nativo caricato. Importa dal catalogo unificato, poi riapri il gioco.",
        "I programmi completi sono stati installati disattivati. Chiudi e riapri questo gioco, poi attiva i codici desiderati in questo menu.",
        "Impossibile completare il comando dei trucchi nativi.", "Disattivato", "Riavvio del gioco richiesto"),
    "pt": (
        "Escolha explicitamente os códigos aqui. As escolhas valem apenas nesta sessão; os códigos começam desativados a cada abertura do jogo.",
        "Os códigos recém-importados são carregados após fechar e reabrir este jogo.", "Atualizar cheats nativos",
        "Nenhum código nativo carregado. Importe do catálogo unificado e reabra o jogo.",
        "Os programas completos foram instalados desativados. Feche e reabra este jogo e ative os códigos desejados neste menu.",
        "Não foi possível concluir o comando de cheats nativos.", "Desativado", "É necessário reabrir o jogo"),
    "ru": (
        "Выбирайте коды здесь вручную. Выбор действует только в этой сессии; при каждом запуске игры коды выключены.",
        "Новые импортированные коды загрузятся после закрытия и повторного открытия игры.", "Обновить встроенные читы",
        "Встроенные коды не загружены. Импортируйте их из общего каталога и откройте игру заново.",
        "Полные программы установлены выключенными. Закройте и заново откройте игру, затем включите нужные коды в этом меню.",
        "Не удалось выполнить команду встроенных читов.", "Выключено", "Требуется перезапуск игры"),
    "id": (
        "Pilih kode secara eksplisit di sini. Pilihan hanya berlaku untuk sesi ini; kode selalu nonaktif setiap kali game dibuka.",
        "Kode yang baru diimpor dimuat setelah game ditutup dan dibuka kembali.", "Segarkan cheat bawaan",
        "Tidak ada kode bawaan yang dimuat. Impor dari katalog terpadu, lalu buka kembali game.",
        "Program lengkap dipasang dalam keadaan nonaktif. Tutup dan buka kembali game ini, lalu aktifkan kode yang diinginkan di menu ini.",
        "Perintah cheat bawaan tidak dapat diselesaikan.", "Nonaktif", "Game perlu dibuka kembali"),
    "zh": (
        "请在此明确选择代码。选择仅在当前会话有效；每次打开游戏时代码均处于禁用状态。",
        "关闭并重新打开此游戏后，将加载新导入的代码。", "刷新原生金手指",
        "未加载原生代码。请从统一目录导入，然后重新打开游戏。",
        "完整程序已以禁用状态安装。请关闭并重新打开此游戏，再在此菜单中启用所需代码。",
        "无法完成原生金手指命令。", "已禁用", "需要重新打开游戏"),
    "zh_Hant": (
        "請在此明確選擇代碼。選擇僅在目前工作階段有效；每次開啟遊戲時代碼均處於停用狀態。",
        "關閉並重新開啟此遊戲後，將載入新匯入的代碼。", "重新整理原生金手指",
        "未載入原生代碼。請從統一目錄匯入，然後重新開啟遊戲。",
        "完整程式已以停用狀態安裝。請關閉並重新開啟此遊戲，再於此選單啟用所需代碼。",
        "無法完成原生金手指命令。", "已停用", "需要重新開啟遊戲"),
    "ja": (
        "ここでコードを明示的に選択してください。選択は現在のセッションでのみ有効で、ゲームを開くたびにコードは無効になります。",
        "新しくインポートしたコードは、このゲームを閉じて開き直すと読み込まれます。", "ネイティブチートを更新",
        "ネイティブコードは読み込まれていません。統合カタログからインポートし、ゲームを開き直してください。",
        "完全なプログラムを無効のままインストールしました。このゲームを閉じて開き直し、このメニューで必要なコードを有効にしてください。",
        "ネイティブチートの操作を完了できませんでした。", "無効", "ゲームの再起動が必要"),
    "ko": (
        "여기서 코드를 명시적으로 선택하세요. 선택은 현재 세션에서만 유효하며 게임을 열 때마다 코드는 비활성 상태로 시작합니다.",
        "게임을 닫고 다시 열면 새로 가져온 코드를 불러옵니다.", "네이티브 치트 새로 고침",
        "불러온 네이티브 코드가 없습니다. 통합 카탈로그에서 가져온 후 게임을 다시 여세요.",
        "완전한 프로그램을 비활성 상태로 설치했습니다. 이 게임을 닫고 다시 연 다음 이 메뉴에서 필요한 코드를 활성화하세요.",
        "네이티브 치트 명령을 완료할 수 없습니다.", "비활성화됨", "게임을 다시 열어야 함"),
}

ACTIVATION_CONFLICT_LABELS = {
    "en": ("These codes are mutually exclusive. Disable the conflicting code before enabling this one.",
           "This code cannot run with the other active GBA codes. Disable conflicting codes and try again. Compatible VBA codes can remain enabled."),
    "fr": ("Ces codes sont incompatibles entre eux. Désactivez le code en conflit avant d’activer celui-ci.",
           "Ce code ne peut pas fonctionner avec les autres codes GBA actifs. Désactivez les codes en conflit, puis réessayez. Les codes VBA compatibles peuvent rester actifs."),
    "es": ("Estos códigos son mutuamente excluyentes. Desactiva el código en conflicto antes de activar este.",
           "Este código no puede funcionar con los otros códigos GBA activos. Desactiva los códigos en conflicto y vuelve a intentarlo. Los códigos VBA compatibles pueden seguir activos."),
    "de": ("Diese Codes schließen sich gegenseitig aus. Deaktiviere den widersprüchlichen Code, bevor du diesen aktivierst.",
           "Dieser Code kann nicht zusammen mit den anderen aktiven GBA-Codes laufen. Deaktiviere die widersprüchlichen Codes und versuche es erneut. Kompatible VBA-Codes können aktiviert bleiben."),
    "it": ("Questi codici si escludono a vicenda. Disattiva il codice in conflitto prima di attivare questo.",
           "Questo codice non può funzionare con gli altri codici GBA attivi. Disattiva i codici in conflitto e riprova. I codici VBA compatibili possono restare attivi."),
    "pt": ("Estes códigos são mutuamente exclusivos. Desative o código em conflito antes de ativar este.",
           "Este código não pode funcionar com os outros códigos GBA ativos. Desative os códigos em conflito e tente novamente. Os códigos VBA compatíveis podem permanecer ativos."),
    "ru": ("Эти коды взаимоисключающие. Выключите конфликтующий код, прежде чем включать этот.",
           "Этот код нельзя использовать с другими активными кодами GBA. Выключите конфликтующие коды и повторите попытку. Совместимые коды VBA могут оставаться включёнными."),
    "id": ("Kode-kode ini saling meniadakan. Nonaktifkan kode yang bertentangan sebelum mengaktifkan kode ini.",
           "Kode ini tidak dapat berjalan bersama kode GBA aktif lainnya. Nonaktifkan kode yang bertentangan dan coba lagi. Kode VBA yang kompatibel boleh tetap aktif."),
    "zh": ("这些代码互斥。请先禁用冲突代码，再启用此代码。",
           "此代码无法与其他已启用的 GBA 代码同时运行。请禁用冲突代码后重试。兼容的 VBA 代码可保持启用。"),
    "zh_Hant": ("這些代碼互斥。請先停用衝突代碼，再啟用此代碼。",
                "此代碼無法與其他已啟用的 GBA 代碼同時執行。請停用衝突代碼後重試。相容的 VBA 代碼可保持啟用。"),
    "ja": ("これらのコードは同時に使用できません。このコードを有効にする前に、競合するコードを無効にしてください。",
           "このコードは、ほかの有効な GBA コードと同時に使用できません。競合するコードを無効にして再試行してください。対応する VBA コードは有効のままにできます。"),
    "ko": ("이 코드들은 동시에 사용할 수 없습니다. 이 코드를 활성화하기 전에 충돌하는 코드를 비활성화하세요.",
           "이 코드는 다른 활성 GBA 코드와 함께 실행할 수 없습니다. 충돌하는 코드를 비활성화하고 다시 시도하세요. 호환되는 VBA 코드는 활성 상태로 유지할 수 있습니다."),
}


FBNEO_UNAVAILABLE_LABELS = {
    "en": ("This native option cannot be safely disabled, so activation is unavailable.", "This option is outside the verified catalogue installation. Import its complete program from the catalogue to use it safely."),
    "fr": ("Cette option native ne peut pas être désactivée de façon fiable. Son activation est indisponible.", "Cette option ne fait pas partie de l’installation vérifiée du catalogue. Importez son programme complet depuis le catalogue pour l’utiliser en toute sécurité."),
    "es": ("Esta opción nativa no se puede desactivar de forma fiable. Su activación no está disponible.", "Esta opción no pertenece a la instalación verificada del catálogo. Importa su programa completo desde el catálogo para usarla de forma segura."),
    "de": ("Diese native Option lässt sich nicht zuverlässig deaktivieren. Ihre Aktivierung ist nicht verfügbar.", "Diese Option gehört nicht zur geprüften Kataloginstallation. Importiere ihr vollständiges Programm aus dem Katalog, um sie sicher zu verwenden."),
    "it": ("Questa opzione nativa non può essere disattivata in modo affidabile. L’attivazione non è disponibile.", "Questa opzione non fa parte dell’installazione verificata del catalogo. Importa il programma completo dal catalogo per usarla in sicurezza."),
    "pt": ("Esta opção nativa não pode ser desativada de forma fiável. A ativação está indisponível.", "Esta opção não pertence à instalação verificada do catálogo. Importe o programa completo do catálogo para usá-la com segurança."),
    "ru": ("Эту встроенную опцию нельзя надёжно выключить, поэтому её включение недоступно.", "Эта опция не входит в проверенную установку каталога. Для безопасного использования импортируйте её полную программу из каталога."),
    "id": ("Opsi bawaan ini tidak dapat dinonaktifkan dengan andal, sehingga aktivasi tidak tersedia.", "Opsi ini berada di luar pemasangan katalog terverifikasi. Impor program lengkapnya dari katalog agar dapat digunakan dengan aman."),
    "zh": ("此原生选项无法可靠禁用，因此不可启用。", "此选项不属于已验证的目录安装。请从目录导入其完整程序以安全使用。"),
    "zh_Hant": ("此原生選項無法可靠停用，因此不可啟用。", "此選項不屬於已驗證的目錄安裝。請從目錄匯入其完整程式以安全使用。"),
    "ja": ("このネイティブ設定は確実に無効化できないため、有効にできません。", "この設定は検証済みカタログのインストールに含まれていません。安全に使用するには、カタログから完全なプログラムをインポートしてください。"),
    "ko": ("이 네이티브 옵션은 확실하게 비활성화할 수 없어 활성화할 수 없습니다.", "이 옵션은 검증된 카탈로그 설치에 포함되지 않습니다. 안전하게 사용하려면 카탈로그에서 전체 프로그램을 가져오세요."),
}


DIRECT_LABELS = {
 "en": ("Import cheats", "Patches"), "fr": ("Importer des cheats", "Patchs"),
 "de": ("Cheats importieren", "Patches"), "es": ("Importar trucos", "Parches"),
 "it": ("Importa trucchi", "Patch"), "pt": ("Importar cheats", "Patches"),
 "ru": ("Импортировать читы", "Патчи"), "id": ("Impor cheat", "Patch"),
 "zh": ("导入金手指", "补丁"), "zh_Hant": ("匯入金手指", "修補程式"),
 "ja": ("チートをインポート", "パッチ"), "ko": ("치트 가져오기", "패치"),
}

RESUME_DOWNLOAD_LABELS = {
 "en": "Complete the catalogue", "fr": "Compléter le catalogue",
 "de": "Katalog vervollständigen", "es": "Completar el catálogo",
 "it": "Completa il catalogo", "pt": "Completar o catálogo",
 "ru": "Дополнить каталог", "id": "Lengkapi katalog",
 "zh": "补全目录", "zh_Hant": "補齊目錄",
 "ja": "カタログを補完", "ko": "카탈로그 완성",
}

FBNEO_AUTOMATIC_LABELS = {
 "en": "Download the catalogue, then reopen this game to load its cheats. New codes start off.",
 "fr": "Téléchargez le catalogue, puis rouvrez ce jeu pour charger ses cheats. Les nouveaux codes sont désactivés.",
 "de": "Lade den Katalog herunter und öffne dieses Spiel erneut, um seine Cheats zu laden. Neue Codes sind deaktiviert.",
 "es": "Descarga el catálogo y vuelve a abrir este juego para cargar sus trucos. Los códigos nuevos están desactivados.",
 "it": "Scarica il catalogo e riapri questo gioco per caricare i trucchi. I nuovi codici sono disattivati.",
 "pt": "Baixe o catálogo e abra este jogo novamente para carregar os cheats. Os novos códigos ficam desativados.",
 "ru": "Скачайте каталог и снова откройте эту игру, чтобы загрузить читы. Новые коды выключены.",
 "id": "Unduh katalog, lalu buka kembali game ini untuk memuat cheat. Kode baru dinonaktifkan.",
 "zh": "下载目录后重新打开此游戏，即可加载金手指。新代码默认关闭。",
 "zh_Hant": "下載目錄後重新開啟此遊戲，即可載入金手指。新代碼預設關閉。",
 "ja": "カタログをダウンロードしてからゲームを開き直すと、チートが読み込まれます。新しいコードは無効になっています。",
 "ko": "카탈로그를 다운로드한 다음 게임을 다시 열면 치트를 불러옵니다. 새 코드는 꺼져 있습니다.",
}

EDITION_DIAGNOSTICS = {
 "en": ("Detected edition: {serial} · {revision}", "Codes exist for version(s): {versions}. They do not match this game's detected version."),
 "fr": ("Édition détectée : {serial} · {revision}", "Des codes existent pour la ou les versions : {versions}. Ils ne correspondent pas à la version détectée de ce jeu."),
 "de": ("Erkannte Ausgabe: {serial} · {revision}", "Codes sind für folgende Versionen vorhanden: {versions}. Sie passen nicht zur erkannten Version dieses Spiels."),
 "es": ("Edición detectada: {serial} · {revision}", "Hay códigos para estas versiones: {versions}. No coinciden con la versión detectada de este juego."),
 "it": ("Edizione rilevata: {serial} · {revision}", "Sono disponibili codici per queste versioni: {versions}. Non corrispondono alla versione rilevata di questo gioco."),
 "pt": ("Edição detectada: {serial} · {revision}", "Existem códigos para estas versões: {versions}. Não correspondem à versão detectada deste jogo."),
 "ru": ("Обнаруженное издание: {serial} · {revision}", "Есть коды для версий: {versions}. Они не соответствуют обнаруженной версии этой игры."),
 "id": ("Edisi terdeteksi: {serial} · {revision}", "Kode tersedia untuk versi: {versions}. Kode tersebut tidak cocok dengan versi game yang terdeteksi."),
 "zh": ("检测到的版本：{serial} · {revision}", "以下版本有代码：{versions}。它们与此游戏检测到的版本不匹配。"),
 "zh_Hant": ("偵測到的版本：{serial} · {revision}", "以下版本有代碼：{versions}。它們與此遊戲偵測到的版本不相符。"),
 "ja": ("検出したエディション：{serial} · {revision}", "コードがあるバージョン：{versions}。このゲームで検出したバージョンとは一致しません。"),
 "ko": ("감지된 에디션: {serial} · {revision}", "다음 버전의 코드가 있습니다: {versions}. 이 게임에서 감지된 버전과 일치하지 않습니다."),
}

def resource():
    result = {}
    for locale, values in STRINGS.items():
        if len(values) != len(KEYS):
            raise ValueError(f"{locale}: {len(values)} values, expected {len(KEYS)}")
        result[locale] = dict(zip(KEYS, values))
        result[locale]["directImport"], result[locale]["directPatches"] = DIRECT_LABELS[locale]
        result[locale]["unifiedCatalogue"], result[locale]["noDependencies"] = ENTRY_LABELS[locale]
        result[locale]["dependenciesExclusive"] = EXCLUSIVE_ERRORS[locale]
        result[locale]["notes"] = NOTES_LABELS[locale]
        result[locale]["cataloguePart"] = PART_LABELS[locale]
        result[locale]["downloadSize"], result[locale]["storageSize"] = SIZE_LABELS[locale]
        result[locale]["editionMismatch"] = EDITION_MISMATCH_LABELS[locale]
        if len(FBNEO_LABELS[locale]) != len(FBNEO_KEYS):
            raise ValueError(f"{locale}: incomplete FBNeo translations")
        result[locale].update(zip(FBNEO_KEYS, FBNEO_LABELS[locale]))
        result[locale]["resumeDownload"] = RESUME_DOWNLOAD_LABELS[locale]
        result[locale]["detectedEdition"], result[locale]["otherRevisions"] = EDITION_DIAGNOSTICS[locale]
        result[locale]["fbneoSessionHelp"] = FBNEO_AUTOMATIC_LABELS[locale]
        result[locale]["exclusiveConflict"], result[locale]["mgbaIsolationConflict"] = ACTIVATION_CONFLICT_LABELS[locale]
        result[locale]["fbneoUnsafeDefault"], result[locale]["fbneoUnmanagedOption"] = FBNEO_UNAVAILABLE_LABELS[locale]
    return result


if __name__ == "__main__":
    target = ROOT / "packages/neo_cheat_catalog/ios/Resources/labels.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(resource(), ensure_ascii=False, indent=2) + "\n")
