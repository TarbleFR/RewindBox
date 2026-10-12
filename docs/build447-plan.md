# Build 447 — grande mise à jour : AirPlay universel, Nintendo 3DS, livres et mangas 3D, analyse du stockage

Demande du mainteneur du 12 octobre 2026 : cinq chantiers (AirPlay universel ; Nintendo 3DS : langue, région,
données système ; livres et mangas 3D ; musique d'ambiance « Fairy Lights » ; analyse et nettoyage du stockage),
précédés d'un audit complet (`docs/grande-mise-a-jour-audit-2026-10-12.md`), chaque fonction placée dans l'interface
et traduite dans les douze langues, et un rapport final distinguant le démontré, les hypothèses, les tests exécutés
ou ignorés et la validation sur iPhone.

Réponses du mainteneur du 12 octobre 2026 : version d'iOS de l'iPhone de test inconnue (les deux régimes de scène
externe sont couverts) ; cœurs libretro ré-épinglés immédiatement ; chantier musique **reporté** ; **une seule IPA**
en fin de cycle, construite par-dessus la Build 446. Les autres décisions suivent le § 11 de l'audit.

Base : Build 446 (`8ceeb055c67688442b637a5a0f48dfbcd4f8ae9a`). Le produit change (`lib/`, `packages/`, `assets/`,
`pubspec.yaml`) ; `pubspec.lock` est identique (aucune dépendance ajoutée) ; aucun cœur, helper JIT ni fichier
verrouillé sur la Build 419 n'est modifié.

## Chantiers

| Chantier | Contrat et écarts | Commits | État |
| --- | --- | --- | --- |
| 0. Cœurs libretro | § 11 de l'audit | `8a93e76d` | ré-épinglés sur le run `38195212647` (artefact `LibretroCores-ba3dc14d…`, rétention jusqu'au 26 octobre 2026) |
| 1. AirPlay universel | `docs/external-display-universal.md` | `7daade2c`, `e341644d`, `2f7f6f53`, `7af619d2` | implémenté, revue contradictoire corrigée |
| 2. Nintendo 3DS | `docs/libretro-3ds-system-settings.md` | `379e5906`, `9df9df63` | implémenté, revue contradictoire corrigée |
| 3. Livres et mangas 3D | `docs/library-books-3d-plan.md` | `7cea2c58` … `72b96dd2`, `618bf1cc` | implémenté, revue contradictoire corrigée (§ 7.12) |
| 4. Musique « Fairy Lights » | — | — | **reporté** par le mainteneur (fichier et licence inaccessibles depuis le conteneur) |
| 5. Analyse et nettoyage du stockage | `docs/storage-audit-cleanup.md` | `3c8e92d4` … `03921328`, `a4bfa1bf`, `af3cec8a` | implémenté, revues contradictoires des pages (§ 9.6) et des services (§ 9.7) corrigées |

## Où se trouvent les fonctions

- **AirPlay et écran externe** (iOS) : Réglages › Général, rangées « AirPlay et écran externe », « Format sur l’écran
  externe » (Automatique, Adapter à l’écran, Remplir l’écran, Format d’origine) et « Afficher le menu sur le
  téléviseur ». Hors jeu, le téléviseur montre le menu de NeoStation ; en jeu, l'image de Dolphin, libretro, RPCS3
  ou ARMSX2 ; Dusklight et KartPad restent en recopie d'iOS.
- **Nintendo 3DS** : onglet Émulateurs du système Nintendo 3DS › « Réglages système » › page « Système Nintendo 3DS »
  (langue du système, région, modèle de console, import et restauration des données système).
- **Livres et mangas 3D** : Bibliothèque (couvertures en volume, ouverture animée) ; dans les lecteurs CBZ/en ligne,
  PDF et EPUB/TXT, barre d'outils (Réglages en trois sections, Marque-pages, Sommaire ou Chapitres, Progression,
  Bibliothèque), pli de page ou glissement, doubles pages en paysage, Y pour un marque-page.
- **Analyse et nettoyage du stockage** (iOS) : Réglages › Outils › « Analyse et nettoyage du stockage ». Rien ne
  s'exécute au démarrage ni en arrière-plan.

