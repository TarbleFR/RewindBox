# MetalFX et JIT pour les cœurs libretro intégrés — évaluation et plan

*23 novembre 2026 — branche `Claude` (`c3c517c`). Évaluation seulement : aucun code produit modifié, aucune
compilation, aucun cœur recompilé, rien mesuré sur iPhone. Les durées et gains cités sans source sont des
estimations, signalées comme telles.*

## En bref

- **MetalFX : une seule étape, dans le présentateur Metal du pont.** Elle sert tous les cœurs sans en
  modifier aucun.
  - **Mode Spatial uniquement.** Le mode temporel et l'interpolation exigent profondeur et vecteurs de
    mouvement, que les cœurs libretro ne fournissent pas.
  - **Utile surtout pour les consoles 3D** (PS1, N64, PSP, 3DS), combiné à une résolution interne ×2 ou ×3.
    Peu ou pas utile en pixel art, où les shaders du catalogue font mieux.
  - **Désactivé par défaut**, exclusif avec les shaders, suspendu à la chauffe.
  - **Livraison** : application seule, les cœurs sont réutilisés.
- **JIT : aucun cœur libretro n'en a aujourd'hui sur iOS 26.** L'hôte le refuse (`LibretroJitUsableByCores`), et
  les binaires épinglés n'en contiennent pas :
  - Azahar officiel : JIT CPU et JIT de shaders retirés sous iOS ;
  - Beetle PSX : `HAVE_LIGHTREC = 0` sur iOS ;
  - DeSmuME : aucun JIT AArch64 n'existe en amont.
- **Architecture JIT recommandée : l'hôte prépare l'arène, les cœurs la reçoivent.**
  - Un septième helper dédié, `LibretroJITHelper`, est dérivé des helpers existants.
  - L'hôte prépare une arène de code avec le protocole iOS 26 déjà employé par RPCS3, ARMSX2, Xenia et S2Arm,
    avant même de charger le cœur.
  - Il la confie aux cœurs recompilés par une ABI C versionnée installée par `dlsym`, sur le modèle de la
    mémoire PSP de PPSSPP.
  - Sans prérequis, le jeu démarre avec l'interpréteur et le dit.
- **Faisabilité par console :**
  - **3DS : gain le plus fort, priorité.** Azahar compilé depuis la même révision avec dynarmic réactivé.
  - **PS1 : gain modéré** (CPU et chauffe). Lightrec doit passer une étude de faisabilité de l'écriture par
    alias, plus une revue de licence.
  - **DS : impossible avec DeSmuME.** Il faudrait ajouter melonDS, qui perd sur iOS la résolution interne de
    DeSmuME. C'est une décision produit.
- **Levier voisin, pour pousser l'upscaling** : la relecture CPU des images Vulkan (Azahar, Beetle PSX HW) croît
  avec la résolution interne. Le journal la mesure déjà ; la mesurer sur iPhone avant d'envisager une passe sans
  copie.

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
  (§ 5, point 10). MetalFX devrait être moins cher pour une netteté perçue proche. C'est une **estimation, non
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

## 3. JIT : état vérifié et contrat déjà en place

### 3.1 Aujourd'hui

- **Réponse de l'hôte.** `RETRO_ENVIRONMENT_GET_JIT_CAPABLE` reçoit `LibretroJitUsableByCores()`
  (`LibretroJit.m:21-24`, `LibretroCoreHost.m:731-733`, `LibretroSession.m:853`). Sa valeur :
  - **NO sur tout iOS 26 et suivants** ;
  - avant iOS 26, l'état CS_DEBUGGED du processus, qu'aucun flux libretro ne provoque.
- **Surcharges sans JIT.** Elles s'appliquent quand la réponse est non (`LibretroSession.m:866-867`).
  `test/libretro_core_options_test.py` exige une surcharge pour chaque option de génération de code.
- **Aucun flux StikJIT côté libretro** : ni helper, ni sonde de route, ni appairage. `jitCapable` remonte dans les
  diagnostics, mais Dart ne le lit pas.
- **Binaires sans JIT** (relevé de ce jour, sources amont relues) :

