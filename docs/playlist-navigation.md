# Navigation dans les playlists : saccades et jeu sauté

## Signalement (14 novembre 2026)

Vidéo du mainteneur (17 s), playlist Nintendo DS en vue liste, manette :
la navigation saccade et saute parfois un jeu.

Mesures faites sur la vidéo, image par image :

- Au premier passage sur un jeu, l'écran se fige pendant 120 à 370 ms,
  environ 50 ms après le pas. Aucune image ne change pendant ce temps.
  Au retour sur des jeux déjà vus (5 à 7 s), chaque pas défile sans à-coup.
- En maintenant la croix, deux gels complets surviennent : 550 ms à 12,8 s,
  puis 890 ms à 13,9 s.
- Après le second gel, la liste avance de deux jeux d'un coup, sans
  animation. Le joueur remonte ensuite d'un jeu.
- La lettre « K » du saut alphabétique s'affiche aussitôt après ce gel. Le
  saut alphabétique démarrait après 1,2 s de maintien, même si l'écran
  figé n'avait presque pas avancé.

## Causes retenues

1. **Saut d'un jeu.** La répétition de la croix (`GamepadNavigation`) avançait
   même quand l'écran n'avait pas affiché le pas précédent. Elle se
   déclenchait aussi quand la boucle d'événements avait été bloquée, avant
   le relâchement resté en file derrière elle. Le saut alphabétique se
   fondait sur la seule durée du maintien.
2. **Saccades.** À chaque pas, l'écran lançait aussitôt tout le travail du
   jeu sélectionné, en pleine animation de la liste :
   - le fond d'écran (image de 1920 px décodée, fondu et zoom de 512 ms sous
     le panneau flouté), y compris pour chaque jeu traversé en défilement
     rapide ;
   - la recherche RetroAchievements (empreinte, base, réseau) ;
   - la description localisée ;
   - l'écran TV.

   Pour chaque nouvelle ligne de la liste, la taille des jaquettes recto et
   tranche se lisait aussi en synchrone : jusqu'à 1 Mo par fichier, sur le
   fil de l'interface.

La part exacte de chaque cause dans les gels n'a pas été mesurée sur
l'iPhone.

## Changements

- **Répétition** (`lib/utils/gamepad_nav.dart`) :
  - une répétition attend l'image qui montre le pas précédent : jamais plus
    d'un pas d'avance sur l'écran ;
  - une répétition exécutée avec plus de 100 ms de retard attend encore
    120 ms, le temps qu'un relâchement en file arrive ;
  - le saut alphabétique demande, en plus des 1,2 s, au moins 10 pas faits
    (3 avec la cadence des menus).

  Sans gel, la cadence est inchangée.
- **Playlist** (`lib/screens/game_screen/my_games_list*`) : tant que la
  sélection bouge, seuls la surbrillance, le défilement et la capture du
  panneau de détails changent. Le fond de l'écran reste celui du jeu
  quitté. Une fois la sélection posée depuis 300 ms (600 ms pendant un
  saut alphabétique), le reste arrive en une fois : fond, description,
  RetroAchievements, écran TV, aperçu vidéo. Les jeux traversés ne sont
  plus chargés. Une description arrivée après un changement de jeu est
  désormais ignorée (la vérification comparait le jeu à lui-même).
- **Taille des jaquettes** (`GameBoxImageSize.of`) : lit d'abord 64 Ko,
  puis 1 Mo seulement si la taille n'y figure pas (JPEG avec un gros bloc
  EXIF ou ICC).
- **Journal** (`UiRefreshRateService`, `app.log`) : hors jeu, chaque image
  de 250 ms ou plus ajoute une ligne `UI long frame` avec sa durée totale
  et la répartition entre attente du fil de l'interface, construction et
  rendu GPU. Au plus une ligne par seconde, avec le nombre d'images longues
  non écrites. C'est ce qui permettra de situer sur l'appareil les gels qui
  resteraient.

## Vérification

- `test/gamepad_repeat_stall_test.dart` :
  - au plus un pas par image affichée, rien après le relâchement ;
  - la cadence est normale quand les images arrivent ;
  - un appui suivi d'un blocage de 500 ms, avec le relâchement en file, ne
    fait avancer que d'un jeu (2 avec l'ancien code) ;
  - un maintien long derrière un écran lent ne déclenche pas de saut
    alphabétique (2 avec l'ancien code).
- `test/playlist_settle_test.dart` : écran de playlist DS complet en vue
  liste. Pendant deux pas rapides, seul le fond du jeu quitté est présent.
  Une fois la sélection posée, c'est celui du jeu sélectionné, et le jeu
  traversé n'a jamais été chargé. Le test échoue avec l'ancien code.
- `test/game_box_image_size_header_test.dart` : taille lue au-delà de
  64 Ko, gros fichier à petit en-tête, PNG, JPEG sans en-tête de trame.
- `test/ui_long_frame_log_test.dart` : ligne écrite avec sa répartition,
  limitée à une par seconde.

Aucune mesure sur iPhone : l'effet sur les gels reste à observer sur
l'appareil, avec les lignes `UI long frame` du journal.
