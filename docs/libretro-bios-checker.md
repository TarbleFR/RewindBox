# Vérificateur de BIOS des cœurs libretro intégrés (Build 438)

Paquet E de `docs/build438-plan.md`. Réglages › Outils › « Vérificateur de
BIOS » (iOS uniquement, quatrième ligne de l’onglet Outils) ouvre
`lib/screens/libretro/libretro_bios_checker_screen.dart`. La page indique,
pour chaque console du moteur intégré, les fichiers que lisent ses cœurs, où
ils sont attendus, ce qui a été trouvé et si la somme de contrôle correspond à
un dump publié.

Rien n’a été vérifié sur iPhone à ce stade : les comportements ci-dessous sont
établis par les sources et par des tests sur Windows, et les contrôles des
binaires épinglés s’exécutent sur macOS CI.

## Références

Toutes les données sont dans `assets/data/libretro_bios_requirements.json`
(tailles et sommes de contrôle publiques, jamais d’octets de BIOS) :

- `libretro-core-info` `5a74858ab2f7a50cebb5a6330895bc38899531c0`
  (lignes `firmwareN_*` et md5 des `notes` des 14 fichiers `.info`) ;
- `libretro-database` `dat/System.dat` `f206bf65` (v1.19.0) ;
- documentation libretro (`docs.libretro.com/library/<cœur>`) ;
- sources des cœurs au dernier commit précédant l’artefact épinglé
  `LibretroCores-48635465…` (run `37945318237`) : `identity.json` n’enregistre
  pas de commit source, d’où le contrôle des binaires sur CI.

Une copie publique et réduite de ces références est versionnée dans
`test/fixtures/libretro_bios/core_info_5a74858a.json`.

## Fonctionnement

- **Lecture seule.** Le service `lib/services/libretro_bios_check_service.dart`
  ne crée, ne renomme, ne déplace et ne supprime rien dans System, Saves,
  Config ou les bibliothèques. Sa seule écriture est son cache
  `Library/Caches/Libretro/bios-check-v1.json` (clé : dossier + chemin relatif,
  validité : taille et date de modification).
- **Noms exacts.** Les noms sont comparés à partir des listes de dossiers,
  jamais par `File.exists`, comme sur le système de fichiers sensible à la
  casse d’iOS (Windows et macOS ne le sont souvent pas).
- **Hachage en arrière-plan.** MD5, SHA-1 et SHA-256 dans un isolate
  (`Isolate.run`), une seule fois par taille et date ; membres des archives
  ZIP lus dans le répertoire central, sans décompression.
- **Emplacements.** Ceux des cœurs, dans leur ordre : racine de System,
  sous-dossiers (`fbneo/`, `fbneo/patched/`, `Mupen64plus/`, `PPSSPP/`),
  dossier des jeux (Snes9x pour BS-X/Sufami Turbo, FBNeo). Le dossier des jeux
  est celui des jeux qui ont besoin du fichier ; sans tel jeu, ceux des jeux du
  système et les dossiers de console des bibliothèques enregistrées. Un
  fichier mal placé (autre dossier de System jusqu’à 3 niveaux, autre casse,
  autre dossier de jeux, ou même somme de contrôle sous un autre nom) est
  signalé : « trouvé à X, le cœur lit Y ».
- **Options de cœur.** Les fichiers lus seulement avec une option
  (`genesis_plus_gx_bios`, `genesis_plus_gx_lock_on`,
  `desmume_use_external_bios`, `beetle_psx(_hw)_override_bios`,
  `gambatte_gb_bootloader`, `mgba_use_bios`, `mgba_gb_model`) indiquent si
  l’option est active, d’après `Config/*.json` (`values`) ou la valeur par
  défaut du cœur.

## Statuts et niveaux

- Vérifié (badge vert avec coche) : taille et MD5 ou SHA-1 d’un dump connu ;
  pour un jeu FBNeo, chaque membre utilisé trouvé par CRC ; pour PPSSPP, copie
  identique à celle fournie (`Runner.app/Libretro-native-identity.json`).
- Présent, non vérifié : somme de contrôle inconnue, autre révision, ou
  fichier d’une autre entrée (le nom de cette entrée est indiqué).
- Manquant (obligatoire), Manquant (optionnel).
- Inutilisable, seulement sur preuve tirée des sources : fichier vide ou
  illisible, plus court que ce que lit le cœur (BS-X 1 Mio, STBIOS 256 Kio,
  boot ROM Game Boy), en-tête refusé (TMSS « GENESIS OS » à 0x120, Sufami
  Turbo, premier mot de l’IPL 64DD), fichier `.zip` qui n’est pas une archive
  ZIP, archive Neo Geo sans `sm1.sm1` ni `000-lo.lo` dans aucune copie
  vérifiable (une copie `fbneo/patched` n’est jamais déclarée invalide).