| Console | Cœur embarqué | Provenance | JIT dans le binaire | Rendu dans l'app |
| --- | --- | --- | --- | --- |
| 3DS | Azahar 2127.0-alpha1 (`5f3306d1`) | version iOS officielle, SHA épinglés (`build-utils/libretro/cores.json:87-97`) | **Non** : `use_cpu_jit` et `use_shader_jit` forcés à faux sous `IOS`, options retirées. FastInterp par défaut. `validate_libretro_ipa.py:64-67` et `upgrade_azahar.py:67-70` exigent cette absence. | Vulkan (MoltenVK), image relue puis présentée par Metal |
| DS | DeSmuME | buildbot, source exacte non résolue | **Non** : pas de `HAVE_JIT` en ios-arm64. L'amont l'écrit : « AArch64: no dynarec backend available » (AsmJit x86 seulement, JIT `arm_arm` 32 bits seulement). | logiciel, résolution interne calculée par le CPU |
| PS1 | Beetle PSX HW et Beetle PSX (`10e4b0c6`) | buildbot | **Non** : `HAVE_LIGHTREC = 0` imposé dans la branche iOS du Makefile | Vulkan (MoltenVK) relu, ou logiciel |

Aucun de ces quatre cœurs n'est compilé par RewindBox : seuls Nestopia et PPSSPP le sont. **Ajouter le JIT
impose donc de compiler les cœurs concernés depuis leurs sources**, comme PPSSPP (Build 497).

### 3.2 Le contrat iOS 26 que les autres moteurs respectent

| Élément | Contrat |
| --- | --- |
| Composants partagés | Un seul StikJIT 1.9.0 compilé et corrigé (`build-utils/stikjit/source.json`), la sonde de route LocalDevVPN (`10.7.0.1:49152`), `PairingFileService` et `LaunchPrerequisites`. |
| Un helper par moteur | Extension d'application distincte : identifiant, classe principale, marqueur `NeoStation<Moteur>JITHelper`, type de requête et script. Le debugger s'attache au processus RewindBox lui-même (`targetPID = getpid()`). |
| Pièges | `brk #0xf00d`, commande dans x16 : 1 = préparer `[x0, x0+x1)`, la réponse x0 doit être l'adresse ; 3 = sonde de nonce, réponse nonce + 1 ; 0 = détacher. |
| Préparation | Par tranches de 16 Mio au plus. Elle rend chaque page résidente. **Aucune préparation n'est possible après l'unique détachement.** |
| Mémoire | Jamais RWX. Vue RX préparée, plus un alias RW obtenu par `vm_remap(copy=FALSE)` + `vm_protect(RW)`. Écriture par l'alias, puis `sys_icache_invalidate` sur la vue RX. |
| Avant iOS 26 | Attachement classique, puis détachement. CS_DEBUGGED reste levé et le processus crée lui-même ses doubles vues. |
| Décision | iOS ≥ 26 ⇒ poignée de main, y compris sans TXM (RPCS3, ARMSX2, MeloNX, S2Arm). |
| Faits distincts | Route, helper, PID attendu attaché, mémoire préparée, sonde exécutable et première image sont des faits séparés (`docs/PROJECT_RULES.md`). P_TRACED prouve un debugger vivant ; CS_DEBUGGED survit au détachement et ne prouve rien. |
| Un debugger par processus | Un second helper ne peut pas s'attacher par-dessus. |
| Pas d'allocateur commun | Chaque moteur a le sien. Le plus proche d'un besoin libretro est l'allocateur C de S2Arm (`S2ArmCodePages.{h,c}` : modes attaché, détaché, classique ; tranches ≤ 16 Mio ; RX `MAP_FIXED` + alias RW). |

### 3.3 Faisabilité par cœur

