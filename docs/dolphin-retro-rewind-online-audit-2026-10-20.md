# Mario Kart Wii en ligne (Retro Rewind + Retro WFC) avec le Dolphin intégré de NeoStation — audit en lecture seule, 20 octobre 2026

Demande du mainteneur du 20 octobre 2026 : « Reprendre l'audit » (Dolphin + Retro Rewind en ligne, lecture seule, aucun changement du cœur Dolphin sans accord). Périmètre : branche `Claude` (`740a3fc5`), cœur Dolphin verrouillé (identité Build 350 : DolphiniOS `7cac5416`, `DolphinCore` SHA-256 `7129d9c6…3aa2d`). Aucun fichier du dépôt modifié, aucun commit, aucun workflow. Aucune donnée de jeu téléchargée.
Notation : **[D]** démontré par une source ou le binaire lus ; **[I]** déduit ; **[?]** inconnu.

## 1. Conclusions

1. **Riivolution est dans le cœur verrouillé, mais NeoStation ne peut pas l'utiliser sans changer le cœur.**
   - [D] Le code Riivolution amont complet est compilé et même exporté par `DolphinCore` : parseur, patcher, descripteur `.json`, redirection des sauvegardes.
   - [D] Le blocage vient du pont NeoStation, compilé dans `DolphinCore` (`build-utils/patch_dolphin_internal_core_v2.py`, l. 443-476 et 551-628) :
     - `neostation_dolphin_validate_image` exige que `DiscIO::CreateVolume(path)` ouvre une vraie image Wii ;
     - `DOLLaunch` relance exactement ce chemin avec `BootParameters::GenerateFromFile(path)`, sans correctifs ;
     - un descripteur `dolphin-game-mod-descriptor` (`.json`, la méthode de WheelWizard) est donc refusé à la validation ;
     - aucun réglage INI n'applique Riivolution lors d'un démarrage normal.
   - [I] Le changement nécessaire est petit et se fait dans le seul pont NeoStation (Dolphin amont inchangé). Il crée pourtant un nouveau binaire `DolphinCore` : **l'accord du mainteneur est nécessaire**.
