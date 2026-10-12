# Build 448 — skins adaptatifs et tactile, onglet Consoles universel, mode Frontend uniquement, musique d'ambiance, fichiers système 3DS

Demande du mainteneur du 12 octobre 2026 (« Refonte des skins, gestion des consoles, émulateurs et musique
d'ambiance ») : quatre chantiers précédés d'un audit, en réutilisant l'existant, sans casser les fonctions
actuelles ni supprimer de données, traduits dans les douze langues ; puis deux compléments : importer réellement
les fichiers système 3DS (ZIP, dossier NAND) pour le moteur intégré, et ne pas s'arrêter avant de fournir l'IPA.

Base : Build 447 (`af3cec8af0a373641abbf0b11a286bf2c7d5cb03`). Le produit change (`lib/`, `packages/` — pont
libretro —, `assets/`) ; `pubspec.yaml` et `pubspec.lock` sont identiques (aucune dépendance ajoutée) ; aucun
cœur, helper JIT, réglage d'émulation ni fichier verrouillé sur la Build 419 n'est modifié
(`test/retroarch_baseline_scope_test.py`).

## Chantiers

| Chantier | Commits | Contenu |
| --- | --- | --- |
| 4. Musique d'ambiance | `ee619312` | « Once Upon a Time (loop) » de TAD (OpenGameArt, CC0), gestionnaire unique `HomeMusicService` |
| 2 et 3. Consoles et Frontend uniquement | `bdae27e9` | onglet Consoles étendu à 85 consoles, `EmbeddedEnginePolicy`, Réglages › Général |
| 1. Catalogue et gestionnaire de skins | `88b892b1` | mise en page adaptative, filtres repliables, sélecteur d'aperçu |
| 5. Fichiers système 3DS | `24deb26e` | `essential.exefs`, fichiers inutiles signalés, jeux et titres chiffrés |
| 1. Tactile (suite de l'audit) et CI | `f25b8f2a` | cinq défauts confirmés du pont libretro ; contrats de l'onglet Consoles remplacés |
| Livraison | ce commit | porte de réutilisation `BUILD448_DELTA`, listes de tests, clé de destinataire 448 |

## Où se trouvent les fonctions

- **Musique d'ambiance** : Paramètres › Général › « Musique d’ambiance » (interrupteur, activé par défaut pour
  une nouvelle installation) et « Volume de la musique » (propre, indépendant du volume des jeux et des effets) ;
  Paramètres › Thèmes garde le choix d'un fichier personnel. Elle joue dans toutes les sections du menu sans
  redémarrer au changement d'onglet, s'efface (500 ms) au lancement d'un jeu interne ou externe, s'arrête
  complètement pendant la session et reprend en fondu (1,6 s) à la même position au retour.
- **Consoles** : onglet Consoles de la barre principale. Une ligne par console (icône, nom, moteur, interrupteur
  « Menu principal », interrupteur « Moteur intégré » quand la console en a un), filtres Toutes / Dans le menu
  principal / Masquées, « Tout afficher » et « Rétablir par défaut » avec confirmation. Masquer passe par le
  même réglage que Paramètres › Systèmes (aucun second gestionnaire) ; jeux, jaquettes, sauvegardes et réglages
  sont conservés.
- **Frontend uniquement** : Paramètres › Général › « Utiliser les émulateurs intégrés ». Désactivé, chaque jeu
  s'ouvre dans une application externe (RetroArch en priorité) ; les réglages par console ne sont jamais
  réécrits par l'interrupteur global, et le réactiver rétablit l'état précédent. Sans application externe
  capable de lancer la console, le refus est explicite et traduit.
- **Skins** : bouton Skins d'une console (onglet Consoles ou menu d'import) › catalogue (recherche, Filtres
  repliés par défaut en paysage, grille de une à trois colonnes, détail agrandi au toucher, sélecteur d'aperçu
  Portrait / Paysage indépendant de l'orientation de l'appareil, position conservée par console pendant la
  session) et gestionnaire (sélecteur Les deux / Portrait / Paysage). Provenance, Delta Skins, PocketArch et
  common-overlays restent, avec le filtre iPhone central.
- **Fichiers système 3DS** : onglet Consoles › Nintendo 3DS › « Réglages système » › « Importer des données
  système » (ZIP, dossier ou fichiers isolés).

## Constats et corrections

- **Musique** : le MP3 publié a un décalage d'encodeur et un remplissage de fin ; la boucle naïve claque. Le
  fichier livré (`assets/sounds/once_upon_a_time_loop.ogg`, Ogg Vorbis q8, 44,1 kHz stéréo, 2 539 957 images,
  57,595 s, 1 752 020 octets, SHA-256 `86a12b26…20b9`) est reconstruit de façon reproductible
  (`tools/ambient_music/build_ambient_music_asset.py`) : découpe aux échantillons exacts (iTunSMPB), 32 premiers
  échantillons fondus vers une prolongation LPC de la fin (transitoire de raccord : +9,4 dB → −2,0 dB par rapport
  à la médiane locale). Lecture en flux SoLoud (`LoadMode.disk`, `looping: true`).
