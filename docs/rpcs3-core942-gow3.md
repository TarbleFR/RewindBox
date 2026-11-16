# RPCS3 Core 942 — God of War III : à-coups, charge du fil RSX, scintillement du feuillage

Demande du mainteneur (16 novembre 2026) : « Le jeu GW3 reste très instable et les FPS présentent toujours
d'importantes fluctuations et de flickering sur les arbres. Les journaux et les mesures déjà disponibles doivent
maintenant servir à identifier les causes […] Ne limite pas ton intervention à deux correctifs. »

Source des mesures : journaux privés (hors Git) de l'IPA 760 = Core 940, session God of War III BCES00510 (PID 24610,
109 s, démarrage normal puis « Continuer »), 21 fenêtres de 5 s, trois captures de profil PPU/SPU, 93 images lentes
décrites une à une. **Rien de ce document n'a été mesuré avec le Core 942 : aucun gain d'images par seconde, de
régularité ou d'image n'est annoncé avant les prochains journaux.**

## 1. Ce que mesurent les journaux

| Scène | Images/s | Durée d'image médiane / p95 / p99 | PPU / SPU / RSX (cœurs) | GPU occupé | Cœurs P | État |
|---|---|---|---|---|---|---|
| Écran-titre | 60 | 16,7 / 17,6 / 17 à 132 ms | 0,05 / 0,07 / 0,03 | 6 à 23 % | 3,9 GHz | fair |
| Transition, jeu léger | 46 à 59 | 17 à 46 / 30 à 66 / 54 à 78 ms | 0,7 à 1,1 / 0,7 à 1,9 / 0,08 à 0,23 | 26 à 39 % | 1,8 à 3,2 GHz | fair |
| Scène lourde (12 fenêtres) | 13,5 à 21 | 45 à 71 / 69 à 116 / 83 à 288 ms | 0,80 à 0,96 / 3,1 à 3,4 / 0,31 à 0,49 | 28 à 39 % | 1,26 à 1,45 GHz | fair |

Configuration réellement appliquée (`CONFIG_LAYERS`) : entrée de la base RPCS3 (Write Color Buffers, précision Ultra,
blocs SPU Mega), résolution 100 %, MSAA Auto, ZCULL « approximatif » (défaut iOS), shaders asynchrones (Core 939),
réservations SPU exactes, contournement MLAA appliqué (`GOW3MLAA909 ppu=applied`), soumissions MoltenVK asynchrones.
Aucune erreur, aucun gel, aucun arrêt anormal dans la session ; aucun shader ni pipeline compilé pendant la scène
lourde (0 dessin sauté).

## 2. Problèmes identifiés, par ordre d'impact

