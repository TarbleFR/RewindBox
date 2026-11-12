import 'package:flutter/widgets.dart';

/// Localized labels for the RewindBox legal/credits surface.
///
/// Project names and license identifiers intentionally remain untranslated.
/// The surrounding UI covers every locale offered by RewindBox.
abstract final class LegalCreditsLocale {
  static const Map<String, String> _embeddedCoreLicenses = {
    'de': 'Integrierte Kerne: Jeder Kern behält seine eigene Lizenz.',
    'en': 'Embedded cores: each core retains its own license.',
    'es': 'Núcleos integrados: cada núcleo conserva su propia licencia.',
    'fr': 'Cœurs embarqués : chaque cœur conserve sa propre licence.',
    'id': 'Core bawaan: setiap core tetap memiliki lisensinya sendiri.',
    'it': 'Core integrati: ogni core mantiene la propria licenza.',
    'ja': '内蔵コア：各コアにはそれぞれのライセンスが適用されます。',
    'ko': '내장 코어: 각 코어는 고유한 라이선스를 유지합니다.',
    'pt': 'Núcleos integrados: cada núcleo mantém sua própria licença.',
    'ru': 'Встроенные ядра: каждое ядро сохраняет свою лицензию.',
    'zh': '内置核心：每个核心均保留其自身许可。',
    'zh_Hant': '內建核心：每個核心均保留其自身授權。',
  };

  static String embeddedCoreLicenses(BuildContext context) =>
      _lookup(_embeddedCoreLicenses, context);

  static const Map<String, String> _cardTitles = {
    'de': 'Open-Source-Lizenzen & Danksagungen',
    'en': 'Open-source licenses & credits',
    'es': 'Licencias de código abierto y créditos',
    'fr': 'Licences open source et crédits',
    'id': 'Lisensi sumber terbuka & kredit',
    'it': 'Licenze open source e crediti',
    'ja': 'オープンソースライセンスとクレジット',
    'ko': '오픈 소스 라이선스 및 크레딧',
    'pt': 'Licenças de código aberto e créditos',
    'ru': 'Лицензии открытого ПО и авторы',
    'zh': '开源许可与致谢',
    'zh_Hant': '開源授權與致謝',
  };

  static const Map<String, String> _cardDescriptions = {
    'de': 'Integrierte Projekte, Autoren, Lizenzen und Quellcode',
    'en': 'Embedded projects, authors, licenses and source',
    'es': 'Proyectos integrados, autores, licencias y código fuente',
    'fr': 'Projets intégrés, auteurs, licences et sources',
    'id': 'Proyek terintegrasi, pembuat, lisensi, dan sumber',
    'it': 'Progetti integrati, autori, licenze e sorgenti',
    'ja': '統合プロジェクト、作者、ライセンス、ソース',
    'ko': '통합 프로젝트, 제작자, 라이선스 및 소스',
    'pt': 'Projetos integrados, autores, licenças e código-fonte',
    'ru': 'Встроенные проекты, авторы, лицензии и исходники',
    'zh': '集成项目、作者、许可与源代码',
    'zh_Hant': '整合專案、作者、授權與原始碼',
  };

  static const Map<String, String> _dialogTitles = {
    'de': 'Lizenzen & Danksagungen',
    'en': 'Licenses & credits',
    'es': 'Licencias y créditos',
    'fr': 'Licences et crédits',
    'id': 'Lisensi & kredit',
    'it': 'Licenze e crediti',
    'ja': 'ライセンスとクレジット',
    'ko': '라이선스 및 크레딧',
    'pt': 'Licenças e créditos',
    'ru': 'Лицензии и авторы',
    'zh': '许可与致谢',
    'zh_Hant': '授權與致謝',
  };