| Console | JIT possible | Travail sur le cœur | Gain attendu (non mesuré) | Avis |
| --- | --- | --- | --- | --- |
| **3DS, Azahar** | Oui. Dynarmic (ARM11) est encore compilé, mais injoignable sous iOS. Le JIT de shaders PICA existe aussi. | 1. Compiler Azahar à la même révision `5f3306d1` (mêmes sauvegardes et options).<br>2. Choisir dynarmic quand l'hôte annonce le JIT (`CanUseJIT()` existe mais n'est pas appelé).<br>3. Donner au bloc de code oaknut l'adresse RX et l'alias RW de l'arène. Aujourd'hui il bascule RW/RX par `mprotect`, impossible sous TXM. Oaknut prévoit deux pointeurs, écriture et exécution : à confirmer sur la révision épinglée.<br>4. Borner les caches de code.<br>5. Désactiver fastmem au départ. | **Le plus fort.** FastInterp interprète deux à quatre ARM11 ; le JIT conditionne la pleine vitesse des jeux 3D lourds et libère la marge pour ×2–×3 + MetalFX. | **Priorité 1** |
| **PS1, Beetle PSX HW et Beetle PSX** | Probable. Lightrec (MIPS → AArch64 par GNU Lightning) existe en amont. | 1. Compiler `10e4b0c6` avec `HAVE_LIGHTREC = 1` (deux variantes).<br>2. Faire passer le tampon de code de Lightrec par l'arène.<br>3. **Risque principal** : GNU Lightning écrit le code à son adresse d'exécution. Il faut vérifier qu'il accepte un alias d'écriture, ou le corriger.<br>4. Surcharge sans JIT de la nouvelle option `*_cpu_dynarec`.<br>5. Licences de Lightrec et GNU Lightning à relire avec celle de Beetle. | **Modéré.** L'interpréteur de Beetle tient très probablement la pleine vitesse sur A17 et A18 (estimation). Le gain porte sur le temps CPU et la chauffe. Le surcoût d'un rendu ×4–×8 vient surtout du GPU et de la relecture Vulkan (§ 5, point 10). | **Priorité 2, après étude de faisabilité** |
| **DS, DeSmuME** | **Non.** Aucun moteur JIT AArch64 amont ; en écrire un est un projet à part entière. | — | — | **Pas de JIT DS avec DeSmuME** |
| DS, melonDS (alternative non embarquée) | Probable. ARMJIT AArch64 existe ; l'iOS de libretro/melonDS ne l'active pas. | 1. Nouveau cœur compilé.<br>2. Émetteur ARM64 (hérité de Dolphin) à adapter à l'alias d'écriture.<br>3. Fastmem coupé.<br>4. **Rendu logiciel seul sur iOS, donc résolution native** : seul MetalFX agrandit.<br>5. Sauvegardes `.dsv` à convertir en `.sav`, états incompatibles. | Le JIT libère du CPU, mais on perd la 3D recalculée en haute résolution de DeSmuME. | **Décision produit** |

Effet secondaire de l'infrastructure : PPSSPP (IR JIT forcé) et Mupen64Plus-Next (`cached_interpreter`) pourraient
plus tard l'utiliser avec le même correctif d'allocateur. Ce n'est pas dans le périmètre demandé.

## 4. JIT : architecture recommandée

### 4.1 Principe : l'hôte prépare l'arène, le cœur la reçoit

Les cœurs libretro sont ouverts puis fermés à chaque session (`dlopen`/`dlclose`). Sous iOS 26, la mémoire
exécutable doit être préparée pendant que le debugger est attaché, et jamais après. La méthode la plus propre :
**l'hôte prépare lui-même une arène de code, avant de charger le cœur**, puis la lui confie.

Ce que cela apporte :
- aucun code du cœur ne s'exécute pendant l'arrêt du debugger ;
- les mêmes cœurs servent sur iOS 17.4–18 et sur iOS 26 ;
- une seule implémentation du protocole pour tous les cœurs libretro ;
- le cœur ne voit qu'une interface : « donne-moi N octets : adresse d'exécution, alias d'écriture ».

```text
Dart : cœur compatible ? route LocalDevVPN ? appairage ?   (sinon : interpréteur + message, le jeu démarre)
  └─► LibretroJitBridge.prepare(taille du profil du cœur)
        ├─ LibretroJITHelper : attache le PID de RewindBox, script libretro-universal.js
        ├─ hôte : fenêtre réservée → RX MAP_FIXED → commande 1 par tranches ≤ 16 Mio → alias RW
        ├─ hôte : sonde exécutable (écrire « mov w0,#imm ; ret » par l'alias, appeler la vue RX)
        ├─ commande 3 (nonce) puis commande 0 (détachement) ; « complete » du helper ; P_TRACED retombé
        └─ faits notés séparément au journal
  └─► dlopen du cœur → rewindbox_libretro_jit_install(&abi) → GET_JIT_CAPABLE = vrai
      seulement si : arène prête ET sonde réussie ET installation acceptée
  └─► retro_init / retro_load_game : le cœur prend son code dans l'arène, sans croissance après le détachement
  └─► fin de session : retro_deinit, dlclose, libération de l'arène
```

### 4.2 Ce qui est réutilisé, ce qui est nouveau

