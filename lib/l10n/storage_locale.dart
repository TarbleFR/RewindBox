import 'package:flutter/widgets.dart';

/// Texts of Settings › Tools › "Storage analysis and cleanup" (chantier 5,
/// `docs/storage-audit-cleanup.md` § 3.11 and § 7) in NeoStation's twelve
/// languages.
///
/// Sizes arrive already formatted (`Rpcs3SaveExchangeService.formatBytes`)
/// and dates already localized. Paths, refusal codes, errno and SQLite texts
/// and other raw diagnostics are inserted through placeholders or shown apart
/// through [technicalCode], never translated. Product names (NeoStation,
/// RPCS3, Dolphin, KartPad, Dusklight, ARMSX2, NeoSwap, RetroArch, libretro)
/// are not catalog entries. No text names the Library sources folder: it is
/// counted under [rootLibrary].
abstract final class StorageLocale {
  // Settings › Tools row.
  static const toolTitle = 'toolTitle';
  static const toolSubtitle = 'toolSubtitle';

  // Screen and analysis state.
  static const title = 'title';
  static const scanning = 'scanning';
  static const scanAgain = 'scanAgain';
  static const scanFailed = 'scanFailed';
  static const lastScan = 'lastScan';
  static const cancel = 'cancel';

  // Summary.
  static const summary = 'summary';
  static const totalLogical = 'totalLogical';
  static const totalAllocated = 'totalAllocated';
  static const allocatedUnavailable = 'allocatedUnavailable';
  static const freeSpace = 'freeSpace';
  static const freeSpaceUnavailable = 'freeSpaceUnavailable';
  static const gapExplanation = 'gapExplanation';

  // By category (one key per StorageCategory).
  static const byCategory = 'byCategory';
  static const catGames = 'catGames';
  static const catSaves = 'catSaves';
  static const catSystem = 'catSystem';
  static const catCaches = 'catCaches';
  static const catMedia = 'catMedia';
  static const catTemporary = 'catTemporary';
  static const catLogs = 'catLogs';
  static const catUserContent = 'catUserContent';
  static const catNeoSwap = 'catNeoSwap';
  static const catIndex = 'catIndex';
  static const catUnknown = 'catUnknown';

  // By folder: the Library root, the four containers and node counters.
  static const byRoot = 'byRoot';
  static const rootLibrary = 'rootLibrary';
  static const rootDocuments = 'rootDocuments';
  static const rootSupport = 'rootSupport';
  static const rootCaches = 'rootCaches';
  static const rootTemporary = 'rootTemporary';
  static const entries = 'entries';
  static const links = 'links';
  static const inaccessible = 'inaccessible';
  static const icloudPlaceholders = 'icloudPlaceholders';
  static const detailsShow = 'detailsShow';
  static const detailsHide = 'detailsHide';

  // Orphans and duplicates.
  static const orphans = 'orphans';
  static const orphanMedia = 'orphanMedia';
  static const orphanMetadata = 'orphanMetadata';
  static const orphanCovers = 'orphanCovers';
  static const orphanSavesInfo = 'orphanSavesInfo';
  static const duplicates = 'duplicates';
  static const computeHashes = 'computeHashes';
  static const hashing = 'hashing';
  static const duplicateReferenced = 'duplicateReferenced';

  // Cleanup levels, preview and confirmation.
  static const cleanup = 'cleanup';
  static const levelSafe = 'levelSafe';
  static const levelSafeHelp = 'levelSafeHelp';
  static const levelRegenerable = 'levelRegenerable';
  static const levelRegenerableHelp = 'levelRegenerableHelp';
  static const levelConfirmed = 'levelConfirmed';
  static const levelConfirmedHelp = 'levelConfirmedHelp';
  static const levelPreselectedNote = 'levelPreselectedNote';
  static const levelNeverPreselectedNote = 'levelNeverPreselectedNote';
  static const preview = 'preview';
  static const nothingToClean = 'nothingToClean';
  static const selectedTotal = 'selectedTotal';
  static const deleteAction = 'deleteAction';
  static const confirmTitle = 'confirmTitle';
  static const confirmBody = 'confirmBody';

  // Warnings shown on candidates and repeated in the confirmation.
  static const warningTitle = 'warningTitle';
  static const rpcs3CacheWarning = 'rpcs3CacheWarning';
  static const mediaQuotaWarning = 'mediaQuotaWarning';
  static const diagnosticsWarning = 'diagnosticsWarning';
  static const hdd1Warning = 'hdd1Warning';
  static const kartpadGameDataWarning = 'kartpadGameDataWarning';
  static const duplicateWarning = 'duplicateWarning';
  static const metadataBackupNote = 'metadataBackupNote';

  // Execution and result.
  static const sessionActive = 'sessionActive';
  static const rpcs3Busy = 'rpcs3Busy';
  static const deleting = 'deleting';
  static const cancelled = 'cancelled';
  static const resultTitle = 'resultTitle';
  static const resultDeleted = 'resultDeleted';
  static const resultSkippedChanged = 'resultSkippedChanged';
  static const resultMissing = 'resultMissing';
  static const resultRefused = 'resultRefused';
  static const resultMetadata = 'resultMetadata';
  static const journalSaved = 'journalSaved';

  // Refusal reasons (one key per StorageRefusalReason).
  static const refuseLink = 'refuseLink';
  static const refuseProtected = 'refuseProtected';
  static const refuseOutside = 'refuseOutside';
  static const refuseAccess = 'refuseAccess';
  static const refuseNotEmpty = 'refuseNotEmpty';
  static const refuseChanged = 'refuseChanged';
  static const refuseNotInPlan = 'refuseNotInPlan';
  static const refuseRoot = 'refuseRoot';
  static const refuseCacheApi = 'refuseCacheApi';
  static const refuseRedirected = 'refuseRedirected';
  static const refuseUnknown = 'refuseUnknown';

  // Export.
  static const export = 'export';
  static const exportDetailed = 'exportDetailed';
  static const exportDetailedHelp = 'exportDetailedHelp';
  static const share = 'share';
  static const shareFailed = 'shareFailed';

  // Limits announced on the screen (§ 7).
  static const limitsTitle = 'limitsTitle';
  static const limitFfi = 'limitFfi';
  static const limitFreeSpace = 'limitFreeSpace';
  static const limitNeoSwap = 'limitNeoSwap';
  static const limitExtensions = 'limitExtensions';
  static const limitLinkedFolders = 'limitLinkedFolders';
  static const limitRpcs3Cache = 'limitRpcs3Cache';
  static const limitDolphinStates = 'limitDolphinStates';
  static const limitScannerOrphans = 'limitScannerOrphans';
  static const limitNoAutoPurge = 'limitNoAutoPurge';
  static const limitUnverified = 'limitUnverified';

  // Raw diagnostics, shown apart from the translated explanation.
  static const technicalCode = 'technicalCode';

