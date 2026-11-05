# RPCS3 : renderer Metal natif (branche `work/rpcs3-metal-native-20261105`)

Demande du mainteneur (5 novembre 2026) : abandonner l'orchestrateur de threads et « établir une vraie
couche native Metal […] Tout le moteur devra passer par Metal. Si il y a aucun renderer il faudra le créer. »
Branche dédiée, créée depuis `Claude` (`cb29106f`). La branche `Claude` garde les mises à jour mineures
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

Un troisième backend RPCS3, construit comme le backend Vulkan, dans `rpcs3/Emu/RSX/Metal`
(espace de noms `mtl`).

- **Logique RSX commune.** Le backend se branche sur les modèles communs de RPCS3 (`rsx::surface_store`
  et `rsx::texture_cache`) par des traits Metal, comme Vulkan et OpenGL. Toute la logique de cohérence
  mémoire, d'alias de surfaces, d'invalidation et de relecture reste celle qui fait tourner les jeux
  aujourd'hui.
- **Côté Metal :**
  - périphérique, file et cycle des tampons de commandes ;
  - suivi de l'avancement du GPU par `MTLSharedEvent` ;
  - libération différée des ressources ;
  - états et pipelines ;
  - envois et conversions de formats ;
  - copies, mises à l'échelle et résolutions ;
  - requêtes de visibilité en mode comptage ;
  - présentation sur le `CAMetalLayer` de l'hôte.
- **Shaders, étape 1.** Les décompilateurs RSX existants produisent le GLSL, compilé en SPIR-V par
  glslang, puis traduit en MSL par SPIRV-Cross autonome (bibliothèque Khronos, pas MoltenVK). C'est la
  même sémantique que le rendu actuel, ce qui donne la parité d'image comme point de départ.
- **Shaders, étape 2.** Un émetteur RSX → MSL direct, pour le temps de compilation.
- **Exactitude.** Les règles du mainteneur s'appliquent : aucune suppression d'image, aucune baisse
  cachée de qualité ou de précision, aucun résultat ZCULL faux ou périmé. Une fonction pas encore
  écrite est comptée et signalée, jamais contournée. Aucun gain n'est annoncé tant qu'un dessin manque.
- **Capacités Metal à respecter** (tables Apple, octobre 2026) :
  - Familles : A15/A16 = Apple8 ; A17 Pro/A18 = Apple9.
  - Formats BC1-3 garantis seulement sur Apple9. Ailleurs, il faut vérifier
    `supportsBCTextureCompression` à l'exécution et prévoir une conversion.
  - Pas de `Depth24Unorm_Stencil8` sur iPhone : on utilise `Depth32Float_Stencil8`, avec des
    conversions exactes vers la mémoire invitée.
  - Pas de test de profondeur bornée (depth bounds) avant Apple10 : il faut une émulation exacte.
  - Le redémarrage de primitive est toujours actif dans Metal.
  - Pas de remplissage en points.
  - Limites par étage : 31 tampons, 128 textures, 16 échantillonneurs, 8 cibles couleur, MSAA 4x
    au plus.
  - Lecture du tampon d'image (programmable blending) et requêtes d'occlusion par comptage
    disponibles.

## 4. Validation

- **Hôte Linux** : tests unitaires de la logique pure (tables de formats, attribution des liaisons,
  clés de pipelines), avec ASan/UBSan.
- **CI macOS** (les machines macOS de la CI ont un vrai périphérique Metal ; voir
  `test/neo_shader_kit_test.py`) :
  - compilation des shaders RSX traduits par le vrai compilateur Metal ;
  - rendus hors écran de scènes synthétiques, comparés pixel par pixel au rendu Vulkan/MoltenVK de
    la même scène ;
  - aucun contenu de jeu dans Git.
- **iPhone** : IPA de test de cette branche, avec Metal choisi par jeu et Vulkan gardé pour la
  comparaison tant que la parité n'est pas atteinte. La compilation n'est pas une preuve de jeu.

## 5. Étapes

| Étape | Contenu | Preuve attendue |
| --- | --- | --- |
| M0 | Inventaire du backend Vulkan et de l'intégration hôte, plan (ce document) | Inventaire consigné |
| M1 | Squelette sélectionnable « Metal » : périphérique, file, `CAMetalLayer`, cycle d'image, effacements, présentation des cibles invitées ; tout le reste compté comme non pris en charge | Compilation iOS/macOS, test CI d'effacement relu |
| M2 | Shaders et pipelines, sommets persistants et volatils, index, tous les types de dessin, états de profondeur, gabarit et mélange | Shaders RSX compilés par Metal en CI, scènes synthétiques comparées |
| M3 | Cibles de rendu et cache de textures (traits Metal), envois, formats, copies, relectures, cohérence (barrières, labels, sémaphores) | Scènes texturées comparées, relectures exactes |
| M4 | ZCULL et requêtes exactes, rendu conditionnel, MSAA et résolution, calculs de conversion, incrustations | Comptes de visibilité comparés, interface native |
| M5 | Parité sur jeux (BO2, Assassin's Creed, God of War III), cache de pipelines Metal, retrait de Vulkan et de MoltenVK du Core | Mesures iPhone, comparaison au Core Vulkan |

## 6. Inventaire (M0)

À compléter : interface `rsx::thread`/`GSRender` à fournir, taille du backend Vulkan par rôle, code
iOS propre au RSX à porter, intégration hôte (`CAMetalLayer`, présentation, statistiques), construction
(CMake, flux CI).
