# Refonte Liquid Glass de l'interface — candidat privé (numéro réservé : 548)

Branche : `Claude`. Base hôte validée : `3494edc9e09fb60fecc35dd6cc301bcb93bc9434` (Build 542), à laquelle s'ajoutent le correctif MeloNX de fermeture (544, `d9f35c2`/`eabc057`) et le Core RPCS3 le plus récent livré par la session RPCS3 avec ses fichiers hôte (la recette `liquidglass_ui_delivery.py` importe la recette RPCS3 correspondante et vérifie ces fichiers octet par octet). Les numéros 546 et 547 appartiennent aux livraisons RPCS3 ; la refonte de l'interface prend le numéro **548** (à confirmer avec la session RPCS3 avant exécution). Aucune fusion vers `main`, aucun tag, aucune release. Les moteurs, imports, sauvegardes, catalogues et identifiants persistants ne changent pas ; `lib/main.dart` et les fichiers de bibliothèque verrouillés sur la 419 sont intacts.

## 1. Inventaire (état avant la refonte)

243 fichiers Dart lus dans `lib/screens` et `lib/widgets`.

* Primitives de verre existantes : `NeoGlass` (13 usages : en-tête, rail d'actions, dialogue de réglages de jeu, cartes de la bibliothèque, cartes de consoles) et `NeoGlassBubble` (menu latéral des réglages, cartes de consoles). La barre d'onglets (`MainMenuTabStrip`) utilisait des couleurs codées en dur et aucun jeton partagé.
* Aucun thème ne définissait de thème de composant Material : tous les `AlertDialog` (59), `SimpleDialog`, feuilles, `PopupMenuButton`, `Card`, `SnackBar`, champs et boutons tombaient sur les surfaces opaques Material 3 par défaut.
* Jetons ad hoc récurrents : `cardColor@0.25` (18), `surface@0.5` (8), `tertiaryFixed` (17 pastilles presque noires), `surfaceContainerHighest` (~30).
* Cinq dialogues (`update`, `systems_update`, `restart_required`, `move_user_data`, `folder_not_empty`) floutaient tout l'écran avec un `BackdropFilter` non découpé, pour un panneau lui-même opaque.
* Réglages : menu latéral en bulles qui se touchaient (aucun espace), cartes avec une marge de 8, grilles espacées de 8, menus déroulants et sélecteur de langue opaques.

## 2. Architecture

Trois niveaux, partout dans l'application :

1. **Arrière-plan** (`GlassBackdrop`) : la couleur du thème, un léger dégradé vertical et, en style Liquid Glass, deux lueurs d'accent très faibles. Peint une fois, jamais flouté ; les fonds personnalisés des consoles restent au-dessus. Posé dans `AppScreen` et, via `GlassPageScope`, sous chaque page plein écran (consoles intégrées, BIOS, skins, 3DS, résolution, stockage).
2. **Surfaces** (`GlassSurface`) : une seule primitive translucide avec rôle (`panel`, `rail`, `modal`, `chrome`, `pill`, `card`, `bubble`, `control`, `menu`, `banner`), rayon, flou optionnel (un seul `BackdropFilter` par surface, désactivé par défaut pour les cartes et les grands panneaux), liseré, reflet, ombre et états (focus manette, sélectionné, pressé).
3. **Composants interactifs** : `GlassButton`/`GlassIconButton` (primaire, tonal, verre, destructif, fantôme, compression au toucher), `GlassSegmentedControl`, `GlassSlider`, `GlassChip`, `GlassBanner` (info, succès, avertissement, erreur), `GlassDialog`/`showGlassDialog`, `GlassSheet`/`showGlassSheet`, `GlassMenu`/`GlassMenuItem`, `GlassGroup`, `GlassSectionHeader`, `GlassGap`.

### Système de design centralisé

* `lib/themes/interface_style.dart` : `InterfaceStyleSettings` (style, barre d'onglets, indicateur, taille des icônes, libellés, intensité des effets, intensité du verre, transparence, flou, teinte, contraste, arrondi, densité, profondeur, animations), codec JSON tolérant, préréglages par style.
* `lib/themes/liquid_glass_theme.dart` : `LiquidGlassTheme`, extension de thème qui résout les jetons (opacité par rôle dans une plage lisible, sigma de flou, liseré, reflet, ombres, rayons, espacements, durées) à partir des réglages, du budget de performance et de l'accessibilité. `applyLiquidGlass()` compose le thème final et les thèmes de composants Material (dialogues, feuilles, menus, cartes, séparateurs, curseurs, champs, snack bars, infobulles, puces, boutons, barre d'application).
* `ChromeSurface` et `CornerRadii` restent les jetons par thème ; ils sont désormais mis à l'échelle par `LiquidGlassTheme`, donc les 14 thèmes intégrés et leurs identifiants persistés sont inchangés. À réglages par défaut, les opacités et flous sont exactement les valeurs 505/507 (test `liquid_glass_theme_test`).
* `ThemeProvider` compose et met en cache le thème ; `currentTheme` porte toujours les jetons. `lib/main.dart` n'est pas modifié.

### Performance et accessibilité

* `GlassPerformanceGovernor` : plus aucun flou pendant une partie embarquée (`FrontendMediaGate`), flou divisé par deux en Mode économie d'énergie, flou coupé et ombres réduites 90 s après un avertissement mémoire (`didHaveMemoryPressure`). Les surfaces restent translucides : la mise en page ne bouge pas.
* « Augmenter le contraste » d'iOS : surfaces à ≥ 92 % d'opacité, sans flou. « Réduire les animations » : aucun mouvement décoratif, transitions instantanées. Le niveau d'animation choisi par l'utilisateur ne peut qu'en retirer.
* Aucun flou imbriqué : les grands panneaux (rail des réglages, listes) sont translucides sans `BackdropFilter`.

## 3. Réglages › Thèmes › Interface utilisateur

Nouvelle carte dans la grille Thèmes, qui ouvre un écran par-dessus l'application (le verre de l'aperçu montre le vrai contenu).