## Vérifications

Quatre revues contradictoires en lecture seule ont précédé la livraison (AirPlay, 3DS, pages du stockage, puis
livres et services du stockage), et tous leurs constats confirmés ont été corrigés avant la compilation ; les
corrections sont décrites dans les documents des chantiers.

Exécuté dans ce conteneur (Linux x86_64, Flutter 3.47.2), sur un arbre dont toutes les entrées sont identiques à la
source livrée `af3cec8a` (seule la documentation diffère), et comparé à la même exécution sur la source de la
Build 446 (`8ceeb055`) :

| Contrôle | Source 446 | Build 447 |
| --- | --- | --- |
| `verify_delivery_reuse.py --offline` (arbre fermé, blocs `BUILD447_*_DELTA`) | — | réussi |
| Gardes d'identité des cœurs (RPCS3, Dolphin, ARMSX2, Dusklight, libretro, KartPad), simulées | — | 6/6 identiques |
| Contrats Python du job `checks` (27, plus `library_books_3d_contract_test.py`) | — | tous réussis |
| `flutter analyze` | 52 remarques « info » | les mêmes 52, aucune dans les fichiers du cycle |
| Suite Dart complète (`flutter test`) | 2 027 réussis, 6 échecs, 4 ignorés | 2 836 réussis, 6 échecs, 5 ignorés |
| Suite Python complète (`test/*_test.py`) | 175 fichiers : 111 réussis, 64 en échec | 186 fichiers : 123 réussis, 63 en échec |

Les 6 échecs Dart sont les mêmes des deux côtés et ne font partie d'aucun job de livraison :
`dolphin_import_ui_test.dart` (×2), `dolphin_isolation_contract_test.dart` (×2) et
`rpcs3_import_spu_build230_contract_test.dart` (×2). Les 63 échecs Python existaient tous sur la source 446 : tests
qui exigent macOS/Xcode ou une chaîne native, ou contrats historiques épinglés sur d'anciennes builds
(`neoplay_build397_integration_test.py`, `library_cover_delivery_test.py`, `import_memory_candidate_scope_test.py`,
etc.). `dolphin_external_display_ui_test.py`, en échec sur la 446, réussit désormais. Les onze fichiers Python ajoutés
par le cycle réussissent. Le test ignoré en plus est celui du scanner sur un dossier `chmod 000`, sans effet sous
root.

CI GitHub sur la branche `Claude` (macOS 15 et Ubuntu 24.04) : « Libretro engine checks » réussi sur `2f7f6f53`
(`38236315530`), `6f324d5c` (`38241491806`), `9df9df63` (`38250331035`), `7af619d2` (`38250873346`), `03921328`
(`38255805078`) et `a4bfa1bf` (`38270662532`) et `af3cec8a` (`38286806044`) ; « External display (AirPlay universal) native
checks » réussi sur `2f7f6f53` (`38236315498`) et `7af619d2` (`38250873420`) ; « Libretro simulator probe » réussi
sur `379e5906` (`38234814135`) et `7af619d2` (`38250873449`).

Non exécuté ici : XCTest et compilation iPhone (CI macOS seulement), et tout essai sur appareil.

## Livraison

