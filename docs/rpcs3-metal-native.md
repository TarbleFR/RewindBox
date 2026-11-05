# RPCS3 : renderer Metal 4 natif (branche `work/rpcs3-metal-native-20261105`)

Demande du mainteneur (5 novembre 2026) : abandonner l'orchestrateur de threads et « établir une vraie
couche native Metal […] Tout le moteur devra passer par Metal. Si il y a aucun renderer il faudra le créer. »
Branche dédiée, créée depuis `Claude` (`cb29106f`). Choix du mainteneur, même jour : « un renderer Metal 4 ». La branche `Claude` garde les mises à jour mineures
des utilisateurs et leurs IPA ; cette branche produira ses propres IPA de test.

## 1. Objectif et périmètre

- **Tout le moteur graphique RSX passe par Metal :**
  - le rendu (passes, états, dessins) ;
  - la présentation ;
  - la traduction des shaders et les pipelines ;
  - les conversions et envois de textures ;
  - les cibles de rendu et leurs relectures ;
  - ZCULL et les requêtes d'occlusion ;
  - le rendu conditionnel ;
  - les calculs auxiliaires ;
  - les incrustations natives (interface RPCS3).
- **À la fin de la branche, le Core RPCS3 ne contient plus ni Vulkan ni MoltenVK.** MeloNX garde son
  propre MoltenVK : c'est un autre composant, avec un autre propriétaire.
- **Hors périmètre, par nature :** le code processeur de la PS3 (PPU et SPU) reste recompilé en ARM sur
  le processeur. Un GPU n'exécute pas ce code (branches, accès mémoire synchrones, opérations atomiques
  permanentes). La limite processeur mesurée dans Black Ops II reste donc entière ; voir le
  [tableau partagé](AI_TASK_BOARD.md), analyse de l'IPA 666.
- **Ce que Metal natif apporte, sous réserve de mesure sur iPhone :**
  - une couche de traduction en moins : RSX → Metal au lieu de RSX → Vulkan → MoltenVK → Metal ;
  - des pipelines mis en cache par Metal d'une session à l'autre (`MTLBinaryArchive`), contre les
    compilations bloquantes ;
  - la mémoire unifiée utilisée sans copie intermédiaire ;
  - moins de travail processeur pour le thread RSX ;
  - la fin des défauts propres à MoltenVK (perte de périphérique dans `VKQueryPool`).
  - Aucun gain n'est revendiqué sans mesure sur iPhone.

## 2. État de l'existant (5 novembre)

- **RPCS3 upstream** : Vulkan et OpenGL seulement. Aucun renderer Metal natif trouvé (recherche du
  5 novembre ; l'absence n'est pas prouvée pour les branches privées).
- **ARMSX3** (`gr33k/ARMSX3`, branche `ios-core`, `3e4fc24`, 31 octobre) a un dossier
  `rpcs3/Emu/RSX/MTL` d'environ 8 100 lignes.
  - Ce renderer n'est pas sélectionnable. D'après son propre `INTEGRATION.md`, il encode les
    effacements, la présentation et un premier sous-ensemble de dessins non indexés sans texture ;
    tout le reste échoue explicitement.
  - Ses shaders passent par la traduction SPIR-V → MSL de MoltenVK.
  - Licence : GPL-2.0, sauf `MTLRuntime.h/.mm`, en GPL-3.0-or-later, incompatible avec RPCS3
    (GPL-2.0-only) et donc exclu.
  - Il sert de référence. Tout morceau repris le sera avec son attribution et une entrée de provenance.

## 3. Architecture retenue

