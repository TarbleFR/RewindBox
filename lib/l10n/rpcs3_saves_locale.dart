import 'package:flutter/widgets.dart';

/// Texts of the PS3 game-save exchange (RPCS3 manager: export to a ZIP in
/// Files, import from Files, a ZIP or a folder, replace prompt, reports and
/// refusals) in RewindBox's twelve languages. Save directory names, titles
/// read from PARAM.SFO, file names, paths, sizes and raw system diagnostics
/// stay untranslated and are shown apart from these texts.
abstract final class Rpcs3SavesLocale {
  static const Map<String, Map<String, String>>
  values = <String, Map<String, String>>{
    'en': {
      'importSourceTitle': 'Import game saves',
      'importSourceBody':
          'Choose where the saves come from. A save is a folder holding a PARAM.SFO file, alone or inside a ZIP archive.',
      'sourceFilesFolder': 'Files folder of RewindBox',
      'sourceFilesFolderHint':
          'Save folders or ZIP archives placed in Files › On My iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'sourceZip': 'Choose a ZIP archive…',
      'sourceZipHint':
          'An archive exported by RewindBox or by RPCS3 on another device.',
      'sourceFolder': 'Choose a save folder…',
      'sourceFolderHint': 'A save folder, or a folder containing several saves.',
      'cancel': 'Cancel',
      'close': 'Close',
      'share': 'Share…',
      'replace': 'Replace',
      'keepExisting': 'Keep existing',
      'replaceTitle': 'Replace existing saves?',
      'replaceBody':
          'Saves already present in RPCS3 with different content: {count}. If you replace them, the current folders are moved to a backup outside RPCS3 before the new ones are installed.',
      'exportTitle': 'Game saves exported',
      'exportSummary': 'Saves: {saves} • Files: {files} • Size: {size}',
      'exportLocation':
          'Files › On My iPhone › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          'Use Share to copy the archive to iCloud Drive, AirDrop or another app.',
      'exportSkipped': 'Skipped folders (not valid saves): {count}',
      'exportOtherUsers':
          'Other RPCS3 user folders also contain saves ({users}), but the Core only uses user 00000001; they were not exported.',
      'importTitle': 'Game saves import',
      'importLocation':
          'Source: Files › On My iPhone › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': 'Source: {name}',
      'importDestination':
          'RPCS3 reads these saves from RewindBox’s private RPCS3 folder. They appear in RPCS3 without any further step.',
      'countImported': 'Imported: {count}',
      'countReplaced': 'Replaced: {count}',
      'countAlreadyPresent': 'Already present: {count}',
      'countKept': 'Kept: {count}',
      'countRejected': 'Rejected: {count}',
      'statusImported': 'Imported',
      'statusReplaced': 'Replaced',
      'statusAlreadyPresent': 'Already present',
      'statusKept': 'Existing save kept',
      'statusRejected': 'Rejected',
      'itemSize': '{files} file(s), {size}',
      'backupKept':
          'The previous save folder was moved to RewindBox’s private backup folder (RPCS3 › SaveBackups).',
      'reasonInvalidName':
          'The folder name is not a valid RPCS3 save directory: 1 to 32 letters, digits, "_" or "-".',
      'reasonInvalidParamSfo':
          'PARAM.SFO is missing or is not a valid PS3 save descriptor.',
      'reasonDuplicate':
          'The same save directory appears earlier in this selection. Only the first one was used.',
      'reasonConflictKept':
          'A save with this name and different content is already present. It was kept.',
      'reasonStorageRedirected':
          'RPCS3 storage (dev_hdd0) is redirected by Data/vfs.yml. RewindBox only handles saves in its own RPCS3 folder.',
      'reasonUnsafeEntry':
          'The archive contains a path that could leave the destination folder (absolute path, "..", backslash or empty name).',
      'reasonSymbolicLink': 'Symbolic links are not accepted in a save.',
      'reasonTooManyEntries': 'More than {max} entries.',
      'reasonTooLarge': 'More than {max} in total.',
      'reasonFileTooLarge': 'A single file exceeds {max}.',
      'reasonInvalidArchive': 'The file is not a readable ZIP archive.',
      'reasonNoSave':
          'No folder containing a PARAM.SFO file was found in this source.',
      'reasonUnreadable':
          'The source could not be read. If it is in iCloud Drive or another provider, download it in the Files app and try again.',
      'reasonWriteFailed': 'RewindBox could not write this save.',
      'reasonCorruptData':
          'The extracted data does not match the archive (size or checksum).',
      'failNoSaves': 'RPCS3 has no game save to export.',
      'failNothingFound':
          'No save folder or ZIP archive was found in Files › On My iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'failNotZip': 'The selected file is not a .zip archive.',
      'failExportWrite': 'The export archive could not be written.',
      'failed': 'The operation did not complete.',
      'busyGameRunning':
          'A PS3 game is running. Close it first: RPCS3 may be writing a save.',
      'busyLibrary':
          'Another RPCS3 operation is in progress. Wait until it finishes, then try again.',
      'statusExporting': 'Exporting RPCS3 game saves…',
      'statusImporting': 'Importing RPCS3 game saves…',
      'errorTitle': 'Game saves',
    },
    'es': {
      'importSourceTitle': 'Importar partidas guardadas',
      'importSourceBody':
          'Elige de dónde proceden las partidas guardadas. Una partida guardada es una carpeta con un archivo PARAM.SFO, sola o dentro de un archivo ZIP.',
      'sourceFilesFolder': 'Carpeta de Archivos de RewindBox',
      'sourceFilesFolderHint':
          'Carpetas de partidas guardadas o archivos ZIP colocados en Archivos › En mi iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'sourceZip': 'Elegir un archivo ZIP…',
      'sourceZipHint':
          'Un archivo exportado por RewindBox o por RPCS3 en otro dispositivo.',
      'sourceFolder': 'Elegir una carpeta de partida guardada…',
      'sourceFolderHint':
          'Una carpeta de partida guardada o una carpeta que contenga varias.',
      'cancel': 'Cancelar',
      'close': 'Cerrar',
      'share': 'Compartir…',
      'replace': 'Reemplazar',
      'keepExisting': 'Conservar la existente',
      'replaceTitle': '¿Reemplazar las partidas guardadas existentes?',
      'replaceBody':
          'Partidas guardadas ya presentes en RPCS3 con contenido distinto: {count}. Si las reemplazas, las carpetas actuales se mueven a una copia de seguridad fuera de RPCS3 antes de instalar las nuevas.',
      'exportTitle': 'Partidas guardadas exportadas',
      'exportSummary':
          'Partidas guardadas: {saves} • Archivos: {files} • Tamaño: {size}',
      'exportLocation':
          'Archivos › En mi iPhone › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          'Usa Compartir para copiar el archivo a iCloud Drive, AirDrop u otra app.',
      'exportSkipped':
          'Carpetas omitidas (no son partidas guardadas válidas): {count}',
      'exportOtherUsers':
          'Otras carpetas de usuario de RPCS3 también contienen partidas guardadas ({users}), pero el Core solo usa el usuario 00000001; no se exportaron.',
      'importTitle': 'Importación de partidas guardadas',
      'importLocation':
          'Origen: Archivos › En mi iPhone › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': 'Origen: {name}',
      'importDestination':
          'RPCS3 lee estas partidas guardadas desde la carpeta RPCS3 privada de RewindBox. Aparecen en RPCS3 sin ningún paso adicional.',
      'countImported': 'Importadas: {count}',
      'countReplaced': 'Reemplazadas: {count}',
      'countAlreadyPresent': 'Ya presentes: {count}',
      'countKept': 'Conservadas: {count}',
      'countRejected': 'Rechazadas: {count}',
      'statusImported': 'Importada',
      'statusReplaced': 'Reemplazada',
      'statusAlreadyPresent': 'Ya presente',
      'statusKept': 'Partida existente conservada',
      'statusRejected': 'Rechazada',
      'itemSize': '{files} archivo(s), {size}',
      'backupKept':
          'La carpeta anterior se movió a la carpeta de copias de seguridad privada de RewindBox (RPCS3 › SaveBackups).',
      'reasonInvalidName':
          'El nombre de la carpeta no es un directorio de partida guardada de RPCS3 válido: de 1 a 32 letras, dígitos, «_» o «-».',
      'reasonInvalidParamSfo':
          'Falta PARAM.SFO o no es un descriptor de partida guardada de PS3 válido.',
      'reasonDuplicate':
          'El mismo directorio de partida guardada aparece antes en esta selección. Solo se usó el primero.',
      'reasonConflictKept':
          'Ya hay una partida guardada con este nombre y contenido distinto. Se ha conservado.',
      'reasonStorageRedirected':
          'El almacenamiento de RPCS3 (dev_hdd0) está redirigido por Data/vfs.yml. RewindBox solo gestiona partidas guardadas en su propia carpeta de RPCS3.',
      'reasonUnsafeEntry':
          'El archivo contiene una ruta que podría salir de la carpeta de destino (ruta absoluta, «..», barra invertida o nombre vacío).',
      'reasonSymbolicLink':
          'No se aceptan enlaces simbólicos en una partida guardada.',
      'reasonTooManyEntries': 'Más de {max} entradas.',
      'reasonTooLarge': 'Más de {max} en total.',
      'reasonFileTooLarge': 'Un solo archivo supera {max}.',
      'reasonInvalidArchive': 'El archivo no es un ZIP legible.',
      'reasonNoSave':
          'No se encontró ninguna carpeta con un archivo PARAM.SFO en este origen.',
      'reasonUnreadable':
          'No se pudo leer el origen. Si está en iCloud Drive o en otro proveedor, descárgalo en la app Archivos y vuelve a intentarlo.',
      'reasonWriteFailed':
          'RewindBox no pudo escribir esta partida guardada.',
      'reasonCorruptData':
          'Los datos extraídos no coinciden con el archivo (tamaño o suma de verificación).',
      'failNoSaves': 'RPCS3 no tiene ninguna partida guardada que exportar.',
      'failNothingFound':
          'No se encontró ninguna carpeta de partida guardada ni archivo ZIP en Archivos › En mi iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'failNotZip': 'El archivo seleccionado no es un .zip.',
      'failExportWrite': 'No se pudo escribir el archivo de exportación.',
      'failed': 'La operación no se completó.',
      'busyGameRunning':
          'Hay un juego de PS3 en ejecución. Ciérralo primero: puede que RPCS3 esté escribiendo una partida guardada.',
      'busyLibrary':
          'Hay otra operación de RPCS3 en curso. Espera a que termine y vuelve a intentarlo.',
      'statusExporting': 'Exportando partidas guardadas de RPCS3…',
      'statusImporting': 'Importando partidas guardadas de RPCS3…',
      'errorTitle': 'Partidas guardadas',
    },
    'ru': {
      'importSourceTitle': 'Импорт сохранений',
      'importSourceBody':
          'Выберите, откуда взять сохранения. Сохранение — это папка с файлом PARAM.SFO, отдельная или внутри ZIP-архива.',
      'sourceFilesFolder': 'Папка RewindBox в приложении «Файлы»',
      'sourceFilesFolderHint':
          'Папки сохранений или ZIP-архивы, помещённые в Файлы › На iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'sourceZip': 'Выбрать ZIP-архив…',
      'sourceZipHint':
          'Архив, экспортированный RewindBox или RPCS3 на другом устройстве.',
      'sourceFolder': 'Выбрать папку сохранения…',
      'sourceFolderHint':
          'Папка сохранения или папка, содержащая несколько сохранений.',
      'cancel': 'Отмена',
      'close': 'Закрыть',
      'share': 'Поделиться…',
      'replace': 'Заменить',
      'keepExisting': 'Оставить существующее',
      'replaceTitle': 'Заменить существующие сохранения?',
      'replaceBody':
          'Сохранений, уже имеющихся в RPCS3 с другим содержимым: {count}. При замене текущие папки сначала перемещаются в резервную копию вне RPCS3, затем устанавливаются новые.',
      'exportTitle': 'Сохранения экспортированы',
      'exportSummary': 'Сохранений: {saves} • Файлов: {files} • Размер: {size}',
      'exportLocation':
          'Файлы › На iPhone › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          'Нажмите «Поделиться», чтобы скопировать архив в iCloud Drive, передать по AirDrop или в другое приложение.',
      'exportSkipped': 'Пропущено папок (не являются сохранениями): {count}',
      'exportOtherUsers':
          'В других папках пользователей RPCS3 тоже есть сохранения ({users}), но Core использует только пользователя 00000001; они не экспортированы.',
      'importTitle': 'Результат импорта сохранений',
      'importLocation':
          'Источник: Файлы › На iPhone › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': 'Источник: {name}',
      'importDestination':
          'RPCS3 читает эти сохранения из закрытой папки RPCS3 внутри RewindBox. Они появляются в RPCS3 без дополнительных действий.',
      'countImported': 'Импортировано: {count}',
      'countReplaced': 'Заменено: {count}',
      'countAlreadyPresent': 'Уже есть: {count}',
      'countKept': 'Оставлено: {count}',
      'countRejected': 'Отклонено: {count}',
      'statusImported': 'Импортировано',
      'statusReplaced': 'Заменено',
      'statusAlreadyPresent': 'Уже есть',
      'statusKept': 'Существующее сохранение оставлено',
      'statusRejected': 'Отклонено',
      'itemSize': 'Файлов: {files}, {size}',
      'backupKept':
          'Прежняя папка сохранения перемещена в закрытую папку резервных копий RewindBox (RPCS3 › SaveBackups).',
      'reasonInvalidName':
          'Имя папки не является допустимым каталогом сохранения RPCS3: от 1 до 32 букв, цифр, «_» или «-».',
      'reasonInvalidParamSfo':
          'Файл PARAM.SFO отсутствует или не является корректным описанием сохранения PS3.',
      'reasonDuplicate':
          'Тот же каталог сохранения встречается в этом наборе раньше. Использован только первый.',
      'reasonConflictKept':
          'Сохранение с таким именем и другим содержимым уже есть. Оно оставлено.',
      'reasonStorageRedirected':
          'Хранилище RPCS3 (dev_hdd0) перенаправлено файлом Data/vfs.yml. RewindBox работает с сохранениями только в собственной папке RPCS3.',
      'reasonUnsafeEntry':
          'Архив содержит путь, который может выйти за пределы папки назначения (абсолютный путь, «..», обратная косая черта или пустое имя).',
      'reasonSymbolicLink': 'Символические ссылки в сохранении не допускаются.',
      'reasonTooManyEntries': 'Больше {max} элементов.',
      'reasonTooLarge': 'Больше {max} в сумме.',
      'reasonFileTooLarge': 'Один файл превышает {max}.',
      'reasonInvalidArchive': 'Файл не является читаемым ZIP-архивом.',
      'reasonNoSave':
          'В этом источнике не найдено ни одной папки с файлом PARAM.SFO.',
      'reasonUnreadable':
          'Не удалось прочитать источник. Если он находится в iCloud Drive или у другого поставщика, загрузите его в приложении «Файлы» и повторите попытку.',
      'reasonWriteFailed': 'RewindBox не удалось записать это сохранение.',
      'reasonCorruptData':
          'Извлечённые данные не соответствуют архиву (размер или контрольная сумма).',
      'failNoSaves': 'В RPCS3 нет сохранений для экспорта.',
      'failNothingFound':
          'В Файлы › На iPhone › RewindBox › RPCS3 › Import › Game Saves не найдено ни папки сохранения, ни ZIP-архива.',
      'failNotZip': 'Выбранный файл не является архивом .zip.',
      'failExportWrite': 'Не удалось записать архив экспорта.',
      'failed': 'Операция не была завершена.',
      'busyGameRunning':
          'Запущена игра PS3. Сначала закройте её: RPCS3 может записывать сохранение.',
      'busyLibrary':
          'Выполняется другая операция RPCS3. Дождитесь её завершения и повторите попытку.',
      'statusExporting': 'Экспорт сохранений RPCS3…',
      'statusImporting': 'Импорт сохранений RPCS3…',
      'errorTitle': 'Сохранения',
    },
    'zh': {
      'importSourceTitle': '导入游戏存档',
      'importSourceBody':
          '选择存档的来源。存档是一个包含 PARAM.SFO 文件的文件夹，可以单独存在，也可以位于 ZIP 压缩包内。',
      'sourceFilesFolder': 'RewindBox 的“文件”文件夹',
      'sourceFilesFolderHint':
          '放在 文件 › 我的 iPhone › RewindBox › RPCS3 › Import › Game Saves 中的存档文件夹或 ZIP 压缩包。',
      'sourceZip': '选择 ZIP 压缩包…',
      'sourceZipHint': '由另一台设备上的 RewindBox 或 RPCS3 导出的压缩包。',
      'sourceFolder': '选择存档文件夹…',
      'sourceFolderHint': '一个存档文件夹，或包含多个存档的文件夹。',
      'cancel': '取消',
      'close': '关闭',
      'share': '共享…',
      'replace': '替换',
      'keepExisting': '保留现有存档',
      'replaceTitle': '替换现有存档？',
      'replaceBody':
          'RPCS3 中已存在且内容不同的存档：{count} 个。如果替换，当前文件夹会先移动到 RPCS3 之外的备份位置，然后再安装新存档。',
      'exportTitle': '游戏存档已导出',
      'exportSummary': '存档：{saves} • 文件：{files} • 大小：{size}',
      'exportLocation':
          '文件 › 我的 iPhone › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          '使用“共享”可将压缩包复制到 iCloud 云盘、通过隔空投送发送或发送到其他 App。',
      'exportSkipped': '已跳过的文件夹（不是有效存档）：{count}',
      'exportOtherUsers':
          '其他 RPCS3 用户文件夹（{users}）中也有存档，但 Core 只使用用户 00000001，因此未导出。',
      'importTitle': '游戏存档导入结果',
      'importLocation':
          '来源：文件 › 我的 iPhone › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': '来源：{name}',
      'importDestination':
          'RPCS3 从 RewindBox 的私有 RPCS3 文件夹读取这些存档。无需任何额外步骤即可在 RPCS3 中显示。',
      'countImported': '已导入：{count}',
      'countReplaced': '已替换：{count}',
      'countAlreadyPresent': '已存在：{count}',
      'countKept': '已保留：{count}',
      'countRejected': '已拒绝：{count}',
      'statusImported': '已导入',
      'statusReplaced': '已替换',
      'statusAlreadyPresent': '已存在',
      'statusKept': '已保留现有存档',
      'statusRejected': '已拒绝',
      'itemSize': '{files} 个文件，{size}',
      'backupKept':
          '原存档文件夹已移动到 RewindBox 的私有备份文件夹（RPCS3 › SaveBackups）。',
      'reasonInvalidName':
          '文件夹名称不是有效的 RPCS3 存档目录：1 到 32 个字母、数字、“_”或“-”。',
      'reasonInvalidParamSfo': '缺少 PARAM.SFO，或它不是有效的 PS3 存档描述文件。',
      'reasonDuplicate': '同一存档目录在此选择中已先出现。仅使用了第一个。',
      'reasonConflictKept': '已存在同名但内容不同的存档，已保留原存档。',
      'reasonStorageRedirected':
          'RPCS3 存储（dev_hdd0）已被 Data/vfs.yml 重定向。RewindBox 只处理其自身 RPCS3 文件夹中的存档。',
      'reasonUnsafeEntry':
          '压缩包中包含可能超出目标文件夹的路径（绝对路径、“..”、反斜杠或空名称）。',
      'reasonSymbolicLink': '存档中不接受符号链接。',
      'reasonTooManyEntries': '条目超过 {max} 个。',
      'reasonTooLarge': '总大小超过 {max}。',
      'reasonFileTooLarge': '单个文件超过 {max}。',
      'reasonInvalidArchive': '该文件不是可读取的 ZIP 压缩包。',
      'reasonNoSave': '在此来源中未找到包含 PARAM.SFO 文件的文件夹。',
      'reasonUnreadable':
          '无法读取来源。如果它位于 iCloud 云盘或其他提供方中，请先在“文件”App 中下载，然后重试。',
      'reasonWriteFailed': 'RewindBox 无法写入此存档。',
      'reasonCorruptData': '解压的数据与压缩包不一致（大小或校验和）。',
      'failNoSaves': 'RPCS3 没有可导出的游戏存档。',
      'failNothingFound':
          '在 文件 › 我的 iPhone › RewindBox › RPCS3 › Import › Game Saves 中未找到存档文件夹或 ZIP 压缩包。',
      'failNotZip': '所选文件不是 .zip 压缩包。',
      'failExportWrite': '无法写入导出的压缩包。',
      'failed': '操作未完成。',
      'busyGameRunning': '有 PS3 游戏正在运行。请先关闭它：RPCS3 可能正在写入存档。',
      'busyLibrary': '另一个 RPCS3 操作正在进行。请等待其完成后再试。',
      'statusExporting': '正在导出 RPCS3 游戏存档…',
      'statusImporting': '正在导入 RPCS3 游戏存档…',
      'errorTitle': '游戏存档',
    },
    'zh_Hant': {
      'importSourceTitle': '匯入遊戲存檔',
      'importSourceBody':
          '選擇存檔的來源。存檔是一個包含 PARAM.SFO 檔案的資料夾，可以單獨存在，也可以位於 ZIP 壓縮檔內。',
      'sourceFilesFolder': 'RewindBox 的「檔案」資料夾',
      'sourceFilesFolderHint':
          '放在 檔案 › 我的 iPhone › RewindBox › RPCS3 › Import › Game Saves 中的存檔資料夾或 ZIP 壓縮檔。',
      'sourceZip': '選擇 ZIP 壓縮檔…',
      'sourceZipHint': '由另一台裝置上的 RewindBox 或 RPCS3 匯出的壓縮檔。',
      'sourceFolder': '選擇存檔資料夾…',
      'sourceFolderHint': '一個存檔資料夾，或包含多個存檔的資料夾。',
      'cancel': '取消',
      'close': '關閉',
      'share': '分享…',
      'replace': '取代',
      'keepExisting': '保留現有存檔',
      'replaceTitle': '要取代現有存檔嗎？',
      'replaceBody':
          'RPCS3 中已存在且內容不同的存檔：{count} 個。若取代，目前的資料夾會先移到 RPCS3 之外的備份位置，再安裝新存檔。',
      'exportTitle': '遊戲存檔已匯出',
      'exportSummary': '存檔：{saves} • 檔案：{files} • 大小：{size}',
      'exportLocation':
          '檔案 › 我的 iPhone › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          '使用「分享」可將壓縮檔複製到 iCloud 雲碟、透過 AirDrop 傳送或傳到其他 App。',
      'exportSkipped': '已略過的資料夾（不是有效存檔）：{count}',
      'exportOtherUsers':
          '其他 RPCS3 使用者資料夾（{users}）中也有存檔，但 Core 只使用使用者 00000001，因此未匯出。',
      'importTitle': '遊戲存檔匯入結果',
      'importLocation':
          '來源：檔案 › 我的 iPhone › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': '來源：{name}',
      'importDestination':
          'RPCS3 會從 RewindBox 的私有 RPCS3 資料夾讀取這些存檔。無需任何額外步驟即可在 RPCS3 中顯示。',
      'countImported': '已匯入：{count}',
      'countReplaced': '已取代：{count}',
      'countAlreadyPresent': '已存在：{count}',
      'countKept': '已保留：{count}',
      'countRejected': '已拒絕：{count}',
      'statusImported': '已匯入',
      'statusReplaced': '已取代',
      'statusAlreadyPresent': '已存在',
      'statusKept': '已保留現有存檔',
      'statusRejected': '已拒絕',
      'itemSize': '{files} 個檔案，{size}',
      'backupKept':
          '原存檔資料夾已移到 RewindBox 的私有備份資料夾（RPCS3 › SaveBackups）。',
      'reasonInvalidName':
          '資料夾名稱不是有效的 RPCS3 存檔目錄：1 到 32 個字母、數字、「_」或「-」。',
      'reasonInvalidParamSfo': '缺少 PARAM.SFO，或它不是有效的 PS3 存檔描述檔。',
      'reasonDuplicate': '同一存檔目錄已在此選擇中先出現。只使用了第一個。',
      'reasonConflictKept': '已存在同名但內容不同的存檔，已保留原存檔。',
      'reasonStorageRedirected':
          'RPCS3 儲存空間（dev_hdd0）已被 Data/vfs.yml 重新導向。RewindBox 只處理其自身 RPCS3 資料夾中的存檔。',
      'reasonUnsafeEntry':
          '壓縮檔中包含可能超出目標資料夾的路徑（絕對路徑、「..」、反斜線或空名稱）。',
      'reasonSymbolicLink': '存檔中不接受符號連結。',
      'reasonTooManyEntries': '項目超過 {max} 個。',
      'reasonTooLarge': '總大小超過 {max}。',
      'reasonFileTooLarge': '單一檔案超過 {max}。',
      'reasonInvalidArchive': '該檔案不是可讀取的 ZIP 壓縮檔。',
      'reasonNoSave': '在此來源中找不到包含 PARAM.SFO 檔案的資料夾。',
      'reasonUnreadable':
          '無法讀取來源。如果它位於 iCloud 雲碟或其他提供者中，請先在「檔案」App 中下載，然後重試。',
      'reasonWriteFailed': 'RewindBox 無法寫入此存檔。',
      'reasonCorruptData': '解壓縮的資料與壓縮檔不一致（大小或總和檢查碼）。',
      'failNoSaves': 'RPCS3 沒有可匯出的遊戲存檔。',
      'failNothingFound':
          '在 檔案 › 我的 iPhone › RewindBox › RPCS3 › Import › Game Saves 中找不到存檔資料夾或 ZIP 壓縮檔。',
      'failNotZip': '所選檔案不是 .zip 壓縮檔。',
      'failExportWrite': '無法寫入匯出的壓縮檔。',
      'failed': '操作未完成。',
      'busyGameRunning': '有 PS3 遊戲正在執行。請先關閉它：RPCS3 可能正在寫入存檔。',
      'busyLibrary': '另一個 RPCS3 操作正在進行。請等待其完成後再試。',
      'statusExporting': '正在匯出 RPCS3 遊戲存檔…',
      'statusImporting': '正在匯入 RPCS3 遊戲存檔…',
      'errorTitle': '遊戲存檔',
    },
    'pt': {
      'importSourceTitle': 'Importar gravações de jogo',
      'importSourceBody':
          'Escolha de onde vêm as gravações. Uma gravação é uma pasta com um ficheiro PARAM.SFO, sozinha ou dentro de um arquivo ZIP.',
      'sourceFilesFolder': 'Pasta Ficheiros do RewindBox',
      'sourceFilesFolderHint':
          'Pastas de gravação ou arquivos ZIP colocados em Ficheiros › No meu iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'sourceZip': 'Escolher um arquivo ZIP…',
      'sourceZipHint':
          'Um arquivo exportado pelo RewindBox ou pelo RPCS3 noutro dispositivo.',
      'sourceFolder': 'Escolher uma pasta de gravação…',
      'sourceFolderHint':
          'Uma pasta de gravação ou uma pasta que contenha várias.',
      'cancel': 'Cancelar',
      'close': 'Fechar',
      'share': 'Partilhar…',
      'replace': 'Substituir',
      'keepExisting': 'Manter a existente',
      'replaceTitle': 'Substituir as gravações existentes?',
      'replaceBody':
          'Gravações já presentes no RPCS3 com conteúdo diferente: {count}. Se as substituir, as pastas atuais são movidas para uma cópia de segurança fora do RPCS3 antes de instalar as novas.',
      'exportTitle': 'Gravações de jogo exportadas',
      'exportSummary': 'Gravações: {saves} • Ficheiros: {files} • Tamanho: {size}',
      'exportLocation':
          'Ficheiros › No meu iPhone › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          'Use Partilhar para copiar o arquivo para o iCloud Drive, por AirDrop ou para outra app.',
      'exportSkipped': 'Pastas ignoradas (não são gravações válidas): {count}',
      'exportOtherUsers':
          'Outras pastas de utilizador do RPCS3 também contêm gravações ({users}), mas o Core só usa o utilizador 00000001; não foram exportadas.',
      'importTitle': 'Importação de gravações de jogo',
      'importLocation':
          'Origem: Ficheiros › No meu iPhone › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': 'Origem: {name}',
      'importDestination':
          'O RPCS3 lê estas gravações na pasta RPCS3 privada do RewindBox. Aparecem no RPCS3 sem qualquer passo adicional.',
      'countImported': 'Importadas: {count}',
      'countReplaced': 'Substituídas: {count}',
      'countAlreadyPresent': 'Já presentes: {count}',
      'countKept': 'Mantidas: {count}',
      'countRejected': 'Recusadas: {count}',
      'statusImported': 'Importada',
      'statusReplaced': 'Substituída',
      'statusAlreadyPresent': 'Já presente',
      'statusKept': 'Gravação existente mantida',
      'statusRejected': 'Recusada',
      'itemSize': '{files} ficheiro(s), {size}',
      'backupKept':
          'A pasta de gravação anterior foi movida para a pasta de cópias de segurança privada do RewindBox (RPCS3 › SaveBackups).',
      'reasonInvalidName':
          'O nome da pasta não é um diretório de gravação RPCS3 válido: 1 a 32 letras, dígitos, «_» ou «-».',
      'reasonInvalidParamSfo':
          'O PARAM.SFO está em falta ou não é um descritor de gravação PS3 válido.',
      'reasonDuplicate':
          'O mesmo diretório de gravação aparece antes nesta seleção. Só o primeiro foi usado.',
      'reasonConflictKept':
          'Já existe uma gravação com este nome e conteúdo diferente. Foi mantida.',
      'reasonStorageRedirected':
          'O armazenamento do RPCS3 (dev_hdd0) está redirecionado por Data/vfs.yml. O RewindBox só gere gravações na sua própria pasta do RPCS3.',
      'reasonUnsafeEntry':
          'O arquivo contém um caminho que poderia sair da pasta de destino (caminho absoluto, «..», barra invertida ou nome vazio).',
      'reasonSymbolicLink':
          'Não são aceites ligações simbólicas numa gravação.',
      'reasonTooManyEntries': 'Mais de {max} entradas.',
      'reasonTooLarge': 'Mais de {max} no total.',
      'reasonFileTooLarge': 'Um único ficheiro excede {max}.',
      'reasonInvalidArchive': 'O ficheiro não é um arquivo ZIP legível.',
      'reasonNoSave':
          'Não foi encontrada nenhuma pasta com um ficheiro PARAM.SFO nesta origem.',
      'reasonUnreadable':
          'Não foi possível ler a origem. Se estiver no iCloud Drive ou noutro fornecedor, transfira-a na app Ficheiros e tente novamente.',
      'reasonWriteFailed': 'O RewindBox não conseguiu gravar esta gravação.',
      'reasonCorruptData':
          'Os dados extraídos não correspondem ao arquivo (tamanho ou soma de verificação).',
      'failNoSaves': 'O RPCS3 não tem nenhuma gravação de jogo para exportar.',
      'failNothingFound':
          'Não foi encontrada nenhuma pasta de gravação nem arquivo ZIP em Ficheiros › No meu iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'failNotZip': 'O ficheiro selecionado não é um arquivo .zip.',
      'failExportWrite': 'Não foi possível escrever o arquivo de exportação.',
      'failed': 'A operação não foi concluída.',
      'busyGameRunning':
          'Há um jogo PS3 em execução. Feche-o primeiro: o RPCS3 pode estar a gravar uma gravação.',
      'busyLibrary':
          'Outra operação do RPCS3 está em curso. Aguarde que termine e tente novamente.',
      'statusExporting': 'A exportar gravações de jogo do RPCS3…',
      'statusImporting': 'A importar gravações de jogo do RPCS3…',
      'errorTitle': 'Gravações de jogo',
    },
    'fr': {
      'importSourceTitle': 'Importer des sauvegardes',
      'importSourceBody':
          'Choisissez la provenance des sauvegardes. Une sauvegarde est un dossier contenant un fichier PARAM.SFO, seul ou dans une archive ZIP.',
      'sourceFilesFolder': 'Dossier Fichiers de RewindBox',
      'sourceFilesFolderHint':
          'Dossiers de sauvegarde ou archives ZIP déposés dans Fichiers › Sur mon iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'sourceZip': 'Choisir une archive ZIP…',
      'sourceZipHint':
          'Une archive exportée par RewindBox ou par RPCS3 sur un autre appareil.',
      'sourceFolder': 'Choisir un dossier de sauvegarde…',
      'sourceFolderHint':
          'Un dossier de sauvegarde, ou un dossier qui en contient plusieurs.',
      'cancel': 'Annuler',
      'close': 'Fermer',
      'share': 'Partager…',
      'replace': 'Remplacer',
      'keepExisting': 'Conserver l’existante',
      'replaceTitle': 'Remplacer les sauvegardes existantes ?',
      'replaceBody':
          'Sauvegardes déjà présentes dans RPCS3 avec un contenu différent : {count}. Si vous les remplacez, les dossiers actuels sont déplacés dans une copie de secours hors de RPCS3 avant l’installation des nouveaux.',
      'exportTitle': 'Sauvegardes exportées',
      'exportSummary': 'Sauvegardes : {saves} • Fichiers : {files} • Taille : {size}',
      'exportLocation':
          'Fichiers › Sur mon iPhone › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          'Utilisez Partager pour copier l’archive vers iCloud Drive, AirDrop ou une autre app.',
      'exportSkipped': 'Dossiers ignorés (sauvegardes non valides) : {count}',
      'exportOtherUsers':
          'D’autres dossiers d’utilisateur RPCS3 contiennent aussi des sauvegardes ({users}), mais le Core n’utilise que l’utilisateur 00000001 ; elles n’ont pas été exportées.',
      'importTitle': 'Import des sauvegardes',
      'importLocation':
          'Source : Fichiers › Sur mon iPhone › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': 'Source : {name}',
      'importDestination':
          'RPCS3 lit ces sauvegardes dans le dossier RPCS3 privé de RewindBox. Elles apparaissent dans RPCS3 sans autre étape.',
      'countImported': 'Importées : {count}',
      'countReplaced': 'Remplacées : {count}',
      'countAlreadyPresent': 'Déjà présentes : {count}',
      'countKept': 'Conservées : {count}',
      'countRejected': 'Refusées : {count}',
      'statusImported': 'Importée',
      'statusReplaced': 'Remplacée',
      'statusAlreadyPresent': 'Déjà présente',
      'statusKept': 'Sauvegarde existante conservée',
      'statusRejected': 'Refusée',
      'itemSize': '{files} fichier(s), {size}',
      'backupKept':
          'L’ancien dossier de sauvegarde a été déplacé dans le dossier de secours privé de RewindBox (RPCS3 › SaveBackups).',
      'reasonInvalidName':
          'Le nom du dossier n’est pas un répertoire de sauvegarde RPCS3 valide : 1 à 32 lettres, chiffres, « _ » ou « - ».',
      'reasonInvalidParamSfo':
          'PARAM.SFO est absent ou n’est pas un descripteur de sauvegarde PS3 valide.',
      'reasonDuplicate':
          'Le même répertoire de sauvegarde apparaît plus tôt dans cette sélection. Seul le premier a été utilisé.',
      'reasonConflictKept':
          'Une sauvegarde de ce nom avec un contenu différent est déjà présente. Elle a été conservée.',
      'reasonStorageRedirected':
          'Le stockage RPCS3 (dev_hdd0) est redirigé par Data/vfs.yml. RewindBox ne gère les sauvegardes que dans son propre dossier RPCS3.',
      'reasonUnsafeEntry':
          'L’archive contient un chemin qui pourrait sortir du dossier de destination (chemin absolu, « .. », barre oblique inverse ou nom vide).',
      'reasonSymbolicLink':
          'Les liens symboliques ne sont pas acceptés dans une sauvegarde.',
      'reasonTooManyEntries': 'Plus de {max} entrées.',
      'reasonTooLarge': 'Plus de {max} au total.',
      'reasonFileTooLarge': 'Un seul fichier dépasse {max}.',
      'reasonInvalidArchive': 'Le fichier n’est pas une archive ZIP lisible.',
      'reasonNoSave':
          'Aucun dossier contenant un fichier PARAM.SFO n’a été trouvé dans cette source.',
      'reasonUnreadable':
          'La source n’a pas pu être lue. Si elle est dans iCloud Drive ou chez un autre fournisseur, téléchargez-la dans l’app Fichiers et réessayez.',
      'reasonWriteFailed': 'RewindBox n’a pas pu écrire cette sauvegarde.',
      'reasonCorruptData':
          'Les données extraites ne correspondent pas à l’archive (taille ou somme de contrôle).',
      'failNoSaves': 'RPCS3 n’a aucune sauvegarde de jeu à exporter.',
      'failNothingFound':
          'Aucun dossier de sauvegarde ni archive ZIP trouvé dans Fichiers › Sur mon iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'failNotZip': 'Le fichier sélectionné n’est pas une archive .zip.',
      'failExportWrite': 'L’archive d’export n’a pas pu être écrite.',
      'failed': 'L’opération ne s’est pas terminée.',
      'busyGameRunning':
          'Un jeu PS3 est en cours. Fermez-le d’abord : RPCS3 est peut-être en train d’écrire une sauvegarde.',
      'busyLibrary':
          'Une autre opération RPCS3 est en cours. Attendez qu’elle se termine, puis réessayez.',
      'statusExporting': 'Export des sauvegardes RPCS3…',
      'statusImporting': 'Import des sauvegardes RPCS3…',
      'errorTitle': 'Sauvegardes de jeu',
    },
    'de': {
      'importSourceTitle': 'Spielstände importieren',
      'importSourceBody':
          'Wählen Sie, woher die Spielstände kommen. Ein Spielstand ist ein Ordner mit einer PARAM.SFO-Datei, allein oder in einem ZIP-Archiv.',
      'sourceFilesFolder': 'Dateien-Ordner von RewindBox',
      'sourceFilesFolderHint':
          'Spielstand-Ordner oder ZIP-Archive, die unter Dateien › Auf meinem iPhone › RewindBox › RPCS3 › Import › Game Saves abgelegt wurden.',
      'sourceZip': 'ZIP-Archiv auswählen…',
      'sourceZipHint':
          'Ein Archiv, das RewindBox oder RPCS3 auf einem anderen Gerät exportiert hat.',
      'sourceFolder': 'Spielstand-Ordner auswählen…',
      'sourceFolderHint':
          'Ein Spielstand-Ordner oder ein Ordner mit mehreren Spielständen.',
      'cancel': 'Abbrechen',
      'close': 'Schließen',
      'share': 'Teilen…',
      'replace': 'Ersetzen',
      'keepExisting': 'Vorhandenen behalten',
      'replaceTitle': 'Vorhandene Spielstände ersetzen?',
      'replaceBody':
          'In RPCS3 bereits vorhandene Spielstände mit anderem Inhalt: {count}. Beim Ersetzen werden die aktuellen Ordner vor der Installation der neuen in eine Sicherung außerhalb von RPCS3 verschoben.',
      'exportTitle': 'Spielstände exportiert',
      'exportSummary': 'Spielstände: {saves} • Dateien: {files} • Größe: {size}',
      'exportLocation':
          'Dateien › Auf meinem iPhone › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          'Mit „Teilen“ kopieren Sie das Archiv nach iCloud Drive, per AirDrop oder in eine andere App.',
      'exportSkipped': 'Übersprungene Ordner (keine gültigen Spielstände): {count}',
      'exportOtherUsers':
          'Andere RPCS3-Benutzerordner enthalten ebenfalls Spielstände ({users}), der Core verwendet jedoch nur den Benutzer 00000001; sie wurden nicht exportiert.',
      'importTitle': 'Import der Spielstände',
      'importLocation':
          'Quelle: Dateien › Auf meinem iPhone › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': 'Quelle: {name}',
      'importDestination':
          'RPCS3 liest diese Spielstände aus dem privaten RPCS3-Ordner von RewindBox. Sie erscheinen in RPCS3 ohne weiteren Schritt.',
      'countImported': 'Importiert: {count}',
      'countReplaced': 'Ersetzt: {count}',
      'countAlreadyPresent': 'Bereits vorhanden: {count}',
      'countKept': 'Behalten: {count}',
      'countRejected': 'Abgelehnt: {count}',
      'statusImported': 'Importiert',
      'statusReplaced': 'Ersetzt',
      'statusAlreadyPresent': 'Bereits vorhanden',
      'statusKept': 'Vorhandener Spielstand behalten',
      'statusRejected': 'Abgelehnt',
      'itemSize': '{files} Datei(en), {size}',
      'backupKept':
          'Der bisherige Spielstand-Ordner wurde in den privaten Sicherungsordner von RewindBox verschoben (RPCS3 › SaveBackups).',
      'reasonInvalidName':
          'Der Ordnername ist kein gültiges RPCS3-Spielstandverzeichnis: 1 bis 32 Buchstaben, Ziffern, „_“ oder „-“.',
      'reasonInvalidParamSfo':
          'PARAM.SFO fehlt oder ist kein gültiger PS3-Spielstandbeschreiber.',
      'reasonDuplicate':
          'Dasselbe Spielstandverzeichnis kommt in dieser Auswahl bereits früher vor. Nur das erste wurde verwendet.',
      'reasonConflictKept':
          'Ein Spielstand mit diesem Namen und anderem Inhalt ist bereits vorhanden. Er wurde behalten.',
      'reasonStorageRedirected':
          'Der RPCS3-Speicher (dev_hdd0) wird durch Data/vfs.yml umgeleitet. RewindBox verwaltet Spielstände nur in seinem eigenen RPCS3-Ordner.',
      'reasonUnsafeEntry':
          'Das Archiv enthält einen Pfad, der den Zielordner verlassen könnte (absoluter Pfad, „..“, Backslash oder leerer Name).',
      'reasonSymbolicLink':
          'Symbolische Links werden in einem Spielstand nicht akzeptiert.',
      'reasonTooManyEntries': 'Mehr als {max} Einträge.',
      'reasonTooLarge': 'Insgesamt mehr als {max}.',
      'reasonFileTooLarge': 'Eine einzelne Datei ist größer als {max}.',
      'reasonInvalidArchive': 'Die Datei ist kein lesbares ZIP-Archiv.',
      'reasonNoSave':
          'In dieser Quelle wurde kein Ordner mit einer PARAM.SFO-Datei gefunden.',
      'reasonUnreadable':
          'Die Quelle konnte nicht gelesen werden. Liegt sie in iCloud Drive oder bei einem anderen Anbieter, laden Sie sie in der App „Dateien“ herunter und versuchen Sie es erneut.',
      'reasonWriteFailed':
          'RewindBox konnte diesen Spielstand nicht schreiben.',
      'reasonCorruptData':
          'Die entpackten Daten stimmen nicht mit dem Archiv überein (Größe oder Prüfsumme).',
      'failNoSaves': 'RPCS3 hat keinen Spielstand zum Exportieren.',
      'failNothingFound':
          'Unter Dateien › Auf meinem iPhone › RewindBox › RPCS3 › Import › Game Saves wurde kein Spielstand-Ordner und kein ZIP-Archiv gefunden.',
      'failNotZip': 'Die ausgewählte Datei ist kein .zip-Archiv.',
      'failExportWrite': 'Das Exportarchiv konnte nicht geschrieben werden.',
      'failed': 'Der Vorgang wurde nicht abgeschlossen.',
      'busyGameRunning':
          'Ein PS3-Spiel läuft. Schließen Sie es zuerst: RPCS3 schreibt möglicherweise gerade einen Spielstand.',
      'busyLibrary':
          'Ein anderer RPCS3-Vorgang läuft. Warten Sie, bis er abgeschlossen ist, und versuchen Sie es erneut.',
      'statusExporting': 'RPCS3-Spielstände werden exportiert…',
      'statusImporting': 'RPCS3-Spielstände werden importiert…',
      'errorTitle': 'Spielstände',
    },
    'it': {
      'importSourceTitle': 'Importa salvataggi',
      'importSourceBody':
          'Scegli da dove provengono i salvataggi. Un salvataggio è una cartella con un file PARAM.SFO, da sola o dentro un archivio ZIP.',
      'sourceFilesFolder': 'Cartella File di RewindBox',
      'sourceFilesFolderHint':
          'Cartelle di salvataggio o archivi ZIP messi in File › Sul mio iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'sourceZip': 'Scegli un archivio ZIP…',
      'sourceZipHint':
          'Un archivio esportato da RewindBox o da RPCS3 su un altro dispositivo.',
      'sourceFolder': 'Scegli una cartella di salvataggio…',
      'sourceFolderHint':
          'Una cartella di salvataggio o una cartella che ne contiene diverse.',
      'cancel': 'Annulla',
      'close': 'Chiudi',
      'share': 'Condividi…',
      'replace': 'Sostituisci',
      'keepExisting': 'Mantieni esistente',
      'replaceTitle': 'Sostituire i salvataggi esistenti?',
      'replaceBody':
          'Salvataggi già presenti in RPCS3 con contenuto diverso: {count}. Se li sostituisci, le cartelle attuali vengono spostate in una copia di sicurezza fuori da RPCS3 prima di installare le nuove.',
      'exportTitle': 'Salvataggi esportati',
      'exportSummary': 'Salvataggi: {saves} • File: {files} • Dimensione: {size}',
      'exportLocation':
          'File › Sul mio iPhone › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          'Usa Condividi per copiare l’archivio su iCloud Drive, via AirDrop o in un’altra app.',
      'exportSkipped': 'Cartelle ignorate (salvataggi non validi): {count}',
      'exportOtherUsers':
          'Anche altre cartelle utente di RPCS3 contengono salvataggi ({users}), ma il Core usa solo l’utente 00000001; non sono stati esportati.',
      'importTitle': 'Importazione dei salvataggi',
      'importLocation':
          'Origine: File › Sul mio iPhone › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': 'Origine: {name}',
      'importDestination':
          'RPCS3 legge questi salvataggi dalla cartella RPCS3 privata di RewindBox. Compaiono in RPCS3 senza altri passaggi.',
      'countImported': 'Importati: {count}',
      'countReplaced': 'Sostituiti: {count}',
      'countAlreadyPresent': 'Già presenti: {count}',
      'countKept': 'Mantenuti: {count}',
      'countRejected': 'Rifiutati: {count}',
      'statusImported': 'Importato',
      'statusReplaced': 'Sostituito',
      'statusAlreadyPresent': 'Già presente',
      'statusKept': 'Salvataggio esistente mantenuto',
      'statusRejected': 'Rifiutato',
      'itemSize': '{files} file, {size}',
      'backupKept':
          'La cartella di salvataggio precedente è stata spostata nella cartella di sicurezza privata di RewindBox (RPCS3 › SaveBackups).',
      'reasonInvalidName':
          'Il nome della cartella non è una directory di salvataggio RPCS3 valida: da 1 a 32 lettere, cifre, «_» o «-».',
      'reasonInvalidParamSfo':
          'PARAM.SFO manca o non è un descrittore di salvataggio PS3 valido.',
      'reasonDuplicate':
          'La stessa directory di salvataggio compare prima in questa selezione. È stata usata solo la prima.',
      'reasonConflictKept':
          'Un salvataggio con questo nome e contenuto diverso è già presente. È stato mantenuto.',
      'reasonStorageRedirected':
          'L’archiviazione di RPCS3 (dev_hdd0) è reindirizzata da Data/vfs.yml. RewindBox gestisce i salvataggi solo nella propria cartella RPCS3.',
      'reasonUnsafeEntry':
          'L’archivio contiene un percorso che potrebbe uscire dalla cartella di destinazione (percorso assoluto, «..», barra rovesciata o nome vuoto).',
      'reasonSymbolicLink':
          'I collegamenti simbolici non sono accettati in un salvataggio.',
      'reasonTooManyEntries': 'Più di {max} voci.',
      'reasonTooLarge': 'Più di {max} in totale.',
      'reasonFileTooLarge': 'Un singolo file supera {max}.',
      'reasonInvalidArchive': 'Il file non è un archivio ZIP leggibile.',
      'reasonNoSave':
          'In questa origine non è stata trovata alcuna cartella contenente un file PARAM.SFO.',
      'reasonUnreadable':
          'Impossibile leggere l’origine. Se si trova in iCloud Drive o presso un altro provider, scaricala nell’app File e riprova.',
      'reasonWriteFailed':
          'RewindBox non è riuscito a scrivere questo salvataggio.',
      'reasonCorruptData':
          'I dati estratti non corrispondono all’archivio (dimensione o checksum).',
      'failNoSaves': 'RPCS3 non ha alcun salvataggio da esportare.',
      'failNothingFound':
          'Nessuna cartella di salvataggio né archivio ZIP trovati in File › Sul mio iPhone › RewindBox › RPCS3 › Import › Game Saves.',
      'failNotZip': 'Il file selezionato non è un archivio .zip.',
      'failExportWrite': 'Impossibile scrivere l’archivio di esportazione.',
      'failed': 'L’operazione non è stata completata.',
      'busyGameRunning':
          'Un gioco PS3 è in esecuzione. Chiudilo prima: RPCS3 potrebbe stare scrivendo un salvataggio.',
      'busyLibrary':
          'Un’altra operazione RPCS3 è in corso. Attendi che finisca, poi riprova.',
      'statusExporting': 'Esportazione dei salvataggi RPCS3…',
      'statusImporting': 'Importazione dei salvataggi RPCS3…',
      'errorTitle': 'Salvataggi',
    },
    'id': {
      'importSourceTitle': 'Impor data simpanan',
      'importSourceBody':
          'Pilih asal data simpanan. Data simpanan adalah folder berisi file PARAM.SFO, berdiri sendiri atau di dalam arsip ZIP.',
      'sourceFilesFolder': 'Folder RewindBox di app File',
      'sourceFilesFolderHint':
          'Folder simpanan atau arsip ZIP yang diletakkan di File › Di iPhone Saya › RewindBox › RPCS3 › Import › Game Saves.',
      'sourceZip': 'Pilih arsip ZIP…',
      'sourceZipHint':
          'Arsip yang diekspor oleh RewindBox atau RPCS3 di perangkat lain.',
      'sourceFolder': 'Pilih folder simpanan…',
      'sourceFolderHint':
          'Satu folder simpanan, atau folder yang berisi beberapa simpanan.',
      'cancel': 'Batal',
      'close': 'Tutup',
      'share': 'Bagikan…',
      'replace': 'Ganti',
      'keepExisting': 'Pertahankan yang ada',
      'replaceTitle': 'Ganti simpanan yang sudah ada?',
      'replaceBody':
          'Simpanan yang sudah ada di RPCS3 dengan isi berbeda: {count}. Jika diganti, folder saat ini dipindahkan ke cadangan di luar RPCS3 sebelum yang baru dipasang.',
      'exportTitle': 'Data simpanan diekspor',
      'exportSummary': 'Simpanan: {saves} • File: {files} • Ukuran: {size}',
      'exportLocation':
          'File › Di iPhone Saya › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          'Gunakan Bagikan untuk menyalin arsip ke iCloud Drive, AirDrop, atau app lain.',
      'exportSkipped': 'Folder dilewati (bukan simpanan yang valid): {count}',
      'exportOtherUsers':
          'Folder pengguna RPCS3 lain juga berisi simpanan ({users}), tetapi Core hanya memakai pengguna 00000001; simpanan itu tidak diekspor.',
      'importTitle': 'Hasil impor data simpanan',
      'importLocation':
          'Sumber: File › Di iPhone Saya › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': 'Sumber: {name}',
      'importDestination':
          'RPCS3 membaca simpanan ini dari folder RPCS3 privat milik RewindBox. Simpanan muncul di RPCS3 tanpa langkah tambahan.',
      'countImported': 'Diimpor: {count}',
      'countReplaced': 'Diganti: {count}',
      'countAlreadyPresent': 'Sudah ada: {count}',
      'countKept': 'Dipertahankan: {count}',
      'countRejected': 'Ditolak: {count}',
      'statusImported': 'Diimpor',
      'statusReplaced': 'Diganti',
      'statusAlreadyPresent': 'Sudah ada',
      'statusKept': 'Simpanan yang ada dipertahankan',
      'statusRejected': 'Ditolak',
      'itemSize': '{files} file, {size}',
      'backupKept':
          'Folder simpanan sebelumnya dipindahkan ke folder cadangan privat RewindBox (RPCS3 › SaveBackups).',
      'reasonInvalidName':
          'Nama folder bukan direktori simpanan RPCS3 yang valid: 1 sampai 32 huruf, angka, "_" atau "-".',
      'reasonInvalidParamSfo':
          'PARAM.SFO tidak ada atau bukan deskriptor simpanan PS3 yang valid.',
      'reasonDuplicate':
          'Direktori simpanan yang sama sudah muncul lebih dulu dalam pilihan ini. Hanya yang pertama yang dipakai.',
      'reasonConflictKept':
          'Simpanan dengan nama ini dan isi berbeda sudah ada. Simpanan itu dipertahankan.',
      'reasonStorageRedirected':
          'Penyimpanan RPCS3 (dev_hdd0) dialihkan oleh Data/vfs.yml. RewindBox hanya menangani simpanan di folder RPCS3 miliknya sendiri.',
      'reasonUnsafeEntry':
          'Arsip berisi jalur yang dapat keluar dari folder tujuan (jalur absolut, "..", garis miring terbalik, atau nama kosong).',
      'reasonSymbolicLink': 'Tautan simbolik tidak diterima dalam simpanan.',
      'reasonTooManyEntries': 'Lebih dari {max} entri.',
      'reasonTooLarge': 'Lebih dari {max} secara total.',
      'reasonFileTooLarge': 'Satu file melebihi {max}.',
      'reasonInvalidArchive': 'File bukan arsip ZIP yang dapat dibaca.',
      'reasonNoSave':
          'Tidak ditemukan folder yang berisi file PARAM.SFO di sumber ini.',
      'reasonUnreadable':
          'Sumber tidak dapat dibaca. Jika berada di iCloud Drive atau penyedia lain, unduh dulu di app File lalu coba lagi.',
      'reasonWriteFailed': 'RewindBox tidak dapat menulis simpanan ini.',
      'reasonCorruptData':
          'Data yang diekstrak tidak cocok dengan arsip (ukuran atau checksum).',
      'failNoSaves': 'RPCS3 tidak memiliki simpanan untuk diekspor.',
      'failNothingFound':
          'Tidak ditemukan folder simpanan maupun arsip ZIP di File › Di iPhone Saya › RewindBox › RPCS3 › Import › Game Saves.',
      'failNotZip': 'File yang dipilih bukan arsip .zip.',
      'failExportWrite': 'Arsip ekspor tidak dapat ditulis.',
      'failed': 'Operasi tidak selesai.',
      'busyGameRunning':
          'Sebuah game PS3 sedang berjalan. Tutup dulu: RPCS3 mungkin sedang menulis simpanan.',
      'busyLibrary':
          'Operasi RPCS3 lain sedang berlangsung. Tunggu sampai selesai, lalu coba lagi.',
      'statusExporting': 'Mengekspor data simpanan RPCS3…',
      'statusImporting': 'Mengimpor data simpanan RPCS3…',
      'errorTitle': 'Data simpanan',
    },
    'ja': {
      'importSourceTitle': 'セーブデータをインポート',
      'importSourceBody':
          'セーブデータの取り込み元を選んでください。セーブデータは PARAM.SFO ファイルを含むフォルダで、単体または ZIP アーカイブ内にあります。',
      'sourceFilesFolder': 'RewindBox の「ファイル」フォルダ',
      'sourceFilesFolderHint':
          'ファイル › このiPhone内 › RewindBox › RPCS3 › Import › Game Saves に置いたセーブフォルダまたは ZIP アーカイブ。',
      'sourceZip': 'ZIP アーカイブを選択…',
      'sourceZipHint':
          '別のデバイスの RewindBox または RPCS3 でエクスポートしたアーカイブ。',
      'sourceFolder': 'セーブフォルダを選択…',
      'sourceFolderHint': 'セーブフォルダ、または複数のセーブを含むフォルダ。',
      'cancel': 'キャンセル',
      'close': '閉じる',
      'share': '共有…',
      'replace': '置き換える',
      'keepExisting': '既存を保持',
      'replaceTitle': '既存のセーブデータを置き換えますか？',
      'replaceBody':
          '内容が異なる状態で RPCS3 にすでにあるセーブデータ: {count} 件。置き換えると、現在のフォルダは RPCS3 の外にあるバックアップへ移動してから新しいものが入ります。',
      'exportTitle': 'セーブデータをエクスポートしました',
      'exportSummary': 'セーブ: {saves} • ファイル: {files} • サイズ: {size}',
      'exportLocation':
          'ファイル › このiPhone内 › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          '「共有」を使うと、アーカイブを iCloud Drive や AirDrop、他のアプリへコピーできます。',
      'exportSkipped': 'スキップしたフォルダ（有効なセーブではない）: {count}',
      'exportOtherUsers':
          '他の RPCS3 ユーザーフォルダ（{users}）にもセーブデータがありますが、Core はユーザー 00000001 のみを使うため、エクスポートしていません。',
      'importTitle': 'セーブデータのインポート結果',
      'importLocation':
          '取り込み元: ファイル › このiPhone内 › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': '取り込み元: {name}',
      'importDestination':
          'RPCS3 は RewindBox の非公開 RPCS3 フォルダからこれらのセーブデータを読み込みます。追加の操作なしで RPCS3 に表示されます。',
      'countImported': 'インポート: {count}',
      'countReplaced': '置き換え: {count}',
      'countAlreadyPresent': 'すでに存在: {count}',
      'countKept': '保持: {count}',
      'countRejected': '拒否: {count}',
      'statusImported': 'インポートしました',
      'statusReplaced': '置き換えました',
      'statusAlreadyPresent': 'すでに存在します',
      'statusKept': '既存のセーブを保持しました',
      'statusRejected': '拒否しました',
      'itemSize': '{files} ファイル、{size}',
      'backupKept':
          '以前のセーブフォルダは RewindBox の非公開バックアップフォルダ（RPCS3 › SaveBackups）へ移動しました。',
      'reasonInvalidName':
          'フォルダ名が RPCS3 の有効なセーブディレクトリではありません: 英数字、「_」、「-」の 1〜32 文字。',
      'reasonInvalidParamSfo':
          'PARAM.SFO がないか、有効な PS3 セーブ記述子ではありません。',
      'reasonDuplicate':
          '同じセーブディレクトリがこの選択内で先に出ています。最初のものだけを使いました。',
      'reasonConflictKept':
          '同じ名前で内容が異なるセーブがすでにあります。既存のものを保持しました。',
      'reasonStorageRedirected':
          'RPCS3 のストレージ（dev_hdd0）は Data/vfs.yml によって別の場所に向けられています。RewindBox は自身の RPCS3 フォルダ内のセーブデータのみを扱います。',
      'reasonUnsafeEntry':
          'アーカイブに、保存先フォルダの外へ出る可能性のあるパス（絶対パス、「..」、バックスラッシュ、空の名前）が含まれています。',
      'reasonSymbolicLink': 'セーブデータ内のシンボリックリンクは受け付けません。',
      'reasonTooManyEntries': 'エントリが {max} を超えています。',
      'reasonTooLarge': '合計が {max} を超えています。',
      'reasonFileTooLarge': '1 つのファイルが {max} を超えています。',
      'reasonInvalidArchive': 'このファイルは読み取れる ZIP アーカイブではありません。',
      'reasonNoSave':
          'この取り込み元に PARAM.SFO ファイルを含むフォルダが見つかりません。',
      'reasonUnreadable':
          '取り込み元を読み取れませんでした。iCloud Drive や他のプロバイダにある場合は、「ファイル」アプリでダウンロードしてからやり直してください。',
      'reasonWriteFailed': 'RewindBox はこのセーブデータを書き込めませんでした。',
      'reasonCorruptData':
          '展開したデータがアーカイブと一致しません（サイズまたはチェックサム）。',
      'failNoSaves': 'RPCS3 にエクスポートできるセーブデータがありません。',
      'failNothingFound':
          'ファイル › このiPhone内 › RewindBox › RPCS3 › Import › Game Saves にセーブフォルダも ZIP アーカイブも見つかりません。',
      'failNotZip': '選択したファイルは .zip アーカイブではありません。',
      'failExportWrite': 'エクスポート用アーカイブを書き込めませんでした。',
      'failed': '操作は完了しませんでした。',
      'busyGameRunning':
          'PS3 のゲームが実行中です。先に終了してください。RPCS3 がセーブデータを書き込んでいる可能性があります。',
      'busyLibrary':
          '別の RPCS3 の処理が進行中です。終わるまで待ってから、もう一度お試しください。',
      'statusExporting': 'RPCS3 のセーブデータをエクスポート中…',
      'statusImporting': 'RPCS3 のセーブデータをインポート中…',
      'errorTitle': 'セーブデータ',
    },
    'ko': {
      'importSourceTitle': '세이브 데이터 가져오기',
      'importSourceBody':
          '세이브 데이터를 어디에서 가져올지 선택하세요. 세이브 데이터는 PARAM.SFO 파일이 들어 있는 폴더이며, 단독이거나 ZIP 아카이브 안에 있을 수 있습니다.',
      'sourceFilesFolder': 'RewindBox의 파일 앱 폴더',
      'sourceFilesFolderHint':
          '파일 › 나의 iPhone › RewindBox › RPCS3 › Import › Game Saves에 넣어 둔 세이브 폴더 또는 ZIP 아카이브.',
      'sourceZip': 'ZIP 아카이브 선택…',
      'sourceZipHint': '다른 기기의 RewindBox 또는 RPCS3에서 내보낸 아카이브.',
      'sourceFolder': '세이브 폴더 선택…',
      'sourceFolderHint': '세이브 폴더 하나 또는 여러 세이브가 들어 있는 폴더.',
      'cancel': '취소',
      'close': '닫기',
      'share': '공유…',
      'replace': '교체',
      'keepExisting': '기존 항목 유지',
      'replaceTitle': '기존 세이브 데이터를 교체할까요?',
      'replaceBody':
          '내용이 다른 상태로 RPCS3에 이미 있는 세이브 데이터: {count}개. 교체하면 현재 폴더는 RPCS3 밖의 백업으로 옮겨진 뒤 새 폴더가 설치됩니다.',
      'exportTitle': '세이브 데이터를 내보냈습니다',
      'exportSummary': '세이브: {saves} • 파일: {files} • 크기: {size}',
      'exportLocation':
          '파일 › 나의 iPhone › RewindBox › RPCS3 › Export › Game Saves › {file}',
      'exportShareHint':
          '공유를 사용하면 아카이브를 iCloud Drive, AirDrop 또는 다른 앱으로 복사할 수 있습니다.',
      'exportSkipped': '건너뛴 폴더(유효한 세이브가 아님): {count}',
      'exportOtherUsers':
          '다른 RPCS3 사용자 폴더({users})에도 세이브 데이터가 있지만 Core는 사용자 00000001만 사용하므로 내보내지 않았습니다.',
      'importTitle': '세이브 데이터 가져오기 결과',
      'importLocation':
          '원본: 파일 › 나의 iPhone › RewindBox › RPCS3 › Import › Game Saves',
      'importSourceLabel': '원본: {name}',
      'importDestination':
          'RPCS3는 RewindBox의 비공개 RPCS3 폴더에서 이 세이브 데이터를 읽습니다. 추가 단계 없이 RPCS3에 표시됩니다.',
      'countImported': '가져옴: {count}',
      'countReplaced': '교체됨: {count}',
      'countAlreadyPresent': '이미 있음: {count}',
      'countKept': '유지됨: {count}',
      'countRejected': '거부됨: {count}',
      'statusImported': '가져옴',
      'statusReplaced': '교체됨',
      'statusAlreadyPresent': '이미 있음',
      'statusKept': '기존 세이브 유지됨',
      'statusRejected': '거부됨',
      'itemSize': '파일 {files}개, {size}',
      'backupKept':
          '이전 세이브 폴더는 RewindBox의 비공개 백업 폴더(RPCS3 › SaveBackups)로 옮겨졌습니다.',
      'reasonInvalidName':
          '폴더 이름이 유효한 RPCS3 세이브 디렉터리가 아닙니다. 영문자, 숫자, "_" 또는 "-"로 된 1~32자여야 합니다.',
      'reasonInvalidParamSfo':
          'PARAM.SFO가 없거나 유효한 PS3 세이브 설명자가 아닙니다.',
      'reasonDuplicate':
          '같은 세이브 디렉터리가 이 선택에서 먼저 나타났습니다. 첫 번째 항목만 사용했습니다.',
      'reasonConflictKept':
          '같은 이름에 내용이 다른 세이브가 이미 있습니다. 기존 세이브를 유지했습니다.',
      'reasonStorageRedirected':
          'RPCS3 저장소(dev_hdd0)가 Data/vfs.yml에 의해 다른 위치로 지정되어 있습니다. RewindBox은 자체 RPCS3 폴더의 세이브 데이터만 다룹니다.',
      'reasonUnsafeEntry':
          '아카이브에 대상 폴더 밖으로 나갈 수 있는 경로(절대 경로, "..", 백슬래시 또는 빈 이름)가 있습니다.',
      'reasonSymbolicLink': '세이브 데이터 안의 심볼릭 링크는 허용되지 않습니다.',
      'reasonTooManyEntries': '항목이 {max}개를 초과합니다.',
      'reasonTooLarge': '전체 크기가 {max}를 초과합니다.',
      'reasonFileTooLarge': '파일 하나가 {max}를 초과합니다.',
      'reasonInvalidArchive': '이 파일은 읽을 수 있는 ZIP 아카이브가 아닙니다.',
      'reasonNoSave':
          '이 원본에서 PARAM.SFO 파일이 들어 있는 폴더를 찾지 못했습니다.',
      'reasonUnreadable':
          '원본을 읽을 수 없습니다. iCloud Drive나 다른 제공자에 있다면 파일 앱에서 다운로드한 후 다시 시도하세요.',
      'reasonWriteFailed': 'RewindBox이 이 세이브 데이터를 쓰지 못했습니다.',
      'reasonCorruptData':
          '추출한 데이터가 아카이브와 일치하지 않습니다(크기 또는 체크섬).',
      'failNoSaves': 'RPCS3에 내보낼 세이브 데이터가 없습니다.',
      'failNothingFound':
          '파일 › 나의 iPhone › RewindBox › RPCS3 › Import › Game Saves에서 세이브 폴더나 ZIP 아카이브를 찾지 못했습니다.',
      'failNotZip': '선택한 파일은 .zip 아카이브가 아닙니다.',
      'failExportWrite': '내보내기 아카이브를 쓸 수 없습니다.',
      'failed': '작업이 완료되지 않았습니다.',
      'busyGameRunning':
          'PS3 게임이 실행 중입니다. 먼저 게임을 닫으세요. RPCS3가 세이브 데이터를 쓰고 있을 수 있습니다.',
      'busyLibrary':
          '다른 RPCS3 작업이 진행 중입니다. 끝날 때까지 기다린 후 다시 시도하세요.',
      'statusExporting': 'RPCS3 세이브 데이터 내보내는 중…',
      'statusImporting': 'RPCS3 세이브 데이터 가져오는 중…',
      'errorTitle': '세이브 데이터',
    },
  };