| Réutilisé tel quel ou par copie | Nouveau |
| --- | --- |
| StikJIT 1.9.0 corrigé (même binaire), sonde de route, `PairingFileService`, `LaunchPrerequisites` | `packages/libretro_jit_helper` et `native/libretro_internal_helper`, dérivés par un outil de copie comme `tools/xenia/derive_jit_helper.py` ; marqueur `NeoStationLibretroJITHelper` |
| Script universel (commandes 0, 1 et 3), copie renommée de `rpcs3-universal.js` | `LibretroJitArena.{h,c}`, calqué sur `S2ArmCodePages.c` : modes attaché, classique et éteint, sans réserve pour après le détachement |
| Session hôte de S2Arm (`S2ArmJitSession.m`, Objective-C simple comme le pont libretro), sonde de nonce, contrôles P_TRACED, CS_DEBUGGED et `get-task-allow` | `LibretroJitBridge` dans `libretro_internal_bridge` ; état JIT mesuré par session, qui remplace `LibretroJitUsableByCores()` |
| Modèle d'ABI C versionnée installée par `dlsym` (`NeoStationPSPMemory.h` de PPSSPP) | En-tête `RewindBoxLibretroJit.h` v1 et correctifs d'allocateur des cœurs recompilés |
| Réservation anticipée d'adresses (fenêtre PSP de `LibretroAddressSpace.m`, séquestre de RPCS3) | Une fenêtre réservée pour l'arène, prise à l'enregistrement du plugin, après RPCS3 |
| Ensembles fermés des validateurs d'IPA et de la recette | Une entrée de plus dans chacun (`validate_single_ipa_distribution.py`, `verify_ipa.py` de Dolphin, `validate_rpcs3_ipa.py`, contrôle de versions `ENGINE_HELPERS` de `standard-delivery.yml`, `verify_downloaded_delivery.py`) |

### 4.3 ABI v1 (principe)

```c
// RewindBoxLibretroJit.h — partagé entre l'hôte et les cœurs recompilés. Aucun objet C++.
typedef struct RewindBoxLibretroJitV1 {
  uint32_t version;      // 1
  uint32_t structBytes;
  uint64_t pageBytes;    // 16 Kio
  uint64_t capacity;     // octets préparés pour cette session
  // Bloc aligné sur une page : *rx exécute, *rw écrit (même pages physiques). 0 = succès.
  int (*allocate)(uint64_t bytes, uint64_t *rx, uint64_t *rw);
  // Après écriture par l'alias : invalidation du cache d'instructions sur la vue RX.
  void (*flush)(uint64_t rx, uint64_t bytes);
} RewindBoxLibretroJitV1;
// Exporté par un cœur recompilé ; l'hôte l'appelle juste après dlopen, avant retro_init.
int rewindbox_libretro_jit_install(const RewindBoxLibretroJitV1 *abi);
```

- **Allocation.** Un simple découpage croissant suffit : la capacité est fixée par le profil du cœur et ne
  grandit jamais.
- **Code des cœurs inchangé.** Un cœur qui n'exporte pas le symbole garde exactement son comportement actuel.
- **Ordres de grandeur, estimations à confirmer dans les sources** : Azahar 64 à 160 Mio (caches dynarmic par
  ARM11 bornés, plus le JIT de shaders) ; Beetle/Lightrec environ 16 Mio. Toute l'arène est résidente : ces
  tailles comptent dans le budget mémoire.

### 4.4 Comportement attendu

- **Même expérience que les autres moteurs.** Même LocalDevVPN, même fichier d'appairage, mêmes messages de
  prérequis.
- **Différence avec RPCS3, MeloNX, S2Arm et Xenia, qui exigent le JIT.** Les cœurs libretro ont un
  interpréteur. Un prérequis absent ou un échec d'une étape ne bloque pas le lancement : la session démarre avec
  l'interpréteur (FastInterp, interpréteur de Beetle) et l'indique, sans jamais présenter le JIT comme actif.
- **Une transaction par session, au départ (modèle ARMSX2)** : l'arène est libérée à la fin de chaque jeu.
  - Si l'attente d'attachement gêne à chaque lancement, l'arène peut être gardée pour la durée du processus
    (modèle MeloNX), au prix de sa mémoire résidente. Décision après mesure.
- **Coexistence.** Refus explicite quand un autre debugger est déjà attaché (P_TRACED sans transaction
  libretro). Aucune transaction ne doit chevaucher celle d'un autre moteur.

### 4.5 Ce que le JIT apporte vraiment à l'upscaling