  static const Map<String, String> _intros = {
    'de': 'RewindBox baut auf vielen Open-Source-Projekten auf. Jede Komponente behält ihre eigene Lizenz und Urheberschaft. Die Nennung bedeutet keine Empfehlung durch die jeweiligen Projekte.',
    'en': 'RewindBox builds on many open-source projects. Every component keeps its own license and authorship. Attribution does not imply endorsement by those projects.',
    'es': 'RewindBox se basa en numerosos proyectos de código abierto. Cada componente conserva su propia licencia y autoría. La atribución no implica respaldo de esos proyectos.',
    'fr': 'RewindBox s’appuie sur de nombreux projets open source. Chaque composant conserve sa propre licence et ses auteurs. Leur mention n’implique aucune approbation de leur part.',
    'id': 'RewindBox dibangun di atas banyak proyek sumber terbuka. Setiap komponen tetap memiliki lisensi dan kepengarangan masing-masing. Atribusi tidak berarti dukungan dari proyek tersebut.',
    'it': 'RewindBox si basa su numerosi progetti open source. Ogni componente conserva la propria licenza e paternità. L’attribuzione non implica approvazione da parte di tali progetti.',
    'ja': 'RewindBox は多くのオープンソースプロジェクトを基盤としています。各コンポーネントのライセンスと作者表記はそのまま維持され、記載は各プロジェクトによる承認を意味しません。',
    'ko': 'RewindBox는 여러 오픈 소스 프로젝트를 기반으로 합니다. 각 구성 요소의 라이선스와 저작자 표시는 그대로 유지되며, 표기는 해당 프로젝트의 보증을 의미하지 않습니다.',
    'pt': 'O RewindBox baseia-se em vários projetos de código aberto. Cada componente mantém sua própria licença e autoria. A atribuição não implica endosso desses projetos.',
    'ru': 'RewindBox использует множество проектов с открытым исходным кодом. Каждый компонент сохраняет свою лицензию и авторство. Указание авторства не означает одобрения со стороны этих проектов.',
    'zh': 'RewindBox 基于多个开源项目构建。每个组件均保留其自身许可和作者信息。署名并不代表相关项目对 RewindBox 的认可。',
    'zh_Hant': 'RewindBox 建構於多個開源專案之上。每個元件均保留其自身授權與作者資訊。署名不代表相關專案對 RewindBox 的認可。',
  };

