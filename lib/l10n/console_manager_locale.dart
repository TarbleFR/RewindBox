import 'package:flutter/widgets.dart';

/// Texts of the console management of Build 448 in NeoStation's twelve
/// languages: the Consoles tab (visibility and built-in engine of every
/// console, "Show all", "Restore defaults"), Settings › General › "Use
/// built-in emulators", and the launch messages of a console whose built-in
/// engine is off. Console, engine and app names are product names, inserted
/// as they are; raw technical details stay apart, untranslated.
abstract final class ConsoleManagerLocale {
  static const tabTitle = 'tabTitle';
  static const tabIntro = 'tabIntro';
  static const sectionEmbedded = 'sectionEmbedded';
  static const sectionExternal = 'sectionExternal';
  static const filterAll = 'filterAll';
  static const filterShown = 'filterShown';
  static const filterHidden = 'filterHidden';
  static const visibleLabel = 'visibleLabel';
  static const engineLabel = 'engineLabel';
  static const engineBuiltIn = 'engineBuiltIn';
  static const engineExternal = 'engineExternal';
  static const fallbackRetroArch = 'fallbackRetroArch';
  static const fallbackRetroArchPs2 = 'fallbackRetroArchPs2';
  static const fallbackNone = 'fallbackNone';
  static const stateShown = 'stateShown';
  static const stateHidden = 'stateHidden';
  static const stateAbsent = 'stateAbsent';
  static const unavailable = 'unavailable';
  static const globalOff = 'globalOff';
  static const showAll = 'showAll';
  static const showAllTitle = 'showAllTitle';
  static const showAllBody = 'showAllBody';
  static const showAllDone = 'showAllDone';
  static const nothingToShow = 'nothingToShow';
  static const restoreDefaults = 'restoreDefaults';
  static const restoreTitle = 'restoreTitle';
  static const restoreBody = 'restoreBody';
  static const restoreDone = 'restoreDone';
  static const changeFailed = 'changeFailed';
  static const noMatch = 'noMatch';
  static const useEmbeddedTitle = 'useEmbeddedTitle';
  static const useEmbeddedOn = 'useEmbeddedOn';
  static const useEmbeddedOff = 'useEmbeddedOff';
  static const launchEngineOff = 'launchEngineOff';
  static const launchEngineOffRetroArch = 'launchEngineOffRetroArch';
  static const launchMelonxFailed = 'launchMelonxFailed';
  static const launchArmsx2Failed = 'launchArmsx2Failed';

