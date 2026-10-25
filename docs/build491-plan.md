# Build 491 — Build 490 + Canvas (ES-DE) + retrait de KartPad, 20 octobre 2026

Choix du mainteneur du 20 octobre 2026 : « 490 + Canvas + retrait ». La Build 491 est la Build 490 livrée (tag `build-490` = `d152e5a2`, run `39346406673`) avec deux changements de la branche `Claude` :

- **Canvas (ES-DE)**, source externe d'icônes de systèmes dans Réglages › System Art ([`system-art/Canvas-ES-DE.md`](system-art/Canvas-ES-DE.md)), avec le nettoyage d'analyse de la même session (`libretro_skin_catalog_service.dart`, `texture_catalog_service.dart`, sans changement de comportement) ;
- **retrait complet de KartPad** ([`kartpad-removal-2026-10-19.md`](kartpad-removal-2026-10-19.md)) : aucun framework, pont, hôte ni ressource KartPad dans l'IPA ; le donneur natif Build 350 est récupéré par plages sans aucun membre KartPad ; l'IPA est contrôlée par `build-utils/validate_no_kartpad_ipa.py` (préfixes et fichiers KartPad, puis `game_content_gate`).

Aucun Core reconstruit ; aucune entrée des moteurs, helpers, skins, triches, textures ni des boîtiers 3D ne change : ce sont ceux de la 490 livrée.

## 1. Périmètre

Produit : les sept fichiers Canvas et les fichiers du retrait listés dans `.github/diagnostics/kartpad491_delivery.py` (`CANVAS_PRODUCT`, `KARTPAD_REMOVAL_PRODUCT`). La porte refuse toute autre différence de produit avec la 490, toute entrée de Core modifiée (RPCS3, ARMSX2, paquet libretro), tout changement du catalogue de textures, des ponts des moteurs, de Dusklight et de NeoSwap, et tout retour d'un chemin KartPad.

Fichiers de bibliothèque verrouillés sur la 419 : seules les deux modifications autorisées par le mainteneur pour le retrait (`sqlite_config_provider.dart`, `scanning.dart`), reconstruites à l'envers par `test/retroarch_baseline_scope_test.py` avant la comparaison d'empreinte.

## 2. Contrôle préalable du validateur sur une IPA réelle

`validate_no_kartpad_ipa.py` a été exécuté dans la session sur l'IPA publique 0.0.8 (Build 480, SHA-256 `2e9f1868…825c`, 4 683 membres, 34 cœurs libretro, catalogues de triches et de textures) : 34 membres KartPad refusés et 5 constats de contenu de jeu, **tous dans `KartPadCore` et `KartPadRuntime`** (noms de fonctions traduites, `RVL_SDK`, `RKSystem`, `DWCi_`) ; aucun faux positif dans les cœurs, Dolphin, les catalogues ou les autres frameworks ; 20 s d'exécution.

Constat à signaler : les IPA déjà publiées qui embarquaient KartPad (dont la release publique 0.0.8) contiennent ce runtime de donneur. Conformément à la consigne du mainteneur, aucune release n'est supprimée ni modifiée.

## 3. Vérifications

Contrôles ciblés : `.github/workflows/build491-checks.yml`, `test/build491_targeted_test.py`. Chaque partie vérifie d'abord que ses entrées déclarées couvrent tous les fichiers modifiés depuis la 490 (hors documentation et câblage de livraison), puis :

- **hôte** (Ubuntu 24.04, Flutter 3.47.2) : générateur Canvas (`canvas_es_de.py --check`), `flutter analyze` de toute l'application, la suite Dart de livraison lue dans `retroarch-delivery.yml` (identique ligne pour ligne), les tests Dart modifiés ou concernés (retrait et refus de KartPad en douze langues, Ports et Dusklight, écran externe, aperçus des boîtiers, MD5 en flux, packs System Art externes), les contrats Python modifiés (validateur sans KartPad, porte de contenu, sous-ensemble du donneur, référence 419, notices, stockage, Ports, NeoPlay, statut de fermeture, routes des moteurs) ;
- **natif** (macOS 15, Xcode 26.3) : harnais NeoPlay NPCheck dans le Simulateur iOS 18, qui compile toutes les sources Swift de NeoPlay (dont `NPGameHUDAnchor.swift`) et exécute `test/neoplay/*_tests.swift`.