  // Free software, no warranty, source; no affiliation with console makers;
  // no game, BIOS, firmware or key included.
  static const Map<String, String> _disclaimers = {
    'de':
        'RewindBox ist freie Software unter der GNU GPL Version 3 oder später und wird ohne jede Gewährleistung bereitgestellt; der Quellcode ist auf github.com/TarbleFR/RewindBox veröffentlicht. RewindBox ist nicht mit Nintendo, Sony Interactive Entertainment, Microsoft, Sega oder einem anderen Konsolenhersteller verbunden und wird von ihnen weder unterstützt noch gesponsert; ihre Namen und Marken gehören ihren Inhabern und dienen nur zur Bezeichnung kompatibler Systeme. Es sind keine Spiele, BIOS, Firmware oder Schlüssel enthalten: Verwende nur Inhalte, die du rechtmäßig nutzen darfst.',
    'en':
        'RewindBox is free software under the GNU GPL version 3 or later, provided without any warranty; its source is published at github.com/TarbleFR/RewindBox. It is not affiliated with, endorsed or sponsored by Nintendo, Sony Interactive Entertainment, Microsoft, Sega or any other console maker; their names and trademarks belong to their owners and only identify compatible systems. No game, BIOS, firmware or key is included: use only content you are legally entitled to use.',
    'es':
        'RewindBox es software libre bajo la GNU GPL versión 3 o posterior y se ofrece sin ninguna garantía; su código fuente está publicado en github.com/TarbleFR/RewindBox. No está afiliado, respaldado ni patrocinado por Nintendo, Sony Interactive Entertainment, Microsoft, Sega ni ningún otro fabricante de consolas; sus nombres y marcas pertenecen a sus titulares y solo identifican los sistemas compatibles. No incluye juegos, BIOS, firmware ni claves: usa solo contenido que tengas derecho a usar legalmente.',
    'fr':
        'RewindBox est un logiciel libre sous GNU GPL version 3 ou ultérieure, fourni sans aucune garantie ; son code source est publié sur github.com/TarbleFR/RewindBox. Il n’est ni affilié, ni approuvé, ni sponsorisé par Nintendo, Sony Interactive Entertainment, Microsoft, Sega ou tout autre fabricant de consoles ; leurs noms et marques appartiennent à leurs titulaires et servent uniquement à désigner les systèmes compatibles. Aucun jeu, BIOS, firmware ni clé n’est inclus : n’utilisez que des contenus que vous avez légalement le droit d’utiliser.',
    'id':
        'RewindBox adalah perangkat lunak bebas di bawah GNU GPL versi 3 atau yang lebih baru, disediakan tanpa jaminan apa pun; kode sumbernya diterbitkan di github.com/TarbleFR/RewindBox. RewindBox tidak berafiliasi dengan, tidak didukung, dan tidak disponsori oleh Nintendo, Sony Interactive Entertainment, Microsoft, Sega, atau produsen konsol lainnya; nama dan merek dagang mereka milik pemiliknya dan hanya menunjukkan sistem yang kompatibel. Tidak ada game, BIOS, firmware, atau kunci yang disertakan: gunakan hanya konten yang secara sah boleh Anda gunakan.',
    'it':
        'RewindBox è software libero sotto la GNU GPL versione 3 o successiva, fornito senza alcuna garanzia; il codice sorgente è pubblicato su github.com/TarbleFR/RewindBox. Non è affiliato, approvato né sponsorizzato da Nintendo, Sony Interactive Entertainment, Microsoft, Sega o altri produttori di console; i loro nomi e marchi appartengono ai rispettivi titolari e servono solo a indicare i sistemi compatibili. Non sono inclusi giochi, BIOS, firmware né chiavi: usa solo contenuti che hai il diritto legale di usare.',
    'ja':
        'RewindBox は GNU GPL バージョン 3 以降のもとで提供されるフリーソフトウェアで、いかなる保証もありません。ソースコードは github.com/TarbleFR/RewindBox で公開されています。Nintendo、Sony Interactive Entertainment、Microsoft、Sega その他のゲーム機メーカーとは提携しておらず、承認や支援も受けていません。各社の名称と商標はそれぞれの権利者に帰属し、対応システムを示すためにのみ使用しています。ゲーム、BIOS、ファームウェア、キーは含まれていません。法的に使用が認められたコンテンツのみを使用してください。',
    'ko':
        'RewindBox는 GNU GPL 버전 3 이상에 따른 자유 소프트웨어이며 어떠한 보증도 없이 제공됩니다. 소스 코드는 github.com/TarbleFR/RewindBox에 공개되어 있습니다. Nintendo, Sony Interactive Entertainment, Microsoft, Sega 또는 기타 콘솔 제조사와 제휴하거나 그들로부터 승인 또는 후원을 받지 않았습니다. 해당 이름과 상표는 각 소유자에게 있으며 호환 시스템을 표시하는 용도로만 사용됩니다. 게임, BIOS, 펌웨어, 키는 포함되어 있지 않습니다. 합법적으로 사용할 권리가 있는 콘텐츠만 사용하세요.',
    'pt':
        'O RewindBox é software livre sob a GNU GPL versão 3 ou posterior e é fornecido sem qualquer garantia; o código-fonte está publicado em github.com/TarbleFR/RewindBox. Não é afiliado, endossado nem patrocinado pela Nintendo, Sony Interactive Entertainment, Microsoft, Sega ou qualquer outro fabricante de consoles; seus nomes e marcas pertencem aos respectivos titulares e apenas identificam os sistemas compatíveis. Nenhum jogo, BIOS, firmware ou chave está incluído: use apenas conteúdo que você tem o direito legal de usar.',
    'ru':
        'RewindBox — свободное программное обеспечение по лицензии GNU GPL версии 3 или более поздней, предоставляемое без каких-либо гарантий; исходный код опубликован на github.com/TarbleFR/RewindBox. Приложение не связано с Nintendo, Sony Interactive Entertainment, Microsoft, Sega или другими производителями консолей и не одобрено и не спонсируется ими; их названия и товарные знаки принадлежат правообладателям и лишь обозначают совместимые системы. Игры, BIOS, прошивки и ключи не входят в комплект: используйте только контент, который вы вправе использовать законно.',
    'zh':
        'RewindBox 是依据 GNU GPL 第 3 版或更高版本发布的自由软件，不提供任何担保；其源代码发布于 github.com/TarbleFR/RewindBox。RewindBox 与 Nintendo、Sony Interactive Entertainment、Microsoft、Sega 或任何其他游戏机厂商均无关联，也未获得其认可或赞助；相关名称和商标归其各自所有者所有，仅用于标识兼容的系统。不包含任何游戏、BIOS、固件或密钥：请仅使用您有合法权利使用的内容。',
    'zh_Hant':
        'RewindBox 是依據 GNU GPL 第 3 版或更新版本發布的自由軟體，不提供任何擔保；其原始碼發布於 github.com/TarbleFR/RewindBox。RewindBox 與 Nintendo、Sony Interactive Entertainment、Microsoft、Sega 或任何其他遊戲主機廠商均無關聯，亦未獲其認可或贊助；相關名稱與商標歸其各自所有者所有，僅用於標示相容的系統。不包含任何遊戲、BIOS、韌體或金鑰：請僅使用您有合法權利使用的內容。',
  };