  static const Map<String, Map<String, String>> values = {
    'en': {
      toolTitle: 'Storage analysis and cleanup',
      toolSubtitle:
          'Measures the space used by NeoStation and its engines, then offers a cleanup with a preview.',
      title: 'Storage',
      scanning: 'Analyzing…',
      scanAgain: 'Analyze again',
      scanFailed: 'The analysis failed: {error}',
      lastScan: 'Last analysis: {date}',
      cancel: 'Cancel',
      summary: 'Summary',
      totalLogical: 'Total file size: {size}',
      totalAllocated: 'Space used on the device: {size}',
      allocatedUnavailable: 'Allocated size unavailable',
      freeSpace: 'Free space: {free} of {total}',
      freeSpaceUnavailable: 'Free space unavailable',
      gapExplanation:
          'The difference with iOS Settings comes from APFS blocks, the temporary folder purged by iOS, unlinked NeoSwap memory and iCloud files that are not downloaded.',
      byCategory: 'By category',
      catGames: 'Games and ROMs',
      catSaves: 'Saves and states',
      catSystem: 'BIOS, firmware, licenses and system files',
      catCaches: 'Rebuildable caches',
      catMedia: 'Scraped media and metadata',
      catTemporary: 'Temporary files',
      catLogs: 'Logs and diagnostics',
      catUserContent: 'User content (other than games)',
      catNeoSwap: 'NeoSwap data',
      catIndex: 'Database, indexes and settings',
      catUnknown: 'Other data (unidentified)',
      byRoot: 'By folder',
      rootLibrary: 'Library',
      rootDocuments: 'NeoStation folder in Files',
      rootSupport: 'Internal app data',
      rootCaches: 'App caches',
      rootTemporary: 'App temporary folder',
      entries: 'Items: {count}',
      links: 'Symbolic links (not followed): {count}',
      inaccessible: 'Inaccessible items: {count}',
      icloudPlaceholders: 'iCloud files not downloaded: {count}',
      detailsShow: 'Show details',
      detailsHide: 'Hide details',
      orphans: 'Orphans and duplicates',
      orphanMedia: 'Media without a matching game: {count} ({size})',
      orphanMetadata: 'Metadata without a matching game: {count}',
      orphanCovers: 'Covers without a matching book: {count}',
      orphanSavesInfo:
          'Saves and states without a matching game: {count} (never deleted)',
      duplicates: 'Possible duplicates (same name and size): {count} ({size})',
      computeHashes: 'Compute checksums',
      hashing: 'Computing checksums…',
      duplicateReferenced: 'Referenced by the library',
      cleanup: 'Cleanup',
      levelSafe: 'Safe',
      levelSafeHelp:
          'Temporary copies left by imports, interrupted downloads and extraction leftovers. No game data, no database entry.',
      levelRegenerable: 'Rebuildable',
      levelRegenerableHelp:
          'Safe level, plus caches, orphans (media, metadata, covers) and old logs. Everything can be recreated, sometimes at the cost of a recompilation or a new scrape.',
      levelConfirmed: 'With detailed confirmation',
      levelConfirmedHelp:
          'Rebuildable level, plus diagnostics, video recordings, exports, backup copies and duplicates, to be ticked one by one.',
      levelPreselectedNote: 'Items at this level are preselected.',
      levelNeverPreselectedNote:
          'Nothing is preselected: tick each item to delete.',
      preview: 'Cleanup preview',
      nothingToClean: 'Nothing to clean at this level.',
      selectedTotal: 'Selected: {count} ({size})',
      deleteAction: 'Delete',
      confirmTitle: 'Delete the selected items?',
      confirmBody: 'Items to delete: {count} ({size}). Deletion is permanent.',
      warningTitle: 'Warning',
      rpcs3CacheWarning:
          'RPCS3 will recompile its LLVM caches at the next launch (longer start).',
      mediaQuotaWarning:
          'Removed media will have to be scraped again (ScreenScraper quota).',
      diagnosticsWarning:
          'Deleted diagnostics can no longer help investigate a problem.',
      hdd1Warning:
          'PS3 cache disk: games recreate it, but some reinstall data at their next launch (longer start).',
      kartpadGameDataWarning:
          'KartPad will extract the game data again at the next launch (longer start).',
      duplicateWarning:
          'Only the copy the library does not use can be deleted. Check both paths before confirming.',
      metadataBackupNote:
          'A copy of the database is saved before any metadata is removed.',
      sessionActive: 'Cleanup refused: a game or an import is in progress.',
      rpcs3Busy:
          'RPCS3 cleanup refused: a PS3 game or another RPCS3 operation is in progress.',
      deleting: 'Deleting… {done} of {total}',
      cancelled: 'Cleanup stopped: files already deleted stay deleted.',
      resultTitle: 'Cleanup result',
      resultDeleted: 'Deleted: {count} ({size})',
      resultSkippedChanged: 'Skipped (changed since the preview): {count}',
      resultMissing: 'Already gone: {count}',
      resultRefused: 'Refused: {count}',
      resultMetadata: 'Metadata removed from the database: {count}',
      journalSaved: 'Log saved: {path}',
      refuseLink: 'Symbolic link: never followed or deleted.',
      refuseProtected: 'Protected item: never deleted.',
      refuseOutside: 'Outside the folders analyzed by NeoStation.',
      refuseAccess: 'Access denied by the system.',
      refuseNotEmpty: 'Folder not empty: it still contains other files.',
      refuseChanged: 'Changed since the preview: left untouched.',
      refuseNotInPlan: 'Not part of the preview.',
      refuseRoot: 'Main folder: only its contents can be cleaned.',
      refuseCacheApi: 'The Library cache could not be cleared.',
      refuseRedirected:
          'RPCS3 storage is redirected elsewhere: NeoStation leaves it untouched.',
      refuseUnknown: 'Refused for an unexpected reason.',
      export: 'Export report',
      exportDetailed: 'Detailed mode (relative paths)',
      exportDetailedHelp: 'By default, the export contains only totals.',
      share: 'Share…',
      shareFailed: 'The report could not be shared.',
      limitsTitle: 'Analysis limits',
      limitFfi:
          'Allocated sizes and free space are not available on this device: logical sizes shown.',
      limitFreeSpace:
          'Free space does not include the purgeable space that iOS Settings counts as available.',
      limitNeoSwap:
          'Unlinked NeoSwap memory cannot be measured: its files stay open while a game runs but appear in no folder.',
      limitExtensions:
          'NeoStation cannot read the containers of its app extensions, so they are not measured.',
      limitLinkedFolders:
          'Folders linked from outside NeoStation are neither analyzed nor cleaned.',
      limitRpcs3Cache:
          'The RPCS3 cache is shown as a single block: its breakdown by game is unknown.',
      limitDolphinStates: 'Dolphin save states are not matched to their game.',
      limitScannerOrphans:
          'Orphans are found after the fact: the analysis does not prevent them from appearing.',
      limitNoAutoPurge:
          'Nothing is ever cleaned automatically, neither at startup nor in the background.',
      limitUnverified: 'Figures not verified on iPhone.',
      technicalCode: 'Technical code: {code}',
    },
    'es': {
      toolTitle: 'Análisis y limpieza del almacenamiento',
      toolSubtitle:
          'Mide el espacio que usan NeoStation y sus motores, y luego propone una limpieza con vista previa.',
      title: 'Almacenamiento',
      scanning: 'Analizando…',
      scanAgain: 'Analizar de nuevo',
      scanFailed: 'El análisis falló: {error}',
      lastScan: 'Último análisis: {date}',
      cancel: 'Cancelar',
      summary: 'Resumen',
      totalLogical: 'Tamaño total de los archivos: {size}',
      totalAllocated: 'Espacio ocupado en el dispositivo: {size}',
      allocatedUnavailable: 'Tamaño asignado no disponible',
      freeSpace: 'Espacio libre: {free} de {total}',
      freeSpaceUnavailable: 'Espacio libre no disponible',
      gapExplanation:
          'La diferencia con los Ajustes de iOS se debe a los bloques APFS, a la carpeta temporal que vacía iOS, a la memoria NeoSwap desvinculada y a los archivos de iCloud no descargados.',
      byCategory: 'Por categoría',
      catGames: 'Juegos y ROM',
      catSaves: 'Partidas y estados guardados',
      catSystem: 'BIOS, firmware, licencias y archivos del sistema',
      catCaches: 'Cachés regenerables',
      catMedia: 'Medios y metadatos del scraping',
      catTemporary: 'Archivos temporales',
      catLogs: 'Registros y diagnósticos',
      catUserContent: 'Contenido del usuario (sin juegos)',
      catNeoSwap: 'Datos de NeoSwap',
      catIndex: 'Base de datos, índices y ajustes',
      catUnknown: 'Otros datos (sin identificar)',
      byRoot: 'Por carpeta',
      rootLibrary: 'Biblioteca',
      rootDocuments: 'Carpeta de NeoStation en Archivos',
      rootSupport: 'Datos internos de la app',
      rootCaches: 'Cachés de la app',
      rootTemporary: 'Carpeta temporal de la app',
      entries: 'Elementos: {count}',
      links: 'Enlaces simbólicos (no se siguen): {count}',
      inaccessible: 'Elementos inaccesibles: {count}',
      icloudPlaceholders: 'Archivos de iCloud sin descargar: {count}',
      detailsShow: 'Mostrar detalles',
      detailsHide: 'Ocultar detalles',
      orphans: 'Huérfanos y duplicados',
      orphanMedia: 'Medios sin juego asociado: {count} ({size})',
      orphanMetadata: 'Metadatos sin juego asociado: {count}',
      orphanCovers: 'Portadas sin libro asociado: {count}',
      orphanSavesInfo:
          'Partidas y estados guardados sin juego asociado: {count} (nunca se eliminan)',
      duplicates:
          'Posibles duplicados (mismo nombre y tamaño): {count} ({size})',
      computeHashes: 'Calcular sumas de verificación',
      hashing: 'Calculando sumas de verificación…',
      duplicateReferenced: 'Referenciado por la biblioteca',
      cleanup: 'Limpieza',
      levelSafe: 'Seguro',
      levelSafeHelp:
          'Copias temporales que dejan las importaciones, descargas interrumpidas y restos de extracción. Ningún dato de juego ni entrada de la base de datos.',
      levelRegenerable: 'Regenerable',
      levelRegenerableHelp:
          'Nivel Seguro más cachés, huérfanos (medios, metadatos, portadas) y registros antiguos. Todo se puede volver a crear, a veces a costa de una recompilación o de un nuevo scraping.',
      levelConfirmed: 'Con confirmación detallada',
      levelConfirmedHelp:
          'Nivel Regenerable más diagnósticos, grabaciones de vídeo, exportaciones, copias de seguridad y duplicados, que se marcan uno a uno.',
      levelPreselectedNote:
          'Los elementos de este nivel están preseleccionados.',
      levelNeverPreselectedNote:
          'No hay nada preseleccionado: marca cada elemento que quieras eliminar.',
      preview: 'Vista previa de la limpieza',
      nothingToClean: 'No hay nada que limpiar en este nivel.',
      selectedTotal: 'Seleccionados: {count} ({size})',
      deleteAction: 'Eliminar',
      confirmTitle: '¿Eliminar los elementos seleccionados?',
      confirmBody:
          'Elementos que se eliminarán: {count} ({size}). La eliminación es definitiva.',
      warningTitle: 'Advertencia',
      rpcs3CacheWarning:
          'RPCS3 volverá a compilar sus cachés LLVM en el próximo inicio (arranque más lento).',
      mediaQuotaWarning:
          'Los medios eliminados tendrán que obtenerse de nuevo por scraping (cuota de ScreenScraper).',
      diagnosticsWarning:
          'Los diagnósticos eliminados ya no podrán ayudar a investigar un problema.',
      hdd1Warning:
          'Disco de caché de PS3: los juegos lo vuelven a crear, pero algunos reinstalan datos en su próximo inicio (arranque más lento).',
      kartpadGameDataWarning:
          'KartPad volverá a extraer los datos del juego en el próximo inicio (arranque más lento).',
      duplicateWarning:
          'Solo se puede eliminar la copia que la biblioteca no usa. Comprueba las dos rutas antes de confirmar.',
      metadataBackupNote:
          'Se guarda una copia de la base de datos antes de quitar metadatos.',
      sessionActive:
          'Limpieza rechazada: hay un juego o una importación en curso.',
      rpcs3Busy:
          'Limpieza de RPCS3 rechazada: hay un juego de PS3 u otra operación de RPCS3 en curso.',
      deleting: 'Eliminando… {done} de {total}',
      cancelled:
          'Limpieza interrumpida: los archivos ya eliminados no se recuperan.',
      resultTitle: 'Resultado de la limpieza',
      resultDeleted: 'Eliminados: {count} ({size})',
      resultSkippedChanged:
          'Omitidos (cambiaron desde la vista previa): {count}',
      resultMissing: 'Ya no existían: {count}',
      resultRefused: 'Rechazados: {count}',
      resultMetadata: 'Metadatos quitados de la base de datos: {count}',
      journalSaved: 'Registro guardado: {path}',
      refuseLink: 'Enlace simbólico: nunca se sigue ni se elimina.',
      refuseProtected: 'Elemento protegido: nunca se elimina.',
      refuseOutside: 'Fuera de las carpetas que analiza NeoStation.',
      refuseAccess: 'El sistema denegó el acceso.',
      refuseNotEmpty: 'Carpeta no vacía: todavía contiene otros archivos.',
      refuseChanged: 'Cambió desde la vista previa: se deja intacto.',
      refuseNotInPlan: 'No forma parte de la vista previa.',
      refuseRoot: 'Carpeta principal: solo se puede limpiar su contenido.',
      refuseCacheApi: 'No se pudo vaciar la caché de la Biblioteca.',
      refuseRedirected:
          'El almacenamiento de RPCS3 está redirigido a otro lugar: NeoStation no lo toca.',
      refuseUnknown: 'Rechazado por un motivo inesperado.',
      export: 'Exportar el informe',
      exportDetailed: 'Modo detallado (rutas relativas)',
      exportDetailedHelp:
          'De forma predeterminada, la exportación solo contiene totales.',
      share: 'Compartir…',
      shareFailed: 'No se pudo compartir el informe.',
      limitsTitle: 'Límites del análisis',
      limitFfi:
          'Los tamaños asignados y el espacio libre no están disponibles en este dispositivo: se muestran los tamaños lógicos.',
      limitFreeSpace:
          'El espacio libre no incluye el espacio purgable que los Ajustes de iOS cuentan como disponible.',
      limitNeoSwap:
          'La memoria NeoSwap desvinculada no se puede medir: sus archivos siguen abiertos durante el juego, pero no aparecen en ninguna carpeta.',
      limitExtensions:
          'NeoStation no puede leer los contenedores de las extensiones de la app, así que no se miden.',
      limitLinkedFolders:
          'Las carpetas vinculadas desde fuera de NeoStation no se analizan ni se limpian.',
      limitRpcs3Cache:
          'La caché de RPCS3 se muestra como un solo bloque: se desconoce su reparto por juego.',
      limitDolphinStates:
          'Los estados guardados de Dolphin no se asocian a su juego.',
      limitScannerOrphans:
          'Los huérfanos se detectan a posteriori: el análisis no evita que aparezcan.',
      limitNoAutoPurge:
          'Nunca se limpia nada automáticamente, ni al iniciar ni en segundo plano.',
      limitUnverified: 'Cifras no verificadas en iPhone.',
      technicalCode: 'Código técnico: {code}',
    },
    'ru': {
      toolTitle: 'Анализ и очистка хранилища',
      toolSubtitle:
          'Измеряет место, занятое NeoStation и его движками, затем предлагает очистку с предварительным просмотром.',
      title: 'Хранилище',
      scanning: 'Идёт анализ…',
      scanAgain: 'Повторить анализ',
      scanFailed: 'Анализ не удался: {error}',
      lastScan: 'Последний анализ: {date}',
      cancel: 'Отмена',
      summary: 'Сводка',
      totalLogical: 'Общий размер файлов: {size}',
      totalAllocated: 'Занято на устройстве: {size}',
      allocatedUnavailable: 'Выделенный размер недоступен',
      freeSpace: 'Свободно: {free} из {total}',
      freeSpaceUnavailable: 'Свободное место недоступно',
      gapExplanation:
          'Расхождение с настройками iOS вызвано блоками APFS, временной папкой, которую очищает iOS, отвязанной памятью NeoSwap и незагруженными файлами iCloud.',
      byCategory: 'По категориям',
      catGames: 'Игры и ROM',
      catSaves: 'Сохранения и состояния',
      catSystem: 'BIOS, прошивки, лицензии и системные файлы',
      catCaches: 'Восстанавливаемые кэши',
      catMedia: 'Медиа и метаданные скрапера',
      catTemporary: 'Временные файлы',
      catLogs: 'Журналы и диагностика',
      catUserContent: 'Пользовательские данные (кроме игр)',
      catNeoSwap: 'Данные NeoSwap',
      catIndex: 'База данных, индексы и настройки',
      catUnknown: 'Прочие данные (не опознаны)',
      byRoot: 'По папкам',
      rootLibrary: 'Библиотека',
      rootDocuments: 'Папка NeoStation в «Файлах»',
      rootSupport: 'Внутренние данные приложения',
      rootCaches: 'Кэши приложения',
      rootTemporary: 'Временная папка приложения',
      entries: 'Элементов: {count}',
      links: 'Символические ссылки (без перехода): {count}',
      inaccessible: 'Недоступные элементы: {count}',
      icloudPlaceholders: 'Незагруженные файлы iCloud: {count}',
      detailsShow: 'Показать подробности',
      detailsHide: 'Скрыть подробности',
      orphans: 'Потерянные данные и дубликаты',
      orphanMedia: 'Медиа без связанной игры: {count} ({size})',
      orphanMetadata: 'Записи метаданных без связанной игры: {count}',
      orphanCovers: 'Обложки без связанной книги: {count}',
      orphanSavesInfo:
          'Сохранения и состояния без связанной игры: {count} (никогда не удаляются)',
      duplicates: 'Возможные дубликаты (те же имя и размер): {count} ({size})',
      computeHashes: 'Вычислить контрольные суммы',
      hashing: 'Вычисление контрольных сумм…',
      duplicateReferenced: 'Используется библиотекой',
      cleanup: 'Очистка',
      levelSafe: 'Безопасный',
      levelSafeHelp:
          'Временные копии после импорта, прерванные загрузки и остатки распаковки. Без игровых данных и записей базы данных.',
      levelRegenerable: 'Восстанавливаемый',
      levelRegenerableHelp:
          'Уровень «Безопасный», а также кэши, потерянные данные (медиа, метаданные, обложки) и старые журналы. Всё можно восстановить, иногда ценой перекомпиляции или повторного скрапинга.',
      levelConfirmed: 'С подробным подтверждением',
      levelConfirmedHelp:
          'Уровень «Восстанавливаемый», а также диагностика, видеозаписи, экспорт, резервные копии и дубликаты — каждый элемент отмечается отдельно.',
      levelPreselectedNote: 'Элементы этого уровня выбраны заранее.',
      levelNeverPreselectedNote:
          'Ничего не выбрано заранее: отметьте каждый элемент, который нужно удалить.',
      preview: 'Предпросмотр очистки',
      nothingToClean: 'На этом уровне нечего очищать.',
      selectedTotal: 'Выбрано: {count} ({size})',
      deleteAction: 'Удалить',
      confirmTitle: 'Удалить выбранные элементы?',
      confirmBody:
          'Будет удалено элементов: {count} ({size}). Удаление необратимо.',
      warningTitle: 'Предупреждение',
      rpcs3CacheWarning:
          'RPCS3 заново скомпилирует кэши LLVM при следующем запуске (запуск займёт больше времени).',
      mediaQuotaWarning:
          'Удалённые медиа придётся заново загрузить скрапером (квота ScreenScraper).',
      diagnosticsWarning:
          'Удалённую диагностику уже нельзя будет использовать для разбора проблемы.',
      hdd1Warning:
          'Кэш-диск PS3: игры создают его заново, но некоторые при следующем запуске переустанавливают данные (запуск займёт больше времени).',
      kartpadGameDataWarning:
          'KartPad снова распакует данные игры при следующем запуске (запуск займёт больше времени).',
      duplicateWarning:
          'Удалить можно только копию, которую не использует библиотека. Перед подтверждением проверьте оба пути.',
      metadataBackupNote:
          'Перед удалением метаданных сохраняется копия базы данных.',
      sessionActive: 'Очистка отклонена: идёт игра или импорт.',
      rpcs3Busy:
          'Очистка RPCS3 отклонена: идёт игра PS3 или другая операция RPCS3.',
      deleting: 'Удаление… {done} из {total}',
      cancelled: 'Очистка прервана: уже удалённые файлы не восстанавливаются.',
      resultTitle: 'Результат очистки',
      resultDeleted: 'Удалено: {count} ({size})',
      resultSkippedChanged: 'Пропущено (изменено после предпросмотра): {count}',
      resultMissing: 'Уже отсутствовало: {count}',
      resultRefused: 'Отклонено: {count}',
      resultMetadata: 'Удалено записей метаданных из базы: {count}',
      journalSaved: 'Журнал сохранён: {path}',
      refuseLink: 'Символическая ссылка: по ней не переходят и её не удаляют.',
      refuseProtected: 'Защищённый элемент: никогда не удаляется.',
      refuseOutside: 'Вне папок, которые анализирует NeoStation.',
      refuseAccess: 'Система запретила доступ.',
      refuseNotEmpty: 'Папка не пуста: в ней остались другие файлы.',
      refuseChanged: 'Изменено после предпросмотра: оставлено как есть.',
      refuseNotInPlan: 'Нет в предпросмотре.',
      refuseRoot: 'Основная папка: очистить можно только её содержимое.',
      refuseCacheApi: 'Не удалось очистить кэш Библиотеки.',
      refuseRedirected:
          'Хранилище RPCS3 перенаправлено в другое место: NeoStation его не трогает.',
      refuseUnknown: 'Отклонено по непредвиденной причине.',
      export: 'Экспорт отчёта',
      exportDetailed: 'Подробный режим (относительные пути)',
      exportDetailedHelp: 'По умолчанию экспорт содержит только итоги.',
      share: 'Поделиться…',
      shareFailed: 'Не удалось поделиться отчётом.',
      limitsTitle: 'Ограничения анализа',
      limitFfi:
          'Выделенные размеры и свободное место на этом устройстве недоступны: показаны логические размеры.',
      limitFreeSpace:
          'Свободное место не включает очищаемое пространство, которое настройки iOS считают доступным.',
      limitNeoSwap:
          'Отвязанную память NeoSwap измерить нельзя: её файлы открыты во время игры, но не видны ни в одной папке.',
      limitExtensions:
          'NeoStation не может прочитать контейнеры расширений приложения, поэтому они не измеряются.',
      limitLinkedFolders:
          'Подключённые папки за пределами NeoStation не анализируются и не очищаются.',
      limitRpcs3Cache:
          'Кэш RPCS3 показан одним блоком: его распределение по играм неизвестно.',
      limitDolphinStates: 'Состояния Dolphin не сопоставляются с играми.',
      limitScannerOrphans:
          'Потерянные данные обнаруживаются задним числом: анализ не предотвращает их появление.',
      limitNoAutoPurge:
          'Ничего не очищается автоматически — ни при запуске, ни в фоне.',
      limitUnverified: 'Цифры не проверены на iPhone.',
      technicalCode: 'Технический код: {code}',
    },
    'zh': {
      toolTitle: '存储空间分析与清理',
      toolSubtitle: '测量 NeoStation 及其引擎占用的空间，然后提供可预览的清理方案。',
      title: '存储空间',
      scanning: '正在分析…',
      scanAgain: '重新分析',
      scanFailed: '分析失败：{error}',
      lastScan: '上次分析：{date}',
      cancel: '取消',
      summary: '概览',
      totalLogical: '文件总大小：{size}',
      totalAllocated: '设备上实际占用：{size}',
      allocatedUnavailable: '无法获取分配大小',
      freeSpace: '剩余空间：{free}（共 {total}）',
      freeSpaceUnavailable: '无法获取剩余空间',
      gapExplanation:
          '与 iOS 设置的差异来自 APFS 块、iOS 会清除的临时文件夹、已解除链接的 NeoSwap 内存，以及未下载的 iCloud 文件。',
      byCategory: '按类别',
      catGames: '游戏与 ROM',
      catSaves: '存档与即时存档',
      catSystem: 'BIOS、固件、许可证与系统文件',
      catCaches: '可重新生成的缓存',
      catMedia: '刮削的媒体与元数据',
      catTemporary: '临时文件',
      catLogs: '日志与诊断',
      catUserContent: '用户内容（游戏除外）',
      catNeoSwap: 'NeoSwap 数据',
      catIndex: '数据库、索引与设置',
      catUnknown: '其他数据（未识别）',
      byRoot: '按文件夹',
      rootLibrary: '资料库',
      rootDocuments: '“文件”App 中的 NeoStation 文件夹',
      rootSupport: 'App 内部数据',
      rootCaches: 'App 缓存',
      rootTemporary: 'App 临时文件夹',
      entries: '项目数：{count}',
      links: '符号链接（不跟随）：{count}',
      inaccessible: '无法访问的项目：{count}',
      icloudPlaceholders: '未下载的 iCloud 文件：{count}',
      detailsShow: '显示详情',
      detailsHide: '隐藏详情',
      orphans: '孤立项与重复项',
      orphanMedia: '无对应游戏的媒体：{count}（{size}）',
      orphanMetadata: '无对应游戏的元数据：{count}',
      orphanCovers: '无对应书籍的封面：{count}',
      orphanSavesInfo: '无对应游戏的存档与即时存档：{count}（绝不删除）',
      duplicates: '可能的重复项（名称和大小相同）：{count}（{size}）',
      computeHashes: '计算校验和',
      hashing: '正在计算校验和…',
      duplicateReferenced: '被游戏库引用',
      cleanup: '清理',
      levelSafe: '安全',
      levelSafeHelp: '导入留下的临时副本、中断的下载和解压残留。不含任何游戏数据或数据库条目。',
      levelRegenerable: '可重新生成',
      levelRegenerableHelp:
          '包括“安全”级别，以及缓存、孤立项（媒体、元数据、封面）和旧日志。均可重新生成，但有时需要重新编译或重新刮削。',
      levelConfirmed: '需逐项确认',
      levelConfirmedHelp: '包括“可重新生成”级别，以及诊断、视频录制、导出文件、备份副本和重复项，需逐项勾选。',
      levelPreselectedNote: '此级别的项目已预先选中。',
      levelNeverPreselectedNote: '未预先选中任何项目：请逐一勾选要删除的项目。',
      preview: '清理预览',
      nothingToClean: '此级别没有可清理的内容。',
      selectedTotal: '已选择：{count}（{size}）',
      deleteAction: '删除',
      confirmTitle: '删除所选项目？',
      confirmBody: '将删除的项目：{count}（{size}）。删除后无法恢复。',
      warningTitle: '警告',
      rpcs3CacheWarning: 'RPCS3 将在下次启动时重新编译其 LLVM 缓存（启动时间更长）。',
      mediaQuotaWarning: '移除的媒体需要重新刮削（消耗 ScreenScraper 配额）。',
      diagnosticsWarning: '删除的诊断信息将无法再用于排查问题。',
      hdd1Warning: 'PS3 缓存磁盘：游戏会重新创建它，但部分游戏会在下次启动时重新安装数据（启动时间更长）。',
      kartpadGameDataWarning: 'KartPad 将在下次启动时重新解压游戏数据（启动时间更长）。',
      duplicateWarning: '只能删除游戏库未使用的副本。确认前请核对两个路径。',
      metadataBackupNote: '移除元数据前会先保存一份数据库副本。',
      sessionActive: '已拒绝清理：有游戏或导入正在进行。',
      rpcs3Busy: '已拒绝清理 RPCS3：有 PS3 游戏或其他 RPCS3 操作正在进行。',
      deleting: '正在删除… {done}/{total}',
      cancelled: '清理已中断：已删除的文件不会恢复。',
      resultTitle: '清理结果',
      resultDeleted: '已删除：{count}（{size}）',
      resultSkippedChanged: '已跳过（预览后有变动）：{count}',
      resultMissing: '已不存在：{count}',
      resultRefused: '已拒绝：{count}',
      resultMetadata: '已从数据库移除的元数据：{count}',
      journalSaved: '日志已保存：{path}',
      refuseLink: '符号链接：从不跟随，也不删除。',
      refuseProtected: '受保护的项目：绝不删除。',
      refuseOutside: '不在 NeoStation 分析的文件夹内。',
      refuseAccess: '系统拒绝访问。',
      refuseNotEmpty: '文件夹不为空：其中仍有其他文件。',
      refuseChanged: '预览后已变动：保持原样。',
      refuseNotInPlan: '不在预览范围内。',
      refuseRoot: '主文件夹：只能清理其中的内容。',
      refuseCacheApi: '无法清空资料库缓存。',
      refuseRedirected: 'RPCS3 存储已重定向到其他位置：NeoStation 不会改动。',
      refuseUnknown: '因意外原因被拒绝。',
      export: '导出报告',
      exportDetailed: '详细模式（相对路径）',
      exportDetailedHelp: '默认情况下，导出内容只包含总计。',
      share: '共享…',
      shareFailed: '无法共享报告。',
      limitsTitle: '分析的局限',
      limitFfi: '此设备无法获取分配大小和剩余空间：显示的是逻辑大小。',
      limitFreeSpace: '剩余空间不包括 iOS 设置中计为“可用”的可清除空间。',
      limitNeoSwap: '无法测量已解除链接的 NeoSwap 内存：其文件在游戏期间保持打开，但不出现在任何文件夹中。',
      limitExtensions: 'NeoStation 无法读取其 App 扩展的容器，因此不计入测量。',
      limitLinkedFolders: '从 NeoStation 外部链接的文件夹既不分析也不清理。',
      limitRpcs3Cache: 'RPCS3 缓存显示为一个整体：无法按游戏细分。',
      limitDolphinStates: 'Dolphin 的即时存档不会对应到具体游戏。',
      limitScannerOrphans: '孤立项是事后发现的：分析无法阻止其产生。',
      limitNoAutoPurge: '不会自动清理任何内容，启动时和后台均不会。',
      limitUnverified: '数据尚未在 iPhone 上验证。',
      technicalCode: '技术代码：{code}',
    },
    'zh_Hant': {
      toolTitle: '儲存空間分析與清理',
      toolSubtitle: '測量 NeoStation 及其引擎佔用的空間，然後提供可預覽的清理方案。',
      title: '儲存空間',
      scanning: '分析中…',
      scanAgain: '重新分析',
      scanFailed: '分析失敗：{error}',
      lastScan: '上次分析時間：{date}',
      cancel: '取消',
      summary: '總覽',
      totalLogical: '檔案總大小：{size}',
      totalAllocated: '裝置上實際佔用：{size}',
      allocatedUnavailable: '無法取得配置大小',
      freeSpace: '剩餘空間：{free}（共 {total}）',
      freeSpaceUnavailable: '無法取得剩餘空間',
      gapExplanation:
          '與 iOS 設定的差異來自 APFS 區塊、iOS 會清除的暫存資料夾、已解除連結的 NeoSwap 記憶體，以及未下載的 iCloud 檔案。',
      byCategory: '依類別',
      catGames: '遊戲與 ROM',
      catSaves: '存檔與即時存檔',
      catSystem: 'BIOS、韌體、授權檔與系統檔案',
      catCaches: '可重新產生的快取',
      catMedia: '刮削的媒體與中繼資料',
      catTemporary: '暫存檔案',
      catLogs: '記錄檔與診斷',
      catUserContent: '使用者內容（遊戲除外）',
      catNeoSwap: 'NeoSwap 資料',
      catIndex: '資料庫、索引與設定',
      catUnknown: '其他資料（未識別）',
      byRoot: '依資料夾',
      rootLibrary: '資料庫',
      rootDocuments: '「檔案」App 中的 NeoStation 資料夾',
      rootSupport: 'App 內部資料',
      rootCaches: 'App 快取',
      rootTemporary: 'App 暫存資料夾',
      entries: '項目數：{count}',
      links: '符號連結（不追蹤）：{count}',
      inaccessible: '無法存取的項目：{count}',
      icloudPlaceholders: '未下載的 iCloud 檔案：{count}',
      detailsShow: '顯示詳細資訊',
      detailsHide: '隱藏詳細資訊',
      orphans: '孤立項目與重複項目',
      orphanMedia: '無對應遊戲的媒體：{count}（{size}）',
      orphanMetadata: '無對應遊戲的中繼資料：{count}',
      orphanCovers: '無對應書籍的封面：{count}',
      orphanSavesInfo: '無對應遊戲的存檔與即時存檔：{count}（絕不刪除）',
      duplicates: '可能的重複項目（名稱與大小相同）：{count}（{size}）',
      computeHashes: '計算校驗和',
      hashing: '正在計算校驗和…',
      duplicateReferenced: '遊戲庫參照中',
      cleanup: '清理',
      levelSafe: '安全',
      levelSafeHelp: '匯入後留下的暫存副本、中斷的下載與解壓縮殘留檔案。不含任何遊戲資料或資料庫項目。',
      levelRegenerable: '可重新產生',
      levelRegenerableHelp:
          '包含「安全」層級，以及快取、孤立項目（媒體、中繼資料、封面）和舊記錄檔。皆可重新產生，但有時需要重新編譯或重新刮削。',
      levelConfirmed: '需逐項確認',
      levelConfirmedHelp: '包含「可重新產生」層級，以及診斷、影片錄製、匯出檔案、備份副本和重複項目，需逐項勾選。',
      levelPreselectedNote: '此層級的項目已預先選取。',
      levelNeverPreselectedNote: '未預先選取任何項目：請逐一勾選要刪除的項目。',
      preview: '清理預覽',
      nothingToClean: '此層級沒有可清理的內容。',
      selectedTotal: '已選取：{count}（{size}）',
      deleteAction: '刪除',
      confirmTitle: '要刪除所選項目嗎？',
      confirmBody: '將刪除的項目：{count}（{size}）。刪除後無法復原。',
      warningTitle: '警告',
      rpcs3CacheWarning: 'RPCS3 將在下次啟動時重新編譯其 LLVM 快取（啟動時間較長）。',
      mediaQuotaWarning: '移除的媒體需要重新刮削（會用掉 ScreenScraper 配額）。',
      diagnosticsWarning: '刪除的診斷資訊將無法再用於排查問題。',
      hdd1Warning: 'PS3 快取磁碟：遊戲會重新建立它，但部分遊戲會在下次啟動時重新安裝資料（啟動時間較長）。',
      kartpadGameDataWarning: 'KartPad 將在下次啟動時重新解壓縮遊戲資料（啟動時間較長）。',
      duplicateWarning: '只能刪除遊戲庫未使用的副本。確認前請核對兩個路徑。',
      metadataBackupNote: '移除中繼資料前會先儲存一份資料庫副本。',
      sessionActive: '已拒絕清理：有遊戲或匯入正在進行。',
      rpcs3Busy: '已拒絕清理 RPCS3：有 PS3 遊戲或其他 RPCS3 操作正在進行。',
      deleting: '刪除中… {done}/{total}',
      cancelled: '清理已中斷：已刪除的檔案不會復原。',
      resultTitle: '清理結果',
      resultDeleted: '已刪除：{count}（{size}）',
      resultSkippedChanged: '已略過（預覽後有變動）：{count}',
      resultMissing: '已不存在：{count}',
      resultRefused: '已拒絕：{count}',
      resultMetadata: '已從資料庫移除的中繼資料：{count}',
      journalSaved: '記錄檔已儲存：{path}',
      refuseLink: '符號連結：從不追蹤，也不刪除。',
      refuseProtected: '受保護的項目：絕不刪除。',
      refuseOutside: '不在 NeoStation 分析的資料夾內。',
      refuseAccess: '系統拒絕存取。',
      refuseNotEmpty: '資料夾不是空的：其中仍有其他檔案。',
      refuseChanged: '預覽後已變動：維持原狀。',
      refuseNotInPlan: '不在預覽範圍內。',
      refuseRoot: '主資料夾：只能清理其中的內容。',
      refuseCacheApi: '無法清除資料庫快取。',
      refuseRedirected: 'RPCS3 儲存空間已重新導向至其他位置：NeoStation 不會更動。',
      refuseUnknown: '因非預期的原因遭拒。',
      export: '匯出報告',
      exportDetailed: '詳細模式（相對路徑）',
      exportDetailedHelp: '預設情況下，匯出內容只包含總計。',
      share: '分享…',
      shareFailed: '無法分享報告。',
      limitsTitle: '分析的限制',
      limitFfi: '此裝置無法取得配置大小與剩餘空間：顯示的是邏輯大小。',
      limitFreeSpace: '剩餘空間不包含 iOS 設定中算作「可用」的可清除空間。',
      limitNeoSwap: '無法測量已解除連結的 NeoSwap 記憶體：其檔案在遊戲期間保持開啟，但不會出現在任何資料夾中。',
      limitExtensions: 'NeoStation 無法讀取其 App 延伸功能的容器，因此不列入測量。',
      limitLinkedFolders: '從 NeoStation 外部連結的資料夾既不分析也不清理。',
      limitRpcs3Cache: 'RPCS3 快取顯示為一個整體：無法依遊戲細分。',
      limitDolphinStates: 'Dolphin 的即時存檔不會對應到具體遊戲。',
      limitScannerOrphans: '孤立項目是事後才發現的：分析無法防止其產生。',
      limitNoAutoPurge: '不會自動清理任何內容，啟動時與背景中皆不會。',
      limitUnverified: '數值尚未在 iPhone 上驗證。',
      technicalCode: '技術代碼：{code}',
    },
    'pt': {
      toolTitle: 'Análise e limpeza do armazenamento',
      toolSubtitle:
          'Mede o espaço usado pelo NeoStation e por seus motores e, depois, propõe uma limpeza com pré-visualização.',
      title: 'Armazenamento',
      scanning: 'Analisando…',
      scanAgain: 'Analisar novamente',
      scanFailed: 'A análise falhou: {error}',
      lastScan: 'Última análise: {date}',
      cancel: 'Cancelar',
      summary: 'Resumo',
      totalLogical: 'Tamanho total dos arquivos: {size}',
      totalAllocated: 'Espaço ocupado no dispositivo: {size}',
      allocatedUnavailable: 'Tamanho alocado indisponível',
      freeSpace: 'Espaço livre: {free} de {total}',
      freeSpaceUnavailable: 'Espaço livre indisponível',
      gapExplanation:
          'A diferença em relação aos Ajustes do iOS vem dos blocos APFS, da pasta temporária que o iOS limpa, da memória NeoSwap desvinculada e dos arquivos do iCloud não baixados.',
      byCategory: 'Por categoria',
      catGames: 'Jogos e ROMs',
      catSaves: 'Dados salvos e estados salvos',
      catSystem: 'BIOS, firmware, licenças e arquivos de sistema',
      catCaches: 'Caches regeneráveis',
      catMedia: 'Mídia e metadados do scraping',
      catTemporary: 'Arquivos temporários',
      catLogs: 'Registros e diagnósticos',
      catUserContent: 'Conteúdo do usuário (exceto jogos)',
      catNeoSwap: 'Dados do NeoSwap',
      catIndex: 'Banco de dados, índices e configurações',
      catUnknown: 'Outros dados (não identificados)',
      byRoot: 'Por pasta',
      rootLibrary: 'Biblioteca',
      rootDocuments: 'Pasta do NeoStation no app Arquivos',
      rootSupport: 'Dados internos do app',
      rootCaches: 'Caches do app',
      rootTemporary: 'Pasta temporária do app',
      entries: 'Itens: {count}',
      links: 'Links simbólicos (não seguidos): {count}',
      inaccessible: 'Itens inacessíveis: {count}',
      icloudPlaceholders: 'Arquivos do iCloud não baixados: {count}',
      detailsShow: 'Mostrar detalhes',
      detailsHide: 'Ocultar detalhes',
      orphans: 'Órfãos e duplicatas',
      orphanMedia: 'Mídia sem jogo associado: {count} ({size})',
      orphanMetadata: 'Metadados sem jogo associado: {count}',
      orphanCovers: 'Capas sem livro associado: {count}',
      orphanSavesInfo:
          'Dados salvos e estados salvos sem jogo associado: {count} (nunca excluídos)',
      duplicates:
          'Possíveis duplicatas (mesmo nome e tamanho): {count} ({size})',
      computeHashes: 'Calcular somas de verificação',
      hashing: 'Calculando somas de verificação…',
      duplicateReferenced: 'Referenciado pela biblioteca',
      cleanup: 'Limpeza',
      levelSafe: 'Seguro',
      levelSafeHelp:
          'Cópias temporárias deixadas por importações, downloads interrompidos e restos de extração. Nenhum dado de jogo nem entrada do banco de dados.',
      levelRegenerable: 'Regenerável',
      levelRegenerableHelp:
          'Nível Seguro, mais caches, órfãos (mídia, metadados, capas) e registros antigos. Tudo pode ser recriado, às vezes ao custo de uma recompilação ou de um novo scraping.',
      levelConfirmed: 'Com confirmação detalhada',
      levelConfirmedHelp:
          'Nível Regenerável, mais diagnósticos, gravações de vídeo, exportações, cópias de backup e duplicatas, a marcar um por um.',
      levelPreselectedNote: 'Os itens deste nível já vêm selecionados.',
      levelNeverPreselectedNote:
          'Nenhum item vem selecionado: marque cada item a excluir.',
      preview: 'Pré-visualização da limpeza',
      nothingToClean: 'Nada a limpar neste nível.',
      selectedTotal: 'Selecionados: {count} ({size})',
      deleteAction: 'Excluir',
      confirmTitle: 'Excluir os itens selecionados?',
      confirmBody:
          'Itens a excluir: {count} ({size}). A exclusão é definitiva.',
      warningTitle: 'Aviso',
      rpcs3CacheWarning:
          'O RPCS3 vai recompilar os caches LLVM na próxima inicialização (início mais demorado).',
      mediaQuotaWarning:
          'A mídia removida terá de passar por scraping novamente (cota do ScreenScraper).',
      diagnosticsWarning:
          'Os diagnósticos excluídos não poderão mais ajudar a investigar um problema.',
      hdd1Warning:
          'Disco de cache do PS3: os jogos o recriam, mas alguns reinstalam dados na próxima inicialização (início mais demorado).',
      kartpadGameDataWarning:
          'O KartPad vai extrair os dados do jogo novamente na próxima inicialização (início mais demorado).',
      duplicateWarning:
          'Só a cópia que a biblioteca não usa pode ser excluída. Confira os dois caminhos antes de confirmar.',
      metadataBackupNote:
          'Uma cópia do banco de dados é salva antes de remover metadados.',
      sessionActive:
          'Limpeza recusada: um jogo ou uma importação está em andamento.',
      rpcs3Busy:
          'Limpeza do RPCS3 recusada: um jogo de PS3 ou outra operação do RPCS3 está em andamento.',
      deleting: 'Excluindo… {done} de {total}',
      cancelled:
          'Limpeza interrompida: os arquivos já excluídos continuam excluídos.',
      resultTitle: 'Resultado da limpeza',
      resultDeleted: 'Excluídos: {count} ({size})',
      resultSkippedChanged:
          'Ignorados (alterados após a pré-visualização): {count}',
      resultMissing: 'Já ausentes: {count}',
      resultRefused: 'Recusados: {count}',
      resultMetadata: 'Metadados removidos do banco de dados: {count}',
      journalSaved: 'Registro salvo: {path}',
      refuseLink: 'Link simbólico: nunca é seguido nem excluído.',
      refuseProtected: 'Item protegido: nunca é excluído.',
      refuseOutside: 'Fora das pastas analisadas pelo NeoStation.',
      refuseAccess: 'Acesso negado pelo sistema.',
      refuseNotEmpty: 'Pasta não vazia: ainda contém outros arquivos.',
      refuseChanged: 'Alterado após a pré-visualização: mantido intacto.',
      refuseNotInPlan: 'Não faz parte da pré-visualização.',
      refuseRoot: 'Pasta principal: só o conteúdo dela pode ser limpo.',
      refuseCacheApi: 'Não foi possível limpar o cache da Biblioteca.',
      refuseRedirected:
          'O armazenamento do RPCS3 está redirecionado para outro local: o NeoStation não mexe nele.',
      refuseUnknown: 'Recusado por um motivo inesperado.',
      export: 'Exportar relatório',
      exportDetailed: 'Modo detalhado (caminhos relativos)',
      exportDetailedHelp: 'Por padrão, a exportação contém apenas totais.',
      share: 'Compartilhar…',
      shareFailed: 'Não foi possível compartilhar o relatório.',
      limitsTitle: 'Limites da análise',
      limitFfi:
          'Tamanhos alocados e espaço livre indisponíveis neste dispositivo: são exibidos os tamanhos lógicos.',
      limitFreeSpace:
          'O espaço livre não inclui o espaço removível que os Ajustes do iOS contam como disponível.',
      limitNeoSwap:
          'A memória NeoSwap desvinculada não pode ser medida: seus arquivos ficam abertos durante o jogo, mas não aparecem em nenhuma pasta.',
      limitExtensions:
          'O NeoStation não consegue ler os contêineres das extensões do app, por isso eles não são medidos.',
      limitLinkedFolders:
          'As pastas vinculadas de fora do NeoStation não são analisadas nem limpas.',
      limitRpcs3Cache:
          'O cache do RPCS3 aparece como um único bloco: a divisão por jogo é desconhecida.',
      limitDolphinStates:
          'Os estados salvos do Dolphin não são associados ao jogo.',
      limitScannerOrphans:
          'Os órfãos são detectados depois: a análise não impede que apareçam.',
      limitNoAutoPurge:
          'Nada é limpo automaticamente, nem ao iniciar nem em segundo plano.',
      limitUnverified: 'Números não verificados no iPhone.',
      technicalCode: 'Código técnico: {code}',
    },
    'fr': {
      toolTitle: 'Analyse et nettoyage du stockage',
      toolSubtitle:
          'Mesure l’espace utilisé par NeoStation et ses moteurs, puis propose un nettoyage prévisualisé.',
      title: 'Stockage',
      scanning: 'Analyse en cours…',
      scanAgain: 'Analyser à nouveau',
      scanFailed: 'L’analyse a échoué : {error}',
      lastScan: 'Dernière analyse : {date}',
      cancel: 'Annuler',
      summary: 'Résumé',
      totalLogical: 'Taille totale des fichiers : {size}',
      totalAllocated: 'Espace occupé sur l’appareil : {size}',
      allocatedUnavailable: 'Taille allouée indisponible',
      freeSpace: 'Espace libre : {free} sur {total}',
      freeSpaceUnavailable: 'Espace libre indisponible',
      gapExplanation:
          'L’écart avec les Réglages iOS vient des blocs APFS, du dossier temporaire purgé par iOS, de la mémoire NeoSwap délinkée et des fichiers iCloud non téléchargés.',
      byCategory: 'Par catégorie',
      catGames: 'Jeux et ROM',
      catSaves: 'Sauvegardes et états',
      catSystem: 'BIOS, firmware, licences et fichiers système',
      catCaches: 'Caches régénérables',
      catMedia: 'Médias et métadonnées scrapés',
      catTemporary: 'Fichiers temporaires',
      catLogs: 'Journaux et diagnostics',
      catUserContent: 'Contenu utilisateur (hors jeux)',
      catNeoSwap: 'Données NeoSwap',
      catIndex: 'Base de données, index et réglages',
      catUnknown: 'Autres données (non identifiées)',
      byRoot: 'Par dossier',
      rootLibrary: 'Bibliothèque',
      rootDocuments: 'Dossier NeoStation dans Fichiers',
      rootSupport: 'Données internes de l’app',
      rootCaches: 'Caches de l’app',
      rootTemporary: 'Dossier temporaire de l’app',
      entries: 'Éléments : {count}',
      links: 'Liens symboliques (non suivis) : {count}',
      inaccessible: 'Éléments inaccessibles : {count}',
      icloudPlaceholders: 'Fichiers iCloud non téléchargés : {count}',
      detailsShow: 'Afficher le détail',
      detailsHide: 'Masquer le détail',
      orphans: 'Orphelins et doublons',
      orphanMedia: 'Médias sans jeu associé : {count} ({size})',
      orphanMetadata: 'Métadonnées sans jeu associé : {count}',
      orphanCovers: 'Couvertures sans livre associé : {count}',
      orphanSavesInfo:
          'Sauvegardes et états sans jeu associé : {count} (jamais supprimés)',
      duplicates:
          'Doublons possibles (même nom, même taille) : {count} ({size})',
      computeHashes: 'Calculer les empreintes',
      hashing: 'Calcul des empreintes…',
      duplicateReferenced: 'Référencé par la bibliothèque',
      cleanup: 'Nettoyage',
      levelSafe: 'Sûr',
      levelSafeHelp:
          'Copies temporaires laissées par les imports, téléchargements interrompus et restes d’extraction. Aucune donnée de jeu, aucune ligne de la base.',
      levelRegenerable: 'Régénérable',
      levelRegenerableHelp:
          'Niveau Sûr, plus les caches, les orphelins (médias, métadonnées, couvertures) et les anciens journaux. Tout se recrée, parfois au prix d’une recompilation ou d’un nouveau scraping.',
      levelConfirmed: 'Avec confirmation détaillée',
      levelConfirmedHelp:
          'Niveau Régénérable, plus les diagnostics, enregistrements vidéo, exports, copies de sauvegarde et doublons, à cocher un par un.',
      levelPreselectedNote: 'Les éléments de ce niveau sont présélectionnés.',
      levelNeverPreselectedNote:
          'Aucun élément n’est présélectionné : cochez chaque élément à supprimer.',
      preview: 'Aperçu du nettoyage',
      nothingToClean: 'Rien à nettoyer à ce niveau.',
      selectedTotal: 'Sélectionnés : {count} ({size})',
      deleteAction: 'Supprimer',
      confirmTitle: 'Supprimer les éléments sélectionnés ?',
      confirmBody:
          'Éléments à supprimer : {count} ({size}). La suppression est définitive.',
      warningTitle: 'Avertissement',
      rpcs3CacheWarning:
          'RPCS3 recompilera ses caches LLVM au prochain lancement (démarrage plus long).',
      mediaQuotaWarning:
          'Les médias retirés devront être rescrapés (quota ScreenScraper).',
      diagnosticsWarning:
          'Les diagnostics supprimés ne pourront plus servir à analyser un problème.',
      hdd1Warning:
          'Disque cache de la PS3 : les jeux le recréent, mais certains réinstallent des données à leur prochain lancement (démarrage plus long).',
      kartpadGameDataWarning:
          'KartPad extraira à nouveau les données du jeu au prochain lancement (démarrage plus long).',
      duplicateWarning:
          'Seule la copie que la bibliothèque n’utilise pas peut être supprimée. Vérifiez les deux chemins avant de confirmer.',
      metadataBackupNote:
          'Une copie de la base est enregistrée avant de retirer des métadonnées.',
      sessionActive: 'Nettoyage refusé : un jeu ou un import est en cours.',
      rpcs3Busy:
          'Nettoyage RPCS3 refusé : un jeu PS3 ou une autre opération RPCS3 est en cours.',
      deleting: 'Suppression en cours… {done} sur {total}',
      cancelled:
          'Nettoyage interrompu : les fichiers déjà supprimés le restent.',
      resultTitle: 'Résultat du nettoyage',
      resultDeleted: 'Supprimés : {count} ({size})',
      resultSkippedChanged: 'Ignorés (modifiés depuis l’aperçu) : {count}',
      resultMissing: 'Déjà absents : {count}',
      resultRefused: 'Refusés : {count}',
      resultMetadata: 'Métadonnées retirées de la base : {count}',
      journalSaved: 'Journal enregistré : {path}',
      refuseLink: 'Lien symbolique : jamais suivi ni supprimé.',
      refuseProtected: 'Élément protégé : jamais supprimé.',
      refuseOutside: 'Hors des dossiers analysés par NeoStation.',
      refuseAccess: 'Accès refusé par le système.',
      refuseNotEmpty:
          'Dossier non vide : il contient encore d’autres fichiers.',
      refuseChanged: 'Modifié depuis l’aperçu : laissé intact.',
      refuseNotInPlan: 'Absent de l’aperçu.',
      refuseRoot: 'Dossier principal : seul son contenu peut être nettoyé.',
      refuseCacheApi: 'Le cache de la Bibliothèque n’a pas pu être vidé.',
      refuseRedirected:
          'Le stockage RPCS3 est redirigé ailleurs : NeoStation n’y touche pas.',
      refuseUnknown: 'Refusé pour une raison inattendue.',
      export: 'Exporter le rapport',
      exportDetailed: 'Mode détaillé (chemins relatifs)',
      exportDetailedHelp: 'Par défaut, l’export ne contient que des totaux.',
      share: 'Partager…',
      shareFailed: 'Le rapport n’a pas pu être partagé.',
      limitsTitle: 'Limites de l’analyse',
      limitFfi:
          'Tailles allouées et espace libre non disponibles sur cet appareil : tailles logiques affichées.',
      limitFreeSpace:
          'L’espace libre ne comprend pas l’espace purgeable que les Réglages iOS comptent comme disponible.',
      limitNeoSwap:
          'La mémoire NeoSwap délinkée n’est pas mesurable : ses fichiers restent ouverts pendant le jeu mais n’apparaissent dans aucun dossier.',
      limitExtensions:
          'Les conteneurs des extensions de l’app sont illisibles pour NeoStation et ne sont pas mesurés.',
      limitLinkedFolders:
          'Les dossiers liés hors de NeoStation ne sont ni analysés ni nettoyés.',
      limitRpcs3Cache:
          'Le cache RPCS3 apparaît d’un seul bloc : sa répartition par jeu n’est pas connue.',
      limitDolphinStates: 'Les états Dolphin ne sont pas rattachés à leur jeu.',
      limitScannerOrphans:
          'Les orphelins sont repérés après coup : l’analyse n’empêche pas leur apparition.',
      limitNoAutoPurge:
          'Aucun nettoyage automatique, ni au démarrage ni en arrière-plan.',
      limitUnverified: 'Chiffres non vérifiés sur iPhone.',
      technicalCode: 'Code technique : {code}',
    },
    'de': {
      toolTitle: 'Speicheranalyse und -bereinigung',
      toolSubtitle:
          'Misst den von NeoStation und seinen Engines belegten Speicher und schlägt dann eine Bereinigung mit Vorschau vor.',
      title: 'Speicher',
      scanning: 'Wird analysiert …',
      scanAgain: 'Erneut analysieren',
      scanFailed: 'Die Analyse ist fehlgeschlagen: {error}',
      lastScan: 'Letzte Analyse: {date}',
      cancel: 'Abbrechen',
      summary: 'Übersicht',
      totalLogical: 'Gesamtgröße der Dateien: {size}',
      totalAllocated: 'Belegter Platz auf dem Gerät: {size}',
      allocatedUnavailable: 'Belegte Größe nicht verfügbar',
      freeSpace: 'Freier Speicher: {free} von {total}',
      freeSpaceUnavailable: 'Freier Speicher nicht verfügbar',
      gapExplanation:
          'Die Abweichung von den iOS-Einstellungen entsteht durch APFS-Blöcke, den von iOS geleerten temporären Ordner, NeoSwap-Speicher ohne Verzeichniseintrag und nicht geladene iCloud-Dateien.',
      byCategory: 'Nach Kategorie',
      catGames: 'Spiele und ROMs',
      catSaves: 'Spielstände und Zustände',
      catSystem: 'BIOS, Firmware, Lizenzen und Systemdateien',
      catCaches: 'Neu erstellbare Caches',
      catMedia: 'Gescrapte Medien und Metadaten',
      catTemporary: 'Temporäre Dateien',
      catLogs: 'Protokolle und Diagnosen',
      catUserContent: 'Eigene Inhalte (ohne Spiele)',
      catNeoSwap: 'NeoSwap-Daten',
      catIndex: 'Datenbank, Indizes und Einstellungen',
      catUnknown: 'Sonstige Daten (nicht zugeordnet)',
      byRoot: 'Nach Ordner',
      rootLibrary: 'Bibliothek',
      rootDocuments: 'NeoStation-Ordner in „Dateien“',
      rootSupport: 'Interne App-Daten',
      rootCaches: 'App-Caches',
      rootTemporary: 'Temporärer App-Ordner',
      entries: 'Einträge: {count}',
      links: 'Symbolische Links (nicht verfolgt): {count}',
      inaccessible: 'Nicht zugängliche Einträge: {count}',
      icloudPlaceholders: 'Nicht geladene iCloud-Dateien: {count}',
      detailsShow: 'Details einblenden',
      detailsHide: 'Details ausblenden',
      orphans: 'Verwaiste Daten und Duplikate',
      orphanMedia: 'Medien ohne zugehöriges Spiel: {count} ({size})',
      orphanMetadata: 'Metadaten ohne zugehöriges Spiel: {count}',
      orphanCovers: 'Cover ohne zugehöriges Buch: {count}',
      orphanSavesInfo:
          'Spielstände und Zustände ohne zugehöriges Spiel: {count} (werden nie gelöscht)',
      duplicates:
          'Mögliche Duplikate (gleicher Name, gleiche Größe): {count} ({size})',
      computeHashes: 'Prüfsummen berechnen',
      hashing: 'Prüfsummen werden berechnet …',
      duplicateReferenced: 'Von der Bibliothek verwendet',
      cleanup: 'Bereinigung',
      levelSafe: 'Sicher',
      levelSafeHelp:
          'Temporäre Kopien von Importen, abgebrochene Downloads und Entpackungsreste. Keine Spieldaten, keine Datenbankeinträge.',
      levelRegenerable: 'Neu erstellbar',
      levelRegenerableHelp:
          'Stufe „Sicher“ plus Caches, verwaiste Daten (Medien, Metadaten, Cover) und alte Protokolle. Alles lässt sich neu erstellen, manchmal um den Preis einer Neukompilierung oder eines erneuten Scrapings.',
      levelConfirmed: 'Mit ausführlicher Bestätigung',
      levelConfirmedHelp:
          'Stufe „Neu erstellbar“ plus Diagnosen, Videoaufnahmen, Exporte, Sicherungskopien und Duplikate, die einzeln angehakt werden.',
      levelPreselectedNote: 'Die Einträge dieser Stufe sind vorausgewählt.',
      levelNeverPreselectedNote:
          'Nichts ist vorausgewählt: Hake jeden Eintrag an, der gelöscht werden soll.',
      preview: 'Vorschau der Bereinigung',
      nothingToClean: 'Auf dieser Stufe gibt es nichts zu bereinigen.',
      selectedTotal: 'Ausgewählt: {count} ({size})',
      deleteAction: 'Löschen',
      confirmTitle: 'Ausgewählte Einträge löschen?',
      confirmBody:
          'Zu löschende Einträge: {count} ({size}). Das Löschen ist endgültig.',
      warningTitle: 'Warnung',
      rpcs3CacheWarning:
          'RPCS3 kompiliert seine LLVM-Caches beim nächsten Start neu (längerer Start).',
      mediaQuotaWarning:
          'Entfernte Medien müssen erneut gescrapt werden (ScreenScraper-Kontingent).',
      diagnosticsWarning:
          'Gelöschte Diagnosen helfen nicht mehr bei der Untersuchung eines Problems.',
      hdd1Warning:
          'PS3-Cache-Laufwerk: Spiele legen es neu an, manche installieren beim nächsten Start jedoch Daten erneut (längerer Start).',
      kartpadGameDataWarning:
          'KartPad entpackt die Spieldaten beim nächsten Start erneut (längerer Start).',
      duplicateWarning:
          'Nur die Kopie, die die Bibliothek nicht verwendet, kann gelöscht werden. Prüfe vor dem Bestätigen beide Pfade.',
      metadataBackupNote:
          'Vor dem Entfernen von Metadaten wird eine Kopie der Datenbank gespeichert.',
      sessionActive: 'Bereinigung abgelehnt: Ein Spiel oder ein Import läuft.',
      rpcs3Busy:
          'RPCS3-Bereinigung abgelehnt: Ein PS3-Spiel oder ein anderer RPCS3-Vorgang läuft.',
      deleting: 'Wird gelöscht … {done} von {total}',
      cancelled:
          'Bereinigung abgebrochen: Bereits gelöschte Dateien bleiben gelöscht.',
      resultTitle: 'Ergebnis der Bereinigung',
      resultDeleted: 'Gelöscht: {count} ({size})',
      resultSkippedChanged:
          'Übersprungen (seit der Vorschau geändert): {count}',
      resultMissing: 'Bereits entfernt: {count}',
      resultRefused: 'Abgelehnt: {count}',
      resultMetadata: 'Aus der Datenbank entfernte Metadaten: {count}',
      journalSaved: 'Protokoll gespeichert: {path}',
      refuseLink: 'Symbolischer Link: wird nie verfolgt oder gelöscht.',
      refuseProtected: 'Geschützter Eintrag: wird nie gelöscht.',
      refuseOutside: 'Außerhalb der von NeoStation analysierten Ordner.',
      refuseAccess: 'Zugriff vom System verweigert.',
      refuseNotEmpty: 'Ordner nicht leer: Er enthält noch andere Dateien.',
      refuseChanged: 'Seit der Vorschau geändert: unverändert gelassen.',
      refuseNotInPlan: 'Nicht Teil der Vorschau.',
      refuseRoot: 'Hauptordner: Nur sein Inhalt kann bereinigt werden.',
      refuseCacheApi: 'Der Cache der Bibliothek konnte nicht geleert werden.',
      refuseRedirected:
          'Der RPCS3-Speicher ist an einen anderen Ort umgeleitet: NeoStation lässt ihn unverändert.',
      refuseUnknown: 'Aus einem unerwarteten Grund abgelehnt.',
      export: 'Bericht exportieren',
      exportDetailed: 'Detailmodus (relative Pfade)',
      exportDetailedHelp: 'Standardmäßig enthält der Export nur Summen.',
      share: 'Teilen…',
      shareFailed: 'Der Bericht konnte nicht geteilt werden.',
      limitsTitle: 'Grenzen der Analyse',
      limitFfi:
          'Belegte Größen und freier Speicher sind auf diesem Gerät nicht verfügbar: Es werden logische Größen angezeigt.',
      limitFreeSpace:
          'Der freie Speicher enthält nicht den löschbaren Speicher, den die iOS-Einstellungen als verfügbar zählen.',
      limitNeoSwap:
          'NeoSwap-Speicher ohne Verzeichniseintrag lässt sich nicht messen: Seine Dateien bleiben während des Spiels geöffnet, erscheinen aber in keinem Ordner.',
      limitExtensions:
          'NeoStation kann die Container seiner App-Erweiterungen nicht lesen; sie werden daher nicht gemessen.',
      limitLinkedFolders:
          'Verknüpfte Ordner außerhalb von NeoStation werden weder analysiert noch bereinigt.',
      limitRpcs3Cache:
          'Der RPCS3-Cache erscheint als ein einziger Block: Seine Aufteilung nach Spielen ist unbekannt.',
      limitDolphinStates: 'Dolphin-Zustände werden keinem Spiel zugeordnet.',
      limitScannerOrphans:
          'Verwaiste Daten werden erst nachträglich erkannt: Die Analyse verhindert nicht, dass sie entstehen.',
      limitNoAutoPurge:
          'Nichts wird automatisch bereinigt, weder beim Start noch im Hintergrund.',
      limitUnverified: 'Zahlen nicht auf dem iPhone überprüft.',
      technicalCode: 'Technischer Code: {code}',
    },
    'it': {
      toolTitle: 'Analisi e pulizia dello spazio di archiviazione',
      toolSubtitle:
          'Misura lo spazio usato da NeoStation e dai suoi motori, poi propone una pulizia con anteprima.',
      title: 'Spazio di archiviazione',
      scanning: 'Analisi in corso…',
      scanAgain: 'Analizza di nuovo',
      scanFailed: 'L’analisi non è riuscita: {error}',
      lastScan: 'Ultima analisi: {date}',
      cancel: 'Annulla',
      summary: 'Riepilogo',
      totalLogical: 'Dimensione totale dei file: {size}',
      totalAllocated: 'Spazio occupato sul dispositivo: {size}',
      allocatedUnavailable: 'Dimensione allocata non disponibile',
      freeSpace: 'Spazio libero: {free} su {total}',
      freeSpaceUnavailable: 'Spazio libero non disponibile',
      gapExplanation:
          'La differenza con le Impostazioni di iOS dipende dai blocchi APFS, dalla cartella temporanea svuotata da iOS, dalla memoria NeoSwap scollegata e dai file iCloud non scaricati.',
      byCategory: 'Per categoria',
      catGames: 'Giochi e ROM',
      catSaves: 'Salvataggi e stati',
      catSystem: 'BIOS, firmware, licenze e file di sistema',
      catCaches: 'Cache rigenerabili',
      catMedia: 'Media e metadati dello scraping',
      catTemporary: 'File temporanei',
      catLogs: 'Log e diagnostica',
      catUserContent: 'Contenuti dell’utente (esclusi i giochi)',
      catNeoSwap: 'Dati di NeoSwap',
      catIndex: 'Database, indici e impostazioni',
      catUnknown: 'Altri dati (non identificati)',
      byRoot: 'Per cartella',
      rootLibrary: 'Biblioteca',
      rootDocuments: 'Cartella NeoStation in File',
      rootSupport: 'Dati interni dell’app',
      rootCaches: 'Cache dell’app',
      rootTemporary: 'Cartella temporanea dell’app',
      entries: 'Elementi: {count}',
      links: 'Collegamenti simbolici (non seguiti): {count}',
      inaccessible: 'Elementi non accessibili: {count}',
      icloudPlaceholders: 'File iCloud non scaricati: {count}',
      detailsShow: 'Mostra dettagli',
      detailsHide: 'Nascondi dettagli',
      orphans: 'Orfani e duplicati',
      orphanMedia: 'Media senza gioco associato: {count} ({size})',
      orphanMetadata: 'Metadati senza gioco associato: {count}',
      orphanCovers: 'Copertine senza libro associato: {count}',
      orphanSavesInfo:
          'Salvataggi e stati senza gioco associato: {count} (mai eliminati)',
      duplicates:
          'Possibili duplicati (stesso nome e dimensione): {count} ({size})',
      computeHashes: 'Calcola i checksum',
      hashing: 'Calcolo dei checksum in corso…',
      duplicateReferenced: 'Usato dalla libreria',
      cleanup: 'Pulizia',
      levelSafe: 'Sicuro',
      levelSafeHelp:
          'Copie temporanee lasciate dalle importazioni, download interrotti e residui di estrazione. Nessun dato di gioco né voce del database.',
      levelRegenerable: 'Rigenerabile',
      levelRegenerableHelp:
          'Livello Sicuro, più cache, orfani (media, metadati, copertine) e vecchi log. Tutto si può ricreare, a volte al prezzo di una ricompilazione o di un nuovo scraping.',
      levelConfirmed: 'Con conferma dettagliata',
      levelConfirmedHelp:
          'Livello Rigenerabile, più diagnostica, registrazioni video, esportazioni, copie di backup e duplicati, da spuntare uno per uno.',
      levelPreselectedNote:
          'Gli elementi di questo livello sono preselezionati.',
      levelNeverPreselectedNote:
          'Nessun elemento è preselezionato: spunta ogni elemento da eliminare.',
      preview: 'Anteprima della pulizia',
      nothingToClean: 'Niente da pulire a questo livello.',
      selectedTotal: 'Selezionati: {count} ({size})',
      deleteAction: 'Elimina',
      confirmTitle: 'Eliminare gli elementi selezionati?',
      confirmBody:
          'Elementi da eliminare: {count} ({size}). L’eliminazione è definitiva.',
      warningTitle: 'Avviso',
      rpcs3CacheWarning:
          'RPCS3 ricompilerà le sue cache LLVM al prossimo avvio (avvio più lento).',
      mediaQuotaWarning:
          'I media rimossi dovranno essere recuperati di nuovo con lo scraping (quota ScreenScraper).',
      diagnosticsWarning:
          'La diagnostica eliminata non potrà più servire ad analizzare un problema.',
      hdd1Warning:
          'Disco cache della PS3: i giochi lo ricreano, ma alcuni reinstallano dati al prossimo avvio (avvio più lento).',
      kartpadGameDataWarning:
          'KartPad estrarrà di nuovo i dati del gioco al prossimo avvio (avvio più lento).',
      duplicateWarning:
          'Si può eliminare solo la copia che la libreria non usa. Controlla entrambi i percorsi prima di confermare.',
      metadataBackupNote:
          'Prima di rimuovere metadati viene salvata una copia del database.',
      sessionActive:
          'Pulizia rifiutata: è in corso un gioco o un’importazione.',
      rpcs3Busy:
          'Pulizia di RPCS3 rifiutata: è in corso un gioco PS3 o un’altra operazione di RPCS3.',
      deleting: 'Eliminazione in corso… {done} di {total}',
      cancelled: 'Pulizia interrotta: i file già eliminati restano eliminati.',
      resultTitle: 'Risultato della pulizia',
      resultDeleted: 'Eliminati: {count} ({size})',
      resultSkippedChanged: 'Saltati (modificati dopo l’anteprima): {count}',
      resultMissing: 'Già assenti: {count}',
      resultRefused: 'Rifiutati: {count}',
      resultMetadata: 'Metadati rimossi dal database: {count}',
      journalSaved: 'Log salvato: {path}',
      refuseLink: 'Collegamento simbolico: mai seguito né eliminato.',
      refuseProtected: 'Elemento protetto: mai eliminato.',
      refuseOutside: 'Fuori dalle cartelle analizzate da NeoStation.',
      refuseAccess: 'Accesso negato dal sistema.',
      refuseNotEmpty: 'Cartella non vuota: contiene ancora altri file.',
      refuseChanged: 'Modificato dopo l’anteprima: lasciato intatto.',
      refuseNotInPlan: 'Non fa parte dell’anteprima.',
      refuseRoot: 'Cartella principale: si può pulire solo il suo contenuto.',
      refuseCacheApi: 'Impossibile svuotare la cache della Biblioteca.',
      refuseRedirected:
          'Lo spazio di archiviazione di RPCS3 è reindirizzato altrove: NeoStation non lo tocca.',
      refuseUnknown: 'Rifiutato per un motivo imprevisto.',
      export: 'Esporta il rapporto',
      exportDetailed: 'Modalità dettagliata (percorsi relativi)',
      exportDetailedHelp:
          'Per impostazione predefinita, l’esportazione contiene solo i totali.',
      share: 'Condividi…',
      shareFailed: 'Impossibile condividere il rapporto.',
      limitsTitle: 'Limiti dell’analisi',
      limitFfi:
          'Dimensioni allocate e spazio libero non disponibili su questo dispositivo: vengono mostrate le dimensioni logiche.',
      limitFreeSpace:
          'Lo spazio libero non include lo spazio eliminabile che le Impostazioni di iOS contano come disponibile.',
      limitNeoSwap:
          'La memoria NeoSwap scollegata non è misurabile: i suoi file restano aperti durante il gioco, ma non compaiono in nessuna cartella.',
      limitExtensions:
          'NeoStation non può leggere i contenitori delle estensioni dell’app, quindi non vengono misurati.',
      limitLinkedFolders:
          'Le cartelle collegate esterne a NeoStation non vengono né analizzate né pulite.',
      limitRpcs3Cache:
          'La cache di RPCS3 appare come un unico blocco: la sua suddivisione per gioco non è nota.',
      limitDolphinStates:
          'Gli stati di Dolphin non vengono associati al loro gioco.',
      limitScannerOrphans:
          'Gli orfani vengono individuati a posteriori: l’analisi non ne impedisce la comparsa.',
      limitNoAutoPurge:
          'Nessuna pulizia automatica, né all’avvio né in background.',
      limitUnverified: 'Cifre non verificate su iPhone.',
      technicalCode: 'Codice tecnico: {code}',
    },
    'id': {
      toolTitle: 'Analisis dan pembersihan penyimpanan',
      toolSubtitle:
          'Mengukur ruang yang dipakai NeoStation dan mesinnya, lalu menawarkan pembersihan dengan pratinjau.',
      title: 'Penyimpanan',
      scanning: 'Sedang menganalisis…',
      scanAgain: 'Analisis ulang',
      scanFailed: 'Analisis gagal: {error}',
      lastScan: 'Analisis terakhir: {date}',
      cancel: 'Batal',
      summary: 'Ringkasan',
      totalLogical: 'Total ukuran file: {size}',
      totalAllocated: 'Ruang terpakai di perangkat: {size}',
      allocatedUnavailable: 'Ukuran teralokasi tidak tersedia',
      freeSpace: 'Ruang kosong: {free} dari {total}',
      freeSpaceUnavailable: 'Ruang kosong tidak tersedia',
      gapExplanation:
          'Selisih dengan Pengaturan iOS berasal dari blok APFS, folder sementara yang dikosongkan iOS, memori NeoSwap yang sudah di-unlink, dan file iCloud yang belum diunduh.',
      byCategory: 'Menurut kategori',
      catGames: 'Game dan ROM',
      catSaves: 'Simpanan dan status',
      catSystem: 'BIOS, firmware, lisensi, dan file sistem',
      catCaches: 'Cache yang dapat dibuat ulang',
      catMedia: 'Media dan metadata hasil scraping',
      catTemporary: 'File sementara',
      catLogs: 'Log dan diagnostik',
      catUserContent: 'Konten pengguna (selain game)',
      catNeoSwap: 'Data NeoSwap',
      catIndex: 'Basis data, indeks, dan pengaturan',
      catUnknown: 'Data lain (tidak dikenali)',
      byRoot: 'Menurut folder',
      rootLibrary: 'Perpustakaan',
      rootDocuments: 'Folder NeoStation di app File',
      rootSupport: 'Data internal aplikasi',
      rootCaches: 'Cache aplikasi',
      rootTemporary: 'Folder sementara aplikasi',
      entries: 'Jumlah item: {count}',
      links: 'Tautan simbolik (tidak diikuti): {count}',
      inaccessible: 'Item yang tidak dapat diakses: {count}',
      icloudPlaceholders: 'File iCloud yang belum diunduh: {count}',
      detailsShow: 'Tampilkan detail',
      detailsHide: 'Sembunyikan detail',
      orphans: 'Item yatim dan duplikat',
      orphanMedia: 'Media tanpa game terkait: {count} ({size})',
      orphanMetadata: 'Metadata tanpa game terkait: {count}',
      orphanCovers: 'Sampul tanpa buku terkait: {count}',
      orphanSavesInfo:
          'Simpanan dan status tanpa game terkait: {count} (tidak pernah dihapus)',
      duplicates:
          'Kemungkinan duplikat (nama dan ukuran sama): {count} ({size})',
      computeHashes: 'Hitung checksum',
      hashing: 'Menghitung checksum…',
      duplicateReferenced: 'Dirujuk oleh perpustakaan',
      cleanup: 'Pembersihan',
      levelSafe: 'Aman',
      levelSafeHelp:
          'Salinan sementara sisa impor, unduhan yang terputus, dan sisa ekstraksi. Tanpa data game dan tanpa entri basis data.',
      levelRegenerable: 'Dapat dibuat ulang',
      levelRegenerableHelp:
          'Tingkat “Aman”, ditambah cache, item yatim (media, metadata, sampul), dan log lama. Semuanya dapat dibuat ulang, kadang dengan kompilasi ulang atau scraping baru.',
      levelConfirmed: 'Dengan konfirmasi terperinci',
      levelConfirmedHelp:
          'Tingkat “Dapat dibuat ulang”, ditambah diagnostik, rekaman video, ekspor, salinan cadangan, dan duplikat; centang satu per satu.',
      levelPreselectedNote: 'Item pada tingkat ini sudah dipilih sebelumnya.',
      levelNeverPreselectedNote:
          'Tidak ada yang dipilih sebelumnya: centang setiap item yang akan dihapus.',
      preview: 'Pratinjau pembersihan',
      nothingToClean: 'Tidak ada yang perlu dibersihkan pada tingkat ini.',
      selectedTotal: 'Dipilih: {count} ({size})',
      deleteAction: 'Hapus',
      confirmTitle: 'Hapus item yang dipilih?',
      confirmBody:
          'Item yang akan dihapus: {count} ({size}). Penghapusan bersifat permanen.',
      warningTitle: 'Peringatan',
      rpcs3CacheWarning:
          'RPCS3 akan mengompilasi ulang cache LLVM-nya saat diluncurkan berikutnya (mulai lebih lama).',
      mediaQuotaWarning:
          'Media yang dihapus harus di-scraping ulang (kuota ScreenScraper).',
      diagnosticsWarning:
          'Diagnostik yang dihapus tidak dapat lagi dipakai untuk menyelidiki masalah.',
      hdd1Warning:
          'Disk cache PS3: game membuatnya ulang, tetapi beberapa game memasang ulang data saat diluncurkan berikutnya (mulai lebih lama).',
      kartpadGameDataWarning:
          'KartPad akan mengekstrak ulang data game saat diluncurkan berikutnya (mulai lebih lama).',
      duplicateWarning:
          'Hanya salinan yang tidak dipakai perpustakaan yang dapat dihapus. Periksa kedua jalur sebelum mengonfirmasi.',
      metadataBackupNote:
          'Salinan basis data disimpan sebelum metadata dihapus.',
      sessionActive:
          'Pembersihan ditolak: ada game atau impor yang sedang berjalan.',
      rpcs3Busy:
          'Pembersihan RPCS3 ditolak: ada game PS3 atau operasi RPCS3 lain yang sedang berjalan.',
      deleting: 'Menghapus… {done} dari {total}',
      cancelled:
          'Pembersihan dihentikan: file yang sudah dihapus tetap terhapus.',
      resultTitle: 'Hasil pembersihan',
      resultDeleted: 'Dihapus: {count} ({size})',
      resultSkippedChanged: 'Dilewati (berubah sejak pratinjau): {count}',
      resultMissing: 'Sudah tidak ada: {count}',
      resultRefused: 'Ditolak: {count}',
      resultMetadata: 'Metadata yang dihapus dari basis data: {count}',
      journalSaved: 'Log disimpan: {path}',
      refuseLink: 'Tautan simbolik: tidak pernah diikuti atau dihapus.',
      refuseProtected: 'Item terlindungi: tidak pernah dihapus.',
      refuseOutside: 'Di luar folder yang dianalisis NeoStation.',
      refuseAccess: 'Akses ditolak oleh sistem.',
      refuseNotEmpty: 'Folder tidak kosong: masih berisi file lain.',
      refuseChanged: 'Berubah sejak pratinjau: dibiarkan apa adanya.',
      refuseNotInPlan: 'Tidak termasuk dalam pratinjau.',
      refuseRoot: 'Folder utama: hanya isinya yang dapat dibersihkan.',
      refuseCacheApi: 'Cache Perpustakaan tidak dapat dikosongkan.',
      refuseRedirected:
          'Penyimpanan RPCS3 dialihkan ke tempat lain: NeoStation tidak menyentuhnya.',
      refuseUnknown: 'Ditolak karena alasan yang tidak terduga.',
      export: 'Ekspor laporan',
      exportDetailed: 'Mode terperinci (jalur relatif)',
      exportDetailedHelp: 'Secara default, ekspor hanya berisi total.',
      share: 'Bagikan…',
      shareFailed: 'Laporan tidak dapat dibagikan.',
      limitsTitle: 'Batasan analisis',
      limitFfi:
          'Ukuran teralokasi dan ruang kosong tidak tersedia di perangkat ini: yang ditampilkan adalah ukuran logis.',
      limitFreeSpace:
          'Ruang kosong tidak mencakup ruang yang dapat dibersihkan, yang oleh Pengaturan iOS dihitung sebagai tersedia.',
      limitNeoSwap:
          'Memori NeoSwap yang sudah di-unlink tidak dapat diukur: file-nya tetap terbuka selama game berjalan, tetapi tidak muncul di folder mana pun.',
      limitExtensions:
          'NeoStation tidak dapat membaca kontainer ekstensi aplikasinya, jadi kontainer itu tidak diukur.',
      limitLinkedFolders:
          'Folder tertaut di luar NeoStation tidak dianalisis dan tidak dibersihkan.',
      limitRpcs3Cache:
          'Cache RPCS3 ditampilkan sebagai satu blok: rinciannya per game tidak diketahui.',
      limitDolphinStates: 'Status Dolphin tidak dikaitkan dengan game-nya.',
      limitScannerOrphans:
          'Item yatim baru terdeteksi setelah muncul: analisis tidak mencegah kemunculannya.',
      limitNoAutoPurge:
          'Tidak ada pembersihan otomatis, baik saat memulai maupun di latar belakang.',
      limitUnverified: 'Angka belum diverifikasi di iPhone.',
      technicalCode: 'Kode teknis: {code}',
    },
    'ja': {
      toolTitle: 'ストレージの分析とクリーンアップ',
      toolSubtitle: 'NeoStation とそのエンジンが使用している容量を測定し、プレビュー付きのクリーンアップを提案します。',
      title: 'ストレージ',
      scanning: '分析中…',
      scanAgain: '再分析',
      scanFailed: '分析に失敗しました：{error}',
      lastScan: '前回の分析：{date}',
      cancel: 'キャンセル',
      summary: '概要',
      totalLogical: 'ファイルの合計サイズ：{size}',
      totalAllocated: 'デバイス上の使用領域：{size}',
      allocatedUnavailable: '割り当てサイズを取得できません',
      freeSpace: '空き容量：{free}（合計 {total}）',
      freeSpaceUnavailable: '空き容量を取得できません',
      gapExplanation:
          'iOS の設定との差は、APFS のブロック、iOS が消去する一時フォルダ、リンク解除された NeoSwap のメモリ、未ダウンロードの iCloud ファイルによるものです。',
      byCategory: 'カテゴリ別',
      catGames: 'ゲームと ROM',
      catSaves: 'セーブデータとステートセーブ',
      catSystem: 'BIOS、ファームウェア、ライセンス、システムファイル',
      catCaches: '再生成できるキャッシュ',
      catMedia: 'スクレイピングしたメディアとメタデータ',
      catTemporary: '一時ファイル',
      catLogs: 'ログと診断',
      catUserContent: 'ユーザーコンテンツ（ゲーム以外）',
      catNeoSwap: 'NeoSwap のデータ',
      catIndex: 'データベース、インデックス、設定',
      catUnknown: 'その他のデータ（未識別）',
      byRoot: 'フォルダ別',
      rootLibrary: 'ライブラリ',
      rootDocuments: '「ファイル」App の NeoStation フォルダ',
      rootSupport: 'App の内部データ',
      rootCaches: 'App のキャッシュ',
      rootTemporary: 'App の一時フォルダ',
      entries: '項目数：{count}',
      links: 'シンボリックリンク（たどらない）：{count}',
      inaccessible: 'アクセスできない項目：{count}',
      icloudPlaceholders: '未ダウンロードの iCloud ファイル：{count}',
      detailsShow: '詳細を表示',
      detailsHide: '詳細を隠す',
      orphans: '孤立データと重複',
      orphanMedia: '対応するゲームがないメディア：{count}（{size}）',
      orphanMetadata: '対応するゲームがないメタデータ：{count}',
      orphanCovers: '対応する本がない表紙：{count}',
      orphanSavesInfo: '対応するゲームがないセーブデータとステートセーブ：{count}（削除されません）',
      duplicates: '重複の可能性（同じ名前とサイズ）：{count}（{size}）',
      computeHashes: 'チェックサムを計算',
      hashing: 'チェックサムを計算中…',
      duplicateReferenced: 'ライブラリが参照中',
      cleanup: 'クリーンアップ',
      levelSafe: '安全',
      levelSafeHelp:
          'インポートで残った一時コピー、中断したダウンロード、展開の残りです。ゲームデータやデータベースの項目は含みません。',
      levelRegenerable: '再生成可能',
      levelRegenerableHelp:
          '「安全」レベルの内容に加え、キャッシュ、孤立データ（メディア、メタデータ、表紙）、古いログが対象です。すべて再生成できますが、再コンパイルや再スクレイピングが必要になる場合があります。',
      levelConfirmed: '詳細な確認が必要',
      levelConfirmedHelp:
          '「再生成可能」レベルの内容に加え、診断、ビデオ録画、エクスポートしたファイル、バックアップコピー、重複が対象です。1 つずつチェックします。',
      levelPreselectedNote: 'このレベルの項目はあらかじめ選択されています。',
      levelNeverPreselectedNote:
          'あらかじめ選択されている項目はありません。削除する項目を 1 つずつチェックしてください。',
      preview: 'クリーンアップのプレビュー',
      nothingToClean: 'このレベルでクリーンアップするものはありません。',
      selectedTotal: '選択中：{count}（{size}）',
      deleteAction: '削除',
      confirmTitle: '選択した項目を削除しますか？',
      confirmBody: '削除する項目：{count}（{size}）。削除は元に戻せません。',
      warningTitle: '警告',
      rpcs3CacheWarning: 'RPCS3 は次回の起動時に LLVM キャッシュを再コンパイルします（起動に時間がかかります）。',
      mediaQuotaWarning: '削除したメディアは再スクレイピングが必要です（ScreenScraper の利用枠を消費）。',
      diagnosticsWarning: '削除した診断は、問題の調査に使えなくなります。',
      hdd1Warning:
          'PS3 のキャッシュディスク：ゲームが再作成しますが、次回の起動時にデータを再インストールするゲームもあります（起動に時間がかかります）。',
      kartpadGameDataWarning: 'KartPad は次回の起動時にゲームデータを再展開します（起動に時間がかかります）。',
      duplicateWarning: '削除できるのは、ライブラリが使用していないコピーだけです。確定する前に両方のパスを確認してください。',
      metadataBackupNote: 'メタデータを削除する前に、データベースのコピーを保存します。',
      sessionActive: 'クリーンアップを拒否しました：ゲームまたはインポートが進行中です。',
      rpcs3Busy: 'RPCS3 のクリーンアップを拒否しました：PS3 ゲームまたは別の RPCS3 の処理が進行中です。',
      deleting: '削除中… {done}/{total}',
      cancelled: 'クリーンアップを中断しました：削除済みのファイルは元に戻りません。',
      resultTitle: 'クリーンアップの結果',
      resultDeleted: '削除済み：{count}（{size}）',
      resultSkippedChanged: 'スキップ（プレビュー後に変更あり）：{count}',
      resultMissing: 'すでに存在しない：{count}',
      resultRefused: '拒否：{count}',
      resultMetadata: 'データベースから削除したメタデータ：{count}',
      journalSaved: 'ログを保存しました：{path}',
      refuseLink: 'シンボリックリンク：たどることも削除することもありません。',
      refuseProtected: '保護された項目：削除されません。',
      refuseOutside: 'NeoStation が分析するフォルダの外にあります。',
      refuseAccess: 'システムによりアクセスが拒否されました。',
      refuseNotEmpty: 'フォルダが空ではありません：ほかのファイルが残っています。',
      refuseChanged: 'プレビュー後に変更されました：そのまま残しています。',
      refuseNotInPlan: 'プレビューに含まれていません。',
      refuseRoot: 'メインフォルダ：クリーンアップできるのは中身だけです。',
      refuseCacheApi: 'ライブラリのキャッシュを消去できませんでした。',
      refuseRedirected: 'RPCS3 のストレージは別の場所にリダイレクトされています：NeoStation は変更しません。',
      refuseUnknown: '予期しない理由で拒否されました。',
      export: 'レポートをエクスポート',
      exportDetailed: '詳細モード（相対パス）',
      exportDetailedHelp: 'デフォルトでは、エクスポートには合計のみが含まれます。',
      share: '共有…',
      shareFailed: 'レポートを共有できませんでした。',
      limitsTitle: '分析の制限',
      limitFfi: 'このデバイスでは割り当てサイズと空き容量を取得できません：論理サイズを表示しています。',
      limitFreeSpace: '空き容量には、iOS の設定で「利用可能」に含まれる削除可能な領域は含まれません。',
      limitNeoSwap:
          'リンク解除された NeoSwap のメモリは測定できません：そのファイルはゲーム中も開いたままですが、どのフォルダにも表示されません。',
      limitExtensions: 'NeoStation は App の機能拡張のコンテナを読み取れないため、それらは測定されません。',
      limitLinkedFolders: 'NeoStation の外部からリンクしたフォルダは、分析もクリーンアップもされません。',
      limitRpcs3Cache: 'RPCS3 のキャッシュは 1 つのまとまりとして表示されます：ゲームごとの内訳は不明です。',
      limitDolphinStates: 'Dolphin のステートセーブは、対応するゲームと関連付けられません。',
      limitScannerOrphans: '孤立データは後から検出されます：分析で発生を防ぐことはできません。',
      limitNoAutoPurge: '起動時にもバックグラウンドでも、自動でクリーンアップすることはありません。',
      limitUnverified: '数値は iPhone で検証されていません。',
      technicalCode: '技術コード：{code}',
    },
    'ko': {
      toolTitle: '저장 공간 분석 및 정리',
      toolSubtitle: 'NeoStation과 엔진이 사용하는 공간을 측정한 뒤, 미리 보기가 있는 정리를 제안합니다.',
      title: '저장 공간',
      scanning: '분석 중…',
      scanAgain: '다시 분석',
      scanFailed: '분석하지 못했습니다: {error}',
      lastScan: '마지막 분석: {date}',
      cancel: '취소',
      summary: '요약',
      totalLogical: '파일 전체 크기: {size}',
      totalAllocated: '기기에서 차지하는 공간: {size}',
      allocatedUnavailable: '할당 크기를 확인할 수 없음',
      freeSpace: '여유 공간: {total} 중 {free}',
      freeSpaceUnavailable: '여유 공간을 확인할 수 없음',
      gapExplanation:
          'iOS 설정과의 차이는 APFS 블록, iOS가 비우는 임시 폴더, 링크 해제된 NeoSwap 메모리, 다운로드되지 않은 iCloud 파일에서 생깁니다.',
      byCategory: '카테고리별',
      catGames: '게임 및 ROM',
      catSaves: '세이브 데이터 및 상태 저장',
      catSystem: 'BIOS, 펌웨어, 라이선스 및 시스템 파일',
      catCaches: '다시 만들 수 있는 캐시',
      catMedia: '스크래핑한 미디어 및 메타데이터',
      catTemporary: '임시 파일',
      catLogs: '로그 및 진단',
      catUserContent: '사용자 콘텐츠(게임 제외)',
      catNeoSwap: 'NeoSwap 데이터',
      catIndex: '데이터베이스, 색인 및 설정',
      catUnknown: '기타 데이터(식별되지 않음)',
      byRoot: '폴더별',
      rootLibrary: '라이브러리',
      rootDocuments: '파일 앱의 NeoStation 폴더',
      rootSupport: '앱 내부 데이터',
      rootCaches: '앱 캐시',
      rootTemporary: '앱 임시 폴더',
      entries: '항목 수: {count}',
      links: '심볼릭 링크(따라가지 않음): {count}',
      inaccessible: '접근할 수 없는 항목: {count}',
      icloudPlaceholders: '다운로드되지 않은 iCloud 파일: {count}',
      detailsShow: '자세히 보기',
      detailsHide: '간단히 보기',
      orphans: '고아 항목 및 중복',
      orphanMedia: '연결된 게임이 없는 미디어: {count}({size})',
      orphanMetadata: '연결된 게임이 없는 메타데이터: {count}',
      orphanCovers: '연결된 책이 없는 표지: {count}',
      orphanSavesInfo: '연결된 게임이 없는 세이브 데이터 및 상태 저장: {count}(삭제하지 않음)',
      duplicates: '중복 가능 항목(이름과 크기가 같음): {count}({size})',
      computeHashes: '체크섬 계산',
      hashing: '체크섬 계산 중…',
      duplicateReferenced: '라이브러리에서 참조 중',
      cleanup: '정리',
      levelSafe: '안전',
      levelSafeHelp:
          '가져오기 후 남은 임시 사본, 중단된 다운로드, 압축 해제 잔여 파일입니다. 게임 데이터와 데이터베이스 항목은 포함되지 않습니다.',
      levelRegenerable: '다시 생성 가능',
      levelRegenerableHelp:
          '‘안전’ 단계에 더해 캐시, 고아 항목(미디어, 메타데이터, 표지), 오래된 로그가 포함됩니다. 모두 다시 만들 수 있지만 다시 컴파일하거나 다시 스크래핑해야 할 수 있습니다.',
      levelConfirmed: '상세 확인 필요',
      levelConfirmedHelp:
          '‘다시 생성 가능’ 단계에 더해 진단, 동영상 녹화, 내보낸 파일, 백업 사본, 중복 항목이 포함되며 하나씩 선택합니다.',
      levelPreselectedNote: '이 단계의 항목은 미리 선택되어 있습니다.',
      levelNeverPreselectedNote: '미리 선택된 항목이 없습니다. 삭제할 항목을 하나씩 선택하세요.',
      preview: '정리 미리 보기',
      nothingToClean: '이 단계에서 정리할 항목이 없습니다.',
      selectedTotal: '선택됨: {count}({size})',
      deleteAction: '삭제',
      confirmTitle: '선택한 항목을 삭제할까요?',
      confirmBody: '삭제할 항목: {count}({size}). 삭제하면 되돌릴 수 없습니다.',
      warningTitle: '경고',
      rpcs3CacheWarning: '다음 실행 때 RPCS3의 LLVM 캐시를 다시 컴파일합니다(시작이 더 오래 걸림).',
      mediaQuotaWarning: '삭제한 미디어는 다시 스크래핑해야 합니다(ScreenScraper 할당량 사용).',
      diagnosticsWarning: '삭제한 진단 정보는 더 이상 문제 분석에 사용할 수 없습니다.',
      hdd1Warning:
          'PS3 캐시 디스크: 게임이 다시 만들지만, 일부 게임은 다음 실행 때 데이터를 다시 설치합니다(시작이 더 오래 걸림).',
      kartpadGameDataWarning: 'KartPad가 다음 실행 때 게임 데이터를 다시 추출합니다(시작이 더 오래 걸림).',
      duplicateWarning:
          '라이브러리가 사용하지 않는 사본만 삭제할 수 있습니다. 확인하기 전에 두 경로를 모두 살펴보세요.',
      metadataBackupNote: '메타데이터를 제거하기 전에 데이터베이스 사본을 저장합니다.',
      sessionActive: '정리 거부됨: 게임 또는 가져오기가 진행 중입니다.',
      rpcs3Busy: 'RPCS3 정리 거부됨: PS3 게임 또는 다른 RPCS3 작업이 진행 중입니다.',
      deleting: '삭제 중… {done}/{total}',
      cancelled: '정리가 중단되었습니다. 이미 삭제된 파일은 복구되지 않습니다.',
      resultTitle: '정리 결과',
      resultDeleted: '삭제됨: {count}({size})',
      resultSkippedChanged: '건너뜀(미리 보기 이후 변경됨): {count}',
      resultMissing: '이미 없음: {count}',
      resultRefused: '거부됨: {count}',
      resultMetadata: '데이터베이스에서 제거한 메타데이터: {count}',
      journalSaved: '로그 저장됨: {path}',
      refuseLink: '심볼릭 링크: 따라가거나 삭제하지 않습니다.',
      refuseProtected: '보호된 항목: 삭제하지 않습니다.',
      refuseOutside: 'NeoStation이 분석하는 폴더 밖에 있습니다.',
      refuseAccess: '시스템이 접근을 거부했습니다.',
      refuseNotEmpty: '폴더가 비어 있지 않습니다. 다른 파일이 남아 있습니다.',
      refuseChanged: '미리 보기 이후 변경됨: 그대로 두었습니다.',
      refuseNotInPlan: '미리 보기에 포함되지 않은 항목입니다.',
      refuseRoot: '기본 폴더: 안의 내용만 정리할 수 있습니다.',
      refuseCacheApi: '라이브러리 캐시를 비울 수 없습니다.',
      refuseRedirected: 'RPCS3 저장 공간이 다른 위치로 리디렉션되어 있어 NeoStation이 건드리지 않습니다.',
      refuseUnknown: '예상치 못한 이유로 거부되었습니다.',
      export: '보고서 내보내기',
      exportDetailed: '상세 모드(상대 경로)',
      exportDetailedHelp: '기본적으로 내보내기에는 합계만 포함됩니다.',
      share: '공유…',
      shareFailed: '보고서를 공유할 수 없습니다.',
      limitsTitle: '분석의 한계',
      limitFfi: '이 기기에서는 할당 크기와 여유 공간을 확인할 수 없어 논리 크기를 표시합니다.',
      limitFreeSpace: '여유 공간에는 iOS 설정이 ‘사용 가능’으로 계산하는 제거 가능한 공간이 포함되지 않습니다.',
      limitNeoSwap:
          '링크 해제된 NeoSwap 메모리는 측정할 수 없습니다. 해당 파일은 게임 중에 열려 있지만 어떤 폴더에도 나타나지 않습니다.',
      limitExtensions: 'NeoStation은 앱 확장 프로그램의 컨테이너를 읽을 수 없어 측정하지 않습니다.',
      limitLinkedFolders: 'NeoStation 외부에서 연결한 폴더는 분석하거나 정리하지 않습니다.',
      limitRpcs3Cache: 'RPCS3 캐시는 하나로 묶어 표시되며 게임별 내역은 알 수 없습니다.',
      limitDolphinStates: 'Dolphin 상태 저장은 해당 게임과 연결되지 않습니다.',
      limitScannerOrphans: '고아 항목은 생긴 뒤에 발견되며, 분석으로 생기는 것을 막을 수는 없습니다.',
      limitNoAutoPurge: '시작할 때나 백그라운드에서 자동으로 정리하지 않습니다.',
      limitUnverified: 'iPhone에서 검증되지 않은 수치입니다.',
      technicalCode: '기술 코드: {code}',
    },
  };

