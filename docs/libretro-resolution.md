# Résolution interne du moteur libretro intégré (Build 455)

Demande du mainteneur du 13 octobre 2026 : un réglage d'augmentation de résolution pour les émulateurs du moteur
libretro intégré (« RetroArch embarqué »), extensible aux futurs cœurs. Natif par défaut, valeurs réellement prises en
charge seulement, choix mémorisé par cœur avec priorité aux préférences propres à un jeu, application immédiate quand
le cœur le permet, sinon message clair de relancement. Résolution interne, agrandissement de l'image et filtrage
distingués ; proportions, écrans tactiles, doubles écrans, shaders, sauvegardes et Fast Interpreter d'Azahar
préservés.

## 1. Trois réglages distincts

| Réglage | Ce qu'il change | Où |
| --- | --- | --- |
| Résolution interne | La taille à laquelle le cœur dessine le jeu (surtout la 3D). Option du cœur. | Menu en jeu › Réglages d'émulation › Résolution et image ; réglages de la console |
| Agrandissement de l'image | Comment NeoStation agrandit l'image du cœur pour remplir l'écran : format d'écran, disposition des écrans (DS/3DS), shaders, dont les shaders d'agrandissement (catégorie « upscaling » du catalogue vérifié). La résolution du jeu ne change pas. | Même page (liens vers les pages existantes) |
| Filtrage | Lissage linéaire ou pixels nets de l'image agrandie ; un shader actif garde son propre filtrage. | Même page (le même interrupteur « Image lissée » que le menu principal) |

Un cœur sans résolution interne (les cœurs 2D) l'affiche : « Non proposée par {cœur} », avec l'explication, et garde
l'agrandissement et le filtrage.

## 2. Options des cœurs (sources amont)

Relevé du 13 octobre 2026 sur `raw.githubusercontent.com`, révision par défaut de chaque dépôt (Azahar à
`5f3306d1`, la révision épinglée). Les binaires embarqués sont ceux du buildbot (seul Azahar est épinglé par
révision) ; `test/libretro_core_options_test.py --cores` vérifie dans chaque binaire épinglé la clé, chaque valeur, la
valeur par défaut et le nom de bibliothèque déclarés au catalogue.

