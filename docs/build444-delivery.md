# Build 444 — livraison vérifiée (12 octobre 2026, 01 h 20)

Cycle RPCS3 / LLVM / NeoSwap demandé le 11 octobre 2026 au soir ; audit,
explication de l'écart God of War III / BladeStorm, correctifs et protocole :
`docs/rpcs3-neoswap-llvm-build444-audit.md`. Le numéro 443 ayant été pris et
livré entre-temps par une autre session (couvertures 3D, `79a5920a`), cette
livraison porte le numéro 444.

## Identité

| Élément | Valeur |
|---|---|
| Source de l'IPA | `a221ae0c66fedb1f899d16eaadaf3877a14f8349` (branche `Claude`) |
| Commits du cycle | `7ec94a8c` (hôte NeoSwap + Core + tests), `f5c0d839` (comparateur), `d96ae671`/`3a3dfb8e` (audit), `4af4618c`/`36d14530` (chaîne du contrôle de périmètre), `dcf0df67` (correctif de compilation Core), `71c93bad` (épingle du Core, entrée `recipient`), `605ca593` (DELTA des entrées libretro de l'autre session), `a221ae0c` (empreintes 444 du garde-fou de baseline) |
| Patch canonique RPCS3 | `f19ec0f82bf830e1d371f0cc2de581f3df26c7beaac1a133d79b9dc04cc7cfb7` (211 sections, 14 régénérées) |
| Core RPCS3 | source `dcf0df67b3edf923d5dd54071f5228e6cf6882b6`, run `rpcs3-core.yml` `38178247609` (réussi en 59 min), artefact `RPCS3Core-dcf0df67…` 28 312 061 octets ; identité vérifiée à l'empaquetage (ABI 30, client 1, stats 1, relais 1) |
| Run de livraison | `retroarch-delivery.yml` `38182831110`, périmètre `full`, 15 min 52 s (`checks`, `native`, `cold` réussis, `warm` non demandé) |
| Artefact | `NeoStation-Build-444-a221ae0c…-cold` (`11718638757`, 207 757 213 octets chiffrés), clé publique `build-utils/delivery-424-recipient.pem` passée par l'entrée `recipient` |
| IPA | `NeoStation-Build444-a221ae0c66fedb1f899d16eaadaf3877a14f8349-cold.ipa`, 207 536 584 octets, SHA-256 `a06c4d460fb6531e2f16f2b06998489d4520cf9a9789694b0ad1212090ebeade` (égal à `SHA256SUMS` et à `signed-payload-identity.json` ; le `ipaSha256` du journal CI est pris avant le scellement) |
| Copie locale | `C:\Users\Coren\Downloads\NeoStation-Build444-a221ae0.ipa` ; déchiffrement dans `C:\Users\Coren\nsw\b444` |
| Environnement | Xcode 26.3 (17C529), SDK iOS 26.2, Flutter 3.47.2 / Dart 3.13.2, macOS 15.7.9 |
| `libRPCS3Core.dylib` dans l'IPA | SHA-256 `416924d5da2895e888667578d773117f219ade8cfecb858e0db08790fd1d94a4` |

Les Builds 442 (Dolphin, sauvegardes RPCS3) et 443 (couvertures 3D) ainsi
que les commits libretro `4da31544…1e210a28` de l'autre session (filtre de
skins, diagnostics tactiles, catalogues) sont dans cette IPA tels que présents
sur `Claude` ; ce cycle ne les a ni modifiés ni validés. Leur contrôle
`Libretro engine checks` (`38182221976`) était en échec au moment de la
livraison ; leurs 17 nouveaux fichiers ont été inscrits dans `DELTA` pour que le
contrôle d'arbre fermé les nomme.

## Vérifications

Exécutées et réussies par le run `38182831110` sur `a221ae0c` :

- `checks` : analyse Dart et tests Dart ciblés validés à `a221ae0c` (clé
  d'entrées verrouillée vérifiée, aucune réutilisation), contrats Python
  (12 locales / 917 clés, KartPad, Wii Shake, démarrage), contrôle d'arbre
  fermé (1 463 entrées inchangées, 749 entrées modifiées toutes nommées dans
  `DELTA`), garde-fou de baseline 419 avec les empreintes 444 des deux fichiers
  `native/neoswap-relay/Backend.cpp/.h`.
- `native` : relais (`relay_backend_test` avec les quatre tests 444), donneurs,
  budget (`neoswap_budget_test` avec l'allocation directe), métriques de don,
  localisations NeoSwap (204 traductions, chinois traditionnel), compilation
  des sources ObjC++ modifiées pour iPhone arm64 ; validation Swift réutilisée
  du run `37844950677` (entrées de transport inchangées, identité comparée).
- `cold` : Core épinglé `dcf0df67` / `38178247609` vérifié par identité,
  compilation Release, empaquetage, contrôles ABI, scellement SideStore.

Exécutées avant la livraison, sur les mêmes sources :

- `rpcs3-core.yml` `38178247609` : tests préalables du Core (dont
  `rpcs3_neoswap_relay_test.py` et `rpcs3_build444_core_delta_test.py` avec
  ASan/UBSan) puis construction complète. Le run précédent `38177331182`
  (`7ec94a8c`) avait été arrêté par le portail de syntaxe iOS sur deux erreurs
  de compilation, corrigées par `dcf0df67`.
- `neoswap-relay-check.yml` `38177333574` (`7ec94a8c`) : backend ASan/UBSan,
  extension, simulateur iOS 18 : réussi.
- Sur ce poste (zig 0.17.0, C++20, `-Werror`) : backend, budget, registre de
  phases JIT, client relais matérialisé en TU, matérialisation du patch sur un
  arbre XITRIX vierge, 24 tests du comparateur.

Non réalisé : toute validation sur iPhone (installation, fluidité, mémoire,
compilation). Le protocole est au §10 de l'audit. Le contrôle
`neoswap-check.yml` reste en échec sur une liste d'empreintes approuvées
obsolète depuis plusieurs builds (décision du mainteneur, hors livraison).

## Reprise par SideStore

L'IPA est scellée pour la re-signature Apple par SideStore ; aucune
installation ni mesure sur appareil n'est revendiquée. Première ouverture de
chaque titre PS3 après cette build : recompilation PPU complète attendue
(nouveau nom d'objet `v9-…`), à enregistrer mais pas à mesurer.