  /// Catalog key of each `StorageCategory`, by enum `name` (§ 3.1).
  static const Map<String, String> categoryKeys = <String, String>{
    'games': catGames,
    'saves': catSaves,
    'systemFiles': catSystem,
    'caches': catCaches,
    'media': catMedia,
    'temporary': catTemporary,
    'logs': catLogs,
    'userContent': catUserContent,
    'neoSwap': catNeoSwap,
    'index': catIndex,
    'unknown': catUnknown,
  };

  /// Catalog key of each `StorageContainer`, by enum `name` (§ 3.1).
  static const Map<String, String> containerKeys = <String, String>{
    'documents': rootDocuments,
    'applicationSupport': rootSupport,
    'caches': rootCaches,
    'temporary': rootTemporary,
  };

  /// Catalog key of each `StorageCleanupLevel`, by enum `name` (§ 3.7).
  static const Map<String, String> levelKeys = <String, String>{
    'safe': levelSafe,
    'regenerable': levelRegenerable,
    'confirmed': levelConfirmed,
  };

  /// Help text of each `StorageCleanupLevel`, by enum `name` (§ 3.7).
  static const Map<String, String> levelHelpKeys = <String, String>{
    'safe': levelSafeHelp,
    'regenerable': levelRegenerableHelp,
    'confirmed': levelConfirmedHelp,
  };

