# Imports, dossiers de bibliothèque et messages de prérequis (11 novembre 2026)

Demandes du mainteneur, 11 novembre 2026 :

- « Corrige ce dernier bug côté utilisateur. Un utilisateur a un crash lorsque il essaye d'importer ces jeux
  retroarch. »
- « Vérifie chaque fonctionnalité d'imports et corrige les si tu trouves des erreurs. Si un import échoue il faut
  que l'utilisateur sache pourquoi, exemple : mauvais dossier ou non de dossier »
- « Simplifie l'import si c'est trop compliqué pour l'utilisateur, ont dois pouvoir distinguer qu'elle jeu vas dans
  qu'elle playliste »
- « Si tu introduit un nouveau mécanisme et tu ne dois pas casser les bibliothèques déjà importer par les joueurs ou
  importer manuellement depuis les playlist »
- « Met des messages d'erreurs également la ou l'utilisateur fais mal les choses, exemple : Pas de bios, manque les
  entiltments etc... »

Statut : écrit, testé sur Linux (tests Dart et contrats Python), les deux ponts natifs modifiés compilés avec le SDK
iPhone par la CI (runs `42966944007` et `42966947262`). **Rien n'a été observé sur un iPhone.** Livraison prévue :
IPA 725.

## 1. Le bug du testeur (dossier RetroArch)

Journal fourni : aucune ligne d'erreur ni de plantage ; le parcours lit seulement des noms et des tailles. La cause
d'un arrêt de l'application n'est donc **pas prouvée**. Défauts réels trouvés et corrigés sur ce parcours :

- un échec natif du sélecteur de dossier était présenté comme une annulation ; une sélection pouvait rester en
  attente pour toujours (le bouton restait inactif) ;
- un dossier lié perdu après un déplacement du conteneur faisait disparaître ses jeux de la bibliothèque ;
- « Ajouter un dossier de ROM » ne faisait rien de visible sur iOS.

Si l'arrêt se reproduit avec l'IPA 725, il faut le rapport `.ips` de l'iPhone (Réglages › Confidentialité ›
Analyse › Données d'analyse) en plus du journal.

## 2. Dossiers de bibliothèque : quel jeu va dans quelle playlist

Avant d'ajouter un dossier, RewindBox affiche ce qu'il y lira : chaque dossier de console et la playlist qu'il
alimente (avec des exemples de jeux), puis ce qui est laissé de côté et pourquoi (dossier au nom inconnu avec la
console suggérée, jeux posés à la racine, consoles dont les jeux restent dans le stockage de RewindBox sur iOS :
GameCube, Wii, PS2). Un dossier sans aucun dossier de console le dit, avec des noms réels ; le dossier d'**une**
console choisi à la place de celui qui le contient (« gba ») dit quel dossier choisir.

Ce qui reste comme avant (rien n'est retiré) : les dossiers déjà enregistrés, le lien unique de la carte RetroArch,
les jeux déjà indexés et les imports faits depuis les playlists. Un dossier qu'iOS ne rend pas au lancement garde
ses jeux et le dit ; l'ajouter de nouveau rétablit l'accès.

## 3. Chaque import dit pourquoi un fichier est refusé

| Import | Ce qui est dit |
| --- | --- |
| Consoles rétro (et déplacement d'une bibliothèque) | type refusé avec les types acceptés, fichier vide, illisible, espace insuffisant, pistes d'un .cue/.m3u absentes ou non copiées, fichier iCloud non téléchargé ; un déplacement de rien ne retire plus aucun dossier |
| GameCube / Wii / PS2 | chaque fichier refusé et sa raison ; « déjà dans la bibliothèque » seulement si le **contenu** est identique (deux images GameCube de même nom et même taille ne sont plus confondues) ; un nom pris n'est jamais écrasé |
| PS3 | type refusé avec les types acceptés, clés de disque sans le jeu, dossier qui n'est pas un jeu décrypté (avec ce qui lui manque), liste complète des refus dans un rapport au-delà de cinq ; un jeu installé dont l'actualisation de la liste a échoué n'est plus présenté comme un échec |
| Switch | type refusé avec les extensions acceptées, fichier vide ou illisible, disque plein, texte du système pour une copie échouée, diagnostic natif conservé |

## 4. Prérequis manquants au lancement

Une phrase par prérequis, en 12 langues, qui dit ce qui manque puis quoi faire :

| Prérequis | Moteurs |
| --- | --- |
| LocalDevVPN non connecté | PS2, PS3, GameCube/Wii, Switch |
| Pairing File absent, illisible ou non choisi | idem |
| Installation signée sans `get-task-allow` (le JIT ne peut jamais s'activer) | idem |
| iOS antérieur à 17.4 | idem |
| BIOS PS2 absent (avec l'action d'import de la liste PlayStation 2) ou non choisi | PS2 |
| BIOS que seuls certains jeux demandent (Mega-CD, Famicom Disk System, PC Engine CD, Neo Geo…) | consoles rétro, nommé quand le cœur a refusé le jeu |

Les entitlements mémoire de MeloNX avaient déjà leur phrase. Le texte technique reste dans les détails et le
journal ; une erreur inconnue garde son ancien texte.

## 5. Revues

Chaque lot délégué a été relu par un agent indépendant ; les défauts confirmés ont été corrigés avant toute
livraison, dont une régression : « déjà dans la bibliothèque » comparait nom et taille, ce qui aurait empêché
d'importer un second jeu GameCube nommé `game.iso`.

## 6. Livraison

Trois fichiers modifiés portent encore, en dessous, le travail RetroAchievements différé depuis la 611 (`b06888a9`).
Comme en 615, les sept commits concernés sont classés « source seulement » et leur changement est réappliqué par un
commit revu qui part des octets compilés par la 724 (fusion sans conflit, sans les lignes différées), puis les lignes
différées sont remises : l'arbre final est identique à l'arbre d'avant ces trois commits.