2. **Le réseau ne demande rien de plus au cœur.** [D] Ce qui suit est déjà en place, dans le cœur ou dans le pack :
   - émulation réseau IOS compilée (`WiiSockMan`, mbedTLS) et `/dev/dolphin` avec les IOCTL 0x01 à 0x0A qu'utilise Pulsar ;
   - configuration réseau Wii par défaut créée automatiquement (filaire, DHCP) ;
   - redirection vers `http://nas.play.rwfc.net` faite par le code du pack lui-même : pas de DNS, pas de certificat SSL ;
   - le serveur Retro WFC accepte la NAND et les clés Dolphin par défaut (identifiant d'appareil `0x0403AC68`) : **aucune NAND de console réelle n'est nécessaire**.
3. **La base du cœur est ancienne pour un usage en ligne.**
   - [D] `7cac5416` repose sur Dolphin **2509** : dernier tag amont fusionné le 20 septembre 2025, et `master` de DolphiniOS n'a pas avancé depuis.
   - [D] Il lui manque les correctifs de sécurité de **2606a** : validation de `DolReader`, GCZ, `sockaddr` mis à zéro dans `NetIPTopDevice`, bornes DSPHLE.
   - [D] WheelWizard, le lanceur de référence, bloque par défaut tout Dolphin antérieur à 2606a ou au build de développement 2606-300. Le joueur peut passer outre (« Play anyway »).
   - [D] Le serveur Retro WFC ne reçoit que la chaîne `"Dolphin"` et ne contrôle aucune version.
   - [I] Mettre à niveau la base est recommandé avant tout jeu en ligne, mais c'est un chantier lourd du cœur.
4. **Distribution du pack.**
   - [D] Le code de Retro Rewind est sous GPLv3. Pulsar et les parties reprises de mkw-sp sont sous MIT.
   - [?] Les éléments du pack (pistes, musiques, `Assets`) n'ont aucune licence publiée.
   - [I] NeoStation ne doit pas réhéberger le pack. Un téléchargement direct depuis le CDN officiel, comme le fait WheelWizard, demande l'accord écrit de l'équipe Retro Rewind. À défaut, le joueur importe lui-même l'archive officielle.
5. **Version et accès aux sources.**
   - [D] Version épinglée le 19 octobre : 6.13.3 (`migration-target.json`, retiré au commit `21f8b3a3`).
   - [?] Le flux `update.rwfc.net` est refusé par la politique réseau de la session, comme `rwfc.net`, `mkwiiki.org`, `wiki.tockdom.com`, `www.retrorewind.page` et `wiimmfi.de` : version non revérifiée le 20 octobre.
6. **Wiimmfi (jeu original).**
   - [I] Techniquement possible sans changer le cœur, si le joueur fournit une image déjà patchée par l'outil Wiimmfi et sa NAND réelle (`keys.bin`), que NeoStation sait importer.
   - [I] NeoStation ne devrait ni patcher le jeu ni distribuer le patch.
   - [?] Les exigences actuelles de Wiimmfi n'ont pas pu être vérifiées (site bloqué).

## 2. Preuves

### 2.1 Binaire verrouillé

Récupéré par `fetch_native_donor_subset.py` (2 698 membres, aucun membre KartPad demandé).

- Identité : `DolphinCore` 22 342 192 octets, SHA-256 `7129d9c654fb6d28f2fa92ae1a4c14d1f25a1fc3e87788237676b48a0fb3aa2d`, égal à `DOLPHIN_SHA` de `build-utils/prepare_fast_native_runtime.py` ; UUID `AC5C18E7-8FD6-3BB0-A82D-EE31F5ED3AC5`, SDK iOS 18.5.
- Le trie d'exports contient 21 265 symboles, dont :
  - `BootParameters::GenerateFromFile` (deux surcharges) ;
  - `AddRiivolutionPatches(BootParameters*, vector<Riivolution::Patch>)` ;
  - `DiscIO::Riivolution::GenerateRiivolutionPatchesFromConfig` et `GenerateRiivolutionPatchesFromGameModDescriptor` ;
  - `DiscIO::ParseGameModDescriptorFile` et `BootManager::BootCore` ;
  - `ApplyGeneralMemoryPatches`, `ApplyApploaderMemoryPatches`, `ExtractSavegameRedirect` ;
  - les chaînes « Riivolution memory patch overlaps… ».
- En revanche, `DOLLaunch` et l'état du lancement (`g_running`, `g_validated_game`) sont locaux (`t`). Le pont Objective-C++ (lié par `-framework DolphinCore`) pourrait appeler ces fonctions C++ directement, mais il contournerait les portes strictes : JIT, Metal, `g_running`. Menu, pause, arrêt et états ne fonctionneraient plus. **Cette voie est écartée.**
- La pile réseau est présente : symboles `IOS::HLE::WiiSockMan::*` et 183 symboles `mbedtls_ssl*`.

### 2.2 Sources DolphiniOS `7cac5416`

- `Source/Core/Core/Boot/Boot.cpp` :
  - l. 278-298 : branche `.json` → `ParseGameModDescriptorFile` → `AddRiivolutionPatches` ;
  - l. 721-741 : disque virtuel (`DirectoryBlobReader`) avec FST patchée.
- `BootManager.cpp` l. 143-145 : la vitesse de disque rapide est forcée pour Riivolution. `Core.cpp` l. 593-595 : redirection des sauvegardes.
- `DiscIO/RiivolutionParser.cpp` l. 388-419 : `GenerateRiivolutionPatchesFromConfig` lit `Load/Riivolution/riivolution/*.xml` et `riivolution/config/<ID4>.xml`.
- `Common/FileUtil.cpp` l. 865 : `D_RIIVOLUTION_IDX` = `User/Load/Riivolution/`. `UICommon.cpp` l. 88 crée ce dossier ; chez NeoStation, il se trouve sous `Application Support/NeoStation/Dolphin/User/Load/Riivolution`.
- Chemins d'appel :
  - Android le branche (`Source/Android/jni/MainAndroid.cpp` l. 598-610 : `Run(…, riivolution)`) ;
  - l'application iOS de DolphiniOS ne le fait pas (`Source/iOS/App/Common/Emulation/EmulationBootParameter.mm`).
- Réseau et identité :
  - `IOS/Network/NCD/WiiNetConfig.cpp` l. 41-48 : configuration filaire DHCP créée si elle manque ;
  - `IOS/DolphinDevice.cpp` l. 30-39 : IOCTL 0x01 à 0x0A ;
  - `IOS/IOSC.cpp` l. 172 et 629 : identifiant d'appareil par défaut `0x0403AC68`, ou `keys.bin` s'il existe ;
  - `Boot/Boot_BS2Emu.cpp` l. 423-437 : numéro de série `SERNO` généré une seule fois dans `setting.txt`.
- Écart avec la 2606a :
  - `Core/Boot/DolReader.cpp` n'a pas les contrôles d'alignement de `1496e7a0` ;
  - `IOS/Network/IP/Top.cpp` l. 737 et 765 garde `sockaddr sa;` (corrigé par `87d5e731`) ;
  - delta amont `2606..2606a` (tag `c77bbaa0`, 10 août 2026) : 17 commits de durcissement.

### 2.3 NeoStation

- `lib/services/dolphin_internal_v2_service.dart` :
  - `_wiiExtensions` (l. 88-96) n'accepte pas `json` ;
  - le dossier utilisateur est passé au natif (l. 728).
- `packages/dolphin_internal_bridge/core/NeoStationSession.inc` : seuls la langue, les graphismes et les hacks viennent de `NeoStationSession.ini` ; rien pour Riivolution.
- `lib/services/dolphin_system_files.dart` : import d'une NAND extraite, de `keys.bin` et des certificats.

### 2.4 Retro Rewind, Retro WFC et WheelWizard

Clones publics dans `src/` :

| Dépôt | Révision | Licence |
| --- | --- | --- |
| `Retro-Rewind-Team/Pulsar` | `dd799bd` (19/10/2026) | GPLv3 ; `LICENSE_pulsar` MIT ; `LICENSE_mkw-sp` MIT |
| `Retro-Rewind-Team/wfc-server` | `6592a03` | AGPL-3.0 |
| `Retro-Rewind-Team/wfc-patcher-wii` | `9ee5c2d` | licence de type zlib, sous-licenciée en GPLv3 par le README |
| `TeamWheelWizard/WheelWizard` | `ed58f43` | GPL-3.0 |

- **Pack.** Modèle `PulsarPackCreator/Resources/Base.xml` :
  - crochets `<memory … original=…>` pour RMCP, RMCE, RMCJ et RMCK ;
  - `Loader.pul` chargé à `0x80004000` ;
  - dossiers `Binaries`, `Tracks`, `Assets` (racine du disque) et `CTBRSTM`.
  - `Code.pul` est du code de mod relié par Kamek à des adresses du jeu (par exemple `kmCall(0x8052fbd8, …)`) ; le dépôt ne contient pas de code du jeu [D pour le dépôt, I pour le binaire].
- **Comportement sur Dolphin** (Pulsar) :
  - `PulsarEngine/PulsarSystem.cpp` l. 154-167 : entrées-sorties `IOType_DOLPHIN` (NAND) ;
  - `Security/FrameLag.cpp` : `raceFrameCounter` est recalé sur l'horloge réelle par `GetElapsedTime`. Un jeu sous la pleine vitesse subira donc des sauts [I] ;
  - `Network/WiiLink.cpp` l. 182 : `http://nas.play.rwfc.net`.
- **Serveur Retro WFC :**
  - `common/config.go` l. 78 : `AllowDefaultDolphinKeys = true` ;
  - `gpcm/login.go` l. 65-77 : les clés publiques fuitées sont bannies, mais pas `0x0403ac68`. Une NAND fuitée renvoie l'erreur 22001 (« revenez à la NAND Dolphin par défaut ») ;
  - `database/login.go` : le profil est lié à l'identifiant d'appareil et au `csnum` ;
  - `gpcm/login.go` l. 231-300 : `pack_id`, `pack_ver` et `pack_hash` sont vérifiés par région, donc un pack officiel inchangé est obligatoire ;
  - `wl:host` ne vaut que « Dolphin » ou « Wii » (`payload/wwfcLogin.cpp` l. 178-180).
- **WheelWizard :**
  - installe le pack dans `<Load>/Riivolution/WheelWizard/{RetroRewind6, riivolution/RetroRewind6.xml}` ;
  - met à jour par `update.rwfc.net/RetroRewind/RetroRewind{Install,Version,Delete}.txt` (archive complète, deltas, suppressions) ;
  - lance `Dolphin -e RR.json --config=Dolphin.Core.EnableCheats=False --config=Achievements.Achievements.Enabled=False`. Le descripteur `RR.json` a les options « Pack » = 1 et « My Stuff » = 0 (`Features/Launching/RetroRewindLaunchDescriptor.cs`) ;
  - exige 2606a (`Features/DolphinInstaller/DolphinVersion.cs`).

## 3. Faisable sans toucher au cœur (a)

Ces éléments peuvent être préparés et testés maintenant, mais ils restent inutiles tant que (b) n'est pas fait.

- **Disque du joueur.** L'import Wii existe (iso, ciso, gcz, rvz, wia, wbfs). L'identité vient de `neostation_dolphin_save_identity` (RMCP01, RMCE01, RMCJ01, RMCK01).
- **Import du zip officiel** fourni par le joueur, ou téléchargé depuis le CDN officiel si l'équipe l'autorise :
  - extraction en flux vers `User/Load/Riivolution/RetroRewind/{RetroRewind6, riivolution/RetroRewind6.xml}` ;
  - refus de toute traversée de chemin, contrôle de l'espace libre (environ 1,9 Go compressé) ;
  - version lue dans `RetroRewind6/version.txt` ;
  - mise à jour : archive complète ou deltas, en conservant `riivolution/save/RetroWFC` ;
  - le pack n'est jamais embarqué dans l'IPA.
- **Descripteur `RR.json`** généré à l'identique de WheelWizard.
- **Session en ligne :**
  - triches coupées (`neostation_dolphin_set_cheats_enabled(0)`) et RetroAchievements coupés (`configure_achievements(nil, nil)`), puis rétablis après la session ;
  - chargement d'état bloqué pendant la session (menu du pont : l'en-tête `DolphinSessionMenu.h` est sous une garde de livraison).
