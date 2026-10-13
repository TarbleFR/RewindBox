# Système de shaders de NeoStation iOS (Build 450)

Ce document décrit l'architecture livrée par le chantier « gestion avancée des
shaders », ce qui est vérifié et comment, et ce qui ne l'est pas. Les preuves
citées sont des runs CI identifiés ; rien n'a été vérifié sur iPhone.

## 1. Vue d'ensemble

| Couche | Emplacement | Rôle |
|---|---|---|
| Kit partagé | `packages/neo_shader_kit` | Cœur portable C++17 (règles des préréglages `.slangp`/`.slang` de RetroArch, réflexion, liaisons MSL), glslang et SPIRV-Cross vendorisés (`vulkan-sdk-1.4.350.1`, fichiers épinglés par SHA-256), exécution Metal multi-passes (`NeoSlangRenderer.mm`), catalogues, stockage vérifié, profils, API Dolphin (`NeoDolphinShader`). |
| Moteur libretro intégré | `packages/libretro_internal_bridge` | Préréglages intégrés (portages Metal) et préréglages slang compilés sur l'appareil ; menu en jeu Réglages › Shaders. |
| Dolphin | `packages/dolphin_internal_bridge` | Page Affichage › Effet de post-traitement : effets officiels de Dolphin, effets importés, réglages ; appliqué au lancement suivant. |
| Moteurs futurs | `NeoShaderEngine.h` | `NeoShaderEngineCapabilities` (formats, changement en cours de partie ou non, catalogue téléchargeable, portées de profils) et `NeoShaderBackendAdapter` : un moteur décrit ce qu'il sait faire, les pages s'y adaptent. |

Chaque format reste propre à son moteur : un shader Dolphin n'est jamais chargé
comme préréglage RetroArch, et l'inverse.

## 2. Moteur libretro : préréglages slang

- **Exécution** : `NeoSlangRenderer.mm` reproduit la chaîne de filtres de
  RetroArch (`shader_vulkan.c`) : Original, Source, `PassOutput#`,
  `PassFeedback#`, `OriginalHistory#`, LUT ; `filter_linear#`, `wrap_mode#`,
  `mipmap_input#` ; échelles source/viewport/absolue ; dernière passe sans
  échelle rendue à la taille de sortie ; framebuffers sRGB et flottants ;
  `frame_count_mod` ; budget de 1 Gio de textures par chaîne (au-delà :
  image standard et message « trop lourd à cette taille »).
- **Compilation** : sur l'appareil, hors des fils principal et d'émulation
  (file dédiée), la demande la plus récente l'emporte. Un échec laisse
  l'image en effet inchangée.
- **Catalogue** : `slang-catalog.json`, généré par
  `tools/shaders/build_slang_catalog.py` depuis `libretro/slang-shaders` @
  `e1d75632a205c70f14a4cc947c46d5abb7b3f7f1` : 982 préréglages sur 2 658
  (1 676 écartés avec leur motif dans `slang-catalog-diagnostics.json` :
  cadres et habillages, sortie HDR, stéréo, sous-images, mires, palettes
  brutes, sémantiques non prises en charge, échec GPU). Chaque fichier
  nécessaire (préréglage, sources, inclusions, textures) est listé avec sa
  taille et son SHA-256 ; 2 412 fichiers, 33,8 Mo au total.
- **Téléchargement** : seulement à la demande, depuis ce commit
  (`raw.githubusercontent.com`), vérification taille + SHA-256 de chaque
  fichier, mise en place atomique quand tout est vérifié ; fichiers partagés
  par révision et conservés tant qu'un préréglage les utilise ; annulation ;
  aperçus `libretro/shader-previews` @ `2adabb17…` vérifiés et mis en cache.
- **Menu en jeu** (Réglages › Shaders) : portée console/jeu, interrupteur,
  préréglages intégrés, préréglages installés (favoris en tête), catalogue
  officiel (recherche, favoris, 12 catégories, fiche détaillée), profils
  (shader + valeurs, applicables à tout jeu), réglages du préréglage en effet
  (titres de section de l'auteur), temps GPU mesuré, passes, durée de
  compilation, mémoire des textures, crédits cités tels quels.

### Ce que « vérifié » veut dire

Un préréglage est offert comme « Vérifié » seulement si la porte Metal de la CI
(`test/neo_shader_kit_catalog_test.py`, workflow `shader-kit-checks`) l'a :

1. traduit pour iOS avec le cœur de l'application, puis compilé avec le
   compilateur Metal de l'iPhone (`xcrun -sdk iphoneos metal`) ;
2. compilé et exécuté par le code d'exécution de l'application
   (`NeoSlangRenderer.mm`) sur le GPU Metal de macOS, trois images d'un motif
   animé, relues ;
3. trouvé visiblement différent d'un simple agrandissement (au moins 0,1 %
   des pixels, image non noire, non uniforme, valeurs finies).

