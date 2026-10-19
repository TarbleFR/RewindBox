# Build 489 — catalogue HD étendu (GameCube, Wii, 3DS) et Beetle PSX HW en Vulkan, 19 octobre 2026

Demande du mainteneur (19 octobre 2026) : étendre massivement le catalogue unifié de textures HD (priorités GameCube, Wii et 3DS, puis PSP et PS2) à partir des 386 références fournies (S001–S386), des autres projets de leurs auteurs et des annuaires ; mesurer et figer N0 (packs distincts installables) au départ, viser au moins 3 × N0 au total et séparément pour le GameCube, la Wii et la 3DS, et publier l'écart honnêtement ; ne compter comme « installable » qu'une archive vérifiée en CI, distincte du « rendu vérifié en jeu » ; implémenter réellement Beetle PSX HW avec son rendu Vulkan (MoltenVK) pour la PS1, avec l'état réel affiché et sans fausse conversion de packs DuckStation ; une IPA de test une fois stabilisé. Branche `Claude` seule, rien sur `main`, aucune release, pas de contournement de CAPTCHA, d'authentification, de paiement ni de limite d'accès, pas de réhébergement.

Inventaire généré : [`HD_TEXTURE_CATALOG_SOURCES.md`](HD_TEXTURE_CATALOG_SOURCES.md). Expansion 488 : [`hd-textures-expansion-2026-10-19.md`](hd-textures-expansion-2026-10-19.md). Architecture 486 : [`build486-hd-textures-catalogue.md`](build486-hd-textures-catalogue.md).

## 1. Règle de comptage et N0

