# MetalFX et JIT pour les cœurs libretro intégrés — évaluation et plan

*23 novembre 2026 — branche `Claude` (`c3c517c`). Évaluation seulement : aucun code produit modifié, aucune
compilation, aucun cœur recompilé, rien mesuré sur iPhone. Les durées et gains cités sans source sont des
estimations, signalées comme telles.*

> Brouillon : les parties MetalFX (§ 1–2) sont rédigées ; le JIT, les points de vigilance et le plan suivent.

<!-- SECTION:SUMMARY -->

## 1. MetalFX : utilité réelle

### 1.1 Quel mode MetalFX

| Mode MetalFX | Entrées exigées | Applicable aux cœurs libretro ? |
| --- | --- | --- |
| **Spatial** (`MTLFXSpatialScaler`, iOS 16+) | une image couleur | **Oui, pour tous les cœurs**, sans modifier aucun cœur |
| Temporel (`MTLFXTemporalScaler`) | couleur, profondeur, vecteurs de mouvement, décalage de gigue par image | **Non.** L'API libretro ne transmet que l'image finale. Il faudrait réécrire le moteur de rendu de chaque cœur (Beetle PSX, Azahar, PPSSPP, GLideN64…) pour produire mouvement et gigue. La PS1 n'a pas de tampon de profondeur matériel, et les cœurs 2D n'ont pas de mouvement exploitable. |
| Interpolation d'images (iOS 26) | couleur, profondeur, mouvement | **Non.** Mêmes entrées, plus une image de latence, mauvaise pour l'émulation. Des développeurs rapportent environ 11 à 18 ms par image sur iPhone ([forum Apple](https://developer.apple.com/forums/thread/853871)). |
| Débruitage temporel (iOS 26) | entrées du lancer de rayons | Sans objet |

Seul le **mode Spatial** est retenu. Il ressemble à FSR 1 (EASU) : un agrandissement qui suit les contours,
avec un affûtage, sans historique. Il n'ajoute aucune image de latence.

### 1.2 Pertinence selon les consoles

| Famille | Cœurs embarqués | Intérêt de MetalFX Spatial | Recommandation |
| --- | --- | --- | --- |
| 2D en pixel art | Nestopia, Mesen, Snes9x, Gambatte, mGBA, Genesis Plus GX, PicoDrive, FinalBurn Neo, Beetle PCE/WonderSwan/NeoPop/VB, Handy, Stella… | **Faible, voire négatif.** Le scaler ne connaît pas la grille de pixels : il arrondit les bords francs, crée des halos avec son affûtage et déforme les pixels de façon irrégulière. | Désactivé par défaut. L'échelle entière nette, le bilinéaire net, xBR, ScaleFX, MMPX et les shaders CRT/LCD du catalogue répondent mieux à ce besoin. |
| 3D avec résolution interne réglable | Beetle PSX HW (×1 à ×8), Azahar (×1 à ×10), PPSSPP (×1 à ×5), Mupen64Plus-Next | **Moyen.** Le scaler agrandit l'image du cœur jusqu'à l'écran mieux qu'un bilinéaire. Une résolution interne plus basse (×2 ou ×3) peut alors donner une netteté perçue proche d'une résolution plus haute. | Proposé, désactivé par défaut, à combiner avec une résolution interne ×2 ou ×3. |
| 3D logicielle ou image mixte 2D/3D | DeSmuME (3D agrandie par le CPU, 2D agrandie au plus proche), Beetle PSX logiciel | **Limité.** L'interface 2D est lissée elle aussi. | Facultatif. |

Points propres à certaines consoles :
- **PS1.** Le tramage de Beetle à ×1 et les textures 256 × 256 sont accentués par l'affûtage. L'ondulation des
  textures affines et des sommets n'est pas corrigée par un agrandissement (c'est le rôle de PGXP).
- **DS et 3DS.** L'écran tactile affiche souvent du texte en 2D. Comme pour les shaders, dont la courbure est
  déjà annulée sur l'écran tactile, ne garder MetalFX que sur l'écran principal est une variante à évaluer.
- **FMV** (PS1, Mega-CD). L'affûtage peut accentuer les artefacts de compression.

Le catalogue slang propose déjà le même rôle : `edge-smoothing/fsr/fsr.slangp` (EASU + RCAS, validation
`rendered`), NIS, ScaleFX, xBR, nnedi3. Ce qu'apporte MetalFX :
- une seule option native, sans compilation slang ;
- une implémentation d'Apple pour ses GPU (son coût face à FSR slang n'est pas mesuré) ;
- une intégration directe aux écrans DS et 3DS.

Ses limites : il est fermé, son rendu peut changer selon la version d'iOS, et il ne peut pas tourner dans la CI
macOS (GPU paravirtuel sans scaler MetalFX, cf. [S2Arm 233](evidence/s2arm-fluidity-803/implementation-status.md))
ni dans le Simulateur. Avant de le promouvoir, une comparaison A/B face à FSR slang sur iPhone est nécessaire.