Un troisième backend RPCS3, construit comme le backend Vulkan, dans `rpcs3/Emu/RSX/Metal` (espace de noms `mtl`),
sur **Metal 4** (iOS 26 au minimum, GPU Apple7 ou plus récent ; l'iPhone du mainteneur, A18 Pro, est en iOS 27.0).

- **Une seule porte vers Metal : `MTLAPI.h`.** Le renderer est en C++ pur ; `MTLAPIApple.mm` (ARC) implémente cette
  interface sur Metal 4, et chaque valeur d'énumération est vérifiée à la compilation contre sa constante Metal. Le même
  code se compile donc ici sous Linux (contrôles locaux) et se teste sur un vrai GPU Metal en CI macOS.
- **Le modèle Metal 4, tel quel :**
  - file `MTL4CommandQueue` ;
  - un allocateur et un tampon de commandes par image en vol (3), réutilisés seulement après le signal d'un
    `MTLSharedEvent` ; l'attente du GPU n'est jamais abandonnée, une attente de plus de 5 s est seulement comptée et
    journalisée ;
  - résidence explicite : un ensemble pour le renderer, celui du `CAMetalLayer` pour les drawables ;
  - liaisons par tables d'arguments (adresses GPU, identifiants de ressources), capturées à chaque dessin ;
  - compilateur `MTL4Compiler` (sans mathématiques rapides : NaN, infinis et zéro signé comptent pour le RSX) ;
  - présentation `waitForDrawable` / `signalDrawable` sur la file ;
  - barrières explicites (Metal 4 ne suit pas les dépendances) ;
  - copies et remplissages dans l'encodeur de calcul.
- **La logique RSX commune.** Le backend se branchera sur `rsx::surface_store` et `rsx::texture_cache` par des traits
  Metal, comme Vulkan et OpenGL, pour garder toute la cohérence mémoire qui fait tourner les jeux aujourd'hui.
- **Shaders, étape 1.** Les décompilateurs RSX existants produisent le GLSL, compilé en SPIR-V par glslang, puis traduit
  en MSL par SPIRV-Cross autonome (bibliothèque Khronos, pas MoltenVK). Le Core n'a pas encore SPIRV-Cross en propre :
  il existe dans MoltenVK et dans le pod hôte `neo_shader_kit` (vulkan-sdk-1.4.350.1), à intégrer au Core en M2.
- **Shaders, étape 2.** Un émetteur RSX → MSL direct, pour le temps de compilation ; mise en cache par les jeux de
  données de pipelines de Metal 4 (`MTL4PipelineDataSetSerializer`, archives) contre les saccades.
- **Exactitude.** Les règles du mainteneur s'appliquent : aucune suppression d'image, aucune baisse cachée de qualité ou
  de précision, aucun résultat ZCULL faux ou périmé. Une fonction pas encore écrite est comptée et signalée
  (`COREPROF METAL_M1`), jamais simulée. Aucun gain n'est annoncé tant qu'un dessin manque.
- **Capacités Metal à respecter** (tables Apple, octobre 2026) :
  - Familles : A15/A16 = Apple8 ; A17 Pro/A18 = Apple9.
  - Formats BC1-3 garantis seulement sur Apple9. Ailleurs, il faut vérifier `supportsBCTextureCompression` et prévoir
    une conversion.
  - Pas de `Depth24Unorm_Stencil8` sur iPhone : on utilise `Depth32Float_Stencil8`, avec des conversions exactes vers la
    mémoire invitée.
  - Test de profondeur bornée : l'encodeur Metal 4 a `setDepthTestBounds`, mais le matériel ne l'a qu'à partir
    d'Apple10. Il faut donc une émulation exacte sur A15-A18.
  - Redémarrage de primitive toujours actif ; pas de remplissage en points ; formats de profondeur hors des pipelines
    (Metal 4).
  - Limites par étage : 31 tampons, 128 textures, 16 échantillonneurs, 8 cibles couleur, MSAA 4x.

## 4. Validation

- **Hôte Linux** : vérification syntaxique stricte du renderer contre les vrais en-têtes RPCS3 (clang, `-std=gnu++20`)
  et tests unitaires de la logique pure (conversion du tampon d'écran, cadrage ; plus tard formats, liaisons, clés de
  pipelines), avec ASan/UBSan.
- **CI macOS** (`rpcs3-metal-checks.yml`, Xcode 26.3) :
  - compilation pour iOS avec le SDK iOS 26, où un appel Metal 4 hors garde de disponibilité ou un sélecteur inconnu
    est une erreur ;
  - test unitaire (UBSan) ;
  - sonde Metal 4 compilée, liée et lancée.
  - **Limite constatée (run `42121690064`)** : le GPU des machines macOS de GitHub est un « Apple Paravirtual device »
    sans Metal 4 (Apple7=0, Metal4=0). La sonde s'y arrête donc sans pouvoir relire l'image.
  - En M2, la CI compilera hors ligne, sans GPU, les shaders MSL produits par la traduction (`xcrun -sdk iphoneos metal`).
- **iPhone** :
  - seul endroit où le comportement de Metal 4 s'exécute vraiment ;
  - IPA de test de cette branche, avec Metal choisi par jeu et Vulkan gardé pour la comparaison tant que la parité n'est
    pas atteinte ;
  - la compilation n'est pas une preuve de jeu.

## 5. Étapes

| Étape | Contenu | Preuve attendue |
| --- | --- | --- |
| M0 | Inventaire du backend Vulkan et de l'intégration hôte, plan | Inventaire consigné (section 6) |
| **M1 (Core 901, cette livraison)** | Renderer Metal 4 sélectionnable par jeu (« Moteur Metal 4 natif », page de test, chiffre 18 de `levers627`) : périphérique, file, allocateurs, résidence, compilateur, présentation sur le `CAMetalLayer` du tampon d'écran lu en mémoire (conversion identique à Vulkan, rapport largeur/hauteur gardé) ; dessins, effacements et requêtes comptés, non exécutés | Compilation iOS 26 et test hôte en CI (run `42121690064`, réussis) ; exécution Metal 4 réelle : sur iPhone seulement |
| M2 | SPIRV-Cross dans le Core, shaders et pipelines, sommets persistants et volatils, index, tous les types de dessin, états de profondeur, gabarit et mélange | Shaders RSX compilés par Metal en CI, scènes synthétiques comparées |
| M3 | Cibles de rendu et cache de textures (traits Metal), envois, formats, copies, relectures, cohérence (barrières, labels, sémaphores) | Scènes texturées comparées, relectures exactes |
| M4 | ZCULL et requêtes exactes, rendu conditionnel, MSAA et résolution, calculs de conversion, incrustations natives | Comptes de visibilité comparés, interface native |
| M5 | Parité sur jeux (BO2, Assassin's Creed, God of War III), cache de pipelines Metal 4, retrait de Vulkan et de MoltenVK du Core | Mesures iPhone, comparaison au Core Vulkan |

Numérotation : les Cores de cette branche sont 901, 902… ; ceux de la ligne `Claude` gardent la série 6xx.

## 6. Inventaire (M0, 5 novembre)

- **Backend Vulkan à remplacer** : 120 fichiers, 37 453 lignes, dont :
  - dessin et cœur : 8 753 ;
  - textures et images : 5 727 ;
  - outils de périphérique et de synchronisation : 4 771 ;
  - mémoire et DMA : 3 422 ;
  - pipelines et descripteurs : 3 286 ;
  - présentation : 3 246 ;
  - cibles de rendu : 2 818 ;
  - programmes de shaders : 2 389 ;
  - calcul : 1 316 ;
  - incrustations : 1 257 ;
  - requêtes : 468.
  - Deux morceaux sont déjà du Metal natif : MetalFX spatial et `metal_event`.
- **Code propre à iOS dans le RSX** : 543 blocs `RPCS3_IOS` dans 76 fichiers, dont 270 dans le backend Vulkan (ZCULL,
  minutage GPU, préchauffage des shaders, cache SPIR-V, census des passes, MoltenVK). Chacun aura un équivalent Metal
  ou une décision écrite.
- **Interface à fournir** : les virtuelles de `rsx::thread`, `GSRender` et `ZCULL_control` que surcharge `VKGSRender`.
  Le Metal M1 surcharge `on_init_thread`, `on_exit`, `begin`, `end`, `clear_surface`, `flip` et les requêtes
  d'occlusion. Viendront ensuite `do_local_task`, `on_invalidate_memory_range`, `on_access_violation`,
  `notify_tile_unbound`, `write_barrier`, `release_GCM_label`, `on_semaphore_acquire_wait`,
  `scaled_image_from_memory`, le rendu conditionnel et `sync_hint`.
- **Intégration hôte** : l'hôte crée le `CAMetalLayer` et le transmet par `rpcs3_ios_set_display_surface` ;
  `gs_frame::handle()` le rend au renderer. Aucun changement de l'hôte n'est nécessaire pour présenter en Metal.
- **Construction** :
  - le Core est compilé par le clang LLVM 22 de Homebrew contre le SDK iOS de l'Xcode choisi ;
  - Metal 4 exige le SDK iOS 26 (Xcode 26.3 en CI), contre Xcode 16.4 pour la ligne `Claude` ;
  - Metal, QuartzCore, CoreGraphics, IOSurface et UIKit ne sont liés aujourd'hui qu'à travers MoltenVK : le bloc Metal
    lie Metal et QuartzCore lui-même.
- **Limites connues de M1** : l'interface native de RPCS3 (boîtes de dialogue, notifications) n'est pas dessinée par
  Metal avant M4 ; avec Metal activé, un jeu qui dessine sur le GPU n'affiche pas encore d'image.