Résultats, run `build491-checks.yml` `39349740393` sur `59bec98c` (déclenché par la poussée de ses propres fichiers : un workflow absent de la branche par défaut ne peut pas être lancé à la main, et `main` n'est pas modifiée) :

- **hôte**, job `118390848595` (Ubuntu 24.04, Flutter 3.47.2), réussi : couverture des fichiers modifiés, `canvas_es_de.py --check`, `flutter analyze` sans aucun constat (« No issues found »), suite Dart de livraison complète (dont la boucle musicale exacte sur 21 boucles et le passage audio jeu → menu), tests du retrait, des Ports, de l'écran externe, des aperçus des boîtiers, du MD5 en flux et des packs System Art, douze contrats Python (validateur sans KartPad, porte de contenu, sous-ensemble du donneur sans aucun octet KartPad, référence 419, routes, écran externe, statut de fermeture, Ports, stockage, notices, NeoPlay), compilation du lanceur 486 ; 66 entrées hachées dans le verdict ;
- **natif**, job `118390848905` (macOS 15, Xcode 26.3, SDK iPhone 26.2), réussi : harnais NPCheck dans le Simulateur iOS 18.

Un premier commit `44f1dd0a` (sans déclencheur de poussée) n'a lancé aucun contrôle ; le tag `build-491` a été refusé par le proxy Git de la session et n'a pas été contourné : la livraison part de la branche `Claude`, au commit des contrôles.

## 4. Livraison

- Porte : `.github/diagnostics/kartpad491_delivery.py` (produit = 490 livrée + fichiers Canvas et retrait, aucune entrée de Core modifiée, aucun chemin KartPad revenu, verdicts hôte et natif du run ci-dessus sur le commit livré, entrées identiques à l'octet).
- Run `retroarch-delivery.yml` `39350746416` sur `Claude` @ `59bec98c31741c010d827dd2b58949244eb93431` : `checks` (job `118394087441`) et `native` (job `118394086892`) réussis en réutilisant les preuves, `Release device build • cold` réussi (job `118394360196` ; compilation Xcode de 01:04:48 à 01:11:36), `warm` ignoré.
- Donneur natif Build 350 récupéré par plages sans membre KartPad, contrôlé par `game_content_gate.py` ; IPA contrôlée par `validate_no_kartpad_ipa.py` : « No KartPad and no game-origin file in NeoStation.ipa (4521 members inspected) ». IPA validée avant scellement : SHA-256 `c02024fcfe3e19e9764ac7eb5b0ce3a79c050ca7b221798c9cb1947bc4d4f7a3` (174 Mio) ; le scellement SideStore recrée l'IPA, dont le SHA-256 n'est que dans l'archive chiffrée (`SHA256SUMS`, `signed-payload-identity.json`).
- Artefact chiffré `12233906099` `NeoStation-Build-491-59bec98c…-cold` (186 674 077 octets, archive SHA-256 `12f989d5f64f97665e166433b553a52a7bb6a30df74d8f9c19e248f583fb962c`, conservé jusqu'au 3 novembre 2026), chiffré pour `build-utils/delivery-424-recipient.pem` (clé du PC du mainteneur). L'archive est plus petite de 41 969 664 octets que celle de la 490 (`228 643 741`), ce qui correspond au retrait de `KartPadCore` et `KartPadRuntime`.
- Clé `build-utils/delivery-491-recipient.pem` : créée pour ce cycle, non utilisée par cette livraison (la clé privée correspondante est restée hors Git, dans le conteneur de la session).
- Remise du premier artefact impossible : le mainteneur a supprimé la clé privée 424 de son PC (20 octobre 2026). L'artefact `12233906099` ne peut plus être déchiffré par personne ; il n'est pas remis et son IPA scellée n'a pas d'empreinte relevée.
- Seconde livraison, même produit : run `retroarch-delivery.yml` sur `Claude` (commit postérieur ne contenant que les enregistrements de livraison et cette porte), artefact chiffré pour `build-utils/delivery-491-recipient.pem`, dont la clé privée reste dans le conteneur de la session. Seule l'enveloppe de l'artefact (`password.rsa`, 256 octets) est déchiffrée dans le conteneur ; le PC du mainteneur télécharge et déchiffre l'archive avec le mot de passe de session, supprimé ensuite. La porte accepte les contrôles du run `39349740393` sur `59bec98c` parce que tout ce qui a été commité depuis est de la documentation ou du câblage de livraison (`records_only`), et compare toujours chaque entrée testée à l'octet. Identités : § 5.
- Aucune validation sur iPhone. Ne pas réutiliser le numéro 491.

## 5. Livraison remise

- Source : `Claude` @ `9faa3f9b07f93b4fdca19a0a325a9180fe75b20f` (produit identique à `59bec98c` ; depuis, seulement la documentation et la porte). La porte a relu les verdicts du run `39349740393` sur `59bec98c` (ancêtre ne différant que par des enregistrements) et comparé chaque entrée testée à l'octet.
- Run `retroarch-delivery.yml` `39353891715` : `checks` (job `118404161815`) et `native` (job `118404161606`) réussis en réutilisant les preuves, `Release device build • cold` réussi (job `118404417119` ; compilation Xcode de 01:36:30 à 01:42:12 UTC), `warm` ignoré. IPA contrôlée sans KartPad ni fichier d'origine jeu (4 521 membres avant scellement) ; IPA validée avant scellement `f64495cfdd1ca2dc359e74bd2df95a3881a4c79007cdcb524bb2993a4dfad9cc` ; signature de l'application « valid on disk » et conforme à son exigence désignée.
- Artefact chiffré `12235290471` `NeoStation-Build-491-9faa3f9b…-cold` (186 674 205 octets, archive SHA-256 `7d1c001cfe3488fa09a048c5d6c5ba9269a66c2769152c5e244995ac62285e64`, conservé jusqu'au 3 novembre 2026), chiffré pour `build-utils/delivery-491-recipient.pem`. Le PC du mainteneur a téléchargé l'archive (empreinte égale à celle publiée par GitHub) ; seule l'enveloppe de 512 octets a été déchiffrée dans le conteneur ; le mot de passe de session a servi une fois sur le PC puis a été supprimé des deux côtés ; la clé privée 491 a été supprimée du conteneur après la remise : cet artefact ne peut plus être redéchiffré.
- **IPA 0.0.8 (491)** `NeoStation-Build491-9faa3f9b…-cold.ipa`, **186 428 464 octets**, SHA-256 **`ad3963793fc4ca19b89f46613f9cdf139ec5c5bfa202d0132e7698413aeb894e`**, égal à `SHA256SUMS`, à `signed-payload-identity.json` et à la copie `C:\Users\Coren\Downloads\NeoStation-Build491-9faa3f9b.ipa` (relue après copie). Dossier de travail du PC supprimé.
- Inspection indépendante de l'IPA scellée sur le PC (Python 3.13.7) : `validate_no_kartpad_ipa.py` du commit livré réussi (4 661 membres, aucun membre KartPad ni fichier d'origine jeu) ; six bundles en 0.0.8 (491) (application et cinq extensions) ; 72 frameworks ; dans le code Dart, marqueurs Canvas (`CanvasESDE`, `zenandiko/canvas-es-de`, révision `12d03b18…`) et `kartpadRemoved` présents, canal `neostation/kartpad_internal` et route `ios_kartpad_internal` absents. Contrôle négatif du même vérificateur sur l'IPA publique 0.0.8 : refusée (KartPad, build 480). La comparaison image par image avec la 490 n'a pas été faite : l'IPA 490 n'existe plus sur le PC.
- Re-signature SideStore requise. Aucune validation sur iPhone. Ne pas réutiliser le numéro 491. Reçu : [`evidence/kartpad491-delivery.json`](evidence/kartpad491-delivery.json).
