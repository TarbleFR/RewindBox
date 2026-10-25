import 'package:flutter/widgets.dart';

abstract final class MelonxLaunchAccessLocale {
  static const values = <String, Map<String, String>>{
    "en": {
      "memoryEntitlements":
          "MeloNX cannot start: this signed installation is missing required memory entitlements. Enable Increased Memory Limit (Get More RAM) and, when required on this device, Extended Virtual Addressing in a signing tool and provisioning profile that support them. Re-sign and reinstall RewindBox, then try again. These permissions cannot be enabled inside the app.",
      "entitlementCheckFailed":
          "RewindBox could not verify the signed permissions. MeloNX remains blocked. Reopen the app or check its signing configuration.",
      "libraryRestartRequired":
          "Close and reopen RewindBox to finish loading your transferred MeloNX data before starting a Switch game.",
    },
    "fr": {
      "memoryEntitlements":
          "MeloNX ne peut pas démarrer : cette installation signée ne possède pas les entitlements mémoire requis. Activez Increased Memory Limit (Get More RAM) et, lorsque cet appareil le nécessite, Extended Virtual Addressing avec un outil de signature et un profil de provisionnement compatibles. Signez de nouveau et réinstallez RewindBox, puis réessayez. Ces droits ne peuvent pas être activés depuis l’application.",
      "entitlementCheckFailed":
          "RewindBox ne peut pas vérifier les droits signés. MeloNX reste bloqué. Rouvrez l’application ou vérifiez sa configuration de signature.",
      "libraryRestartRequired":
          "Fermez puis rouvrez RewindBox pour charger les données MeloNX transférées avant de lancer un jeu Switch.",
    },
    "de": {
      "memoryEntitlements":
          "MeloNX kann nicht starten: Dieser signierten Installation fehlen erforderliche Speicherberechtigungen. Aktiviere Increased Memory Limit (Get More RAM) und, falls dieses Gerät es benötigt, Extended Virtual Addressing mit einem geeigneten Signierwerkzeug und Bereitstellungsprofil. Signiere RewindBox erneut und installiere es neu. Diese Rechte lassen sich nicht in der App aktivieren.",
      "entitlementCheckFailed":
          "RewindBox konnte die signierten Rechte nicht prüfen. MeloNX bleibt gesperrt. Öffne die App erneut oder prüfe die Signierung.",
      "libraryRestartRequired":
          "Schließe und öffne RewindBox vor dem Start eines Switch-Spiels, um die übertragenen MeloNX-Daten zu laden.",
    },
    "es": {
      "memoryEntitlements":
          "MeloNX no puede iniciarse: faltan permisos de memoria en esta instalación firmada. Activa Increased Memory Limit (Get More RAM) y, si el dispositivo lo requiere, Extended Virtual Addressing con una herramienta de firma y un perfil de aprovisionamiento compatibles. Vuelve a firmar e instalar RewindBox. Estos permisos no se pueden activar dentro de la aplicación.",
      "entitlementCheckFailed":
          "No se pudieron verificar los permisos firmados. MeloNX sigue bloqueado. Abre de nuevo RewindBox o revisa la firma.",
      "libraryRestartRequired":
          "Cierra y vuelve a abrir RewindBox para cargar los datos transferidos antes de iniciar un juego de Switch.",
    },
    "it": {
      "memoryEntitlements":
          "MeloNX non può avviarsi: in questa installazione firmata mancano le autorizzazioni di memoria richieste. Attiva Increased Memory Limit (Get More RAM) e, se richiesto dal dispositivo, Extended Virtual Addressing con uno strumento di firma e un profilo di provisioning compatibili. Firma nuovamente e reinstalla RewindBox. Questi permessi non si possono attivare dall’app.",
      "entitlementCheckFailed":
          "Impossibile verificare i permessi firmati. MeloNX resta bloccato. Riapri RewindBox o verifica la firma.",
      "libraryRestartRequired":
          "Chiudi e riapri RewindBox per caricare i dati MeloNX trasferiti prima di avviare un gioco Switch.",
    },
    "pt": {
      "memoryEntitlements":
          "O MeloNX não pode iniciar: faltam permissões de memória nesta instalação assinada. Ative Increased Memory Limit (Get More RAM) e, se o dispositivo exigir, Extended Virtual Addressing com uma ferramenta de assinatura e um perfil de aprovisionamento compatíveis. Assine novamente e reinstale o RewindBox. Estas permissões não podem ser ativadas dentro da aplicação.",
      "entitlementCheckFailed":
          "Não foi possível verificar as permissões assinadas. O MeloNX permanece bloqueado. Reabra o RewindBox ou verifique a assinatura.",
      "libraryRestartRequired":
          "Feche e reabra o RewindBox para carregar os dados transferidos antes de iniciar um jogo Switch.",
    },
    "ru": {
      "memoryEntitlements":
          "MeloNX не запускается: в подписанной установке отсутствуют необходимые права памяти. Включите Increased Memory Limit (Get More RAM) и, если устройство требует, Extended Virtual Addressing с помощью поддерживаемого инструмента подписи и профиля. Подпишите и установите RewindBox заново. Эти права нельзя включить внутри приложения.",
      "entitlementCheckFailed":
          "Не удалось проверить подписанные права. MeloNX остаётся заблокированным. Откройте RewindBox заново или проверьте подпись.",
      "libraryRestartRequired":
          "Закройте и откройте RewindBox, чтобы загрузить перенесённые данные перед запуском игры Switch.",
    },
    "id": {
      "memoryEntitlements":
          "MeloNX tidak dapat dimulai: instalasi bertanda tangan ini tidak memiliki izin memori yang diperlukan. Aktifkan Increased Memory Limit (Get More RAM) dan, jika diperlukan perangkat, Extended Virtual Addressing dengan alat penandatanganan dan profil provisioning yang mendukungnya. Tanda tangani ulang dan pasang kembali RewindBox. Izin ini tidak dapat diaktifkan dari dalam aplikasi.",
      "entitlementCheckFailed":
          "Izin bertanda tangan tidak dapat diverifikasi. MeloNX tetap diblokir. Buka kembali RewindBox atau periksa penandatanganannya.",
      "libraryRestartRequired":
          "Tutup dan buka kembali RewindBox untuk memuat data yang ditransfer sebelum menjalankan game Switch.",
    },
    "ja": {
      "memoryEntitlements":
          "MeloNXを起動できません。この署名済みインストールには必要なメモリー権限がありません。対応する署名ツールとプロビジョニングプロファイルでIncreased Memory Limit（Get More RAM）を有効にし、この端末で必要な場合はExtended Virtual Addressingも有効にしてください。RewindBoxを再署名して再インストールしてください。これらの権限はアプリ内では有効にできません。",
      "entitlementCheckFailed":
          "署名された権限を確認できません。MeloNXの起動はブロックされています。RewindBoxを開き直すか署名設定を確認してください。",
      "libraryRestartRequired":
          "Switchのゲームを起動する前にRewindBoxを閉じて開き直し、転送したデータを読み込んでください。",
    },
    "ko": {
      "memoryEntitlements":
          "MeloNX를 시작할 수 없습니다. 서명된 설치에 필요한 메모리 권한이 없습니다. 지원하는 서명 도구와 프로비저닝 프로필에서 Increased Memory Limit(Get More RAM)을 활성화하고, 기기에 필요한 경우 Extended Virtual Addressing도 활성화하세요. RewindBox를 다시 서명하고 재설치하세요. 앱 안에서는 이 권한을 활성화할 수 없습니다.",
      "entitlementCheckFailed":
          "서명된 권한을 확인할 수 없습니다. MeloNX 실행이 차단됩니다. RewindBox를 다시 열거나 서명 설정을 확인하세요.",
      "libraryRestartRequired":
          "Switch 게임을 시작하기 전에 RewindBox를 닫고 다시 열어 전송한 데이터를 불러오세요.",
    },
    "zh": {
      "memoryEntitlements":
          "MeloNX 无法启动：此签名安装缺少所需的内存权限。请使用支持这些权限的签名工具和描述文件，启用 Increased Memory Limit（Get More RAM），并在设备需要时启用 Extended Virtual Addressing。重新签名并安装 RewindBox 后重试。这些权限无法在应用内启用。",
      "entitlementCheckFailed":
          "无法验证签名权限。MeloNX 将保持阻止状态。请重新打开 RewindBox 或检查签名配置。",
      "libraryRestartRequired": "启动 Switch 游戏前，请关闭并重新打开 RewindBox，以加载已迁移的数据。",
    },
    "zh_Hant": {
      "memoryEntitlements":
          "MeloNX 無法啟動：此簽章安裝缺少必要的記憶體權限。請使用支援這些權限的簽章工具與佈建描述檔，啟用 Increased Memory Limit（Get More RAM），並在裝置需要時啟用 Extended Virtual Addressing。重新簽章並安裝 RewindBox 後再試。這些權限無法在應用程式內啟用。",
      "entitlementCheckFailed":
          "無法驗證簽章權限。MeloNX 將保持封鎖狀態。請重新開啟 RewindBox 或檢查簽章設定。",
      "libraryRestartRequired": "啟動 Switch 遊戲前，請關閉並重新開啟 RewindBox，以載入已移轉的資料。",
    },
  };
  static String text(Locale locale, String key) {
    final traditional =
        locale.languageCode == 'zh' &&
        (locale.scriptCode == 'Hant' ||
            const {'TW', 'HK', 'MO'}.contains(locale.countryCode));
    return (values[traditional ? 'zh_Hant' : locale.languageCode] ??
            values['en']!)[key] ??
        values['en']!['entitlementCheckFailed']!;
  }
}
