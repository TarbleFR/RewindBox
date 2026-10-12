# Livres et mangas 3D — conception et contrat (12 octobre 2026)

Chantier 3 de la grande mise à jour (`docs/grande-mise-a-jour-audit-2026-10-12.md`, § 5,
verdict § 10 « Livres », décisions § 11 questions 14 à 20). Candidate : l'IPA unique de fin
de cycle construite par-dessus la Build 446 ; numéro attribué à la livraison. Sources
relues à `5183c8d9` (HEAD de `Claude`). Ce document fixe les noms, signatures, clés et
fichiers **avant** le code ; toute déviation y est reportée. Là où les sources
contredisent l'audit, les sources font foi et l'écart est signalé (« ≠ audit »).

## 1. Décisions du mainteneur et cadre

- Q14 : épaisseur par **estimation bornée** pour EPUB/TXT (`sizeBytes ~/ 1800` pages,
  bornée 40–1200) ; CBZ/PDF par `pageCount`. Q15 : volume aussi dans le hub en ligne, à
  **épaisseur fixe**. Q16 : tour de page **curl** par défaut partout sauf en défilement
  vertical ; **double page automatique en paysage, première page seule** ; PDF en **deux
  modes avec bascule** (pages / défilement-zoom). Q17 : barre d'outils **automatique**
  (masquage 4 s de la 440) avec option « toujours visible ». Q18 : `assets/shaders/page_curl.frag`
  accepté comme actif de build, **repli painter** obligatoire. Q19 : **Y = marque-page**
  dans les trois lecteurs ; « Ajuster » du PDF passe sur le **clic du stick droit**.
  Q20 : `reading-state.json` reste en **version 1**, clés additives seulement.
- Cadre AGENTS.md : aucun des dix fichiers de bibliothèque verrouillés ni `lib/main.dart`
  n'est touché (`test/retroarch_baseline_scope_test.py:45-78`) ; `main.dart:1113-1122`
  impose `FadeUpwardsPageTransitionsBuilder` à toutes les plateformes, donc l'ouverture
  animée est une **route dédiée** poussée par le lanceur, jamais une transition globale ni
  un balayage de bord. Aucune dépendance nouvelle : pdfrx reste `^2.4.6` (`pubspec.yaml:97`,
  verrouillé `2.4.7`, `pubspec.lock:703`) ; `flutter_gpu` écarté ; `pubspec.lock` sans diff.
  `pubspec.yaml` change d'une seule ligne (entrée `shaders:`), inscrite au bloc DELTA
  (`verify_tree` l'admet quand elle y figure, `build-utils/verify_delivery_reuse.py:1162-1191`).
- Douze langues : toute chaîne nouvelle va dans `LibraryReaderLocale` (déjà couvert par
  `test/localization_12_locale_coverage_test.py:35-45` et `test/library_reader_locale_test.dart`) ;
  `LibraryLocalLocale` ne reçoit aucune clé (la vue locale n'affiche aucun texte nouveau, le
  volume est décoratif et `ExcludeSemantics`). Jamais de repli anglais : seule la parité
  protège (`library_reader_locale.dart:1275`).
- Gate fermée : bloc `BUILD447_BOOKS_DELTA` listant chaque fichier créé ou modifié sous
  `lib/`, `assets/`, `test/`, `build-utils/` et `pubspec.yaml`, sinon la livraison échoue
  avant le premier test Flutter. Aucune validation iPhone n'est revendiquée ; la fluidité,
  la mémoire, VoiceOver et la manette sont à vérifier sur l'appareil (§ 6).

## 2. Faits établis (sources, `fichier:ligne`)

- `LibraryBookCover` : API `child/selected/rightToLeft/radius` (`lib/widgets/library_book_cover.dart:12-24`),
  pile plate inclinée (front à 46°, `:209-212`), Reduce Motion = `disableAnimations ||
  accessibleNavigation` (`:47-50`) ; usage unique dans le hub (`library_screen.dart:2996-3010`),
  carte `_LibraryCatalogCard` sélectionnée par index (`:2332`, `:2362`). La vue locale
  n'utilise pas la couverture : `_BookTile` sans paramètre `selected` (`library_local_view.dart:1004-1022`),
  focus Flutter via `LibraryFocusRing(onFocusChange:)` (`:1037-1039`, `library_focus_gamepad_layer.dart:288-294`),
  le parent note `_focusedBookId` sans se reconstruire (`:938-944`). « Reprendre » :
  `_Cover` plat (`library_favorites_view.dart:1119-1151`) dans `_buildContinueCard`
  (`:814-870`, `AspectRatio(0.66)`), sélection par `_SelectableCard(selected:)` (`:1078-1116`).
- Lanceur : `MaterialPageRoute` sur le navigateur racine (`library_reader_launcher.dart:54`,
  `:131-135`) ; `rightToLeft` transmis au seul lecteur CBZ (`:82-90`), jamais à
  `LibraryBookReaderScreen` (`:62-75`) alors que l'indice EPUB `page-progression-direction`
  est extrait à l'import (`library_book_formats.dart:1120-1126` → `LibraryLocalBook.rightToLeft`,
  `library_local_models.dart:311`). Le hub pousse ses propres lecteurs en `MaterialPageRoute`
  (`library_screen.dart:1452`, `:1470`) et un titre Aidoku ouvre `LibraryMangaDetailsScreen`
  (`:1244-1256`), pas un lecteur.
- EPUB/TXT : défilement continu (`ScrollController`, `library_book_reader_screen.dart:1372-1374`),
  `_scrollBy` 0,9/0,3 écran plafonné par `_pageStep` (`:866-893`), ancre
  `LibraryReflowPosition(chapter, block, offset)` (`:114-123`, `library_reflow_source.dart:14-35`),
  `_opening` (`:91`), sauvegarde par `locationFor`/`fractionFor` (`:808-834`), ré-ancrage au
  changement de largeur (`:1117-1121`). Unités ≤ 2000 caractères (`library_reflow_view.dart:47`),
  `LibraryReflowStyle` (`:139-186`, `tallestLine`), `offsetAt` et `caretTop` lisent le
  `RenderParagraph` (`:313-339`). CFI NeoStation `epubcfi(/6/<2(i+1)>[idref]!<path>:<offset>)`
  (`library_epub.dart:199-209`, `cfiForChapter` `:491-511`). Manette : X = sommaire, **Y non lié**
  (`:168-181`).
- Pages (CBZ/en ligne) : `PageView.builder` (`library_page_reader_screen.dart:1040-1049`,
  `reverse: rightToLeft`, physique `Never…` en zoom), décodage ≤ 2400×3072 px par pas de 128
  (`:57-62`, `:628-634`), **trois pages décodées** (courante + `precacheImage` ±1, `:587-603`),
  éviction des `_providers` à la fermeture (`:211-217`), sémantique `pageNumber` par
  `LibraryReaderPageImage` (`:1283`, `:1375-1386`) ; **ni X ni Y liés** (`:133-152`).
  `LibraryArchivePageSource.prefetch` est vide (`library_page_source.dart:175-177`).
  Précédence actuelle (`library_page_reader_controller.dart:86-117`) : surcharge de session,
  puis indice du contenu en mode `auto`, puis réglage global ; `chapterId` enregistré avec la
  progression (`:305`).
- PDF : `PdfViewer.file` continu (`library_pdf_reader_screen.dart:374-410`, cache pdfrx
  `maxImageBytesCachedOnMemory: 48 Mio` `:382`, `layoutPages` inutilisé) ; Y = `_fitPage`
  (`:99-112`, `calcMatrixForFit` `:251-255`), X = sommaire, LB/RB = ±10 pages.
- Chrome 440 : `LibraryReaderChromeController` (4 s, `hold/release`, `accessibleNavigation`,
  `library_reader_chrome.dart:453-541`), `LibraryReaderChromeOverlay(onBack:)` et bouton
  flottant (`:306-328`), contrat « un seul Retour » (`test/library_reader_back_button_test.dart`,
  `expectOneBack` `:106-117`). `LibraryReaderGamepadBindings` sans clic de stick
  (`library_reader_gamepad.dart:8-40`) alors que `GamepadNavigation.onRightStickClick`
  existe (`lib/utils/gamepad_nav.dart:70`, `:285`, `:874-875`). Aucun lecteur ne lit
  `disableAnimations` ; aucun `didHaveMemoryPressure` dans `lib/`.
