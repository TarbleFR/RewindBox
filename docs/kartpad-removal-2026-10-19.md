# Retrait de KartPad de NeoStation — 19 octobre 2026

## 1. Décision du mainteneur

Pendant le cycle « KartPad en ligne » (`docs/kartpad-online-dusklight-audit-2026-10-19.md`), le mainteneur a décidé :

> « Retire complètement Mario Kart Pad. Vu qu'il contient du code, et que c'est un port, c'est à l'utilisateur de le construire lui-même et de l'installer en tant qu'IPA unique. Je pense que c'est la meilleure des solutions pour protéger. »

Cette décision remplace les choix précédents du même cycle :

- donneur 0.5.1 gardé dans la prochaine IPA ;
- moteur 0.8.3 sans jeu intégré à NeoStation ;
- outil d'ajout d'un pack personnel dans l'IPA de NeoStation.

Raison de fond, démontrée par l'audit (§ 2 de l'audit) : le moteur KartPad intégré (`KartPadRuntime`, donneur officiel `v0.5.1-experimental.1`) contient du code de Mario Kart Wii traduit à l'avance. On y trouve 29 065 fonctions `func_8…`, les chaînes `RVL_SDK` et les classes du jeu. Depuis la 0.7, KartPad ne publie plus de code de jeu pour iPhone : chaque joueur compile son propre pack à partir de son disque.

Le mainteneur a aussi autorisé (même jour) la modification des deux fichiers de bibliothèque verrouillés sur la Build 419 qui analysaient le dossier KartPad.

## 2. Ce qui est retiré

- **Moteur et pont.** Le pont Flutter `packages/kartpad_internal_bridge` et les sources de l'hôte donneur `native/kartpad/` sont retirés. Les outils `build-utils/kartpad/`, `build-utils/restore_kartpad_donor_from_ipa.py` et `build-utils/validate_kartpad_ipa.py` aussi. Le moteur 0.8.3 sans jeu préparé dans ce cycle (`build-utils/kartpad_runtime/`, `.github/workflows/kartpad-runtime.yml`) et l'outil d'ajout d'un pack personnel (`tools/kartpad/`) sont abandonnés.
- **Application.**
  - `lib/services/kartpad_internal_service.dart` et `lib/services/ports_display_title.dart` sont supprimés.
  - L'import « Mario Kart Pad » du menu Ports, la route de lancement, la surveillance de session, la restauration audio propre à KartPad et l'identité de scraping « Mario Kart Wii » sont retirés.
  - Le crédit KartPad quitte la boîte de dialogue des crédits, et l'émulateur `ports.ios.kartpad` quitte `assets/systems/ports.json`.
- **Bibliothèque (exception autorisée).** `lib/providers/sqlite_config_provider.dart` perd l'import du service, et `scanning.dart` perd la racine `Ports/KartPad` de l'analyse. `test/retroarch_baseline_scope_test.py` reconstruit exactement ces lignes avant de comparer l'empreinte 419 : aucun autre octet verrouillé ne change. À la prochaine analyse de Ports, la ligne de bibliothèque de l'ancien jeu disparaît (nettoyage des lignes orphelines existant). Aucun fichier n'est supprimé.
- **NeoPlay.** `NPGameHUDAnchor.swift` ne reconnaît plus le menu de l'ancien overlay KartPad.
- **Workflows.** Les sept workflows `kartpad-*.yml` sont supprimés. Dans `retroarch-delivery.yml`, `neoswap-ipa.yml` et `ios-ci.yml` (hérité), les étapes qui restauraient, vérifiaient et embarquaient le donneur KartPad sont retirées. `delivery_cipher.py` ne met plus `dist/kartpad-native` en cache.
- **Mentions légales.** `assets/legal/KartPad-*.md` ne sont plus embarqués. `NOTICE.md`, `docs/LEGAL_AND_CREDITS.md` et `assets/legal/THIRD_PARTY_NOTICES.md` gardent le crédit de KartPad et de WiiCompiled pour les builds antérieures qui l'intégraient. Le README indique que KartPad n'est plus inclus.

## 3. Ce qui est conservé

- **Les données des joueurs.** Rien n'est déplacé ni supprimé dans `Fichiers › NeoStation › Ports › KartPad` : fichier du jeu, sauvegardes (`Saves/NAND`), identité de console, réglages, journaux, données préparées (`Runtime/GameData`).
- **L'outil de stockage.** Il reconnaît toujours ce dossier : il ne propose jamais de supprimer les sauvegardes. Les données préparées restent supprimables seulement sur demande explicite, avec un avertissement corrigé dans les douze langues : « extraites de votre disque pour l'ancien KartPad intégré ; NeoStation ne les utilise plus ».
- **Un jeu encore listé avant la prochaine analyse.** Le lancement le refuse avec un message traduit dans les douze langues (`PortsLocale` `kartpadRemoved`) : KartPad n'est plus inclus, il s'installe comme une application séparée, et le fichier et les sauvegardes restent dans `Ports › KartPad`. Le jeu n'est jamais transmis à Dusklight.
- **Ce qui garde la mention de KartPad sans l'exécuter.**
  - La valeur d'ABI `NEOSWAP_KARTPAD = 4` de NeoSwap reste, car elle est partagée avec le Core RPCS3 épinglé.
  - L'historique de `build-utils/rpcs3/embedded-core.patch` reste.
  - Le service `ExternalDisplayService.runUnsupportedEngineSession` reste disponible pour un futur moteur.
  - Les anciens portails de livraison (`.github/diagnostics/*`) et les manifestes historiques ne sont pas réécrits.
