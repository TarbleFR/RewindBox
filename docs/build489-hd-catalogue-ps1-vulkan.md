# Build 489 — catalogue HD étendu (GameCube, Wii, 3DS) et Beetle PSX HW en Vulkan, 19 octobre 2026

Demande du mainteneur (19 octobre 2026) : étendre massivement le catalogue unifié de textures HD (priorités GameCube, Wii et 3DS, puis PSP et PS2) à partir des 386 références fournies (S001–S386), des autres projets de leurs auteurs et des annuaires ; mesurer et figer N0 (packs distincts installables) au départ, viser au moins 3 × N0 au total et séparément pour le GameCube, la Wii et la 3DS, et publier l'écart honnêtement ; ne compter comme « installable » qu'une archive vérifiée en CI, distincte du « rendu vérifié en jeu » ; implémenter réellement Beetle PSX HW avec son rendu Vulkan (MoltenVK) pour la PS1, avec l'état réel affiché et sans fausse conversion de packs DuckStation ; une IPA de test une fois stabilisé. Branche `Claude` seule, rien sur `main`, aucune release, pas de contournement de CAPTCHA, d'authentification, de paiement ni de limite d'accès, pas de réhébergement.

Inventaire généré : [`HD_TEXTURE_CATALOG_SOURCES.md`](HD_TEXTURE_CATALOG_SOURCES.md). Expansion 488 : [`hd-textures-expansion-2026-10-19.md`](hd-textures-expansion-2026-10-19.md). Architecture 486 : [`build486-hd-textures-catalogue.md`](build486-hd-textures-catalogue.md).

## 1. Règle de comptage et N0

