# Build 494 — netteté et lisibilité du texte des dos de boîtiers, 20 octobre 2026

Demande du mainteneur (20 octobre 2026) : « améliore si tu peux encore la netteté et la lisibilité des textes à l'arrière des boîtes ». Construite par-dessus la Build 493 livrée (`013d32ed`, run `39359025363`), dont elle conserve tout le produit. Branche `Claude`, aucune release.

Conception, mesures et limites : [`game-box-3d.md`](game-box-3d.md) § 12.

## 1. Audit (avant toute modification)

- Téléchargement : les dos viennent de ScreenScraper en résolution d'origine (aucun `maxwidth`/`maxheight` dans `mediaJeu.php` ni dans les adresses de `jeuInfos.php`). Aucun gain possible de ce côté.
- Affichage 3D : le dos est décodé à 2 400 px de large (`GameBoxArtSet.detailWidth`) et dessiné en `FilterQuality.medium` sous la transformation de la face : le GPU le réduit par filtrage trilinéaire, ce qui adoucit les petits caractères.
- Vue à plat : décodage jusqu'à 4 096 px, réduit de même par le GPU à l'ajustement.
- Place à l'écran : en portrait, le panneau de la visionneuse prenait sa hauteur naturelle ; mesuré, le dos tourné vers le lecteur faisait 234 pt de large sur un iPhone 14 et n'était plus visible du tout sur un iPhone SE.
- Lecture du dos : `VNRecognizeTextRequest` gardait `minimumTextHeight` par défaut (1/32 de la hauteur de l'image) ; les fixtures natives de la Build 490 avaient un texte de 12 % de la hauteur de l'image, donc ne l'exerçaient pas.

## 2. Périmètre

Fichiers produit (liste fermée dans `test/build494_targeted_test.py`, `PRODUCT`) :
- nouveau : `lib/services/game_box/game_box_sharp_scan.dart` (rééchantillonnage de Mitchell-Netravali, accentuation de la luminosité, fournisseur d'image et rendu tenu à jour pour un écran) ;
- modifiés : `lib/screens/game_box/game_box_inspector.dart` (dos rendu à sa taille, panneau limité à 36 % de la hauteur en portrait avec « Jouer » toujours visible, option « Texte net », feuille d'options défilante) ; `lib/screens/game_box/game_box_scan_viewer.dart` (rendu par zoom, bouton « Texte net », X à la manette) ; `lib/widgets/game_box/game_box_scene.dart` (`GameBoxArt.copyWith(back:)`) ; `lib/services/game_box/game_box_preferences.dart` (`NeoStation.GameBox.SharpText`) ; `lib/services/game_box/box_text_service.dart` (transcriptions version 2) ; `packages/neo_box_reader/ios/Classes/BoxTextRecognizer.swift` (petits caractères, agrandissement des petits scans pour Vision seulement) ; `tools/game_box/strings.json` et le catalogue généré `lib/l10n/game_box_locale.dart` (2 textes, douze langues : 125 textes).

Inchangés : fichiers de bibliothèque verrouillés sur la 419, lancement et moteurs, cœurs, ponts, autres plugins, catalogues, NeoSwap ; aucun Core reconstruit. Seule entrée native modifiée : le recognizer du plugin `neo_box_reader`, lié statiquement à `Runner`.

## 3. Vérifications

Dans la session (Linux, Flutter 3.47.2) :
- petits caractères rendus (Roboto) réduits par le modèle trilinéaire du GPU et par les filtres candidats, comparés au texte dessiné à la taille d'arrivée : tableau du § 12 de `game-box-3d.md` ; Mitchell-Netravali retenu (plus fidèle que le GPU de 0,3 à 0,9 dB aux trois largeurs, aussi net que le texte de référence) ; Lanczos-3, essayé d'abord, s'éloignait de la référence (32,61 contre 33,42 dB à 896 px) et a été écarté ;
- `test/game_box_sharp_scan_test.dart` (7), `test/game_box_sharp_back_test.dart` (10), `test/game_box_text_test.dart` (9) et les suites des boîtiers (103 tests au total) réussis ;
- deux défauts trouvés et corrigés pendant le cycle, chacun avec son test : la largeur visée prenait la première face « dos » trouvée, une facette d'angle de 24 px (rendu de 64 px) — le test mesure maintenant la face réellement dessinée à l'écran ; la feuille d'options débordait de 55 px sur 400 × 600 avec la nouvelle ligne — elle défile ;
- contrôle négatif de la place du boîtier : sans la limite du panneau, les trois cas portrait échouent ;
- aperçus rendus et examinés (iPhone 14 et iPhone SE, dos synthétique couvert de texte) ;
- `test/build494_targeted_test.py --part host` complet : à consigner.

Contrôles ciblés en CI : `.github/workflows/build494-checks.yml` — partie `host` (Ubuntu : couverture de tout fichier modifié depuis la 493, catalogue des textes, `flutter analyze`, suite Dart de livraison lue dans `retroarch-delivery.yml`, nouvelles suites et suites des boîtiers, contrats Python) et partie `native` (macOS 15, Xcode 26.3 : contrôle des douze langues de la 490 avec le nouveau recognizer sur macOS et dans le Simulateur iOS ; petits caractères lus par le recognizer de la Build 493 (contrôle) et par le nouveau ; vérification de type des sources Swift du plugin contre le SDK iPhone et Flutter). Seuils du nouveau recognizer : ≥ 0,85 de similarité pour chaque bloc à 2 000 et 1 000 px de large, à 600 px titre et corps ≥ 0,85, liste ≥ 0,80, encart ≥ 0,75 (mentions légales de 6,6 px relevées seulement) ; aucun bloc à plus de 0,03 sous la Build 493.

Résultats CI : à consigner.

## 4. Livraison

À consigner : runs des contrôles ciblés, porte `.github/diagnostics/gamebox494_delivery.py` (produit = 493 livrée + fichiers 494, seul le recognizer du plugin change côté natif, aucun Core, verdicts réutilisés, jamais relancés), run `retroarch-delivery.yml`, artefact chiffré pour `build-utils/delivery-494-recipient.pem` (clé privée hors Git, dans le conteneur de la session), IPA et SHA-256.

## 5. Protocole sur iPhone

1. Un jeu PS1 ou PS2 avec un dos téléchargé : visionneuse en portrait. Le boîtier occupe l'essentiel de l'écran ; les boutons défilent dans le panneau ; « Jouer » reste visible.
2. « Face arrière » : attendre une demi-seconde immobile ; les petits caractères doivent être nets, sans halo ni franges colorées. Options du boîtier › « Texte net » désactivé : le dos reste net (rééchantillonné) mais moins accentué ; réactiver.
3. Pincer pour zoomer puis relâcher : le texte se précise au relâchement ; tourner le boîtier : aucun saut ni scintillement visible.
4. « Vue à plat » : texte net à l'ajustement, puis après chaque zoom ; bouton « Texte net » en haut (X à la manette) ; le choix est le même dans la visionneuse.
5. « Lire la jaquette » sur un dos qui avait déjà été lu en 493 : une nouvelle reconnaissance (une seule fois), qui doit trouver le corps du texte et les mentions légales ; hors ligne ensuite, la lecture vient du cache.
6. iPhone SE ou petit écran en portrait, puis paysage : boîtier visible, options lisibles et défilantes.
