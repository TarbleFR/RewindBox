/// Wii Remote "Shake" in the embedded Dolphin engine (Build 440): the touch
/// Shake button of the Wii layout and the in-game Controls row that assigns
/// one controller button to Shake X, Y and Z. The native overlay and session
/// menu receive these texts through the session labels built by
/// `DolphinImportLocale.labelsFor`.
abstract final class DolphinShakeLocale {
  static const values = <String, Map<String, String>>{
    'en': {
      'shakeTouchButton': 'Shake the Wii Remote',
      'shakeTouchHint': 'Hold to keep shaking. A short tap gives one shake.',
      'shakeAssign': 'Shake',
      'shakeAssignHelp':
          'Assign one controller button to the three shake axes of the Wii Remote (X, Y, Z); hold it to shake. For player 1, the on-screen Shake button and phone shaking keep working. Each axis can still be changed under Button mapping.',
      'shakeMixed': 'Different per axis',
    },
    'fr': {
      'shakeTouchButton': 'Secouer la Wiimote',
      'shakeTouchHint':
          'Maintenez pour continuer à secouer. Un appui bref donne une secousse.',
      'shakeAssign': 'Secouer',
      'shakeAssignHelp':
          'Attribuez un bouton de manette aux trois axes de secousse de la Wiimote (X, Y, Z) ; maintenez-le pour secouer. Pour le joueur 1, le bouton tactile Secouer et la secousse du téléphone restent actifs. Chaque axe reste modifiable dans Remappage des touches.',
      'shakeMixed': 'Différent selon l’axe',
    },
    'de': {
      'shakeTouchButton': 'Wii-Fernbedienung schütteln',
      'shakeTouchHint':
          'Gedrückt halten, um weiter zu schütteln. Kurzes Tippen schüttelt einmal.',
      'shakeAssign': 'Schütteln',
      'shakeAssignHelp':
          'Weise den drei Schüttelachsen der Wii-Fernbedienung (X, Y, Z) eine Controllertaste zu; halte sie gedrückt, um zu schütteln. Für Spieler 1 funktionieren die Bildschirmtaste „Schütteln“ und das Schütteln des Telefons weiterhin. Jede Achse lässt sich weiterhin unter Tastenbelegung ändern.',
      'shakeMixed': 'Je Achse unterschiedlich',
    },
    'es': {
      'shakeTouchButton': 'Agitar el mando de Wii',
      'shakeTouchHint':
          'Mantén pulsado para seguir agitando. Un toque breve produce una sacudida.',
      'shakeAssign': 'Agitar',
      'shakeAssignHelp':
          'Asigna un botón del mando a los tres ejes de sacudida del mando de Wii (X, Y, Z); mantenlo pulsado para agitar. Para el jugador 1, el botón táctil Agitar y agitar el teléfono siguen funcionando. Cada eje se puede seguir cambiando en Asignación de botones.',
      'shakeMixed': 'Distinto en cada eje',
    },
    'it': {
      'shakeTouchButton': 'Scuoti il telecomando Wii',
      'shakeTouchHint':
          'Tieni premuto per continuare a scuotere. Un tocco breve produce una scossa.',
      'shakeAssign': 'Scuoti',
      'shakeAssignHelp':
          'Assegna un tasto del controller ai tre assi di scuotimento del telecomando Wii (X, Y, Z); tienilo premuto per scuotere. Per il giocatore 1, il pulsante a schermo Scuoti e lo scuotimento del telefono continuano a funzionare. Ogni asse resta modificabile in Mappatura dei tasti.',
      'shakeMixed': 'Diverso per ogni asse',
    },
    'pt': {
      'shakeTouchButton': 'Sacudir o Wii Remote',
      'shakeTouchHint':
          'Mantenha pressionado para continuar sacudindo. Um toque rápido produz uma sacudida.',
      'shakeAssign': 'Sacudir',
      'shakeAssignHelp':
          'Atribua um botão do controle aos três eixos de sacudida do Wii Remote (X, Y, Z); mantenha-o pressionado para sacudir. Para o jogador 1, o botão na tela Sacudir e sacudir o telefone continuam funcionando. Cada eixo ainda pode ser alterado em Mapeamento dos botões.',
      'shakeMixed': 'Diferente em cada eixo',
    },
    'ru': {
      'shakeTouchButton': 'Встряхнуть Wii Remote',
      'shakeTouchHint':
          'Удерживайте, чтобы продолжать встряхивание. Короткое касание — одно встряхивание.',
      'shakeAssign': 'Встряхивание',
      'shakeAssignHelp':
          'Назначьте одну кнопку контроллера на три оси встряхивания Wii Remote (X, Y, Z); удерживайте её, чтобы встряхивать. Для игрока 1 экранная кнопка встряхивания и встряхивание телефона продолжают работать. Каждую ось по-прежнему можно изменить в разделе «Назначение кнопок».',
      'shakeMixed': 'Разное для каждой оси',
    },
    'id': {
      'shakeTouchButton': 'Goyangkan Wii Remote',
      'shakeTouchHint':
          'Tahan untuk terus menggoyangkan. Ketukan singkat menghasilkan satu goyangan.',
      'shakeAssign': 'Goyangkan',
      'shakeAssignHelp':
          'Tetapkan satu tombol pengontrol ke tiga sumbu goyangan Wii Remote (X, Y, Z); tahan tombol itu untuk menggoyangkan. Untuk pemain 1, tombol layar Goyangkan dan goyangan ponsel tetap berfungsi. Setiap sumbu tetap dapat diubah di Pemetaan tombol.',
      'shakeMixed': 'Berbeda per sumbu',
    },
    'ja': {
      'shakeTouchButton': 'Wiiリモコンを振る',
      'shakeTouchHint': '押し続けると振り続けます。短くタップすると1回振ります。',
      'shakeAssign': '振る',
      'shakeAssignHelp':
          'Wiiリモコンの3つの振り軸（X、Y、Z）にコントローラのボタンを1つ割り当てます。押している間、振る操作になります。プレイヤー1では、画面の「振る」ボタンと本体を振る操作も引き続き使えます。各軸は「ボタン割り当て」で個別に変更できます。',
      'shakeMixed': '軸ごとに異なる',
    },
    'ko': {
      'shakeTouchButton': 'Wii 리모컨 흔들기',
      'shakeTouchHint': '누르고 있으면 계속 흔듭니다. 짧게 탭하면 한 번 흔듭니다.',
      'shakeAssign': '흔들기',
      'shakeAssignHelp':
          'Wii 리모컨의 세 흔들기 축(X, Y, Z)에 컨트롤러 버튼 하나를 지정합니다. 누르고 있는 동안 흔듭니다. 플레이어 1은 화면의 흔들기 버튼과 휴대폰 흔들기도 계속 사용할 수 있습니다. 각 축은 버튼 매핑에서 계속 변경할 수 있습니다.',
      'shakeMixed': '축마다 다름',
    },
    'zh': {
      'shakeTouchButton': '摇动Wii遥控器',
      'shakeTouchHint': '按住可持续摇动。轻点一下摇动一次。',
      'shakeAssign': '摇动',
      'shakeAssignHelp':
          '为Wii遥控器的三个摇动轴（X、Y、Z）指定一个手柄按键，按住即可摇动。玩家1仍可使用屏幕上的摇动按钮和摇动手机。各轴仍可在“按键映射”中单独更改。',
      'shakeMixed': '各轴不同',
    },
    'zh_Hant': {
      'shakeTouchButton': '搖動Wii遙控器',
      'shakeTouchHint': '按住可持續搖動。輕點一下搖動一次。',
      'shakeAssign': '搖動',
      'shakeAssignHelp':
          '為Wii遙控器的三個搖動軸（X、Y、Z）指定一個控制器按鍵，按住即可搖動。玩家1仍可使用螢幕上的搖動按鈕和搖動手機。各軸仍可在「按鍵對應」中單獨變更。',
      'shakeMixed': '各軸不同',
    },
  };

  /// Labels for a `DolphinImportLocale.localeKey` value. Every supported
  /// language has every key; English only covers an unsupported language.
  static Map<String, String> labels(String localeKey) => <String, String>{
        ...values['en']!,
        ...?values[localeKey],
      };
}
