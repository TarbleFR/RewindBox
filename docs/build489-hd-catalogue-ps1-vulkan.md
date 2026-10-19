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

**État affiché.** La page Textures HD du menu en jeu montre ce que le cœur rapporte (journal du cœur lu par `LibretroCoreHost`) : rendu (Vulkan, OpenGL ES, logiciel), remplacement actif ou non, textures reconnues dans le dossier et attachées ; jamais « HD actif » sur le rendu logiciel ni sans texture reconnue. Le journal de session écrit `hd-textures: core=beetle renderer=… replace=… recognized=…`.

**Packs DuckStation.** Les packs faits pour DuckStation (ses propres hachages et noms) ne sont pas lus par Beetle ; NeoStation ne les renomme pas et ne les présente pas comme compatibles (exclusions S170–S175).

⟪résultats Simulateur et limites Beetle⟫

## 5. Vérifications

⟪CI⟫

## 6. Limites

⟪limites⟫

## 7. Livraison Build 489

⟪livraison⟫
