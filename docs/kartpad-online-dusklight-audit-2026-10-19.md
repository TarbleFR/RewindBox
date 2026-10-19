# KartPad en ligne et mise à jour des ports natifs (KartPad, Dusklight) — audit du 19 octobre 2026

Demande du mainteneur (19 octobre 2026, priorité haute) : un joueur signale que KartPad installé seul propose le jeu en ligne, mais pas le port intégré à NeoStation. Le mainteneur demande trois choses :

- intégrer dans NeoStation le multijoueur en ligne de KartPad (Retro Rewind et Retro WFC en priorité, puis une étude de Mario Kart Wii original) ;
- mettre à jour le moteur KartPad vers la 0.8.3 en reconstruisant le cœur iOS ;
- ajouter une section « Multijoueur en ligne » au menu en jeu et vérifier Dusklight.

Conditions posées :

- KartPad et Dusklight restent des ports natifs intégrés, sans redirection vers une autre application ;
- aucun ISO, code de jeu non autorisé ni fichier protégé n'est redistribué ;
- aucun faux cœur n'est fabriqué ;
- si un élément indispensable bloque la construction du nouveau KartPadCore, le dire exactement, avec son origine et les étapes pour lever le blocage.

Ce document sépare ce que les sources et les binaires **démontrent** de ce qui est **déduit**. Aucun essai n'a été fait sur iPhone dans ce cycle.

## 1. Conclusions

1. **Le moteur intégré contient déjà le jeu en ligne, mais il ne peut plus servir.**
   - Le cœur KartPad de NeoStation est le donneur officiel `v0.5.1-experimental.1` (§ 2). Il contient le jeu de base, le profil Retro Rewind **6.12.8** et toute la pile Retro WFC.
   - NeoStation force le profil « base » et masque le choix Original / Retro Rewind. Le service en ligne du jeu original (Nintendo WFC) est fermé.
   - Retro WFC n'accepte que le Retro Rewind actuel (6.13.3). Le serveur refuse les autres versions (« Invalid pack version! … Error Code: 22010 », `docs/KNOWN-ISSUES.md` amont), et l'application 0.5.1 bloque elle-même Retro Rewind dès que le flux officiel annonce une version plus récente.
   - Démontré : afficher le profil Retro Rewind ou un menu multijoueur avec ce moteur ne donnerait **aucune** partie en ligne.
2. **La seule voie vers Retro WFC est un cœur KartPad 0.8.3 avec le code de Retro Rewind 6.13.3 traduit.**
   - Depuis la 0.7, KartPad ne publie plus aucun code de jeu pour iPhone (`publication.public_binaries: false`).
   - Le code traduit (jeu de base et Retro Rewind) est un **pack personnel** (`libkartpad_game.dylib`). PadMint le compile à partir du disque de chaque joueur.
3. **Bloquant :** le cœur 0.8.3 ne peut pas être construit dans ce cycle (§ 6). Il manque le pack traduit, qui vient du `main.dol` et du `StaticR.rel` du disque du joueur. Il manque aussi le travail d'adaptation du cycle de vie, qui ne peut être vérifié qu'avec ce pack.
   - **Aucun KartPadCore n'est reconstruit et aucune IPA n'est produite** : rien dans le produit ne change.
   - Aucune fonction en ligne n'est présentée comme disponible.
4. **Mario Kart Wii original en ligne n'est pas implémenté en amont** (§ 7) : ni Wiimmfi (#90 ouvert), ni service de remplacement. Une adresse de serveur ne suffit pas.
5. **Dusklight est à jour.** La v2.0.3 reste la dernière version stable (§ 9), sans correctif iOS, Metal, sauvegarde ou fermeture plus récent. Rien n'est reconstruit.

## 2. Le cœur KartPad réellement intégré

