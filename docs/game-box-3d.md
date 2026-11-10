# Boîtiers 3D de la bibliothèque (Carrousel, Grille, Liste), lecture du dos, notice dans le boîtier et ouverture au lancement

Build 493 (20 octobre 2026) : les boîtiers passent aux trois vues de la bibliothèque, le halo ne reste que sur le titre sélectionné de la vue Liste, la visionneuse a un bouton Retour, une vue plane du dos et une commande « Ouvrir la boîte » qui montre le support et la notice PDF déjà téléchargée, que l'on prend et lit dans le lecteur de notices de NeoStation (§ 3, § 11 ; plan : [`build493-plan.md`](build493-plan.md)).

Build 494 (20 octobre 2026) : netteté et lisibilité du texte des dos — dos et vue à plat dessinés à la taille exacte qu'ils occupent à l'écran, légère accentuation optionnelle (« Texte net »), boîtier plus grand en portrait, seconde lecture des plus petits caractères qui complète celle de la Build 493 sans jamais la remplacer (§ 12 ; plan : [`build494-plan.md`](build494-plan.md)).

Correction du 1er novembre 2026 (PS3 et Switch en priorité, vidéo du mainteneur filmée sur le code de `6d17e6d`, identique au HEAD `df337fe` pour tous les fichiers du boîtier) : boîtiers rigides aux dimensions physiques quelle que soit l'image, plastique transparent PS3/Switch distinct de l'impression de la jaquette, images posées sans déformation et reconnues (scan, jaquette dépliée, rendu 3D, icône ou logo), rotation sans saut de projection, images refusées quand elles ne sont pas des scans (dos vert uniforme), dimensions WebP/GIF/BMP lues, zoom au point de pincement, et « Médias du boîtier » : compléter les faces ou choisir de meilleures sources (ScreenScraper, GameTDB, MobyGames facultatif, import manuel), avec la provenance de chaque face (§ 13 à § 17).

Scraping par lot du 2 novembre 2026 : « Nouveau contenu uniquement » applique de nouveau les choix modifiés (types de médias, ordre des régions, langue), remplace les icônes de console copiées à l'import sans plus rien écraser d'autre, et le même bouton « Démarrer » complète les faces de boîtier manquantes avec GameTDB et MobyGames, ou seulement elles (§ 18).

Demande du mainteneur (19 octobre 2026) : faire de la vue Jaquette un boîtier manipulable comme un objet réel (rotation libre, inclinaison, zoom), dont on lit le dos dans les douze langues de NeoStation, et qui s'ouvre sur sa cartouche ou son disque quand on appuie sur « Jouer ». Précision du mainteneur en cours de cycle : les jaquettes doivent être réalistes, de vraies jaquettes (PlayStation 1 par exemple) et ainsi de suite pour chaque console.

Référence visuelle : la vidéo YouTube `teVZ90DnkbQ` n'a pas pu être consultée (YouTube est refusé par la politique réseau du conteneur de travail, HTTP 403 sur le tunnel ; aucune recherche ne retrouve son titre). Les mouvements, proportions et transitions suivent donc les exigences écrites et les dimensions réelles des boîtiers ; rien de la vidéo n'est vérifié.

## 1. Vues concernées et pile graphique