- Magasin : `_formatVersion = 1` (`library_reading_store.dart:549`), écrit dans `toJson`
  (`:1373`) mais **jamais relu** par `_StoreData.fromJson` (`:1402-1448`, entrées invalides
  ignorées, clés inconnues perdues à la prochaine écriture) ; écriture atomique `.tmp` +
  `rename` (`:1042-1044`) ; `_progressEvictable` épargne `local:`, favoris et titres à
  marques (`:1281-1284`) ; **un seul** `LibraryReaderSettings` (`:346-470`, `fromJson`
  tolérant `:430`) ; aucun marque-page.
- Couvertures locales ≤ 360 px (`LibraryFileBookInspector.coverWidth = 360`,
  `library_book_formats.dart:1701` ; PDF rendu par `PdfPage.render(fullWidth: 360)` `:2064-2072`),
  ordre de recherche `_findCover` (`:1231-1297`) matérialisé à l'import ; `pageCount` connu
  pour CBZ/PDF, null pour EPUB/TXT (`library_local_models.dart:124-125`, `:312`).
- SDK épinglé : `FragmentProgram.fromAsset` (`sky_engine/lib/ui/painting.dart:5432`),
  `FragmentShader.setImageSampler` (`:6488`), `Canvas.drawVertices` (`:7393`), `Vertices.raw`
  (`:6717`), `ImageShader` (`:5331`), `Picture.toImage` (`:8456`),
  `TextPainter.computeLineMetrics()` (`painting/text_painter.dart:1794`), `getLineBoundary`
  (`:1750`). Trois `.frag` déjà chargés par `fromAsset` (`music_visualizer.dart:133`, …),
  déclarés un par un sous `shaders:` (`pubspec.yaml:126-131`).
- CI : `retroarch-delivery.yml:106` exécute `flutter test test/library_*_test.dart` par
  **glob** (≠ audit § 2.1 « listes explicites ») : un test Dart nommé ainsi tourne sans
  éditer la ligne figée par `test/delivery_pipeline_test.py`. Contrats Python après
  `python3 test/library_reader_orientation_contract_test.py` (`:143`). La clé `hashFiles`
  couvre `lib/**`, `assets/**`, `test/**/*.dart`, `pubspec.yaml` : aucune preuve réutilisée.

## 3. Architecture (tout en Dart/Impeller, aucun natif, aucun cœur)

### 3.1 Volume — `lib/widgets/library_book_volume.dart`

```dart
abstract final class LibraryBookThickness {
  static const double minimum = 0.035, maximum = 0.22, fixed = 0.09; // fraction de la largeur
  static int estimatePages({required LibraryBookFormat format, int? pageCount, required int sizeBytes});
      // cbz/pdf : pageCount ?? 120 ; epub/txt : sizeBytes ~/ 1800 ; borné 40..1200
  static double of(int pages) => lerp(minimum, maximum, (pages.clamp(40, 1200) - 40) / 1160);
}
class LibraryBookVolume extends StatelessWidget {       // corps du livre derrière la face avant
  const LibraryBookVolume({super.key, required this.opening, required this.thickness,
    required this.rightToLeft, required this.radius, this.image, this.spineColor, required this.front});
}
class LibraryBookVolumePainter extends CustomPainter {  // 8 sommets, faces triées, Lambert, ombre au sol
  static List<Offset> project(List<Vector3> corners, Size size, double tilt);   // pur, testé
  static List<LibraryBookFace> sortedFaces(List<Offset> projected, double tilt); // pur, testé
}
```

Faces : dos (bande gauche/droite de `image` assombrie par `ImageShader` + `drawVertices`,
ou `spineColor` plat sans image), tranche de papier (trois stries), face arrière, ombre au
sol ; éclairage Lambert par face (normale projetée). `LibraryBookCover` **garde son API**
(7 tests inchangés) et gagne `image: ImageProvider?` (même fournisseur que l'`Image` enfant,
résolu par `ImageStream`, `ImageInfo` libéré au `dispose`), `format`, `pageCount`,
`sizeBytes`, `thickness` (explicite, hub), `spineColor`. La face avant reste le `child`
sous la transformation 443 (les tests mesurent son rectangle), le volume est peint derrière.
Thickness : `thickness ?? LibraryBookThickness.of(estimatePages(…)) ?? fixed`. ≠ audit :
la formule `clamp(pageCount, 40, 1200)/1200` est normalisée pour que 40 pages donnent
`minimum`.

### 3.2 Ouverture animée — `lib/widgets/library_book_open_transition.dart`

```dart
class LibraryBookOpenOrigin { const LibraryBookOpenOrigin({required this.rect, this.image,
    this.rightToLeft = false, this.thickness = LibraryBookThickness.fixed}); }   // rect global de la tuile
class LibraryReaderRoute<T> extends PageRouteBuilder<T> {
  LibraryReaderRoute({required WidgetBuilder builder, LibraryBookOpenOrigin? origin, bool reduceMotion = false});
  // 520 ms (200 ms en Reduce Motion), retour 360 ms ; opaque ; fondu du lecteur de t = 0,65 à 1
}
class LibraryBookOpenOverlay extends StatelessWidget {  // OverlayEntry du navigateur racine pendant la transition
  // vol de origin.rect vers le centre (easeInOutCubic), pivot 15°, couverture à 180° côté charnière,
  // image redécodée à la largeur d'écran (ResizeImage(origin.image, width: largeur × dpr)), retrait à completed
}
```

`LibraryReaderLauncher.openLocalBook(context, book, {service, LibraryBookOpenOrigin? origin})`
et `_push(context, reader, {origin})` remplacent `MaterialPageRoute` par `LibraryReaderRoute`
(`library_reader_launcher.dart:54`, `:131-135`) ; `_showTextReader`/`_showPageReader` du hub
passent aussi à `LibraryReaderRoute` sans origine. L'origine est fournie par la vue locale
(`_BookTile.onOpen` → `_open(book, origin)`) et par les cartes « reprendre »/favoris des
livres locaux ; le hub ne la fournit jamais (ses touchers mènent à `LibraryMangaDetailsScreen`
ou à un lecteur sans couverture locale) : il reçoit le volume seul (Q15). Retour inverse au
pop vers `origin.rect` ; Reduce Motion = fondu 200 ms sans overlay. Le test
« readers are pushed on the root navigator » (`test/library_reader_misc_test.dart:292`)
reste vrai (même navigateur, autre classe de route).

### 3.3 Textures — `lib/screens/library_screen/reader/library_page_textures.dart`

```dart
class LibraryPageTexture { final ui.Image image; int get bytes => image.width * image.height * 4; void dispose(); }
class LibraryPageTextureCache {
  LibraryPageTextureCache({this.maxTextures = 5, this.maxBytes = 48 << 20});
  Future<LibraryPageTexture?> acquire(Object key, Future<ui.Image?> Function(LibraryCancelToken) render);
  LibraryPageTexture? peek(Object key);
  void retain(Set<Object> keys);                 // planche courante + voisines ±1, jamais évincées
  void purge({Set<Object> keep = const {}});     // pression mémoire : tout sauf keep
  void cancelAll(); int get textures; int get bytes; void dispose();
}
```

