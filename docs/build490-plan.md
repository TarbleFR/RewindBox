# Build 490 — boîtiers 3D de la vue Jaquette, lecture du dos en douze langues et ouverture au lancement, 19 octobre 2026

Demande du mainteneur (19 octobre 2026) : enrichir la vue Jaquette d'un boîtier en volume adapté à la console et au support, manipulable à 360°, dont le dos se lit dans les douze langues de NeoStation (scan localisé quand il existe, sinon reconnaissance et traduction), qui s'ouvre sur sa cartouche ou son disque au lancement, avec récupération des médias étendue, cache hors ligne et une IPA testable par le processus existant. Précision en cours de cycle : « Il faut que les jaquettes soient réalistes. Des vraies jaquettes de PlayStation 1, pour exemple. Et ainsi de suite. » Branche `Claude`, aucune release GitHub.

Conception, sources, réglages et limites : [`game-box-3d.md`](game-box-3d.md).

## 1. Périmètre

Fichiers produit :
- nouveaux : `lib/services/game_box/` (profils, régions, médias et manifeste, récupération, préférences, mise en page et service de lecture), `lib/widgets/game_box/` (géométrie, scène, surfaces, carte, sélecteur de langue, chargeur d'images), `lib/screens/game_box/` (visionneuse, lecture du dos), `lib/l10n/game_box_locale.dart` (généré, 106 textes × 12 langues), `packages/neo_box_reader/` (plugin Swift : Vision, NaturalLanguage, Translation ; lié statiquement) ;
- modifiés : `lib/screens/game_screen/my_games_carousel.dart` (style « Boîte » seulement), `lib/services/screenscraper/media_resolver.dart` (trois dossiers), `lib/services/screenscraper/media_downloader.dart` (téléchargement validé réutilisable), `lib/services/screenscraper_service.dart` (`mediaJeuUri`), `lib/repositories/game_repository.dart` (suppression des faces avec les médias du jeu), `lib/screens/scraper_screen/scraper_contents/media_content.dart` et `new_scraper_options_screen.dart` (option « Faces du boîtier »), `lib/utils/artwork_cache.dart` (rechargement des faces après un scraping), `pubspec.yaml` (paquet de l'espace de travail).

Inchangés : les dix fichiers de bibliothèque verrouillés sur la 419 (dont `scraper_repository.dart`), les vues Liste et Grille, le carrousel « Fanart », le lancement (`launch_flow.dart`, `game_launch_utils.dart`, `game_launch_service.dart`), tous les moteurs, cœurs et helpers.

## 2. Vérifications

⟪résultats CI⟫

## 3. Limites

Voir [`game-box-3d.md`](game-box-3d.md) § 10. Aucune validation sur iPhone ou iPad ; la traduction réelle n'est pas exécutée en CI ; la vidéo de référence n'a pas pu être consultée.

## 4. Livraison

⟪livraison⟫

## 5. Protocole sur iPhone

1. Bibliothèque PS1, vue Carrousel, style de carte « Boîte » : boîtier cristal en volume, tranche visible ; glisser change de jeu.
2. Toucher le boîtier centré : visionneuse. Tourner à 360°, incliner, pincer, déplacer en zoom ; « Face avant », « Dos », « Position initiale ».
3. « Récupérer les faces du boîtier » (compte ScreenScraper connecté) : dos, tranche, disque ; vérifier l'édition annoncée et la région de votre jeu.
4. « Langue » : choisir une langue avec un scan publié (icône), puis une sans scan ; « Lire la jaquette » : texte reconnu, traduction (iOS peut proposer de télécharger la langue), « Texte d'origine », taille du texte, scan en plein écran ; recommencer en mode Avion.
5. « Jouer » : ouverture, disque dans son logement, lancement unique malgré des appuis répétés ; essayer aussi une cartouche (NES, SNES, N64), une carte (DS, 3DS), un jeu PS2 avec BIOS manquant (le dialogue habituel doit apparaître), « Réduire les animations » activé, puis l'animation désactivée dans les options du boîtier.
6. Portrait, paysage, iPad ; texte agrandi (Réglages › Accessibilité).