  /// Catalog key of each `StorageRefusalReason`, by enum `name` (§ 3.8). The
  /// raw reason and errno text stay visible through [technicalCode].
  static const Map<String, String> refusalKeys = <String, String>{
    'sessionActive': sessionActive,
    'notInPlan': refuseNotInPlan,
    'outsideWhitelist': refuseOutside,
    'isRoot': refuseRoot,
    'isProtected': refuseProtected,
    'isLink': refuseLink,
    'changedSincePreview': refuseChanged,
    'accessDenied': refuseAccess,
    'notEmpty': refuseNotEmpty,
    'cacheApiFailed': refuseCacheApi,
    'rpcs3Busy': rpcs3Busy,
    'redirected': refuseRedirected,
    'unknown': refuseUnknown,
  };

  /// Catalog code for [locale]: `zh_Hant` for Traditional Chinese (script
  /// Hant, or Taiwan, Hong Kong, Macao), English for unsupported languages.
  static String codeFor(Locale locale) {
    var code = locale.languageCode;
    if (code == 'zh_Hant') return 'zh_Hant';
    if (code == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' ||
          country == 'TW' ||
          country == 'HK' ||
          country == 'MO') {
        code = 'zh_Hant';
      }
    }
    return values.containsKey(code) ? code : 'en';
  }

  /// Text of [key] for [locale], each `{name}` placeholder replaced by
  /// `parameters[name]` (see [fill]).
  static String forLocale(
    Locale locale,
    String key, [
    Map<String, Object?> parameters = const <String, Object?>{},
  ]) => fill(
    values[codeFor(locale)]?[key] ?? values['en']![key] ?? key,
    parameters,
  );

  /// Text of [key] in the app language, its placeholders filled from
  /// [parameters]:
  ///
  /// ```dart
  /// StorageLocale.text(context, StorageLocale.freeSpace, {
  ///   'free': free,
  ///   'total': total,
  /// });
  /// ```
  static String text(
    BuildContext context,
    String key, [
    Map<String, Object?> parameters = const <String, Object?>{},
  ]) => forLocale(
    Localizations.maybeLocaleOf(context) ?? const Locale('en'),
    key,
    parameters,
  );

  /// Same as [text] with mandatory parameters (the other catalogs' form).
  static String format(
    BuildContext context,
    String key,
    Map<String, Object?> parameters,
  ) => text(context, key, parameters);

  /// Replaces each `{name}` of [template] present in [parameters] in a
  /// single pass: a value that itself contains `{…}` (a path, a raw error)
  /// is inserted as is and never expanded again. Unknown placeholders stay.
  static String fill(String template, Map<String, Object?> parameters) {
    if (parameters.isEmpty) return template;
    return template.replaceAllMapped(_placeholder, (match) {
      final name = match[1]!;
      if (!parameters.containsKey(name)) return match[0]!;
      return parameters[name]?.toString() ?? '';
    });
  }

  static final RegExp _placeholder = RegExp(r'\{(\w+)\}');
}