  static const Map<String, String> _fullRecords = {
    'de': 'Vollständige Hinweise und Quellen',
    'en': 'Full notices and source records',
    'es': 'Avisos completos y registros de fuentes',
    'fr': 'Notices complètes et sources',
    'id': 'Pemberitahuan lengkap dan catatan sumber',
    'it': 'Avvisi completi e registri sorgente',
    'ja': '完全な通知とソース記録',
    'ko': '전체 고지 및 소스 기록',
    'pt': 'Avisos completos e registros de fonte',
    'ru': 'Полные уведомления и сведения об исходниках',
    'zh': '完整声明与源代码记录',
    'zh_Hant': '完整聲明與原始碼記錄',
  };

  static const Map<String, String> _closeLabels = {
    'de': 'Schließen',
    'en': 'Close',
    'es': 'Cerrar',
    'fr': 'Fermer',
    'id': 'Tutup',
    'it': 'Chiudi',
    'ja': '閉じる',
    'ko': '닫기',
    'pt': 'Fechar',
    'ru': 'Закрыть',
    'zh': '关闭',
    'zh_Hant': '關閉',
  };

  static const Map<String, String> _sourceLabels = {
    'de': 'Quellcode',
    'en': 'Source',
    'es': 'Código fuente',
    'fr': 'Sources',
    'id': 'Sumber',
    'it': 'Sorgente',
    'ja': 'ソース',
    'ko': '소스',
    'pt': 'Código-fonte',
    'ru': 'Исходный код',
    'zh': '源代码',
    'zh_Hant': '原始碼',
  };

  static const Map<String, String> _licenseDocumentLabels = {
    'de': 'Lizenzdokument',
    'en': 'License document',
    'es': 'Documento de licencia',
    'fr': 'Document de licence',
    'id': 'Dokumen lisensi',
    'it': 'Documento di licenza',
    'ja': 'ライセンス文書',
    'ko': '라이선스 문서',
    'pt': 'Documento de licença',
    'ru': 'Текст лицензии',
    'zh': '许可文档',
    'zh_Hant': '授權文件',
  };

  static String cardTitle(BuildContext context) => _lookup(_cardTitles, context);
  static String cardDescription(BuildContext context) =>
      _lookup(_cardDescriptions, context);
  static String dialogTitle(BuildContext context) =>
      _lookup(_dialogTitles, context);
  static String intro(BuildContext context) => _lookup(_intros, context);
  static String disclaimer(BuildContext context) =>
      _lookup(_disclaimers, context);
  static String fullRecord(BuildContext context) =>
      _lookup(_fullRecords, context);
  static String close(BuildContext context) => _lookup(_closeLabels, context);
  static String source(BuildContext context) => _lookup(_sourceLabels, context);
  static String licenseDocument(BuildContext context) =>
      _lookup(_licenseDocumentLabels, context);

  static String _lookup(Map<String, String> values, BuildContext context) {
    final locale = Localizations.localeOf(context);
    return values[_localeKey(locale)] ?? values['en']!;
  }

  static String _localeKey(Locale locale) {
    if (locale.languageCode == 'zh') {
      final script = locale.scriptCode?.toLowerCase();
      final country = locale.countryCode?.toUpperCase();
      if (script == 'hant' ||
          country == 'TW' ||
          country == 'HK' ||
          country == 'MO') {
        return 'zh_Hant';
      }
    }
    return locale.languageCode;
  }
}