| Console | Où est la limite de l'upscaling | Effet du JIT |
| --- | --- | --- |
| 3DS | CPU (ARM11 interprétés), puis GPU via MoltenVK et relecture Vulkan | Direct : condition de la pleine vitesse, puis marge pour ×2–×3 + MetalFX |
| PS1 | GPU (×4–×8 Vulkan) et relecture CPU de chaque image | Indirect : moins de CPU et de chaleur dans l'enveloppe commune du SoC |
| DS (DeSmuME) | CPU : la 3D en haute résolution est rastérisée par le CPU | Aucun : pas de JIT possible. Avec melonDS : JIT, mais pas de résolution interne sur iOS |

## 5. Points de vigilance

1. **Seul l'iPhone prouve quelque chose.**
   - MetalFX est absent du GPU paravirtuel de la CI et du Simulateur.
   - Azahar ne démarre pas dans le Simulateur.
   - Le JIT exige LocalDevVPN, l'appairage et un appareil.
   - Une compilation réussie ne prouve ni le rendu, ni le JIT, ni un gain.
2. **Mémoire résidente.** Toute arène préparée est résidente aussitôt, et s'ajoute à la mémoire d'Azahar (FCRAM,
   caches Vulkan) et aux textures MetalFX. Les tailles sont fixées par profil et notées au journal.
3. **Aucune croissance après le détachement.** Les caches de code sont bornés. Un cache plein se vide (dynarmic
   sait le faire) ; il ne demande jamais une nouvelle préparation.
4. **Un seul debugger par processus.** Pas de transaction libretro pendant celle d'un autre moteur. Refus
   explicite si P_TRACED est levé sans transaction libretro en cours.
5. **Faits séparés et mesurés.** Sur iOS 26, CS_DEBUGGED seul ne vaut rien. `GET_JIT_CAPABLE` ne dit vrai
   qu'après une sonde exécutable réussie dans cette session, jamais d'après une route ou une session précédente.
6. **Signaux.** Fastmem (dynarmic, melonDS) repose sur des gestionnaires de fautes. Le désactiver dans la
   première version.
7. **Contrats à changer explicitement.**
   - `validate_libretro_ipa.py:64-67` et `upgrade_azahar.py:67-70` refusent aujourd'hui toute option JIT
     d'Azahar. Ils doivent décrire la nouvelle identité (binaire compilé, symbole d'ABI présent).
   - `test/libretro_core_options_test.py` garde son exigence d'une surcharge sans JIT pour toute option de
     génération de code : c'est le repli.
8. **Sources correspondantes et licences.**
   - Chaque cœur recompilé garde sa source et ses correctifs publiés, comme Nestopia et PPSSPP
     (`docs/ENGINE_CORRESPONDING_SOURCES.md`).
   - Azahar : GPLv3 ou ultérieure. melonDS : GPLv3.
   - Lightrec et GNU Lightning : à relire face à la licence de Beetle avant toute livraison.
9. **Sauvegardes et états.**
   - Azahar à la même révision : sauvegardes inchangées. La reprise d'un état entre interpréteur et JIT est à
     vérifier.
   - melonDS : conversion `.dsv` → `.sav`, états incompatibles.
10. **Relecture Vulkan.**
    - Son coût CPU croît avec la résolution interne. Il est mesuré par la ligne
      `[Libretro] Vulkan read-back over N frames` (`LibretroVulkanRenderer.m:1513-1530`).
    - Une passe sans copie demanderait `VK_EXT_metal_objects`, écarté parce que MoltenVK 1.2.8 plante avec ARC
      (`LibretroVulkanRenderer.h`). Il faudrait une unité compilée sans ARC, ou un MoltenVK plus récent.
11. **Qualité de MetalFX.**
    - Pixel art.
    - Tramage PS1 à ×1.
    - Textes des écrans tactiles.
    - FMV.
    - Plafond du facteur d'agrandissement.
    - À juger en A/B sur iPhone face au bilinéaire et à FSR slang.
12. **Chauffe.**
    - MetalFX ajoute une charge GPU constante, d'où la mise en retrait automatique.
    - Le JIT retire de la charge CPU.
    - Le journal de session note déjà chaque changement d'état thermique.
13. **Signature.** Une extension de plus à signer par l'outil d'installation, avec le même `get-task-allow`.
14. **Recette.**
    - Aucun nouveau test pour les cœurs et l'IPA ; on compile les ajouts.
    - Les contrôles existants (ensembles fermés des validateurs, empreintes, ABI) sont étendus, jamais
      contournés.
    - Seuls les cœurs modifiés sont recompilés ; les 30 et quelques autres gardent leur identité.

