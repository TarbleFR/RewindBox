# Réglages RetroArch — Build 438 (paquet F)

Demande du mainteneur du 11 octobre 2026, décision F de
`docs/build438-plan.md` : retirer l’entrée « RetroArch externe » des
paramètres du jeu en gardant les réglages encore utiles au bon endroit,
afficher « RetroArch embarqué » dans les paramètres du système comme les
autres émulateurs intégrés, et reformuler les textes qui présentaient
l’application RetroArch comme nécessaire. Base : `a434881e` (branche
`Claude`).

## Ce qui change

### Paramètres du jeu › Émulateur (`game_settings_emulator_tab.dart`)

- La liste des choix vient de `libretroEngineChoices(système, choix
  enregistré)` (`lib/services/libretro_engine_choices.dart`, fonction pure) :
  les cœurs intégrés du système, le cœur par défaut en premier.
- « Application RetroArch » n’est plus proposée. Un jeu dont le choix
  enregistré est déjà `retroarch` garde ce réglage : la ligne apparaît en
  dernier, active, libellée « Application RetroArch (réglage précédent) »
  (clé `externalRetroArch`, nouvelle valeur dans les douze langues), et le
  jeu continue de s’ouvrir dans l’application RetroArch.
- Choisir un cœur remplace ce réglage (comportement existant de
  `setCoreChoice`). La liste est calculée une fois par visite : la ligne
  reste visible jusqu’à la réouverture de l’onglet, ce qui évite de déplacer
  la sélection et permet d’annuler. À la visite suivante, elle n’apparaît
  plus.
- Au-dessus de la liste, la tuile d’identité du moteur
  (`LibretroEngineIdentityTile`) : même présentation que DolphiniOS, ARMSX2,
  RPCS3 et Dusklight. Elle n’est pas navigable : les indices des lignes de
  choix ne changent pas. Sa coche disparaît pour un jeu encore réglé sur
  l’application RetroArch.
- Aucune migration : la lecture de la liste n’écrit rien, le préfixe
  `libretro_core_v1.` et la valeur `retroarch` sont inchangés. Le routage
  (`LibretroInternalService.shouldLaunchEmbedded`, `game_launch_service.dart`)
  n’est pas modifié.

### Paramètres du système › Émulateurs (`system_emulator_settings_dialog*`)

Pour un système lancé par le moteur libretro intégré (iOS,
`LibretroInternalService.handlesSystemModel`), l’onglet affiche
`LibretroEngineSettingsPanel` (`lib/widgets/libretro_engine_panel.dart`) au
lieu de la ligne « RetroArch — Non installé » :

1. « RetroArch embarqué » (en « Embedded RetroArch ») : icône
   `Symbols.sports_esports_rounded`, sous-titre « Embarqué dans NeoStation ·
   <cœur> » (« <cœur> (par défaut) » quand le système propose d’autres
   cœurs), coche `check_circle`. Le nom est celui demandé par le mainteneur
   (plan F) ; il remplace la recommandation de
   `docs/retroarch-integre-architecture.md` (nommer seulement le cœur), le
   cœur restant nommé dans le sous-titre.
2. « Skins » : `LibretroSkinManagerScreen(console:)` de la console du
   système, seulement si le système a une console (terme du catalogue
   existant, identique à la page ouverte).
3. « Vérificateur de BIOS » : `LibretroBiosCheckerScreen(console:)`, filtré
   sur la console (page du paquet E ; ce paquet ne modifie pas ce fichier).
4. Rappel : format d’écran, shaders, commandes, codes de triche et réglages
   d’émulation se règlent dans le menu en jeu, pour la console ou pour un
   seul jeu.

L’entrée « Consoles intégrées » n’est pas reprise : elle devient un onglet
de la barre principale (paquet C). Les systèmes sans cœur intégré (2600,
PC Engine…) gardent la ligne de l’application RetroArch, inchangée.

Manette : haut, bas et A sont transmis au panneau
(`_libretroPanelKey.currentState`) avant les retours anticipés
`_totalEmulators == 0` et `Platform.isIOS` de `gamepad_nav.dart` ; le
déplacement boucle comme les autres lignes de la boîte de dialogue. Une
seconde pression pendant l’ouverture d’une page est ignorée. Chaque page
ouverte pose sa propre couche de navigation (`LibretroPageNavigation`) et la
boîte de dialogue reprend la main à sa fermeture.

### Textes reformulés (douze langues)

