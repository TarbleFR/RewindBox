import 'package:flutter/widgets.dart';

/// Texts of the PS3 RAP licence import (library Import menu, replace prompt
/// and per-file report) in RewindBox's twelve languages. File names,
/// content IDs, paths and raw system diagnostics stay untranslated and are
/// shown apart from these texts.
abstract final class Rpcs3RapLocale {
  static const Map<String, Map<String, String>>
  values = <String, Map<String, String>>{
    'en': {
      'importRapLicenses': 'Import RAP licenses',
      'rapReportTitle': 'RAP licenses',
      'rapCountImported': 'Imported: {count}',
      'rapCountReplaced': 'Replaced: {count}',
      'rapCountAlreadyPresent': 'Already present: {count}',
      'rapCountRejected': 'Rejected: {count}',
      'rapStatusImported': 'Imported',
      'rapStatusReplaced': 'Replaced',
      'rapStatusAlreadyPresent': 'Already present',
      'rapStatusRejected': 'Rejected',
      'rapInstalledAs': 'Installed as {name}',
      'rapBackupKept': 'The previous license was kept as a backup.',
      'rapReasonNotRap': 'Not a .rap file.',
      'rapReasonContentId':
          'The file name must be the PS3 content ID, for example {example}.rap.',
      'rapReasonSize':
          'A RAP license is exactly 16 bytes; this file has {size} bytes.',
      'rapReasonUnreadable':
          'The file could not be read. If it is in iCloud Drive or another provider, download it in the Files app and try again.',
      'rapReasonSelectionConflict':
          'Another selected file has the same content ID but different content. Only the first one was used.',
      'rapReasonConflictKept':
          'A different license is already installed for this content ID. It was kept.',
      'rapReasonStorageRedirected':
          'RPCS3 storage (dev_hdd0) is redirected by Data/vfs.yml. RewindBox installs licenses only in its own RPCS3 folder.',
      'rapReasonWriteFailed': 'RewindBox could not save this license.',
      'rapReplaceTitle': 'Replace installed licenses?',
      'rapReplaceBody':
          'Selected licenses that differ from the license installed for the same content ID: {count}. The previous files are kept as a backup.',
      'rapReplace': 'Replace',
      'rapKeep': 'Keep installed',
      'rapClose': 'Close',
      'rapImportFailed': 'RAP license import failed.',
    },
    'es': {
      'importRapLicenses': 'Importar licencias RAP',
      'rapReportTitle': 'Licencias RAP',
      'rapCountImported': 'Importadas: {count}',
      'rapCountReplaced': 'Reemplazadas: {count}',
      'rapCountAlreadyPresent': 'Ya presentes: {count}',
      'rapCountRejected': 'Rechazadas: {count}',
      'rapStatusImported': 'Importada',
      'rapStatusReplaced': 'Reemplazada',
      'rapStatusAlreadyPresent': 'Ya presente',
      'rapStatusRejected': 'Rechazada',
      'rapInstalledAs': 'Instalada como {name}',
      'rapBackupKept':
          'La licencia anterior se ha guardado como copia de seguridad.',
      'rapReasonNotRap': 'No es un archivo .rap.',
      'rapReasonContentId':
          'El nombre del archivo debe ser el ID de contenido de PS3, por ejemplo {example}.rap.',
      'rapReasonSize':
          'Una licencia RAP tiene exactamente 16 bytes; este archivo tiene {size} bytes.',
      'rapReasonUnreadable':
          'No se pudo leer el archivo. Si está en iCloud Drive o en otro proveedor, descárgalo en la app Archivos y vuelve a intentarlo.',
      'rapReasonSelectionConflict':
          'Otro archivo seleccionado tiene el mismo ID de contenido, pero un contenido distinto. Solo se usó el primero.',
      'rapReasonConflictKept':
          'Ya hay instalada una licencia distinta para este ID de contenido. Se ha conservado.',
      'rapReasonStorageRedirected':
          'El almacenamiento de RPCS3 (dev_hdd0) está redirigido por Data/vfs.yml. RewindBox solo instala licencias en su propia carpeta de RPCS3.',
      'rapReasonWriteFailed': 'RewindBox no pudo guardar esta licencia.',
      'rapReplaceTitle': '¿Reemplazar las licencias instaladas?',
      'rapReplaceBody':
          'Licencias seleccionadas distintas de la instalada para el mismo ID de contenido: {count}. Los archivos anteriores se conservan como copia de seguridad.',
      'rapReplace': 'Reemplazar',
      'rapKeep': 'Conservar la instalada',
      'rapClose': 'Cerrar',
      'rapImportFailed': 'Error al importar las licencias RAP.',
    },
    'ru': {
      'importRapLicenses': 'Импортировать лицензии RAP',
      'rapReportTitle': 'Лицензии RAP',
      'rapCountImported': 'Импортировано: {count}',
      'rapCountReplaced': 'Заменено: {count}',
      'rapCountAlreadyPresent': 'Уже установлено: {count}',
      'rapCountRejected': 'Отклонено: {count}',
      'rapStatusImported': 'Импортирована',
      'rapStatusReplaced': 'Заменена',
      'rapStatusAlreadyPresent': 'Уже установлена',
      'rapStatusRejected': 'Отклонена',
      'rapInstalledAs': 'Установлена как {name}',
      'rapBackupKept': 'Прежняя лицензия сохранена как резервная копия.',
      'rapReasonNotRap': 'Это не файл .rap.',
      'rapReasonContentId':
          'Имя файла должно быть идентификатором контента PS3, например {example}.rap.',
      'rapReasonSize':
          'Лицензия RAP занимает ровно 16 байт; размер этого файла — {size} байт.',
      'rapReasonUnreadable':
          'Не удалось прочитать файл. Если он находится в iCloud Drive или у другого поставщика, загрузите его в приложении «Файлы» и повторите попытку.',
      'rapReasonSelectionConflict':
          'Другой выбранный файл имеет тот же идентификатор контента, но другое содержимое. Использован только первый.',
      'rapReasonConflictKept':
          'Для этого идентификатора контента уже установлена другая лицензия. Она сохранена.',
      'rapReasonStorageRedirected':
          'Хранилище RPCS3 (dev_hdd0) перенаправлено файлом Data/vfs.yml. RewindBox устанавливает лицензии только в собственную папку RPCS3.',
      'rapReasonWriteFailed': 'RewindBox не удалось сохранить эту лицензию.',
      'rapReplaceTitle': 'Заменить установленные лицензии?',
      'rapReplaceBody':
          'Выбранные лицензии, отличающиеся от установленной для того же идентификатора контента: {count}. Прежние файлы сохраняются как резервные копии.',
      'rapReplace': 'Заменить',
      'rapKeep': 'Оставить установленную',
      'rapClose': 'Закрыть',
      'rapImportFailed': 'Не удалось импортировать лицензии RAP.',
    },
    'zh': {
      'importRapLicenses': '导入 RAP 许可证',
      'rapReportTitle': 'RAP 许可证',
      'rapCountImported': '已导入：{count}',
      'rapCountReplaced': '已替换：{count}',
      'rapCountAlreadyPresent': '已存在：{count}',
      'rapCountRejected': '已拒绝：{count}',
      'rapStatusImported': '已导入',
      'rapStatusReplaced': '已替换',
      'rapStatusAlreadyPresent': '已存在',
      'rapStatusRejected': '已拒绝',
      'rapInstalledAs': '已安装为 {name}',
      'rapBackupKept': '原许可证已作为备份保留。',
      'rapReasonNotRap': '不是 .rap 文件。',
      'rapReasonContentId': '文件名必须是 PS3 内容 ID，例如 {example}.rap。',
      'rapReasonSize': 'RAP 许可证正好为 16 字节；此文件为 {size} 字节。',
      'rapReasonUnreadable':
          '无法读取该文件。如果它位于 iCloud 云盘或其他提供方中，请先在“文件”App 中下载，然后重试。',
      'rapReasonSelectionConflict': '另一个所选文件的内容 ID 相同但内容不同。仅使用了第一个文件。',
      'rapReasonConflictKept': '此内容 ID 已安装了不同的许可证，已保留原许可证。',
      'rapReasonStorageRedirected':
          'RPCS3 存储（dev_hdd0）已被 Data/vfs.yml 重定向。RewindBox 只会将许可证安装到其自己的 RPCS3 文件夹中。',
      'rapReasonWriteFailed': 'RewindBox 无法保存此许可证。',
      'rapReplaceTitle': '替换已安装的许可证？',
      'rapReplaceBody': '与同一内容 ID 已安装许可证不同的所选许可证：{count} 个。原文件将作为备份保留。',
      'rapReplace': '替换',
      'rapKeep': '保留已安装的',
      'rapClose': '关闭',
      'rapImportFailed': 'RAP 许可证导入失败。',
    },
    'zh_Hant': {
      'importRapLicenses': '匯入 RAP 授權檔',
      'rapReportTitle': 'RAP 授權檔',
      'rapCountImported': '已匯入：{count}',
      'rapCountReplaced': '已取代：{count}',
      'rapCountAlreadyPresent': '已存在：{count}',
      'rapCountRejected': '已拒絕：{count}',
      'rapStatusImported': '已匯入',
      'rapStatusReplaced': '已取代',
      'rapStatusAlreadyPresent': '已存在',
      'rapStatusRejected': '已拒絕',
      'rapInstalledAs': '已安裝為 {name}',
      'rapBackupKept': '原授權檔已保留為備份。',
      'rapReasonNotRap': '不是 .rap 檔案。',
      'rapReasonContentId': '檔案名稱必須是 PS3 內容 ID，例如 {example}.rap。',
      'rapReasonSize': 'RAP 授權檔正好為 16 位元組；此檔案為 {size} 位元組。',
      'rapReasonUnreadable':
          '無法讀取此檔案。如果它位於 iCloud 雲碟或其他提供者中，請先在「檔案」App 中下載，然後再試一次。',
      'rapReasonSelectionConflict': '另一個所選檔案的內容 ID 相同但內容不同。僅使用了第一個檔案。',
      'rapReasonConflictKept': '此內容 ID 已安裝不同的授權檔，已保留原授權檔。',
      'rapReasonStorageRedirected':
          'RPCS3 儲存空間（dev_hdd0）已被 Data/vfs.yml 重新導向。RewindBox 只會將授權檔安裝到自己的 RPCS3 資料夾。',
      'rapReasonWriteFailed': 'RewindBox 無法儲存此授權檔。',
      'rapReplaceTitle': '要取代已安裝的授權檔嗎？',
      'rapReplaceBody': '與同一內容 ID 已安裝授權檔不同的所選授權檔：{count} 個。原檔案將保留為備份。',
      'rapReplace': '取代',
      'rapKeep': '保留已安裝的',
      'rapClose': '關閉',
      'rapImportFailed': 'RAP 授權檔匯入失敗。',
    },
    'pt': {
      'importRapLicenses': 'Importar licenças RAP',
      'rapReportTitle': 'Licenças RAP',
      'rapCountImported': 'Importadas: {count}',
      'rapCountReplaced': 'Substituídas: {count}',
      'rapCountAlreadyPresent': 'Já presentes: {count}',
      'rapCountRejected': 'Recusadas: {count}',
      'rapStatusImported': 'Importada',
      'rapStatusReplaced': 'Substituída',
      'rapStatusAlreadyPresent': 'Já presente',
      'rapStatusRejected': 'Recusada',
      'rapInstalledAs': 'Instalada como {name}',
      'rapBackupKept':
          'A licença anterior foi guardada como cópia de segurança.',
      'rapReasonNotRap': 'Não é um ficheiro .rap.',
      'rapReasonContentId':
          'O nome do ficheiro tem de ser o ID de conteúdo da PS3, por exemplo {example}.rap.',
      'rapReasonSize':
          'Uma licença RAP tem exatamente 16 bytes; este ficheiro tem {size} bytes.',
      'rapReasonUnreadable':
          'Não foi possível ler o ficheiro. Se estiver no iCloud Drive ou noutro fornecedor, transfira-o na app Ficheiros e tente novamente.',
      'rapReasonSelectionConflict':
          'Outro ficheiro selecionado tem o mesmo ID de conteúdo, mas um conteúdo diferente. Só foi usado o primeiro.',
      'rapReasonConflictKept':
          'Já está instalada uma licença diferente para este ID de conteúdo. Foi mantida.',
      'rapReasonStorageRedirected':
          'O armazenamento do RPCS3 (dev_hdd0) está redirecionado por Data/vfs.yml. O RewindBox só instala licenças na sua própria pasta RPCS3.',
      'rapReasonWriteFailed':
          'O RewindBox não conseguiu guardar esta licença.',
      'rapReplaceTitle': 'Substituir as licenças instaladas?',
      'rapReplaceBody':
          'Licenças selecionadas diferentes da instalada para o mesmo ID de conteúdo: {count}. Os ficheiros anteriores são guardados como cópia de segurança.',
      'rapReplace': 'Substituir',
      'rapKeep': 'Manter a instalada',
      'rapClose': 'Fechar',
      'rapImportFailed': 'A importação das licenças RAP falhou.',
    },
    'fr': {
      'importRapLicenses': 'Importer des licences RAP',
      'rapReportTitle': 'Licences RAP',
      'rapCountImported': 'Importées : {count}',
      'rapCountReplaced': 'Remplacées : {count}',
      'rapCountAlreadyPresent': 'Déjà présentes : {count}',
      'rapCountRejected': 'Refusées : {count}',
      'rapStatusImported': 'Importée',
      'rapStatusReplaced': 'Remplacée',
      'rapStatusAlreadyPresent': 'Déjà présente',
      'rapStatusRejected': 'Refusée',
      'rapInstalledAs': 'Installée sous le nom {name}',
      'rapBackupKept': 'L’ancienne licence a été conservée en sauvegarde.',
      'rapReasonNotRap': 'Ce n’est pas un fichier .rap.',
      'rapReasonContentId':
          'Le nom du fichier doit être l’identifiant de contenu PS3, par exemple {example}.rap.',
      'rapReasonSize':
          'Une licence RAP fait exactement 16 octets ; ce fichier en fait {size}.',
      'rapReasonUnreadable':
          'Le fichier n’a pas pu être lu. S’il se trouve dans iCloud Drive ou chez un autre fournisseur, téléchargez-le dans l’app Fichiers puis réessayez.',
      'rapReasonSelectionConflict':
          'Un autre fichier sélectionné porte le même identifiant de contenu avec un contenu différent. Seul le premier a été utilisé.',
      'rapReasonConflictKept':
          'Une licence différente est déjà installée pour cet identifiant de contenu. Elle a été conservée.',
      'rapReasonStorageRedirected':
          'Le stockage RPCS3 (dev_hdd0) est redirigé par Data/vfs.yml. RewindBox installe les licences uniquement dans son propre dossier RPCS3.',
      'rapReasonWriteFailed':
          'RewindBox n’a pas pu enregistrer cette licence.',
      'rapReplaceTitle': 'Remplacer les licences installées ?',
      'rapReplaceBody':
          'Licences sélectionnées différentes de la licence installée pour le même identifiant de contenu : {count}. Les anciens fichiers sont conservés en sauvegarde.',
      'rapReplace': 'Remplacer',
      'rapKeep': 'Conserver l’installée',
      'rapClose': 'Fermer',
      'rapImportFailed': 'L’import des licences RAP a échoué.',
    },
    'de': {
      'importRapLicenses': 'RAP-Lizenzen importieren',
      'rapReportTitle': 'RAP-Lizenzen',
      'rapCountImported': 'Importiert: {count}',
      'rapCountReplaced': 'Ersetzt: {count}',
      'rapCountAlreadyPresent': 'Bereits vorhanden: {count}',
      'rapCountRejected': 'Abgelehnt: {count}',
      'rapStatusImported': 'Importiert',
      'rapStatusReplaced': 'Ersetzt',
      'rapStatusAlreadyPresent': 'Bereits vorhanden',
      'rapStatusRejected': 'Abgelehnt',
      'rapInstalledAs': 'Installiert als {name}',
      'rapBackupKept': 'Die bisherige Lizenz wurde als Sicherung aufbewahrt.',
      'rapReasonNotRap': 'Keine .rap-Datei.',
      'rapReasonContentId':
          'Der Dateiname muss die PS3-Content-ID sein, zum Beispiel {example}.rap.',
      'rapReasonSize':
          'Eine RAP-Lizenz ist genau 16 Byte groß; diese Datei hat {size} Byte.',
      'rapReasonUnreadable':
          'Die Datei konnte nicht gelesen werden. Liegt sie in iCloud Drive oder bei einem anderen Anbieter, lade sie in der Dateien-App herunter und versuche es erneut.',
      'rapReasonSelectionConflict':
          'Eine andere ausgewählte Datei hat dieselbe Content-ID, aber einen anderen Inhalt. Nur die erste wurde verwendet.',
      'rapReasonConflictKept':
          'Für diese Content-ID ist bereits eine andere Lizenz installiert. Sie wurde beibehalten.',
      'rapReasonStorageRedirected':
          'Der RPCS3-Speicher (dev_hdd0) wird durch Data/vfs.yml umgeleitet. RewindBox installiert Lizenzen nur in seinem eigenen RPCS3-Ordner.',
      'rapReasonWriteFailed': 'RewindBox konnte diese Lizenz nicht speichern.',
      'rapReplaceTitle': 'Installierte Lizenzen ersetzen?',
      'rapReplaceBody':
          'Ausgewählte Lizenzen, die sich von der installierten Lizenz mit derselben Content-ID unterscheiden: {count}. Die bisherigen Dateien werden als Sicherung aufbewahrt.',
      'rapReplace': 'Ersetzen',
      'rapKeep': 'Installierte behalten',
      'rapClose': 'Schließen',
      'rapImportFailed': 'Import der RAP-Lizenzen fehlgeschlagen.',
    },
    'it': {
      'importRapLicenses': 'Importa licenze RAP',
      'rapReportTitle': 'Licenze RAP',
      'rapCountImported': 'Importate: {count}',
      'rapCountReplaced': 'Sostituite: {count}',
      'rapCountAlreadyPresent': 'Già presenti: {count}',
      'rapCountRejected': 'Rifiutate: {count}',
      'rapStatusImported': 'Importata',
      'rapStatusReplaced': 'Sostituita',
      'rapStatusAlreadyPresent': 'Già presente',
      'rapStatusRejected': 'Rifiutata',
      'rapInstalledAs': 'Installata come {name}',
      'rapBackupKept': 'La licenza precedente è stata conservata come backup.',
      'rapReasonNotRap': 'Non è un file .rap.',
      'rapReasonContentId':
          'Il nome del file deve essere l’ID contenuto della PS3, ad esempio {example}.rap.',
      'rapReasonSize':
          'Una licenza RAP è di esattamente 16 byte; questo file ne ha {size}.',
      'rapReasonUnreadable':
          'Impossibile leggere il file. Se si trova in iCloud Drive o presso un altro fornitore, scaricalo nell’app File e riprova.',
      'rapReasonSelectionConflict':
          'Un altro file selezionato ha lo stesso ID contenuto ma un contenuto diverso. È stato usato solo il primo.',
      'rapReasonConflictKept':
          'Per questo ID contenuto è già installata una licenza diversa. È stata mantenuta.',
      'rapReasonStorageRedirected':
          'L’archivio di RPCS3 (dev_hdd0) è reindirizzato da Data/vfs.yml. RewindBox installa le licenze solo nella propria cartella RPCS3.',
      'rapReasonWriteFailed':
          'RewindBox non è riuscito a salvare questa licenza.',
      'rapReplaceTitle': 'Sostituire le licenze installate?',
      'rapReplaceBody':
          'Licenze selezionate diverse da quella installata per lo stesso ID contenuto: {count}. I file precedenti vengono conservati come backup.',
      'rapReplace': 'Sostituisci',
      'rapKeep': 'Mantieni quella installata',
      'rapClose': 'Chiudi',
      'rapImportFailed': 'Importazione delle licenze RAP non riuscita.',
    },
    'id': {
      'importRapLicenses': 'Impor lisensi RAP',
      'rapReportTitle': 'Lisensi RAP',
      'rapCountImported': 'Diimpor: {count}',
      'rapCountReplaced': 'Diganti: {count}',
      'rapCountAlreadyPresent': 'Sudah ada: {count}',
      'rapCountRejected': 'Ditolak: {count}',
      'rapStatusImported': 'Diimpor',
      'rapStatusReplaced': 'Diganti',
      'rapStatusAlreadyPresent': 'Sudah ada',
      'rapStatusRejected': 'Ditolak',
      'rapInstalledAs': 'Dipasang sebagai {name}',
      'rapBackupKept': 'Lisensi sebelumnya disimpan sebagai cadangan.',
      'rapReasonNotRap': 'Bukan file .rap.',
      'rapReasonContentId':
          'Nama file harus berupa ID konten PS3, misalnya {example}.rap.',
      'rapReasonSize':
          'Lisensi RAP berukuran tepat 16 byte; file ini berukuran {size} byte.',
      'rapReasonUnreadable':
          'File tidak dapat dibaca. Jika file berada di iCloud Drive atau penyedia lain, unduh file tersebut di aplikasi File lalu coba lagi.',
      'rapReasonSelectionConflict':
          'File lain yang dipilih memiliki ID konten yang sama dengan isi yang berbeda. Hanya file pertama yang digunakan.',
      'rapReasonConflictKept':
          'Lisensi lain sudah terpasang untuk ID konten ini. Lisensi tersebut dipertahankan.',
      'rapReasonStorageRedirected':
          'Penyimpanan RPCS3 (dev_hdd0) dialihkan oleh Data/vfs.yml. RewindBox hanya memasang lisensi di folder RPCS3 miliknya sendiri.',
      'rapReasonWriteFailed': 'RewindBox tidak dapat menyimpan lisensi ini.',
      'rapReplaceTitle': 'Ganti lisensi yang terpasang?',
      'rapReplaceBody':
          'Lisensi terpilih yang berbeda dari lisensi terpasang untuk ID konten yang sama: {count}. File sebelumnya disimpan sebagai cadangan.',
      'rapReplace': 'Ganti',
      'rapKeep': 'Pertahankan yang terpasang',
      'rapClose': 'Tutup',
      'rapImportFailed': 'Impor lisensi RAP gagal.',
    },
    'ja': {
      'importRapLicenses': 'RAP ライセンスをインポート',
      'rapReportTitle': 'RAP ライセンス',
      'rapCountImported': 'インポート済み: {count}',
      'rapCountReplaced': '置き換え済み: {count}',
      'rapCountAlreadyPresent': '既に存在: {count}',
      'rapCountRejected': '拒否: {count}',
      'rapStatusImported': 'インポート済み',
      'rapStatusReplaced': '置き換え済み',
      'rapStatusAlreadyPresent': '既に存在',
      'rapStatusRejected': '拒否',
      'rapInstalledAs': '{name} としてインストール済み',
      'rapBackupKept': '以前のライセンスはバックアップとして保持されています。',
      'rapReasonNotRap': '.rap ファイルではありません。',
      'rapReasonContentId':
          'ファイル名は PS3 のコンテンツ ID にする必要があります（例: {example}.rap）。',
      'rapReasonSize': 'RAP ライセンスはちょうど 16 バイトです。このファイルは {size} バイトです。',
      'rapReasonUnreadable':
          'ファイルを読み込めませんでした。iCloud Drive または他のプロバイダにある場合は、「ファイル」App でダウンロードしてから、もう一度お試しください。',
      'rapReasonSelectionConflict':
          '選択した別のファイルのコンテンツ ID が同じで、内容が異なります。最初のファイルのみ使用しました。',
      'rapReasonConflictKept':
          'このコンテンツ ID には別のライセンスが既にインストールされています。そのライセンスを保持しました。',
      'rapReasonStorageRedirected':
          'RPCS3 のストレージ（dev_hdd0）が Data/vfs.yml によってリダイレクトされています。RewindBox は自身の RPCS3 フォルダにのみライセンスをインストールします。',
      'rapReasonWriteFailed': 'RewindBox はこのライセンスを保存できませんでした。',
      'rapReplaceTitle': 'インストール済みのライセンスを置き換えますか？',
      'rapReplaceBody':
          '同じコンテンツ ID のインストール済みライセンスと異なる選択ライセンス: {count} 件。以前のファイルはバックアップとして保持されます。',
      'rapReplace': '置き換える',
      'rapKeep': 'インストール済みを保持',
      'rapClose': '閉じる',
      'rapImportFailed': 'RAP ライセンスのインポートに失敗しました。',
    },
    'ko': {
      'importRapLicenses': 'RAP 라이선스 가져오기',
      'rapReportTitle': 'RAP 라이선스',
      'rapCountImported': '가져옴: {count}',
      'rapCountReplaced': '교체됨: {count}',
      'rapCountAlreadyPresent': '이미 있음: {count}',
      'rapCountRejected': '거부됨: {count}',
      'rapStatusImported': '가져옴',
      'rapStatusReplaced': '교체됨',
      'rapStatusAlreadyPresent': '이미 있음',
      'rapStatusRejected': '거부됨',
      'rapInstalledAs': '{name}(으)로 설치됨',
      'rapBackupKept': '이전 라이선스는 백업으로 보관되었습니다.',
      'rapReasonNotRap': '.rap 파일이 아닙니다.',
      'rapReasonContentId': '파일 이름은 PS3 콘텐츠 ID여야 합니다(예: {example}.rap).',
      'rapReasonSize': 'RAP 라이선스는 정확히 16바이트입니다. 이 파일은 {size}바이트입니다.',
      'rapReasonUnreadable':
          '파일을 읽을 수 없습니다. iCloud Drive나 다른 제공자에 있다면 파일 앱에서 다운로드한 후 다시 시도하세요.',
      'rapReasonSelectionConflict':
          '선택한 다른 파일의 콘텐츠 ID가 같지만 내용이 다릅니다. 첫 번째 파일만 사용했습니다.',
      'rapReasonConflictKept':
          '이 콘텐츠 ID에 다른 라이선스가 이미 설치되어 있습니다. 기존 라이선스를 유지했습니다.',
      'rapReasonStorageRedirected':
          'RPCS3 저장소(dev_hdd0)가 Data/vfs.yml에 의해 다른 위치로 지정되어 있습니다. RewindBox은 자체 RPCS3 폴더에만 라이선스를 설치합니다.',
      'rapReasonWriteFailed': 'RewindBox이 이 라이선스를 저장하지 못했습니다.',
      'rapReplaceTitle': '설치된 라이선스를 교체할까요?',
      'rapReplaceBody':
          '같은 콘텐츠 ID로 설치된 라이선스와 다른 선택 라이선스: {count}개. 이전 파일은 백업으로 보관됩니다.',
      'rapReplace': '교체',
      'rapKeep': '설치된 항목 유지',
      'rapClose': '닫기',
      'rapImportFailed': 'RAP 라이선스를 가져오지 못했습니다.',
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