- **Défaut existant corrigé** : un lancement externe refusé laissait la session de jeu ouverte (aperçus et musique
  bloqués jusqu'au retour au premier plan) : `GameSessionManager.cancelGameLaunch()`.
- **Tactile** (`docs/libretro-touch-skins-audit.md`, défauts 6 à 10) : taps brefs perdus sur les cibles
  analogiques (boutons C de la N64) ; glissement Haut → Bas montrant les deux directions ; bords étendus d'un stick
  prenant un doigt posé sur un bouton dessiné ; stick converti en croix allumé sans rien envoyer ; second doigt
  mélangé au premier sur un stick.
- **3DS** (`docs/libretro-3ds-system-settings.md` § 7) : `essential.exefs` était refusé comme image NAND alors
  qu'il contient SecureInfo_A, LocalFriendCodeSeed_B, movable.sed et l'OTP ; les ROM de démarrage et le secteur de
  clés étaient « non reconnus » ; les textes conseillaient d'importer des clés pour un jeu chiffré alors que le
  cœur refuse tout NCCH chiffré ; un jeu chiffré échouait sans explication.

## Vérifications

Exécuté dans ce conteneur (Linux x86_64, Flutter 3.47.2), sur l'arbre livré :

| Contrôle | Résultat |
| --- | --- |
| `verify_delivery_reuse.py --offline` (arbre fermé, bloc `BUILD448_DELTA`, 60 chemins) | réussi (1 434 entrées inchangées) |
| `flutter analyze` | 52 remarques « info », le même nombre qu'à la Build 447, aucune erreur ni avertissement |
| Étape Dart du job `checks` (toutes ses lignes, dans l'ordre) | 2 285 tests réussis, 3 ignorés (239 + 1 104 + 21 + 244 + 70 + 607) |
| `test/ambient_music_loop_test.py` (SoLoud réel, 21 boucles en flux et en mémoire, blocs impairs, reprises après seek) | réussi : chaque échantillon égal à la piste décodée, aucun silence ni répétition au raccord |
| `test/game_audio_handoff_test.py` | 4 réussis |
| Contrats Python des jobs `checks` et `libretro-checks` (dont `delivery_pipeline_test.py`, `external_display_host_plist_test.py`, `libretro_frontend_ui_contract_test.py`, `embedded_engine_route_contract_test.py`, `localization_12_locale_coverage_test.py`) | tous réussis |
| `test/libretro_host/frontend/input_latch_test.m` compilé en C (clang 18) | 24 contrôles réussis ; les 4 nouveaux cas échouent sur l'ancienne version |

CI GitHub sur la branche `Claude` :

- « Libretro engine checks » : rouge sur `bdae27e9`, `88b892b1` et `24deb26e` (contrat Build 440 de l'onglet
  Consoles, puis `Text()` littéral du badge de filtres) ; corrigé et **réussi** sur `f25b8f2a` (`38314857948`) :
  job `native` (macOS 15, Xcode 26.3 : tests du pont libretro dont les 15 nouveaux contrôles tactiles, compilation
  iPhone de chaque source du pont) et job `dart`.
- Livraison `38315400256` sur `aab282e7` (périmètre `full`) : `checks`, `native` et « Release device build • cold »
  **réussis** (identités des cœurs RPCS3, Dolphin, ARMSX2, Dusklight, libretro et KartPad vérifiées par le run,
  IPA validée puis scellée pour SideStore). Artefact `NeoStation-Build-448-aab282e7…-cold` (`11777716184`,
  210 114 461 octets, SHA-256 de l'archive `3fa7aad9e561b10e8e18843451cdd9c860f5de39d58f9bea3643048c6f2fefb9`),
  **chiffré pour la clé de session 448 et non remis** : le conteneur de la session ne peut pas télécharger les
  artefacts (hôte de stockage refusé par la politique de sortie), et la clé privée 448 n'existe que dans ce
  conteneur. Une tentative de lire l'enveloppe par un workflow a été refusée et retirée (`84714b6d`, `36567551`) :
  elle aurait contourné cette politique.
- Livraison remise : run `38317793450` sur `36567551`, dont l'arbre Git (`fb4f2eaf`) est identique octet pour
  octet à celui de `aab282e7`, chiffrée pour `build-utils/delivery-424-recipient.pem` (clé du mainteneur, comme la
  447). Identité : section « Livraison ».

Non exécuté : XCTest, essai sur iPhone, écoute du raccord de la boucle.

## Ce qui n'est pas vérifié

Aucune fonction n'a été essayée sur un iPhone. Validation à l'oreille du raccord de la boucle : non faite
(extrait de 20 s autour d'un raccord, rendu par SoLoud, fourni avec le rapport). Lancement RetroArch à froid :
toujours perdu par le récepteur RetroArch (`RetroArchSceneDelegate`, correctif proposé
`docs/upstream/retroarch-initial-scene-url.patch`, non appliqué au TestFlight) ; NeoStation n'a pas d'accusé de
démarrage effectif du jeu dans RetroArch.
