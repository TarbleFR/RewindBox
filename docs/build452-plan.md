# Build 452 — import du BIOS 3DS depuis le menu de la console

Demande du mainteneur, avec une vidéo : « analyse la vidéo et lis le message d'erreur pour le bios de la 3ds, j'ai
tout essayé ! il n'importe aucun de mes fichiers ».

Base : Build 451 (`c65efd42e09da3d1a1f27e59644a4ad2c7875902`).
- Aucun cœur, natif, helper JIT ni fichier verrouillé sur la Build 419 n'est modifié.
- `pubspec.lock` est identique.
- `pubspec.yaml` passe à `0.0.7+452`.

## Ce que montre la vidéo

- **Écran.** Page de la console Nintendo 3DS de la bibliothèque (Mario Kart 7), menu d'import : « Importer des
  jeux », « Copier les sauvegardes et BIOS de RetroArch », « Skins ».
- **Action.** Le mainteneur choisit « Copier les sauvegardes et BIOS de RetroArch », puis l'un de ces dossiers :
  - son dossier Azahar (`iCloud Drive › 1-Corentin › 3ds › Azahar`) ;
  - `nand` (6 éléments) ;
  - `sysdata` (`otp.bin` 256 octets, `mcu.dat`, `mac`, `play_time.bin`…).
- **Message.** Chaque fois : « Aucune sauvegarde, aucun état ni fichier système RetroArch trouvé dans le dossier
  choisi. »

**Cause.** Cette action ne cherche que les dossiers `saves`, `states` et `system` d'une installation RetroArch. Un
dossier Azahar n'en a aucun. L'import qui le lit n'était proposé que dans Consoles › Nintendo 3DS › « Réglages
système » › « Importer des données système », et le menu de la console, là où l'on cherche le BIOS 3DS, ne le
proposait pas. Les fichiers du mainteneur ne sont pas en cause.

## Correctif

| Élément | Contenu |
| --- | --- |
| Menu de la console 3DS | Nouvelle entrée « BIOS et fichiers système 3DS ». Elle ouvre la page Nintendo 3DS avec son assistant d'import déjà lancé (Un ZIP, Un dossier, Fichiers isolés). |
| Copie RetroArch | Elle reconnaît un dossier Azahar, Citra ou Lime3DS (`nand` ou `sysdata`, au plus deux niveaux plus bas). Quand rien n'est copié, elle l'explique au lieu de dire « rien trouvé ». Le bouton « Importer des données système » ouvre l'assistant 3DS ; il existe dans la bibliothèque et dans le vérificateur de BIOS. |
| Textes | `import3dsSystem` et `retroArch3dsFolder`, en douze langues. |
| Porte de livraison | Bloc `BUILD452_DELTA` : 11 entrées revues depuis `c65efd42`. |

L'import 3DS lui-même est inchangé ; il garde les règles des Builds 448 à 451. Détail :
`docs/libretro-3ds-system-settings.md` § 10.

## Pour le dossier du mainteneur

1. Dans Fichiers, téléchargez d'abord le dossier Azahar sur l'iPhone : maintenez le doigt sur le dossier ›
   « Télécharger maintenant ». Un fichier resté dans iCloud est signalé, jamais lu.
2. Dans la page de la console Nintendo 3DS, ouvrez le menu d'import et touchez « BIOS et fichiers système 3DS ».
3. Choisissez « Un dossier », puis le dossier `Azahar`.
4. Cochez « Inclure les données de console », puis installez.

Avec `sysdata/otp.bin`, les titres système chiffrés par Azahar pour la console sont installés (Build 451).

## Vérifications

Exécuté dans ce conteneur (Linux x86_64, Flutter 3.47.2) :

| Contrôle | Résultat |
| --- | --- |
| Tests des fichiers concernés : actions de la bibliothèque, vérificateur de BIOS, écran et service 3DS, catalogue `libretro_locale`, réglages du moteur, onglet Consoles | 195 tests réussis, dont 7 nouveaux |
| Contrats Python : interface libretro (textes de `LibretroLocale`), onglet d'import, couverture des douze langues, stockage, routes | réussis |
| `flutter analyze` des fichiers Dart modifiés | aucun problème |
| Porte `verify_delivery_reuse.py --offline` (bloc `BUILD452_DELTA`) | réussie |
| `delivery_pipeline_test.py` | 13 sur 13 |

## Ce qui n'est pas vérifié

Aucun essai sur iPhone : ni l'entrée de menu, ni l'import du dossier Azahar du mainteneur, ni un lancement 3DS avec ses
titres système.
