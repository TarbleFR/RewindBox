# Build 449 — recopie AirPlay de l'interface, version 0.0.7, import 3DS depuis iCloud Drive

Demandes du mainteneur (12-13 octobre 2026), en cours de chantier « catalogue de shaders » :

- **AirPlay / Apple TV** : « je veux que l'Apple TV affiche exactement la même interface NeoStation que celle
  visible sur l'iPhone via AirPlay » ; aujourd'hui le téléviseur n'affiche que le logo de la console pendant la
  navigation, alors que les jeux s'affichent correctement ; identifier précisément la cause (Flutter, vues natives,
  AVPlayer, sans supposer les vidéos), correctif ciblé, sans casser les améliorations AirPlay existantes, sans
  refonte inutile.
- **Version** : « baser la future compilation sur la 0.0.7 » (les livraisons portaient toujours 0.0.2).
- **3DS** : « je ne peux toujours pas importer un dossier Nand-zip pour la 3DS ».

Base : Build 448 (`36567551838130bb34abe48f93177ac3cef15f1c`). Aucun cœur, helper JIT, réglage d'émulation ni
fichier verrouillé sur la Build 419 n'est modifié ; `pubspec.lock` est identique ; `pubspec.yaml` ne change que
par sa version.

## Chantiers

| Chantier | Commits | Contenu |
| --- | --- | --- |
| AirPlay | `7eae3dd1`, `1afa598c` | hors jeu, la fenêtre externe quitte sa scène : iOS recopie l'iPhone ; plus de menu du second moteur sur le téléviseur ; rangée « Afficher le menu sur le téléviseur » retirée ; textes en douze langues |
| Version | `3348b3e5` | `0.0.7+449` ; portes d'IPA lisant la version de `pubspec.yaml` |
| 3DS | `7e4aef05` | fichiers système encore dans iCloud Drive signalés (refus `notDownloaded`, douze langues) au lieu de « non reconnu » |

## Cause AirPlay (détail : `docs/external-display-universal.md` § 10)

Depuis la Build 447, l'hôte déclare le rôle d'écran externe et le coordinateur crée une fenêtre dans la scène
AirPlay : la recopie système s'arrête. Hors jeu, il y plaçait le second moteur Flutter (`externalDisplayMain` →
`SecondaryScreen`, l'écran secondaire des consoles portables Android : logo et fond de la console sélectionnée),
réglage actif par défaut ; ce n'est pas l'interface de NeoStation. Les cas « recopie » masquaient seulement la
fenêtre, alors qu'Apple indique de la retirer de la scène. Les lecteurs vidéo ne sont pas en cause.

Le correctif garde l'affichage des jeux sur le téléviseur (Builds 442/447 : plein écran, Adapter / Remplir /
Format d'origine, rendu libretro à la résolution du téléviseur, commandes sur l'iPhone). Limite : la recopie
système garde le format de l'iPhone, d'où des bandes autour de l'interface sur un téléviseur 16:9.

## Où se trouvent les fonctions

- AirPlay : Paramètres › Général › « AirPlay et écran externe » (interrupteur et ligne d'état) et « Format sur
  l'écran externe » ; la troisième rangée a disparu.
- Version : visible dans Réglages iOS › NeoStation et dans SideStore (0.0.7, build 449).
- 3DS : onglet Consoles › Nintendo 3DS › « Réglages système » › « Importer des données système » › Dossier.

## Vérifications

Exécuté dans ce conteneur (Linux x86_64, Flutter 3.47.2) :

| Contrôle | Résultat |
| --- | --- |
| `flutter analyze` des fichiers modifiés | aucun problème |
| Tests Dart AirPlay (rangées, ligne d'état, catalogue, NeoPlay, service, liste des jeux, écran TV, moteurs non pris en charge) | 111 réussis |
| Tests Dart 3DS et catalogue libretro (service, page, langue, chiffrement, défaut de lancement, `libretro_locale_test`) | 125 réussis, dont le nouveau test iCloud |
| Contrats Python external_display, ponts, douze langues, interface libretro | réussis ; contrôle négatif : le coordinateur de la Build 448 échoue au nouveau contrat |
| Porte `verify_delivery_reuse.py --offline` (bloc `BUILD449_DELTA`) | réussie |
| `delivery_pipeline_test.py` | 12 sur 13 ; le test du cache demande `zstd`, absent du conteneur (présent sur la CI) |

CI GitHub (branche `Claude`) :

- `external-display-check` `38324717607` sur `7eae3dd1` : contrats et syntaxe iPhone réussis ; XCTest simulateur :
  les nouveaux tests passent, 4 tests de géométrie échouent (cadre recalé sur la scène de l'iPhone qui tient lieu
  de scène externe) → corrigé par `1afa598c`.
- `external-display-check` `38325569449` sur `1afa598c` : réussi — contrats de source, syntaxe arm64 iPhone de chaque
  source du greffon contre le vrai `Flutter.xcframework`, XCTest simulateur : 18 tests, 0 échec (dont la fenêtre qui
  quitte sa scène hors jeu puis y revient pour un jeu, et « aucun menu sur le téléviseur »).
- `libretro-checks` `38325967145` sur `7e4aef05` : réussi — job `dart` (analyse, tests libretro / lancement /
  bibliothèque dont le nouveau test iCloud, contrats de source) et job `native` (hôte portable, modules du frontend,
  rendu Metal des préréglages, compilation iPhone des ponts).

## Livraison

- Run `retroarch-delivery.yml` `38326750311` (dispatch sur `Claude`, `build_number` 449, périmètre `full`), source
  `ff2a491c83b9eb7477b0e38e6f4a83e4a20680d1` (arbre de `7e4aef05` + ce plan) : jobs `checks`, `native` et
  `Release device build • cold` réussis (00:20 → 00:42 UTC, 13 octobre 2026). L'étape « Align application and
  extension versions to the pubspec version » a posé 0.0.7 (449) dans l'application et ses extensions, et l'étape
  « Package and validate NeoStation IPA » (portes `validate_release002_ipa.py` et `validate_cheat_bulk_ipa.py`
  lisant la version de `pubspec.yaml`) a réussi.
- Artefact remis : `NeoStation-Build-449-ff2a491c83b9eb7477b0e38e6f4a83e4a20680d1-cold` (ID `11781772870`,
  210 115 997 octets, SHA-256 de l'archive `68abff9c0db715ee6f7b56116d50196ffc42ec084164450007e7538dc1675683`,
  conservé jusqu'au 27 octobre 2026), chiffré pour `build-utils/delivery-424-recipient.pem` (clé du PC du
  mainteneur). Le SHA-256 de l'IPA se relève après déchiffrement (`SHA256SUMS` de l'enveloppe) ; il n'est pas
  connu dans ce conteneur, qui ne peut pas télécharger les artefacts.
- Diagnostics chiffrés : `…-cold-diagnostics` (ID `11781942401`, 4 841 817 octets).

## Ce qui n'est pas vérifié

Aucune fonction essayée sur iPhone ni sur Apple TV : recopie de l'interface, retour à la recopie après un jeu,
jeux en plein écran, connexion/déconnexion AirPlay en jeu ; import 3DS depuis un dossier iCloud Drive. Les fichiers
3DS exacts du mainteneur ne sont pas connus : d'autres causes restent possibles (ZIP de plus de 2 000 entrées,
image NAND brute, titres système chiffrés ; `docs/libretro-3ds-system-settings.md` § 8).