- **Installable** : pack en un geste (fichier de l'auteur vérifié) ou pack manuel portant le fichier de l'auteur vérifié en CI (`download.verified`, § 3). Un lien manuel sans fichier vérifié n'est pas installable.
- **Une famille par pack** : résolutions, formats (PNG/DDS), éditions de plateforme (bureau/mobile), régions, styles de boutons, mises à jour, miroirs et dépendances d'un même pack comptent une fois (`family` des sources, sinon règles de `tools/textures/count_packs.py`). Les champs `family` et `scope` restent dans les sources ; l'index ne les porte pas.
- **Portée** : `complete`, `partial` (travail en cours, sélection, correctifs), `ui` (interface, polices, boutons).
- **N0 figé** sur l'index livré de la Build 488 (`2026-10-19.72e26f767470`, `python3 tools/textures/count_packs.py --git 2bdca0d4`) :

| Console | N0 | 3 × N0 | Nfinal | ajoutées | rapport | écart à 3 × N0 | complètes / partielles / UI | un geste / manuelles vérifiées | variantes | jeux |
|---|---|---|---|---|---|---|---|---|---|---|
| GameCube | 21 | 63 | 76 | +55 | 3,62 | atteint | 52 / 8 / 16 | 23 / 53 | 25 | 53 |
| Wii | 13 | 39 | 39 | +26 | 3,00 | atteint | 23 / 4 / 12 | 14 / 25 | 21 | 30 |
| 3DS | 10 | 30 | 37 | +27 | 3,70 | atteint | 16 / 7 / 14 | 11 / 26 | 6 | 45 |
| PSP | 56 | 168 | 82 | +26 | 1,46 | −86 | 62 / 7 / 13 | 56 / 26 | 14 | 97 |
| PS2 | 32 | 96 | 33 | +1 | 1,03 | −63 | 25 / 1 / 7 | 32 / 1 | 12 | 44 |
| N64 | 14 | 42 | 14 | +0 | 1,00 | −28 | 12 / 2 / 0 | 14 / 0 | 7 | 11 |
| PS1 | 0 | 0 | 1 | +1 | — | atteint | 0 / 1 / 0 | 1 / 0 | 0 | 1 |
| Total | 144 | 432 | 280 | +136 | 1,94 | −152 | 188 / 30 / 62 | 149 / 131 | 82 | 277 |

Index final `2026-10-19.85092338c53c` : 1034 entrées (194 en un geste, 168 manuelles à fichier vérifié, 672 liens sans fichier vérifié, dont les 637 liens PS2 de ps2ktxpak). « Rendu vérifié en jeu » : 0 pack (aucun n'a été chargé dans un jeu sur iPhone pendant ce cycle).

**Écart publié (Nfinal − N0).** GameCube +55, Wii +26, 3DS +27, PSP +26, PS2 +1, N64 +0, PS1 +1, total +136. L'objectif 3 × N0 est atteint pour le GameCube, la Wii et la 3DS ; il ne l'est pas au total (280 pour 432, écart 152) ni pour la PSP, la PS2 et la N64. L'objectif de plus de 800 packs distincts valides n'est pas atteint en packs installables : les 1 034 entrées de l'index n'y arrivent qu'en comptant 672 liens sans fichier vérifié, qui ne sont pas comptés ici.

**Doublons évités.** 362 entrées installables pour 280 familles : 82 résolutions, formats, éditions, styles de boutons et mises à jour comptés une seule fois. Les autres téléversements, formats ou add-ons d'un pack déjà catalogué que les sondes ont rencontrés ne sont pas ajoutés une seconde fois et figurent avec leur motif sous « Reviewed and left out » de l'inventaire.

**Rendu vérifié en jeu.** 0 pack : « installable » veut dire archive de l'auteur téléchargée sur un runner, taille et SHA-256 mesurées, installée par le code de l'application ; aucun pack de ce cycle n'a été chargé dans un jeu.


## 2. Exploration des références

**Méthode.** Les 386 références (S001–S386) ont été lues sur des runners CI (`research.py refs`, partie `research` de `hd-textures.yml` : page, API publiques GitHub et GameBanana, pages d'annuaire suivies), puis chaque fichier téléchargeable trouvé a été sondé (`research.py probe` : arborescence de l'archive résumée comme la lisent les moteurs, taille, SHA-256 ; rien n'est publié ni conservé). Les autres projets des auteurs, les fils du forum Dolphin et du forum PPSSPP, les listes de rapka, thelostgrimm et Admentus64 et la feuille Texture Packs Archive ont été suivis de la même façon, ainsi que 12 recherches GameBanana génériques (3 pages chacune) et 56 recherches par jeu GameCube/Wii (runs `39315268955` et `39315276351` : 743 mods lus, dont 155 GameCube/Wii et 14 retenus pour une sonde, le reste étant des mods de fichiers de jeu, des skins ou des portages PC).

**Sondes.** 934 enregistrements pour 845 URL de fichiers distinctes : 449 archives lues, 137 pages protégées (défi anti-robot, connexion, CAPTCHA : jamais contournés), 85 fichiers retirés (404, fichiers MEGA supprimés), 64 dossiers partagés (développés en leurs fichiers), 45 archives non prises en charge (RAR surtout ; l'application n'ouvre pas le RAR), 11 quotas atteints (Google Drive, MEGA), 16 pages HTML à la place du fichier, 16 erreurs, 21 sans statut final. Deux runs de sonde (`39295542382`, `39294151651`) ont atteint leur limite de 300 minutes après 5 fichiers sur 38 et 26 sur 45 ; ces résultats partiels ne sont pas revus dans ce cycle (catalogue figé).

**Décisions.** 456 archives distinctes (par SHA-256) : 172 deviennent des entrées du catalogue, 272 sont écartées avec leur motif, 12 restent des candidats pour un cycle suivant (ci-dessous). Les vérifications d'installation de ce cycle : 17 runs enregistrés (`tools/textures/ci-records.json`), 202 enregistrements dont 31 échecs conservés tels quels : 9 quotas Google Drive (packs restés des liens), 5 archives au-delà des limites de l'installateur sur iPhone, 4 archives contenant une image endommagée, 5 dossiers lus comme un autre jeu (dossier déclaré puis revérifié avec succès), 3 archives sans texture qu'un moteur charge, 2 copies refusées, 1 format non pris en charge, 1 fichier changé par GameBanana sous le lien sondé, 1 transfert MEGA bloqué 4 heures (revérifié avec succès après la borne de 45 minutes de `hosts.py`). Un enregistrement remplacé par une vérification ultérieure est marqué `superseded` dans le run qui l'avait produit.

**Issue de chaque référence** (« pack catalogué » : au moins une entrée de l'index, installable ou lien ; « jeu couvert » : le jeu a déjà un pack d'une autre source ; « lue, sans fichier exploitable » : page lue, aucun fichier qu'un moteur sache charger) :

| Références | pack catalogué | jeu couvert (titre) | exclue | lue, sans fichier exploitable | fichier lu, candidat | protégée | injoignable | morte | non lue | total |
|---|---|---|---|---|---|---|---|---|---|---|
| GameCube | 18 | 11 | 3 | 18 | 0 | 1 | 0 | 0 | 0 | 51 |
| Wii | 11 | 8 | 0 | 20 | 0 | 2 | 0 | 0 | 0 | 41 |
| 3DS | 21 | 10 | 4 | 11 | 0 | 6 | 6 | 0 | 0 | 58 |
| PSP | 45 | 4 | 4 | 76 | 2 | 0 | 0 | 0 | 0 | 131 |
| PS2 | 74 | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 78 |
| PS1 | 0 | 0 | 7 | 1 | 0 | 4 | 0 | 0 | 0 | 12 |
| Annuaires | 6 | 0 | 0 | 6 | 0 | 2 | 1 | 0 | 0 | 15 |
| Total | 175 | 33 | 18 | 132 | 2 | 19 | 7 | 0 | 0 | 386 |

**Contrôle des liens** (run `39315058711`, index du commit `7435f8fd`, 1 006 entrées) : 362 pages et fichiers joignables (188 en un geste, 174 manuels), 632 pages refusées aux lectures automatiques (toutes sur gbatemp.net, HTTP 403 : elles restent des liens), 3 pages cassées — des adresses de fils du forum Dolphin raccourcies par erreur, corrigées (`5647c853`) —, 9 signalements de version : quatre dépôts dont la branche a avancé depuis le commit vérifié (le catalogue reste épinglé sur ce commit), Pokémon Y Resurrection v2.3 plus récente que la v0.2 cataloguée (non adoptée, non vérifiée), et quatre faux positifs (la dernière publication du dépôt est un autre pack).

**Candidats non catalogués** (fichier lu, à revoir) : Phazon UI v1.19 (archive qui semble être un thème de l'interface de Dolphin), Gauntlet: Dark Legacy HD 2.0 pour PCSX2 (dossier du numéro de série inconnu), SoniPro HD, Tomodachi Life HD Miis (trois régions), Majora's Mask 3D Project Restoration UI et boutons PlayStation, A Link Between Worlds (jaz) pour la 3DS, Resistance: Retribution HD, Ys Seven HD et une archive Dissidia 012 (NPHH00293) pour la PSP, dont les identifiants de jeu ne sont ni dans l'archive ni dans le titre.


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

Source testée : `7c6a86e425f678607a885d3be70bb64221919732` (catalogue figé, index `2026-10-19.85092338c53c`, SHA-256 `3d46adc5d94ccd9694ae7d94d902f6ad0c001139605920ef8cf3ce56840eb6c4`). Toutes les parties ont été exécutées sur cette source ; aucune n'est reprise d'une source antérieure.

| Vérification | Run / job | Résultat |
|---|---|---|
| Partie `host` de `hd-textures.yml` (lecteurs, identités, installateur, libellés, catalogue, contrats, Flutter) | `39337036938` / `118349013443` | réussi : 51 vérifications, 207 entrées ; libellés en 12 langues (177 clés natives, 4 Flutter) ; `build_catalogue.py --check` (1 034 entrées) ; **290 enregistrements CI comparés à leurs artefacts** (`check_ci_records.py`, dont tous ceux recopiés des journaux dans ce cycle) ; 130 tests Flutter ; test de la porte de l’IPA (13 + 4 cas de refus) |
| Partie `native` (magasin et adaptateurs sur Foundation, SDK iPhone) | `39337040395` / `118349023281` | réussi : 7 vérifications, 156 entrées ; 8 sources `neo_texture_catalog` compilées et liées pour iPhone ; 77 objets du pont libretro liés (aucun symbole du pont indéfini) |
| Partie `uikit` (page Textures HD sur UIKit) | `39337043258` / `118349032287` | réussi : page unifiée avec le catalogue embarqué, rapport du moteur PS1 Beetle et options, import d'un pack manuel vérifié, douze langues |
| Beetle PSX HW dans le Simulateur (`libretro-simulator.yml`, `beetle_only`) | `39337045728` / `118349042081` | réussi : trois scénarios en Vulkan (iPhone SE 3e génération, iOS 26.2, 66,2 s) ; `frame` : `replace=off recognized=0`, 611 images ; `pack` : `replace=on recognized=5` (11 fichiers écrits, dont 6 que le cœur ignore), 13 vérifications de cycle de vie ; `off` : `replace=off recognized=5` ; rectangle `f80000` sur fond `202020` présenté dans les trois ; `applied=0` (aucun envoi de texture dans le Simulateur) |
| Garde MEGA de `hosts.py` (transfert bloqué → `quota`, fichier partiel supprimé) | `test/texture_verify_checks_test.py` (partie `host`) | 16 vérifications ; échoue sur l'ancien code (contrôle négatif local) |
| Contrôle des liens du catalogue | `39315058711` | voir § 2 |

Vérifications d'installation des packs : 17 runs du job `hosts` et `repositories` (§ 2), chacun enregistré dans `tools/textures/ci-records.json`.

Mises au point antérieures de Beetle (échecs conservés) : runs `39278458161` (SIGSEGV sur l'image nulle `A1R5G5B5`, corrigé par la garde de format), `39291452900`, `39293066511`, `39296323461`, `39299245695` (attente GPU de la sonde, copies CPU→VRAM refusées par le Simulateur) et `39302343072` (premier passage des trois scénarios, source `cc9f93a9`). Aucun test n'a été supprimé ni affaibli.

## 6. Limites

- **Rendu en jeu.** Aucun pack de ce cycle n'a été chargé dans un jeu sur un iPhone : « installable » veut dire archive et installation vérifiées par le code de l'application en CI, jamais « rendu vérifié en jeu » (0 pack dans cet état).
- **Objectif 3 × N0.** Atteint pour le GameCube (76), la Wii (39) et la 3DS (37) ; non atteint au total (280 pour 432), ni pour la PSP (82 pour 168), la PS2 (33 pour 96) et la N64 (14 pour 42). Les 637 liens PS2 de ps2ktxpak restent des liens (pages GBAtemp refusées aux lectures automatiques : HTTP 403) : la PS2 ne gagne qu'un pack installable (Rayman 2: Revolution HD, icup321). L'objectif de 800 packs distincts valides n'est pas atteint en packs installables ; aucun pack n'est inventé pour combler l'écart.
- **Hôtes.** Pages qui refusent une lecture automatique (GBAtemp HTTP 403, défi anti-robot de MediaFire, Discord, Patreon), quotas Google Drive, fichiers MEGA retirés : jamais contournés ; les packs concernés restent des liens ou des exclusions motivées (`tools/textures/sources/excluded*.json`).
- **Beetle PSX HW.** Dans le Simulateur, aucune texture n'est envoyée au GPU (copies CPU→VRAM refusées par son Metal) : remplacement à l'écran, chargement d'état en Vulkan, changement de disque d'un M3U et cartes mémoire pendant un remplacement restent à vérifier sur l'iPhone. Le rendu Vulkan sur un GPU d'iPhone (format `A1R5G5B5` pris en charge, garde inactive) n'a été exercé par aucun essai automatique. Un seul pack PS1 au format de Beetle est catalogué ; les packs DuckStation ne sont ni convertis ni proposés.
- **Version d'iOS** de l'iPhone de test toujours inconnue ; aucune mesure de mémoire ou de température avec un pack chargé.

## 7. Livraison Build 489

⟪livraison⟫