Résultat : run 38330265352 (commit `63d991b`) puis run 38332666178 (commit
`2a076d8`) : **982 sur 982 rendus** après exclusion de
`deinterlacing/nnedi3-nns256-deinterlacing` (délai GPU dépassé sur le GPU
paravirtuel de la CI). Les verdicts sont transcrits dans
`tools/shaders/slang-metal-results.json`. Il s'agit d'un GPU Apple de macOS,
pas d'un iPhone : le comportement sur iPhone (performances, mémoire) n'est
pas démontré.

## 3. Dolphin : effets de post-traitement

- Le cœur Dolphin conservé (identité vérifiée par la livraison) lit son effet
  au démarrage d'un jeu et n'expose aucun appel pour le changer en cours de
  partie ; il réécrit ses réglages à l'arrêt. Le choix est donc enregistré
  par NeoStation (`Config/NeoStationShaders.json`) et écrit dans
  `GFX.ini [Enhancements] PostProcessingShader` et `Dolphin.ini
  <effet>-options` juste avant l'initialisation du cœur
  (`DOLShaderStore.h`). Une proposition d'ABI de changement en direct est
  décrite au § 5 ; elle n'est pas activée.
- Effets officiels : les 46 fichiers de premier niveau de `Data/Sys/Shaders`
  de DolphiniOS @ `7cac5416…` (45 effets et la passe par défaut de Dolphin,
  déjà livrés dans le dossier Sys de l'application). 43 effets sont listés dans `dolphin-catalog.json` avec taille et
  SHA-256, tous « rendus » par la CI ; « Vérifié » s'affiche seulement si le
  fichier livré est celui que la CI a rendu. Écartés avec leur motif
  (`dolphin-catalog-diagnostics.json`) et absents de la page : la passe par
  défaut de Dolphin, les 7 shaders stéréoscopiques (`Anaglyph/`,
  `Passive/`), et `AutoHDR` et `PerceptualHDR`, qui ne font rien sans sortie
  HDR : leur code renvoie l'image inchangée si `hdr_output` est désactivé, et
  DolphiniOS fixe `bSupportsHDROutput = false` sous `IPHONEOS`
  (`Source/Core/VideoBackends/Metal/MTLUtil.mm`).
- Effets importés : fichiers `.glsl` choisis dans Fichiers ; chaque fichier
  est traduit comme le fait le cœur puis compilé par le compilateur Metal de
  l'appareil avant d'être copié dans `User/Shaders` ; un import ne peut pas
  porter le nom d'un effet officiel.
- Validation CI (`test/neo_shader_kit_dolphin_test.py`) : traduction,
  compilation iPhone des deux étapes MSL, dessin par une **reproduction de
  l'interface de post-traitement de Dolphin** (`neoshader-dolphin-validate` :
  un triangle, tampon d'uniformes de `FillUniformBuffer`, texture tableau,
  échantillonneur linéaire) comparé au rendu sans effet. Ce n'est pas le cœur
  Dolphin lui-même. Résultat : run 38334940237 (commit `71b8815`), 43 effets
  officiels sur 45 rendus (de 2,7 % à 100 % des pixels changés, de 0,37 à
  1,50 ms de GPU à 1186 × 890 sur le GPU paravirtuel), les deux effets HDR
  sans effet visible ; verdicts transcrits dans
  `tools/shaders/dolphin-metal-results.json`, avec l'analyse des sources pour
  les deux effets HDR, signalée comme telle.

## 4. Mattias CRT

Voir `docs/shaders-mattias-crt.md` : analyse technique, chemin d'import
compatible, et ce qui empêche la redistribution.

## 5. Proposition (non activée) : changement d'effet en direct pour Dolphin

Le changement en direct demande une fonction du cœur, par exemple
`neostation_dolphin_set_post_processing(const char* name)` qui ferait
`Config::SetCurrent(Config::GFX_ENHANCE_POST_SHADER, name)` sur le fil du
cœur (Dolphin recompile alors l'effet via
`CONFIG_CHANGE_BIT_POST_PROCESSING_SHADER`, `VideoCommon/Present.cpp`) et une
fonction pour les options. Cela modifie l'ABI du cœur conservé, bloqué par la
porte d'identité de la livraison : à décider explicitement par le mainteneur,
avec une nouvelle construction du cœur et ses propres validations.

## 6. Mentions légales

glslang et SPIRV-Cross : `assets/legal/glslang-LICENSE.txt`,
`assets/legal/SPIRV-Cross-Apache-2.0.txt`, section dédiée de
`THIRD_PARTY_NOTICES.md` et de `docs/LEGAL_AND_CREDITS.md`, crédits dans
l'application. Les fichiers de `libretro/slang-shaders` ne sont pas
empaquetés : téléchargés à la demande au commit épinglé, chacun sous sa propre
licence ; 207 entrées du catalogue ne mentionnent aucune licence dans leurs
fichiers et l'application l'indique (« Aucune licence indiquée »).

## 7. Non vérifié

- Aucun shader n'a été appliqué sur un iPhone ni sur une Apple TV.
- Le cœur Dolphin n'a pas été exécuté avec un effet choisi par NeoStation.
- Les durées de compilation et le temps GPU sur iPhone ne sont pas mesurés.
