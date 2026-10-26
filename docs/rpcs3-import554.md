# RPCS3 554 — import des jeux PS3 du dossier de bibliothèque (26 octobre 2026)

Signalement transmis par le mainteneur : « Apparemment, RPCS3 a un problème
lors de l'import des jeux », avec le `app.log` d'un autre utilisateur
(conteneur `20C07790-…`, puis `D4871C5C-…` après une réinstallation).

## 1. Faits (journal)

* Firmware PS3 4.93 installé sans erreur par la porte RPCS3
  (`RPCS3 firmware installed successfully: 4.93`).
* La bibliothèque RPCS3 ne reçoit aucun jeu : à chaque démarrage
  `Rpcs3LibraryService: reconciled 0 live PS3 game(s)`, et aucune ligne
  d'import ni de synchronisation RPCS3.
* L'ISO `Call of Duty - Black Ops (USA) (En,Fr) 2.iso` est copiée dans
  `Documents/roms/Ps3/`, puis renommée et déplacée vers `Documents/roms/ps3/`.
  Le scanner de la bibliothèque la trouve (`SystemGamesList: Loaded 1 games for
  ps3`).
* Ses **20 lancements**, de 04:48 à 15:21, finissent tous ainsi :

  ```
  RetroArchLaunch attempt=… stage=cacheEmpty
  romPath=…/Documents/roms/ps3/Call of Duty - Black Ops (USA) (En,Fr).iso
  No persisted RetroArch export is available. Synchronize the library.
  [E] SystemGamesList: Game launch failed
  ```

## 2. Cause

Sur iOS, `GameLaunchService` n'envoyait une ligne PS3 à RPCS3 que si elle
portait un identifiant de titre (`isRpcs3VirtualRom || titleId non vide`).
Seules les lignes créées par la bibliothèque RPCS3 en ont un ; une ISO trouvée
par le scanner dans `roms/ps3` n'en a jamais. Elle continuait donc vers la
route générique iOS, celle de l'application RetroArch, qui ne lance aucun jeu
PS3 et répond qu'aucune bibliothèque RetroArch n'est synchronisée. RPCS3
n'était jamais appelé : il ne démarre que les titres installés dans sa
bibliothèque privée (`rpcs3_ios_boot_game` exige un titre installé), et rien
ne lui proposait d'installer ce fichier.

Lacunes associées :

* une clé de disque Redump `.dkey` choisie avec son ISO dans le menu
  « Importer des jeux » était refusée comme « unsupported game format », et la
  clé voisine n'était cherchée qu'en `.key` ;
* le motif d'un refus d'import RPCS3 n'allait que dans une notification, jamais
  dans `app.log` : le journal ne pouvait pas dire pourquoi un import échouait.

## 3. Correction (Dart seulement ; Core 551 et plugins inchangés)

* **Routage** : sur iOS, toute ligne PS3 prend la branche RPCS3, qui renvoie
  sur chaque chemin ; aucune ligne PS3 n'atteint plus RetroArch. La politique
  des moteurs intégrés est toujours consultée en premier.
* **Disque du dossier de bibliothèque** (`.iso` sans titre installé dans
  RPCS3, `Rpcs3LibraryFileService`) :
  * `PS3_GAME/PARAM.SFO` est lu sur place dans l'arbre ISO 9660
    (`Rpcs3DiscImage`), sans copie ;
  * si RPCS3 a déjà ce titre (même identifiant, ou à défaut même image : taille
    et premier Mio identiques), la ligne est liée à ce titre et le jeu démarre ;
  * sinon une boîte de dialogue dit que RPCS3 lance les jeux depuis sa propre
    bibliothèque, que le fichier (nom, taille) y sera copié et qu'il faut autant
    d'espace libre ; elle cite le disque et la clé trouvée. « Annuler » arrête
    sans message d'erreur ;
  * « Installer et jouer » : l'import validé de RPCS3 lui-même
    (`installIso`, avec la clé `.dkey` ou `.key` de même nom), sous une
    progression non fermable, écran maintenu allumé ; puis la ligne est liée au
    titre installé (favori, temps de jeu et dernière partie d'une ligne RPCS3 du
    même titre reportés), la bibliothèque est synchronisée et le jeu démarre ;
  * sans firmware PS3, rien n'est copié et l'utilisateur est renvoyé vers
    l'étape du firmware ; les refus de RPCS3 (espace libre, clé manquante,
    image tronquée) sont traduits, le message exact de RPCS3 restant en détail
    technique.
* **Menu « Importer des jeux »** : `.dkey` reconnu comme clé de disque, choisi
  ou voisin ; chaque fichier choisi, sa clé et le résultat de RPCS3 sont
  journalisés (`RPCS3 import: …`).
* Textes en 12 langues (`Rpcs3LibraryFileLocale`).
* Le fichier d'origine reste dans `roms/ps3` (RPCS3 en garde sa copie) ; le
  supprimer depuis Fichiers libère l'espace, la ligne RPCS3 du titre reprend
  alors sa place.