Un BIOS conditionnel (Mega-CD, FDS, BS-X, Sufami Turbo, 64DD, Neo Geo,
Neo Geo CD) n’est « obligatoire » que si la bibliothèque contient des jeux du
système concerné ; sinon il est « optionnel » avec la condition affichée.
Pour le Mega-CD, les étiquettes de région des noms de fichiers (`(USA)`,
`(Europe)`, `(Japan)`…) désignent le BIOS de la région ; un disque sans
étiquette rend les trois régions obligatoires tant qu’aucune n’est présente.
Les BIOS des cartes d’arcade (PGM, Super Kaneko Nova System, etc.) restent
optionnels : la bibliothèque ne permet pas de reconnaître leurs jeux.

« Aucun BIOS externe requis » s’affiche pour 32X et SG-1000 ; les autres
consoles portent une note propre (cartouches, logo de démarrage, options Sega,
DeSmuME, PPSSPP fourni, Azahar).

## PlayStation

La règle de lancement de NeoStation ne change pas : un des noms exacts
`scph5500.bin`, `scph5501.bin`, `scph5502.bin` dans System
(`LibretroCore.biosAnyOf`). Le vérificateur la rapporte telle quelle :

- sans aucun de ces noms, la console n’est pas prête et chaque ligne de
  région manquante est obligatoire (« un seul de ces fichiers suffit ») ;
- un nom que Beetle accepte mais pas NeoStation (`SCPH5501.BIN`,
  `scph7003.bin`, ou un fichier trouvé par la somme de contrôle) est vérifié,
  avec l’indication de renommage ;
- une fois la règle remplie, les autres régions sont « recommandées » :
  Beetle démarre alors leurs disques avec OpenBIOS. Cette affirmation dépend
  du drapeau `flags.beetleOpenBiosFallback` du JSON, confirmé sur CI par le
  mode `--cores` (valeur d’option `openbios` présente dans les deux binaires
  épinglés). Sans ce repli, une région dont la bibliothèque a des disques
  redevient obligatoire.

## Exclusions motivées

- FBNeo : `coleco`, `fdsbios`, `msx`, `ngp`, `spectrum`, `spec128`,
  `spec1282a`, `channelf` — NeoStation n’envoie jamais ces consoles à FBNeo
  (FBNeo ne sert qu’à `arc`, `fbneo`, `cps1-3`, `neogeo`).
- Genesis Plus GX Wide : BIOS Mega-CD, Master System et Game Gear — ce cœur
  ne sert qu’à la Mega Drive dans NeoStation.

## Rafraîchissement et import

Nouvelle vérification à l’ouverture, sur « Vérifier à nouveau », au retour de
l’app au premier plan (fichiers ajoutés dans Fichiers), quand les dossiers de
bibliothèque enregistrés changent et après l’import. Le seul lien d’import est
le flux existant « Copier les sauvegardes et BIOS de RetroArch »
(`LibretroInternalService.copyRetroArchData`), suivi d’une vérification.

Un BIOS optionnel manquant ne bloque jamais un lancement : le vérificateur
n’ajoute aucune règle de lancement.

## Traductions

98 clés `bios*` ajoutées à la fin des douze cartes de `LibretroLocale`
(en, fr, de, es, it, pt, ru, id, ja, ko, zh, zh_Hant). Les noms de produits,
fichiers, chemins, options et sommes de contrôle restent bruts, sous des
libellés traduits.

## Tests

- `test/libretro_bios_check_service_test.dart` : statuts, conditions et
  régions, PlayStation (alias, recherche par somme de contrôle, règle de
  lancement, OpenBIOS), emplacements et casse, validateurs, jeux FBNeo,
  options de cœur, PPSSPP, cache, absence d’écriture, cœurs absents,
  isolate.
- `test/libretro_bios_launch_test.dart` : lancement inchangé (BIOS optionnel
  absent, règle PS1 identique et cohérente avec le vérificateur).
- `test/libretro_bios_checker_screen_test.dart` : résumé, badge vert,
  filtres, console présélectionnée, vérification à nouveau, retour au premier
  plan, changement de dossiers, import RetroArch, échec, entrée Outils
  (4 sur iOS, 3 ailleurs).
- `test/libretro_bios_catalog_test.dart` : données, exclusions, clés et
  paramètres des douze langues, chinois traditionnel.
- `test/libretro_bios_requirements_test.py` : sans argument, contrat avec
  core-info et System.dat (toute plateforme) ; avec `--cores dist/libretro`,
  contrôle des binaires épinglés (macOS CI).

Les contrats « Outils = 3 éléments » de
`test/jit_backend_preference_service_test.dart` et
`test/neoplay_build397_integration_test.py` sont remplacés par le nouveau
comportement : 3 outils partout, le vérificateur en quatrième sur iOS,
jamais NeoPlay.

## À confirmer sur iPhone

Affichage du dossier Libretro › System dans Fichiers et sensibilité à la
casse ; refus réel des disques Mega-CD, FDS, BS-X/Sufami Turbo, 64DD sans BIOS
et démarrage avec ; démarrage PS1 sous OpenBIOS avec le binaire épinglé ;
`neogeo.zip` lu à côté des jeux dans une bibliothèque externe ; durée de la
première vérification et d’une vérification en cache ; navigation à la manette
dans les filtres et les cartes ; rafraîchissement après modification dans
Fichiers ; lecture de `Libretro-native-identity.json` depuis
`Platform.resolvedExecutable`.
