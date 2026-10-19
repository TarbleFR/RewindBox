# Boîtiers 3D de la vue Jaquette, lecture multilingue du dos et ouverture au lancement

Demande du mainteneur (19 octobre 2026) : faire de la vue Jaquette un boîtier manipulable comme un objet réel (rotation libre, inclinaison, zoom), dont on lit le dos dans les douze langues de NeoStation, et qui s'ouvre sur sa cartouche ou son disque quand on appuie sur « Jouer ». Précision du mainteneur en cours de cycle : les jaquettes doivent être réalistes, de vraies jaquettes (PlayStation 1 par exemple) et ainsi de suite pour chaque console.

Référence visuelle : la vidéo YouTube `teVZ90DnkbQ` n'a pas pu être consultée (YouTube est refusé par la politique réseau du conteneur de travail, HTTP 403 sur le tunnel ; aucune recherche ne retrouve son titre). Les mouvements, proportions et transitions suivent donc les exigences écrites et les dimensions réelles des boîtiers ; rien de la vidéo n'est vérifié.

## 1. Vue concernée et pile graphique

- **Vue Jaquette** : le carrousel des jeux en style de carte « Boîte » (`gameCarouselCardStyle == 'box'`, `lib/screens/game_screen/my_games_carousel.dart`). Les vues Liste, Grille et le carrousel « Fanart » ne changent pas.
- **Pile graphique** : celle des couvertures de livres 3D de la Bibliothèque (Build 443/447) — des widgets Flutter transformés par des `Matrix4` en perspective, sans dépendance nouvelle ni moteur 3D. Chaque face est un widget (image, surface neutre ou peinture) placé par sa propre matrice ; les faces tournées vers l'arrière sont écartées et les autres peintes de la plus éloignée à la plus proche. Un boîtier fermé est convexe : l'élimination des faces arrière suffit. Ouvert, le corps, le support et le couvercle sont peints dans un ordre de calques défini par famille (le volet d'une boîte en carton passe derrière la cartouche une fois rabattu). Un moteur 3D natif (SceneKit dans une vue de plateforme) a été écarté : coût de composition des vues de plateforme Flutter sur iOS, navigation à la manette et accessibilité à refaire, et aucun test possible hors appareil, alors que le rendu `Matrix4` se teste et se photographie dans `flutter test`.
- Modules : `lib/widgets/game_box/game_box_geometry.dart` (modèle, poses, projection, ouverture), `game_box_scene.dart` (faces), `game_box_surfaces.dart` (surfaces neutres, disque, cartouche, intérieur, charnière), `game_box_card.dart` (carte du carrousel), `lib/screens/game_box/game_box_inspector.dart` (visionneuse), `box_back_reader_screen.dart` (lecture), `lib/services/game_box/` (profils, médias, éditions, lecture du texte).

## 2. Familles de boîtiers (réalisme)

`GameBoxProfile.forSystem` (`lib/services/game_box/game_box_profile.dart`) donne à chaque console sa famille, ses dimensions réelles en millimètres et son support ; une console sans entrée dédiée suit les supports déclarés dans `assets/systems/<id>.json` (`cd_rom` → boîtier cristal, `dvd` → boîtier DVD, `cartridge` → boîte en carton, `digital`/borne d'arcade → carte plate sans ouverture).

| Famille | Consoles | Taille (mm) | Ouverture | Support |
|---|---|---|---|---|
| Boîtier DVD | PS2, Xbox, Xbox 360, Wii, Wii U, GameCube (130 × 184) | 135 × 190 × 14, coins arrondis 4,5 mm | panneau avant autour de la tranche | DVD 120 mm ; GameCube : mini-disque 80 mm |
| Blu-ray | PS3 | 135 × 170 × 12 | idem | BD 120 mm |
| UMD | PSP | 104 × 180 × 13 | idem | UMD dans sa coque |
| Boîtier cristal | PS1, Saturn, Dreamcast, Mega-CD, 3DO, CD-i, PC Engine CD, Neo Geo CD, PC-FX, Jaguar CD | 142 × 125 × 10, angles vifs | couvercle transparent autour de la charnière | CD 120 mm sur plateau noir |
| Boîtier de cartes | DS, 3DS, Switch (105 × 170), Vita (105 × 135) | 125 × 137 × 14 / 11, coins arrondis | panneau avant | carte dans son logement, en haut à droite |
| Boîtier plastique | Mega Drive/Genesis, 32X, Master System, Pico, PC Engine (HuCard) | 135 × 190 × 27 | panneau avant | cartouche ou HuCard |
| Boîte en carton | NES, Famicom, SNES/Super Famicom, N64, GB/GBC, GBA, Virtual Boy, Game Gear, Lynx, NGP, WonderSwan, Atari, Jaguar, Neo Geo | dimensions par console (SNES 180 × 128 × 35, N64 225 × 160 × 40…) | volet supérieur rabattu vers l'arrière | cartouche qui sort par le haut |

Détails reproduits d'après les boîtiers réels :
- **Boîtier cristal (PS1…)** : taille fixe quel que soit l'encart ; l'encart avant carré est posé à droite de la bande de charnière (8 mm), sur le plateau noir vu à travers le couvercle transparent, avec ses marges de plastique ; les deux tranches de l'encart dorsal sont visibles sur les côtés (charnière et ouverture) ; les ergots de charnière apparaissent aux deux bouts du côté charnière ; le dessus et le dessous sont en plastique transparent fumé ; ouvert, le plateau noir et son moyeu à dents tiennent le disque, le couvercle montre ses quatre ergots de livret. Un dos scanné avec ses tranches (≈ 151 × 118 mm, rapport ≥ 1,22) est recadré au milieu pour le dos, et ses bandes latérales servent de tranches réelles quand il n'existe pas de scan de tranche (la bande droite de l'encart, scannée à plat, se replie sur le côté charnière).
- **Boîtier DVD/Blu-ray/portable** : coins arrondis (quatre arcs de trois facettes), jaquette sous film transparent dans un liseré de plastique de 1,4 mm, tranche imprimée entre les plastiques des deux panneaux, stries de préhension côté ouverture, joint du film sur le dessus et le dessous ; ouvert, moyeu à dents ou logement de carte, attaches du livret à l'intérieur du panneau avant.
- **Boîte en carton** : couleur des bords échantillonnée sur le pourtour du recto réel (image réduite à 24 px), plis marqués.
- **Lumière** : un éclairage doux qui ne modifie jamais la face tournée vers le lecteur ; reflet du film limité à 8 % de blanc, coupé quand on regarde le dos ou qu'on zoome.

Rendu de contrôle : `test/game_box_render_preview_test.dart` et `test/game_box_render_inspector_preview_test.dart` écrivent des images quand `GAME_BOX_RENDER_DIR` est défini (images de démonstration générées, jamais de vraie jaquette dans le dépôt).

## 3. Vue Jaquette et visionneuse

**Carrousel.** Chaque carte du style « Boîte » est le boîtier en volume, immobile, à la pose de repos (recto, un peu de tranche et de dessus), avec le vrai recto et, s'il existe, le vrai scan de tranche. La carte n'a pas de geste propre : glisser change toujours de jeu. Toucher le boîtier centré, son badge 360° ou ↑ à la manette ouvre la visionneuse ; « Jouer » (A, bouton du pied de page) ouvre le boîtier puis lance le jeu. Sans recto, la carte de remplacement habituelle de NeoStation est conservée.

**Visionneuse** (plein écran, au-dessus de la bibliothèque, dont la sélection ne peut pas changer) :
- glisser horizontalement : rotation libre sur 360° (le recto suit le doigt), avec une inertie qui s'arrête d'elle-même ; glisser verticalement : inclinaison bornée à ±75° pour voir le dessus et le dessous ;
- pincer : zoom ×1 à ×4 ; à un doigt quand le zoom est actif : déplacement ; double toucher : ×2,2 ou retour ;
- « Face avant », « Dos », « Position initiale » ; le dos est présenté face à la caméra avec une perspective réduite et reste immobile tant qu'on ne le touche pas ;
- manette : ←/→ quart de tour, ↑/↓ inclinaison, L/R zoom, A jouer, B fermer, X lire la jaquette, Y avant/dos, Start langue de lecture, clic gauche position initiale, Select options ;
- portrait : commandes sous le boîtier ; paysage et iPad : colonne à droite ; les commandes passent à la ligne avec l'agrandissement du texte ; le boîtier porte une étiquette d'accessibilité (« Boîtier de …, face visible : dos »).

**Images.** La carte décode le recto à 1024 px de large (la taille que le carrousel utilisait déjà, donc le même décodage) ; la visionneuse demande 2400 px pour le recto et le dos une fois affichée et les libère en se fermant ; le scan du dos s'ouvre en plein écran jusqu'à 4096 px dans le mode lecture. Une image agrandie n'invente rien : si le scan est trop flou, le mode lecture textuelle le signale.

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

`GameBoxMediaFetcher.fetch` (« Récupérer les faces du boîtier » dans la visionneuse) :
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
- **Couverture** : les douze langues font partie des langues de Translation d'Apple (anglais, espagnol, russe, chinois simplifié et traditionnel, portugais du Brésil, français, allemand, italien, indonésien, japonais, coréen) ; Vision reconnaît anglais, français, italien, allemand, espagnol, portugais, chinois simplifié et traditionnel, cantonais, coréen, japonais, russe et ukrainien, entre autres. **L'indonésien n'a pas de modèle de reconnaissance dédié** : un dos imprimé en indonésien (cas très rare) est lu par la reconnaissance latine générale. La couverture effective est relevée par le contrôle natif (§ 9) : liste des langues de reconnaissance de l'OS, reconnaissance réelle d'un texte dans chacune des douze langues sur macOS et dans le Simulateur iOS, et état de `LanguageAvailability` pour les douze langues cibles.
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

Lanceur : `python3 test/game_box_targeted_test.py --part host|native` (verdicts `build/gamebox/<partie>-verdict.json` avec l'empreinte de chaque entrée).

## 10. Limites

- Aucune validation sur iPhone ni iPad : fluidité, mémoire, rendu des scans réels, gestes et lecture restent à essayer sur l'appareil.
- La traduction ne s'exécute pas en CI : le Simulateur ne télécharge pas de modèles de traduction ; seules la disponibilité des langues et la reconnaissance sont exercées. La première traduction vers une langue demande à iOS de télécharger cette langue (proposé par iOS, une fois).
- La qualité de la lecture dépend du scan : un dos basse résolution ou très stylisé donne des lignes peu lisibles, signalées, jamais complétées.
- La langue d'un scan est présumée de sa région ScreenScraper ; les éditions européennes multilingues sont présentées comme anglaises tant que la reconnaissance n'a pas détecté autre chose.
- `box-texture` (gabarit déplié de ScreenScraper) n'est pas utilisé : sa disposition varie selon les consoles et ne peut pas être vérifiée de façon fiable sans exemple consultable depuis le conteneur.
- Le scraping par lots (option « Faces du boîtier ») choisit les faces selon l'ordre des régions, sans manifeste des éditions ; la récupération depuis la visionneuse choisit l'édition de votre jeu et liste toutes les éditions.
- Le cache du texte des dos (`Application Support/NeoStation/BoxText`) n'a pas de rubrique dédiée dans l'analyse du stockage ; il est régénérable et n'est jamais supprimé automatiquement.