  static const Map<String, Map<String, String>> values = {
    'en': {
      tabTitle: 'Consoles',
      tabIntro:
          'Choose which consoles appear in the main menu and whether their games run in NeoStation’s built-in engines. A hidden console keeps its games, covers, saves and settings.',
      sectionEmbedded: 'Built-in engines',
      sectionExternal: 'External apps',
      filterAll: 'All',
      filterShown: 'In the main menu',
      filterHidden: 'Hidden',
      visibleLabel: 'Main menu',
      engineLabel: 'Built-in engine',
      engineBuiltIn: 'Built-in engine: {engine}',
      engineExternal: 'External app: {app}',
      fallbackRetroArch: 'Engine off: its games open in the RetroArch app.',
      fallbackRetroArchPs2:
          'Engine off: only the games outside NeoStation’s ARMSX2 folder open in the RetroArch app.',
      fallbackNone:
          'Engine off: its games cannot be launched, no external app runs them on iOS.',
      stateShown: 'In the main menu: {systems}',
      stateHidden: 'Hidden from the main menu: {systems}',
      stateAbsent: 'Not in the main menu (no games yet)',
      unavailable: 'Not included in this version of NeoStation',
      globalOff:
          'Built-in emulators are off in Settings › General: every game opens in an external app. Each console keeps its own setting.',
      showAll: 'Show all',
      showAllTitle: 'Show every console?',
      showAllBody:
          '{count} consoles will appear in the main menu, including those without games.',
      showAllDone: '{count} consoles shown in the main menu.',
      nothingToShow: 'Every console is already in the main menu.',
      restoreDefaults: 'Restore defaults',
      restoreTitle: 'Restore the defaults?',
      restoreBody:
          'Consoles with games are shown again, consoles added without games leave the main menu, and every console’s built-in engine is turned back on. Games, covers, saves and settings are kept.',
      restoreDone: 'Defaults restored.',
      changeFailed: 'The change could not be saved ({error}).',
      noMatch: 'No console matches this filter.',
      useEmbeddedTitle: 'Use built-in emulators',
      useEmbeddedOn:
          'Games run in NeoStation’s built-in engines when their console allows it (Consoles tab).',
      useEmbeddedOff:
          'Frontend only: every game opens in an external app, RetroArch first. The built-in engines, their saves and settings are kept.',
      launchEngineOff:
          'The built-in engine of {console} is off, and no external app can run its games on iOS. Turn it back on in the Consoles tab or in Settings › General.',
      launchEngineOffRetroArch:
          'The built-in engine of {console} is off, and the RetroArch app could not open this game. Install RetroArch and keep its library synced in NeoStation, or turn the built-in engine back on.',
      launchMelonxFailed:
          'This Nintendo Switch game could not be launched in MeloNX.',
      launchArmsx2Failed:
          'This PlayStation 2 game could not be launched in ARMSX2.',
    },
    'fr': {
      tabTitle: 'Consoles',
      tabIntro:
          'Choisissez les consoles affichées dans le menu principal et si leurs jeux tournent dans les moteurs intégrés de NeoStation. Une console masquée conserve ses jeux, jaquettes, sauvegardes et réglages.',
      sectionEmbedded: 'Moteurs intégrés',
      sectionExternal: 'Applications externes',
      filterAll: 'Toutes',
      filterShown: 'Dans le menu principal',
      filterHidden: 'Masquées',
      visibleLabel: 'Menu principal',
      engineLabel: 'Moteur intégré',
      engineBuiltIn: 'Moteur intégré : {engine}',
      engineExternal: 'Application externe : {app}',
      fallbackRetroArch:
          'Moteur désactivé : ses jeux s’ouvrent dans l’application RetroArch.',
      fallbackRetroArchPs2:
          'Moteur désactivé : seuls les jeux hors du dossier ARMSX2 de NeoStation s’ouvrent dans l’application RetroArch.',
      fallbackNone:
          'Moteur désactivé : ses jeux ne peuvent pas être lancés, aucune application externe ne les fait tourner sur iOS.',
      stateShown: 'Dans le menu principal : {systems}',
      stateHidden: 'Masquée dans le menu principal : {systems}',
      stateAbsent: 'Absente du menu principal (aucun jeu pour l’instant)',
      unavailable: 'Non incluse dans cette version de NeoStation',
      globalOff:
          'Les émulateurs intégrés sont désactivés dans Paramètres › Général : chaque jeu s’ouvre dans une application externe. Chaque console conserve son propre réglage.',
      showAll: 'Tout afficher',
      showAllTitle: 'Afficher toutes les consoles ?',
      showAllBody:
          '{count} consoles apparaîtront dans le menu principal, y compris celles sans jeu.',
      showAllDone: '{count} consoles affichées dans le menu principal.',
      nothingToShow: 'Toutes les consoles sont déjà dans le menu principal.',
      restoreDefaults: 'Rétablir par défaut',
      restoreTitle: 'Rétablir les réglages par défaut ?',
      restoreBody:
          'Les consoles qui ont des jeux sont de nouveau affichées, celles ajoutées sans jeu quittent le menu principal et le moteur intégré de chaque console est réactivé. Les jeux, jaquettes, sauvegardes et réglages sont conservés.',
      restoreDone: 'Réglages par défaut rétablis.',
      changeFailed: 'La modification n’a pas pu être enregistrée ({error}).',
      noMatch: 'Aucune console ne correspond à ce filtre.',
      useEmbeddedTitle: 'Utiliser les émulateurs intégrés',
      useEmbeddedOn:
          'Les jeux tournent dans les moteurs intégrés de NeoStation lorsque leur console le permet (onglet Consoles).',
      useEmbeddedOff:
          'Frontend uniquement : chaque jeu s’ouvre dans une application externe, RetroArch en priorité. Les moteurs intégrés, leurs sauvegardes et réglages sont conservés.',
      launchEngineOff:
          'Le moteur intégré de {console} est désactivé et aucune application externe ne fait tourner ses jeux sur iOS. Réactivez-le dans l’onglet Consoles ou dans Paramètres › Général.',
      launchEngineOffRetroArch:
          'Le moteur intégré de {console} est désactivé et l’application RetroArch n’a pas pu ouvrir ce jeu. Installez RetroArch et gardez sa bibliothèque synchronisée dans NeoStation, ou réactivez le moteur intégré.',
      launchMelonxFailed:
          'Ce jeu Nintendo Switch n’a pas pu être lancé dans MeloNX.',
      launchArmsx2Failed:
          'Ce jeu PlayStation 2 n’a pas pu être lancé dans ARMSX2.',
    },
    'de': {
      tabTitle: 'Konsolen',
      tabIntro:
          'Wähle, welche Konsolen im Hauptmenü erscheinen und ob ihre Spiele in den integrierten Engines von NeoStation laufen. Eine ausgeblendete Konsole behält ihre Spiele, Cover, Spielstände und Einstellungen.',
      sectionEmbedded: 'Integrierte Engines',
      sectionExternal: 'Externe Apps',
      filterAll: 'Alle',
      filterShown: 'Im Hauptmenü',
      filterHidden: 'Ausgeblendet',
      visibleLabel: 'Hauptmenü',
      engineLabel: 'Integrierte Engine',
      engineBuiltIn: 'Integrierte Engine: {engine}',
      engineExternal: 'Externe App: {app}',
      fallbackRetroArch:
          'Engine aus: Ihre Spiele öffnen sich in der RetroArch-App.',
      fallbackRetroArchPs2:
          'Engine aus: Nur Spiele außerhalb des ARMSX2-Ordners von NeoStation öffnen sich in der RetroArch-App.',
      fallbackNone:
          'Engine aus: Ihre Spiele können nicht gestartet werden, keine externe App führt sie unter iOS aus.',
      stateShown: 'Im Hauptmenü: {systems}',
      stateHidden: 'Im Hauptmenü ausgeblendet: {systems}',
      stateAbsent: 'Nicht im Hauptmenü (noch keine Spiele)',
      unavailable: 'In dieser NeoStation-Version nicht enthalten',
      globalOff:
          'Integrierte Emulatoren sind unter Einstellungen › Allgemein ausgeschaltet: Jedes Spiel öffnet sich in einer externen App. Jede Konsole behält ihre eigene Einstellung.',
      showAll: 'Alle anzeigen',
      showAllTitle: 'Alle Konsolen anzeigen?',
      showAllBody:
          '{count} Konsolen erscheinen im Hauptmenü, auch solche ohne Spiele.',
      showAllDone: '{count} Konsolen im Hauptmenü angezeigt.',
      nothingToShow: 'Alle Konsolen sind bereits im Hauptmenü.',
      restoreDefaults: 'Standard wiederherstellen',
      restoreTitle: 'Standardeinstellungen wiederherstellen?',
      restoreBody:
          'Konsolen mit Spielen werden wieder angezeigt, ohne Spiele hinzugefügte Konsolen verlassen das Hauptmenü und die integrierte Engine jeder Konsole wird wieder eingeschaltet. Spiele, Cover, Spielstände und Einstellungen bleiben erhalten.',
      restoreDone: 'Standardeinstellungen wiederhergestellt.',
      changeFailed: 'Die Änderung konnte nicht gespeichert werden ({error}).',
      noMatch: 'Keine Konsole entspricht diesem Filter.',
      useEmbeddedTitle: 'Integrierte Emulatoren verwenden',
      useEmbeddedOn:
          'Spiele laufen in den integrierten Engines von NeoStation, wenn ihre Konsole es erlaubt (Tab Konsolen).',
      useEmbeddedOff:
          'Nur Frontend: Jedes Spiel öffnet sich in einer externen App, zuerst RetroArch. Die integrierten Engines, ihre Spielstände und Einstellungen bleiben erhalten.',
      launchEngineOff:
          'Die integrierte Engine von {console} ist ausgeschaltet, und keine externe App führt ihre Spiele unter iOS aus. Schalte sie im Tab Konsolen oder unter Einstellungen › Allgemein wieder ein.',
      launchEngineOffRetroArch:
          'Die integrierte Engine von {console} ist ausgeschaltet, und die RetroArch-App konnte dieses Spiel nicht öffnen. Installiere RetroArch und halte seine Bibliothek in NeoStation synchronisiert oder schalte die integrierte Engine wieder ein.',
      launchMelonxFailed:
          'Dieses Nintendo-Switch-Spiel konnte nicht in MeloNX gestartet werden.',
      launchArmsx2Failed:
          'Dieses PlayStation-2-Spiel konnte nicht in ARMSX2 gestartet werden.',
    },
    'es': {
      tabTitle: 'Consolas',
      tabIntro:
          'Elige qué consolas aparecen en el menú principal y si sus juegos se ejecutan en los motores integrados de NeoStation. Una consola oculta conserva sus juegos, portadas, partidas guardadas y ajustes.',
      sectionEmbedded: 'Motores integrados',
      sectionExternal: 'Aplicaciones externas',
      filterAll: 'Todas',
      filterShown: 'En el menú principal',
      filterHidden: 'Ocultas',
      visibleLabel: 'Menú principal',
      engineLabel: 'Motor integrado',
      engineBuiltIn: 'Motor integrado: {engine}',
      engineExternal: 'Aplicación externa: {app}',
      fallbackRetroArch:
          'Motor desactivado: sus juegos se abren en la aplicación RetroArch.',
      fallbackRetroArchPs2:
          'Motor desactivado: solo los juegos fuera de la carpeta ARMSX2 de NeoStation se abren en la aplicación RetroArch.',
      fallbackNone:
          'Motor desactivado: sus juegos no se pueden iniciar, ninguna aplicación externa los ejecuta en iOS.',
      stateShown: 'En el menú principal: {systems}',
      stateHidden: 'Oculta en el menú principal: {systems}',
      stateAbsent: 'No está en el menú principal (aún sin juegos)',
      unavailable: 'No incluida en esta versión de NeoStation',
      globalOff:
          'Los emuladores integrados están desactivados en Ajustes › General: cada juego se abre en una aplicación externa. Cada consola conserva su propio ajuste.',
      showAll: 'Mostrar todas',
      showAllTitle: '¿Mostrar todas las consolas?',
      showAllBody:
          '{count} consolas aparecerán en el menú principal, incluidas las que no tienen juegos.',
      showAllDone: '{count} consolas mostradas en el menú principal.',
      nothingToShow: 'Todas las consolas ya están en el menú principal.',
      restoreDefaults: 'Restablecer valores predeterminados',
      restoreTitle: '¿Restablecer los valores predeterminados?',
      restoreBody:
          'Las consolas con juegos vuelven a mostrarse, las añadidas sin juegos salen del menú principal y se reactiva el motor integrado de cada consola. Se conservan los juegos, portadas, partidas guardadas y ajustes.',
      restoreDone: 'Valores predeterminados restablecidos.',
      changeFailed: 'No se pudo guardar el cambio ({error}).',
      noMatch: 'Ninguna consola coincide con este filtro.',
      useEmbeddedTitle: 'Usar los emuladores integrados',
      useEmbeddedOn:
          'Los juegos se ejecutan en los motores integrados de NeoStation cuando su consola lo permite (pestaña Consolas).',
      useEmbeddedOff:
          'Solo frontend: cada juego se abre en una aplicación externa, primero RetroArch. Se conservan los motores integrados, sus partidas guardadas y ajustes.',
      launchEngineOff:
          'El motor integrado de {console} está desactivado y ninguna aplicación externa ejecuta sus juegos en iOS. Vuelve a activarlo en la pestaña Consolas o en Ajustes › General.',
      launchEngineOffRetroArch:
          'El motor integrado de {console} está desactivado y la aplicación RetroArch no pudo abrir este juego. Instala RetroArch y mantén su biblioteca sincronizada en NeoStation, o vuelve a activar el motor integrado.',
      launchMelonxFailed:
          'No se pudo iniciar este juego de Nintendo Switch en MeloNX.',
      launchArmsx2Failed:
          'No se pudo iniciar este juego de PlayStation 2 en ARMSX2.',
    },
    'it': {
      tabTitle: 'Console',
      tabIntro:
          'Scegli quali console appaiono nel menu principale e se i loro giochi girano nei motori integrati di NeoStation. Una console nascosta conserva giochi, copertine, salvataggi e impostazioni.',
      sectionEmbedded: 'Motori integrati',
      sectionExternal: 'App esterne',
      filterAll: 'Tutte',
      filterShown: 'Nel menu principale',
      filterHidden: 'Nascoste',
      visibleLabel: 'Menu principale',
      engineLabel: 'Motore integrato',
      engineBuiltIn: 'Motore integrato: {engine}',
      engineExternal: 'App esterna: {app}',
      fallbackRetroArch:
          'Motore disattivato: i suoi giochi si aprono nell’app RetroArch.',
      fallbackRetroArchPs2:
          'Motore disattivato: solo i giochi fuori dalla cartella ARMSX2 di NeoStation si aprono nell’app RetroArch.',
      fallbackNone:
          'Motore disattivato: i suoi giochi non si possono avviare, nessuna app esterna li esegue su iOS.',
      stateShown: 'Nel menu principale: {systems}',
      stateHidden: 'Nascosta nel menu principale: {systems}',
      stateAbsent: 'Non nel menu principale (ancora nessun gioco)',
      unavailable: 'Non inclusa in questa versione di NeoStation',
      globalOff:
          'Gli emulatori integrati sono disattivati in Impostazioni › Generale: ogni gioco si apre in un’app esterna. Ogni console conserva la propria impostazione.',
      showAll: 'Mostra tutte',
      showAllTitle: 'Mostrare tutte le console?',
      showAllBody:
          '{count} console appariranno nel menu principale, comprese quelle senza giochi.',
      showAllDone: '{count} console mostrate nel menu principale.',
      nothingToShow: 'Tutte le console sono già nel menu principale.',
      restoreDefaults: 'Ripristina predefiniti',
      restoreTitle: 'Ripristinare le impostazioni predefinite?',
      restoreBody:
          'Le console con giochi tornano visibili, quelle aggiunte senza giochi lasciano il menu principale e il motore integrato di ogni console viene riattivato. Giochi, copertine, salvataggi e impostazioni vengono conservati.',
      restoreDone: 'Impostazioni predefinite ripristinate.',
      changeFailed: 'Impossibile salvare la modifica ({error}).',
      noMatch: 'Nessuna console corrisponde a questo filtro.',
      useEmbeddedTitle: 'Usa gli emulatori integrati',
      useEmbeddedOn:
          'I giochi girano nei motori integrati di NeoStation quando la loro console lo consente (scheda Console).',
      useEmbeddedOff:
          'Solo frontend: ogni gioco si apre in un’app esterna, prima RetroArch. I motori integrati, i loro salvataggi e le impostazioni vengono conservati.',
      launchEngineOff:
          'Il motore integrato di {console} è disattivato e nessuna app esterna ne esegue i giochi su iOS. Riattivalo nella scheda Console o in Impostazioni › Generale.',
      launchEngineOffRetroArch:
          'Il motore integrato di {console} è disattivato e l’app RetroArch non è riuscita ad aprire questo gioco. Installa RetroArch e mantieni la sua libreria sincronizzata in NeoStation, oppure riattiva il motore integrato.',
      launchMelonxFailed:
          'Impossibile avviare questo gioco Nintendo Switch in MeloNX.',
      launchArmsx2Failed:
          'Impossibile avviare questo gioco PlayStation 2 in ARMSX2.',
    },
    'pt': {
      tabTitle: 'Consoles',
      tabIntro:
          'Escolha quais consoles aparecem no menu principal e se os jogos deles rodam nos motores integrados do NeoStation. Um console oculto mantém seus jogos, capas, saves e configurações.',
      sectionEmbedded: 'Motores integrados',
      sectionExternal: 'Apps externos',
      filterAll: 'Todos',
      filterShown: 'No menu principal',
      filterHidden: 'Ocultos',
      visibleLabel: 'Menu principal',
      engineLabel: 'Motor integrado',
      engineBuiltIn: 'Motor integrado: {engine}',
      engineExternal: 'App externo: {app}',
      fallbackRetroArch:
          'Motor desativado: os jogos dele abrem no app RetroArch.',
      fallbackRetroArchPs2:
          'Motor desativado: só os jogos fora da pasta ARMSX2 do NeoStation abrem no app RetroArch.',
      fallbackNone:
          'Motor desativado: os jogos dele não podem ser iniciados, nenhum app externo os executa no iOS.',
      stateShown: 'No menu principal: {systems}',
      stateHidden: 'Oculto no menu principal: {systems}',
      stateAbsent: 'Fora do menu principal (ainda sem jogos)',
      unavailable: 'Não incluído nesta versão do NeoStation',
      globalOff:
          'Os emuladores integrados estão desativados em Configurações › Geral: cada jogo abre em um app externo. Cada console mantém sua própria configuração.',
      showAll: 'Mostrar todos',
      showAllTitle: 'Mostrar todos os consoles?',
      showAllBody:
          '{count} consoles aparecerão no menu principal, inclusive os que não têm jogos.',
      showAllDone: '{count} consoles mostrados no menu principal.',
      nothingToShow: 'Todos os consoles já estão no menu principal.',
      restoreDefaults: 'Restaurar padrões',
      restoreTitle: 'Restaurar as configurações padrão?',
      restoreBody:
          'Os consoles com jogos voltam a aparecer, os adicionados sem jogos saem do menu principal e o motor integrado de cada console é reativado. Jogos, capas, saves e configurações são mantidos.',
      restoreDone: 'Configurações padrão restauradas.',
      changeFailed: 'Não foi possível salvar a alteração ({error}).',
      noMatch: 'Nenhum console corresponde a este filtro.',
      useEmbeddedTitle: 'Usar os emuladores integrados',
      useEmbeddedOn:
          'Os jogos rodam nos motores integrados do NeoStation quando o console deles permite (aba Consoles).',
      useEmbeddedOff:
          'Somente frontend: cada jogo abre em um app externo, primeiro o RetroArch. Os motores integrados, seus saves e configurações são mantidos.',
      launchEngineOff:
          'O motor integrado de {console} está desativado e nenhum app externo executa os jogos dele no iOS. Reative-o na aba Consoles ou em Configurações › Geral.',
      launchEngineOffRetroArch:
          'O motor integrado de {console} está desativado e o app RetroArch não conseguiu abrir este jogo. Instale o RetroArch e mantenha a biblioteca dele sincronizada no NeoStation, ou reative o motor integrado.',
      launchMelonxFailed:
          'Não foi possível iniciar este jogo de Nintendo Switch no MeloNX.',
      launchArmsx2Failed:
          'Não foi possível iniciar este jogo de PlayStation 2 no ARMSX2.',
    },
    'ru': {
      tabTitle: 'Консоли',
      tabIntro:
          'Выберите, какие консоли показываются в главном меню и запускаются ли их игры во встроенных движках NeoStation. Скрытая консоль сохраняет игры, обложки, сохранения и настройки.',
      sectionEmbedded: 'Встроенные движки',
      sectionExternal: 'Внешние приложения',
      filterAll: 'Все',
      filterShown: 'В главном меню',
      filterHidden: 'Скрытые',
      visibleLabel: 'Главное меню',
      engineLabel: 'Встроенный движок',
      engineBuiltIn: 'Встроенный движок: {engine}',
      engineExternal: 'Внешнее приложение: {app}',
      fallbackRetroArch:
          'Движок выключен: её игры открываются в приложении RetroArch.',
      fallbackRetroArchPs2:
          'Движок выключен: в приложении RetroArch открываются только игры вне папки ARMSX2 NeoStation.',
      fallbackNone:
          'Движок выключен: её игры нельзя запустить, ни одно внешнее приложение не запускает их на iOS.',
      stateShown: 'В главном меню: {systems}',
      stateHidden: 'Скрыта в главном меню: {systems}',
      stateAbsent: 'Нет в главном меню (пока без игр)',
      unavailable: 'Не входит в эту версию NeoStation',
      globalOff:
          'Встроенные эмуляторы выключены в разделе Настройки › Общие: каждая игра открывается во внешнем приложении. Каждая консоль сохраняет свою настройку.',
      showAll: 'Показать все',
      showAllTitle: 'Показать все консоли?',
      showAllBody:
          'В главном меню появятся консоли ({count}), включая те, где нет игр.',
      showAllDone: 'Показано консолей в главном меню: {count}.',
      nothingToShow: 'Все консоли уже в главном меню.',
      restoreDefaults: 'Восстановить по умолчанию',
      restoreTitle: 'Восстановить настройки по умолчанию?',
      restoreBody:
          'Консоли с играми снова показываются, добавленные без игр консоли убираются из главного меню, а встроенный движок каждой консоли снова включается. Игры, обложки, сохранения и настройки сохраняются.',
      restoreDone: 'Настройки по умолчанию восстановлены.',
      changeFailed: 'Не удалось сохранить изменение ({error}).',
      noMatch: 'Нет консолей, подходящих под этот фильтр.',
      useEmbeddedTitle: 'Использовать встроенные эмуляторы',
      useEmbeddedOn:
          'Игры запускаются во встроенных движках NeoStation, если их консоль это позволяет (вкладка «Консоли»).',
      useEmbeddedOff:
          'Только фронтенд: каждая игра открывается во внешнем приложении, в первую очередь в RetroArch. Встроенные движки, их сохранения и настройки сохраняются.',
      launchEngineOff:
          'Встроенный движок {console} выключен, и ни одно внешнее приложение не запускает её игры на iOS. Включите его на вкладке «Консоли» или в разделе Настройки › Общие.',
      launchEngineOffRetroArch:
          'Встроенный движок {console} выключен, а приложение RetroArch не смогло открыть эту игру. Установите RetroArch и синхронизируйте его библиотеку в NeoStation или снова включите встроенный движок.',
      launchMelonxFailed:
          'Не удалось запустить эту игру Nintendo Switch в MeloNX.',
      launchArmsx2Failed:
          'Не удалось запустить эту игру PlayStation 2 в ARMSX2.',
    },
    'id': {
      tabTitle: 'Konsol',
      tabIntro:
          'Pilih konsol yang muncul di menu utama dan apakah game-nya berjalan di mesin bawaan NeoStation. Konsol yang disembunyikan tetap menyimpan game, sampul, simpanan, dan pengaturannya.',
      sectionEmbedded: 'Mesin bawaan',
      sectionExternal: 'Aplikasi eksternal',
      filterAll: 'Semua',
      filterShown: 'Di menu utama',
      filterHidden: 'Disembunyikan',
      visibleLabel: 'Menu utama',
      engineLabel: 'Mesin bawaan',
      engineBuiltIn: 'Mesin bawaan: {engine}',
      engineExternal: 'Aplikasi eksternal: {app}',
      fallbackRetroArch:
          'Mesin nonaktif: game-nya dibuka di aplikasi RetroArch.',
      fallbackRetroArchPs2:
          'Mesin nonaktif: hanya game di luar folder ARMSX2 NeoStation yang dibuka di aplikasi RetroArch.',
      fallbackNone:
          'Mesin nonaktif: game-nya tidak dapat dijalankan, tidak ada aplikasi eksternal yang menjalankannya di iOS.',
      stateShown: 'Di menu utama: {systems}',
      stateHidden: 'Disembunyikan di menu utama: {systems}',
      stateAbsent: 'Tidak ada di menu utama (belum ada game)',
      unavailable: 'Tidak disertakan di versi NeoStation ini',
      globalOff:
          'Emulator bawaan dinonaktifkan di Pengaturan › Umum: setiap game dibuka di aplikasi eksternal. Setiap konsol tetap menyimpan pengaturannya sendiri.',
      showAll: 'Tampilkan semua',
      showAllTitle: 'Tampilkan semua konsol?',
      showAllBody:
          '{count} konsol akan muncul di menu utama, termasuk yang belum memiliki game.',
      showAllDone: '{count} konsol ditampilkan di menu utama.',
      nothingToShow: 'Semua konsol sudah ada di menu utama.',
      restoreDefaults: 'Pulihkan bawaan',
      restoreTitle: 'Pulihkan pengaturan bawaan?',
      restoreBody:
          'Konsol yang memiliki game ditampilkan lagi, konsol yang ditambahkan tanpa game keluar dari menu utama, dan mesin bawaan setiap konsol diaktifkan kembali. Game, sampul, simpanan, dan pengaturan tetap tersimpan.',
      restoreDone: 'Pengaturan bawaan dipulihkan.',
      changeFailed: 'Perubahan tidak dapat disimpan ({error}).',
      noMatch: 'Tidak ada konsol yang cocok dengan filter ini.',
      useEmbeddedTitle: 'Gunakan emulator bawaan',
      useEmbeddedOn:
          'Game berjalan di mesin bawaan NeoStation jika konsolnya mengizinkan (tab Konsol).',
      useEmbeddedOff:
          'Hanya frontend: setiap game dibuka di aplikasi eksternal, RetroArch lebih dulu. Mesin bawaan, simpanan, dan pengaturannya tetap tersimpan.',
      launchEngineOff:
          'Mesin bawaan {console} nonaktif, dan tidak ada aplikasi eksternal yang menjalankan game-nya di iOS. Aktifkan lagi di tab Konsol atau di Pengaturan › Umum.',
      launchEngineOffRetroArch:
          'Mesin bawaan {console} nonaktif, dan aplikasi RetroArch tidak dapat membuka game ini. Pasang RetroArch dan jaga pustakanya tetap tersinkron di NeoStation, atau aktifkan lagi mesin bawaan.',
      launchMelonxFailed:
          'Game Nintendo Switch ini tidak dapat dijalankan di MeloNX.',
      launchArmsx2Failed:
          'Game PlayStation 2 ini tidak dapat dijalankan di ARMSX2.',
    },
    'ja': {
      tabTitle: 'ゲーム機',
      tabIntro: 'メインメニューに表示するゲーム機と、そのゲームを NeoStation の内蔵エンジンで動かすかどうかを選びます。非表示にしたゲーム機のゲーム、カバー、セーブデータ、設定はそのまま残ります。',
      sectionEmbedded: '内蔵エンジン',
      sectionExternal: '外部アプリ',
      filterAll: 'すべて',
      filterShown: 'メインメニューに表示中',
      filterHidden: '非表示',
      visibleLabel: 'メインメニュー',
      engineLabel: '内蔵エンジン',
      engineBuiltIn: '内蔵エンジン：{engine}',
      engineExternal: '外部アプリ：{app}',
      fallbackRetroArch: 'エンジンオフ：ゲームは RetroArch アプリで開きます。',
      fallbackRetroArchPs2: 'エンジンオフ：NeoStation の ARMSX2 フォルダー外のゲームだけが RetroArch アプリで開きます。',
      fallbackNone: 'エンジンオフ：iOS でこのゲームを動かす外部アプリがないため、起動できません。',
      stateShown: 'メインメニューに表示中：{systems}',
      stateHidden: 'メインメニューで非表示：{systems}',
      stateAbsent: 'メインメニューにありません（ゲームはまだありません）',
      unavailable: 'このバージョンの NeoStation には含まれていません',
      globalOff: '設定 › 全般 で内蔵エミュレーターがオフになっています。すべてのゲームは外部アプリで開きます。各ゲーム機の設定はそのまま残ります。',
      showAll: 'すべて表示',
      showAllTitle: 'すべてのゲーム機を表示しますか？',
      showAllBody: 'ゲームのないものも含め、{count} 台のゲーム機がメインメニューに表示されます。',
      showAllDone: '{count} 台のゲーム機をメインメニューに表示しました。',
      nothingToShow: 'すべてのゲーム機がすでにメインメニューにあります。',
      restoreDefaults: '初期設定に戻す',
      restoreTitle: '初期設定に戻しますか？',
      restoreBody: 'ゲームのあるゲーム機は再び表示され、ゲームなしで追加したゲーム機はメインメニューから外れ、各ゲーム機の内蔵エンジンは再びオンになります。ゲーム、カバー、セーブデータ、設定は残ります。',
      restoreDone: '初期設定に戻しました。',
      changeFailed: '変更を保存できませんでした（{error}）。',
      noMatch: 'このフィルターに合うゲーム機はありません。',
      useEmbeddedTitle: '内蔵エミュレーターを使う',
      useEmbeddedOn: 'ゲーム機が許可していれば、ゲームは NeoStation の内蔵エンジンで動きます（ゲーム機タブ）。',
      useEmbeddedOff: 'フロントエンドのみ：すべてのゲームを外部アプリ（RetroArch を優先）で開きます。内蔵エンジンとそのセーブデータ、設定は残ります。',
      launchEngineOff: '{console} の内蔵エンジンはオフで、iOS でそのゲームを動かす外部アプリはありません。ゲーム機タブまたは 設定 › 全般 で再びオンにしてください。',
      launchEngineOffRetroArch: '{console} の内蔵エンジンはオフで、RetroArch アプリはこのゲームを開けませんでした。RetroArch をインストールして NeoStation でライブラリを同期するか、内蔵エンジンを再びオンにしてください。',
      launchMelonxFailed: 'この Nintendo Switch のゲームを MeloNX で起動できませんでした。',
      launchArmsx2Failed: 'この PlayStation 2 のゲームを ARMSX2 で起動できませんでした。',
    },
    'ko': {
      tabTitle: '콘솔',
      tabIntro: '메인 메뉴에 표시할 콘솔과 해당 게임을 NeoStation 내장 엔진에서 실행할지 선택하세요. 숨긴 콘솔도 게임, 커버, 저장 데이터와 설정은 그대로 유지됩니다.',
      sectionEmbedded: '내장 엔진',
      sectionExternal: '외부 앱',
      filterAll: '전체',
      filterShown: '메인 메뉴에 표시됨',
      filterHidden: '숨김',
      visibleLabel: '메인 메뉴',
      engineLabel: '내장 엔진',
      engineBuiltIn: '내장 엔진: {engine}',
      engineExternal: '외부 앱: {app}',
      fallbackRetroArch: '엔진 꺼짐: 게임이 RetroArch 앱에서 열립니다.',
      fallbackRetroArchPs2: '엔진 꺼짐: NeoStation의 ARMSX2 폴더 밖에 있는 게임만 RetroArch 앱에서 열립니다.',
      fallbackNone: '엔진 꺼짐: iOS에서 이 게임을 실행하는 외부 앱이 없어 실행할 수 없습니다.',
      stateShown: '메인 메뉴에 표시됨: {systems}',
      stateHidden: '메인 메뉴에서 숨김: {systems}',
      stateAbsent: '메인 메뉴에 없음(아직 게임 없음)',
      unavailable: '이 버전의 NeoStation에는 포함되어 있지 않습니다',
      globalOff: '설정 › 일반에서 내장 에뮬레이터가 꺼져 있습니다. 모든 게임이 외부 앱에서 열립니다. 각 콘솔의 설정은 그대로 유지됩니다.',
      showAll: '모두 표시',
      showAllTitle: '모든 콘솔을 표시할까요?',
      showAllBody: '게임이 없는 콘솔을 포함해 {count}개의 콘솔이 메인 메뉴에 표시됩니다.',
      showAllDone: '{count}개의 콘솔을 메인 메뉴에 표시했습니다.',
      nothingToShow: '모든 콘솔이 이미 메인 메뉴에 있습니다.',
      restoreDefaults: '기본값 복원',
      restoreTitle: '기본값으로 복원할까요?',
      restoreBody: '게임이 있는 콘솔은 다시 표시되고, 게임 없이 추가한 콘솔은 메인 메뉴에서 빠지며, 각 콘솔의 내장 엔진이 다시 켜집니다. 게임, 커버, 저장 데이터와 설정은 유지됩니다.',
      restoreDone: '기본값을 복원했습니다.',
      changeFailed: '변경 사항을 저장할 수 없습니다({error}).',
      noMatch: '이 필터에 맞는 콘솔이 없습니다.',
      useEmbeddedTitle: '내장 에뮬레이터 사용',
      useEmbeddedOn: '콘솔이 허용하면 게임이 NeoStation 내장 엔진에서 실행됩니다(콘솔 탭).',
      useEmbeddedOff: '프런트엔드 전용: 모든 게임이 외부 앱(RetroArch 우선)에서 열립니다. 내장 엔진과 저장 데이터, 설정은 유지됩니다.',
      launchEngineOff: '{console}의 내장 엔진이 꺼져 있고 iOS에서 해당 게임을 실행하는 외부 앱이 없습니다. 콘솔 탭이나 설정 › 일반에서 다시 켜세요.',
      launchEngineOffRetroArch: '{console}의 내장 엔진이 꺼져 있고 RetroArch 앱이 이 게임을 열지 못했습니다. RetroArch를 설치하고 NeoStation에서 라이브러리를 동기화하거나 내장 엔진을 다시 켜세요.',
      launchMelonxFailed: '이 Nintendo Switch 게임을 MeloNX에서 실행할 수 없습니다.',
      launchArmsx2Failed: '이 PlayStation 2 게임을 ARMSX2에서 실행할 수 없습니다.',
    },
    'zh': {
      tabTitle: '游戏机',
      tabIntro: '选择哪些游戏机显示在主菜单中，以及它们的游戏是否在 NeoStation 的内置引擎中运行。隐藏的游戏机会保留其游戏、封面、存档和设置。',
      sectionEmbedded: '内置引擎',
      sectionExternal: '外部应用',
      filterAll: '全部',
      filterShown: '在主菜单中',
      filterHidden: '已隐藏',
      visibleLabel: '主菜单',
      engineLabel: '内置引擎',
      engineBuiltIn: '内置引擎：{engine}',
      engineExternal: '外部应用：{app}',
      fallbackRetroArch: '引擎已关闭：其游戏在 RetroArch 应用中打开。',
      fallbackRetroArchPs2: '引擎已关闭：只有 NeoStation 的 ARMSX2 文件夹以外的游戏会在 RetroArch 应用中打开。',
      fallbackNone: '引擎已关闭：iOS 上没有外部应用能运行其游戏，因此无法启动。',
      stateShown: '在主菜单中：{systems}',
      stateHidden: '已在主菜单中隐藏：{systems}',
      stateAbsent: '不在主菜单中（暂无游戏）',
      unavailable: '此版本的 NeoStation 未包含',
      globalOff: '内置模拟器已在 设置 › 常规 中关闭：每个游戏都在外部应用中打开。每台游戏机保留各自的设置。',
      showAll: '全部显示',
      showAllTitle: '显示所有游戏机？',
      showAllBody: '{count} 台游戏机将出现在主菜单中，包括没有游戏的。',
      showAllDone: '已在主菜单中显示 {count} 台游戏机。',
      nothingToShow: '所有游戏机都已在主菜单中。',
      restoreDefaults: '恢复默认',
      restoreTitle: '恢复默认设置？',
      restoreBody: '有游戏的游戏机重新显示，未添加游戏而加入的游戏机离开主菜单，每台游戏机的内置引擎重新开启。游戏、封面、存档和设置都会保留。',
      restoreDone: '已恢复默认设置。',
      changeFailed: '无法保存更改（{error}）。',
      noMatch: '没有符合此筛选条件的游戏机。',
      useEmbeddedTitle: '使用内置模拟器',
      useEmbeddedOn: '在游戏机允许时，游戏在 NeoStation 的内置引擎中运行（游戏机标签页）。',
      useEmbeddedOff: '仅作为前端：每个游戏都在外部应用中打开，优先使用 RetroArch。内置引擎及其存档和设置都会保留。',
      launchEngineOff: '{console} 的内置引擎已关闭，且 iOS 上没有外部应用能运行其游戏。请在游戏机标签页或 设置 › 常规 中重新开启。',
      launchEngineOffRetroArch: '{console} 的内置引擎已关闭，且 RetroArch 应用无法打开此游戏。请安装 RetroArch 并在 NeoStation 中保持其游戏库同步，或重新开启内置引擎。',
      launchMelonxFailed: '无法在 MeloNX 中启动此 Nintendo Switch 游戏。',
      launchArmsx2Failed: '无法在 ARMSX2 中启动此 PlayStation 2 游戏。',
    },
    'zh_Hant': {
      tabTitle: '遊戲機',
      tabIntro: '選擇哪些遊戲機顯示在主選單中，以及它們的遊戲是否在 NeoStation 的內建引擎中執行。隱藏的遊戲機會保留其遊戲、封面、存檔和設定。',
      sectionEmbedded: '內建引擎',
      sectionExternal: '外部應用程式',
      filterAll: '全部',
      filterShown: '在主選單中',
      filterHidden: '已隱藏',
      visibleLabel: '主選單',
      engineLabel: '內建引擎',
      engineBuiltIn: '內建引擎：{engine}',
      engineExternal: '外部應用程式：{app}',
      fallbackRetroArch: '引擎已關閉：其遊戲會在 RetroArch 應用程式中開啟。',
      fallbackRetroArchPs2: '引擎已關閉：只有 NeoStation 的 ARMSX2 資料夾以外的遊戲會在 RetroArch 應用程式中開啟。',
      fallbackNone: '引擎已關閉：iOS 上沒有外部應用程式能執行其遊戲，因此無法啟動。',
      stateShown: '在主選單中：{systems}',
      stateHidden: '已在主選單中隱藏：{systems}',
      stateAbsent: '不在主選單中（尚無遊戲）',
      unavailable: '此版本的 NeoStation 未包含',
      globalOff: '內建模擬器已在 設定 › 一般 中關閉：每個遊戲都會在外部應用程式中開啟。每台遊戲機保留各自的設定。',
      showAll: '全部顯示',
      showAllTitle: '顯示所有遊戲機？',
      showAllBody: '{count} 台遊戲機將出現在主選單中，包括沒有遊戲的。',
      showAllDone: '已在主選單中顯示 {count} 台遊戲機。',
      nothingToShow: '所有遊戲機都已在主選單中。',
      restoreDefaults: '恢復預設',
      restoreTitle: '恢復預設設定？',
      restoreBody: '有遊戲的遊戲機重新顯示，未加入遊戲而新增的遊戲機離開主選單，每台遊戲機的內建引擎重新開啟。遊戲、封面、存檔和設定都會保留。',
      restoreDone: '已恢復預設設定。',
      changeFailed: '無法儲存變更（{error}）。',
      noMatch: '沒有符合此篩選條件的遊戲機。',
      useEmbeddedTitle: '使用內建模擬器',
      useEmbeddedOn: '在遊戲機允許時，遊戲會在 NeoStation 的內建引擎中執行（遊戲機分頁）。',
      useEmbeddedOff: '僅作為前端：每個遊戲都在外部應用程式中開啟，優先使用 RetroArch。內建引擎及其存檔和設定都會保留。',
      launchEngineOff: '{console} 的內建引擎已關閉，且 iOS 上沒有外部應用程式能執行其遊戲。請在遊戲機分頁或 設定 › 一般 中重新開啟。',
      launchEngineOffRetroArch: '{console} 的內建引擎已關閉，且 RetroArch 應用程式無法開啟此遊戲。請安裝 RetroArch 並在 NeoStation 中保持其遊戲庫同步，或重新開啟內建引擎。',
      launchMelonxFailed: '無法在 MeloNX 中啟動此 Nintendo Switch 遊戲。',
      launchArmsx2Failed: '無法在 ARMSX2 中啟動此 PlayStation 2 遊戲。',
    },
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

  static String forLocale(Locale locale, String key) =>
      values[codeFor(locale)]?[key] ?? values['en']![key] ?? key;

  static String format(
    Locale locale,
    String key,
    Map<String, Object?> parameters,
  ) {
    var value = forLocale(locale, key);
    for (final entry in parameters.entries) {
      value = value.replaceAll('{${entry.key}}', entry.value?.toString() ?? '');
    }
    return value;
  }

  static String text(BuildContext context, String key) => forLocale(
    Localizations.maybeLocaleOf(context) ?? const Locale('en'),
    key,
  );
}
