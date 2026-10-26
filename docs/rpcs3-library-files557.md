# RPCS3 557 — suite de l'import des disques PS3 du dossier de bibliothèque (26 octobre 2026)

Demande du mainteneur après la livraison 554 : « je t'autorise à finir ce que
tu n'as pas corrigé. Il faut tout corriger. » La 554 laissait de côté deux
défauts relevés dans le même `app.log`. Sa relecture a montré en plus quatre
défauts du cycle de vie d'un disque du dossier de bibliothèque
(`roms/ps3/*.iso`) une fois installé par RPCS3.

## 1. Défauts corrigés

1. **Recherche** : refuser l'installation d'un disque depuis l'écran de
   recherche affichait la notification générique « Erreur lors du lancement
   du jeu ». La liste des jeux ne montrait déjà plus d'erreur dans ce cas
   (554).
2. **`UNIQUE constraint failed: user_rom_folders.path`** (journal de
   l'utilisateur) : deux sauvegardes de configuration lancées ensemble
   remplaçaient la table des dossiers sur la même connexion SQLite. Une
   transaction ouverte pendant qu'une autre l'est s'exécute dedans
   (`DatabaseAdapter.transaction`), donc les deux suppressions et les
   insertions s'entremêlaient, et la seconde insertion d'un même chemin
   échouait. Reproduit en test : trois sauvegardes simultanées.
3. **Supprimer un disque jamais installé** (ligne sans identifiant de titre)
   était impossible : « Invalid RPCS3 library entry. »
4. **Supprimer un disque installé** n'effaçait que la copie de RPCS3 :
   l'ISO restait dans `roms/ps3` et le scan suivant remettait le jeu dans la
   liste, à réinstaller.
5. **La suppression multiple PS3** (appui long) ne listait que les lignes
   pourvues d'un identifiant de titre : un disque jamais installé n'y
   figurait pas.
6. **Double occupation de l'espace** : RPCS3 démarre sa propre copie du
   disque (`DiscImages/<TITLE_ID>/disc.iso`), l'original restait dans le
   dossier. Le supprimer depuis Fichiers, comme le conseillait la note 554,
   faisait disparaître la ligne au scan suivant : temps de jeu, favori et
   dernière partie perdus, la ligne RPCS3 du titre revenant à zéro.

## 2. Corrections

* **Recherche** (`search_screen.dart`, fichier de l'interface 550) : aucune
  notification pour un lancement annulé (`GameLaunchResult.cancelled`).
* **Dossiers de ROM** (`sqlite_service.dart`, épinglé par le contrat de
  retour arrière Build 419) : les sauvegardes passent l'une après l'autre,
  dans l'ordre d'appel ; la liste est lue à l'appel ; un chemin présent deux
  fois n'est enregistré qu'une fois (`ConflictAlgorithm.ignore`, y compris
  pour une différence de casse sous `COLLATE NOCASE`). Une sauvegarde qui
  échoue rend son erreur sans bloquer les suivantes. La reconstruction exacte
  des octets 419 est ajoutée à `test/retroarch_baseline_scope_test.py`.
* **Disque installé dont le fichier est supprimé** : la ligne reste, liée au
  titre RPCS3, et se lance par son identifiant de titre :
  * le scan (`sqlite_database_service.dart`, épinglé 419 : deux blocs
    marqués `RPCS3_LIBRARY_FILE`, retirés par le contrat) garde sur iOS la
    ligne PS3 d'une `.iso` liée à un titre tant que le dossier qui la
    contenait existe ; un dossier disparu (conteneur déplacé, disque
    débranché) ou une ligne sans titre suit la règle commune ;
  * le lanceur ne demande plus le fichier d'une ligne PS3 dont RPCS3 détient
    le titre ;
  * la synchronisation RPCS3 (`settleLibraryFileRows`) relie une ISO
    renommée ou déplacée à son titre d'après son `PARAM.SFO`, fait passer
    temps de jeu, favori et dernière partie d'une ligne dont le fichier a
    disparu vers la ligne du même titre dont le fichier existe, réunit deux
    lignes sans fichier d'un même titre, et, lors d'une synchronisation
    réelle (pas depuis le cache), retire la ligne d'un titre que RPCS3 ne
    détient plus. Un dossier invisible (non monté, accès non accordé) ne
    prouve rien : ses lignes restent au scan.
* **Libérer l'espace** : la demande d'installation propose « Supprimer
  ensuite le fichier d'origine pour libérer {taille} » (« … et sa clé de
  disque … » si une clé est trouvée), **désactivé par défaut**. Coché,
  l'original et sa clé ne sont supprimés qu'après une installation réussie,
  le titre identifié et la ligne liée ; un refus de suppression laisse les
  fichiers en place, le jeu démarre quand même. La phrase « Le fichier reste
  dans votre dossier. » est retirée du texte de la demande (douze langues).
* **Supprimer le jeu** (réglages du jeu et suppression multiple) :
  `Rpcs3LibraryFileDeletion` supprime d'abord l'ISO (un refus laisse tout en
  place), puis sa clé `.dkey`/`.key` de même nom (une clé restée n'empêche
  pas la suite), puis, pour une ligne liée, l'installation RPCS3 du titre
  (sauvegardes, firmware et états conservés par RPCS3) et la ligne. La
  suppression multiple liste toutes les lignes PS3, repérées par leur chemin,
  et passe par la même suppression par jeu.

Non modifié : le Core RPCS3 (celui de la 551) et les ponts natifs. RPCS3
copie toujours le disque à l'installation : il faut toujours autant d'espace
libre que la taille du fichier pendant la copie.

## 3. Vérifications (sans iPhone)

* `test/rom_folders_concurrent_save_test.dart` (5) : trois sauvegardes
  simultanées sur la table de production (`UNIQUE COLLATE NOCASE`), ordre
  d'appel, doublons et casse, liste lue à l'appel, échec isolé.
* `test/rpcs3_library_file_rows_test.dart` (16) : scan (ligne gardée avec
  ses statistiques, lignes sans titre ou sans dossier retirées, comportement
  hors iOS inchangé), synchronisation (ISO renommée reliée et reprenant
  l'ancienne ligne, ligne sans fichier gardée, deux copies réunies, retrait
  en synchronisation réelle seulement, dossier invisible, disque non détenu),
  suppression (disque jamais installé, disque installé, disque déjà retiré,
  refus, clé verrouillée, libération d'espace et son refus).
* `test/rpcs3_library_file_service_test.dart` (18, dont 2 nouveaux) :
  l'original n'est supprimé qu'après l'installation, la liaison et la
  synchronisation, jamais sans la case ou après un refus de RPCS3.
* `test/rpcs3_library_file_dialog_test.dart` (19, dont 1 nouveau) : case
  décochée par défaut, texte avec ou sans clé, choix renvoyé.
* `test/rpcs3_library_file_route_contract_test.py` : garde du lanceur,
  ordre installation → liaison → synchronisation → suppression de
  l'original, ordre de suppression fichier → clé → installation → ligne,
  suppression multiple sur toutes les lignes, recherche.
* `test/retroarch_baseline_scope_test.py` : les deux fichiers SQLite
  reconstruits redonnent leurs empreintes 419 ; les 10 échecs déjà présents
  sur la base (`main.dart`, `system_content.dart`, 8 fichiers natifs
  `neoswap-storage`) sont inchangés.
* `flutter analyze` sur les fichiers modifiés : aucun problème.

Preuve locale `docs/evidence/rpcs3-library-files557-local.json`, produite sur
l'arbre 557 épinglé (`d645f05`) et sur l'arbre 554 livré, épinglé depuis le
même commit par la recette 554 :

* analyse de toute l'application : aucun avertissement ni erreur
  (108 informations, comme en 554) ;
* les tests ci-dessus, plus ceux de l'image disque (11), des dossiers de ROM
  (3) et de la bibliothèque RPCS3 (6) ;
* **suite Dart complète** sur les deux arbres, en série : 3 551 réussites sur
  l'arbre 557 contre 3 527 sur l'arbre 554 (les 24 tests ajoutés), et les
  mêmes 23 échecs, déjà présents sur l'arbre 554 (interface Dolphin et
  bibliothèque de lecture, `neo_glass_bubble`, deux contrats RPCS3 de la
  Build 231, etc.) ;
* contrat Build 419 : mêmes 10 échecs sur les deux arbres, aucun sur les deux
  fichiers SQLite ;
* contrôles négatifs sur l'arbre 554 : le test des sauvegardes simultanées y
  échoue sur `UNIQUE constraint failed: user_rom_folders.path`, et le contrat
  de routage 557 y échoue (« one guard for installed discs whose file is
  gone »).

Hors arbre épinglé, sur la branche entière : les 384 tests Python ont le même
résultat avec et sans le correctif (237 échecs historiques des deux côtés,
aucun écart).

## 4. Protocole iPhone

1. Un disque de `roms/ps3` jamais installé : le supprimer depuis les
   réglages du jeu ; il disparaît, sa clé aussi, et ne revient pas au scan.
2. Lancer un autre disque, cocher « Supprimer ensuite le fichier
   d'origine », « Installer et jouer » : le jeu démarre ; dans Fichiers,
   l'ISO et sa clé ont disparu de `roms/ps3` ; relancer RewindBox et le jeu :
   il démarre sans copie, temps de jeu conservé.
3. Supprimer ce jeu depuis les réglages : il quitte la liste et la
   bibliothèque RPCS3.
4. Depuis la recherche, lancer un disque non installé puis « Annuler » :
   aucune notification d'erreur.
5. `app.log` ne doit plus contenir `UNIQUE constraint failed:
   user_rom_folders.path`.