  /// Catalog key for a Flutter locale; the Hant script or a TW, HK or MO
  /// region selects Traditional Chinese.
  static String localeKey(Locale locale) {
    final language = locale.languageCode;
    if (language == 'zh_Hant') return 'zh_Hant';
    if (language == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' ||
          country == 'TW' ||
          country == 'HK' ||
          country == 'MO') {
        return 'zh_Hant';
      }
      return 'zh';
    }
    return values.containsKey(language) ? language : 'en';
  }

  /// Catalog key for a language tag such as `fr`, `zh-Hant-TW` or `zh_TW`
  /// (the form `FlutterLocalization` reports outside a widget tree).
  static String localeKeyForTag(String localeTag) {
    final lower = localeTag.replaceAll('-', '_').toLowerCase();
    if (lower.startsWith('zh_hant') ||
        lower.startsWith('zh_tw') ||
        lower.startsWith('zh_hk') ||
        lower.startsWith('zh_mo')) {
      return 'zh_Hant';
    }
    final language = lower.split('_').first;
    return values.containsKey(language) ? language : 'en';
  }

  static String forLocale(Locale locale, String key) =>
      values[localeKey(locale)]?[key] ?? values['en']![key] ?? key;

  static String textForLocale(String localeTag, String key) =>
      values[localeKeyForTag(localeTag)]?[key] ?? values['en']![key] ?? key;

  static String _fill(String text, Map<String, Object?> arguments) {
    var result = text;
    for (final entry in arguments.entries) {
      result = result.replaceAll(
        '{${entry.key}}',
        entry.value?.toString() ?? '',
      );
    }
    return result;
  }

  static String format(
    Locale locale,
    String key,
    Map<String, Object?> arguments,
  ) => _fill(forLocale(locale, key), arguments);

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