| Élément | Valeur | Source |
| --- | --- | --- |
| Mode | `official-ipa-donor` : l'exécutable de l'IPA officielle 0.5.1 converti en bibliothèque, plus le pont NeoStation | `build-utils/kartpad/source.json`, `KartPad-native-identity.json` de l'IPA 0.0.1 (Build 350, SHA-256 `e1017b96…`) |
| Version amont | `v0.5.1-experimental.1`, source compilée `67c7e2f9`, étiquette `0d657f36`, runtime iOS `d0b8dec6` | idem |
| `KartPadRuntime` | SHA-256 `ad5c00a0a508bbfcc0dc3eb1ee04a17f10919cde0b5cccd90d1d9e6a31c39eb0`, 103 576 952 octets | identité restaurée (`build-utils/restore_kartpad_donor_from_ipa.py`) |
| `KartPadCore` (pont NeoStation) | SHA-256 `995e8767…`, ABI NeoStation 2, identité `kartpad_rmcp01_full_game_v1` | idem |
| Code traduit | 29 637 fonctions : 29 065 du jeu de base, le reste pour Retro Rewind | `source.json`, cible amont `KartPadDual` |
| Retro Rewind | **6.12.8**, archive `https://cdn.update.rwfc.net/RetroRewind/zip/6.12.8-full.zip`, flux `https://update.rwfc.net/RetroRewind/RetroRewindVersion.txt` | chaînes du binaire `ad5c00a0…` |
| Pile en ligne | `nas.play.rwfc.net`, `gs.play.rwfc.net`, NATNEG/QR2, GameSpy/DWC traduits, serveur privé `KartPadPrivateWfcHost` / `KARTPAD_PRIVATE_WFC_HOST`, message « Retro Rewind Update Needed » | chaînes du binaire |
| Identité réseau (CSNum, #94) | Correctif présent : `RuntimeScSerial::Write` écrit le numéro de série en `u32` (`runtime/include/sc_serial_contract.h` au runtime `d0b8dec6`), corrigé depuis iOS 0.4.11 | sources `chrissotraidis/wiicompiled` |
| Fermeture réseau au retour | `NetworkHle::CleanupAllWiiSockets` appelé par le pont avant la réutilisation de session | `native/kartpad/donor/DonorSessionControl.inc` |

Comportement imposé par NeoStation :

- `NeoKartPadDonorCore.mm` écrit `KartPadRequestedRuntimeProfile = base` et `KartPadPreferredGame = base` avant chaque lancement ;
- le sélecteur autonome Original / Retro Rewind et l'entrée « menu principal » du menu ••• de KartPad sont retirés.

Le profil Retro Rewind du donneur n'est donc jamais ouvert.

Au-delà de l'absence de traduction de Retro Rewind 6.13.3, il manque à ce donneur les correctifs amont de la 0.8.0, dont l'arrêt des sessions TLS après une écriture échouée (WiiCompiled #258, KartPad `731fc84`).

## 3. KartPad 0.8.3 (dernière version stable)

- **Version** : `v0.8.3`, build 265, commit `7e99c6776263caa85dccde2de6281cb092778877`, publiée le 16 octobre 2026. `main` (`c30f758e`, 19 octobre) porte encore 0.8.3 ; aucune étiquette plus récente.
- **Dépendances** :
  - runtime iOS `chrissotraidis/wiicompiled` branche `kartpad-ios` `2babfb71` (203 commits après `d0b8dec6`) ;
  - traducteur `937c334d` ;
  - synchronisation amont WiiCompiled `bd219e3` (0.8.0) ;
  - PadMint en version 0.5.9.
- **IPA publique** : `KartPad-v0.8.3-ios-for-padmint.ipa`, 9 289 255 octets, SHA-256 `b5096fe14cb93e6305e365e49dddd65027fa2a386d6d06271dc4d6a9c5a3eb4d`, égal au `SHA256SUMS` publié. C'est l'**application sans code de jeu**, vérifiée ici :
  - l'exécutable est arm64 `MH_EXECUTE`, SHA-256 `0477ba73…4cc0`, iOS 16.0 minimum ;
  - il ne contient aucun symbole `func_8…` ;
  - il n'y a pas de `Frameworks/libkartpad_game.dylib` ;
  - l'exécutable contient l'empreinte d'interface `47d67acd0c1ac5e7736cb1a6159425ab7663e4d3a2d5dec28aee1c507fdac58e`. Elle a été recalculée indépendamment à partir des sources épinglées et donne la même valeur.
- **Pack personnel**, construit par PadMint avec le disque du joueur :
  - fichier `Frameworks/libkartpad_game.dylib`, `MH_DYLIB` arm64 ;
  - liaison `-undefined dynamic_lookup` contre les symboles exportés par l'application (19 626) ;
  - ABI 3 (`runtime/include/game_pack.h`). Il exporte `kartpad_game_pack_info` (48 octets) et `kartpad_game_pack_fingerprint` (`"kartpad-pack-fingerprint:<hex>"`, lisible sans charger le pack).
  - Chargement : `KartPadRuntimeOverlayHost -run` → `GamePack::EnsureLoaded()`, qui fait `dlopen(RTLD_NOW|RTLD_GLOBAL)`, contrôle l'ABI puis compare l'empreinte avec `strcmp`.
  - **Un seul pack contient le jeu de base et Retro Rewind.** Le profil se choisit au lancement par `KartPadRequestedRuntimeProfile` (`base` ou `retro_rewind`).
- **Entrées du pack** (`builder/profiles/mkwii-rmcp01-rev0.json`) :
  - `sys/main.dol` SHA-256 `80d18895…5b05` et `files/rel/StaticR.rel` SHA-256 `16d9d146…f67d`, extraits du disque PAL RMCP01 révision 0 du joueur (nodtool 2.0.0-alpha.9, sans clé Wii) ;
  - Retro Rewind 6.13.3, archive officielle de 1 939 354 554 octets (SHA-256 `7e8008b5…26b9`), `Code.pul` (SHA-256 `58f4ac46…f036`) et XML (SHA-256 `8759d8d9…3a41`). Le `version.txt` du pack indique 6.13.2, comme prévu en amont ;
  - charge utile Retro WFC `http://nas.play.rwfc.net/payload?g=RMCPD00` (SHA-256 `099097a0…6471`, signature RSA contrôlée).

  Le traducteur recopie les octets des fonctions du jeu de base pour construire celles de Retro Rewind (`OverlayFunctionBuilder.cs`). **Retro Rewind ne peut donc pas être traduit sans le `main.dol` et le `StaticR.rel` du joueur.**
- **Partie en ligne :**
  - le transport est dans le runtime : sockets BSD, DNS hors du fil d'émulation, TLS par SecureTransport avec certificats vérifiés, IPv4 seulement, sans relais ;
  - les protocoles DWC/GameSpy, la recherche d'adversaires et le comportement de la charge utile sont du code de jeu traduit ;
  - la redirection des noms vers Retro WFC est faite par la charge utile traduite, pas par le runtime ;
  - le serveur expérimental (`KartPadPrivateWfcHost`) redirige seulement `*.nintendowifi.net` et `*.play.rwfc.net` vers un hôte choisi, en clair, au lancement suivant ;
  - le flux de version bloque Retro Rewind quand une version plus récente est annoncée (après 15 s sans réponse, l'utilisateur peut réessayer ou lancer la version installée) ;
  - les salons privés se font dans le jeu : Nintendo WFC → Amis, code ami, puis le salon de l'hôte. Le menu iOS de KartPad ne fait qu'expliquer cette démarche.
- **Limites amont connues :**
  - erreur 86420 en données mobiles derrière un NAT d'opérateur (#405) : la connexion directe entre joueurs échoue, il faut le Wi-Fi ou un VPN ;
  - déconnexions en course observées sur émulateur Android ;
  - transfert d'identité imparfait (#234).
  - Les notes de la 0.8.3 disent : « Not checked: online races on 6.13.3 … iPhone gameplay ».
- **Mises à jour de Retro Rewind :** la plupart changent son code (`Code.pul`), donc le pack traduit. Une mise à jour faite dans l'application ne remplace que les fichiers de données ; un nouveau code exige une nouvelle construction du pack avec PadMint (KNOWN-ISSUES amont).

## 4. Écart entre le cœur intégré et la 0.8.3

| Point | Intégré (0.5.1) | 0.8.3 |
| --- | --- | --- |
| Code du jeu | Lié dans l'exécutable officiel publié | Pack personnel séparé, ABI 3, empreinte `47d67acd…` |
| Retro Rewind | 6.12.8, refusé par Retro WFC (22010) | 6.13.3, la version acceptée |
| ABI NeoStation | 2, adaptée par patchs binaires vérifiés sur le donneur | À créer : les adaptations visaient des adresses du code traduit (§ 6) |
| Identité (CSNum) | Corrigée | Corrigée, identité dans `setting.txt` de la NAND, avec migration de `ConsoleIdentity.txt` |
| TLS après une écriture échouée | Non corrigé | Corrigé (0.8.0) |
| Profils | Base forcé par NeoStation | Base et Retro Rewind dans le même pack |

## 5. Ce qui est fait dans ce cycle (vérifiable sans pack)

- `build-utils/kartpad/migration-target.json` passe à la cible **0.8.3** : release, runtime, traducteur, ABI 3, empreinte `47d67acd…`, IPA et exécutable officiels, éléments épinglés de Retro Rewind 6.13.3, empreintes des deux fichiers du disque nécessaires au pack, procédure officielle PadMint.
  - Ce fichier ne change pas le cœur installé (`integrated: false`). Les workflows de livraison `retroarch-delivery.yml` et `neoswap-ipa.yml` l'excluent déjà, avec l'inspecteur, de la comparaison d'identité KartPad.
- `build-utils/kartpad/inspect_personal_pack.py` exige désormais le symbole exporté `kartpad_game_pack_fingerprint` et compare l'empreinte **à l'adresse de ce symbole**. Auparavant, il cherchait le marqueur n'importe où dans le fichier.
  - Contrôle négatif : un pack 0.7.3 (empreinte `35ccf81c…`) contenant ailleurs le marqueur 0.8.3 est accepté par l'ancien inspecteur et refusé par le nouveau.
  - Ces deux résultats ont été vérifiés dans le conteneur de travail (`test/kartpad_personal_pack_test.py`).
  - L'IPA publique 0.8.3 réelle est refusée (« A personal libkartpad_game.dylib is required »).
  - Cet inspecteur lit seulement : il ne charge, n'extrait ni ne copie aucun code de jeu.
- **Volontairement non fait :**
  - **pas de section « Multijoueur en ligne » dans le menu en jeu** avec le moteur 0.5.1. Elle n'aurait que des options inutilisables : profil Retro Rewind refusé par le serveur, service du jeu original fermé, serveur expérimental sans service public compatible. Sa conception est décrite au § 8 pour le cœur 0.8.3 ;
  - pas de reconstruction du pont `KartPadCore` (identité `995e8767…`) ni du runtime donneur ;
  - pas d'IPA : aucune source du produit ne change.

## 6. Élément bloquant pour le nouveau KartPadCore et étapes pour le lever

**Élément indispensable absent :** le pack traduit KartPad 0.8.3 (jeu de base RMCP01 et Retro Rewind 6.13.3), compilé pour iPhone.

**Origine :**

- il se produit uniquement à partir du `main.dol` (SHA-256 `80d18895…`) et du `StaticR.rel` (SHA-256 `16d9d146…`) du disque du joueur ;
- l'amont ne le publie plus pour Apple : « PadMint outputs are personal builds », et `RIGHTS_AND_LICENSES.md` amont précise que les droits du code traduit ne sont pas acquis ;
- la CI de NeoStation n'a, et ne doit avoir, ni ces fichiers ni le code traduit.

**Second verrou, d'ingénierie :** l'intégration actuelle repose sur des patchs binaires vérifiés à des adresses fixes du donneur 0.5.1 (`build-utils/kartpad/patch_donor_session_bridge.py`, `patch_donor_language_bridge.py`) :

- retour coopératif à la fin d'image de `RKSystem::run` (`func_8000951C`) ;
- garde du sélecteur de profil figé ;
- réentrée de `DVDInit` ;
- `SCGetLanguage` ;
- session audio ;
- pompe d'évènements UIKit.

En 0.8.3, le code traduit vit dans un pack **propre à chaque joueur**, dont les adresses diffèrent d'une construction à l'autre. Ces adaptations doivent être refaites dans les sources du runtime : fin d'image, sortie de la boucle invitée, réinitialisation DVD et mémoire, langue, audio, fenêtre. On ne peut les vérifier qu'en faisant tourner le jeu, donc avec un pack.

**Signature iOS (déduit des règles d'iOS) :**

- un `dlopen` ne fonctionne que sur du code signé avec l'application. Le pack doit donc être dans le bundle de NeoStation au moment de la signature SideStore ;
- NeoStation ne peut ni compiler ni signer un pack sur l'iPhone ;
- le pack est lié par nom aux exports du runtime 0.8.3 et à son empreinte exacte. Il ne se charge que dans un processus qui exporte ce runtime.

**Étapes pour lever le blocage :**

1. **Mainteneur, procédure officielle.** Construire son pack personnel KartPad 0.8.3 pour iOS avec PadMint (0.5.3 ou plus récent), à partir de son disque RMCP01 révision 0.
   - Hôtes : Mac, ou Windows/Linux en expérimental.
   - Outils : Python 3, git, CMake, Ninja, .NET 8, nodtool ; Xcode sur Mac, LLVM 21 sur Windows/Linux.
   - Mesures amont en 0.7.2 : environ 15 à 30 min et 16 Go d'espace.
   - Contrôler le résultat avec `python3 build-utils/kartpad/inspect_personal_pack.py <IPA PadMint>`. **Ne jamais téléverser ce pack dans un ticket, un dépôt ou un artefact de CI.**
2. **NeoStation, cycle autorisé séparément :**
   - construire en CI le runtime 0.8.3 **depuis les sources publiques**, sans code de jeu, comme framework chargé à la demande. Contrôles : empreinte `47d67acd…` reproduite, exports exigés par le pack, aucun symbole `func_8…` ;
   - porter le cycle de vie du § 6 dans ces sources et réécrire l'ABI NeoStation (3) ;
   - garder le donneur 0.5.1 pour qui n'a pas de pack. Un processus ne charge qu'un seul des deux runtimes : ils exportent les mêmes classes Objective-C et ne se déchargent pas.
3. **Injection hors CI.** Le mainteneur ajoute son pack dans l'IPA NeoStation déchiffrée, sur son PC, avant la signature SideStore (script NeoStation à écrire, comme `add-game-pack-to-ipa.sh` en amont). Ni la CI ni l'IPA livrée ne contiennent de code de jeu.
4. **Migration des données sans perte :**
   - NAND et identité de `Ports/KartPad/Saves/NAND` : `title/00000001/00000002/data/setting.txt`, `ConsoleIdentity.txt` migré par l'amont ;
   - `rksys.dat` (`title/00010004/524d4350/data/`), licences, fantômes, Miis (`shared2/menu/FaceLib/RFL_DB.dat`), `nwc24msg.cfg` ;
   - sauvegardes Retro Rewind (`riivolution/save/RetroWFC*/RMCP/rksys.dat`) et `Config/Config.toml`.

   Aucun numéro de série n'est régénéré et aucune sauvegarde n'est effacée.
5. **Validation** avec le pack, sur iPhone : la matrice du § 10.

## 7. Mario Kart Wii original en ligne

- Démontré : Nintendo WFC est fermé, et aucun code Wiimmfi n'existe dans KartPad. Les seules occurrences de « wiimmfi » sont les messages qui refusent un disque déjà patché. Le ticket #90 est ouvert, sans implémentation.
- Une adresse de serveur ou un DNS ne suffit pas, d'après `ONLINE.md` et `MULTIPLAYER.md` amont. Wiimmfi et les services de type WiiLink attendent un jeu patché et une authentification. Il faudrait au minimum :
  - un profil exécutable correspondant, reproductible et traduit, donc un autre pack (par exemple à partir d'un jeu patché pour ce service) ;
  - une gestion privée de l'identité ;
  - une validation complète : connexion, course, résultats, reconnexion.

  KartPad n'exécute aucun code téléchargé : une charge utile envoyée par un serveur doit être traduite à la construction, comme celle de Retro WFC.
- Le réglage « Experimental Server Settings » (`KartPadPrivateWfcHost`) vise un service privé compatible. Aucun service public compatible avec le jeu original sans patch n'est établi. **Rien n'est proposé pour le jeu original dans ce cycle.**

## 8. Conception de la section « Multijoueur en ligne », à réaliser avec le cœur 0.8.3

La section ira dans le menu « Réglages KartPad » du pont. Chaque entrée correspond à une fonction réelle du runtime 0.8.3 ; les opérations du jeu ne sont pas dupliquées.

- **Profil :** Mario Kart Wii (Original) ou Retro Rewind (`KartPadRequestedRuntimeProfile`), appliqué au lancement suivant, avec confirmation, comme la langue.
- **Retro Rewind :**
  - affiche la version installée et la version que contient le pack ;
  - le flux officiel est lu à la demande, sans bloquer le jeu hors ligne ;
  - une mise à jour de données compatible passe par l'installeur du runtime (`KartPadRetroRewindInstaller` : archive officielle, taille et SHA-256 vérifiés ; sauvegardes et fantômes conservés) ;
  - un nouveau code Retro Rewind annonce honnêtement qu'il faut un nouveau pack PadMint.
- **Service :** Retro WFC pour Retro Rewind ; « fermé » pour l'Original.
- **Amis et salons privés :** renvoi au menu Nintendo WFC → Amis du jeu, sans menu parallèle.
- **Serveur expérimental :** hôte ou IPv4 (`KartPadPrivateWfcHost`, validé comme en amont), appliqué au lancement suivant, avec retour possible au service par défaut.
- **Messages d'erreur**, sans jamais effacer de sauvegarde ni régénérer d'identité :
  - 22010 : pack Retro Rewind trop ancien ;
  - 86420 : données mobiles ou NAT d'opérateur, utiliser le Wi-Fi ou un VPN ;
  - 22005 : CSNum ou profil refusé par le serveur, qui relève de son administration ;
  - 61070 : connexion au service impossible ;
  - délai réseau dépassé.
- **Textes NeoStation** dans les douze langues (catalogue du pont, `set_ui_text`). Les six langues du jeu PAL ne changent pas.
- Le mode en ligne reste facultatif : le jeu hors ligne n'exige ni connexion ni réglage.

## 9. Dusklight

- **Démontré (`git ls-remote`, 19 octobre 2026) :** aucune étiquette après `v2.0.3` (`40457c6a`, 30 septembre), qui est l'épinglage NeoStation.
  - `main` (`34a144a4`) ajoute 2 commits du 4 au 10 octobre : `2c4960dc` (endurance d'Epona infinie) et `34a144a4` (suppression de l'étourdissement après un coup). Ce sont deux triches de jeu désactivées par défaut. Elles ne touchent rien côté iOS, Metal, sauvegarde, cycle de vie, performances, audio ou commandes.
  - Les pointeurs Aurora (`3227d76c`) et Borealis (`4ac5e705`) ne changent pas, ni SDL 3.4.10.
- **Aurora `main` (`51797212`, 25 commits)** n'est pas adoptée par Dusklight et ne compile pas avec la 2.0.3 : le nouveau routeur d'entrée `d664382` supprime `aurora/lib/input.hpp`, encore utilisé par `src/dusk/action_bindings.cpp`.
  - Elle entrerait en conflit avec les adaptations validées de NeoStation : `release_frame_resources()` appelle `clear_caches()` et `depth_peek`, retirés par `b922153` et `6f07a59`, et `window.cpp` est réécrit.
  - Le cache LRU de `b922153` traite une croissance mémoire observée dans un autre jeu. NeoStation vide déjà ces caches au retour (Builds 317–322).
- **Décision : Dusklight reste en v2.0.3, sans reconstruction.**
  - `DusklightCore.framework`, la playlist Ports, les sauvegardes, les commandes, les réglages, l'import et les menus restent identiques.
  - Les validations précédentes restent valables, car aucune entrée n'a changé.
  - À surveiller : la prochaine étiquette Dusklight qui adoptera `b922153`, `6f07a59` et `d664382`. Il faudra alors porter la libération des ressources, rebaser `window.cpp` et revérifier le tactile.

## 10. Matrice de validation

| # | Scénario | État |
| --- | --- | --- |
| H1–H5 | KartPad hors ligne : lancement, course solo, tactile et manettes, sauvegardes, retour et lancements successifs | Aucun changement du moteur ni du pont : les validations précédentes restent valables (`docs/kartpad-integration.md`). Rien n'est rejoué. |
| L1 | Connexion au service Retro WFC | Non exécuté : bloqué, aucun moteur intégré n'a de profil accepté par Retro WFC (§ 1) |
| L2 | Authentification avec un profil compatible | Non exécuté : bloqué |
| L3 | Salle publique | Non exécuté : bloqué |
| L4 | Recherche d'adversaires | Non exécuté : bloqué |
| L5 | Début de course | Non exécuté : bloqué |
| L6 | Synchronisation en course | Non exécuté : bloqué |
| L7 | Fin de course et résultats | Non exécuté : bloqué |
| L8 | Retour au salon | Non exécuté : bloqué |
| L9 | Déconnexion volontaire et reconnexion | Non exécuté : bloqué |
| L10 | Erreurs réseau sans plantage | Non exécuté : bloqué |
| P1 | Précontrôle du pack personnel 0.8.3 (ABI, empreinte exportée, plateforme, bornes ; refus de l'IPA publique sans pack et d'un pack 0.7.3) | Réussi dans le conteneur (`test/kartpad_personal_pack_test.py`, avec contrôle négatif de l'ancien inspecteur) |
| D1 | Dusklight | Aucun fichier modifié : validations précédentes conservées, rien rejoué |

Pour L1–L10, l'amont lui-même ne déclare comme réussi qu'un essai local entre Apple et Apple (macOS et Simulateur iPad sur un serveur WFC isolé, 1er septembre). Sur Android, des connexions, salles mondiales et courses Retro WFC ont été signalées par des joueurs. Les courses en ligne 6.13.3 et le jeu sur iPhone ne sont pas vérifiés en amont pour la 0.8.3. Une connexion réussie ne suffira pas : la validation exige une vraie course en ligne et son résultat sur iPhone.

## 11. Sources

- KartPad : https://github.com/chrissotraidis/kartpad (étiquette `v0.8.3`, `docs/ONLINE.md`, `MULTIPLAYER.md`, `STATUS.md`, `KNOWN-ISSUES.md`, `docs/releases/v0.8.3.md`, `padmint.json`, `builder/`), fichiers publiés `KartPad-v0.8.3-ios-for-padmint.ipa` et `SHA256SUMS`.
- WiiCompiled (fork KartPad) : https://github.com/chrissotraidis/wiicompiled (`kartpad-ios` `2babfb71`, `runtime/include/game_pack.h`, `runtime/game_pack/pack_info.cpp`, `runtime/include/sc_serial_contract.h`).
- PadMint : https://github.com/chrissotraidis/padmint (v0.5.9).
- Dusklight : https://github.com/TwilitRealm/dusklight (`v2.0.3`, `main` `34a144a4`), Aurora et Borealis aux URL des sous-modules.
- NeoStation : IPA 0.0.1 (Build 350) pour l'identité du donneur, `native/kartpad/donor/`, `build-utils/kartpad/`.