- **Les anciennes releases.** La release 0.0.1 (Build 350, qui contient le donneur) et les IPA déjà distribuées ne sont ni supprimées ni modifiées. L'historique Git n'est pas réécrit.

## 4. Garanties de livraison

- **Donneur natif sans KartPad.** Les livraisons ne téléchargent plus l'IPA Build 350 entière. `build-utils/fetch_native_donor_subset.py` lit son répertoire central épinglé par requêtes de plage et ne récupère que les membres réutilisés : cœurs Dolphin, RPCS3, ARMSX2 et Dusklight, `Sys`, ressources tactiles et `cacert.pem`. Aucun octet d'un membre KartPad n'est demandé. `game_content_gate.py` contrôle ensuite le sous-ensemble.
- **IPA finale.** `build-utils/validate_no_kartpad_ipa.py` refuse :
  - les frameworks `KartPadCore`, `KartPadRuntime` et `KartPadEngine`, le framework du pont et un pack `libkartpad_game.dylib` ;
  - une `KartPad.app` imbriquée et `KartPad-native-identity.json` ;
  - les ressources racine de l'ancien port (`wii_bootstrap/`, `initial_pipeline_cache.db`, `dsp_coef.bin`) ; Dolphin garde les siennes sous `Sys/GC` ;
  - et, par `game_content_gate.py`, tout fichier d'origine du jeu : empreintes connues, noms, en-têtes de disque, marqueurs du code traduit, archives imbriquées comprises.

  Étalonnage :
  - sur la vraie IPA Build 350, 21 fichiers KartPad (28 entrées d'archive) et 6 marques de code traduit sont refusés, jusque dans l'hôte NeoStation du donneur (`func_80635A3C`) ;
  - le dépôt entier ne donne aucun faux positif hors des sources, tests et audits du contrôle lui-même.
- **Caches GitHub Actions.** `dist/kartpad-native` (le donneur) n'est plus placé dans le cache chiffré de livraison. Les anciennes entrées de cache, chiffrées, ne sont pas supprimables depuis cette session ; GitHub les évince d'elles-mêmes après 7 jours sans accès.

## 5. Vérifications

Dans le conteneur, sans Flutter :

- `test/retroarch_baseline_scope_test.py` : les deux fichiers verrouillés retrouvent exactement l'empreinte 419 une fois les seules lignes KartPad reconstruites, et `native/kartpad` est absent.
- Contrôles réussis : `test/no_kartpad_ipa_test.py`, `test/game_content_gate_test.py`, `test/native_donor_subset_test.py`, `test/cheats_media_source_contract_test.py`, `test/embedded_engine_route_contract_test.py`, `test/ports_external_display_test.py`, `test/storage_contract_test.py`, `test/legal_bundle_preflight_test.py` et `test/neoplay_companion_contract_test.py`.
- Comparaison : 60 tests Python concernés, exécutés avant (HEAD) et après le retrait, ont donné les mêmes résultats, sauf les deux tests adaptés. Les échecs restants existaient déjà à HEAD (pas de Flutter ni de macOS dans le conteneur, ou portails historiques).

En CI :

- `launch-ui-checks.yml` exécute l'analyse Flutter complète, les tests Dart touchés et ces contrôles ;
- `neoplay-check.yml` (tâche `native`) exécute `test/neoplay/companion_tests.swift`.

Les runs et leurs résultats sont consignés au § 7.

Aucune validation sur iPhone n'est revendiquée.

## 6. Procédure pour les joueurs qui veulent KartPad

KartPad devient une application séparée, construite par chaque joueur sur son propre ordinateur, à partir de son propre disque. NeoStation n'intervient plus et ne distribue rien de KartPad.

1. **Récupérer KartPad et PadMint.** Prendre l'IPA officielle sans jeu (`KartPad-v0.8.3-ios-for-padmint.ipa`) et PadMint sur la page des releases de KartPad (https://github.com/chrissotraidis/kartpad/releases), en suivant ses instructions.
2. **Construire son IPA personnelle.** PadMint compile le pack de jeu à partir du disque PAL du joueur (RMCP01, révision 0) et l'ajoute à l'IPA. L'IPA personnelle reste sur l'ordinateur du joueur : on ne la partage pas.
3. **Installer et signer.** Installer cette IPA avec SideStore, comme une application à part. Elle ne remplace pas NeoStation et n'a pas besoin de lui.
4. **Reprendre sa sauvegarde (facultatif).**
   - Dans NeoStation, la sauvegarde se trouve dans `Fichiers › NeoStation › Ports › KartPad › Saves › NAND › title › 00010004 › 524d4350 › data › rksys.dat`.
   - Dans KartPad 0.8.3, passer par le menu en jeu, puis Game Data › Manage Saves…, et restaurer ce `rksys.dat` (2 867 200 octets).
   - Ne sont pas inclus : les Mii et l'identité de console (donc le code ami).
5. **Mettre à jour.** Une nouvelle version de KartPad demande de reconstruire son IPA avec PadMint. Un pack compilé pour une version ne vaut que pour une interface identique : son empreinte doit correspondre à celle du nouveau moteur.

## 7. Résultats CI et livraison

À compléter avec les runs réels. L'IPA du retrait se construit après la fin des compilations en cours (Build 490 de l'autre session), avec son propre numéro, sa porte de livraison et son reçu.
