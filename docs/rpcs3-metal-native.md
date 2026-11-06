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
  - compilateur `MTL4Compiler`. La passe de présentation est compilée en mode sûr. Les shaders RSX suivent le réglage
    existant « Disable MSL Fast Math » (désactivé par défaut) exactement comme MoltenVK aujourd'hui. Les SPIR-V de glslang
    n'ont pas de contrôle flottant, donc MoltenVK les compile en mode rapide (`MTLMathModeFast`). Le rendu ne change donc
    pas en silence, et le réglage reste au joueur. La position invariante active `preserveInvariance` ;
  - présentation `waitForDrawable` / `signalDrawable` sur la file ;
  - barrières explicites (Metal 4 ne suit pas les dépendances) ;
  - copies et remplissages dans l'encodeur de calcul.
- **La logique RSX commune.** Le backend se branchera sur `rsx::surface_store` et `rsx::texture_cache` par des traits
  Metal, comme Vulkan et OpenGL, pour garder toute la cohérence mémoire qui fait tourner les jeux aujourd'hui.
- **Shaders, étape 1 (M2.1, écrite).** La chaîne compte trois maillons.
  - `MTLVertexProgram.cpp` et `MTLFragmentProgram.cpp` produisent, ligne pour ligne, le GLSL des décompilateurs Vulkan.
    Les faits du GPU viennent d'un relevé Metal (`mtl::shader_device_caps`). Ces faits sont ceux que MoltenVK fournit
    aujourd'hui : pas de double précision, D24S8 émulé, rendu conditionnel résolu sur le CPU. Aucun en-tête Vulkan n'est
    nécessaire.
  - glslang compile ce GLSL en SPIR-V.
  - SPIRV-Cross autonome traduit le SPIR-V en MSL (`MTLShaderTranslator.cpp`). C'est la version vulkan-sdk-1.4.350.1,
    copie identique à celle de `neo_shader_kit`, placée dans les espaces de noms `rbx_spirv_cross` et `rbx_spv` pour ne
    jamais entrer en collision avec celle de MoltenVK.

  Les options de traduction sont celles de MoltenVK : iOS, MSL 3.2, tampons de texels natifs, sorties complétées,
  inversion de Y, correctif AGX des cubes, taille de point seulement pour les points, lecture du tampon d'image pour le
  mélange programmable.

  Contrat des emplacements, par étage :
  - un tampon prend l'emplacement de sa liaison GLSL, une texture aussi ;
  - un échantillonneur prend l'unité RSX ;
  - les constantes poussées vont dans le tampon 30, avec les mêmes octets pour les deux étages ;
  - les miroirs stencil et l'entrée de comparaison de profondeur ont des échantillonneurs inscrits dans le shader, avec
    les mêmes états que Vulkan.

  Une ressource du SPIR-V que le décompilateur n'a pas listée fait refuser la traduction : aucun emplacement automatique.
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
  - Depuis M2.1, le banc `test/native/build_rpcs3_metal_shader_stack.sh` fait passer de vrais programmes RSX par toute
    la chaîne. Il s'exécute sous Linux et dans la CI macOS. Les programmes sont encodés au format microcode RSX :
    transformation par 4 constantes, couleur, coordonnée de texture, texture 2D et constante littérale. Le banc vérifie le
    GLSL, le SPIR-V et chaque emplacement, puis écrit le MSL. La CI compile ensuite ce MSL pour iOS avec le compilateur
    Metal hors ligne d'Apple (`-std=metal3.2 -target air64-apple-ios26.0 -Werror`).
  - Le travail en cours d'une étape est appliqué par la CI au-dessus du Core canonique, au moyen de
    `build-utils/rpcs3/metal-wip-from-901.patch` et de la copie de SPIRV-Cross de `neo_shader_kit`. Ce n'est pas un
    Core : le Core suivant (902) l'intégrera au delta canonique, avec ses registres, avant toute IPA.
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
| M2 (en cours) | M2.1, écrite : SPIRV-Cross dans le Core, décompilateurs Metal, traduction en MSL et contrat des emplacements. M2.2, en cours : anneaux, clés de pipeline et de profondeur/gabarit, cache de programmes, contexte de commandes, surfaces, puis dessin et présentation (voir ci-dessous) | M2.1 : banc hôte (Linux, réussi) et compilation iOS du MSL en CI (run `42127316385`) ; M2.2 : CI iOS à chaque étape, puis IPA de test « première image » |
| M3 | Cibles de rendu et cache de textures (traits Metal), envois, formats, copies, relectures, cohérence (barrières, labels, sémaphores) | Scènes texturées comparées, relectures exactes |
| M4 | ZCULL et requêtes exactes, rendu conditionnel, MSAA et résolution, calculs de conversion, incrustations natives | Comptes de visibilité comparés, interface native |
| M5 | Parité sur jeux (BO2, Assassin's Creed, God of War III), cache de pipelines Metal 4, retrait de Vulkan et de MoltenVK du Core | Mesures iPhone, comparaison au Core Vulkan |

Numérotation : les Cores de cette branche sont 901, 902… ; ceux de la ligne `Claude` gardent la série 6xx.

### M2.2 : état et objectif « première image »

Toutes ces pièces sont dans `metal-wip-from-901.patch`. Chacune compile pour iOS 26 en CI.

Pièces écrites :
- `MTLDataHeap.h` : anneaux `rsx::data_heap` sur un `MTLBuffer` partagé (mémoire unifiée). Un anneau plein demande au
  renderer de soumettre et d'attendre ; il n'écrase jamais une mémoire encore lue par le GPU.
- `MTLPipelineState` : décodage des registres comme `decode_rsx_state` et `update_draw_state` de Vulkan, puis conversion
  comme MoltenVK. Le sens d'enroulement est le même grâce à l'inversion de Y ; « éliminer les deux faces » ne rastérise
  aucun triangle. Les clés n'ont aucun octet de remplissage : le cache les hache brutes.
- `MTLProgramBuffer` : traits du `program_state_cache` commun.
  - Les traductions MSL et les bibliothèques MTL4 sont gardées par programme et par variante, sous verrou.
  - Un échec est conservé avec son erreur, et ses dessins sont sautés et comptés, comme dans Vulkan quand un programme
    n'est pas prêt.
- `MTLCommandContext` : un tampon de commandes à la fois sur l'allocateur du frame et un encodeur ouvert.
  - Barrière de file après toutes les étapes à chaque nouvel encodeur.
  - Résidence et libération différée (Metal 4 ne retient rien).
  - Attentes jamais abandonnées.
- `MTLFormats` : formats de surface (table MoltenVK des choix Vulkan).
- `MTLRenderTargets` : traits du `surface_store` commun.
  - Initialisation identique à Vulkan sans lecture mémoire : couleur (0, 0, 0, 1), profondeur 1.0, stencil 255.
  - Héritage copié par le GPU quand le format et l'échelle sont identiques.

Écrit ensuite (`c889bff2`, `f62fd724`), pour la première image, c'est-à-dire les dessins d'un jeu exécutés par Metal 4
et présentés :
- branchement dans `MTLGSRender` : préparation des cibles, passes de rendu, envoi des sommets et des index,
  environnements et constantes, liaisons par tables d'arguments, dessins et effacements ;
- présentation de la surface qui tient l'adresse du tampon d'écran ;
- remplacement des tables d'arguments et de la résidence de M1.

Revue indépendante du chemin de dessin (6 novembre, lecture du code, rien exécuté). Trois défauts confirmés sont
corrigés :
- Anneau plein : l'attente du GPU libère tout l'anneau épuisé, mais un emplacement de frame gardait une position GET
  plus ancienne. La restaurer au frame suivant aurait rendu de la place encore lue par le GPU. Désormais, aucun
  emplacement ne restaure ses positions après un épuisement.
- Effacement : la place des constantes était réservée après l'ouverture de la passe. Si l'anneau débordait, la
  soumission fermait l'encodeur et l'effacement était perdu, alors que la surface était marquée écrite. La réservation
  se fait maintenant avant l'ouverture de la passe, comme pour les dessins.
- Effacement de la profondeur : le biais de profondeur du dessin précédent s'appliquait. Il est remis à zéro, comme le
  fait `vkCmdClearAttachments` (et l'aide de dessin de MoltenVK), avec le mode de découpe « clip ».

Un point reste plausible et n'est pas modifié : l'offset d'index `uint16` aligné sur 2 octets dans les dessins
indexés en plusieurs plages. MoltenVK envoie les mêmes offsets (`ibb.offset + firstIndex * idxSize`) au même iPhone
avec le moteur Vulkan. On le contrôlera avec la validation Metal sur l'IPA de test. La revue n'a pas couvert les cibles,
le cache de programmes, tout l'état de pipeline ni les formats.

Limites assumées et comptées de cette étape. Aucune n'est simulée : chacune a un compteur `COREPROF`.
- Textures : pas encore de cache de textures, une texture neutre est liée par unité ; c'est l'étape M3.
- Recopie des surfaces vers la mémoire invitée et chargement depuis elle : M3.
- Héritage sans type ou mis à l'échelle : M3.
- MSAA : textures à un échantillon, comme le réglage « MSAA : désactivé » ; les métriques d'échantillons RSX sont
  gardées pour la disposition mémoire. C'est l'étape M4.

Le jeu verra donc sa géométrie, ses couleurs, sa profondeur et son mélange, mais pas encore ses textures. Vulkan reste
le moteur par défaut, et Metal se choisit par jeu.

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
