# Écart libretro_internal_bridge — IPA802 → IPA803

**Verdict : variation de stubs Objective-C générés par le linker, équivalents par leurs liaisons, accompagnée d’un nouvel UUID et de différences dans le bloc de signature. Aucun changement de code applicatif ou de données applicatives identifié.** L’image n’est pas identique octet pour octet ; il serait incorrect de réduire l’écart à UUID/signature seulement.

Les deux Mach-O arm64 font **2 159 024 octets**, avec le même en-tête, le même agencement et 32 sections. Les contenus de **30 sections sur 32** sont identiques, dont `__TEXT,__text` (**832 092 octets**), toutes les constantes, métadonnées Objective-C, données, tables d’exception et d’unwind. Les deux sections restantes sont `__stubs` et `__objc_stubs`.

| Zone | Écart établi |
|---|---|
| `__stubs` | 1 instruction LDR : `0xf9447e10` → `0xf9448210` |
| `__objc_stubs` | 2 057 instructions LDR : permutation inverse |
| `LC_UUID` | 16 octets différents |
| Bloc `LC_CODE_SIGNATURE` | 606 octets différents |
| Autres octets | **0 différence inexpliquée** |

Les **2 058 LDR** alternent uniquement entre les adresses GOT `0x11c8f8` et `0x11c900`. Les deux entrées contiennent exactement `0x801000000000011f`, au format chained-fixups 6. Elles désignent toutes deux l’import **287 `_objc_msgSend`**, de la bibliothèque **25 `/usr/lib/libobjc.A.dylib`**, avec **addend 0**, sans liaison faible, et le même symbole indirect **22145**. Les sélecteurs, les ADRP et les instructions de branchement restent inchangés. Chaque instruction différente a été résolue, pas seulement un exemple.

Tout `__LINKEDIT` avant la signature est identique : fixups/imports, export trie, débuts de fonctions, tables de symboles et chaînes. Sur les **2 680 octets différents**, les 2 058 octets de LDR, les 16 d’UUID et les 606 de signature expliquent l’intégralité de l’écart. Après normalisation limitée à ces éléments vérifiés, les deux images ont le même SHA256 :

`c7f53a1ff4a18f0175d7bf564a25cbf27533262940302de4d2a85184f7c204d9`

## Sources et entrées de build

Git `ffdb82c37d6dd8e1763a1263fca28eb424fb5e30` → `c5422386b72ec4ea88b010dab3826075ee7e79f8` ne modifie ni le bridge ni son podspec ni ses tiers inclus. Le tree Git du package est identique : `4b2986e01f8299dd044dce7ede37a9ad5e86a659`. Les dépendances déclarées du pod, `pubspec.yaml`/`pubspec.lock`, la recette standard réellement utilisée (`.github/workflows/standard-delivery.yml`), le workflow de livraison S2Arm historique et `build-utils/libretro` ont également des entrées Git identiques. Les chemins `ios/Podfile` et `ios/Podfile.lock` sont absents des deux révisions : ils ne constituent donc pas des entrées de build vérifiées dans ce constat. Le détail et les empreintes de toutes les sections figurent dans [libretro-image-difference.json](libretro-image-difference.json).

## Traitement dans le reçu

Conserver la détection de changement d’image et la qualifier explicitement **« linker-generated equivalent objc_msgSend stubs + UUID/signature »**. Ne pas déclarer l’image inchangée au niveau binaire et ne pas attribuer ce changement à une optimisation libretro. Cette revue est statique ; elle n’ajoute ni essai sur appareil ni validation cryptographique à la vérification IPA déjà passée. Aucune compilation, aucun test, aucune modification du dépôt et aucune consultation de clé privée n’ont été effectués.