- Carte RetroArch de Réglages › Dossiers (valeurs seulement, le fichier
  verrouillé `directories_settings_content.dart` n’est pas modifié) :
  `iosRetroarchStatusNeedsLink`, `iosRetroarchStatusNeedsSync`,
  `iosRetroarchStatusSynced` (aussi message de fin de synchronisation) et
  `iosRetroarchLinkSuccess`. L’application devient facultative ; les
  consoles intégrées démarrent dans NeoStation ; la synchronisation ne sert
  qu’aux jeux que l’application lance elle-même.
- Assistant iOS, option « Lier un dossier sans le déplacer »
  (`IosSetupLocale.linkDescription`) : n’importe quel dossier de jeux, celui
  de RetroArch n’étant qu’un exemple.
- Message de relance de la bibliothèque vide
  (`IosSetupLocale.restartDescription`) : il s’affiche pour tout dossier lié
  et ne parle plus de RetroArch.

Nouvelles clés `LibretroLocale`, ajoutées à la fin des douze cartes :
`engineName`, `engineInGameSettings`, `engineSkinsSubtitle`,
`engineBiosChecker`, `engineBiosCheckerSubtitle` (`{console}` = nom produit
de la console, non traduit).

## Ce qui ne change pas

- La synchronisation RetroArch du premier lancement
  (`permission_check_wrapper.dart`) et le bouton de synchronisation de la
  carte RetroArch.
- La route `retroarch://` pour les systèmes sans cœur intégré, les jeux
  connus seulement de la bibliothèque RetroArch et les jeux déjà réglés sur
  l’application RetroArch.
- Les sauvegardes, états, skins, réglages par console et par jeu, choix de
  cœur et BIOS (`Documents/Libretro/…`), les dossiers liés et les fichiers
  verrouillés de la Build 419. Aucun code natif.

Formulation proposée pour la ligne d’`AGENTS.md` sur la route
`retroarch://` (réservée à l’intégration) : « …et pour les jeux déjà réglés
sur l’application RetroArch avant la Build 438 (« Application RetroArch
(réglage précédent) ») ; ce choix n’est plus proposé pour les autres jeux. »

## Vérifications

Exécutées sur Windows (Flutter 3.47.2, Python 3.12.10) :

- `flutter test --no-pub test/libretro_engine_settings_test.dart` : choix par
  jeu sur tous les systèmes du catalogue, aller-retour SharedPreferences
  (lecture sans réécriture, remplacement par un cœur, autres réglages
  intacts), tuile et panneau dans les douze langues et pour zh-Hant, zh-TW,
  zh-HK, zh-MO, navigation manette (boucle, A, double pression), absence de
  la ligne Skins sans console, pages ouvertes avec la bonne console, textes
  de l’assistant et de la carte RetroArch, câblage des fichiers de la boîte
  de dialogue.
- Tests existants concernés : `libretro_locale_test.dart`,
  `retroarch_sync_locale_test.dart` (quatre clés ajoutées),
  `rpcs3_embedded_identity_test.dart`,
  `armsx2_embedded_library_contract_test.dart`,
  `gamepad_settings_scrolling_test.dart`, `libretro_playlist_actions_test.dart`,
  `libretro_core_catalog_test.dart`, `libretro_skin_manager_test.dart`,
  `libretro_skin_catalog_test.dart`.
- Contrats Python : `libretro_route_contract_test.py` (renforcé : garde
  `retroarch`, préfixe des préférences, liste des choix sans écriture),
  `localization_12_locale_coverage_test.py` (ajout de `ios_setup_locale.dart`
  et `embedded_emulator_locale.dart`), `libretro_frontend_ui_contract_test.py`,
  `integrated_import_tab_contract_test.py`, `retroarch_baseline_scope_test.py`.

Hors Windows : `build-utils/verify_delivery_reuse.py` (Linux),
`libretro-checks.yml` et `retroarch-delivery.yml` par `workflow_dispatch
--ref Claude`.

À confirmer sur iPhone (non démontré ici) : apparence du panneau pour SNES,
MD, PS1, 3DS et GBA ; ouverture et retour des pages au toucher et à la
manette ; ligne « réglage précédent » d’un jeu réglé sur l’application
RetroArch sous la 437, qui ouvre toujours RetroArch puis démarre dans
NeoStation après le choix d’un cœur ; ligne RetroArch inchangée pour 2600 ou
PC Engine ; nouveaux textes en fr, en et zh_Hant.