* **Style général** : Liquid Glass (défaut), Classique, Minimaliste — chaque choix applique son préréglage de surfaces.
* **Barre d'onglets** : flottante / compacte / classique ; indicateur lentille (Mau Ali) / pastille / soulignement ; icônes petites / moyennes / grandes ; libellés masqués / onglet sélectionné / toujours ; intensité des effets. Les cellules restent de taille égale et adjacentes, l'indicateur aligné : navigation tactile, glissements et manette inchangés (`main_menu_tab_strip_styles_test`, 81 combinaisons).
* **Surfaces** : intensité du verre, transparence, flou, teinte (neutre, accent, secondaire, froide, chaude), contraste, arrondi, espacement et densité, ombres et profondeur. Chaque curseur est une fraction 0–1 projetée sur une plage sûre.
* **Animations** : complètes, réduites, essentielles seulement ; note sur la priorité des réglages iOS.
* **Aperçu en temps réel** : une barre d'onglets, deux bulles de réglage, deux boutons et un encart, dessinés avec les vrais widgets et le thème brouillon. **Appliquer** enregistre (`SharedPreferences`, clé `rewindbox_interface_style_v1`), **Rétablir les valeurs par défaut** applique le préréglage. Le brouillon n'est jamais enregistré seul ; une puce « Aperçu seulement » l'indique.
* Manette : haut/bas pour la ligne, gauche/droite pour la valeur, A pour activer, B pour revenir.
* 70 libellés dans les 12 langues (`lib/l10n/interface_style_locale.dart`, test de complétude et de chinois traditionnel).

## 4. Espacement des réglages

Jetons : espace standard entre deux bulles indépendantes 14.r (≈ 13 pt sur iPhone 16 Pro Max en paysage), marges 18.r (≈ 16,5 pt), espace de catégorie ×1,8, rembourrage de bulle selon la densité. Appliqués au menu latéral des réglages et du scraper (rail translucide, bulles espacées), aux listes (`GlassGap` remplace les 24 `SizedBox(12.r)`), aux cartes (`SettingsCardRow`), aux grilles Thèmes et System Art et aux cartes des dossiers. Le test `liquid_glass_settings_spacing_test` vérifie qu'aucune bulle ne touche la suivante dans les trois densités.

## 5. Écrans et composants migrés

