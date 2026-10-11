/// Wii Remote "Shake" in the embedded Dolphin engine (Build 440): the touch
/// Shake button of the Wii layout and the in-game Controls row that assigns
/// one controller button to Shake X, Y and Z. Build 442 adds the phone-shake
/// sensitivity (in-game Controls row and the Wii settings panel). The native overlay and session
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
      'shakeSensitivity': 'Shake sensitivity',
      'shakeSensitivityLow': 'Low',
      'shakeSensitivityMedium': 'Medium',
      'shakeSensitivityHigh': 'High',
      'shakeSensitivityHelp':
          'Sensitivity of phone shaking. Medium recognises a light, deliberate shake; Low needs a firm shake (previous behaviour); High reacts to very small movements. The shake lasts as long as the phone keeps moving.',
      'phoneShakeToggle': 'Shake the phone to shake the Wii Remote',
      'phoneShakeToggleHelp':
          'First Wii Remote, with or without Nunchuk. Also available in the in-game Controls menu.',
      'wiiMotionSection': 'Wii Remote motion',
    },
    'fr': {
      'shakeTouchButton': 'Secouer la Wiimote',
      'shakeTouchHint':
          'Maintenez pour continuer à secouer. Un appui bref donne une secousse.',
      'shakeAssign': 'Secouer',
      'shakeAssignHelp':
          'Attribuez un bouton de manette aux trois axes de secousse de la Wiimote (X, Y, Z) ; maintenez-le pour secouer. Pour le joueur 1, le bouton tactile Secouer et la secousse du téléphone restent actifs. Chaque axe reste modifiable dans Remappage des touches.',
      'shakeMixed': 'Différent selon l’axe',
      'shakeSensitivity': 'Sensibilité de la secousse',
      'shakeSensitivityLow': 'Faible',
      'shakeSensitivityMedium': 'Moyenne',
      'shakeSensitivityHigh': 'Élevée',
      'shakeSensitivityHelp':
          'Sensibilité de la secousse du téléphone. Moyenne reconnaît une secousse légère et volontaire ; Faible exige une secousse franche (comportement précédent) ; Élevée réagit à de très petits mouvements. La secousse dure tant que le téléphone bouge.',
      'phoneShakeToggle': 'Secouer le téléphone pour secouer la Wiimote',
      'phoneShakeToggleHelp':
          'Première Wiimote, avec ou sans Nunchuk. Aussi disponible dans le menu Commandes en jeu.',
      'wiiMotionSection': 'Mouvements de la Wiimote',
    },
    'de': {
      'shakeTouchButton': 'Wii-Fernbedienung schütteln',
      'shakeTouchHint':
          'Gedrückt halten, um weiter zu schütteln. Kurzes Tippen schüttelt einmal.',
      'shakeAssign': 'Schütteln',
      'shakeAssignHelp':
          'Weise den drei Schüttelachsen der Wii-Fernbedienung (X, Y, Z) eine Controllertaste zu; halte sie gedrückt, um zu schütteln. Für Spieler 1 funktionieren die Bildschirmtaste „Schütteln“ und das Schütteln des Telefons weiterhin. Jede Achse lässt sich weiterhin unter Tastenbelegung ändern.',
      'shakeMixed': 'Je Achse unterschiedlich',
      'shakeSensitivity': 'Schüttel-Empfindlichkeit',
      'shakeSensitivityLow': 'Niedrig',
      'shakeSensitivityMedium': 'Mittel',
      'shakeSensitivityHigh': 'Hoch',
      'shakeSensitivityHelp':
          'Empfindlichkeit für das Schütteln des Telefons. Mittel erkennt ein leichtes, bewusstes Schütteln; Niedrig verlangt ein kräftiges Schütteln (bisheriges Verhalten); Hoch reagiert auf sehr kleine Bewegungen. Das Schütteln dauert, solange sich das Telefon bewegt.',
      'phoneShakeToggle': 'Telefon schütteln, um die Wii-Fernbedienung zu schütteln',
      'phoneShakeToggleHelp':
          'Erste Wii-Fernbedienung, mit oder ohne Nunchuk. Auch im Menü „Steuerung“ im Spiel verfügbar.',
      'wiiMotionSection': 'Bewegung der Wii-Fernbedienung',
    },
    'es': {
      'shakeTouchButton': 'Agitar el mando de Wii',
      'shakeTouchHint':
          'Mantén pulsado para seguir agitando. Un toque breve produce una sacudida.',
      'shakeAssign': 'Agitar',
      'shakeAssignHelp':
          'Asigna un botón del mando a los tres ejes de sacudida del mando de Wii (X, Y, Z); mantenlo pulsado para agitar. Para el jugador 1, el botón táctil Agitar y agitar el teléfono siguen funcionando. Cada eje se puede seguir cambiando en Asignación de botones.',
      'shakeMixed': 'Distinto en cada eje',
      'shakeSensitivity': 'Sensibilidad de la sacudida',
      'shakeSensitivityLow': 'Baja',
      'shakeSensitivityMedium': 'Media',
      'shakeSensitivityHigh': 'Alta',
      'shakeSensitivityHelp':
          'Sensibilidad al agitar el teléfono. Media reconoce una sacudida ligera y deliberada; Baja exige una sacudida firme (comportamiento anterior); Alta reacciona a movimientos muy pequeños. La sacudida dura mientras el teléfono siga moviéndose.',
      'phoneShakeToggle': 'Agitar el teléfono para agitar el mando de Wii',
      'phoneShakeToggleHelp':
          'Primer mando de Wii, con o sin Nunchuk. También disponible en el menú Controles durante el juego.',
      'wiiMotionSection': 'Movimiento del mando de Wii',
    },
    'it': {
      'shakeTouchButton': 'Scuoti il telecomando Wii',
      'shakeTouchHint':
          'Tieni premuto per continuare a scuotere. Un tocco breve produce una scossa.',
      'shakeAssign': 'Scuoti',
      'shakeAssignHelp':
          'Assegna un tasto del controller ai tre assi di scuotimento del telecomando Wii (X, Y, Z); tienilo premuto per scuotere. Per il giocatore 1, il pulsante a schermo Scuoti e lo scuotimento del telefono continuano a funzionare. Ogni asse resta modificabile in Mappatura dei tasti.',
      'shakeMixed': 'Diverso per ogni asse',
      'shakeSensitivity': 'Sensibilità dello scuotimento',
      'shakeSensitivityLow': 'Bassa',
      'shakeSensitivityMedium': 'Media',
      'shakeSensitivityHigh': 'Alta',
      'shakeSensitivityHelp':
          'Sensibilità allo scuotimento del telefono. Media riconosce una scossa leggera e intenzionale; Bassa richiede una scossa decisa (comportamento precedente); Alta reagisce a movimenti molto piccoli. Lo scuotimento dura finché il telefono continua a muoversi.',
      'phoneShakeToggle': 'Scuoti il telefono per scuotere il telecomando Wii',
      'phoneShakeToggleHelp':
          'Primo telecomando Wii, con o senza Nunchuk. Disponibile anche nel menu Comandi durante il gioco.',
      'wiiMotionSection': 'Movimento del telecomando Wii',
    },
    'pt': {
      'shakeTouchButton': 'Sacudir o Wii Remote',
      'shakeTouchHint':
          'Mantenha pressionado para continuar sacudindo. Um toque rápido produz uma sacudida.',
      'shakeAssign': 'Sacudir',
      'shakeAssignHelp':
          'Atribua um botão do controle aos três eixos de sacudida do Wii Remote (X, Y, Z); mantenha-o pressionado para sacudir. Para o jogador 1, o botão na tela Sacudir e sacudir o telefone continuam funcionando. Cada eixo ainda pode ser alterado em Mapeamento dos botões.',
      'shakeMixed': 'Diferente em cada eixo',
      'shakeSensitivity': 'Sensibilidade da sacudida',
      'shakeSensitivityLow': 'Baixa',
      'shakeSensitivityMedium': 'Média',
      'shakeSensitivityHigh': 'Alta',
      'shakeSensitivityHelp':
          'Sensibilidade ao sacudir o telefone. Média reconhece uma sacudida leve e intencional; Baixa exige uma sacudida firme (comportamento anterior); Alta reage a movimentos muito pequenos. A sacudida dura enquanto o telefone continuar se movendo.',
      'phoneShakeToggle': 'Sacudir o telefone para sacudir o Wii Remote',
      'phoneShakeToggleHelp':
          'Primeiro Wii Remote, com ou sem Nunchuk. Também disponível no menu Controles durante o jogo.',
      'wiiMotionSection': 'Movimento do Wii Remote',
    },
    'ru': {
      'shakeTouchButton': 'Встряхнуть Wii Remote',
      'shakeTouchHint':
          'Удерживайте, чтобы продолжать встряхивание. Короткое касание — одно встряхивание.',
      'shakeAssign': 'Встряхивание',
      'shakeAssignHelp':
          'Назначьте одну кнопку контроллера на три оси встряхивания Wii Remote (X, Y, Z); удерживайте её, чтобы встряхивать. Для игрока 1 экранная кнопка встряхивания и встряхивание телефона продолжают работать. Каждую ось по-прежнему можно изменить в разделе «Назначение кнопок».',
      'shakeMixed': 'Разное для каждой оси',
      'shakeSensitivity': 'Чувствительность встряхивания',
      'shakeSensitivityLow': 'Низкая',
      'shakeSensitivityMedium': 'Средняя',
      'shakeSensitivityHigh': 'Высокая',
      'shakeSensitivityHelp':
          'Чувствительность к встряхиванию телефона. Средняя распознаёт лёгкое намеренное встряхивание; Низкая требует резкого встряхивания (прежнее поведение); Высокая реагирует на очень слабые движения. Встряхивание длится, пока телефон продолжает двигаться.',
      'phoneShakeToggle': 'Встряхивать телефон, чтобы встряхнуть Wii Remote',
      'phoneShakeToggleHelp':
          'Первый Wii Remote, с Nunchuk или без него. Также доступно в меню «Управление» во время игры.',
      'wiiMotionSection': 'Движение Wii Remote',
    },
    'id': {
      'shakeTouchButton': 'Goyangkan Wii Remote',
      'shakeTouchHint':
          'Tahan untuk terus menggoyangkan. Ketukan singkat menghasilkan satu goyangan.',
      'shakeAssign': 'Goyangkan',
      'shakeAssignHelp':
          'Tetapkan satu tombol pengontrol ke tiga sumbu goyangan Wii Remote (X, Y, Z); tahan tombol itu untuk menggoyangkan. Untuk pemain 1, tombol layar Goyangkan dan goyangan ponsel tetap berfungsi. Setiap sumbu tetap dapat diubah di Pemetaan tombol.',
      'shakeMixed': 'Berbeda per sumbu',
      'shakeSensitivity': 'Sensitivitas goyangan',
      'shakeSensitivityLow': 'Rendah',
      'shakeSensitivityMedium': 'Sedang',
      'shakeSensitivityHigh': 'Tinggi',
      'shakeSensitivityHelp':
          'Sensitivitas goyangan ponsel. Sedang mengenali goyangan ringan yang disengaja; Rendah memerlukan goyangan yang kuat (perilaku sebelumnya); Tinggi bereaksi terhadap gerakan yang sangat kecil. Goyangan berlangsung selama ponsel terus bergerak.',
      'phoneShakeToggle': 'Goyangkan ponsel untuk menggoyangkan Wii Remote',
      'phoneShakeToggleHelp':
          'Wii Remote pertama, dengan atau tanpa Nunchuk. Juga tersedia di menu Kontrol dalam game.',
      'wiiMotionSection': 'Gerakan Wii Remote',
    },
    'ja': {
      'shakeTouchButton': 'Wiiリモコンを振る',
      'shakeTouchHint': '押し続けると振り続けます。短くタップすると1回振ります。',
      'shakeAssign': '振る',
      'shakeAssignHelp':
          'Wiiリモコンの3つの振り軸（X、Y、Z）にコントローラのボタンを1つ割り当てます。押している間、振る操作になります。プレイヤー1では、画面の「振る」ボタンと本体を振る操作も引き続き使えます。各軸は「ボタン割り当て」で個別に変更できます。',
      'shakeMixed': '軸ごとに異なる',
      'shakeSensitivity': '振りの感度',
      'shakeSensitivityLow': '低',
      'shakeSensitivityMedium': '中',
      'shakeSensitivityHigh': '高',
      'shakeSensitivityHelp':
          '本体を振る操作の感度です。「中」は軽く意図的に振る動きを認識し、「低」はしっかり振る必要があります（従来の動作）。「高」はごく小さな動きにも反応します。本体が動いている間、振る操作が続きます。',
      'phoneShakeToggle': '本体を振ってWiiリモコンを振る',
      'phoneShakeToggleHelp': '1番目のWiiリモコン用です。ヌンチャクの有無は問いません。ゲーム中の「操作」メニューでも設定できます。',
      'wiiMotionSection': 'Wiiリモコンのモーション',
    },
    'ko': {
      'shakeTouchButton': 'Wii 리모컨 흔들기',
      'shakeTouchHint': '누르고 있으면 계속 흔듭니다. 짧게 탭하면 한 번 흔듭니다.',
      'shakeAssign': '흔들기',
      'shakeAssignHelp':
          'Wii 리모컨의 세 흔들기 축(X, Y, Z)에 컨트롤러 버튼 하나를 지정합니다. 누르고 있는 동안 흔듭니다. 플레이어 1은 화면의 흔들기 버튼과 휴대폰 흔들기도 계속 사용할 수 있습니다. 각 축은 버튼 매핑에서 계속 변경할 수 있습니다.',
      'shakeMixed': '축마다 다름',
      'shakeSensitivity': '흔들기 감도',
      'shakeSensitivityLow': '낮음',
      'shakeSensitivityMedium': '보통',
      'shakeSensitivityHigh': '높음',
      'shakeSensitivityHelp':
          '휴대폰 흔들기의 감도입니다. 보통은 가볍고 의도적인 흔들기를 인식하고, 낮음은 세게 흔들어야 하며(이전 동작), 높음은 아주 작은 움직임에도 반응합니다. 휴대폰이 움직이는 동안 흔들기가 계속됩니다.',
      'phoneShakeToggle': '휴대폰을 흔들어 Wii 리모컨 흔들기',
      'phoneShakeToggleHelp': '첫 번째 Wii 리모컨에서 사용하며 눈차크는 선택 사항입니다. 게임 중 조작 메뉴에서도 설정할 수 있습니다.',
      'wiiMotionSection': 'Wii 리모컨 모션',
    },
    'zh': {
      'shakeTouchButton': '摇动Wii遥控器',
      'shakeTouchHint': '按住可持续摇动。轻点一下摇动一次。',
      'shakeAssign': '摇动',
      'shakeAssignHelp':
          '为Wii遥控器的三个摇动轴（X、Y、Z）指定一个手柄按键，按住即可摇动。玩家1仍可使用屏幕上的摇动按钮和摇动手机。各轴仍可在“按键映射”中单独更改。',
      'shakeMixed': '各轴不同',
      'shakeSensitivity': '摇动灵敏度',
      'shakeSensitivityLow': '低',
      'shakeSensitivityMedium': '中',
      'shakeSensitivityHigh': '高',
      'shakeSensitivityHelp':
          '摇动手机的灵敏度。“中”可识别轻微而有意的摇动；“低”需要用力摇动（之前的行为）；“高”对非常小的动作也会响应。手机持续移动时，摇动会一直持续。',
      'phoneShakeToggle': '摇动手机以摇动Wii遥控器',
      'phoneShakeToggleHelp': '用于第一个Wii遥控器，可搭配或不搭配双截棍。也可在游戏内的“操作”菜单中设置。',
      'wiiMotionSection': 'Wii遥控器体感',
    },
    'zh_Hant': {
      'shakeTouchButton': '搖動Wii遙控器',
      'shakeTouchHint': '按住可持續搖動。輕點一下搖動一次。',
      'shakeAssign': '搖動',
      'shakeAssignHelp':
          '為Wii遙控器的三個搖動軸（X、Y、Z）指定一個控制器按鍵，按住即可搖動。玩家1仍可使用螢幕上的搖動按鈕和搖動手機。各軸仍可在「按鍵對應」中單獨變更。',
      'shakeMixed': '各軸不同',
      'shakeSensitivity': '搖動靈敏度',
      'shakeSensitivityLow': '低',
      'shakeSensitivityMedium': '中',
      'shakeSensitivityHigh': '高',
      'shakeSensitivityHelp':
          '搖動手機的靈敏度。「中」可辨識輕微且刻意的搖動；「低」需要用力搖動（先前的行為）；「高」對非常小的動作也會反應。手機持續移動時，搖動會一直持續。',
      'phoneShakeToggle': '搖動手機以搖動Wii遙控器',
      'phoneShakeToggleHelp': '適用於第一個Wii遙控器，可搭配或不搭配雙節棍。也可在遊戲內的「操作」選單中設定。',
      'wiiMotionSection': 'Wii遙控器體感',
    },
  };

  /// Labels for a `DolphinImportLocale.localeKey` value. Every supported
  /// language has every key; English only covers an unsupported language.
  static Map<String, String> labels(String localeKey) => <String, String>{
        ...values['en']!,
        ...?values[localeKey],
      };
}