## 6. Plan d'intégration

Une build de validation par lot, selon la [recette standard](standard-delivery-recipe.md), IPA privée.

| Lot | Contenu | Compilation | Validation sur iPhone (maintainer) |
| --- | --- | --- | --- |
| **0. Mesures de départ** | Aucun code. Journaux existants sur des titres représentatifs : images/s d'Azahar FastInterp à ×1 et ×2 ; relecture Vulkan (attente de fence, transfert) d'Azahar et Beetle HW à ×1, ×2 et ×4 ; `gpuMilliseconds` ; états thermiques sur dix minutes. | Aucune | Base de comparaison, et décision du lot F |
| **A. MetalFX Spatial** | `LibretroMetalFXUpscaler.{h,m}`, branche du présentateur, réglage par cœur, mise en retrait thermique et journal dans `LibretroSession.m`, framework au podspec, trois libellés en douze langues | IPA seule. Cœurs libretro conservés (`build-utils/libretro/` inchangé), moteurs réutilisés, groupes Flutter et natifs `not-run` | A/B bilinéaire, FSR slang, MetalFX sur PS1 ×2, N64, PSP ×2, 3DS ×2 et DS ; temps GPU avec et sans ; rotation, téléviseur, tactile DS/3DS, chauffe |
| **B. Infrastructure JIT libretro** | Helper `LibretroJITHelper` dérivé ; `libretro-universal.js` ; script de configuration Xcode ; ensembles fermés des validateurs ; `LibretroJitArena`, `LibretroJitBridge`, état mesuré à la place de `LibretroJitUsableByCores()` ; prérequis et messages côté Dart ; faits au journal | IPA, livrée **avec le lot C** pour qu'un cœur l'exerce | — |
| **C. JIT 3DS (Azahar)** | Compilation d'Azahar `5f3306d1` depuis la source (CMake iOS, Vulkan/MoltenVK) avec les correctifs du § 3.3 et le symbole d'installation ; emballage par la route source de `build_cores.py` (comme PPSSPP 497) ; mise à jour de `cores.json`, des validateurs Azahar et des sources correspondantes | Collection de cœurs avec Azahar seul recompilé (les autres identiques octet pour octet), puis IPA | Chaque fait de la chaîne ; images/s face à FastInterp sur les mêmes scènes ; mémoire ; repli sans VPN (interpréteur et message) ; iOS 18 si un appareil le permet |
| **D. JIT PS1 (Beetle)** | D'abord une étude sur la source, sans IPA : écriture par alias dans Lightrec et GNU Lightning, et licences. Si elle est concluante : Beetle HW et logiciel `10e4b0c6` avec `HAVE_LIGHTREC = 1`, correctif d'ABI, surcharge sans JIT | Deux cœurs recompilés, puis IPA | Temps CPU et chauffe à ×4 Vulkan ; packs HD ; codes de triche ; états |
| **E. DS** | Seulement sur décision : melonDS comme second cœur DS avec JIT. Sinon, rien. | Nouveau cœur, puis IPA | Compatibilité, conversion des sauvegardes |
| **F. Image Vulkan sans copie** (facultatif) | Seulement si le lot 0 montre une relecture coûteuse aux résolutions visées : texture Metal du `VkImage` exportée, synchronisation par événement partagé | IPA (pont) ; peut-être MoltenVK | Temps de relecture avant et après, à résolution égale |

Ordre recommandé : **0 → A → B + C → D**, puis E et F selon les décisions et les mesures. Le lot A est
indépendant et peut avancer pendant l'étude de faisabilité de C et D.

## 7. Décisions à prendre

1. **MetalFX.** Désactivé par défaut et réglé par cœur, proposé à tous les cœurs (2D compris, avec
   avertissement), ou réservé aux cœurs 3D ?
2. **3DS.** Remplacer le binaire officiel d'Azahar par une compilation RewindBox de la même révision, avec les
   correctifs JIT ?
3. **PS1.** Engager l'étude Lightrec, licences comprises, avant toute compilation ?
4. **DS.** Garder DeSmuME sans JIT (conseillé pour l'instant) ou ajouter melonDS (JIT, résolution native et
   MetalFX) ?
5. **Arène JIT.** Une par session pour commencer (conseillé) ou une pour toute la durée du processus ?
6. **Lot F** selon les mesures du lot 0 ?

## 8. Décisions du 23 novembre 2026 et avancement