- **Identité :**
  - le stockage classe `User/Wii` (`setting.txt`, donc `csnum`) et `riivolution/save` en « jamais » ;
  - l'application prévient qu'importer une autre NAND ou un autre `keys.bin` change l'identité Retro WFC.
- **Textes** dans les douze langues.
- **Réseau** : aucun réglage Dolphin à écrire.

## 4. Nécessite un changement du cœur (b)

- **B1, recommandé.** `validate_image` accepte un descripteur `.json` :
  - lecture par `ParseGameModDescriptorFile` ;
  - `base-file`, `xml` et `root` confinés au dossier Dolphin de NeoStation ;
  - `CreateVolume(base-file)` doit ouvrir un disque Wii RMC ;
  - XML lu par `Riivolution::ParseFile` et accepté par `IsValidForGame`, avec au moins un correctif ;
  - nombre de correctifs écrit dans le journal.
  - `DOLLaunch` et le redémarrage ne changent pas : `GenerateFromFile` traite déjà `.json`.
- **B2.** Un drapeau de lancement à la manière d'Android, avec `GenerateRiivolutionPatchesFromConfig` et un `riivolution/config/RMCP.xml` écrit par l'hôte. Moins déterministe : tous les XML valides du dossier sont pris en compte.
- **Conséquences communes :**
  - nouvelle identité `DolphinCore` ;
  - régression complète de Dolphin : StikJIT, Metal, effets, écran externe, commandes tactiles, triches, états, RetroAchievements ;
  - un test hôte du descripteur ;
  - un test Simulateur avec un disque homebrew, sans aucun contenu de jeu.