- **Installable** : pack en un geste (fichier de l'auteur vérifié) ou pack manuel portant le fichier de l'auteur vérifié en CI (`download.verified`, § 3). Un lien manuel sans fichier vérifié n'est pas installable.
- **Une famille par pack** : résolutions, formats (PNG/DDS), éditions de plateforme (bureau/mobile), régions, styles de boutons, mises à jour, miroirs et dépendances d'un même pack comptent une fois (`family` des sources, sinon règles de `tools/textures/count_packs.py`). Les champs `family` et `scope` restent dans les sources ; l'index ne les porte pas.
- **Portée** : `complete`, `partial` (travail en cours, sélection, correctifs), `ui` (interface, polices, boutons).
- **N0 figé** sur l'index livré de la Build 488 (`2026-10-19.72e26f767470`, `python3 tools/textures/count_packs.py --git 2bdca0d4`) :

⟪tableau N0 / objectif / Nfinal⟫

## 2. Exploration des références

⟪statistiques des 386 références, sondes, hôtes, exclusions⟫

## 3. Packs manuels à fichier vérifié

Un auteur qui publie sur MEGA, Google Drive, Dropbox, MediaFire, GameBanana ou archive.org garde un lien manuel (règle de la Build 486 : NeoStation ne télécharge jamais lui-même ces fichiers). Depuis la 489, le job `hosts` de `hd-textures.yml` récupère une fois sur les runners le fichier exact de l'auteur (`tools/textures/hosts.py` : liens publics seulement ; quota, connexion, CAPTCHA ou protection anti-robot → statut `protected`/`quota`, jamais contournés) et l'installe avec le code de l'application (`verify_packs.py --kind host`). L'index porte alors `download.verified` (format, nom, taille, SHA-256, hôte) : la page du pack propose « Importer le fichier téléchargé », et le magasin n'accepte que ce fichier exact (taille puis SHA-256 pendant la copie), installé comme un pack en un geste ; tout autre fichier est refusé sans rien toucher. Les applications 486–488 ignorent ces clés (lien manuel).

Les enregistrements de ces runs sont recopiés depuis leurs journaux (le conteneur de travail ne peut pas télécharger les artefacts) et `tools/textures/check_ci_records.py` (partie host) exige qu'ils soient identiques aux artefacts `hdtex-hosts-<console>-<run>`.

## 4. Beetle PSX HW en Vulkan (PS1)

**Cœur et dépendances (aucun cœur reconstruit).** Beetle PSX HW `mednafen_psx_hw`, version `0.9.44.1-GLES3 10e4b0c` (`libretro/beetle-psx-libretro` `10e4b0c6ceae20daa65ddf436a4445dddd0982d2`, paquet de cœurs épinglé `LibretroCores-fdeaef56…`, run `38638115521`), compilé avec son rendu Vulkan (`rhi/rhi_lib_vulkan.c`) et son suivi de textures (`rhi/rhi_tt.c`). MoltenVK 1.2.8 est le framework épinglé avec les cœurs (`build-utils/libretro/cores.json`, RetroArch `df16ef19`, fichiers vérifiés par SHA-256) ; il est déjà dans l'IPA (Azahar, PPSSPP). Aucune dépendance nouvelle.

**Contexte Vulkan.** Le choix de rendu du cœur (`rhi_intf_open`, « Hardware (Auto) ») n'ouvre OpenGL que pour une préférence OpenGL/OpenGL Core : la préférence OpenGL ES 3 donnée jusqu'à la Build 488 finissait toujours sur son rendu logiciel, qui ne remplace aucune texture. Depuis la 489, NeoStation demande un contexte Vulkan (`preferredHardwareContext: vulkan`) et le crée par l'interface de négociation libretro (`LibretroVulkanRenderer`, images remises à Metal par deux tampons hôtes). Si aucun périphérique Vulkan ne peut être créé, la session est relancée une fois sur le rendu logiciel (`LibretroInternalService`) et le dit.

**Format `A1R5G5B5` (défaut trouvé en CI et corrigé).** Quand il tramait (option par défaut « 1x (Native) »), le cœur produisait son image en `VK_FORMAT_A1R5G5B5_UNORM_PACK16` (`renderer_scanout_to_texture`, et `renderer_scanout_vram_to_texture` pour la vue VRAM) et utilisait l'image nulle que `device_create_image` rend quand le format manque (« Format 8 is not supported for usage flags! », puis SIGSEGV, run `39278458161`). MoltenVK 1.2.8 donne à ce format (Metal `BGR5A1Unorm`) attachement couleur, échantillonnage et blit sur les GPU d'iPhone, et rien dans un Simulateur sans `MTLGPUFamilyApple5` (celui des runners annonce « GPU Family Apple 2 »). Avant `loadCore`, une session Beetle en Vulkan lit les capacités réelles du format sur le GPU que `prepare:` utilisera (`+[LibretroVulkanRenderer optimalTilingFeatures:ofFormat:]`, instance jetable, résultat gardé pour le processus) ; sans les trois, la trame et la vue VRAM sont verrouillées pour la session (`beetle_psx_hw_dither_mode` et `beetle_psx_hw_display_vram` = `disabled`) et le cœur produit du `R8G8B8A8`. Le journal de session l'écrit dans les deux cas (`vulkan: A1R5G5B5 features 0x…`). Avec le format pris en charge, rien ne change.

**Options.** Interrupteur par jeu : `beetle_psx_hw_track_textures` + `beetle_psx_hw_replace_textures` (`Config/Games/Beetle PSX HW.json`), réversible. Verrouillées pour la session : dossier des textures `save`, aucun dump, cache paresseux, budgets VRAM et RAM de 512 Mo (les 3 Go / 2 Go du cœur sont des budgets de bureau).

**Dossier et disques.** Pack installé en `<nom du contenu>-texture-replacements` dans le dossier de sauvegarde du cœur, à côté des cartes mémoire, qui restent intactes ; le nom est celui du fichier que Beetle charge (CUE, CHD, PBP ou M3U). Un jeu multidisque lancé par son M3U garde ce nom pour tous ses disques (le changement de disque du menu passe par `set_image_index`, qui ne change pas `retro_cd_base_name` ; seul `replace_image_index`, que NeoStation n'appelle pas, le changerait) : un seul dossier, aucune copie par disque. Identité : numéro de série lu dans `SYSTEM.CNF` (CUE/M3U/CCD/BIN/ISO) ; CHD/PBP reconnus par le titre (et la région) avec confirmation.

**État affiché.** La page Textures HD du menu en jeu montre le rendu obtenu (Vulkan, OpenGL ES, logiciel), le remplacement actif ou non (Track + Replace Textures tels que le cœur les a reçus), les fichiers de remplacement que le cœur liste dans son dossier et les textures qu'il dit avoir attachées ; jamais « HD actif » sur le rendu logiciel ni sans fichier reconnu. Le journal de session écrit `hd-textures: core=beetle renderer=… replace=… recognized=…`.

*Défaut trouvé et corrigé.* Le suivi de textures du cœur (`rhi_tt.c`) liste son dossier de remplacements au démarrage du rendu, quand sa racine est encore le dossier du contenu ; la première image applique ensuite la racine `save` que NeoStation verrouille et relit le bon dossier, mais n'en écrit le compte que dans une compilation verbeuse. La ligne `num hd textures` lue jusque-là comptait donc le dossier du contenu : 0 pour tout pack NeoStation. La session compte désormais les fichiers de `<save>/<nom du contenu>-texture-replacements` selon la règle du cœur (`read_texture_directory` : `<hex>-<hex>.<ext>`, ext png/dds/webp/jpg/jpeg/bmp/tga sans casse, un par hachage et palette ; `LibretroCoreHost textureReplacementFilesInSaveFolder:`), au démarrage du rendu puis après le démarrage confirmé. Les textures attachées restent celles que le cœur annonce (`[hdcache] … attaches`).

**Packs DuckStation.** Les packs faits pour DuckStation (ses propres hachages et noms) ne sont pas lus par Beetle ; NeoStation ne les renomme pas et ne les présente pas comme compatibles (exclusions S170–S175).

**Simulateur (ce qui y est prouvé, ce qui ne l'est pas).** Dans le Simulateur, toute copie CPU→VRAM du rendu Vulkan de Beetle (envoi de textures, chargement d'un état) demande à MoltenVK une texture linéaire sur un tampon visible par l'hôte, que le Metal du Simulateur refuse (« Linear texture can only be created on buffers with MTLStorageModePrivate in the simulator », runs `39291452900` et `39299245695`) ; le Metal d'un iPhone l'accepte. Aucun remplacement de texture à l'écran, aucun dump et aucun chargement d'état ne peuvent donc y être exercés : ils restent à vérifier sur l'iPhone. La sonde (`--beetle`, BIOS de remplacement écrit par la sonde, jamais un BIOS de console) vérifie :
- `beetle-vulkan-frame` : l'image du GPU (écran effacé en gris, rectangle rouge rempli par le GPU) atteint le drawable présenté, en Vulkan, avec la garde `A1R5G5B5` ;
- `beetle-vulkan-pack` : avec Track + Replace Textures, un pack écrit dans le dossier que lit le cœur (5 noms valides, un second format de l'un d'eux et cinq noms que le cœur ignore) est rapporté comme exactement 5 fichiers, à travers 13 vérifications de cycle de vie (audio, pause/reprise, arrière-plan/premier plan, état sauvegardé en Vulkan, rotation aller-retour, Vulkan et pack toujours rapportés) ;
- `beetle-vulkan-off` : le remplacement coupé est rapporté coupé.

Mise au point de la sonde (échecs conservés) : le programme de remplacement attendait le bit 28 de GPUSTAT avant chaque mot, ce qui bloquait un quad (`INCMD_QUAD`) puis un transfert CPU→VRAM que Beetle ne démarre qu'avec ses trois mots (runs `39291452900`, `39293066511`, `39296323461`, marqueurs de progression en RAM) ; chaque commande attend désormais le bit 26 (GPU inactif) puis envoie tous ses mots.

Résultat : run `39302343072`, job `118230500429`, source `cc9f93a9` (iPhone SE 3e génération, iOS 26.2, Simulateur, 89,6 s) — les trois scénarios réussis :
- `beetle-vulkan-frame` : Vulkan, garde `A1R5G5B5` (`features 0x0 lack 0x481`, balayage 32 bits), 584 images 256 × 240 ; programme à 85 boucles ; drawable 750 × 1334 : rectangle `f80000` exactement sur les cellules 4–11 / 4–11 de la grille, fond `202020` autour ;
- `beetle-vulkan-pack` : `replace=on recognized=5` dès le rendu prêt et après 297 images (11 fichiers écrits, dont 6 que le cœur ignore) ; les 13 vérifications de cycle de vie réussies ; même image ;
- `beetle-vulkan-off` : `replace=off`, les 5 fichiers toujours listés, même image ; aucun dump.
`applied` reste 0 partout : aucune texture n'est envoyée, donc aucune n'est remplacée (voir ci-dessus). Ce n'est pas une validation sur iPhone.

## 5. Vérifications

⟪CI⟫

## 6. Limites

⟪limites⟫

## 7. Livraison Build 489

⟪livraison⟫