* **Barre d'onglets** : capsule aux couleurs d'origine, désormais pilotée par les jetons (flou optionnel, liseré, ombre, reflet), trois indicateurs, libellés, tailles.
* **Réglages** : `SettingRow`, `SettingsCardRow`, `SettingValueChip` (→ `GlassChip`), `SettingsActionButton`, `SettingsSectionHeader`, `CustomRadioButton`, `CustomToggleSwitch` (piste en verre), menu latéral, sélecteur de langue, carte « À propos », cartes des dossiers, contenu Général/Secondaire/Outils/Systèmes/Thèmes/System Art.
* **Dialogues** : `ConfirmActionDialog` et `DeleteGameDialog` (thème de dialogue), les cinq dialogues à flou plein écran (verre sur le panneau seulement), résumé de scraping, dialogue de réglages d'émulateur ; tous les `AlertDialog`/`Dialog`/feuilles/menus Material restants héritent du thème composé (surface translucide, rayon, liseré, barrière).
* **Menus** : tri de l'en-tête, mode d'affichage, cloche des notifications, menus Material.
* **Encarts** : bandeau Tachiyomi, index récupéré, bannière source de manga, erreur de configuration initiale, erreur du gestionnaire RPCS3, « consoles désactivées » → `GlassBanner`.
* **Chrome** : `GamepadControl` (pieds de page), pied de page de la grille des systèmes, bouton d'import de playlist, déclencheur du menu de tri, panneau latéral de la liste des jeux (liseré/ombre/flou par jetons), lecteur de musique, rangées d'émulateurs, panneaux du scraper et des succès, barre de recherche, puces et panneaux de la recherche.
* **Pages plein écran** : barre d'application transparente par thème ; `GlassPageScope` sous les pages libretro et stockage.
* **UIKit natif** : les pages Textures HD et Triches unifiées lisent la même préférence (`flutter.rewindbox_interface_style_v1`) et appliquent le matériau système correspondant (chrome pour Liquid Glass, épais pour Classique, opaque pour Minimaliste ou si « Réduire la transparence » est actif), avec des cellules translucides. L'éditeur de disposition tactile utilisait déjà `UIVisualEffectView`.

## 6. Conservé volontairement

* `lib/widgets/game_launch_dialog.dart` reste identique : ses octets sont liés à la preuve du correctif MeloNX 544 réutilisée par la livraison.
* Les lecteurs Livres/Manga/PDF gardent leur palette de lecture (confort visuel) ; leurs feuilles restent celles de la palette.
* Les menus natifs en jeu (ARMSX2, Dolphin, libretro) restent opaques : ils s'affichent au-dessus d'un émulateur actif.
* Les couleurs d'action par jeu (`GameActionButton`, pastilles tertiaires des playlists MeloNX/RPCS3/ARMSX2/Dolphin) ne sont pas touchées : ces fichiers sont liés à des preuves d'import existantes.
* Aucune mesure CPU/GPU/RAM sur iPhone n'est revendiquée. La règle appliquée est structurelle : un flou par surface au plus, aucun flou sur les grandes zones ni pendant l'émulation.

## 7. Validation

Locale (Flutter 3.47.2, Linux) : `flutter analyze` sans erreur ni avertissement (mêmes 107 informations préexistantes) ; les sept nouveaux fichiers de test et la série des tests existants concernés (barre d'onglets, en-tête, navigation, bulles, dialogues, réglages, thèmes, notifications, libretro) passent : 367 cas. Détail et empreintes dans `docs/evidence/liquid-glass-ui-local.json`. Aucun rendu iPhone, aucune mesure de fréquence d'images.

Deux constats indépendants de cette refonte, consignés plutôt que masqués :

* `test/retroarch_baseline_scope_test.py` échoue déjà sur la base (`e5007d9`) : dix empreintes périmées (`lib/main.dart`, `lib/screens/systems_screen/system_content.dart`, `native/neoswap-storage/*`). Les workflows Liquid Glass remplacent cette étape par une garde directe : aucun fichier de `lib/main.dart`, `lib/data`, `lib/repositories`, `lib/models`, `lib/utils`, `lib/sync`, `native`, `assets`, `ios`, `pubspec.yaml`, `pubspec.lock` ne diffère de l'hôte validé 542 ; la recette de livraison vérifie en plus octet par octet le correctif MeloNX de `game_launch_dialog.dart`.
* Le cas « rapid focus changes retarget the moving lens without a position jump » de `test/neo_glass_bubble_test.dart` échoue déjà sur la base : il attend un `Transform` nommé `main-menu-liquid-stretch` qu'aucun widget ne fournit depuis `ab7997a`. Une implémentation l'ajoutant autour du peintre validé 507 a été essayée puis retirée (elle déplaçait le rectangle de l'indicateur au repos et ne satisfaisait pas la plage attendue à 100 ms) ; le cas est exclu par son nom (`--name '^(?!rapid focus changes retarget)'`) et les autres cas du fichier s'exécutent.

Le premier commit (`style:`) ne contient que le `dart format` de onze fichiers touchés et des accolades sur les `if` d'une ligne que le formateur a scindés ; le commit de la refonte ne montre que ses propres changements.

## Livraison

Voir la section ajoutée après exécution du workflow `liquid-glass-ui-delivery.yml`. Aucune IPA n'est déclarée avant vérification du fichier téléchargé.
