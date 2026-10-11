# Build 445 — par-dessus la Build 444

Demandes du mainteneur :
- pendant la Build 444 : « attends que le build 444 soit fini pour pouvoir
  lancer le build 445 par-dessus celle-ci » ;
- le 12 octobre 2026, une fois la 444 livrée : « reprend l'intégration du
  build 445 », puis « tu conserves toutes les améliorations et correctifs du
  build 444 et tu ne fais que construire par-dessus lui ».

Aucun correctif n'est demandé pour cette build.

## Base

La Build 444 est livrée depuis `a221ae0c66fedb1f899d16eaadaf3877a14f8349`
(run `38182831110`, IPA SHA-256 `a06c4d46…ebeade`, voir
`docs/build444-delivery.md`).

La 445 part de ce commit et de ses deux commits de documentation
(`4faa514b`, `9339daac`). Rien de la 444 n'est retiré ni remplacé :
- RPCS3 / LLVM / NeoSwap et le Core épinglé `dcf0df67` / run `38178247609` ;
- le pont libretro et son cycle tactile/skins (`4da31544…1e210a28`) ;
- les Builds 442 et 443.

`git diff a221ae0c` est vide sous `lib/`, `packages/`, `native/`, `assets/`,
`pubspec.yaml` et `pubspec.lock` : les sources du produit sont identiques.
L'IPA ne diffère de la 444 que par :
- le numéro de build ;
- le SHA source qu'elle enregistre (`NeoPlay-build-identity.json`, rapports
  intégrés) ;
- sa signature et son scellement.

## Ce que la 445 ajoute (aucun fichier produit)

1. **Clé de livraison.** `build-utils/delivery-445-recipient.pem` est une clé
   publique RSA-3072 :
   - empreinte DER SHA-256
     `ec179354f43da31a57791e3bf48b2556dbe715751d569dce2ac59323450f3f3c` ;
   - passée par l'entrée `recipient`, comme `AGENTS.md` le prévoit depuis la
     444 ;
   - déclarée dans `BUILD445_DELTA` (`build-utils/verify_delivery_reuse.py`).

   La clé privée reste hors du dépôt, dans le conteneur de la session qui
   remet l'IPA. Le mainteneur autorise `*.blob.core.windows.net` pour le
   téléchargement de l'artefact.
2. **Contrôle de livraison.** `test/libretro_skin_catalogs_test.dart` (19
   tests) rejoint la première commande Dart de
   `.github/workflows/retroarch-delivery.yml`. Jusqu'ici, il ne tournait que
   dans `libretro-checks.yml`. Le workflow modifié change la clé des preuves
   Dart : les tests Dart sont exécutés à nouveau au lieu d'être réutilisés
   depuis la 444.

## Vérifications locales (Linux, Flutter 3.47.2, historique complet)

- `verify_delivery_reuse.py --offline --scope full` : code de sortie 0.
- Garde-fous Python de la livraison réussis :
  - `retroarch_baseline_scope` ;
  - `delivery_pipeline` (13 tests, avec `zstd`) ;
  - libretro : route, shaders, contrat d'interface, cœurs et BIOS sans
    binaires ;
  - onglet d'import, 12 langues, triches/médias ;
  - orientation du lecteur, donneur NeoSwap ;
  - Dolphin Shake et écran externe (contrats source ; leur exécution demande
    macOS) ;
  - RAP et état RPCS3, 120 Hz.
- Première commande `flutter test` de l'étape Dart de la livraison (28
  fichiers, dont les catalogues) : 233 tests réussis. Les autres commandes de
  l'étape (`library_*`, NeoSwap, Builds 440/442) et l'analyse Dart n'ont pas
  été relancées localement ; le run de livraison les exécute.
- Aller-retour du chiffrement vérifié avec la clé 445 : enveloppe RSA de
  384 octets, même format que les clés précédentes.
- Hors contrôle de livraison : `import_memory_candidate_scope_test.py` échoue
  déjà sur `9339daac` (sources de la 444 et sa documentation). Il s'arrête sur
  `.github/workflows/dolphin-motion-check.yml`, mais 53 des 269 empreintes
  approuvées de `native/import-memory-candidate.json` ne correspondent plus.
  Leur rafraîchissement revient au mainteneur (audit 444) ; la liste n'est pas
  modifiée ici.

## Lancement

- **Lancement.** `retroarch-delivery.yml` est lancé sur `Claude`, seulement
  quand aucune livraison n'est en cours, avec :
  - `build_number=445` ;
  - `validation_scope=full` ;
  - `benchmark=false` ;
  - `recipient=build-utils/delivery-445-recipient.pem`.

  Le `head_sha` du run doit être le SHA 445, et la clé publique doit être
  présente dans l'arbre de ce SHA avec la même empreinte.
- **Remise de l'IPA.**
  1. L'artefact chiffré est téléchargé et rapproché de l'empreinte SHA-256
     GitHub.
  2. Il est déchiffré avec la clé de la session (OAEP SHA-256, AES-256-CBC
     PBKDF2, `build-utils/delivery_cipher.py`).
  3. L'IPA est contrôlée contre `SHA256SUMS` et `signed-payload-identity.json`,
     puis remise au mainteneur.

L'IPA est préparée ad hoc pour la re-signature par SideStore. Aucune
installation, aucun comportement ni aucune fluidité sur iPhone n'est
revendiqué avant l'essai du mainteneur.

## Production

À compléter : run, nom, taille et SHA-256 de l'IPA, durées observées.