Clé `(sourceKey, page, decodeWidth, decodeHeight)`. Rendus : CBZ/en ligne par
`LibraryPageSource.imageFor` résolu en `ui.Image` (clone de l'`ImageInfo`) ; PDF par
`PdfPage.render(fullWidth:, fullHeight:)` puis `createImage()`, jeton vérifié avant
`createImage` et `PdfImage.dispose()` systématique (annulation des rendus hors ±1) ; EPUB
par `Picture.toImage`. LRU au-delà de 5 textures ou 48 Mio, `dispose` explicite. Aujourd'hui
trois pages décodées ; la nouvelle borne vaut pour le chemin curl, le chemin `PageView`
(glissement, aucun, Reduce Motion) garde le `precacheImage` ±1 existant. **Purge nouvelle** :
les trois lecteurs (déjà `WidgetsBindingObserver`) implémentent `didHaveMemoryPressure`
→ `purge(keep: planche courante)` (Flutter vide déjà `imageCache` de son côté).

### 3.4 Curl — `reader/library_page_curl.dart` + `assets/shaders/page_curl.frag`

```dart
enum LibraryPageTurnStyle { curl, slide, none }
enum LibraryPageTurnDirection { forward, backward }
class LibraryPageCurlProgram {
  static Future<ui.FragmentProgram> Function(String asset) loader = ui.FragmentProgram.fromAsset; // seam de test
  static Future<LibraryPageCurlProgram?> load();   // une tentative par processus ; null = repli painter, ne lève jamais
  static void resetForTesting();
}
class LibraryPageCurlController {                 // geste suivi du doigt, deux sens, RTL
  void beginDrag(Offset local); void updateDrag(Offset local);
  Future<bool> endDrag(Velocity v);              // complète si > 30 % ou vitesse > 600 px/s, sinon annule (220 ms)
  Future<bool> turn(LibraryPageTurnDirection d); // manette/zones : courbe 380 ms
}
class LibraryPageCurl extends StatefulWidget {    // front, verso (page suivante/précédente ou papier), dessous
  const LibraryPageCurl({super.key, required this.front, required this.back, this.under,
    required this.rightToLeft, required this.direction, required this.progress, required this.corner, this.program});
}
class LibraryPageCurlMeshPainter extends CustomPainter { /* repli : maillage 24×32, drawVertices + ImageShader */ }
```

Shader : uniformes `uSize`, `uCorner`, `uRadius`, `uDirection`, `uRtl` ; samplers 0 `uFront`,
1 `uBack`, 2 `uUnder` (`setImageSampler`) ; verso assombri, ombre portée. **Politique de
repli** : `load()` attrape toute erreur de `fromAsset` (actif absent, compilation refusée,
`flutter test`) et mémorise `null` ; une exception du shader pendant `paint` bascule le
lecteur sur le painter pour la session ; les tests forcent le painter par
`LibraryPageCurlProgram.loader = (_) => throw …`. Le `PageView` est **conservé** dans
`_buildPaged` ; en style `curl` (et seulement hors zoom, hors vertical), une
`LibraryPageCurlLayer` empilée au-dessus prend les glissements horizontaux (première dans
l'ordre de test d'atteinte, elle gagne l'arène), la physique du `PageView` ne change pas
(`test/library_reader_page_test.dart:268-443` conservé) et la complétion appelle
`_jumpToPage(cible, animate: false)` sous la page repliée (35 tests existants : § 5).

### 3.5 Pagination EPUB/TXT — `reader/library_reflow_paginator.dart`

```dart
class LibraryReflowPageSpec { final int chapter, indexInChapter; final LibraryReflowPosition start, end; }
class LibraryReflowPaginator {
  LibraryReflowPaginator({required LibraryReflowSource source, required LibraryReflowStyle style,
    required Size pageSize, required EdgeInsets padding, required TextScaler textScaler,
    Duration frameBudget = const Duration(milliseconds: 6)});
  Future<List<LibraryReflowPageSpec>> paginate(int chapter); // incrémental, cède la main à chaque budget
  int? pageCountOf(int chapter); LibraryReflowPageSpec? pageFor(LibraryReflowPosition position);
  ui.Picture paint(LibraryReflowPageSpec page);               // TextPainter.paint par tranche d'unité
  void invalidate(); Future<void> cancel();
}
```

Chaque unité (≤ 2000 caractères, `libraryReflowUnits`) est mise en page par `TextPainter`
(mêmes `TextStyle` que `LibraryReflowUnitView`, titres par `headingScales`) ; les pages
contiennent des lignes entières (`computeLineMetrics`, `getLineBoundary`) ; une image plus
haute que l'espace restant ouvre une page (max 0,85 de la hauteur, comme aujourd'hui).
Frontière de page = `LibraryReflowPosition(chapter, block, unit.start + offsetDeLigne)` →
`source.locationFor` → **CFI inchangé** ; reprise = `resolveLocation(saved)` puis `pageFor`.
Chapitres paginés paresseusement (courant + suivant) ; étiquette « Page N sur M » par
chapitre, pourcentage global par `fractionFor`. Nouvelle typographie ou rotation →
repagination depuis la position courante (mêmes mots en haut, règle `_setAnchor`).
`textLayout = scroll` conserve **intégralement** le chemin actuel (`_pageStep`, tests du
bouton Retour). `LibraryBookReaderScreen` gagne `rightToLeft` (défaut `false`), transmis
par le lanceur depuis `book.rightToLeft` : en mode pages, ordre des pages et charnière
inversés (l'indice `page-progression-direction` est enfin honoré) ; sans effet en défilement.

### 3.6 PDF

`LibraryPdfReaderScreen` gagne `_mode` (`LibraryPdfMode.pages | scroll`, précédence § 3.9).
`pages` : `PdfDocument.openFile` (déjà utilisé par `LibraryPdfrxInspector`) + textures § 3.3,
surface partagée avec le lecteur de pages (`LibraryPagedSurface` dans `library_page_curl.dart` :
curl, double page, RTL, cartes début/fin). `scroll` : `PdfViewer.file` actuel, `layoutPages`
à deux colonnes quand la double page s'applique. Sommaire (X) et ±10 pages (LB/RB) dans les
deux modes ; « Ajuster » (clic du stick droit, bouton de barre) en `scroll` seulement ; en
`pages` ni zoom, ni sélection, ni liens (annoncé § 6). Bascule dans la barre d'outils et la
section Navigation ; mémorisée par livre.

### 3.7 Marque-pages — `reader/library_reader_bookmarks.dart` + magasin

```dart
@immutable class LibraryBookmark {
  const LibraryBookmark({required this.id, required this.key, required this.location, required this.fraction,
    this.chapterId, this.chapterTitle, this.pageIndex, this.label, required this.createdAt});
  Map<String, Object?> toJson(); static LibraryBookmark? fromJson(Object? json);
}
// LibraryReadingStore :
static const int maxBookmarksPerTitle = 500;
List<LibraryBookmark> bookmarksFor(String key); LibraryBookmark? bookmarkAt(String key, String location);
bool addBookmark(LibraryBookmark bookmark);   // false à 500, rien n'est écrit
void removeBookmark(String key, String id);
Future<void> showLibraryReaderBookmarksSheet(BuildContext context, {required LibraryReadingStore store,
  required String progressKey, required LibraryReaderPalette palette, String? currentLocation,
  required ValueChanged<LibraryBookmark> onOpen});
class LibraryBookmarkRibbon extends StatelessWidget {}   // ruban au bord haut, option bookmarkRibbon
```

JSON : clé additive de premier niveau `bookmarks: {<key>: [ {id, key, location, fraction,
chapterId?, chapterTitle?, pageIndex?, label?, createdAt} ]}` ; `version` reste 1 ;
`_StoreData.fromJson` lit `bookmarks` avec tolérance (entrée invalide ignorée) ; jamais
évincés ; `_progressEvictable` gagne `!_bookmarks.containsKey(key)`. ≠ audit : `chapterId`
ajouté à la structure, nécessaire aux titres en ligne (le contrôleur enregistre déjà
`chapterId`). Emplacements : `page:N` (+ `chapterId`) pour pages et PDF ; CFI / `txt:b:o`
pour EPUB/TXT. Y bascule le marque-page de la position affichée ; le ruban apparaît quand
la planche ou la ligne courante en porte un.

### 3.8 Barre d'outils — `reader/library_reader_toolbar.dart`

```dart
enum LibraryReaderToolbarMode { auto, always }
class LibraryReaderToolbarProgress { final int? page, pageCount; final double fraction;
  final Duration? remainingInChapter, remainingInBook; final String? chapterTitle; }
class LibraryReaderToolbar extends StatelessWidget {
  const LibraryReaderToolbar({super.key, required this.palette, required this.progress, required this.onSettings,
    required this.onBookmarks, this.onContents, required this.onLibrary, this.slider, this.extra = const <Widget>[]});
}
class LibraryReadingPace { void pageShown(); Duration? remaining(int pagesLeft); } // moyenne glissante, après 3 tours
```

Remplace l'enfant de `LibraryReaderBottomBar` dans les trois lecteurs (le
`LibraryReaderPageSlider` reste dedans) : Réglages, Marque-pages, Sommaire/Chapitres,
Progression (page N/M, %, temps restant), Bibliothèque (= `_close`, **jamais un second
« Retour »** : il est dans la barre basse, hors de l'arbre quand les barres sont masquées,
et `expectOneBack` compte les libellés `back`). `LibraryReaderChromeController` gagne
`set alwaysVisible(bool)` : `_schedule()` sort tôt et `hide()`/`hideAfterTurn()` sont sans
effet (même voie que `_holds > 0`) ; `LibraryReaderChromeOverlay` ne change pas. Réglages en
trois sections par un nouvel item `LibraryReaderSectionHeader(title)` dans
`showLibraryReaderSettingsSheet` : Apparence (thème/fond), Texte (EPUB/TXT : taille,
interligne, police, marges, justification), Navigation (tour de page, double page, première
page seule, sens, page/vertical, mode PDF, mise en page du texte, barre d'outils, zones de
toucher, écran allumé, rotation). Les lignes de Navigation modifiées depuis un lecteur
s'écrivent **par livre** (`bookSettings[key]`) ; « Revenir aux réglages généraux » efface
l'entrée ; Apparence et Texte restent globales.

### 3.9 Réglages, précédence, modèle

```dart
enum LibraryDoublePageMode { auto, always, never }   enum LibraryPdfMode { pages, scroll }   enum LibraryTextLayout { pages, scroll }
// LibraryReaderSettings (global) — nouveaux champs et clés JSON homonymes, lus par _readEnum/readBool :
turnStyle = curl, doublePage = auto, firstPageAlone = true, pdfMode = pages, textLayout = pages,
toolbarMode = auto, bookmarkRibbon = true
@immutable class LibraryReaderBookSettings {       // clé JSON 'bookSettings': {<key>: {...}} ; null = hérite
  final LibraryPageTurnStyle? turnStyle; final LibraryDoublePageMode? doublePage; final bool? firstPageAlone;
  final LibraryPageDirection? pageDirection; final LibraryMangaMode? mangaMode; final LibraryPdfMode? pdfMode;
  final LibraryTextLayout? textLayout; final DateTime updatedAt; }
// LibraryReadingStore : bookSettingsFor(key), updateBookSettings(key, settings), clearBookSettings(key),
// maxBookSettingsTitles = 1000 (jamais pour local:)
class LibraryReaderEffectiveSettings { static LibraryReaderEffectiveSettings resolve({required LibraryReaderSettings global,
  LibraryReaderBookSettings? book, LibraryPageLayoutHint hint = unknown, LibraryReaderSessionOverrides? session}); }
```

**Précédence : surcharge de session > réglage du livre > indice du contenu > global.**
≠ audit (§ 5.3 item 8 « par livre, puis global, puis indice ») : les sources placent déjà
l'indice avant le global en mode `auto` (`controller:102-117`) ; l'ordre retenu insère le
livre entre la session et l'indice. `LibraryPageReaderController.mode`/`rightToLeft`
appliquent cet ordre ; `toggleMode`/`overrideDirection` restent les surcharges de session.
Double page : `auto` = paysage seulement ; `firstPageAlone` = couverture seule puis
planches (2-3, 4-5…) ; une planche RTL place la page suivante à gauche ; jamais en vertical.

### 3.10 Manette (les trois lecteurs ; B et Start inchangés)

| Entrée | Pages / PDF pages | EPUB/TXT pages | EPUB/TXT défilement | PDF défilement |
| --- | --- | --- | --- | --- |
| D-pad ← → | page visuelle précédente/suivante (RTL) | idem | 0,9 écran (inchangé) | page ±1 |
| D-pad ↑ ↓ | page précédente/suivante ; vertical : 0,8 écran | idem | 0,3 écran | page ±1 |
| A | barre (ou réessayer après erreur) | idem | idem | idem |
| B | fermer (`_close`) | | | |
| LB / RB | chapitre ±1 | chapitre ±1 | chapitre ±1 | ±10 pages |
| X | chapitres (titres en ligne), sinon rien | sommaire | sommaire | sommaire |
| **Y** | **marque-page** | **marque-page** | **marque-page** | **marque-page** |
| Start | réglages | | | |
| **Stick droit (clic)** | — | — | — | **Ajuster** (ex-Y) |

`LibraryReaderGamepadBindings` gagne `rightStickClick` ; `LibraryReaderGamepadScope` relie
`onRightStickClick: () => b().rightStickClick?.call()` (`GamepadNavigation` l'expose déjà).

### 3.11 Traductions — `lib/l10n/library_reader_locale.dart` (douze cartes)

Clés réutilisées : `back`, `settings`, `tableOfContents`, `fitPage`, `pageOfTotal`,
`pageNumber`, `percentRead`, `loadingBook`, `switchToPaged`, `switchToVertical`. Nouvelles
clés (français du mainteneur, mêmes paramètres dans les douze langues) : `bookmarks`
« Marque-pages » ; `addBookmark` « Ajouter un marque-page » ; `removeBookmark` « Retirer le
marque-page » ; `bookmarkAdded` « Marque-page ajouté » ; `bookmarkRemoved` « Marque-page
retiré » ; `noBookmarks` « Ce livre n’a pas de marque-page. » ; `bookmarkLimitReached`
« Limite de 500 marque-pages atteinte pour ce livre. » ; `bookmarkDefaultLabel` « Marque-page
{index} » ; `progress` « Progression » ;
`timeLeftInChapter` « {minutes} min restantes dans le chapitre » ; `timeLeftInBook`
« {minutes} min restantes dans le livre » ; `library` « Bibliothèque » ; `toolbarMode`
« Barre d’outils » ; `toolbarAuto` « Automatique (masquée après 4 s) » ; `toolbarAlways`
« Toujours visible » ; `sectionAppearance` « Apparence » ; `sectionText` « Texte » ;
`sectionNavigation` « Navigation » ; `turnStyle` « Tour de page » ; `turnCurl` « Page qui se
plie » ; `turnSlide` « Glissement » ; `turnNone` « Aucun » ; `doublePage` « Double page » ;
`doublePageAuto` « Automatique (en paysage) » ; `doublePageAlways` « Toujours » ;
`doublePageNever` « Jamais » ; `firstPageAlone` « Première page seule (couverture) » ;
`pdfMode` « Affichage du PDF » ; `pdfModePages` « Pages (tour de page) » ; `pdfModeScroll`
« Défilement et zoom » ; `textLayout` « Mise en page du texte » ; `textLayoutPages` « Pages » ;
`textLayoutScroll` « Défilement continu » ; `resetBookSettings` « Revenir aux réglages
généraux » ; `paginating` « Mise en pages… » ;
`pagesOfTotal` « Pages {first} et {second} sur {total} » (sémantique d'une planche) ;
`bookmarkRibbon` « Ruban de marque-page ». Noms de formats (EPUB, PDF, CBZ) et chemins jamais
traduits. `test/library_reader_locale_test.dart` (parité, paramètres, non-anglais, `zh_Hant`)
reste la gate ; les égalités légitimes s'ajoutent à sa liste `identical`.

### 3.12 Points d'intégration

- Hub (`library_screen.dart:2996`) : `LibraryBookCover(selected:, rightToLeft:, radius:,
  image: LibraryNetworkImage(coverUrl, headers:, cacheWidth:), thickness: LibraryBookThickness.fixed,
  child: …)` — modèle de sélection par index inchangé.
- Vue locale (`_BookTile`, `:1004-1110`) : devient `StatefulWidget` avec `_focused`, dérivé
  de `LibraryFocusRing.onFocusChange` (transmis au parent comme aujourd'hui) ; la couverture
  est enveloppée dans `LibraryBookCover(selected: _focused, image: ResizeImage(FileImage(…)),
  format: book.format, pageCount: book.pageCount, sizeBytes: book.sizeBytes, rightToLeft:
  book.rightToLeft, child: Image(…))` ; libellé `Semantics` `'${book.title}, $progressLabel'`
  inchangé (`test/library_ui_local_view_test.dart:698-711`). `onOpen` fournit l'origine
  (`RenderBox.localToGlobal`) à `_open`.
- Favoris / « reprendre » (`_Cover`, `:1119-1151`) : `LibraryBookCover(selected:, image:,
  thickness: livre local ? estimation : fixed, child: …)` dans `_buildContinueCard` et les
  cartes de favoris ; origine fournie pour les livres locaux.
- Reduce Motion (`MediaQuery.disableAnimationsOf`, lu dans `didChangeDependencies` à côté
  de `accessibleNavigation`) : style de tour forcé à `none` (`jumpToPage`), route en fondu
  200 ms sans overlay, couverture et volume immobiles (règle 443), ruban sans animation.

## 4. Phases

| # | Contenu | Fichiers | Tests |
| --- | --- | --- | --- |
| 1 | Magasin : marque-pages, `bookSettings`, nouveaux champs globaux, `_progressEvictable`, tolérance | `lib/services/library_reading_store.dart`, `reader/library_reader_bookmarks.dart` (modèle) | `test/library_reading_store_bookmarks_test.dart` (nouveau), `test/library_infra_reading_store_test.dart` (étendu) |
| 2 | Volume + couverture | `lib/widgets/library_book_volume.dart`, `lib/widgets/library_book_cover.dart`, hub, vue locale, favoris | `test/library_book_volume_test.dart` (nouveau), `test/library_book_cover_test.dart` (7 inchangés + ajouts), `library_ui_hub_test`, `library_ui_local_view_test`, `library_ui_hub_favorites_test` (étendus) |
| 3 | Ouverture animée | `lib/widgets/library_book_open_transition.dart`, `library_reader_launcher.dart`, `library_screen.dart` | `test/library_book_open_transition_test.dart` (nouveau), `test/library_reader_misc_test.dart` (lanceur) |
| 4 | Textures + curl CBZ/en ligne | `reader/library_page_textures.dart`, `reader/library_page_curl.dart`, `assets/shaders/page_curl.frag`, `pubspec.yaml`, `reader/library_page_reader_screen.dart`, `reader/library_page_reader_controller.dart`, `reader/library_reader_gamepad.dart` | `test/library_page_textures_test.dart`, `test/library_page_curl_test.dart` (nouveaux), `test/library_reader_page_test.dart` (35 verts + ajouts) |
| 5 | PDF deux modes | `library_pdf_reader_screen.dart` | `test/library_reader_pdf_modes_test.dart` (nouveau ; pdfium absent en test : rendu injecté) |
| 6 | Pagination EPUB/TXT | `reader/library_reflow_paginator.dart`, `reader/library_book_reader_screen.dart` | `test/library_reflow_paginator_test.dart` (nouveau), `test/library_reader_book_test.dart` (27 verts + ajouts) |
| 7 | Barre d'outils, marque-pages, sections, manette Y / stick droit | `reader/library_reader_toolbar.dart`, `reader/library_reader_chrome.dart`, `reader/library_reader_sheets.dart`, les trois lecteurs, `lib/l10n/library_reader_locale.dart` | `test/library_reader_toolbar_test.dart`, `test/library_reader_bookmarks_test.dart` (nouveaux), `test/library_reader_back_button_test.dart` (étendu : mode `always`), `test/library_reader_locale_test.dart` |
| 8 | Accessibilité et performance : Reduce Motion, purge mémoire, sémantique « Page N sur M » / planche, compteurs (`textures`, `bytes`, temps de pagination) dans la trace `library.reader.*` | les trois lecteurs | `test/library_reader_accessibility_test.dart` (nouveau) |
| 9 | Gate : `BUILD447_BOOKS_DELTA`, contrat Python, document | `build-utils/verify_delivery_reuse.py`, `test/library_books_3d_contract_test.py`, `.github/workflows/retroarch-delivery.yml` (une ligne `python3`), `docs/library-books-3d-plan.md` | `python3 build-utils/verify_delivery_reuse.py --offline`, `test/delivery_pipeline_test.py`, `test/retroarch_baseline_scope_test.py` |

Bloc `BUILD447_BOOKS_DELTA` (modèle `BUILD440_DELTA`, `verify_delivery_reuse.py:749`) :
tous les fichiers des colonnes « Fichiers » et « Tests » ci-dessus, `pubspec.yaml`,
`lib/screens/library_screen/library_local_view.dart`, `library_favorites_view.dart`,
`library_screen.dart`, `test/delivery_pipeline_test.py` si une assertion de forme change.
CI : les tests Dart sont pris par le glob `flutter test test/library_*_test.dart`
(`retroarch-delivery.yml:106`) ; le contrat Python s'insère après `:143`. La voie
`library_covers` (443, `:175-192`, `test/library_cover_delivery_test.py`) n'est pas utilisée
par la livraison `full` ; son assertion « `pubspec.yaml` inchangé depuis 443 » est déjà
caduque dans ce cycle (dépendance AirPlay) et n'est pas réparée ici.

## 5. Tests (jamais affaiblis ; contrats retirés remplacés par le nouveau comportement)

| Fichier | Vérifie |
| --- | --- |
| `test/library_reading_store_bookmarks_test.dart` | ajout/retrait, limite 500 (refus sans écriture), `bookmarks` et `bookSettings` écrits sous `version` 1, relecture d'un fichier 1 **avec clés inconnues** (jamais couvert avant), entrées invalides ignorées, `local:` et titres à marque-pages jamais évincés, atomicité (`.tmp` absent) |
| `test/library_book_volume_test.dart` | `estimatePages`/`of` bornés (40 → minimum, 1200 → maximum, PDF/CBZ par `pageCount`), `project`/`sortedFaces` purs (dos visible côté charnière, faces arrière derrière), rendu sans image = `spineColor`, Reduce Motion immobile, aucun ticker après dispose |
| `test/library_book_cover_test.dart` | les 7 tests 443 inchangés + `image` résolue puis libérée, `thickness` explicite |
| `test/library_book_open_transition_test.dart` | overlay inséré puis retiré, vol depuis `origin.rect`, charnière RTL, Reduce Motion = fondu sans overlay, un seul retrait de route au retour, hub sans origine |
| `test/library_page_curl_test.dart` | `load()` ne lève jamais (loader qui échoue → painter), complétion > 30 % ou vitesse, annulation, RTL, `jumpToPage` sous la page, curl désactivé en zoom/vertical/Reduce Motion, physique du `PageView` inchangée |
| `test/library_page_textures_test.dart` | LRU 5 / 48 Mio, `retain` jamais évincé, `dispose` compté, annulation d'un rendu en cours, `purge(keep:)` |
| `test/library_reflow_paginator_test.dart` | pages de lignes entières, page → position → CFI/`txt:b:o` → page (aller-retour), repagination à la typographie/rotation sur les mêmes mots, image seule, budget par image, RTL |
| `test/library_reader_pdf_modes_test.dart` | bascule pages/défilement, `layoutPages` en double page, Ajuster sur le clic du stick droit seulement en défilement, Y = marque-page |
| `test/library_reader_toolbar_test.dart` | cinq actions, mode `always` (barre jamais masquée, `hideAfterTurn` sans effet), progression et temps restant après 3 tours, un seul « Retour » (`expectOneBack`) barres affichées |
| `test/library_reader_bookmarks_test.dart` | Y bascule dans les trois lecteurs, ruban, feuille (ouverture, suppression), libellés `fr` et `zh-TW` |
| `test/library_reader_accessibility_test.dart` | `disableAnimations` → style `none`, route 200 ms ; `didHaveMemoryPressure` → purge sauf planche courante ; sémantique « Page N sur M » / « Pages N et N+1 sur M » |
| `test/library_reader_page_test.dart`, `library_reader_book_test.dart`, `library_reader_back_button_test.dart` | existants verts (mise en place explicite `turnStyle: slide` / `textLayout: scroll` où le chemin 440 est testé) + précédence session > livre > indice > global, EPUB RTL honoré |
| `test/library_books_3d_contract_test.py` | `page_curl.frag` déclaré dans `pubspec.yaml` ; `fromAsset` seulement derrière `LibraryPageCurlProgram.load` ; aucune nouvelle dépendance (`pubspec.lock` identique) ; `didHaveMemoryPressure` et `disableAnimationsOf` présents dans les trois lecteurs ; `rightStickClick` relié ; aucun texte en dur hors `lib/l10n` ; aucune mention de `Library/Sources` |

## 6. Limites annoncées dans l'interface et non vérifié sans iPhone

- Annoncé : PDF en mode pages sans zoom, sélection ni liens (« Défilement et zoom » à un
  toucher) ; pagination EPUB « de lecteur » (ni césure, ni veuves/orphelines, polices
  système seulement) ; double page jamais en défilement vertical ; curl désactivé en zoom ;
  marque-pages propres à NeoStation (pas d'échange avec d'autres lecteurs) ; CBR/CB7/MOBI/DRM
  toujours refusés ; épaisseur EPUB/TXT estimée ; sans origine de tuile, l'ouverture est un
  simple fondu.
- Non vérifiable ici (§ 12 de l'audit) : exécution réelle du shader sur Impeller/iPhone et
  fluidité du curl (le repli painter est prouvé, pas le shader) ; mémoire sur grands CBZ et
  PDF (48 Mio + cache pdfrx + `imageCache`) ; VoiceOver (un seul « Retour », planches) ;
  manette (Y, stick droit) ; correspondance exacte de `disableAnimations` avec « Réduire les
  animations » d'iOS ; coût de la pagination sur de longs chapitres. Journal :
  `library.reader.textures:<n>/<octets>`, `library.reader.paginate:<chapitre>:<ms>`,
  `library.reader.curl:<shader|painter>`, `library.reader.memory_pressure`. Protocole de
  validation iPhone à joindre au rapport final, comme l'exige AGENTS.md.

## 7. Déviations consignées à l'implémentation (12 octobre 2026)

Relevées dans les rapports des phases et vérifiées par le lead à l'intégration. Les signatures des §§ 3.1–3.12 sont
conservées sauf mention ci-dessous.

### 7.1 Phase 1 — magasin

- `LibraryReaderBookSettings.updatedAt` est facultatif au constructeur, non nul à la lecture (époque par défaut) et
  ignoré par l'égalité : `updateBookSettings` saute une écriture sans changement, comme `updateSettings`.
- Un champ s'efface par `copyWith(clear: {LibraryReaderBookField.x})` ; donné et effacé à la fois, il est effacé.
- `maxBookSettingsTitles` est un paramètre du constructeur (1 000 par défaut), comme `maxChapterMarkTitles` ; les
  retraits sont comptés, enregistrés et journalisés ; seules les clés `local:` et la clé en cours d'écriture sont
  protégées (pas les favoris).
- `addBookmark` refuse aussi, sans rien écrire, un identifiant déjà présent pour le titre et une clé, un identifiant
  ou un emplacement vide ; il enregistre le marque-page normalisé par `fromJson(toJson())` (NaN → 0, `createdAt` en
  millisecondes UTC) ; avant le chargement il renvoie `true` et la relecture du fichier le vérifie à nouveau.
- `updateBookSettings` avec des réglages vides vaut `clearBookSettings` ; une clé vide est ignorée.
- `moveProgress` déplace aussi marque-pages et réglages du livre, sans jamais écraser la destination : un livre local
  modifié sur place change d'identifiant, et ses marque-pages, jamais évincés, resteraient orphelins.
- `_readDate` renvoie `null` pour une date hors plage au lieu de lever : une seule date invalide faisait traiter tout
  le fichier comme corrompu (mis de côté, magasin vide).
- Le style de tour résolu n'est pas forcé à « aucun » en défilement vertical ni en zoom : les lecteurs en décident.

### 7.2 Phase 2 — volume

- Type vectoriel propre (`LibraryBookVector3`) : importer `vector_math`, dépendance transitive, déclencherait
  `depend_on_referenced_packages`, et `pubspec.yaml` ne change pas pour cela.
- `project` et `sortedFaces` gagnent un `pitch` facultatif ; le signe de `tilt` code le côté de la charnière
  (positif : gauche).
- Projection en perspective décentrée dont le plan image est la face avant (rectangle 443 inchangé) ; œil côté
  charnière, un peu au-dessus : dos et tête visibles, la gouttière ne l'est pas, les « trois traits » de tranche sont
  donc sur la tête. Éclairage de Lambert par normale de face (lumière au-dessus, côté gouttière), visibilité par
  l'orientation du quadrilatère projeté, faces latérales peintes en extrusion du contour arrondi de la couverture
  (0,75 px dessous) pour supprimer une encoche et un liseré vus au rendu.
- Un EPUB ou TXT sans `sizeBytes` reçoit l'épaisseur `fixed` ; couverture et favoris utilisent `estimate`.
- Mise en page 443 : la marge fixe (1, 2, 5, 5) devient les marges du volume plus les retraits du dos et de la tête
  (face avant un peu plus petite pour un livre épais) ; le dos `DecoratedBox` et son `BoxShadow` sont remplacés par
  le volume ; les trois feuillets sont rentrés d'un pixel côté charnière. Les transformations 443 ne changent pas.
- Défaut 443 corrigé : un appui commencé sur une couverture puis emporté par un long glissement appelait `reverse()`
  sur un contrôleur libéré (`mounted` vérifié ; le test de non-régression échoue sans le correctif).
- Le dos résout l'image par `ScrollAwareImageProvider` (rien n'est chargé pendant un défilement rapide), ne garde que
  la première image et ne signale pas les erreurs, laissées à l'`Image` de la face ; `LibraryBookVolume.image` est un
  `ui.Image` décodé, pas un provider.
- Favoris : côté de la charnière transmis (valeur du livre local ; `true` pour les titres en ligne, mangas Aidoku
  comme dans le hub) ; un favori local n'a une épaisseur estimée que s'il figure déjà dans « Reprendre ».

### 7.3 Phase 3 — ouverture

- Reduce Motion d'iOS : le moteur ne règle que `AccessibilityFeatures.reduceMotion` et `disableAnimations` n'est
  jamais vrai sur iOS. La route lit donc aussi `PlatformDispatcher.accessibilityFeatures.reduceMotion` ; la phase 8
  étend cette lecture à la couverture, au volume, aux trois lecteurs et au ruban.
- La route écoute son propre contrôleur : le `HeroController` de `MaterialApp` montre la page poussée hors écran
  pendant sa première image, où `ModalRoute.animation` est déjà « terminée ».
- Sans origine : 520/360 ms avec un fondu sur toute la durée, au lieu d'un fondu retardé depuis 0,65 qui figeait
  environ 340 ms ; mouvement réduit : 200 ms dans les deux sens.
- Au retour, le livre revole vers la position actuelle de la tuile (`locate`, sinon `origin.rect`) : la lecture le
  place en tête de « Reprendre » et une première lecture ajoute une barre de progression ; si la taille de l'overlay
  a changé (rotation), simple fondu.
- `_push` reçoit le `NavigatorState` racine, capturé avant le chargement asynchrone ; les couvertures
  `LibraryNetworkImage` sont recréées avec `cacheWidth` (`ResizeImage` ne peut pas envelopper un provider qui fixe
  lui-même la taille de décodage) ; la tuile reste visible sous le livre en vol, assombrie jusqu'à 45 %.

### 7.4 Phase 4 — textures, pli, planches

- Uniformes supplémentaires `uPage`, `uAlign`, `uShadow`, tailles des trois images et `uPaper` ; la géométrie est
  calculée en Dart et partagée avec le peintre de repli.
- Un geste de plus de 600 px/s dans le sens opposé annule le tour, même au-delà de 30 %.
- Une exception du shader pendant la peinture bascule l'instance et marque le programme en échec : tout le processus
  passe au peintre, plutôt qu'une exception par tour.
- `LibraryPageCurl` gagne `spread` et `paperColor` ; `under` nul vaut du papier (la couche recouvre un `PageView` qui
  montre encore la page courante).
- Progression = déplacement du doigt / largeur de page (demi-largeur en planche) ; fin du tour en 380 ms × fraction
  restante, 120 ms au moins.
- Pages seules en double page : couverture à droite en lecture de gauche à droite (à gauche de droite à gauche),
  dernière page seule du côté opposé ; dans un tour de planche, seule la page extérieure se soulève et son verso
  montre la page en vis-à-vis de la planche visée.
- La couche purge elle-même son cache ; `retain()` annule les rendus hors de l'ensemble retenu ; une texture non
  retenue arrivant dans un cache plein de textures retenues est libérée et `acquire` renvoie `null`.
- Page impossible à rendre (résultat nul ou exception, hors annulation) : les tours depuis cette page glissent
  (`PageView`) ; nouvel essai au préchargement suivant.
- Pas de `LibraryPagedSurface` : recette documentée dans `library_page_curl.dart` et `LibraryPageSpreadLayout`.

### 7.5 Phase 4b — lecteur CBZ et chapitres en ligne

- Les tests du chemin 440 posent explicitement `turnStyle: slide` et aussi `doublePage: never` (surface de test en
  paysage).
- Reduce Motion est une surcharge de session du contrôleur (repli : saut, § 3.12).
- API du contrôleur étendue ; `fraction` et marques de lecture tiennent compte des planches.
- Repli de décodage : un pli ne démarre que si chaque page de la face actuelle et de la face visée est dessinable
  (texture prête, ou image décodée dans le cache d'images de Flutter sous une clé synchrone) ; sinon le tour glisse,
  ou saute avec le style « aucun » ou Reduce Motion. Une page en chargement ou en échec n'est jamais pliée ; seules
  les pages déjà décodées reçoivent une texture d'avance, les autres au début du tour, avant sa première image.

### 7.6 Phase 5 — PDF

- Mode pages : `LibraryPdfPagesView` ; aucune carte de début ni de fin ; zones de toucher ajoutées (réglage `tapZones`
  existant, montré en mode pages seulement, aucun texte nouveau).
- Jusqu'à 6 textures en planches paysage (trois planches × deux pages retenues, jamais évincées) ; 5 au plus en
  pages simples, ce que vérifie le test.
- Page enregistrée pour une planche : la page courante si la planche la contient, sinon sa première page, ou la
  dernière page du livre quand elle est affichée (un livre lu jusqu'à sa dernière planche est terminé).
- Un tour en cours à la fermeture, au passage en arrière-plan ou au changement de mode enregistre la page visée, comme
  le correctif 440 du lecteur CBZ.
- Corrigé en cours de travail : quitter le style « pli » relâchait les textures conservées ; la vue les reprend à
  l'image suivante.
- `library_reader_misc_test` (restauration en paysage) ouvre en mode pages, où l'ouverture réelle n'aboutit jamais
  sans PDFium ; il reste vert.

### 7.7 Phase 6 — pagination EPUB et TXT

- API ajoutée : `locate`, `prefetch`, `pageAt`, `next`, `previous`, `update`, `prepare`, `textOf` (VoiceOver),
  `linkAt` (liens en mode pages), `statsOf` (trace), `dispose` ; constructeur : `textDirection`, `locale`, `images`,
  `devicePixelRatio`, `maxChapters` ; `paint(pixelRatio:)`.
- Images : pas de résolveur externe ; la mise en page ne lit que l'en-tête (`ImageDescriptor`) avec le cache
  d'octets partagé avec le défilement ; `prepare(page)` décode à la largeur du texte × densité (2 048 px au plus,
  jamais agrandi), six conservées ; `paint` reste synchrone. Plafond : `min(0,85 × hauteur de page, zone de texte −
  1 em)`.
- Espacement supprimé en haut d'une page ouverte par une coupure, conservé en première page de chapitre ; un titre
  n'est jamais coupé (sauf plus haut qu'une page) et reste avec le texte qui suit ; chaque chapitre, et chaque
  section TXT de 200 paragraphes, commence une page ; hauteur d'un élément de liste = max(puce, texte) ; les pages
  d'une mise en page précédente se peignent avec leur géométrie, dans la palette courante.
- Position en mode pages : début de la dernière page atteinte par un tour, ou, jusqu'au tour suivant, la position
  d'ouverture ou de saut ; les remises en page la conservent, sans dérive en arrière.
- Textures du pli par `toImageSync` ; en planche, TXT ne laisse seule que la première page ; style « aucun » : le
  glissement du doigt fait encore glisser le `PageView`, toucher, manette et sauts sont immédiats ; le sens global
  (réglage manga) ne s'applique pas à EPUB et TXT.

### 7.8 Traductions

- 46 clés : les 37 du § 3.11 et neuf de plus (`chapters`, `bookmarkedPage`, `navigationPerBookNote`,
  `pdfPagesLimits`, `textPagesLimits`, `doublePageNotVertical`, `curlDisabledZoom`, `bookmarksLocalOnly`,
  `bookSettingsActive`). `pdfPagesLimits` cite le texte `pdfModeScroll` de chaque langue ; « 500 » et « 4 s » sont
  écrits dans les textes et changeraient dans les douze langues avec leurs constantes. Égalités légitimes ajoutées à
  la liste `identical` : `fr:sectionNavigation`, `fr:textLayoutPages`, `de:sectionText`, `de:sectionNavigation`.
  Aucune relecture par des locuteurs natifs.

### 7.9 Phase 7 — barre d'outils, marque-pages, sections, Y

- Chapitres en ligne : emplacement `page:N@<chapterId>`, avec `chapterId` et `pageIndex` enregistrés ; le magasin
  n'admet qu'un marque-page par emplacement, et `page:N` seul confondrait deux chapitres.
- Réglages et Sommaire passent dans la barre d'outils (les tests existants exigent un seul contrôle de chaque) ; la
  barre haute garde Retour, le titre et Ajuster (PDF en défilement).
- Progression : CBZ/en ligne et PDF gardent « n / N » sur le curseur, la cellule de progression montre le
  pourcentage et le temps restant ; en EPUB/TXT pages, la cellule montre aussi la page dans le chapitre (clé de
  test `library-book-pages-label`, désormais `LibraryReaderToolbar.pageLabelKey`) ; champs ajoutés `lastPage`
  (planches) et `paginating` (« Mise en pages… ») ; VoiceOver lit un seul nœud « Progression », titre du chapitre
  compris.
- Temps restant : un seul à l'écran, celui du chapitre s'il est connu, sinon celui du livre ; VoiceOver lit les
  deux. Chapitre : chapitres en ligne et EPUB (les sections TXT ne comptent pas comme chapitres). Livre : CBZ, PDF et
  EPUB/TXT en pages (pages des chapitres suivants estimées d'après la part du livre couverte par le chapitre
  courant). Titres en ligne : pas de temps du livre (pages des autres chapitres inconnues) ; défilement continu :
  aucun temps.
- `LibraryReadingPace` : `pageShown({pages})` (une planche compte ses pages), `restart()` (saut, tour en arrière,
  nouveau chapitre, ouverture), fenêtre de 10 tours, tours de moins de 0,5 s par page ou de plus de 10 min écartés ;
  horloge de test `LibraryReadingPace.defaultClock`.
- Barre d'outils : `contents` (sommaire ou chapitres), `bookmarked` (icône pleine, l'état reste visible quand le
  ruban est masqué), `settingsIcon` ; `onBookmarks` nul pour un PDF sans `progressKey` (bouton inactif, `y` nul).
- Mode « Toujours visible » : `LibraryReaderBarsInset` pose les pages des lecteurs d'images entre les barres et
  réserve la hauteur de la barre sous le texte EPUB/TXT, sinon des barres impossibles à masquer couvriraient des
  pages PDF (sans zoom en mode pages) et les dernières lignes EPUB ; l'overlay ne change pas.
- Feuille des marque-pages : première ligne « Ajouter / Retirer le marque-page » (équivalent tactile de Y), bouton de
  suppression par ligne, pied `bookmarksLocalOnly`, message en place à la limite de 500 ; manette : A ouvre, X
  retire, Y bascule, B ferme ; paramètres `isShown`, `onToggle`, `chapterLabel` ; le libellé par défaut
  « Marque-page {index} » suit le rang, rien de traduit n'est enregistré.
- « Affiché » : en pages et PDF, toute la planche (Y retire les marque-pages qu'elle porte, sinon en ajoute un à sa
  première page) ; en EPUB/TXT, la planche en pages ou la ligne de lecture en défilement ; un marque-page correspond
  quand sa fraction tombe dans l'intervalle (un marque-page pris avant un changement de typographie apparaît sur la
  page qui porte désormais ses mots) ; ouvrir un marque-page résout son emplacement, sinon sa fraction.
- Réglages : notes issues des clés de la phase 1 (`navigationPerBookNote`, `bookSettingsActive`, `pdfPagesLimits`,
  `textPagesLimits`, `curlDisabledZoom`, `doublePageNotVertical`) ; « Ruban de marque-page » rangé sous Apparence ;
  lignes de page masquées là où elles ne s'appliquent pas (EPUB/TXT en défilement continu, PDF en défilement) ; la
  ligne de sens du lecteur de pages ne pose plus la surcharge de session `overrideDirection` (la valeur du livre
  l'emporte déjà sur l'indice, et « Revenir aux réglages généraux » l'annule) ; les écritures globales 440 du sens
  et du mode de lecture deviennent des écritures par livre ; un PDF sans `progressKey` écrit la navigation en
  global, sans note ni retour.
- Les messages passent par `showLibraryReaderMessage` ; comme avant la phase 7 pour EPUB/TXT, le `ScaffoldMessenger`
  pose aussi la barre de message dans la route en dessous, masquée par le lecteur.
- Tests : les nouveaux fichiers importent les aides d'autres tests avec `show` (`expectOneBack`, `usePhone`,
  `PopRecorder`, `FakeOpener`, `rendered`, `mockPathProvider`) plutôt que de les dupliquer.

### 7.10 Phase 8 — mouvement réduit, mémoire, VoiceOver, trace (et suite de la phase 7)

- « Appliquer à tous les livres » (`applyNavigationToAllBooks`, confirmation `navigationAppliedToAllBooks`, douze
  langues) rétablit un chemin vers les réglages généraux de navigation, que l'écriture par livre de la phase 7 avait
  fait disparaître (en 440, le sens et le mode de lecture s'écrivaient en global depuis le lecteur). La ligne n'est
  proposée que si le livre a ses propres réglages ; elle copie ses valeurs dans les réglages généraux, puis ne garde
  au livre que les champs pour lesquels un indice de contenu s'applique et diffère de son choix (l'indice l'emporte
  sur le global : les effacer changerait ce que le livre affiche) ; les autres livres gardent leurs réglages. La
  confirmation s'affiche dans la feuille, en région annoncée à VoiceOver (une barre de message serait cachée par la
  feuille) ; ordre : « Réglages propres à ce livre », « Appliquer à tous les livres », « Revenir aux réglages
  généraux ».
- Mouvement réduit : `libraryReduceMotion(context)` (`lib/widgets/library_reduce_motion.dart`) vaut
  `disableAnimations` ou `accessibilityFeatures.reduceMotion`, seul signal d'iOS ; les trois lecteurs l'observent
  (`didChangeAccessibilityFeatures`). Au-delà du style de tour forcé à « aucun » : barres en fondu sur place (le bouton
  Retour flottant cesse de recevoir les touchers dès qu'elles paraissent), feuilles et dialogue de lien sans
  animation (`AnimationStyle.noAnimation`), défilement de focus immédiat, bande verticale et zoom par double toucher
  immédiats, défilement continu EPUB/TXT par sauts, PDF en défilement sans durée. La couverture lit le drapeau au
  moment où elle commencerait à bouger (aucun observateur par tuile) ; le volume n'a pas d'animation propre ;
  `LibraryBookOpenTransition` est inchangée (elle lisait déjà le drapeau sans dépendre de MediaQuery et compte aussi
  `accessibleNavigation`).
- Pression mémoire : le lecteur de pages purge ses textures sauf la planche affichée (la couche du pli purge aussi) ;
  pour le PDF, la vue des pages et la couche purgent déjà, et le cache de pdfrx en défilement (100 Mio par défaut) n'a
  pas de purge publique : la méthode du lecteur n'écrit que la ligne de trace ; EPUB/TXT : textures, images décodées
  (`LibraryReflowPaginator.releaseImages(keep:)`) et octets d'images (`LibraryReflowImageCache.releaseBytes()`,
  proportions conservées) ; une page repeinte après une libération décode d'abord ses images.
- VoiceOver : une page seule dit « Page N sur M » (pages et bande verticale ; avant : « Page N »), contrat de
  `library_reader_page_spreads_test` remplacé ; une page en échec donne son numéro, puis l'erreur et « Réessayer » en
  nœuds séparés ; un échec que la Bibliothèque ne sait pas nommer affiche et annonce `imageUnavailable` au lieu de
  `errorGeneric` (texte visible changé) ; PDF : un rendu en échec est noté (`unavailablePages`) et lu « Page N sur M »
  puis « Image indisponible » ; EPUB/TXT : « Page N sur M » ou « Pages N et N+1 sur M », numérotées dans le chapitre
  (« Page N » pendant la mise en page) ; une image impossible à afficher en mode pages est lue « Image indisponible »
  comme en défilement. Aucune clé ajoutée pour ces annonces.
- Trace (`LibraryReaderTrace`, niveau info, jusque dans le fichier journal) : `textures` relevé aux changements de
  page et après une pression mémoire, écrit seulement quand il change et jamais à 0/0 ; `curl:<shader|painter>` une
  fois par ouverture, défilement compris ; `paginate:<chapitre>:<ms>` par `LibraryReflowPaginator.onPaginated`
  (préchargements et remises en page compris) ; `memory_pressure`. Les tests lisent ces lignes par
  `Logger.addLogListener`.
- Visibilité : `LibraryPdfPagesViewState.textures` n'est plus réservé aux tests (la trace le lit) ; points de test
  `LibraryBookReaderScreenState.reflowImages` et `unavailablePages`.

### 7.11 Phase 9 — contrat et livraison

`test/library_books_3d_contract_test.py` (7 tests), exécuté par le job `checks` juste après le contrat d'orientation :
shader déclaré dans `pubspec.yaml` et chargé seulement par `LibraryPageCurlProgram` ; `pubspec.lock` identique à la
source 446 (SHA-256 épinglé : aucune dépendance) ; `libraryReduceMotion`, `didChangeAccessibilityFeatures` et
`didHaveMemoryPressure` dans les trois lecteurs, et plus aucun `MediaQuery.disableAnimationsOf` seul ; couverture et
ouverture lisent le drapeau d'iOS ; clic du stick droit relié (Ajuster, PDF en défilement seulement) ; aucun texte
littéral visible dans les fichiers des livres ; aucune mention du dossier `Library/Sources` ; `BUILD447_BOOKS_DELTA`
déclare les entrées et les tests du chantier, sans entrée périmée. Les tests Dart restent pris par
`flutter test test/library_*_test.dart`.

### 7.12 Corrections de la revue contradictoire du chantier (12 octobre 2026)

Revue en lecture seule de `72b96dd2` ; sept constats corrigés, chacun avec des tests qui échouent sans le correctif.

1. **Chapitre fini sur une planche.** Un chapitre en ligne terminé sur une double page était enregistré à la première
   page de la planche, donc rouvert sur sa fin et proposé par « Continuer » au lieu du chapitre suivant. Quand la
   dernière planche est affichée, sa dernière page est désormais enregistrée (position et marque de chapitre), comme
   pour le PDF ; trois tests de planches qui figeaient l'ancienne règle sont remplacés (commentés).
2. **Retour à une build antérieure.** La 446 réécrit le fichier du magasin avec les seules clés qu'elle connaît : une
   réinstallation de la 446 par-dessus la 447 (SideStore garde les données) aurait effacé marque-pages, réglages par
   livre et les sept nouveaux réglages généraux. `reading-state.json` garde exactement la disposition de la 446 ; les
   données de la 447 vont dans `Library/reading-state-extra.json` (`LibraryReadingStore.extraFileName`, version 1 :
   `settings` {turnStyle, doublePage, firstPageAlone, pdfMode, textLayout, toolbarMode, bookmarkRibbon}, `bookmarks`,
   `bookSettings`, `evictions.bookSettingsTitles`), écrit de façon atomique après le fichier principal, que les
   builds antérieures ne touchent jamais. Les deux fichiers conservent ce qu'ils ne connaissent pas (clés de premier
   niveau, champs des réglages, des retraits et de chaque entrée, déplacés avec l'entrée par `moveProgress`). Fichier
   corrompu d'un côté : mis de côté en `.corrupt`, l'autre partie se charge ; illisible : aucun des deux n'est
   remplacé. Aucune migration : la 447 n'avait jamais été livrée. Test de retour arrière : réécriture « 446 » du
   fichier principal puis rechargement 447, sur deux cycles.
3. **Dernier marque-page supprimé** depuis la feuille sans ligne d'ajout (carte de début ou de fin, remise en page) :
   l'erreur `ArgumentError` du calcul du focus est corrigée.
4. **Tour en cours en EPUB/TXT.** Fermer, quitter ou passer en arrière-plan pendant un pli ou un glissement
   enregistre la page visée (`_turnTarget`, `_commitTurnInFlight()`), comme les lecteurs PDF et CBZ.
5. **Sens des PDF.** Le sens global vient du lecteur de mangas (440–446) et ne s'appliquait pas aux PDF ; maintenant
   que les PDF s'ouvrent en mode pages, il les aurait tous inversés. Les PDF n'écoutent plus que la session et leur
   propre réglage ; sans clé de progression, le choix du sens dure le temps de la session. Depuis un PDF,
   « Appliquer à tous les livres » rend ses choix généraux (son sens vaut alors pour les CBZ et chapitres en ligne),
   le PDF gardant pour lui un sens droite-à-gauche, que le global ne lui appliquerait pas.
6. **Réglages changés avant le chargement** (ou fichier illisible) : seuls les champs modifiés sont rejoués sur
   l'entrée enregistrée, au lieu de la remplacer ; même correction pour les réglages généraux (`updateSettings`).
7. **Un seul « Retour »** vérifié aussi sur les modes pages par défaut du PDF et d'EPUB/TXT (barres affichées,
   masquées, après un pli, bouton flottant).

Limites ajoutées au § 6 : les textures retenues pour la planche affichée et ses voisines sont à la résolution de
l'écran et échappent aux plafonds de 5 textures et 48 Mio, soit environ 68 Mo par lecteur EPUB ou PDF ouvert sur un
iPad 13 pouces (estimation, non mesurée ; environ 43 Mo sur un iPhone Pro Max en portrait) ; pour un CBZ, ces textures
partagent la mémoire du cache d'images de Flutter et la trace les compte deux fois. Retour à la 446 : un livre local
modifié sur place sous la 446 laisse ses marque-pages sous l'ancienne clé ; la 446 peut évincer la position d'un titre
en ligne qui a des marque-pages ; un arrêt brutal entre les deux renommages peut laisser le fichier annexe en retard
d'une écriture. Rien n'est vérifié sur iPhone ; le retour à la 446 est simulé, pas fait avec l'IPA sous SideStore.