- **B3, souhaitable pour le jeu en ligne.** Rebaser sur Dolphin ≥ 2606a ou 2609a. DolphiniOS n'a pas avancé : il faudrait fusionner l'amont nous-mêmes, puis revalider le catalogue d'effets épinglé sur `7cac5416`.

## 5. Inconnu avant test sur iPhone (c)

- **Vitesse.** Pleine vitesse de Retro Rewind (pistes personnalisées, 12 joueurs) avec JITARM64 et StikJIT. Sous 60 i/s, le recalage `FrameLag` provoquerait des sauts et des désynchronisations.
- **Compilation des shaders.** Saccades à l'arrivée de nouvelles pistes : l'attente des shaders au démarrage ne les couvre pas.
- **Disque virtuel Riivolution** : mémoire, temps du premier démarrage, environ 2 Go sur l'appareil.
- **Réseau iOS :**
  - données mobiles derrière un NAT d'opérateur (erreur 86420 connue en amont) ;
  - réseaux IPv6 seuls (NAT64) avec des sockets IPv4 émulées ;
  - pairs sur le réseau local (autorisation « Réseau local ») ;
  - suspension en arrière-plan.
- **Serveur.** La configuration de production de Retro WFC et son acceptation de ce client.
- **Pack.** Le contenu de `Assets` (fichiers éventuellement dérivés du jeu) et la version en cours le 20 octobre.