### 1.3 Coût GPU et thermique

- **Ce qui coûte.** Le Spatial exécute une ou deux passes de calcul par écran. Ce coût dépend du nombre de pixels
  produits, pas de la scène. Il ne garde aucun historique et n'ajoute aucune latence.
- **Face à une résolution interne plus haute.** Monter la résolution interne multiplie le rendu du cœur par le
  nombre de pixels internes. Pour les cœurs Vulkan, cela multiplie aussi la copie de chaque image
  (§ 3.4). MetalFX devrait être moins cher pour une netteté perçue proche. C'est une **estimation, non
  mesurée**.
- **Aucune mesure n'existe dans le dépôt.** Les chiffres MetalFX de S2Arm portent sur le mode temporel
  960 × 540 → 1920 × 1080, mêlé à d'autres passes. Ils ne valent pas pour le mode Spatial.
- **Comment mesurer.** Le présentateur fournit déjà `gpuMilliseconds` (médiane sur 120 images) et
  `measureLastFrameGPUTime:`. Ce dernier repasse par `encodeFrameOnBuffer:`. Une étape MetalFX insérée là est
  donc mesurée sans nouvelle instrumentation (A/B en pause, comme après le choix d'un shader).
- **Thermique.** C'est une charge GPU constante à 50 ou 60 Hz. Le mode doit céder à la chauffe (§ 2.4).

## 2. MetalFX : architecture recommandée

### 2.1 Un seul point d'insertion pour tous les cœurs

Toutes les images de tous les cœurs passent par `LibretroMetalPresenter`
(`packages/libretro_internal_bridge/ios/Classes/LibretroMetalPresenter.m`) :

- images logicielles converties puis envoyées dans un anneau de textures (`presentSoftwareFrame:`) ;
- OpenGL ES : texture Metal qui partage l'IOSurface du cœur, sans copie (`presentTexture:`) ;
- Vulkan : pixels relus par `LibretroVulkanRenderer` (`presentPixels:`).

Les trois chemins aboutissent à `drawTexture:`, puis à `encodeFrameOnBuffer:`, qui choisit aujourd'hui entre les
chaînes slang par écran et la passe standard (préréglage intégré ou image simple). MetalFX devient une
**troisième branche à cet endroit**. Aucun cœur n'est modifié ni recompilé. Seul le pont change, et il est compilé
avec l'application.

```text
cœur ─► image (logicielle │ IOSurface OpenGL ES │ Vulkan relu) ─► encodeFrameOnBuffer
          ├─ shader slang actif            → chaînes par écran (inchangé)
          ├─ préréglage ou image standard  → une passe (inchangé)
          └─ MetalFX actif et applicable   → par écran : copie de la partie → Spatial → composition
       ─► drawable du CAMetalLayer ; skins, overlay tactile et menus restent des vues UIKit au-dessus
```

Code proposé :
- un nouveau `LibretroMetalFXUpscaler.{h,m}`, propriétaire des scalers, des textures, de la politique et des
  codes d'échec ;
- une branche de quelques dizaines de lignes dans le présentateur, calquée sur `encodeSlangScreens:` ;
- dans `LibretroSession`, le réglage, la préférence et le journal.

### 2.2 Traitement d'un écran (un seul, ou deux pour DS et 3DS)

1. **Zone de sortie.** Elle est calculée exactement comme aujourd'hui (`LibretroFitScreen`, conteneur du skin,
   format d'écran), puis arrondie au pixel entier comme dans le chemin slang.
2. **Copie de la partie de l'écran** dans une texture privée BGRA8, à sa taille en texels. La passe utilisée est
   le pipeline de recopie, avec le même code que la copie « Original » des chaînes slang. Cette copie gère :
   - l'origine de la partie (écran bas DS à y = 192) ;
   - le retournement des images OpenGL ;
   - le format (RGBA8 et RGB10A2 venant de Vulkan).
3. **Spatial.** L'entrée est la partie. Elle est allouée à la plus grande taille vue, et `inputContentWidth` /
   `inputContentHeight` suivent les variations : Beetle passe de 320 à 368, 512 ou 640 de large sans recréer le
   scaler.
   - La sortie a la taille de la zone selon les axes de l'image (un quart de tour échange les côtés).
   - Elle est plafonnée à `entrée × facteur maximal`. Valeur proposée : 3, à régler sur iPhone. Apple ne
     documente aucune limite du Spatial.
   - Si la sortie ne dépasse pas 1,05 × l'entrée, MetalFX est sauté pour cet écran. C'est le cas d'une résolution
     interne déjà plus grande que l'écran, par exemple DeSmuME ×10.
4. **Composition** en une passe sur le drawable, effacé en noir. Chaque sortie est placée avec `RotatedQuad`.
   - Échantillonnage au plus proche en 1:1 ; le facteur restant au-delà du plafond est lissé.
   - Les correspondances écran/tactile sont celles d'aujourd'hui : le tactile ne change pas.

### 2.3 Cycle de vie et mémoire

- **Clé d'un scaler** : taille d'entrée, taille de sortie et formats, tous fixés par le descripteur.
- **Recréation** seulement quand la taille de sortie change : rotation, disposition, skin, téléviseur, facteur
  interne.
  - Elle attend deux images identiques, pour ne pas recréer pendant l'animation de rotation.
  - Elle se fait sur une file utilitaire, jamais sur le chemin du drawable, ni à un changement d'état thermique
    (leçon du patch S2Arm 0217). L'image standard s'affiche en attendant.
- **Libération** : l'ancien scaler et ses textures sont retenus par le gestionnaire de fin du dernier tampon de
  commandes qui les emploie (leçon `defer_obj_unref` de S2Arm). Tout est libéré à la désactivation, en fin de
  session et sur avertissement mémoire.
- **Mémoire** : deux textures privées par écran. Exemple : écran haut 3DS à ×1, 400 × 240 → 1200 × 720 au plus,
  soit environ 3,8 Mo pour les deux. Un compteur `upscalerTextureBytes`, à côté de `slangTextureBytes`, alimente le journal.

### 2.4 Politique et compatibilité

| Sujet | Décision |
| --- | --- |
| Appareil | `MTLFXSpatialScalerDescriptor supportsDevice:` à l'exécution. Sinon le réglage est grisé et expliqué. Simulateur et CI : toujours non pris en charge, chemin standard. |
| Liaison | Framework `MetalFX` (iOS 16+, sous le minimum iOS 18) ajouté au podspec du pont, ou classes prises par leur nom comme S2Arm. Dans les deux cas, contrôle par `supportsDevice:`. |
| Couleur | Entrée et sortie BGRA8Unorm, `MTLFXSpatialScalerColorProcessingModePerceptual` : image LDR encodée gamma, comme le drawable BGRA8. |
| Shaders | **Exclusifs.** Un shader slang ou intégré actif l'emporte et MetalFX n'est pas appliqué ; le réglage l'indique. Les shaders CRT/LCD/pixel art ont besoin des pixels de la console (`SourceSize`), et les shaders d'agrandissement font le même travail. Pas d'enchaînement dans la première version. |
| Lissage | « Image lissée » ne règle plus que le facteur restant au-delà du plafond et l'image de repli. |
| Skins, overlays, menus | Vues UIKit au-dessus de la vue Metal : inchangés. |
| Tactile | Mêmes zones de sortie, mêmes correspondances. |
| Rotation | Appliquée à la composition ; MetalFX travaille dans les axes de l'image. |
| Pause, menu | `representLastFrameWithCompletion:` passe par la même branche. |
| Téléviseur | Fonctionne (drawable à la taille du téléviseur). Le plafond borne le coût ; à mesurer sur téléviseur. |
| Présentation Vulkan de secours (swapchain) | Indisponible, comme les shaders (`_screensAndShadersAvailable`). |
| Chauffe | Retour à l'image standard dès `NSProcessInfoThermalStateSerious`, ou en mode économie d'énergie. Reprise après 30 s continues à Fair ou en dessous (hystérésis de S2Arm 0217). Chaque transition est notée au journal. |
| Échec | Repli par écran sur l'image standard avec un code noté une fois : `METALFX_UNSUPPORTED`, `METALFX_CREATE`, `METALFX_RATIO`, `METALFX_THERMAL`, `METALFX_PRESET`. Même principe que `slangFailureCode`. |

### 2.5 Réglage et journal

- **Réglage.** Une ligne « MetalFX (Apple) » s'ajoute à la section « Agrandissement de l'image » de la page en jeu
  « Résolution et image ». Pied de section : recommandé pour les jeux 3D avec une résolution interne ×2 ou ×3 ;
  sans effet avec un shader ; suspendu quand l'iPhone chauffe.
  - Portée par cœur, désactivé partout par défaut.
  - Trois libellés en douze langues (`LibretroLocale`).
  - La page Flutter des réglages de console peut suivre dans un second temps.
- **Journal de session**, sans nouveau test :
  - `[rb-metalfx] screen= in= out= final= create_ms=` à chaque construction ;
  - `[rb-metalfx] bypass reason=` à chaque transition ;
  - à l'activation, une mesure A/B par `measureLastFrameGPUTime:` (désactivé puis activé), notée comme le temps
    GPU d'un shader.

<!-- SECTION:JIT -->

<!-- SECTION:VIGILANCE -->

<!-- SECTION:PLAN -->

<!-- SECTION:DECISIONS -->