| # | Problème | Ce que disent les mesures | Traité |
|---|---|---|---|
| 1 | La scène lourde est limitée par le CPU, bridé par la chaleur | Cœurs P à 1,26-1,45 GHz (3,9 GHz à l'écran-titre), les deux saturés ; fil principal PPU actif à 79-85 %, dont 51 % des échantillons sur une seule adresse (`0x2eafe8`, un stockage conditionnel) ; trois fils SPU (`BigCellSpursKernel0-2`) exécutent le même travail à 88-92 %, un quatrième à 85 % ; GPU à un tiers. Énergie CPU par image : 104 à 167 mJ pour environ 2,1 W évacués | Mesure ajoutée (§ 3.3) ; pas de correctif sûr sans elle |
| 2 | Le fil RSX re-hache ses textures en permanence | 84 « époques » de validation par image, dont 69 déclenchées par les transferts d'image exécutés sur le CPU ; 11 708 hachages par fenêtre sur le fil RSX (150 par image), 8 à 37 ms de son étape « textures » par image mesurée ; le fil de pré-hachage n'en sert que 9 % et hache 3,3 Go par fenêtre | **Corrigé** (§ 3.1) |
| 3 | L'image n'a plus aucun anti-crénelage | MLAA contourné (voulu : il coûtait le temps SPU et une relecture 1280×720 par image), MSAA non demandé par le jeu, sortie bilinéaire sans filtre : le feuillage fin « fourmille » d'une image à l'autre, d'autant plus à 14-21 images/s | **Corrigé** (§ 3.2), à confirmer à l'écran |
| 4 | Attentes ZCULL du fil RSX | 147 à 312 ms par fenêtre en scène lourde (2 à 4 ms par image, jusqu'à 12 ms sur une image lente), 474 à 794 ms à l'écran-titre ; 16 000 rapports d'occlusion par fenêtre | Non modifié (§ 4) |
| 5 | Images isolées très longues | 9 images de plus de 125 ms en 50 s ; les deux pires (230 et 288 ms) suivent de 48 et 29 ms le départ et la fin d'une capture de profil automatique, mais 4 des 6 bornes de capture n'ont pas d'image lente | Non prouvé, non modifié |
| 6 | Les fils SPU chargés n'obtiennent pas tout leur temps | 0,66 à 0,75 cœur de CPU chacun pour 88-92 % d'état « actif », alors que les cœurs E ont 1,0 à 1,2 cœur libre et qu'iOS fait 9 000 à 11 000 changements de grappe par seconde | Constaté, non modifié (§ 4) |

Lecture d'ensemble : la cadence de la scène lourde suit la fréquence que la chaleur laisse aux cœurs P et le travail
des SPU ; le rendu n'est pas le goulot (GPU à un tiers, fil RSX à 0,3-0,5 cœur). Les à-coups viennent d'abord de ce
travail CPU ; le fil RSX y ajoute sa propre variabilité (8 à 37 ms selon l'image), que le correctif 3.1 retire.

## 3. Modifications du Core 942

### 3.1 `REWINDBOX_SCOPED_CPU_BLIT_942` — revalidation ciblée après un transfert d'image CPU

- **Problème constaté.** `EPOCH909` : sur 6 555 époques de validation d'une fenêtre, 5 419 portent la source `blit_cpu`
  (848 `put`, 205 `acquire`, 78 fin d'image, 5 invalidations). `OPT581` : 1 111 validations servies par le pré-hachage
  contre 11 708 faites sur le fil RSX. `RSXFRAME551` : 10,5 à 16,2 ms d'étape « textures » par image en moyenne, 37 ms
  au pire.
- **Cause.** Quand un transfert d'image NV3089 n'est pas fait par le GPU, le Core copie les octets lui-même dans la
  mémoire du jeu puis ouvre une nouvelle époque : toutes les validations de textures sont annulées, et chaque texture
  échantillonnée ensuite est hachée de nouveau. Le Core 909 avait gardé cette source « globale » parce que les octets
  écrits n'étaient pas bornés (décalage de destination, surfaces « swizzled », lignes mises à l'échelle).
- **Correction** (`Emu/RSX/NV47/HW/nv3089.cpp`). Les octets écrits sont bornés pour une destination non « tiled » :
  tout part de l'adresse de destination plus le décalage de sortie ; une copie linéaire écrit au plus
  `max(out_h, clip_height)` lignes au pas de destination, une ligne ne dépassant jamais
  `max(pas, out_w × bpp, clip_width × bpp)` (64 octets de marge) ; une copie « swizzled » écrit exactement les deux
  côtés arrondis à la puissance de deux. Seules les sections de cache qui recouvrent cet intervalle sont revalidées
  (`ios_rsx_wrote_guest_memory`, déjà employé par NV0039 et NV308A), après la libération du verrou de réservation.
  Destination « tiled », borne au-delà de 4 Gio ou levier de portée coupé : nouvelle époque, comme avant.
  L'intervalle est un sur-ensemble : trop large, il ne coûte que des hachages ; il ne peut pas laisser une texture
  modifiée par ce transfert validée.
- **Retour arrière.** Réglage « Scoped CPU blit revalidation » (Experimental → FPS Experiments) : Désactivé rend une
  époque par transfert, comme les Cores 909 à 941, sans toucher aux autres écritures ciblées. À utiliser si une texture
  paraît en retard d'une image : avec 69 époques de moins par image, une texture qu'un fil PPU ou SPU réécrirait sans
  aucune synchronisation avec le RSX resterait validée plus longtemps (au plus jusqu'au prochain PUT, 11 par image).
- **Vérifications.** Énumération des huit branches de `linear_copy`, de `clip_image`, `clip_image_may_overlap`,
  `convert_scale_image` et de `swizzled_copy_2` contre la borne, refaite par un relecteur indépendant (sur-ensemble
  prouvé ; `convert_linear_swizzle` exécuté par lui sur 2 162 tailles sous ASan/UBSan : il écrit exactement
  largeur × hauteur arrondies) ; contrôle de syntaxe du fichier sur l'hôte (mêmes messages qu'avant modification) ;
  `test/rpcs3_gow3_levers909_test.py` adapté (époque globale jusqu'au Core 941, intervalle borné à partir du 942).
- **À confirmer sur appareil.** `EPOCH909 blit_cpu` proche de 0 et `scoped_rsx_writes` en hausse d'autant,
  `OPT559 epoch_advances` autour de 1 100 par fenêtre au lieu de 6 500, `RSXFRAME551 texture_ms` et `OPT581 misses` en
  baisse, `rsx_cores` en baisse. Aucun changement d'image attendu.

### 3.2 `REWINDBOX_POST_AA_942` — FXAA à la présentation quand le MLAA du jeu est contourné

- **Problème constaté.** Scintillement des arbres signalé par le mainteneur. Les journaux ne voient pas l'image ; ils
  montrent en revanche que rien ne lisse plus les contours : MLAA contourné (`ppu=applied`), `msaa=Auto` sans MSAA
  demandé, aucune relecture d'image (`READBACK555` à zéro), mise à l'échelle bilinéaire.
- **Cause retenue (probable, non prouvée).** God of War III n'utilise pas le MSAA : son seul anti-crénelage est le MLAA
  que ses SPU appliquent à l'image finie. Le contournement le retire ; la géométrie fine découpée par test alpha
  (feuillage) change alors de pixels d'une image à l'autre.
- **Correction.** Le contournement reste (temps SPU, relecture). L'anti-crénelage revient sur le GPU : FXAA à neuf
  échantillons dans la passe qui met l'image à l'échelle de l'écran (`VideoOutCalibrationPass.glsl`, bit 1 de la
  constante `limit_range`, le bit 0 gardant son sens ; `VKOverlays`, `VKPresent.cpp`). Réglage « Post-process
  anti-aliasing (FXAA) » (Experimental → Rendering) : Automatique = God of War III tant que son MLAA est connu comme
  coupé à ce démarrage (moitié PPU écrite, état sauvegardé qui la contient, ou moitié SPU appliquée) ; Activé = toutes
  les images du jeu ; Désactivé = jamais ; lu au démarrage du jeu. Employé seulement avec la mise à l'échelle
  « Bilinear » (la passe échantillonne en linéaire) : pas avec Nearest, MetalFX, FSR, la sortie stéréo, ni quand la
  surface source est plus grande que la zone affichée. La première image compile le shader de la passe (un à-coup
  unique au démarrage).
- **Vérifications.** Le shader compile en SPIR-V (glslang 15.1, cible Vulkan 1.0), passe `spirv-val`, se traduit en
  Metal (SPIRV-Cross, cible iOS) ; la variante OpenGL de la même source est valide ; la version d'avant compile de la
  même façon. Côté C++ : relecture, compilation par la route Core.
- **À confirmer sur appareil.** `COREPROF POSTAA942 wanted=1 frames=` égal au nombre d'images de la fenêtre ; à
  l'écran : contours du feuillage stables, texte de l'interface à peine adouci. Si le scintillement persiste à
  l'identique, la cause est ailleurs (occlusion, § 4) : le dire avec une courte vidéo ou une capture.

### 3.3 `REWINDBOX_HOT_CODE_942` — les mots de code des points chauds (mesure seule)

- **Problème constaté.** 51 % des échantillons du fil principal portent une seule adresse, un stockage conditionnel.
  Le profil ne dit pas s'il s'agit d'une boucle d'attente sur un verrou (du temps de cœur P perdu, pendant que les SPU
  travaillent) ou du travail qui suit un petit utilitaire atomique.
- **Correction.** `PPUPROF912` et `SPUPROF923` ajoutent des lignes `part=code` : les 64 mots d'instruction des deux
  régions de 256 octets les plus chargées de chaque fil PPU suivi (lus par la copie protégée du fichier), et de la région
  la plus chargée de chaque fil SPU (copiée de sa mémoire locale au moment où elle prend la tête, car SPURS recharge
  d'autres travaux aux mêmes adresses). Journal de diagnostic privé ; rien n'est écrit dans le jeu.
- **Suite.** Si c'est une attente active, le correctif est une attente qui rend le cœur ; si c'est du travail, la
  piste est la génération de code de cette fonction. Dans les deux cas la prochaine modification sera ciblée.

## 4. Ce qui n'est pas modifié, et pourquoi

- **ZCULL « approximatif » et ses attentes.** Aucun levier du Core actif pour ce jeu ne rend un rapport d'occlusion
  provisoire ou périmé ; les attentes mesurées sont le prix d'un résultat exact. Le mode « relâché » les supprimerait
  mais a fait scintiller Assassin's Creed (Core 613). Si le FXAA ne règle pas les arbres, l'essai suivant est le
  comptage précis (« Accurate ZCULL stats »), à activer par jeu et à comparer.
- **Shaders asynchrones.** Aucun pipeline compilé ni dessin sauté dans la scène mesurée : ce mode n'explique pas un
  scintillement permanent. Il peut faire apparaître un objet un instant en retard à sa première rencontre.
- **Placement des fils SPU.** Le déficit (0,7 cœur obtenu pour 0,9 demandé) est mesuré, pas son remède ; le placement
  adaptatif a été abandonné le 5 novembre faute de gain mesuré. Non repris sans mesure.
- **Réservations SPU exactes.** Le fil principal est suspendu 12 à 17 % du temps par les écritures exactes des SPU
  (72 000 par seconde) ; le mode relâché a déjà perdu des mises à jour sur Black Ops II. Non modifié.
- **Captures de profil automatiques.** Coïncidence avec deux images longues, non reproduite sur les autres bornes.

## 5. Identités de cache

Aucun fichier d'entrée de la génération de code n'est modifié : identités PPU `a987639e9f838d1c` et SPU
`477a3fa442d27917` inchangées, caches des joueurs conservés.

## 6. Vérifications (PC)

- **Relecture indépendante** du commit avant la demande de compilation : aucun défaut bloquant ni majeur. Neuf remarques
  mineures, traitées : lecture des mots de code par `copy_if_mapped` (une page libérée à l'arrêt du jeu aurait pu
  fauter) ; région entière imprimée au lieu de la fenêtre autour du premier pc ; copie SPU prise pendant l'exécution ;
  FXAA limité au mode Bilinear ; FXAA automatique aussi avec la seule moitié SPU du contournement ; texte « prochain
  démarrage » ; borne « swizzled » exacte ; interrupteur propre pour le transfert CPU ; libellé du compteur.
- Shader : SPIR-V (glslang 15.1, Vulkan 1.0), `spirv-val`, traduction Metal pour iOS (SPIRV-Cross), variante OpenGL.
- Syntaxe sur l'hôte (`-DRPCS3_IOS`) de `nv3089.cpp`, `RPCS3IOSFreezeDump.cpp`, `RPCS3IOSExperimentalPolicy.cpp` :
  seulement les messages des fichiers non modifiés. `VKPresent.cpp`, `VKOverlays.cpp` et `RPCS3IOSSettings.cpp`
  dépendent de bibliothèques absentes ici : relus à la main et par le relecteur, compilés par la route Core.
- Porte de la route Core (`--check-source-closure`), test de route, test du pin (source), règle des marqueurs ;
  correctif canonique re-matérialisé sur une copie propre de l'amont (513 fichiers ; deux fichiers amont portés pour la
  première fois : le shader de la passe et `VKOverlays.h`) ; l'incrément se retire proprement.
- Les 104 tests `--source` : aucun test qui passait sur le Core 941 n'échoue sur le Core 942 (27 passent ici ; les
  autres sont des bancs historiques qui refusent déjà l'arbre courant ou ses arguments sur cet hôte). Trois tests
  encodaient l'ancienne forme (`gow3_levers909`, `spu_profile923`, `spu_wait_site930`) : adaptés, verts sur les deux
  arbres.
- Non exécutés : bancs historiques, appareil.

## 7. À lire dans les prochains journaux

Même scène lourde, démarrage normal (pas un ancien état sauvegardé), 2 minutes : `EPOCH909`, `OPT559`, `OPT581`,
`RSXFRAME551 texture_ms`, `POSTAA942`, les lignes `part=code` de `PPUPROF912` et `SPUPROF923`, `FRAMEPROF527`
(médiane, p95, p99).

## 8. Compilation et livraison (16 novembre 2026)

Core 942 : première demande verte (run 43950007115), artefact vérifié (empreinte de l'API), épinglé (dylib `22c1c3d5`,
81 135 944 octets, empreinte 67fbf239 ; vérificateur du composant : `verified`) ; identités de cache inchangées, les
trois nouveaux marqueurs présents dans le binaire. IPA 763 sur la base 762 (run 43954777719, première demande,
verte) : seul le Core RPCS3 change ; MeloNX et S2Arm sont ceux de la base. IPA `e6f28a70…`, 331 341 591 octets,
vérifiée hors ligne après téléchargement (`passed-offline-checks`) et remise au mainteneur ; clé privée supprimée.
Groupes Flutter et natif non exécutés. **Non testée sur iPhone** : régularité, charge du fil RSX et image restent à
observer (§ 7).