- **Vues concernées** (Build 493) : le carrousel en style de carte « Boîte » (`gameCarouselCardStyle == 'box'`, `my_games_carousel.dart`), la grille dans ce même style (`my_games_grid.dart`), la vue Liste (miniatures des lignes, `game_list_view.dart`, et onglet « Jaquette » du panneau de détails, `game_details_box2d_tab.dart`). Le style « Fanart » du carrousel et de la grille ne change pas (cartes plates, halo conservé).
- **Composants communs** : `GameBoxCard` (boîtier au repos, sans geste ; en grille et en liste avec la largeur de décodage de l'ancienne jaquette plate, `decodeWidth`, et une seule facette par coin arrondi), `GameBoxLibrary` (`lib/widgets/game_box/game_box_library.dart` : chemins des scans mis en cache par jeu et version des illustrations, profils, ouverture de la visionneuse, « Jouer » avec ouverture) et la même visionneuse `GameBoxInspector` pour les trois vues.
- **Pile graphique** : celle des couvertures de livres 3D de la Bibliothèque (Build 443/447) — des widgets Flutter transformés par des `Matrix4` en perspective, sans dépendance nouvelle ni moteur 3D. Chaque face est un widget (image, surface neutre ou peinture) placé par sa propre matrice ; les faces tournées vers l'arrière sont écartées et les autres peintes de la plus éloignée à la plus proche. Un boîtier fermé est convexe : l'élimination des faces arrière suffit. Ouvert, le corps, le support et le couvercle sont peints dans un ordre de calques défini par famille (le volet d'une boîte en carton passe derrière la cartouche une fois rabattu). Un moteur 3D natif (SceneKit dans une vue de plateforme) a été écarté : coût de composition des vues de plateforme Flutter sur iOS, navigation à la manette et accessibilité à refaire, et aucun test possible hors appareil, alors que le rendu `Matrix4` se teste et se photographie dans `flutter test`.
- Modules : `lib/widgets/game_box/game_box_geometry.dart` (modèle, poses, projection, ouverture), `game_box_scene.dart` (faces), `game_box_surfaces.dart` (surfaces neutres, disque, cartouche, intérieur, charnière), `game_box_card.dart` (carte du carrousel), `lib/screens/game_box/game_box_inspector.dart` (visionneuse), `box_back_reader_screen.dart` (lecture), `lib/services/game_box/` (profils, médias, éditions, lecture du texte).

## 2. Familles de boîtiers (réalisme)

`GameBoxProfile.forSystem` (`lib/services/game_box/game_box_profile.dart`) donne à chaque console sa famille, ses dimensions réelles en millimètres et son support ; une console sans entrée dédiée suit les supports déclarés dans `assets/systems/<id>.json` (`cd_rom` → boîtier cristal, `dvd` → boîtier DVD, `cartridge` → boîte en carton, `digital`/borne d'arcade → carte plate sans ouverture).

| Famille | Consoles | Taille (mm) | Ouverture | Support |
|---|---|---|---|---|
| Boîtier DVD | PS2, Xbox, Xbox 360, Wii, Wii U, GameCube (130 × 184) | 135 × 190 × 14, coins arrondis 4,5 mm | panneau avant autour de la tranche | DVD 120 mm ; GameCube : mini-disque 80 mm |
| Blu-ray | PS3 : plastique transparent (blanc translucide), 135 × 171,5 × 14 (§ 13) | 135 × 171,5 × 14 | idem | BD 120 mm |
| UMD | PSP | 104 × 180 × 13 | idem | UMD dans sa coque |
| Boîtier cristal | PS1, Saturn, Dreamcast, Mega-CD, 3DO, CD-i, PC Engine CD, Neo Geo CD, PC-FX, Jaguar CD | 142 × 125 × 10, angles vifs | couvercle transparent autour de la charnière | CD 120 mm sur plateau noir |
| Boîtier de cartes | DS, 3DS, Switch (105 × 170 × 11, plastique transparent, § 13), Vita (105 × 135) | 125 × 137 × 14 / 11, coins arrondis | panneau avant | carte dans son logement, en haut à droite |
| Boîtier plastique | Mega Drive/Genesis, 32X, Master System, Pico, PC Engine (HuCard) | 135 × 190 × 27 | panneau avant | cartouche ou HuCard |
| Boîte en carton | NES, Famicom, SNES/Super Famicom, N64, GB/GBC, GBA, Virtual Boy, Game Gear, Lynx, NGP, WonderSwan, Atari, Jaguar, Neo Geo | dimensions par console (SNES 180 × 128 × 35, N64 225 × 160 × 40…) | volet supérieur rabattu vers l'arrière | cartouche qui sort par le haut |

Détails reproduits d'après les boîtiers réels :
- **Boîtier cristal (PS1…)** : taille fixe quel que soit l'encart ; l'encart avant carré est posé à droite de la bande de charnière (8 mm), sur le plateau noir vu à travers le couvercle transparent, avec ses marges de plastique ; les deux tranches de l'encart dorsal sont visibles sur les côtés (charnière et ouverture) ; les ergots de charnière apparaissent aux deux bouts du côté charnière ; le dessus et le dessous sont en plastique transparent fumé ; ouvert, le plateau noir et son moyeu à dents tiennent le disque, le couvercle montre ses quatre ergots de livret. Un dos scanné avec ses tranches (≈ 151 × 118 mm, rapport ≥ 1,22) est recadré au milieu pour le dos, et ses bandes latérales servent de tranches réelles quand il n'existe pas de scan de tranche (la bande droite de l'encart, scannée à plat, se replie sur le côté charnière).
- **Boîtier DVD/Blu-ray/portable** : coins arrondis (quatre arcs de trois facettes), jaquette sous film transparent dans un liseré de plastique de 1,4 mm, tranche imprimée entre les plastiques des deux panneaux, stries de préhension côté ouverture, joint du film sur le dessus et le dessous ; ouvert, moyeu à dents ou logement de carte, attaches du livret à l'intérieur du panneau avant.
- **Boîte en carton** : couleur des bords échantillonnée sur le pourtour du recto réel (image réduite à 24 px), plis marqués.
- **Lumière** : un éclairage doux qui ne modifie jamais la face tournée vers le lecteur ; reflet du film limité à 8 % de blanc, coupé quand on regarde le dos ou qu'on zoome.

Rendu de contrôle : `test/game_box_render_preview_test.dart` et `test/game_box_render_inspector_preview_test.dart` écrivent des images quand `GAME_BOX_RENDER_DIR` est défini (images de démonstration générées, jamais de vraie jaquette dans le dépôt).

## 3. Vues de la bibliothèque et visionneuse

**Halo.** Le halo lumineux (`RainbowSelectionBorder`) ne correspond plus à des boîtiers en volume :
- Carrousel « Boîte » : aucun halo ; le boîtier centré se distingue par sa taille, sa profondeur et son opacité dans le carrousel (échelle et opacité de `NativeCarousel`).
- Grille « Boîte » : aucun halo ; le boîtier sélectionné est agrandi de 7 % (`AnimatedScale`, 140 ms).
- Liste : le halo est **uniquement sur le nom du jeu sélectionné**. Sa largeur suit la longueur mesurée du titre (cœur des favoris compris, bornée à la largeur de la ligne), il commence après la miniature 3D et ne l'englobe jamais, il suit la sélection (tactile, manette, défilement accéléré) et n'est pas peint quand la visionneuse, opaque, est ouverte au-dessus. Sans support de boîtiers (aucun `FileProvider` transmis), la ligne garde son ancienne surbrillance.
- Le style « Fanart » garde son halo : ce ne sont pas des jaquettes.

**Grille.** Chaque jeu qui a un recto est un boîtier 3D au repos, décodé à la largeur qu'utilisait la jaquette plate (même cache d'images) ; sans recto, la carte de remplacement habituelle. Toucher le boîtier sélectionné ou son badge 360° ouvre la visionneuse ; « Jouer » (A, pied de page) ouvre le boîtier puis lance le jeu ; clic du stick droit : visionneuse.

**Liste.** Une miniature 3D (≈ 30 pt, légèrement tournée pour montrer la tranche) précède chaque titre ; les lignes passent de 26 à 34 pt pour qu'elle reste lisible. Toucher la miniature ouvre la visionneuse du jeu (après l'avoir sélectionné) ; toucher le titre sélectionné ou A joue avec l'ouverture du boîtier ; clic du stick droit : visionneuse. L'onglet « Jaquette » du panneau de détails montre le même boîtier en volume ; le toucher ouvre la visionneuse.

**Retour à la bibliothèque.** La visionneuse est une page opaque au-dessus de la bibliothèque, qui reste montée dessous : en revenant, la vue (Carrousel, Grille ou Liste), le jeu sélectionné et la position de défilement sont ceux de départ, sans rechargement ; la sélection ne peut pas changer tant que la visionneuse est ouverte.


**Carrousel.** Chaque carte du style « Boîte » est le boîtier en volume, immobile, à la pose de repos (recto, un peu de tranche et de dessus), avec le vrai recto et, s'il existe, le vrai scan de tranche. La carte n'a pas de geste propre : glisser change toujours de jeu. Toucher le boîtier centré, son badge 360° ou ↑ à la manette ouvre la visionneuse ; « Jouer » (A, bouton du pied de page) ouvre le boîtier puis lance le jeu. Sans recto, la carte de remplacement habituelle de NeoStation est conservée.

**Visionneuse** (plein écran, au-dessus de la bibliothèque, dont la sélection ne peut pas changer) :
- glisser horizontalement : rotation libre sur 360° (le recto suit le doigt), avec une inertie qui s'arrête d'elle-même ; glisser verticalement : inclinaison bornée à ±75° pour voir le dessus et le dessous ;
- pincer : zoom ×1 à ×4 ; à un doigt quand le zoom est actif : déplacement ; double toucher : ×2,2 ou retour ;
- « Face avant », « Dos », « Position initiale » ; le dos est présenté face à la caméra avec une perspective réduite et reste immobile tant qu'on ne le touche pas ;
- **bouton Retour** toujours visible en haut à gauche (B à la manette, geste retour du système) : il remonte d'un niveau — notice → boîtier ouvert → boîtier fermé → bibliothèque — sans jamais lancer le jeu ni changer la sélection ;
- « Recentrer » apparaît dès qu'un zoom ou un déplacement est actif ; « Vue à plat », quand le dos est tourné vers la caméra, ouvre le scan du dos seul, sans la perspective du boîtier (`GameBoxScanViewer`) : la version déjà décodée s'affiche aussitôt, le scan complet (jusqu'à 4 096 px) la remplace dès qu'il est prêt ; pincer, déplacer, double toucher, « Recentrer » ; le zoom s'arrête à environ 2,5 pixels d'écran par pixel du scan, la résolution réelle est affichée et un scan de moins de 1 000 px de large est signalé comme basse résolution (rien n'est agrandi artificiellement) ;
- manette : ←/→ quart de tour, ↑/↓ inclinaison, L/R zoom, A jouer, B retour, X lire la jaquette (boîtier ouvert : lire la notice), Y avant/dos, Start langue de lecture, clic gauche position initiale (ouvert : recentrer), clic droit ouvrir/refermer la boîte, Select options ;
- portrait : commandes sous le boîtier ; paysage et iPad : colonne à droite ; les commandes passent à la ligne avec l'agrandissement du texte ; le boîtier porte une étiquette d'accessibilité (« Boîtier de …, face visible : dos »).

**Images.** La carte décode le recto à 1024 px de large (la taille que le carrousel utilisait déjà, donc le même décodage) ; la visionneuse demande 2400 px sur le plus grand côté pour le recto et le dos une fois affichée (depuis le 1er novembre 2026 : un scan Switch haut n'est plus décodé à 2400 px de large, § 16) et les libère en se fermant ; le scan du dos s'ouvre en plein écran jusqu'à 4096 px dans le mode lecture. Une image agrandie n'invente rien : si le scan est trop flou, le mode lecture textuelle le signale.

## 4. Surfaces et éléments manquants

- **Dos absent** : surface neutre (plateau ou couleur du boîtier) avec « Dos indisponible » discret ; le recto n'est jamais recopié au dos.
- **Tranche absente** : couleur du boîtier et titre connu en texte simple, jamais un faux scan.
- **Visuel du support absent** : disque argenté à étiquette vierge, ou cartouche de la forme de la console à étiquette vierge portant le titre en texte simple ; la visionneuse précise « présentation neutre, pas l'impression d'origine ».
- **Intérieur** : aucune source de visuel intérieur n'est connue (ScreenScraper n'en propose pas) : plateau, moyeu et attaches neutres.
- **Aucun média** : la carte de remplacement de NeoStation.
- Aucune absence d'image, de texte ou de traduction n'empêche le lancement.

## 5. Récupération et association des médias

Le système de scraping existant est étendu, sans toucher aux fichiers verrouillés sur la 419 (`scraper_repository.dart` n'est que lu) :
- `ScreenscraperMediaResolver.mapMediaTypeToFolder` connaît `box-2D-back` → `box2dback`, `box-2D-side` → `box2dside`, `support-2D` → `support2d` ;
- `ScreenscraperMediaDownloader.downloadValidatedMedia` réutilise la validation des octets, l'écriture atomique et la suppression des doublons d'extension du scraping ;
- `ScreenScraperService.mediaJeuUri` construit l'adresse `mediaJeu.php` d'un média d'un jeu identifié, identifiants ajoutés au moment de la requête.

`GameBoxMediaFetcher.fetch` (« Récupérer les faces du boîtier » dans la visionneuse ; depuis le 1er novembre 2026, ce bouton ouvre « Médias du boîtier », § 14, qui passe par la même identification ScreenScraper, `GameBoxMediaFetcher.list`) :
- **identification** : système ScreenScraper de la console, MD5 de la ROM quand elle est locale et ≤ 64 Mio, numéro de série connu, nom de fichier (les noms No-Intro/Redump portent la région) — jamais le seul titre affiché ;
- **région de votre jeu** : fiche ROM de ScreenScraper quand l'empreinte a correspondu, sinon les étiquettes du nom de fichier (`(USA)`, `(Europe)`, `(Japan)`, `(France)`…) ; affichée avec sa source ;
- **recto déjà présent** : jamais remplacé ; son MD5 est comparé aux rectos listés pour savoir quelle édition la bibliothèque montre ;
- **faces par défaut** : édition de votre jeu, puis celle du recto affiché, puis l'ordre des régions de l'utilisateur ;
- **manifeste** `media/<système>/boxmeta/<rom>.json` : toutes les éditions listées (type, région, langue présumée, format, MD5, SHA-1, CRC, taille, jeton `media`), la face choisie pour chaque type, la méthode d'identification. Aucun identifiant, mot de passe ni URL complète n'y est écrit ;
- **dos d'autres éditions** : téléchargés à la demande dans `media/<système>/box2dback-editions/<rom>/`, une fois par image (identité MD5/SHA-1 : un même scan listé `wor` et `us` n'est téléchargé qu'une fois) ; ensuite consultables hors ligne ;
- quota, connexion manquante, système non associé et jeu introuvable ont chacun leur message traduit.

**Scraping par lots** : l'option « Faces du boîtier (boîtier 3D) » des réglages Scraping › Médias (désactivée par défaut, `boxFaces` dans la liste enregistrée) fait télécharger, par le scraping habituel d'un jeu ou d'une bibliothèque, les trois types `box-2D-back`, `box-2D-side` et `support-2D` dans les mêmes dossiers (`ScreenscraperMediaDownloader.expandMediaTypes`), selon l'ordre des régions et la langue préférée du scraping. Comme pour les manuels, l'activer rouvre les jeux déjà complets pour que le mode « nouveaux seulement » puisse compléter ces médias. Ce chemin n'écrit pas de manifeste : la région de chaque face et les autres éditions apparaissent après « Récupérer les faces du boîtier ». Les nouvelles faces sont rechargées après un scraping d'un seul jeu (`scrapedArtworkTypes`).

Suppression des médias d'un jeu (`GameRepository.deleteNeoStationScrapedMedia`) : les trois nouveaux dossiers, le manifeste et le dossier des éditions sont supprimés avec les autres médias.

## 6. Éditions et langue des scans

ScreenScraper étiquette les scans par région, pas par langue. La langue d'un scan est donc **présumée** de sa région (`GameBoxRegions.languageOfRegion` : `jp` → japonais, `fr` → français, `de` → allemand, `sp` → espagnol, `it` → italien, `pt`/`br` → portugais, `kr` → coréen, `cn` → chinois simplifié, `tw` → chinois traditionnel, `ru` → russe, `us`/`eu`/`wor`/`uk`/`au`/`ca` → anglais, les régions européennes et mondiales étant notées multilingues), puis confirmée par la reconnaissance du texte, qui affiche la langue détectée.

Quand on choisit une langue de lecture, la visionneuse cherche un dos publié pour cette langue ; s'il existe, il est affiché (téléchargé une fois) avec « Scan publié en … » et, si ce n'est pas l'édition de votre jeu, « Édition … : ce n'est pas l'édition de votre jeu (…) ». Sinon, le dos de votre édition reste affiché et la lecture traduite est proposée. La langue de lecture est un réglage propre (`NeoStation.GameBox.ReadingLanguage`, « Langue de NeoStation » par défaut) qui ne change ni la langue de l'application, ni l'identification du jeu, ni ses fichiers, ni son lancement.

## 7. Lecture du dos dans les douze langues

Langues : celles de `AppLocale.supportedLanguages` — `en`, `es`, `ru`, `zh`, `zh_Hant`, `pt`, `fr`, `de`, `it`, `id`, `ja`, `ko`.

**Solution retenue : entièrement sur l'appareil, frameworks d'Apple, plugin `packages/neo_box_reader` (Swift, iOS 18, lié statiquement).**
- **Transcription** : aucune source de médias utilisée ne publie le texte des dos ; la seule transcription réutilisée est celle déjà extraite de la même image (empreinte SHA-256). Sinon, reconnaissance Vision `VNRecognizeTextRequest` (niveau précis, correction linguistique), avec les langues de l'édition comme indices (`ja-JP` d'abord pour un scan japonais) et la détection automatique de Vision quand il n'y a pas d'indice ou que la passe indicée ne trouve presque rien ; la langue dominante vient de NaturalLanguage (`NLLanguageRecognizer`).
- **Mise en forme** (`lib/services/game_box/box_text_layout.dart`, Dart pur) : colonnes séparées par leur étendue horizontale, sections par les écarts de lignes et les changements de taille, titres, listes à puces, petites mentions légales ; lecture colonne par colonne ; mots coupés recollés, lignes chinoises/japonaises/coréennes jointes sans espace. Les lignes que Vision ne lit qu'avec une confiance < 0,15 sont comptées comme illisibles et **jamais reconstituées** ; les sections contenant des lignes < 0,5 sont signalées.
- **Traduction** : framework Translation d'Apple (`TranslationSession`, iOS 18), sur l'appareil ; une session n'étant fournie qu'à une vue SwiftUI (`.translationTask`), le plugin attache pour la durée de la requête un contrôleur d'hébergement invisible d'un point, ce qui permet aussi à iOS de proposer lui-même le téléchargement d'une langue manquante. `LanguageAvailability` est interrogée avant (paire non prise en charge) et après (langue non installée, téléchargement refusé). Chaque section et chaque élément de liste est traduit séparément, l'ordre est conservé.
- **Couverture** : les douze langues font partie des langues de Translation d'Apple (anglais, espagnol, russe, chinois simplifié et traditionnel, portugais du Brésil, français, allemand, italien, indonésien, japonais, coréen) ; Vision reconnaît anglais, français, italien, allemand, espagnol, portugais, chinois simplifié et traditionnel, cantonais, coréen, japonais, russe et ukrainien, entre autres. **L'indonésien n'a pas de modèle de reconnaissance dédié sur macOS 15.7** ; iOS 26.2 (Simulateur, run `39345297065`) en déclare un (`id-ID`). NeoStation ne passe pas l'indonésien comme indice : un dos imprimé en indonésien (cas très rare) est lu par la reconnaissance latine générale, ce qui a donné le texte exact dans les deux environnements. La couverture effective est relevée par le contrôle natif (§ 9) : liste des langues de reconnaissance de l'OS, reconnaissance réelle d'un texte dans chacune des douze langues sur macOS et dans le Simulateur iOS, et état de `LanguageAvailability` pour les douze langues cibles.
- **Cache** : `Application Support/NeoStation/BoxText/<SHA-256 du scan>/transcript.json` et `<langue>.json`, réutilisés pour toute lecture ultérieure, hors ligne comprise ; un autre scan ne réutilise jamais le texte d'un autre.
- **Écran de lecture** : sections nettes, taille du texte de 80 à 240 % (mémorisée), bascule « Traduction / Texte d'origine », mentions « Texte reconnu automatiquement sur le scan : des erreurs sont possibles », « Traduction automatique (langue d'origine : …), réalisée sur l'appareil », « Scan publié en … » ou « Édition … », lignes peu lisibles et parties illisibles, conservation hors ligne ; le résumé de la fiche du jeu est dans une section repliée à part (« métadonnées, pas le texte du boîtier ») ; le scan s'ouvre en plein écran. États de chargement (lecture, traduction) et d'erreur traduits, avec « Réessayer ».

## 8. Ouverture et lancement

« Jouer » (visionneuse, ou A / pied de page dans la vue Jaquette) :
1. alignement sur la pose d'ouverture (recto, un peu de charnière ; vue de dessus pour une boîte en carton) ;
2. ouverture : panneau ou couvercle de 150° autour de la charnière, ou volet rabattu de 112° vers l'arrière ; le cadrage suit le contour réel du boîtier ouvert, perspective comprise ;
3. support : un disque reste dans son logement (illustration d'origine si elle existe) ; une cartouche sort de 62 % de sa hauteur par le haut de la boîte ; une carte ou une cartouche de boîtier plastique se soulève vers le lecteur ;
4. transition finale : zoom sur le support et fondu au noir ;
5. le jeu est confié au lancement habituel de la bibliothèque (`_selectCurrentGame` → `launchGameWithDialog`), qui garde toutes ses vérifications et leurs dialogues (fichier présent, BIOS, état du moteur, JIT, appairage) ; ces dialogues s'affichent avant la présentation du jeu par le moteur. La visionneuse se retire dès que la session de lancement a commencé, sous le dialogue de lancement, et libère ses grandes images avant le démarrage de l'émulation (le délai de présentation de 2 s du dialogue reste inchangé).

Garanties :
- un seul lancement : verrou `GameBoxLaunchGate` partagé par le carrousel et la visionneuse, phase de la visionneuse, puis le garde `_isGameLaunching` existant ;
- si aucune session ne démarre dans les 6 s (lancement refusé par la bibliothèque), le boîtier se referme et la visionneuse revient à l'inspection ; un échec du lancement passe par le traitement d'erreur existant de la bibliothèque, qui recharge la vue ;
- durée ≈ 1,75 s ; « Animation d'ouverture du boîtier » (options de la visionneuse, `NeoStation.GameBox.OpeningAnimation`, activée par défaut) la supprime ; avec « Réduire les animations », le boîtier ouvert apparaît sans mouvement puis l'écran s'efface (≈ 0,5 s) ;
- un rendu qui échoue ou une animation bloquée n'empêche jamais le jeu : délai maximal de 4 s, puis lancement.

## 9. Vérifications

- Flutter (`flutter test`, Linux) : `test/game_box_geometry_test.dart` (17 : faces visibles sur un tour complet, dos et tranche non inversés, inclinaison, cadrage constant en rotation, coins arrondis, ouverture par famille, cadrage du boîtier ouvert dans l'écran pour huit consoles, profils), `test/game_box_media_test.dart` (13 : régions des noms de fichiers, manifeste sans identifiants, éditions dédoublonnées, choix des faces, dos par langue, option de scraping, magasin), `test/game_box_text_test.dart` (8 : colonnes, titres, listes, mentions légales, recollage, illisible, cache de la transcription et de chaque traduction, scan différent, codes d'erreur), `test/game_box_inspector_test.dart` (7 : avant/dos/position initiale, rotation libre et arrêt, lancement unique puis retrait sous le dialogue, lancement qui ne démarre pas, réduction des animations, animation désactivée, scan corrompu), `test/game_box_locale_test.dart` (16 : douze langues, paramètres, chinois traditionnel ; 106 textes), et les suites existantes qui lisent un fichier modifié.
- Python : `tools/game_box/generate_strings.py --check`, `test/game_box_strings_test.py`, `test/localization_12_locale_coverage_test.py`, `test/retroarch_baseline_scope_test.py` (fichiers de bibliothèque 419 intacts).
- Natif (`.github/workflows/game-box-checks.yml`, partie `native`) : le code de reconnaissance du plugin compilé et exécuté sur macOS puis dans le Simulateur iOS (texte rendu dans chacune des douze langues, similarité mesurée, langue détectée), disponibilité Translation des douze langues cibles (exigée sur macOS, relevée dans le Simulateur), vérification de type des sources Swift du plugin contre le SDK iPhone et Flutter.

- Build 493 (Flutter, Linux) : `test/game_box_booklet_test.dart` (9 : aucune notice sans PDF ni boîtier fermé, dimensions et proportions dans neuf familles, couverture lisible et touchable, partie cachée par une boîte en carton non touchable, disque sur le plateau et notice dans le panneau, ordre de peinture, notice prise face à la caméra centrée à 2 % près sans bouger le cadrage, interpolation d'orientation), `test/game_box_manual_inspector_test.dart` (12 : Retour en haut à gauche sans reconstruction ni changement de sélection, ouvrir/refermer puis quitter niveau par niveau, notice lue dans le lecteur sur le même fichier et retour au boîtier ouvert au même angle, toucher sur la notice, aucune notice ni téléchargement à l'ouverture puis téléchargement qui la fait apparaître, aucun téléchargement sans système, geste retour du système, « Jouer » depuis la boîte ouverte une seule fois, « Réduire les animations », vue à plat et résolution, lecteur par défaut, chemin du service = chemin de l'onglet), `test/game_box_library_views_test.dart` (7 : halo de la Liste seulement sur le titre, à droite de la miniature, proportionné et suivant la sélection, toucher une miniature ouvre la visionneuse sans lancer, ancienne surbrillance sans boîtiers ; Grille « Boîte » sans halo avec la sélection agrandie, toucher le boîtier sélectionné ouvre la visionneuse puis Retour revient à la grille, « Fanart » garde son halo). Aperçus de contrôle : `test/game_box_render_open_preview_test.dart` (boîtiers ouverts, prise de la notice, retour, Liste), avec `GAME_BOX_RENDER_DIR` et `ROBOTO`.

- Build 494 (Flutter, Linux) : `test/game_box_sharp_scan_test.dart` (7 : aplat conservé à tous les rapports, noyau de Mitchell-Netravali, couleurs prémultipliées jamais au-dessus de leur alpha, largeur arrondie et jamais supérieure au scan, grain sous le seuil intact et accentuation sans franges colorées, petits caractères comparés au texte dessiné à la bonne taille et au modèle trilinéaire à 896, 640 et 1 280 px, durée bornée sur un dos de 2 400 × 3 400), `test/game_box_sharp_back_test.dart` (10 : rendu demandé seulement dos de face et immobile, à la largeur mesurée à l'écran, utilisé par la face ; plus large pour un zoom sans dépasser le scan ; « Texte net » désactivé et mémorisé ; masqué de face, libéré à la fermeture ; en portrait sur 375 × 667, 390 × 844 et 400 × 600, zone du boîtier ≥ 54 % de la hauteur, dos ≥ 68 % de la largeur, « Face arrière » et « Jouer » visibles — ces trois cas échouent quand la limite du panneau est retirée ; options sans débordement en paysage ; vue à plat suivant l'ajustement et le zoom, bouton « Texte net »), `test/game_box_text_test.dart` (+1 : une transcription de version 1 est relue une fois et sa traduction refaite). Natif (macOS, Simulateur iOS) : petits caractères, recognizer de la Build 493 contre le nouveau (`test/native/game_box_small_print/main.swift`).

Lanceur : `python3 test/game_box_targeted_test.py --part host|native` (verdicts `build/gamebox/<partie>-verdict.json` avec l'empreinte de chaque entrée) ; Build 493 : `python3 test/build493_targeted_test.py --part host` ; Build 494 : `python3 test/build494_targeted_test.py --part host|native`.

## 10. Limites

- Build 493 : aucune validation sur iPhone ni iPad (fluidité de la grille et de la liste à 120 Hz, mémoire avec beaucoup de boîtiers, gestes dans la boîte ouverte, lecteur PDF depuis la boîte) ; les tests remplacent le moteur PDF par une page générée et le lecteur par une page de test (le lecteur réel est celui de Réglages du jeu › Notice, inchangé). Le rendu de la première page par pdfrx n'est pas exécuté en CI.
- La notice n'a qu'une édition par jeu (celle du système de médias) ; la langue du PDF n'est pas détectée.
- L'intérieur des boîtiers reste une présentation neutre (aucune source de scan d'intérieur).

- Aucune validation sur iPhone ni iPad : fluidité, mémoire, rendu des scans réels, gestes et lecture restent à essayer sur l'appareil.
- La traduction ne s'exécute pas en CI : le Simulateur ne télécharge pas de modèles de traduction ; seules la disponibilité des langues et la reconnaissance sont exercées. La première traduction vers une langue demande à iOS de télécharger cette langue (proposé par iOS, une fois).
- La qualité de la lecture dépend du scan : un dos basse résolution ou très stylisé donne des lignes peu lisibles, signalées, jamais complétées.
- La langue d'un scan est présumée de sa région ScreenScraper ; les éditions européennes multilingues sont présentées comme anglaises tant que la reconnaissance n'a pas détecté autre chose.
- `box-texture` (gabarit déplié de ScreenScraper) n'est retenu que si ses proportions correspondent à un agencement vérifié (dos | tranche | recto des gabarits GameTDB PS3 et Switch, § 14) ; sinon il est refusé et mémorisé comme tel. Aucun exemple ScreenScraper n'a pu être consulté depuis le conteneur (API sans identifiants).
- Le scraping par lots (option « Faces du boîtier ») choisit les faces selon l'ordre des régions, sans manifeste des éditions ; la récupération depuis la visionneuse choisit l'édition de votre jeu et liste toutes les éditions.
- Le cache du texte des dos (`Application Support/NeoStation/BoxText`) n'a pas de rubrique dédiée dans l'analyse du stockage ; il est régénérable et n'est jamais supprimé automatiquement.

## 11. Ouvrir la boîte et la notice (Build 493)

**« Ouvrir la boîte »** (visionneuse ; clic du stick droit) est distinct de « Jouer » : le boîtier s'aligne sur la pose d'ouverture et s'ouvre (0,95 s), sans rien lancer. Dans un boîtier plastique (DVD, Blu-ray, UMD, cristal, cartes, Mega Drive), le disque reste sur son moyeu et la carte ou la cartouche dans son logement ; dans une boîte en carton, la cartouche sort par le haut et la notice dépasse derrière elle, pour que les deux se voient. On peut zoomer, déplacer et regarder un peu autour (lacet de −0,5 à +0,45 rad autour de la pose, inclinaison −0,12 à 0,9) ; le boîtier ouvert ne tourne jamais jusqu'à son dos. « Refermer la boîte », B ou Retour le referment et le remettent dans sa pose d'avant. « Jouer » depuis la boîte ouverte garde l'angle et ne fait plus que sortir le support avant la transition habituelle.

**La notice dans le boîtier.** Elle n'existe que si le PDF est sur l'appareil : aucun livret n'est dessiné sans document (`GameBoxModel.booklet` nul). C'est le même fichier que Réglages du jeu › Notice : `GameModel.getManualPath` résolu par le `FileProvider` (`media/<système>/manuals/<jeu>.pdf`), par le service commun `GameManualService`, que l'onglet Notice utilise désormais aussi ; rien n'est copié ni mis en cache à côté.
- Placement : boîtier à charnière (DVD, Blu-ray, UMD, cartes, Mega Drive) — à l'intérieur du panneau avant, couverture vers le lecteur une fois le panneau ouvert, lisible à l'endroit, entre les attaches ; boîtier cristal — dans le couvercle, sous l'emplacement de l'encart avant, à droite de la charnière ; boîte en carton — debout derrière la cartouche, sortie par l'ouverture jusqu'à dépasser de 14 mm la cartouche levée. Tant que le panneau n'est pas tourné vers le lecteur, la notice est peinte sous lui.
- Format : un livret mince (1,2 à 2 mm), aux proportions de la première page du PDF quand elle est lue (sinon : carré pour un CD, portrait pour un DVD), ajusté à l'intérieur du boîtier ; tranche agrafée, bords des pages, dos papier.
- Couverture : la première page du PDF, dessinée par `pdfrx` à 720 px sur son grand côté **seulement à l'ouverture de la boîte** (jamais pendant le défilement de la bibliothèque), puis le document est refermé ; l'image est libérée à la fermeture de la visionneuse et avant le lancement d'un jeu. Tant qu'elle n'est pas lue (ou si le PDF ne se lit pas), le livret est du papier uni portant le titre du jeu : il représente le document présent, jamais une fausse couverture.
- Prendre la notice : un toucher sur sa partie visible (un toucher sur la face avant d'une boîte en carton qui la cache ne compte pas), son étiquette « Lire la notice », le bouton du panneau ou X. Elle se soulève de ses attaches (160 ms), vient face à la caméra, centrée et remplissant environ 82 % de la vue (420 ms, cadrage du boîtier inchangé), puis le **lecteur de notices de NeoStation** (`GameManualReaderScreen`, pdfrx : plein écran, pincement, pages, hors ligne, Retour et manette) s'ouvre sur le même fichier. Pendant la lecture, la scène 3D n'est pas dessinée et ses grandes images sont libérées. À la fermeture du lecteur, la notice retourne à sa place et l'on retrouve le même boîtier, toujours ouvert, au même angle.
- Sans notice : « Aucune notice de ce jeu sur l'appareil. » et, si la bibliothèque est connue et le jeu a un chemin de ROM, « Télécharger la notice » (aussi dans les options du boîtier) — l'appel ScreenScraper de Réglages du jeu › Notice (identifiants, langue préférée, régions, quota, messages). Jamais automatique : ouvrir la boîte ne télécharge rien. Un téléchargement réussi fait apparaître la notice dans la boîte ouverte aussitôt, sans redémarrage. Les faces du boîtier (« Récupérer les faces du boîtier ») et la notice restent deux téléchargements distincts.
- Langue : la notice est le PDF dans sa langue réelle (« dans sa langue d'origine »), jamais présentée comme traduite. Le système de médias ne garde qu'une notice par jeu (choisie au téléchargement selon la langue préférée et les régions du scraping) : aucune autre édition linguistique n'est identifiée ni proposée.
- Libellés : 18 textes ajoutés (Retour, ouvrir/refermer la boîte, notice, téléchargement, vue à plat, recentrer, résolution du scan, intérieur neutre…) dans les douze langues (`tools/game_box/strings.json`, 123 textes) ; en anglais, les faces deviennent « Front cover » / « Back cover » pour ne pas se confondre avec « Back » (Retour), en français la face arrière est « Face arrière ».

## 12. Netteté et lisibilité du dos (Build 494)

Demande du mainteneur (20 octobre 2026) : « améliore si tu peux encore la netteté et la lisibilité des textes à l'arrière des boîtes ». Les scans des dos sont téléchargés en résolution d'origine (aucun `maxwidth` dans les adresses `mediaJeu.php`) : la perte ne vient pas de là. Trois causes ont été établies dans les sources et mesurées.

**1. Le dos était dessiné trop petit en portrait.** Le panneau du bas prenait sa hauteur naturelle et le boîtier le reste. Mesuré dans la visionneuse (tests Flutter, tailles logiques, boîtier PS2 tourné sur son dos) :

| Écran | Zone du boîtier, Build 493 | Largeur du dos, 493 | Zone, Build 494 | Largeur du dos, 494 |
|---|---|---|---|---|
| iPhone SE 375 × 667 | 39 px (0 px une fois tourné) | invisible | 375 px | 322 pt |
| iPhone 14 390 × 844 | 272 px | 234 pt | 488 px | 335 pt (+43 %) |
| 430 × 932 | 360 px | 309 pt | 545 px | 369 pt (+19 %) |
| paysage 844 × 390 | 338 px | 290 pt | inchangé | 290 pt |

En portrait, le panneau ne prend plus que 36 % de la hauteur (`GameBoxInspectorState.portraitPanelShare`) : titre et éventuelle progression en haut, puis les boutons (Avant, Arrière, Position initiale, Vue à plat, langue…) et les notes d'édition qui défilent dessous, « Jouer » toujours affiché en bas. Le paysage ne change pas. Les options du boîtier défilent quand elles dépassent la feuille (paysage).

**2. Le GPU réduisait un grand décodage en mêlant deux de ses copies réduites de moitié** (filtrage trilinéaire de `FilterQuality.medium`), ce qui adoucit les petits caractères : le dos était décodé à 2 400 px de large puis affiché à 600–1 300 px. Désormais, quand le dos est lu de face et que le boîtier est immobile, `GameBoxSharpScan` (`lib/services/game_box/game_box_sharp_scan.dart`) refait le scan **à la largeur exacte qu'il couvre à l'écran** (pixels physiques, arrondie au multiple de 64 supérieur), dans un isolat, et la face le dessine pixel pour pixel.
- Filtre choisi par mesure (`test/game_box_sharp_scan_test.dart`) : un paragraphe de petits caractères (Roboto) rendu à la résolution du décodage puis réduit, comparé au même texte dessiné directement à la taille d'arrivée (référence). Résultats (PSNR en dB vers la référence ; netteté = gradient moyen, référence entre parenthèses) :

| Largeur affichée | Trilinéaire (modèle du GPU) | Aire exacte | **Mitchell-Netravali** | Catmull-Rom / Lanczos-2 | Lanczos-3 | Mitchell + accentuation 0,3 |
|---|---|---|---|---|---|---|
| 896 px (3,85) | 33,42 dB / 3,18 | 34,18 / 4,19 | **33,90 / 3,75** | 33,59 / 4,42 | 32,61 / 5,01 | 33,14 / 4,60 |
| 640 px (3,34) | 30,82 / 3,16 | 30,72 / 4,41 | **31,72 / 3,54** | 31,01 / 4,33 | 30,35 / 4,91 | 30,88 / 4,39 |
| 1 280 px (3,87) | 29,48 / 3,19 | 29,55 / 3,65 | **29,77 / 3,53** | 29,29 / 4,02 | 28,83 / 4,47 | 29,09 / 4,24 |

  Le filtrage du GPU est 5 à 18 % moins net que le texte dessiné à la bonne taille ; Lanczos et Catmull-Rom sont plus « nets » que lui mais s'en éloignent (dépassements autour des traits) ; l'aire exacte, la plus fidèle à 896 px, l'est moins que le GPU à 640 px. **Mitchell-Netravali (B = C = 1/3)** est plus fidèle que le GPU aux trois largeurs (+0,3 à +0,9 dB) et aussi net que le texte de référence (−9 à +6 %) : c'est le rééchantillonnage retenu. Le modèle du GPU (pyramide 2 × 2, interpolation linéaire entre deux niveaux) n'est pas une mesure sur la puce de l'iPhone.
- « Texte net » (activé par défaut ; options du boîtier, bouton de la vue à plat, X à la manette ; préférence `NeoStation.GameBox.SharpText`) ajoute une accentuation légère de la **luminosité seule** (masque flou σ = 0,9, force 0,3) : même correction sur les trois couleurs (pas de franges colorées), différences de luminosité sous 3/255 laissées intactes (grain et bruit JPEG du scan). Mesuré : +20 à +24 % de netteté par rapport au rééchantillonnage seul, fidélité à 0,4 dB près de celle du GPU. Désactivé : le scan est seulement rééchantillonné. Rien n'est ajouté ni inventé.
- Jamais agrandi : affiché plus grand que lui, le scan est utilisé à sa propre taille (la vue à plat garde sa limite de zoom de ≈ 2,5 pixels d'écran par pixel du scan).
- Quand : boîtier fermé, dos vers le lecteur, aucune animation ni geste en cours ; un nouveau rendu seulement si la largeur voulue change de plus de 12 % (ou 64 px), la fois précédente restant affichée jusqu'à l'image suivante ; un résultat tardif d'une demande dépassée est jeté. Pendant une rotation, la face garde le dernier rendu tant que le dos est vu, et le décodage habituel sinon. Libéré à la fermeture de la visionneuse, avant un lancement, pendant la lecture de la notice, et au changement de scan (édition, récupération des faces). Mesure de l'opération sur l'hôte Linux : 2 400 × 3 400 → 896 × 1 269 avec accentuation en ≈ 0,74 s (pas une mesure iPhone).
- Vue à plat (`GameBoxScanViewer`, aussi ouverte depuis la lecture du dos) : même rendu pour la taille ajustée, puis pour chaque zoom à la fin du geste ; pendant un zoom, le rendu devenu trop petit est masqué et le décodage complet reste dessous jusqu'au suivant.
- Largeur visée : celle de la face la plus large de la surface « dos » à l'écran (ses facettes d'angle partagent la surface) ; pour un boîtier cristal dont le scan inclut les tranches, rapportée au scan entier.

**3. La lecture du dos et les plus petits caractères.** Vision a une hauteur de texte minimale par défaut (`minimumTextHeight`, 1/32 de la hauteur de l'image). Mesuré en CI (run `39378255052`), ce n'est pas un seuil strict : le code de la Build 493 lit déjà le corps, la liste et l'encart des dos synthétiques à toutes les tailles, et les mentions légales de 11 et 22 px ; seules les mentions de 6,6 px d'un scan de 600 px lui échappent sur macOS 15.7 (rien de lu), alors que le Simulateur iOS 26.2 les lit (0,977 et 0,988). Une première version du plugin cherchait les lignes jusqu'à 6 px et agrandissait les petits scans pour une lecture unique : elle lisait ces mentions sur macOS (0,795 et 0,907) mais lisait moins bien d'autres lignes (mentions de 11 px sur macOS : 0,977 → 0,750 ; dernière ligne d'une liste perdue dans le Simulateur : 1,000 → 0,902) et a été refusée par le contrôle. Le plugin (`BoxTextRecognizer.swift`) lit désormais le scan exactement comme la Build 493 (mêmes indices de langue, même repli sur la détection automatique), puis fait une seconde lecture : lignes jusqu'à 6 px de l'image lue, scan dont le grand côté fait moins de 1 800 px agrandi (interpolation de haute qualité, deux fois au plus, vers 2 400 px) pour Vision seulement, copie ni affichée ni conservée. De cette seconde lecture, seules les lignes situées là où la première n'a rien trouvé (aucune ligne de la première ne partage plus de la moitié de leur cadre) sont ajoutées : une ligne lue par la Build 493 n'est jamais remplacée ni retirée. Le gain dépend donc de ce que Vision manque sur l'appareil ; il est nul quand la Build 493 lisait déjà tout. Coût : une seconde reconnaissance, une seule fois par scan (le résultat est mis en cache). Les transcriptions déjà en cache (version 1) sont relues une fois (version 2) et leurs traductions refaites. Vérification : `test/build494_targeted_test.py --part native` lit des dos synthétiques (titre, corps, liste, encart clair, mentions légales ; 2 000, 1 000 et 600 px de large, JPEG) avec le code de la Build 493 (contrôle) puis le nouveau, sur macOS et dans le Simulateur iOS — résultats dans [`build494-plan.md`](build494-plan.md) § 3.

Limites : aucune validation sur iPhone (netteté perçue, temps du rendu et de la reconnaissance sur la puce, chaleur) ; un scan flou ou de faible résolution reste limité par lui-même (le rééchantillonnage ne crée pas de détail) ; le dos dessiné pendant une rotation reste celui du GPU ; la reconnaissance plus fine prend plus de temps la première fois (résultat ensuite en cache).


## 13. Boîtiers physiques et images sans déformation (1er novembre 2026)

Constats de la vidéo du mainteneur (enregistrement 1564 × 720, 59 i/s, analysé image par image) et causes confirmées dans les sources :

| Cas filmé | Constat mesuré | Cause confirmée |
|---|---|---|
| Bladestorm (PS3), 16–18 s | boîte horizontale (contour 1,25 au repos) | le recto est `ICON0.PNG` (icône XMB 320 × 176) copiée dans `media/ps3/box2d` par `Rpcs3LibraryService._writeArtwork` quand aucun recto n'existe ; `GameBoxProfile.withFrontAspect` donnait au boîtier le rapport de l'image (1,82 → 208,8 × 114,7 mm) |
| Call of Duty Black Ops II (PS3), 19 s | même défaut | même chemin (icône XMB) |
| Hogwarts Legacy (Switch), 3–6 s | boîte presque carrée (0,89 contre 0,58–0,62 pour Mario), coque rouge opaque, emblème doré sans titre | le recto est l'icône carrée du jeu copiée par l'import MeloNX (`MelonxEmbeddedLibraryService`, `switch/box2d/<rom>.jpg`) ; rapport 1 → 133,6 × 133,6 mm ; le vrai recto Switch (château, PEGI 12, GameTDB `AR3XA`) n'a jamais été récupéré : la récupération des faces ne remplaçait jamais un recto existant |
| God of War III (PS3), 21–24 s | boîte à 0,72 (rapport du scan, pas du boîtier) | même `withFrontAspect` |

Ce qui ne peut pas être établi depuis le conteneur : le fichier exact sur l'iPhone. Les identifications ci-dessus reposent sur les chemins de copie du code, les rapports mesurés et l'aspect des images filmées.

**Dimensions.** Trois tailles sont désormais séparées : le boîtier physique (`width × height × depth`), la zone imprimée (`printedAspect` : la face moins `printInset`), et les pixels de l'image. Un boîtier rigide (DVD, Blu-ray, cartes, UMD, Mega Drive) garde sa taille quelle que soit l'image ; seules les boîtes en carton et les cartes plates suivent leur image, et le boîtier cristal ne change que pour un encart haut (règle inchangée). Références : boîtier Switch 170 × 104 × 10 mm, transparent (Wikipedia, *Keep case*) ; 105 × 168 × 10 mm chez un fournisseur (duplication.com, SWITCH-CL-3) ; le gabarit de jaquette complète GameTDB donne une tranche de 122 px pour 1888 px de haut (≈ 11 mm sur 170) : le profil garde 105 × 170 × 11. Boîtier PS3 : « blanc translucide » (Wikipedia), boîtier Blu-ray 171,5 × 135 × 13 mm (Wikipedia), boîtier PS3 transparent 133 × 167 mm, tranche 14 mm (duplication.com, PS3-CL-3) : le profil passe de 135 × 170 × 12 à 135 × 171,5 × 14.

**Matières.** `GameBoxCaseMaterial.clear` pour PS3 et Switch : la jaquette est vue jusqu'au bord à travers le plastique (liseré clair de 1,4 mm, reflet ≤ 8 %), les chants sont du plastique clair. Le rouge Switch et le noir de la tranche PS3 appartiennent à l'impression (`insertColor`), pas au plastique : une tranche sans scan est dessinée dans ce ton avec le titre en texte simple (jamais de logo imité). Une coque colorée n'est appliquée que pour une édition identifiée par une source qui la liste pour ce code produit (`case color` de GameTDB, ex. `BLUS30902` rouge), enregistrée dans le manifeste (`identifiedCase`) ; jamais devinée. Wikipedia signale des Greatest Hits PS3 rouges en Amérique : ils ne sont appliqués que s'ils sont identifiés ainsi.

**Placement des images** (`GameBoxArtFit`) : un scan dont les proportions diffèrent de la zone imprimée de moins de 3 % la remplit ; au-delà, jusqu'à 3 % de marges de scan sont rognées ; le reste est centré avec des bandes neutres (couleur du bord de l'image, assombrie). L'anisotropie ne dépasse jamais 3 % : titres, logos, personnages et logos d'âge gardent leurs proportions. Exemple : recto PS3 GameTDB 928 × 1080 sur la zone PS3 (0,784) → 3 % rognés en largeur, bandes de 1,6 % en haut et en bas.

**Nature des images** (`GameBoxArtClassifier`, provenance d'abord, puis taille et transparence) :

| Nature | Reconnue par | Dessin |
|---|---|---|
| scan à plat (recto, verso) | provenance `box-2D`, `cover*`, `back*`, ou proportions proches de la zone imprimée | posé sans déformation |
| jaquette dépliée | `coverfull*`, `box-texture` ; ou image aux proportions d'un gabarit vérifié | découpée en fenêtres dos / tranche / recto à l'affichage (aucun réencodage) |
| boîte déjà en 3D | `box-3D`, GameTDB `box` ; ou moins de 90 % de pixels opaques | jamais en texture : couverture neutre |
| visuel de catalogue (icône, logo, fond) | `ICON0` 320 × 176, image carrée ≤ 512 px ou sur boîtier portrait, rapport à plus de 25 % de la zone imprimée | couverture neutre : l'image entière en petit et le titre ; la visionneuse le dit et propose la recherche |

Gabarits dépliés vérifiés sur des téléchargements GameTDB du 1er novembre 2026 : Switch 2454 × 1888 = 1166 + 122 + 1166, PS3 2000 × 1080 = 928 + 144 + 928, dos | tranche | recto (tolérance 2,5 %).

## 14. Rotation continue et « Médias du boîtier »

**Saut pendant la rotation (cause confirmée et mesurée).** `_shownPose` abaissait la perspective à 0,35 dès que le lacet dépassait 90° ou 270° (`_facingBack`) et que le zoom était ≤ 1,05 ; la pose « Dos » animait en plus la perspective vers 0,15 et tout glissement la remettait à 1. Mesures sur la vidéo : God of War III, au passage à 90° (21,525 → 21,542 s) la hauteur projetée perd 23 px (−4 %) et le bord haut descend de 16 px en une image ; au retour du zoom sous 1,05 (24,32 → 24,34 s), −16 px de hauteur et −13 px de centre ; Mario, −23 px à l'aller et +45 px (+8 %) au retour à 270°. Le zoom de 22,85 à 23,2 s est un pincement volontaire, distinct du saut.

Correction : la pose dessinée est la pose elle-même (`shownPose`). La perspective plus plate de la lecture du dos appartient à la pose « Dos » et n'est atteinte que par son animation ; un glissement la quitte progressivement (`turningPerspective`, interpolation lissée sur 90° de rotation) ; le zoom ne change plus la perspective ; le reflet s'efface continûment avec le zoom. En portrait, le panneau garde une hauteur fixe (36 %) : l'apparition de « Vue à plat » ou « Recentrer » ne change plus la taille de la zone du boîtier. Le centre de rotation reste le centre de la zone (cadrage `rotationSafeFit` inchangé).

**Zoom au point de pincement.** Le pincement agrandissait autour du centre de la zone, quelle que soit la position des doigts : pincer sur le texte de gauche d'un dos le faisait sortir du cadre. C'est l'explication la plus probable de la capture du dos Game Boy Color (non reçue dans cette session : seule la vidéo est arrivée), reproduite au banc avec un dos de test (rendu « avant » : début des lignes coupé). Le zoom suit désormais les doigts (`focalPan`), le double toucher zoome là où il a lieu ; la vue à plat (InteractiveViewer) le faisait déjà. Aucun état de zoom n'est restauré à l'ouverture de la vue à plat (matrice identité : scan entier, centré).

**« Médias du boîtier »** (bouton ScreenScraper « Récupérer les faces du boîtier » de la visionneuse, `GameBoxMediaSheet`) : état et provenance de chaque face (recto, dos, tranche, support), « Compléter les faces manquantes », « Choisir un scan » par face (tous les candidats de toutes les sources), « Importer… », recherche The Cover Project, clé MobyGames, bilan (ajoutées, remplacées, toujours manquantes, refusées) et état de chaque source. Comptes, réglages et associations existants sont inchangés.

Sources (`lib/services/game_box/game_box_sources.dart`, `game_box_media_service.dart`) :
- **ScreenScraper** (principale) : identification inchangée (MD5 de la ROM ≤ 64 Mio, numéro de série, nom de fichier ; jamais le titre seul) ; types `box-2D`, `box-2D-back`, `box-2D-side`, `support-2D` et `box-texture` (retenu seulement si son agencement est reconnu). `maxwidth` et `maxheight` (paramètres de sortie de `mediaJeu.php`) ne sont envoyés par aucun chemin de RewindBox ; ils sont en outre retirés des adresses de faces (`ScreenScraperBoxSource.fullSize`), y compris pour les dos d'autres éditions.
- **GameTDB** (PS3, Switch) : PS3 par l'identifiant de titre RPCS3 (= numéro de série = identifiant GameTDB, ex. `BCES00510`) ; Switch par titre exact dans `switchtdb.txt` (liste « ID = Titre », 0,8 Mo, gardée 30 jours ; la base Switch ne contient pas l'identifiant de programme `0100…`), présentée comme correspondance par titre. Une requête de la fiche du jeu donne les illustrations disponibles (`https://art.gametdb.com/<ps3|switch>/<type>/<langue>/<ID>.jpg`) : `coverHQ/coverM/cover`, `backHQ/…`, `coverfullHQ/…` (variantes `B` = autre version de boîtier), `disc` ; `box` (rendu 3D) et `cart` sont exclus. La couleur de boîtier de la fiche est lue pour les variantes identifiées.
- **MobyGames** (facultatif) : avec la clé API du joueur (réglage local, jamais écrite ailleurs), API v1 `games` → `games/{id}/platforms/{pid}/covers` (groupes avec pays, `scan_of`, dimensions), une requête par seconde au plus, crédit MobyGames enregistré. Forme de l'API relevée sur un client tiers publié (npm `@untidy/mobygames`) : la documentation officielle est derrière une protection Cloudflare depuis le conteneur. Non exercé en réel (aucune clé).
- **The Cover Project** : refus HTTP 403 depuis le conteneur, conditions d'accès automatisé non vérifiées → import manuel : bouton qui ouvre sa recherche dans le navigateur, puis « Importer… » avec l'origine déclarée : « jaquette commerciale (Retail) », « création personnalisée (Custom), pas une impression commerciale » ou « scan personnel / autre source ».

Classement des candidats (`GameBoxCandidateRanking`) : 1) bon jeu et bonne plateforme (seuls candidats listés), 2) code produit du joueur (sinon identification par empreinte ou série), 3) édition et région de la copie (régions du ROM, série PS3, édition du recto), 4) nature exacte (scan > jaquette dépliée ; rendus et visuels exclus), 5) qualité et résolution en dernier : une image plus grande ne passe jamais devant la bonne édition. Une complétion garde la cohérence de l'ensemble : après le recto, les autres faces préfèrent le même produit.

Conservation : chaque fichier adopté est vérifié (§ 15), écrit de façon atomique (les autres extensions de la même face supprimées) et décrit dans le manifeste version 2 (`faces` : fournisseur, type, région, langue, édition, code produit, identité à la source, dimensions natives, transformations, MD5, taille, choix manuel, note, crédit). Les manifestes version 1 restent lus. Un enregistrement dont la taille ne correspond plus au fichier (remplacé par un autre outil) est ignoré. Une face importée ou choisie à la main est marquée manuelle et n'est jamais remplacée par une complétion. Seuls les fichiers modifiés voient leurs décodages, tailles, couleurs et contrôles oubliés (`GameBoxArtSet.evictPath`) ; le cache global n'est vidé que si le recto change, parce qu'il est partagé par les vues de la bibliothèque à plusieurs largeurs de décodage (`evictScrapedArtwork`). Les originaux sont gardés tels que téléchargés (jaquette dépliée dans `box2dfull`, supprimée avec les médias du jeu) ; les découpes sont des fenêtres d'affichage, sans réencodage.

## 15. Faces invalides : la face verte de Super Mario 3D World

Chaîne tracée : le dos dessiné à 8 s est un aplat parfait (0, 251, 0 dans l'enregistrement YUV, écart-type nul sur 126 699 pixels) visible dès le début de la rotation, donc avant tout rendu « Texte net » : c'est la texture du dos elle-même. Aucun vert n'existe dans le code du boîtier (une image illisible donne un gris sombre, l'ombrage n'est pas uniforme, une image transparente laisse voir le plastique). Le fichier `box2dback` a donc été adopté tel quel : la validation ne vérifiait que la signature PNG/JPEG. Le panneau indiquait « Édition Australie » pour ce dos ; l'API ScreenScraper n'étant pas joignable sans identifiants depuis le conteneur, la région exacte de l'image fautive chez ScreenScraper n'a pas pu être vérifiée.

Correction (`GameBoxMediaChecker`) : décodage réduit (64 px) et verdict — `uniform` (≥ 98,5 % des pixels opaques dans la même teinte à quelques niveaux près, écart-type de luminance < 3), `transparent` (< 5 % opaques), `tiny` (< 48 px), `unreadable`. Avant adoption : refus, identité ajoutée à `rejected` (jamais retéléchargée), candidat suivant essayé, bilan « dos : image refusée, une seule couleur unie ». À l'affichage : un fichier refusé est dessiné comme une face absente (« Dos refusé : ce n'est pas un scan ») avec le bouton de recherche ; les faces valides restent ; le fichier du joueur n'est jamais supprimé par la visionneuse. Les lectures asynchrones des médias portent une génération : un résultat tardif (autre lecture, autre langue, fichier remplacé) est jeté.

## 16. Netteté et formats

- Dimensions lues sans décodage pour PNG, JPEG (octets de remplissage, marqueurs sans longueur, EXIF/ICC jusqu'à 1 Mio avant le SOF), WebP (VP8, VP8L, VP8X), GIF et BMP. Avant, un WebP accepté au téléchargement n'avait pas de dimensions : pas de rendu à la taille exacte du dos, pas de résolution affichée. Le cache des dimensions est invalidé par la taille et la date du fichier.
- Décodage d'inspection borné par le plus grand côté (2400 px) : un scan Switch 1166 × 1888 est décodé entier (8,8 Mo), un scan de 4000 px de haut est réduit sur sa hauteur ; le rendu à la taille exacte (§ 12) part toujours de l'original.
- Lecteur à plat : ouverture sur le scan entier, centré ; zoom aux doigts, déplacement jusqu'à chaque bord, « Recentrer » et double toucher ; limite de ≈ 2,5 pixels d'écran par pixel du scan inchangée (rien n'est inventé). Un scan basse résolution reste signalé et la recherche d'un meilleur scan est proposée par « Médias du boîtier ».

## 17. Vérifications et limites de la correction du 1er novembre 2026

Exécuté dans le conteneur (Linux, Flutter 3.47.2, celle de la CI) :
- `flutter analyze lib test` : aucune erreur ; aucune remarque dans les fichiers du boîtier.
- `flutter test` : 164 tests des boîtiers (les 110 existants, dont `game_box_sharp_back_test` adapté, et 54 nouveaux) : `game_box_physical_test` (profils physiques, placement, nature des images, gabarits, dimensions des formats, contrôles), `game_box_rotation_test` (rotation complète dans les deux sens depuis l'avant et le dos, bouton « Dos », passage du zoom 1,05, panneau portrait, pincement à gauche ; ces tests échouent avec l'ancienne bascule de perspective, vérifié en la réintroduisant : sauts de 10,5 à 32,9 px), `game_box_sources_test` (GameTDB, MobyGames, classement, URL pleine taille, manifeste v2, adoption avec refus du dos vert, protection des faces manuelles, jaquette dépliée), `game_box_refused_face_test` (le dos vert dans la visionneuse), `game_box_media_sheet_test` (« Médias du boîtier » : ScreenScraper simulé, GameTDB par le titre Switch, complétion cohérente recto/dos, tranche issue de la jaquette dépliée, bilan et état des sources). Suites existantes relues : `game_repository_test`, `game_deletion_regression_test`, `storage_orphan_detector_test`, `artwork_cache_test`.
- Python : `generate_strings.py --check` (178 textes × 12 langues), `test/game_box_strings_test.py`, `test/localization_12_locale_coverage_test.py`, `test/storage_contract_test.py` (l'import manuel d'une face est déclaré et enveloppé dans `StorageImportActivity.run`), `test/rpcs3_library_file_route_contract_test.py`. Rectifié le 2 novembre : `test/rewind610_delivery_contract_test.py` n'était pas au vert ; il échoue (1 échec, 2 erreurs) à l'identique sur `6f4244a` et `7549901` sans ces changements, car il refuse toute modification postérieure à la source testée de la 610. `test/retroarch_baseline_scope_test.py` échoue de la même façon sur l'export intact du HEAD `df337fe` (fichiers non modifiés ici : `lib/main.dart`, `sqlite_config_provider.dart`, `config_service.dart`, `native/neoswap-storage/Store.cpp`).
- Banc avant/après (`test/game_box_compare_preview_test.dart`, hors CI, avec `GAME_BOX_COMPARE_ART` et `GAME_BOX_COMPARE_OUT`) : la même visionneuse pilotée par gestes sur l'ancien code (export du HEAD) et le nouveau ; images de jeux de GameTDB et substituts générés, gardés hors du dépôt. Contours mesurés sur les images rendues : tour au doigt God of War III, saut maximal 17 px avant, ≤ 1 px après ; Mario 11 px → 1 px ; Mario Kart 7 (3DS) identique avant/après.

Le test `game_box_sharp_back_test` (Build 494) est adapté sur deux points : son dos factice (en-tête PNG seul) est déclaré valide au nouveau contrôle, et l'exigence « dos ≥ 68 % de la largeur en portrait » — atteignable seulement parce que le recto de test de 1 × 1 px rendait le boîtier PS2 carré — est remplacée par « dos aussi large que la zone le permet pour le vrai boîtier 135 × 190 mm (à 2 % près), et au moins la moitié de l'écran ».

Choix manuels : un recto remplacé dans Réglages du jeu › Scraping › Médias est désormais enregistré comme choix manuel dans le manifeste. Le scraping par lots (« Faces du boîtier ») enregistre toujours ses fichiers sans contrôle d'image ; depuis le 2 novembre, son étape « faces du boîtier » remplace un aplat ainsi écrit (§ 18).

Limites : aucune mesure sur iPhone (fluidité, mémoire, temps de décodage) — le banc mesure la géométrie, pas la puce ; MobyGames non exercé faute de clé ; The Cover Project seulement en import manuel ; correspondance Switch ↔ GameTDB par titre exact (pas d'identifiant commun) ; un recto découpé dans une jaquette dépliée n'est pas écrit dans `box2d` (seules les fenêtres d'affichage du boîtier en profitent) ; le rendu à la taille exacte reste réservé au dos.

## 18. Scraping par lot : « Nouveau contenu uniquement » et nouvelles sources (2 novembre 2026)

Demande du mainteneur : « l'option scraper que le nouveau contenu en changeant les choix ne scrape rien » ; ajouter sur le même bouton la possibilité de scraper et/ou de chercher ce qui manque avec les nouvelles sources, selon les choix établis.

**Reproduction.** Banc `test/scraper_batch_flow_test.dart` : base SQLite en mémoire, faux ScreenScraper (client HTTP de test `ScreenscraperClient.debugClient`), vrai `ScreenScraperService.startMetadataScraping`. Ajouter un type de média puis lancer « Nouveau contenu uniquement » fonctionnait déjà pour une ROM classique : les jeux terminés sont rouverts à l'ajout d'un type depuis la correction des manuels (migration v112). Causes confirmées :

1. Changer l'ordre des régions ou la langue ne rouvrait aucun jeu : 0 jeu traité, « Tous les jeux sont à jour ».
2. Les icônes de console copiées à l'import comptaient comme des médias présents : `ICON0.PNG` (toujours 320 × 176) copié par la bibliothèque RPCS3 dans `ps3/box2d` et `ps3/screenshots`, icône Switch (JPEG carré 256 × 256) copiée par l'import MeloNX dans `switch/box2d/<jeu>.jpg`. Pour la PS3, le scraper contournait le problème en écrasant tout à chaque passage : après l'ajout des faces, 8 téléchargements au lieu de 3 (vidéo, capture, fanart, logo et jaquette retéléchargés) et la jaquette choisie à la main écrasée. Pour la Switch, quand ScreenScraper envoyait lui aussi un JPEG, l'icône restait en place.
3. Une jaquette présente sous une autre extension (import ES-DE, image personnelle en `.jpg`) était supprimée au profit du PNG de ScreenScraper, même en « Nouveau contenu uniquement ».
4. Une tranche issue d'une jaquette dépliée (`box2dfull`, § 14) n'était pas reconnue : « Compléter les faces » retéléchargeait la jaquette dépliée à chaque fois.

Hypothèse non retenue : la remise à zéro à l'ajout d'un type de média fonctionne (vérifiée par le banc).

**Ce que fait « Démarrer » (page Mode de scraping).**
- *Nouveau contenu uniquement* : seulement ce que les choix actuels demandent et qui manque — jeux jamais recherchés, types de médias cochés depuis, icônes de console (remplacées dans tous les modes) et, après un changement de régions ou de langue, les images que ScreenScraper avait envoyées pour l'ancien choix. Une image n'est remplacée que si son MD5 figure parmi ceux que ScreenScraper liste pour ce type (elle vient donc de lui) et diffère de la meilleure pour les choix actuels ; une image importée, personnelle ou d'un autre scraper n'est jamais remplacée (quand ScreenScraper donne la taille de chaque variante, une taille absente de la liste évite même de hacher le fichier). Vidéos et manuels présents sont gardés ; un média présent sous une autre extension compte comme présent.
- *Tout le contenu* : tout est retéléchargé, sauf les faces du boîtier qui ont une provenance enregistrée (choisies à la main, ou retenues par les sources du boîtier).
- *Faces de boîtier manquantes uniquement* (nouveau) : ni métadonnées ni autres médias. Pour chaque jeu, les faces demandées par les choix (« Box 2D » : face avant ; « Faces du boîtier » : face arrière, tranche, disque ou carte) qui manquent, sont refusées (aplat, image transparente, trop petite, illisible) ou sont une icône importée sont cherchées : ScreenScraper (une requête), puis GameTDB, puis MobyGames avec la clé du joueur. Un jeu sans nom scrapé prend pour GameTDB le nom que donne ScreenScraper (monde, États-Unis puis Europe), la correspondance Switch se faisant par titre exact. Un jeu dont les faces sont complètes ne coûte aucune requête.
- *Compléter avec GameTDB et MobyGames* (interrupteur, activé par défaut, préférence `NeoStation.GameBox.ScrapeExtraSources`) : dans les deux premiers modes, après le téléchargement ScreenScraper, les faces encore manquantes, refusées ou icônes sont complétées avec le classement de la feuille « Médias du boîtier » (§ 14 : produit, édition et région, nature, qualité ; faces choisies à la main jamais remplacées). D'abord les autres scans de la réponse ScreenScraper déjà reçue (aucune requête de plus), puis GameTDB, puis MobyGames pour ce que GameTDB n'a pas. Interrupteur coupé, seule la réponse ScreenScraper sert. Les étapes GameTDB et MobyGames passent une à une entre les fils du scraping (pages partagées, une requête MobyGames par seconde).

**Réouverture des jeux terminés.** `is_fully_scraped` veut dire « complet pour les choix du dernier passage ». Ajouter un type de média (`ScraperRepository.saveEnabledMediaTypes`, inchangé), changer l'ordre des régions (page Régions) ou la langue rouvre les jeux terminés (`ScrapeChoices`) ; rien n'est téléchargé avant « Démarrer ». `lib/repositories/scraper_repository.dart` est un fichier de bibliothèque verrouillé (`docs/retroarch-baseline-manifest.json`, `test/retroarch_baseline_scope_test.py`) : il n'est pas modifié.

**Bilan.** La fenêtre de fin de scraping, jusque-là en anglais seul, est traduite dans les 12 langues et indique : jeux, réussis, échecs, durée, médias ajoutés, médias remplacés, faces de boîtier trouvées (par source), faces encore manquantes, et « Rien de nouveau… » quand rien n'a changé.

**Fichiers.** `lib/services/screenscraper/media_placeholder.dart` (icônes importées), `media_downloader.dart` (présent sous une autre extension, icônes, variantes prouvées par MD5, types protégés ; un fichier présent est validé sur ses 256 premiers octets au lieu d'être relu en entier, une vidéo comprise), `game_id_media_fallback.dart` (garde un média présent en « Nouveau contenu uniquement »), `scrape_choices.dart`, `screenscraper_service.dart` (modes, faces protégées, étape des faces), `media_resolver.dart`, `screenscraper_client.dart` (crochet de test), `lib/services/game_box/game_box_batch.dart`, `game_box_media_service.dart` (`facesToComplete`, `complete(kinds:)`, réponse ScreenScraper réutilisée, source de chaque face, jaquette dépliée comptée pour la tranche et la face arrière), `game_box_fetcher.dart` (`listingOf`, nom ScreenScraper), `game_box_preferences.dart`, écrans `scrape_mode_content.dart`, `scraping_content.dart`, `region_content.dart`, `new_scraper_options_screen.dart`, `lib/widgets/scraping_summary_dialog.dart`, `lib/providers/scraping_provider.dart`, 16 textes × 12 langues dans `tools/game_box/strings.json`.

**Vérifications** (conteneur Linux, Flutter 3.47.2, celle de la CI). `flutter analyze lib test` : aucune erreur ni avertissement (121 remarques, toutes antérieures). `flutter test` : 290 tests réussis, 1 ignoré (banc de comparaison hors CI). Ce total comprend les 10 du nouveau banc `scraper_batch_flow_test` : ajout d'un type, ordre des régions, langue, jaquette sous une autre extension, `ICON0` PS3 puis jaquette choisie à la main, icône Switch, GameTDB après ScreenScraper, interrupteur coupé, mode des faces seules, face protégée en « Tout le contenu ». Il comprend aussi toutes les suites qui importent un fichier modifié : boîtiers, `scraper_repository_test`, `screenscraper_service_test`, `screenscraper_manual_media_test`, `new_scraper_options_screen_test`, `esde_import_service_test`, `scraping_notification_listener_test`, `rpcs3_stage3_test`, `navigation512_switch_test`, `game_repository_test`, `melonx_deletion_test`. Python : `generate_strings.py --check` (194 textes × 12 langues), `game_box_strings_test`, `localization_12_locale_coverage_test`, `storage_contract_test`, `rpcs3_library_file_route_contract_test`. `retroarch_baseline_scope_test` échoue sur les 4 mêmes fichiers que sur le HEAD `35afb4c` intact ; aucun n'est touché ici, et `scraper_repository.dart` garde son empreinte.

**Limites.** Un média supprimé à la main d'un jeu déjà complet n'est pas récupéré par « Nouveau contenu uniquement » : il faudrait mémoriser par jeu et par type ce que ScreenScraper n'a pas, sinon chaque passage réinterrogerait ces jeux ; « Tout le contenu » le récupère, et « Faces de boîtier manquantes uniquement » pour les faces. Après un changement de régions, une image qui ne vient pas de ScreenScraper n'est pas remplacée (par prudence). Rien n'a été exécuté sur iPhone ; MobyGames n'a pas été appelé (pas de clé) ; ScreenScraper et GameTDB sont simulés dans les tests.

## 19. Stabilité du scraping, français et lisibilité au zoom (2 novembre 2026, après l'IPA 614)

Demande du mainteneur, avec quatre captures de dos lus de près (10-Yard Fight, Super Smash Bros. Brawl, Fire Emblem: Radiant Dawn, The Storm of the Century) et un `app.log` : certaines jaquettes restent floues au zoom ; un scraping peut s'arrêter seul puis réussir après plusieurs relances ; mieux prendre en charge le français pour les jaquettes et les notices ; un nouveau scraping en français doit remplacer, et si possible supprimer, les anciennes jaquettes et notices.

**Journal fourni.** Il couvre le 31 octobre (avant la 614) : cinq démarrages de l'app et aucun lancement de scraping ScreenScraper. Il ne montre donc pas l'arrêt ; les causes ci-dessous viennent du code, chacune reproduite par le banc `test/scraper_batch_flow_test.dart`. Le journal du scraping est désormais explicite : début de chaque lancement (mode, langue, fils, médias, nombre de jeux), raison de sa fin (terminé avec les comptes, arrêté par l'utilisateur ou par un nouveau lancement, quota, erreur), cause de chaque jeu non trouvé ou en échec passager, et MD5 évité pour un gros fichier.

**Stabilité : causes et corrections.**
1. Le MD5 d'un fichier non trouvé par son nom était calculé quelle que soit sa taille : plusieurs minutes pour un NSP, XCI ou ISO de plusieurs gigaoctets, pendant lesquelles le lancement semblait arrêté. Au-delà de 1 Gio (`batchMd5Limit`), pas de MD5 : une recherche par le titre nu (sans `[0100…][v0]` ni `(Europe)`) le remplace.
2. Un « Démarrer » pendant qu'un lancement précédent se terminait (après Arrêter, ou bloqué sur un jeu lent) échouait aussitôt sans rien dire, jusqu'à la fin de l'ancien, d'où « ça marche après plusieurs relances ». Pire, l'ancien reprenait, car les deux lisaient le même indicateur. Chaque lancement a maintenant un numéro : un nouveau arrête l'ancien à sa prochaine étape, l'attend (60 s au plus), puis démarre ; seul le dernier « Démarrer » met à jour la progression et la notification.
3. Les jeux passaient par paquets du nombre de fils, et un jeu lent bloquait tout le paquet. Un pool de fils prend désormais le jeu suivant dès qu'un fil est libre.
4. Chaque jeu téléchargeait ses médias en parallèle alors que les fils occupaient déjà tous les créneaux du compte : les requêtes en attente de créneau échouaient au bout de 15 s. Les médias d'un jeu passent maintenant un par un.
5. La réponse « trop de requêtes » de ScreenScraper (HTTP 429) faisait échouer le jeu. Elle est attendue (2, 4 puis 6 s) avant un nouvel essai.
6. Les échecs passagers (connexion perdue, délai dépassé, erreur serveur, pas de créneau, 429 persistant) sont notés par jeu ; ces jeux sont rejoués une fois en fin de lancement, et un jeu introuvable ne l'est pas. Le quota du jour (HTTP 430) arrête aussitôt, au lieu d'être réessayé pour rien.

**Français : jaquettes et notices.**
- ScreenScraper : pour les médias qui portent du texte (jaquette et faces du boîtier, logo, notice), l'impression du pays de la langue de scraping passe devant l'ordre des régions. Bonus de 150, quand l'ordre des régions vaut de 10 à 100 ; une notice marquée de la langue garde son bonus de 200. Les captures, fanarts et vidéos ne changent pas, et l'anglais ne reçoit aucune préférence.
- Changement de langue : il rouvre les jeux terminés (§ 18). Le passage suivant remplace maintenant aussi les notices, en plus des images, dès que le fichier présent est prouvé venir de ScreenScraper (son MD5 figure dans la liste). La nouvelle version prend le même nom ; une image d'une autre extension est supprimée.
- Sources du boîtier (feuille « Médias du boîtier » et étape des faces du lot) : la langue entre dans le classement après le produit, dans l'édition du joueur (+5000). Pour une copie européenne, le scan de France passe devant le scan européen générique ; une copie américaine garde sa boîte américaine. Une face retenue auparavant dans une autre langue (non choisie à la main) cède sa place à l'impression française de la même famille d'édition.
- L'étiquette « Édition France : ce n'est pas l'édition de votre jeu (Europe) » était fausse : chaque pays d'Europe imprime sa boîte de l'édition européenne. La comparaison se fait maintenant par famille de régions.
- Non remplacés, par prudence : une image ou une notice qui ne vient pas de ScreenScraper (import ES-DE, fichier personnel), et les éditions de dos déjà téléchargées pour le sélecteur de langue de lecture.

**Lisibilité au zoom.** Le rendu à la taille exacte du dos et de la vue à plat (§ 12) refusait d'agrandir un scan : au-delà de sa taille, l'écran l'étirait en bilinéaire, d'où le flou des captures. Il l'agrandit maintenant lui-même, jusqu'à 2,5 fois (la limite du zoom de la vue à plat), en bicubique de Mitchell-Netravali. L'accentuation est réglée sur l'agrandissement : rayon 0,9 multiplié par le facteur et plafonné à 1,8 px, force de 0,30 à 0,45. La mémoire reste bornée à 12 Mpx. C'est de l'interpolation : rien n'est inventé, et un scan de 450 px reste un petit scan, mieux rendu. Deux tests du Build 494 exprimaient l'ancienne règle « jamais agrandi » (`game_box_sharp_scan_test`, `game_box_sharp_back_test`) ; ils sont adaptés à la nouvelle borne de 2,5 fois. Un nouveau test vérifie qu'un texte agrandi 2,5 fois garde des bords nettement plus nets (acutance > 1,15 fois) qu'un étirement bilinéaire, sans franges de couleur.

**Vérifications** (conteneur Linux, Flutter 3.47.2). `flutter analyze lib test` : aucune erreur ni avertissement (121 remarques, toutes antérieures). `flutter test` : 278 tests réussis, sur les suites qui importent un fichier modifié (dont toutes celles des boîtiers), plus `scraper_repository_test`, `screenscraper_service_test`, `screenscraper_manual_media_test`, `new_scraper_options_screen_test`, `esde_import_service_test`, `scraping_notification_listener_test`, `game_repository_test`, `melonx_deletion_test`, `rpcs3_stage3_test` et `navigation512_switch_test`. Nouveaux scénarios du banc :
- réponse 429 attendue ;
- jeu rejoué après une connexion perdue ;
- jeu introuvable non rejoué ;
- nouveau « Démarrer » pendant un lancement ;
- gros fichier cherché par son titre nu, sans MD5 ;
- jaquette et notice françaises ;
- passage au français qui remplace la jaquette et la notice, sans toucher la capture ;
- dos GameTDB anglais remplacé par sa version française ;
- choix ScreenScraper selon la langue ;
- classement par langue (dans `game_box_sources_test`).

Python : `generate_strings.py --check` (194 textes × 12 langues), `game_box_strings_test`, `localization_12_locale_coverage_test`, `storage_contract_test`, `rpcs3_library_file_route_contract_test` ; `retroarch_baseline_scope_test` échoue sur les 4 mêmes fichiers qu'avant, et `scraper_repository.dart` n'est pas touché.

**Limites.**
- Rien n'a été mesuré sur iPhone : ni durée d'un lancement réel, ni mémoire de l'agrandissement.
- La cause exacte de l'arrêt observé n'est pas prouvée par un journal : un `app.log` pris juste après un arrêt la montrera.
- Un scan très petit reste peu lisible ; seule une meilleure source y remédie. GameTDB ne sert aujourd'hui que pour la PS3 et la Switch. L'étendre à la Wii, au GameCube, à la DS et à la 3DS (scans HQ et versions françaises, par exemple Brawl et Radiant Dawn des captures) demanderait de lire l'identifiant du jeu dans l'en-tête du disque ou de la cartouche : c'est la prochaine étape proposée.

## 20. Relief des boîtes : tranches, dessus et dessous lisibles pendant la rotation (2 novembre 2026)

**Défaut reproduit.** Le banc `test/game_box_relief_preview_test.dart` rend une boîte par format, avec un recto seul quand il le faut. Il n'est actif qu'avec `GAME_BOX_RELIEF_OUT` et des scans locaux jamais versés. Il couvre :
- les cartons N64, SNES, NES, GBC, GBA, Neo Geo et FDS ;
- les boîtiers PS1 (cristal), Mega Drive (clamshell), PS2, PS3, GameCube, Wii et PSP ;
- les boîtiers Switch, DS, 3DS et Vita.

Vues rendues : face, trois-quarts, profil côté tranche, profil côté ouverture, trois-quarts par le haut et par le bas, trois-quarts arrière, dos, et un tour complet tous les 30°.

Trois causes, toutes dans le composant partagé :
1. **Éclairage.** Il ne faisait qu'assombrir les faces : jusqu'à 45 % de noir, sans reflet. Un boîtier noir (PS1, PS2, GameCube, Mega Drive, PSP) se fondait dans le fond sombre de profil et vu de dessus ou de dessous. Deux faces voisines de même teinte ne se distinguaient pas.
2. **Bords d'un carton.** Le dessus, le dessous et le bord d'ouverture étaient des aplats unis, de la couleur moyenne du bord du recto, sans pli ni impression. De profil, la boîte semblait creuse : c'est la capture d'*A Bug's Life*.
3. **Sans verso.** Une boîte sans verso montrait une dalle vide, de la couleur du boîtier.

**Corrections.**
- Lumière par matériau (`GameBoxScene.lightOf`, `GameBoxFaceLight`) :
  - l'ombre de l'orientation est gardée ;
  - un côté de plastique sombre est moins assombri et reçoit un reflet ;
  - le brillant croît quand la face s'incline ;
  - chaque pli ou arête arrondie entre deux côtés reçoit un fin liseré de lumière.

  Les facettes des coins arrondis ne sont pas striées. Une face vue de face garde son impression intacte : aucun voile, aucun liseré sur un boîtier clair.
- Les côtés d'un carton sont imprimés (`GameBoxCardboardPanel`) : couleur du bord du recto, titre du jeu sur le dessus, le dessous et le bord d'ouverture (lu de haut en bas sur ce dernier), plis aux quatre arêtes. Aucun pixel du recto n'est étiré sur les bords.
- Une boîte sans verso authentique montre un verso reconstitué (§ 21).
- **Même axe.** Vue en perspective, une boîte qui tourne n'est pas symétrique. Pendant le passage au dos, sa silhouette dérivait d'environ 17 px de côté et 15 px vers le haut (fenêtre de 400 × 600), et l'axe semblait bouger. La silhouette du boîtier fermé est maintenant centrée à chaque pose (`BoxProjector._centring`) : la boîte tourne autour de la même verticale de l'écran, sur 360°, inclinée ou non, et l'ouverture du boîtier ne la déplace pas. Le dos atteint est droit et non inversé.

**Tests** (`game_box_relief_test`, `game_box_geometry_test`) :
- une face vue de face reste intacte ;
- chaque côté à trois-quarts reçoit son liseré ;
- un côté noir est relevé, pas assombri ;
- les coins arrondis portent leur propre lumière ;
- les côtés d'un carton portent le titre, jamais le recto étiré ;
- le verso reconstitué s'affiche pour chaque format ;
- la dérive pendant le passage au dos reste sous 0,5 px pour 15 formats, et sous 1 px sur un tour complet à quatre inclinaisons ;
- le dos est droit et non inversé pour chaque format.

## 21. Verso : « Modifier le verso », « Rétablir le verso automatique », verso reconstitué

**Bladestorm (PS3, BLES00113, Europe).**
- Image affichée : `back/EN` de GameTDB, une vignette de 160 × 184 px. GameTDB n'a ni `backHQ` ni `coverfullHQ` pour cette édition, dans aucune langue (vérifié : EN, FR, DE, ES, IT, NL, PT, SE, DK, NO, FI). Seule l'édition américaine BLUS30070 en a un, et c'est une autre édition.
- Ce n'est ni une erreur de découpe ni d'orientation : le cadrage et le sens sont justes, la source est trop petite pour que ses lettres (2 à 3 px) se lisent.
- La correction du § 22 rend les titres plus nets, pas le corps du texte. Il faut une meilleure image de la même édition, choisie dans « Médias du boîtier » ou importée.

**« Modifier le verso »**, depuis la fiche de n'importe quel jeu (bouton sur la boîte de l'onglet Jaquette) et depuis les options de la visionneuse :
- import depuis Photos ou depuis Fichiers (`StorageImportActivity`) ;
- cadre à déplacer et à redimensionner par ses coins ; une jaquette complète est cadrée d'office sur son verso ;
- aperçu sur la boîte vue de dos avant d'enregistrer ;
- enregistrement comme face choisie à la main (`manual:back`, source et recadrage notés) ;
- le verso automatique précédent est mis de côté, intact (`box2dback-auto/`, avec sa fiche) ;
- une image blanche ou illisible est refusée et rien ne change.

**Le choix reste prioritaire :**
- après un redémarrage (fichier et manifeste sur le disque) ;
- après un nouveau scraping : l'étape des faces le garde (`manualKept`), le téléchargement ScreenScraper le protège (`ownedTypes`) ;
- dans toutes les langues de lecture (les éditions de dos d'autres langues ne le remplacent pas).

Seul le verso de ce jeu change.

**« Rétablir le verso automatique »** remet le verso mis de côté et sa fiche, sans réseau. S'il n'y en avait pas, les sources sont interrogées pour ce seul verso ; sinon, le verso reconstitué s'affiche.

**Verso reconstitué** (`GameBoxComposedBack`) : quand aucun verso authentique n'existe, la boîte montre un verso sobre fait des seules données vérifiées du jeu :
- le titre ;
- une capture d'écran scrapée (jamais l'icône de console qui en tient lieu) ;
- le résumé du scraper ;
- l'année, le studio, l'éditeur et le genre ;
- le nombre de joueurs ;
- la plateforme.

Ses couleurs sont tirées du bord du recto. Il porte l'étiquette « Verso reconstitué » et n'imite aucune impression.

**Tests** (`game_box_back_override_test`) : import, recadrage, redémarrage, nouveau scraping (ScreenScraper et GameTDB proposent un verso lisible ; le choix reste), un autre jeu inchangé, retour au verso automatique identique octet pour octet, image blanche refusée, et l'éditeur (cadrage d'une jaquette complète, poignée, aperçu, enregistrement).

## 22. Correction des images dégradées, sans les remplacer

Chaque face (recto, verso, tranche, jaquette complète, en français ou non) est examinée une fois (`GameBoxEnhance`). Seuls les défauts trouvés sont corrigés, sur une copie en cache (`NeoStation/GameBox/enhanced/`). Le fichier d'origine n'est jamais modifié ni remplacé par un autre scan.

| Défaut détecté | Mesure | Correction |
|---|---|---|
| blocs JPEG | saut aux bordures 8 × 8 / saut ailleurs > 1,18 | filtre de dé-blocage des codecs vidéo (fort dans les aplats, faible ailleurs), puis lissage de la chrominance guidé par la luminance |
| bruit | écart-type d'Immerkær sur la moitié la plus plate > 6 | lissage bilatéral 5 × 5 qui garde les bords |
| tons délavés | écart 1–99 % de luminance < 150 | étirement partiel (60 %) |
| flou | mesure de Crété-Roffet > 0,42 | déconvolution de Richardson-Lucy de la luminance, largeur du flou estimée |
| basse résolution | grand côté < 1 600 px | interpolation directionnelle DCCI ×2 par étape (au plus ×8), puis accentuation légère |

Étalonnage sur le verso français de God of War III :

| Version | Valeur avant | Valeur après | Limite |
|---|---|---|---|
| nette | flou 0,20 | — | — |
| flou gaussien de 1,6 px | flou 0,52 | flou 0,40 | 0,42 |
| JPEG qualité 12 | blocs 1,53 | blocs 1,00 | 1,18 |
| bruit σ 9 | bruit 8,8 | bruit 0,5 | 6 |

Une illustration texturée (recto de Bladestorm, bruit 5,1) n'est pas lissée.

Ce n'est que du calcul sur les pixels de l'image : aucun modèle génératif, rien d'inventé.

- À 350 × 408 px (taille « M » de GameTDB), le paragraphe du verso de God of War III redevient lisible.
- À 160 × 184 px (taille du verso de Bladestorm), les titres deviennent plus nets, mais le corps du texte reste illisible : l'information n'est pas dans le fichier.

« Texte net » coupé, les originaux s'affichent. La copie est refaite si le fichier change ; une image saine est mémorisée comme telle. La visionneuse à plat et la ligne des sources indiquent les défauts corrigés.

Une vignette de la même édition cède sa place à un scan lisible seulement quand une face est choisie (face manquante, liste des candidats), jamais quand une face existe déjà. Une impression dans la langue de scraping (par exemple française) n'est jamais déplacée derrière un scan dans une autre langue.

**Tests** (`game_box_enhance_test`) :
- chaque défaut est détecté sur sa propre copie dégradée, et seulement lui ;
- chaque correction repasse sous sa limite ;
- l'agrandissement garde les pixels connus, et une diagonale reste droite ;
- l'original reste identique octet pour octet, et le cache est relu après un redémarrage ;
- une image saine n'est pas copiée ;
- l'impression française reste en tête.

## 23. DS et 3DS fidèles à leurs jaquettes

Références de la même édition (GameTDB) :
- Mario Kart DS France, AMCP : recto, verso et jaquette complète ;
- Mario Kart 7 Europe, AMKP : recto et verso ;
- The Legend of Zelda: Majora's Mask 3D, AJRP : jaquette complète.

Les deux consoles ont le même gabarit : verso 768 | tranche 80 | recto 768 × 680 px. Le recto est donc **plus large que haut** (1,13). Avec la tranche de 14 mm d'un boîtier DS, la jaquette mesure 134,4 × 119 mm.

RewindBox modélisait ces boîtiers en portrait (125 × 137 mm) : le recto réel y était rétréci, avec des bandes vides en haut et en bas, et le verso était mal cadré.

**Corrigé.**
- Boîtier DS de 137 × 125 × 14 mm, boîtier 3DS de 137 × 125 × 11 mm. La zone imprimée est à 1,3 mm des côtés et 3 mm du haut et du bas, aux proportions exactes du scan : rien n'est rogné, rien n'est déformé.
- Le bandeau NINTENDO DS (à gauche du recto) ou NINTENDO 3DS (à droite) est celui du scan : il n'est ni masqué ni ajouté une seconde fois.
- Une jaquette complète est découpée selon ce gabarit et remplit aussi un recto manquant (pour toutes les plateformes qui ont un gabarit vérifié).
- La tranche est lue de haut en bas, comme l'original. Sur un boîtier plus fin que la bande imprimée (3DS), la bande est montrée entière, dans ses proportions, entre deux marges.
- Le témoin 3DS de `game_box_physical_test` supposait un scan portrait de 900 × 1000 px. Il est remplacé par la taille du vrai scan (768 × 680), avec en plus la jaquette complète 3DS et le recto DS.

**À vérifier sur un vrai boîtier.** Aucune photo de boîtier n'a pu être récupérée ici ; la référence de forme est le rendu « box » de GameTDB. L'épaisseur 3DS de 11 mm vient de comptes rendus selon lesquels les boîtiers 3DS sont plus fins que ceux de la DS, pas d'une mesure. GameTDB n'est pas encore une source des faces DS et 3DS dans RewindBox (§ 19).

## 24. Les autres plateformes, avec la même méthode (2 novembre 2026)

Pour chaque boîtier rigide, les proportions du recto imprimé sont comparées à de vrais scans :
- jaquettes complètes de GameTDB : Wii (Brawl RSBP01, Mario Kart Wii RMCP01), GameCube (Melee GALP01, Double Dash!! GM4P01), Wii U (Mario Kart 8 AMKP01, New Super Mario Bros. U ARPP01), en anglais et en français ;
- rectos des vignettes libretro : environ 30 scans par plateforme (Europe, États-Unis, Japon), mesurés en médiane.

| Format | Recto mesuré (l / h) | Zone imprimée avant | Après |
|---|---|---|---|
| PS2, Xbox, Xbox 360, Wii, Wii U | 0,705 à 0,715 | 0,706 | inchangée |
| GameCube | 0,704 à 0,717 | 0,702 | inchangée |
| Mega Drive, Master System | 0,706 à 0,710 | 0,706 | inchangée |
| PSP | 0,58 | 0,571 | 0,582 (boîtier de 106 mm) |
| PS Vita | 0,785 | 0,773 | 0,784 (boîtier de 106,5 mm) |
| PC Engine (Japon) et TurboGrafx-16 (USA) | 1,00 (carré) | 1,14 et 0,71 | 1,00 (jaquette de 120 × 120 mm dans un boîtier de 142 × 125 mm) |
| PS1 et cartons | carré (PS1), variable | cristal : livret carré contenu ; carton : suit son scan | inchangés |

**Bandeaux.** Ils font tous partie de la jaquette :
- en haut : PlayStation 2, PSP, PS Vita, Xbox, Xbox 360, Wii, Wii U, NINTENDO GAMECUBE ;
- à gauche : Mega Drive/Genesis, Sega Saturn.

Le boîtier n'en ajoute aucun, et les zones imprimées corrigées ne les rognent plus.

**Jaquettes complètes.** Les gabarits mesurés sont :
- Wii et GameCube : verso 484 | tranche 56 | recto 484, sur 680 px de haut ;
- Wii U : 776 | 80 | 776, sur 1080 px de haut.

Ils sont reconnus et découpés : une jaquette complète seule donne maintenant le recto, le verso et la tranche (auparavant, une Wii ou une GameCube sans recto restait vide, et une PS3 n'avait que le verso et la tranche).

**Tranches.** Chaque gabarit dit comment poser sa bande de tranche (`GameBoxSpineFit`) :
- Switch, DS, Wii, GameCube, Wii U : la bande garde ses proportions, et le peu qui dépasse (au plus 6 % de chaque côté) est le pli sur les bords ;
- 3DS : la bande est entière, entre deux marges ;
- PS3 : la bande est étirée comme avant. Sa tranche de gabarit (20 mm à l'échelle des panneaux) est bien plus large que la tranche plate du boîtier.

Le rendu « entier entre marges » appliqué la veille à toutes les plateformes réduisait la tranche PS3 : c'est corrigé.

**Icônes carrées.** Une image carrée de 512 px ou moins reste prise pour une icône sur les boîtiers dont la jaquette n'est pas carrée (Switch, PS3, famille DVD). Sur un boîtier HuCard, dont la jaquette est carrée, un scan carré est la jaquette ; seule une image minuscule (128 px ou moins) reste une icône.

**Tests** (`game_box_physical_test`) :
- chaque zone imprimée correspond au recto mesuré de sa plateforme, à 2 % près, pour 15 formats ;
- les jaquettes complètes Wii, GameCube et Wii U sont découpées à leurs limites mesurées ;
- chaque gabarit a son mode de tranche ;
- un scan carré de PC Engine ou de TurboGrafx est une jaquette, et l'icône de la Switch reste une icône.

**Rendus** (`game_box_relief_preview_test`) : Brawl et Melee en jaquette complète seule, Mario Kart 8, God of War III en jaquette complète seule, God of War: Chains of Olympus (PSP), Gravity Rush (Vita) et Boxyboy (TurboGrafx), chacun à côté de sa référence.

**Prochaine étape.** Réalisée au § 25 : GameTDB devient une source pour la Wii, la GameCube, la Wii U, la DS et la 3DS.

## 25. GameTDB pour la Wii, la GameCube, la Wii U, la DS et la 3DS (2 novembre 2026)

GameTDB publie des scans HQ, souvent en français, pour ces cinq plateformes. GameCube et Wii partagent la même base. Ils servent maintenant de source des faces (feuille « Médias du boîtier » et étape des faces du scraping), comme pour la PS3 et la Switch.

**L'identifiant vient du jeu lui-même** (`GameBoxRomId`), lu dans les premiers octets de la ROM sans la charger :

| Plateforme | Identifiant | Formats lus |
|---|---|---|
| Wii, GameCube | 6 caractères (`RSBP01`) | ISO/GCM (0), WBFS (0x200), RVZ et WIA (0x58), CISO (0x8000), TGC (taille de son en-tête) ; le format est vérifié par la signature du disque |
| Wii U | 6 caractères (`AMKP01`) | `meta/meta.xml` d'un titre extrait (code produit et code éditeur) ; un disque WUD ou WUX donne le code produit, complété par la liste GameTDB |
| DS | 4 caractères (`AMCP`) | en-tête de cartouche (0x0C), le titre devant être du texte |
| 3DS | 4 caractères (`AMKP`) | code produit du NCCH (`CTR-P-AMKP`) : .cxi, .3ds/.cci (partition 0), .cia déchiffré (premier contenu) |

À défaut, le jeu est cherché par :
1. l'identifiant de la bibliothèque, s'il a la bonne forme ;
2. un identifiant écrit dans le nom du fichier (`[RSBP01]`) ;
3. son titre exact dans la liste de la plateforme (`wiitdb.txt`, `wiiutdb.txt`, `dstdb.txt`, `3dstdb.txt`, gardée 30 jours).

Un jeu trouvé par son titre n'est jamais pris pour le produit du joueur. Sur un titre commun, une GameCube garde les identifiants G/D et une Wii les identifiants R/S. Les formats compressés dont l'en-tête n'est pas lisible (GCZ, CIA chiffré) passent par le nom puis le titre.

**Édition.** La quatrième lettre de l'identifiant donne la région de la copie : P Europe, F France, D Allemagne, E États-Unis, J Japon… Elle sert, comme le numéro de série PS3, à classer les scans de l'édition du joueur, avec l'impression dans la langue de scraping en tête (§ 19).

**Jaquette complète.** Sur Wii, GameTDB n'a comme recto séparé qu'une vignette de 160 × 224 px ; le recto HQ est dans la jaquette complète de 1024 × 680. Désormais :
- une jaquette complète au gabarit vérifié compte pour le recto, le verso et la tranche ;
- quand une face manque, elle est pesée avec les scans séparés, et une vignette de la même édition et de la même langue lui cède la place ;
- à l'écran, une face gardée qui n'est qu'une vignette de la jaquette (1,5 fois plus étroite ou plus) est montrée depuis la jaquette.

Une face choisie à la main ou imprimée dans une autre langue reste affichée, et aucun fichier n'est remplacé.

**Gabarits mesurés** (téléchargements du 2 novembre 2026) :

| Plateforme | Recto ou verso | Jaquette complète |
|---|---|---|
| Wii | 160 × 224 | 1024 × 680 et 512 × 340 |
| Wii U | 768 × 1080, 350 × 500, 160 × 224 | 1632 × 1080, 752 × 500, 340 × 224 |
| DS et 3DS | 768 × 680, 400 × 352, 160 × 144 | 1616 × 680, 856 × 352, 340 × 144 |

**Tests** (`game_box_nintendo_sources_test`) :
- lecture de l'identifiant dans chaque format, sur des en-têtes construits octet par octet ;
- un fichier sans en-tête de disque ne donne rien ;
- Brawl depuis son ISO : produit, région Europe, jaquette HQ préférée à la vignette, plus aucune face à compléter ;
- une DS sans ROM lisible est trouvée par son titre, sans être prise pour le produit ;
- séparation GameCube/Wii sur un titre commun ;
- recto de la jaquette montré à l'écran seulement dans la même langue.

## 26. Notices en français : nouvelles sources (2 novembre 2026)

Jusqu'ici, ScreenScraper était la seule source des notices. Quand la langue de scraping est le français et qu'un jeu n'a pas encore de notice, deux sources ouvertes s'y ajoutent (`GameManualFrenchSources`). Toutes deux ont été vérifiées en direct le 2 novembre 2026.

1. **Internet Archive, par le code produit de l'édition.**
   - Les collections de notices (`consolemanuals`, `gamemanuals`, `manuals`) comptent au moins 326 notices marquées en français. Leurs titres portent souvent le code de l'édition : `IM-DOL-GALP-FRA` pour Super Smash Bros. Melee France, `DOL-GXEP-FRA` pour Sonic Riders, `AGB-AMKP-NEU5` pour Mario Kart: Super Circuit.
   - Ce code est lu dans la ROM (§ 25), avec en plus le code de jeu d'une cartouche GBA (0xAC), ou vient du numéro de série PS3.
   - Seul un document marqué en français est pris.
2. **Nintendo Europe, pour un jeu DS.** Le PDF officiel français porte le titre du jeu (`Manual_NintendoDS_MarioKartDS_FR.pdf`). Le serveur répond à un nom inconnu par une page HTML avec le statut 200 : seul un vrai PDF (`%PDF`) compte.
3. **Internet Archive, par le titre exact**, en dernier recours. L'élément doit être marqué en français et nommer la même plateforme (« Nintendo GameCube », code `DOL-`, collection GBA…). Il ne doit pas nommer une plateforme voisine : un manuel PlayStation 2 n'est pas pris pour la PlayStation, un manuel Game Boy Advance pas pour la Game Boy.

**Fichier.** C'est l'original quand il fait 60 Mo ou moins. Sinon, c'est la copie compressée que l'archive en fait, avec sa couche de texte : le scan d'origine de Mario Kart: Super Circuit pèse 737 Mo, sa copie 9,8 Mo. Au-delà de 150 Mo, rien n'est pris. La notice est écrite à l'emplacement habituel (`media/<système>/manuals/<jeu>.pdf`), de façon atomique, seulement si c'est un PDF. Une notice déjà présente n'est jamais remplacée.

**Où.**
- Téléchargement d'une notice (Paramètres du jeu › Notice, boîte 3D), en français :
  1. la notice de l'édition par son code produit, ou le PDF Nintendo Europe d'un jeu DS ;
  2. ScreenScraper, comme avant ;
  3. le titre exact sur Internet Archive, si rien n'a été trouvé.
- Scraping par lot : une notice encore manquante est cherchée après l'étape des faces, quand les notices sont cochées et les sources supplémentaires activées. Elle est comptée dans le contenu ajouté du résumé.

**Essai en direct** : Super Smash Bros. Melee et Sonic Riders (GameCube, archive), Mario Kart: Super Circuit (GBA, copie compressée), Mario Kart DS (Nintendo Europe). Un jeu inconnu ne donne rien.

**Tests** (`game_manual_french_sources_test`) :
- notice de l'édition par son code produit lu dans l'ISO, l'élément anglais n'étant pas lu ;
- copie compressée d'un scan géant ;
- par titre, seulement en français et sur la même plateforme (PS1 contre PS2) ;
- PDF Nintendo Europe, et page HTML refusée ;
- seul un PDF est écrit, jamais par-dessus une notice présente ;
- codes produits d'un disque, d'une DS, d'une GBA et d'un numéro de série PS3.

**Limites.**
- La couverture d'Internet Archive en français reste partielle (quelques centaines de notices), surtout GameCube, GBA et Super Nintendo.
- Le PDF Nintendo Europe n'est trouvé que pour les jeux publiés par Nintendo, et seulement sur DS : les dossiers Wii et 3DS de ce serveur n'ont pas un nom prévisible, et une adresse devinée renvoie une page.
- Les notices franco-canadiennes de Nintendo of America sont surtout celles des consoles et accessoires, avec des liens anciens morts : elles ne sont pas utilisées.

## 27. Tranches et côtés comme sur les jaquettes d'origine (3 novembre 2026)

**Retour du mainteneur.** Sur une boîte NES (10-Yard Fight), le côté d'ouverture et les rabats du dessus et du dessous montraient seulement le titre en texte sur un aplat. Ces côtés étaient dessinés ainsi même quand un vrai scan existait. Il demande un rendu comme sur les jaquettes d'origine, par exemple les tranches Wii, GameCube et Wii U de sa photo de référence.

**Ce qui change** (`lib/widgets/game_box/game_box_spine_design.dart`, `game_box_scene.dart`) :

1. **Tranche.** Le scan de la tranche est utilisé s'il existe. Sinon, c'est la tranche de la feuille complète (GameTDB, `box-texture`). Sinon, c'est le **gabarit de la plateforme** :

   | Plateforme | Tranche d'origine reproduite |
   |---|---|
   | Wii | blanche, logo Wii gris en haut, titre foncé |
   | GameCube | noire, logo NINTENDO GAMECUBE blanc, titre blanc en capitales |
   | Wii U | bleue, tête blanche avec le logo Wii U, titre blanc |
   | DS | blanche, logo DS gris |
   | 3DS, Switch | blanche, tête rouge avec le logo blanc |
   | PS1, PS2, PSP | noire, logo blanc, logo du jeu |
   | PS3 | noire, bandeau PS3 |
   | PS Vita | blanche, tête noire PS Vita |
   | Xbox, Xbox 360 | tête verte avec le logo |
   | autres (cartouches, carton, CD) | couleur du bord du recto, logo de la plateforme, logo du jeu |

   Les logos de plateforme sont ceux que l'app affiche déjà (`assets/images/logos`, voir leur `TRADEMARKS.md`). Le « logo du jeu » est le média *wheel* déjà téléchargé par le scraping. Les boîtiers Nintendo et Sony récents impriment le titre en caractères : le logo du jeu n'y est pas utilisé. Un titre long est réduit, jamais coupé.
2. **Boîte en carton.** Une vraie boîte imprime sa tranche sur ses deux grands côtés :
   - le **côté d'ouverture** montre donc la même tranche (scan ou gabarit) ;
   - le **rabat du dessus** montre la tranche couchée en entier, comme le rabat-titre des boîtes réelles ;
   - le **rabat du dessous** garde la couleur de l'impression et le logo de la plateforme ;
   - plus aucun côté n'est « titre en texte sur aplat ».
3. **Boîtiers plastique** (DVD, Blu-ray, cartes). Le dessus, le dessous et l'ouverture restent le plastique du boîtier : blanc pour la Wii, noir pour la GameCube, bleu pour la Wii U. C'est ce que montrent les vrais boîtiers, sans impression.

**Vérification.**
- `test/game_box_spine_design_test.dart` vérifie :
  - les logos ;
  - les gabarits ;
  - la Wii sans scan ;
  - la NES avec scan sur la tranche, le côté d'ouverture et le rabat ;
  - la NES sans scan, avec le logo du jeu ;
  - les titres longs.
- `test/game_box_relief_test.dart` : l'ancien test « titre sur les côtés » est remplacé par cette spécification. Son assertion `find.byType(GameBoxEdgePainter)` ne trouvait jamais rien, car un `CustomPainter` n'est pas un widget ; elle cherche maintenant le `CustomPaint`.
- Rendus manuels : `test/game_box_relief_preview_test.dart`, cas `nes_spine`, `nes_wheel`, `wiiu`, `wii`, `gc`, `ps2`, `n64_bugs` et les feuilles réelles Brawl, Melee et Mario Kart 8. Avec une feuille complète, la tranche est exactement celle de la jaquette.

**Limites.**
- Un gabarit reproduit la mise en page d'origine, pas le visuel propre à un jeu : bandeaux, personnages et mentions légales ne sont pas inventés. Seul un scan (tranche ou feuille complète) donne la tranche exacte. « Récupérer les faces du boîtier » les cherche (ScreenScraper `box-2D-side` et `box-texture`, GameTDB pour Nintendo).
- Le rabat du dessous d'une vraie boîte porte des mentions légales : il reste volontairement sobre.