## 6. Plan proposé

1. **Mainteneur :**
   - autoriser B1, et décider si B3 précède le jeu en ligne ;
   - demander à l'équipe Retro Rewind (ZPL, ppeb) l'autorisation de télécharger depuis son CDN ; à défaut, import par le joueur seulement.
2. **Hôte (a)**, puis **cœur B1**, avec la régression ciblée et la nouvelle identité consignée.
3. **IPA privée**, puis protocole sur iPhone :
   - démarrage hors ligne pour chaque région possédée par le mainteneur ;
   - version affichée ;
   - connexion Retro WFC sans erreur 22001, 22005, 22010 ni 86420 en Wi-Fi ;
   - course mondiale complète et salon d'amis ;
   - fréquence d'images stable ;
   - arrière-plan puis retour au premier plan ;
   - relancement avec le même profil ;
   - mise à jour vers la version suivante ;
   - triches et RetroAchievements bien coupés.

## 7. Wiimmfi (jeu original)

- [I, indirect] Il faut une image patchée par l'outil Wiimmfi et, selon les développeurs de Dolphin, une NAND extraite d'une vraie console : la NAND Dolphin par défaut est refusée (erreur 23918).
- Le cœur verrouillé démarrerait une telle image sans changement. NeoStation importe déjà la NAND et `keys.bin`.
- Cette voie reste compatible avec les contraintes seulement si **le joueur** patche lui-même son image. Elle est **[?]** tant que les règles actuelles de Wiimmfi ne sont pas lues : `wiimmfi.de` est bloqué ici.

## 8. Sources

- https://github.com/OatmealDome/dolphin-ios/tree/7cac54161659421ed95c2cd1c0b0746539a4cd38
- https://github.com/dolphin-emu/dolphin (tags 2509, 2606, 2606a `c77bbaa0`, 2609a)
- https://github.com/Retro-Rewind-Team/Pulsar (`dd799bd`)
- https://github.com/Retro-Rewind-Team/wfc-server (`6592a03`)
- https://github.com/Retro-Rewind-Team/wfc-patcher-wii (`9ee5c2d`)
- https://github.com/MelgMKW/Pulsar (`820ad92`)
- https://github.com/TeamWheelWizard/WheelWizard (`ed58f43`)
- https://forums.dolphin-emu.org/Thread-wiimmfi-23918
- https://forums.dolphin-emu.org/Thread-how-do-i-get-mario-kart-wii-working-online-on-dolphin-but-with-no-wii-console
- https://bugs.dolphin-emu.org/issues/11455
- https://github.com/TarbleFR/neostation-ios/releases/download/0.0.1/NeoStation.ipa (lecture partielle, Dolphin seulement)
- Dépôt NeoStation :
  - `build-utils/patch_dolphin_internal_core_v2.py` ;
  - `packages/dolphin_internal_bridge/` ;
  - `lib/services/dolphin_internal_v2_service.dart` ;
  - `lib/services/dolphin_system_files.dart` ;
  - `docs/kartpad-online-dusklight-audit-2026-10-19.md`.