Non modifié : la notification de l'écran de recherche (interface 550 figée)
affiche l'erreur de lancement générique si l'on refuse l'installation depuis
la recherche. L'erreur `UNIQUE constraint failed: user_rom_folders.path` du
même journal vient de deux sauvegardes de configuration simultanées sur la
même connexion SQLite (reproduite en test) ; `sqlite_service.dart` est figé par
le contrat de retour arrière Build 419, elle n'est donc pas corrigée ici.

## 4. Vérifications (sans iPhone)

* `test/rpcs3_disc_image_test.dart` (11) : lecture de `PARAM.SFO` au-delà du
  remplissage d'un secteur de répertoire, noms sans casse ni version, image
  sans `PS3_GAME`, descripteur illisible (région chiffrée), extent hors image,
  clés `.dkey`/`.key`, même image. Le lecteur lit aussi trois ISO standard
  produites par pycdlib (niveau 1, Joliet + Rock Ridge, niveau 4 ; répertoire
  `PS3_GAME` de 5 secteurs).
* `test/rpcs3_library_file_service_test.dart` (16) : liaison sans copie, image
  identique, plan (taille, identité, clé), installation et liaison, titre
  ajouté ou réinstallé, refus RPCS3 classés, JIT indisponible, titre non
  identifié ; liaison SQLite avec report des statistiques une seule fois ; les
  lignes du journal passent le masquage des secrets (`discKey=`).
* `test/rpcs3_library_file_dialog_test.dart` (18) : 12 langues complètes,
  textes de la demande et de la progression, Annuler/Installer, progression
  suivant RPCS3, écran maintenu puis rendu.
* `test/rpcs3_library_file_route_contract_test.py` : ordre politique →
  résolution → session → démarrage, branche PS3 sans RetroArch et terminée par
  un retour, annulation sans erreur.
* `flutter analyze` : aucun avertissement ni erreur (108 informations, comme
  avant). Les échecs déjà présents sur la base sont inchangés.

## 5. Protocole iPhone

1. Placer une ISO PS3 dans `Sur mon iPhone › RewindBox › roms › ps3` (et sa
   clé `.dkey` de même nom pour une image Redump chiffrée), relancer le scan.
2. Lancer le jeu : la demande d'installation apparaît ; « Installer et jouer ».
3. Le jeu doit démarrer dans RPCS3 ; un second lancement démarre sans copie.
4. En cas d'échec, `app.log` contient désormais les lignes
   `RPCS3 library file: …` avec la raison exacte donnée par RPCS3.

## 6. Livraison privée 554 (26 octobre 2026)

- Recette : `.github/workflows/rpcs3-import554-delivery.yml`,
  `.github/diagnostics/rpcs3import554_tree.py` et `rpcs3import554_delivery.py`,
  `build-utils/validate_rpcs3_import554_ipa.py`, `validate_liquid_glass554_ipa.py`,
  `validate_melonx_parity554_ipa.py`, clé publique
  `build-utils/delivery-554-rpcs3-recipient.pem` (clé privée hors dépôt).
- Arbre : celui de la 553 livrée, plus les seuls fichiers du correctif
  `410678b` (8 fichiers Dart livrés, communs à aucune version précédente).
  Remis à leur version 553, ces fichiers redonnent exactement l'arbre de l'IPA
  553 (`lib` `4ac259a9`) ; les reçus 550, 552 et 553 restent donc liés tels
  quels. Le Core RPCS3 est celui de la 551 (même `libRPCS3Core.dylib` que dans
  les IPA 552 et 553).
- Run `40360743251` (push `9f6892b`) : `checks` (analyse, 494 tests sur l'arbre
  épinglé) et `cold` réussis du premier coup, avec la validation de l'import
  554 dans l'IPA signée (reçu, constantes compilées de la demande et de la
  progression, textes traduits).
- Artefact chiffré `12667899580` (188 592 541 octets, archive SHA-256
  `d2975fb62df35868f1e5a0e061d07be7539059cbc0d3fe4f7dac48e5d9ecc480`), déchiffré
  en local : IPA **0.0.8 (554)**
  `RewindBox-Build554-9f6892b9422aa584e4949680adaa01180458c401-cold.ipa`,
  **188 012 202 octets**, SHA-256
  **`51d8024e3b423390a379eb47bb0a859545a28e886619251f989fd8f723d4f2b4`**, égale à
  `SHA256SUMS` et à `signed-payload-identity.json`. Reçu :
  `docs/evidence/rpcs3-import554-delivery.json`. Remise à l'utilisateur pour
  re-signature SideStore. Aucune validation sur iPhone. **Ne pas réutiliser le
  numéro 554.** Numérotation suivante annoncée par les sessions : 555 = Cell
  RPCS3, 556 = mesure MeloNX.