| Élément | Valeur |
| --- | --- |
| Source | `af3cec8af0a373641abbf0b11a286bf2c7d5cb03` (branche `Claude`) |
| Run | `retroarch-delivery.yml` `38286881882` (build 447, périmètre `full`), 17 h 50 → 18 h 11 UTC le 12 octobre 2026 ; jobs `checks` (tests Dart exécutés à `af3cec8a`, non réutilisés), `native` et « Release device build • cold » réussis |
| Cœurs et moteurs | identités vérifiées par la livraison : RPCS3 `dcf0df67` (run `38178247609`), Dolphin `ae7d46f9`, ARMSX2 `899d3c44` (run `37641466835`), Dusklight `899d3c44` (run `37641472546`), cœurs libretro `ba3dc14d` (run `38195212647` ; validation de l'IPA : nestopia, snes9x, gambatte, mgba, genesis_plus_gx, genesis_plus_gx_wide, picodrive, fbneo, desmume, mupen64plus_next, mednafen_psx_hw, mednafen_psx, ppsspp, azahar), KartPad `3934ac9d` (run `36322395443`) |
| Artefact | `NeoStation-Build-447-af3cec8af0a373641abbf0b11a286bf2c7d5cb03-cold` (identifiant `11764636973`), 208 284 573 octets, SHA-256 de l'archive `bec0ee1daa0fe829d65fd2949eba71dc9f8a452342eec9bd223891f4fee8c9da`, conservé jusqu'au 26 octobre 2026, 18 h 11 UTC ; chiffré pour `build-utils/delivery-424-recipient.pem` |
| IPA | `NeoStation-Build447-af3cec8af0a373641abbf0b11a286bf2c7d5cb03-cold.ipa`, dans l'archive chiffrée ; son SHA-256 et sa taille sont dans `SHA256SUMS` et `signed-payload-identity.json` (`ipaSha256`, `ipaBytes`) et restent **à consigner après le déchiffrement** (illisibles depuis le conteneur de cette session). Le hash `08d53732…` imprimé par l'étape d'empaquetage est celui de l'IPA avant le scellement pour SideStore, qui la recrée : ce n'est pas l'IPA livrée. |

Destinataire : le PC du mainteneur était hors ligne pendant la livraison, et la clé privée 445 n'existe que dans le
conteneur temporaire de cette session ; l'artefact est donc chiffré pour la clé 424, que détient le mainteneur (comme
la 446), afin qu'il reste déchiffrable après la fin de la session.

Déchiffrement (PC du mainteneur, avec sa clé privée 424 et l'`openssl` de Git) : télécharger l'artefact du run,
vérifier que le SHA-256 de l'archive vaut `bec0ee1d…c9da`, l'extraire (`artifact.tar.enc`, `password.rsa`,
`format.json`), puis :

```
openssl pkeyutl -decrypt -inkey neostation-delivery-424.key -in password.rsa -out password -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256
openssl enc -aes-256-cbc -d -pbkdf2 -iter 200000 -salt -pass file:password -in artifact.tar.enc -out artifact.tar
tar -xf artifact.tar
```

Comparer le SHA-256 de l'IPA à `SHA256SUMS` et à `signed-payload-identity.json`, puis supprimer `password` et
`artifact.tar`. L'IPA est scellée pour la re-signature Apple et le provisioning que SideStore applique ; la signature
ad hoc de préparation ne les remplace pas. Ne pas réutiliser le numéro 447.

## Ce qui n'est pas vérifié et protocole sur iPhone

Aucune fonction de cette build n'a été essayée sur un iPhone, une Apple TV ou un adaptateur. À vérifier, dans
l'ordre, en relevant la version d'iOS :

1. **AirPlay** (`docs/external-display-universal.md` § 9) : connexion automatique de la scène externe ; menu sans
   bandes ; un jeu par moteur (Dolphin, libretro dont 3DS, RPCS3, ARMSX2) en Adapter puis Remplir ; connexion et
   déconnexion en jeu ; retour au premier plan ; Dusklight et KartPad en recopie ; changement de langue ; journal
   `display.external_*`.
2. **Nintendo 3DS** (`docs/libretro-3ds-system-settings.md` § 1, § 5) : langue Automatique et choisie, région,
   modèle à la session suivante ; contenu de `Documents/Libretro/Config/Azahar.json` ; import d'un dossier de
   données système, puis restauration de la sauvegarde.
3. **Livres** (`docs/library-books-3d-plan.md` § 6) : un CBZ, un PDF, un EPUB et un chapitre en ligne, en portrait
   et en paysage ; pli (`library.reader.curl:shader` ou `painter` dans le journal), doubles pages, marque-pages, Y à
   la manette, « Réduire les animations » d'iOS, VoiceOver.
4. **Stockage** (`docs/storage-audit-cleanup.md` § 7) : première analyse exportée en agrégats **sans nettoyage**,
   comparée aux Réglages iOS ; puis niveau Sûr seul et nouvelle analyse ; seulement ensuite niveau Régénérable.