Décisions du mainteneur :
1. MetalFX pour tous les cœurs.
2. Azahar : compilation RewindBox de la même version.
3. PS1 : étude Lightrec, puis intégration si elle est possible.
4. DS : garder DeSmuME et en concevoir le JIT.

| Lot | État | Preuve |
| --- | --- | --- |
| A. MetalFX Spatial | **Codé.** Étape du présentateur (`LibretroMetalFXPolicy.h`, `LibretroMetalFXUpscaler` dans `LibretroMetalPresenter.m`), réglage par cœur sur la page « Résolution et image », pause thermique, mesure A/B au journal, cinq libellés en douze langues. | Compilation et édition de liens iPhone de tout le pont : contrôle libretro, run [45175436955](https://github.com/TarbleFR/RewindBox/actions/runs/45175436955), source `aed29a8`. **Non vérifié sur iPhone.** |
| B. Hôte JIT libretro | **Codé, inactif** tant qu'aucun cœur n'annonce d'arène (`jitArenaBytes` vaut 0 partout) :<br>• ABI `RewindBoxLibretroJit.h` v1 ;<br>• arène `LibretroJitArena.m` ;<br>• session du helper `LibretroJitSession.m` ;<br>• transaction `LibretroJitBridge.m` (méthodes `prepareJit` et `releaseJit`) ;<br>• point d'accroche `libraryOpened` de l'hôte ;<br>• paquet `packages/libretro_jit_helper`, copie tracée du helper RPCS3 (`tools/libretro/derive_jit_helper.py`, `copy-of-rpcs3.json`) ;<br>• `build-utils/configure_libretro_ios.py` ;<br>• étape Dart (route LocalDevVPN, appairage, faits journalisés) ;<br>• avis `jitInterpreterNotice`. | Même compilation iPhone pour la partie native. Les 586 tests Dart du contrôle libretro passent localement. Le helper n'est pas encore ajouté par la livraison (validateurs et étape Xcode à brancher avec le premier cœur JIT). |
| C. Azahar JIT | Étude de la recette de compilation et des correctifs en cours. | — |
| D. Beetle PSX (Lightrec) | **Faisable avec un correctif modeste** (ci-dessous). | Étude des sources (Beetle `10e4b0c6`, Lightrec vendu, GNU Lightning vendu, pcsx_rearmed). |
| E. DeSmuME | Conception du JIT AArch64 en cours. | — |

### 8.1 Lightrec : résultat de l'étude (23 novembre)

- **Pas de support existant.** GNU Lightning et Lightrec écrivent le code à l'adresse où il s'exécute. La seule
  bascule W^X de Lightning est `mprotect`, interdite par le contrat.
- **Liste fermée des endroits où l'adresse du code compte** (AArch64) :
  - retour de `jit_emit` et de `jit_address` (fonctions des blocs, distributeur, points d'entrée) ;
  - sauts et appels absolus (`jmpi`, `calli`, relatifs au pc d'écriture) ;
  - adresses d'étiquettes chargées en constantes ;
  - vidage du cache sur la plage d'écriture ;
  - métadonnées TLSF dans le tampon.
- **Pourquoi le correctif reste petit.** Pas de chaînage de blocs, pas de réécriture du code émis (une
  recompilation émet ailleurs et le reaper libère l'ancien bloc), pas d'ADR/ADRP ni de pool de littéraux.
  Un seul décalage « exécution − écriture » par état JIT suffit.
- **Correctif estimé** (estimations de l'étude) :
  - GNU Lightning, AArch64 seul, 40 à 70 lignes : `jit_set_code_exec`, cibles absolues, étiquettes, vidage,
    `HAVE_MMAP 0` sur iOS ;
  - Lightrec, 20 à 40 lignes : `lightrec_set_code_exec_offset`, conversions RX/RW, `isb` après l'installation
    d'un bloc compilé par un fil de travail ;
  - Beetle, 120 à 200 lignes :
    - `HAVE_LIGHTREC = 1` en iOS et `rewindbox_libretro_jit_install` ;
    - un seul `allocate` de 16 Mio par ouverture ;
    - tampon indépendant de la réussite de la disposition mémoire PS1 ;
    - `exit(1)` remplacé par un repli sur l'interpréteur ;
    - reprise du correctif amont `ed9dabc6` (double libération au second chargement d'un jeu) ;
    - vues mémoire par `shm_open` si le bac à sable l'accepte, sinon par Mach `vm_remap`.
- **Arène : 16 Mio**, en une allocation. La table de correspondance de 5 Mio reste hors de l'arène. Aucun
  gestionnaire de signaux.
- **Options.**
  - `beetle_psx_hw_cpu_dynarec` / `beetle_psx_cpu_dynarec` : `disabled`, `execute`, `run_interpreter`.
  - Surcharges : `disabled` sans JIT, `execute` avec l'ABI.
  - `dynarec_invalidate`, `dynarec_eventcycles` et voisines restent celles du cœur.
- **Licences.**
  - Lightrec : LGPL-2.1-or-later. GNU Lightning : LGPL-3.0-or-later. Fichiers Mednafen : GPL-2.0-or-later.
  - Le binaire avec Lightrec doit donc être distribué sous GPLv3, ce qui est compatible avec RewindBox.
  - Doute restant : quelques fichiers sans mention de licence, couverts par le COPYING GPLv2 du dépôt.
- **Comportement.**
  - Dynarec moins précis que l'interpréteur, selon le cœur lui-même.
  - Les codes de triche qui modifient du code MIPS n'atteignent pas les blocs déjà compilés.
  - Le gain n'est pas mesuré : il porte sur le temps CPU et la chauffe.

## Sources consultées

- **Pont libretro** : `LibretroMetalPresenter.{h,m}`, `LibretroVulkanRenderer.{h,m}`, `LibretroGLRenderer.m`,
  `LibretroSession.m`, `LibretroCoreHost.m`, `LibretroJit.{h,m}`, `LibretroRenderSurface.h`,
  `NeoStationPSPMemory.h`, `LibretroAddressSpace.m`, podspec du pont.
- **Catalogue et cœurs** : `lib/services/libretro_core_catalog.dart`, `build-utils/libretro/{cores.json,
  build_cores.py, upgrade_azahar.py}`, `build-utils/validate_libretro_ipa.py`,
  `test/libretro_core_options_test.py`, `build-utils/delivery/824.json`.
- **Chaîne JIT des autres moteurs** :
  - `packages/stikjit_bridge` ;
  - `packages/*_jit_helper` (scripts `*-universal.js`) ;
  - `Rpcs3JitBridgePlugin.mm`, `Armsx2JitBridgePlugin.mm`, `MeloNXJitBridgePlugin.mm`, `XeniaJitBridgePlugin.mm` ;
  - `S2ArmJitSession.{h,m}`, `S2ArmCodePages.{h,c}`, `native/melonx/jit/MeloNXJitSupport.S` ;
  - `build-utils/patch_stikjit_rpcs3.py`, `build-utils/patch_stikjit_compat.py`,
    `build-utils/validate_single_ipa_distribution.py`.
  - Les sources de StikJIT ne figurent pas dans l'extraction : son fonctionnement interne est déduit des
    correctifs et des tests.
- **Documents** : `docs/PROJECT_RULES.md`, `docs/retroarch-integre-architecture.md`, `docs/libretro-resolution.md`,
  `docs/libretro-skins-shaders.md`, `docs/libretro-3ds-psp-lifecycle.md`, `docs/build453-plan.md`,
  `docs/s2arm-jit-helper.md`, `docs/build321-rpcs3-early-jit-escrow.md`,
  `docs/evidence/s2arm-fluidity-803/implementation-status.md`.
- **Amont, relu le 23 novembre 2026** : Azahar `5f3306d1` (`core_settings.cpp`, `core.cpp`, `environment.cpp`,
  `CMakeLists.txt`) ; DeSmuME `Makefile.libretro` ; Beetle PSX `10e4b0c6` (`Makefile`, `libretro_core_options.h`) ;
  libretro/melonDS et PCSX ReARMed (`Makefile*`) ; oaknut `code_block.hpp`.
- **Apple** : [MTLFXSpatialScalerBase](https://developer.apple.com/documentation/metalfx/mtlfxspatialscalerbase.md),
  [MTLFXSpatialScalerDescriptor](https://developer.apple.com/documentation/metalfx/mtlfxspatialscalerdescriptor.md),
  [MTLFXSpatialScaler](https://developer.apple.com/documentation/metalfx/mtlfxspatialscaler.md),
  [Go further with Metal 4 games (WWDC25)](https://developer.apple.com/videos/play/wwdc2025/211/),
  [forum : coût de l'interpolation sur iPhone](https://developer.apple.com/forums/thread/853871),
  [tableaux des fonctions Metal](https://developer.apple.com/metal/Metal-Feature-Set-Tables.pdf).