| Cœur | Clé | Valeurs (défaut du cœur) | Application | Preuve dans les sources |
| --- | --- | --- | --- | --- |
| Azahar (3DS) | `citra_resolution_factor` | `1` à `18` (`1`) | En jeu | `retro_run` : `HasUpdatedConfig()` → `ParseCoreOptions()`, `ApplySettings()`, `UpdateLayout()` (`SET_GEOMETRY`) ; `RasterizerCache::TickFrame` recrée les surfaces à la nouvelle échelle |
| DeSmuME (DS) | `desmume_internal_resolution` | `256x192` à `2560x1920`, par écran (`256x192`) | En jeu | `check_variables(false)` hors du bloc de démarrage, `SetCustomFramebufferSize`, puis `SET_SYSTEM_AV_INFO` ou `SET_GEOMETRY` ; rastériseur logiciel seul sur iOS (3D mise à l'échelle, 2D agrandie) |
| Beetle PSX HW (PS1) | `beetle_psx_hw_internal_resolution` | `1x(native)`, `2x`, `4x`, `8x`, `16x` (`1x(native)`) | En jeu (OpenGL, logiciel) ; au relancement (Vulkan) | `check_variables` : branche d'exécution, `SET_SYSTEM_AV_INFO` ; le rendu Vulkan ne se reconstruit qu'au `context_reset` |
| Beetle PSX (PS1, logiciel) | `beetle_psx_internal_resolution` | idem | En jeu | `retro_run` : `GPU_Rescale`, `SET_SYSTEM_AV_INFO` ; la VRAM logicielle est réellement agrandie |
| PPSSPP (PSP) | `ppsspp_internal_resolution` | `480x272` à `4800x2720` (`480x272`) | En jeu (OpenGL) ; au relancement (Vulkan) ; jamais dans son contexte logiciel | `check_variables` : `iInternalResolution != prev && backend != NONE` → `SET_SYSTEM_AV_INFO`, `NotifyDisplayResized`, réinitialisation GL ; l'option dit « Core restart required with Vulkan » ; option de rendu logiciel = 1x forcé. Sans contexte OpenGL ES ni Vulkan, PPSSPP prend `LibretroSoftwareContext` : ses images restent 480 × 272 (`SwapBuffers` : `NATIVEWIDTH`), et un changement en jeu fait appeler `((LibretroHWRenderContext *)ctx)->ContextReset()` sur ce contexte logiciel (`resetHWContext` pour tout contexte non Vulkan) : comportement indéfini, plantage de la sonde simulateur (run `38385450271`) |
| Mupen64Plus-Next (N64) | `mupen64plus-43screensize` (GLideN64) | `320x240` à `3840x2880` (`640x480`) | Au relancement | lu dans `update_variables(true)`, appelé seulement par `retro_load_game` ; aucun `SET_GEOMETRY` ni `SET_SYSTEM_AV_INFO` |
| Mupen64Plus-Next (ParaLLEl-RDP) | `mupen64plus-parallel-rdp-upscaling` | `1x` à `8x` | Au relancement | consommé seulement par `RDP::init()` |
| Nestopia, Snes9x, Gambatte, mGBA, Genesis Plus GX (+ Wide), PicoDrive, FinalBurn Neo | — | — | — | Aucune résolution interne générale. Options voisines laissées de côté : `snes9x_mode7_hires` (Mode 7 seul), `fbneo-resolution` (jeux vectoriels seuls), filtres NTSC, rendu entrelacé de Genesis Plus GX |

Le moteur NeoStation suit ces changements : `SET_SYSTEM_AV_INFO` réalloue la surface OpenGL ES (`_glNeedsResize`), le
pont Vulkan agrandit ses tampons de copie à la taille de chaque image, le présentateur Metal agrandit son anneau de
textures (16384 px au plus). Les régions des deux écrans (DS, 3DS) et le pointeur tactile sont normalisés : une image
agrandie uniformément garde le découpage et le toucher. Les préréglages de shaders reçoivent la taille console d'une
image agrandie uniformément (`LibretroShaderSourceSize`).

## 3. Reconnaissance extensible

`lib/services/libretro_resolution.dart` (Dart) et `LibretroResolution.m` (natif) appliquent les mêmes règles ; Dart
les envoie au lancement (`resolution` de la requête, `LibretroResolution.nativeRules()`, figées dans
`test/fixtures/libretro_resolution/native_rules.json`).

1. **Profils** (`LibretroResolution.profiles`) : noms connus d'un même réglage selon les cœurs, avec l'application
   (`live` seulement là où la source le prouve), la taille native des valeurs « LxH », un facteur maximal, des
   conditions sur d'autres options (`requires`) et les moteurs de rendu pour lesquels la source a été lue
   (`renderers` : `gles`, `vulkan`, `software`, comme `rendererName` de la session). Une clé peut avoir plusieurs
   profils (PPSSPP OpenGL/Vulkan, Beetle OpenGL ou logiciel/Vulkan) ; le premier décrit la configuration par défaut.
   Des profils couvrent aussi des cœurs non embarqués (Flycast `reicast_internal_resolution`, melonDS
   `melonds_opengl_resolution`, Dolphin `dolphin_efb_scale`, SwanStation, Kronos, YabaSanshiro, parallel-n64, Play!,
   LRPS2) : au relancement, faute de preuve.
   Les moteurs de rendu sont vérifiés une fois le contenu chargé (le cœur a alors obtenu, ou non, son contexte
   matériel) ; avant, ils ne sont pas une condition : le natif par défaut reste toujours applicable. PPSSPP n'a de
   résolution qu'avec OpenGL ES (en jeu) ou Vulkan (au relancement), Beetle PSX avec OpenGL ES ou son rendu
   logiciel (en jeu) ou Vulkan (au relancement), Azahar avec Vulkan ou OpenGL ES, Mupen64Plus-Next (GLideN64) avec
   OpenGL ES, ParaLLEl-RDP avec Vulkan ; DeSmuME n'a pas de condition (rastériseur logiciel).
2. **Reconnaissance générique** : une option visible dont le nom (`internal_res…`, `render_scale`,
   `resolution_factor`, `upscal…`, `efb_scale`…) ou la description (« internal resolution », « rendering
   resolution »…) désigne une résolution interne, et dont les valeurs incluent le natif. Appliquée au prochain
   lancement. Une clé nommée par un profil n'est jamais reconnue génériquement (le rendu logiciel de PPSSPP force
   1x : aucune résolution n'est alors proposée). Un cœur qui déclare une telle clé sans qu'aucun de ses profils
   s'applique (autre moteur de rendu, autre réglage, option masquée) a une résolution **inapplicable** : la page
   l'explique ainsi (`resolutionInapplicableFooter`), distinctement d'un cœur sans réglage.
3. **Lecture des valeurs** (cas partagés : `test/fixtures/libretro_resolution/value_cases.json`) : « 2x », « 2X »,
   « 1x(native) », « x2 », « ×3 », « 2 », « 1.5x » ou « 1,5x », « Native »/« original » ; « 960x544 », divisé par la
   taille native du profil ou la plus petite taille déclarée (une taille d'une autre forme est écartée).
4. **Valeurs offertes** : une par facteur, du natif au facteur maximal du profil, et au plus 8192 px sur le plus
   grand côté de l'image console × facteur. Limites retenues : Azahar 10x (au-delà, l'image dépasse le maximum de
   7200 × 4800 annoncé par le cœur) ; Beetle PSX 8x, PPSSPP 5x, Mupen64Plus 6x (1920 × 1440), limites des builds
   précédentes (16x de Beetle : environ 600 Mio et une VRAM de 16384 px). DeSmuME : toutes (10x).

## 4. Valeur en effet, mémorisation

- **Par cœur** : `Config/<bibliothèque>.json` (`{"values": …}`), le fichier existant, lu et écrit aussi par les
  réglages de console (`LibretroCoreOptionStore`, refusé pendant un jeu).
- **Par jeu** : `Config/Games/<bibliothèque>.json`, `{"version": 1, "games": {"<système>/<rom>": {clé: valeur}}}`.
  Seule l'entrée du jeu lancé est lue et réécrite ; les autres jeux et les clés inconnues sont conservés. Une build
  antérieure ignore ce fichier sans l'effacer.
- **Valeur en effet** : valeur gardée pour la session (choix pour le prochain lancement), surcharge de session, valeur
  du jeu, valeur du cœur, défaut NeoStation, défaut du cœur — la première que le cœur propose.
- **Natif par défaut** : une fois les options déclarées et avant `retro_init`, un cœur dont le défaut n'est pas le
  natif démarre en natif si aucune valeur n'est choisie (`LibretroResolutionApplyNativeDefault`). Changement de
  comportement : Mupen64Plus-Next (défaut du cœur 640×480) et PPSSPP (défaut NeoStation 960×544 retiré) démarrent en
  natif ; un choix déjà enregistré est conservé.
- **Instantané** : à chaque lancement, `Config/Resolution/<cœur>.json` décrit ce que le cœur a déclaré (option, valeurs,
  facteurs, application) ou l'absence d'option, avec le moteur de rendu obtenu (`renderer`) et, pour une option
  inapplicable, sa clé (`inapplicableKey`) ; les réglages de console l'utilisent plutôt que le catalogue.

## 5. Surfaces

- **Menu en jeu** : « Réglages d'émulation » est désormais présent pour tous les cœurs ; sa première ligne
  « Résolution et image » ouvre la page. Portée « Tous les jeux avec {cœur} » / « Ce jeu uniquement » ; valeurs
  « Native », « ×2 »… (taille pour les valeurs « LxH ») ; pied : origine du réglage, application (« dès la reprise du
  jeu » ou « quittez le jeu puis relancez-le »), « Une résolution plus élevée augmente la charge graphique. » ; « Image
  produite par le cœur » (taille réelle de la dernière image) et, si besoin, « Au prochain lancement ». Les
  réglages curatés « Résolution interne » de Mupen64Plus-Next, Beetle PSX HW et PPSSPP sont remplacés par cette page.
- **Réglages de la console** : Paramètres du système › Émulateurs (ligne « Résolution et image » après Skins) et onglet
  Consoles (bouton). Chaque cœur de la console, valeurs détectées au dernier lancement ou du catalogue, choix pour
  tous les jeux du cœur au prochain lancement, nombre de jeux réglés individuellement (jamais modifiés).
- **Journal de session** : option reconnue et valeur en effet au chargement (ou « does not apply (renderer …) » pour une
  option inapplicable), choix du menu, changements de taille de l'image produite (24 au plus).

Textes : 23 libellés natifs (dont l'explication d'une option inapplicable, aussi affichée par les réglages de la
console) et 9 libellés Flutter, douze langues (`LibretroLocale`, `LibretroRequiredUIText`).

## 6. Vérifications

- `test/libretro_resolution_test.dart`, `test/libretro_resolution_screen_test.dart` : lecture des valeurs (cas
  partagés), règles figées, profils, déclarations du catalogue, service, page Flutter (valeurs, enregistrement, refus
  pendant un jeu, cœur 2D, jeux réglés individuellement, virgule décimale en français).
- `test/libretro_host/host_test.m` (macOS) : cas partagés côté natif ; cœur de test à résolution réglable en direct :
  natif par défaut lu dès `retro_init`, changement pour le cœur puis pour le jeu appliqués en cours de jeu (taille des
  images et `SET_SYSTEM_AV_INFO`), persistance par cœur et par jeu, choix au prochain lancement, conditions de profil,
  moteurs de rendu (avant le chargement, nommé, autre), règles de PPSSPP envoyées par l'app (OpenGL ES en jeu, Vulkan
  au relancement, contexte logiciel et option de rendu logiciel : rien), option masquée, cœur sans option.
- `test/libretro_simulator_probe.py` (Simulateur iOS, vrais cœurs, appel de session du menu en jeu) : DeSmuME sur une
  image DS minimale écrite par la sonde — ×2 pour tous les jeux du cœur double les images produites (256 × 384 →
  512 × 768) dès la reprise et s'enregistre pour le cœur ; relancé, il démarre à ×2, et le natif choisi pour ce jeu
  seul rend 256 × 384 aussitôt, enregistré pour le jeu, le cœur gardant ×2. PPSSPP, sans contexte OpenGL ES dans le
  Simulateur, dessine dans son contexte logiciel : aucune résolution proposée, choix refusé, images inchangées, jeu
  toujours en cours, instantané `inapplicableKey` (avec un contexte OpenGL ES, le même scénario attend ×2 en jeu).
- `test/libretro_core_options_test.py --cores` : options, valeurs, défauts et noms de bibliothèque dans les binaires
  épinglés.

Ces essais ne remplacent pas une validation sur iPhone (charge réelle, mémoire, Vulkan d'Azahar sur appareil).
