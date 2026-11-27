# Passation : collection libretro avec DeSmuME (JIT, étapes 1 à 4), Beetle PSX (Lightrec) et Azahar 2127.0-rc5

*23 novembre 2026 — branche `Claude`. Note pour la session qui construit les IPA : consigne du mainteneur, « pas
d'ipa c'est une autre session qui la fera ». Cette session n'a lancé aucune livraison.*

*La collection précédente, `LibretroCores-6cd6a89b…` (id 14839590544, étape 0 de DeSmuME), est livrée dans
l'IPA 827. Celle-ci la remplace ; elle est livrée dans l'IPA 828.*

## Après la 848 : Azahar à 10×, deuxième série (Azahar seul)

*27 novembre 2026, branche `Claude`.* Journal du mainteneur (Mario Kart 7 à 9×, 600 images) : `fps=57.8`, `folded=0.00 flushed=1.48` : la première série ne pliait aucun effacement. Correctif `82b6a4d9` (43 fichiers) : effacements gardés jusqu'à leur passe, cibles gardées à travers un remplissage, stockage RGBA8 réservé aux ombres (compression sans perte Metal), répartition rapide arm64 dans dynarmic, mesures. Détail, champs nouveaux de `[rb-perf]`, ligne `[rb-jit] azahar cpu`, pistes écartées et protocole iPhone : `native/azahar/README.md`. Seul `azahar_libretro` change ; la collection compilée par le job `source-cores` de ce commit est à adopter par une livraison (autre session). Rien de mesuré sur iPhone.

## Après la 835 : 3DS à 10×, passes de rendu adaptées au GPU à tuiles (Azahar seul)

*24 novembre 2026, session « RetroArch MetalFX et JIT ».* Retour du mainteneur (Mario Kart 7 à 10×, image remise
sans copie) : 30 à 40 images/s, 50 au mieux, état thermique 2 après une minute ; demande : 60 constantes à 10×. Le
journal confirme `vulkan: frames reach Metal directly, no copy (4000x4800)` : le coût restant est le rendu.

- **Cause visée** : un GPU d'iPhone recharge et réécrit les attachements à chaque passe de rendu. À 10×, l'écran du
  haut fait 38,4 Mo de couleur et 48 Mo de profondeur-stencil : chaque passe coupée coûte environ 170 Mo. Azahar
  effaçait les tampons de chaque image par des commandes à part (une écriture complète, puis une relecture) et
  coupait la passe à chaque changement de fenêtre de dessin ou de cible unique (HUD sans profondeur).
- **Cœur** `native/azahar` (correctif `fc51c9fe`, 32 fichiers) :
  - effacements reportés, pris comme chargement `CLEAR` de la passe suivante ;
  - zone de rendu égale au rectangle des cibles ;
  - attachement gardé pour les dessins qui n'en utilisent qu'un ;
  - ligne `[rb-perf] azahar` toutes les 600 images.

  Détail et lecture des mesures : `native/azahar/README.md`. Rien ne change côté app.
- **Collection compilée** : run [45455871885](https://github.com/TarbleFR/RewindBox/actions/runs/45455871885)
  (commit `85a5528e`, qui affine `fceead82`, dont le run a été annulé), artefact
  `LibretroCores-85a5528ed969fd0e139c0494d3c72ab8acd624ec`, id 14952660121, 56 393 618 octets, SHA-256
  `7f3b87949c2cf2a6b9a1e33222f9b91eb24b52d7ce7c78fac276340aa3a1e9c1`, disponible jusqu'au 8 décembre. Entrée ajoutée à
  `COLLECTIONS`.
- **Ce qui change** par rapport à `e5378e84` (835) : `azahar_libretro` seul (`edd641bd…`, 17 055 608 octets), sa ligne
  de `LIBRETRO_CORES.txt` et `identity.json` ; DeSmuME (`741cf7b6…`), les deux Beetle PSX et les 244 autres fichiers
  sont identiques octet pour octet.
- **Vérifié sur l'archive téléchargée** :
  - empreinte identique à celle de l'API ;
  - `libretro_source_collections.verify` : 4 cœurs compilés, interface JIT, export ;
  - contrat d'options sur les 35 binaires ;
  - `standard_delivery_contract_test.py` : OK, 4 ignorés ;
  - Azahar arm64 iOS 14.0, chaînes épinglées et `[rb-perf] azahar`, sans `_task_set_exception_ports` ni `_mach_msg` ;
    `__text` grandit de 9 296 octets, le segment `__TEXT` garde sa taille.
- **Manifeste de la livraison qui l'adopte** : `components.libretro.origin` vers cet artefact ; `images.mustChange` :
  `Frameworks/azahar_libretro.framework/azahar_libretro` ; DeSmuME et les deux Beetle PSX restent retenus.
- **Même Azahar dans la collection DeSmuME suivante** : le run
  [45459585271](https://github.com/TarbleFR/RewindBox/actions/runs/45459585271) (commit `57b47ff2`, session DeSmuME,
  descendant de `85a5528e`), artefact 14954690166 (SHA-256 `25062cc3…394d`), porte le même `azahar_libretro`
  (`edd641bd…`, vérifié sur l'archive) et un nouveau `desmume_libretro` (`9adc00f2…`). Une livraison qui adopte
  cette collection, une fois relue par sa session, a donc aussi cet Azahar.
- **À regarder sur iPhone** :
  - Mario Kart 7 à 10× : images/s et image identique (HUD, carte de l'écran du bas, ombres, menus) ;
  - un ou deux autres jeux 3DS d'autres moteurs, pour une régression d'affichage ;
  - dans `session.log`, les lignes `[rb-perf] azahar` : `folded` proche de `fills`, `passes` par image ;
    `transfers` à 3 au lieu de 2 signale un œil droit dessiné (piste suivante si c'est le cas).
- **Limite honnête** : le gain dépend du jeu. Il vient quand le jeu efface ses tampons en entier à chaque image et
  dessine son HUD dans la même cible. 60 images/s constantes à 10× restent limitées par le GPU et la chauffe ;
  rien n'est mesuré sur l'appareil.

## Après la 832 : 3D asynchrone, image écrite dans la mémoire de l'hôte

*24 novembre 2026, session « JIT DS et ×10 ».* Retour du mainteneur sur la 832 : ×5 et ×8 fonctionnent dans
Animal Crossing ; ×10 tourne à 51 i/s (une image de 33 ms à chaque rendu 3D, `host` 2,9 ms). Détail : section 16.7 de
[desmume-arm64-jit-architecture.md](desmume-arm64-jit-architecture.md) et le README de `native/desmume`.

- **Cœur** `native/desmume` (30 fichiers, les mêmes) :
  - 3D asynchrone (`desmume_rb_3d_async`, `auto` par défaut) : un rendu lent se dessine dans un second tampon, la 2D
    montre le dernier rendu terminé ;
  - les deux écrans écrits dans la mémoire de l'hôte (`RETRO_ENVIRONMENT_GET_CURRENT_SOFTWARE_FRAMEBUFFER`) ;
  - mesures `defer` et `direct`.
- **Pont** (`LibretroMetalPresenter`, `LibretroCoreHost`, `LibretroSession`) : deux tampons Metal partagés donnés
  à DeSmuME à tour de rôle, recopiés dans la texture par le GPU dans le lot de commandes de l'affichage.
- **Collections compilées** :
  - DeSmuME seul : run [45423842137](https://github.com/TarbleFR/RewindBox/actions/runs/45423842137) (commit
    `665acae2`), artefact 14938516602, 56 384 732 octets, SHA-256 `d3e34e48…a499` ; seul `desmume_libretro` change
    (4 787 288 octets) ;
  - DeSmuME et Azahar, **celle de l'IPA 835** (le mainteneur a demandé d'y prendre Azahar) : run
    [45425936501](https://github.com/TarbleFR/RewindBox/actions/runs/45425936501) (commit `e5378e84`, qui porte
    `665acae2` et l'Azahar `a92b2264`), artefact `LibretroCores-e5378e84a7b68a56830e6aaed04883857c54bca5`, id
    14939297496, 56 385 054 octets, SHA-256 `fb281c1c5f69d422cf07b86d1b37da2a890dca846e551a4d0d7f66a9809bcb1c`,
    disponible jusqu'au 8 décembre. Entrée ajoutée à `COLLECTIONS`.
- **Ce qui change** par rapport à `f5857282` (832) : `desmume_libretro` (`741cf7b6…`, identique dans les deux
  collections) et `azahar_libretro` (`a231d4bd…`), leurs lignes de `LIBRETRO_CORES.txt` et `identity.json` ; les deux
  Beetle PSX et tous les autres fichiers sont identiques octet pour octet.
- **Vérifié sur les archives téléchargées** : empreintes, contrat d'options sur les 35 binaires, DeSmuME et Azahar
  arm64 iOS 14.0 avec l'interface JIT, correctifs `47b18a9e` (DeSmuME) et `64de19b5` (Azahar) inscrits dans
  `identity.json`, chaînes attendues de DeSmuME (`desmume_rb_3d_async`, `defer`, `direct`).

## Après la 831 : capture de la 3D sans attente complète, composition 2D en NEON

*24 novembre 2026, session « JIT DS et ×10 ».* Retour du mainteneur sur la 831 : 40 i/s au plus dans Animal
Crossing, et un `session.log` sans mesure du cœur (app fermée depuis le sélecteur). Détail : section 16.6 de
[desmume-arm64-jit-architecture.md](desmume-arm64-jit-architecture.md) et le README de `native/desmume`.

- **Cœur** `native/desmume` (30 fichiers ; `types.h`, `GPU.h`, les trois fichiers `colorspacehandler` et
  `utils/rb_sse2neon.h` en plus) :
  - une capture directe de la 3D n'attend plus toute l'image ;
  - composition 2D par les voies SSE2 de DeSmuME, écrites en NEON ;
  - fils du rastériseur sous le fil d'émulation (qualité de service) ;
  - mesures `r3d`, `bands`, `bwait`, `cap`, `cap3d`, `ecpu`, `rcpu`, `t3d`.
- **Pont** (`LibretroCoreHost`, `LibretroSession`) : les lignes `[rb-perf]` et `[rb-jit]` entrent dans
  `session.log` au fil de l'eau.
- **Collection compilée** : run [45379028317](https://github.com/TarbleFR/RewindBox/actions/runs/45379028317)
  (commit `f5857282`, fusion qui porte `468c283f`), artefact `LibretroCores-f585728289d8c25d6ac995c878f5ebc9df214dee`,
  id 14913662229, 56 382 495 octets, SHA-256 `248bd2f73db6f68cc1c0b7eb3d9ad7ae0225a53e89d3d76b2355260efa9ac6bc`,
  disponible jusqu'au 8 décembre. Entrée ajoutée à `COLLECTIONS`.
- **Ce qui change** par rapport à `6f969042` (831) : `desmume_libretro` seul (`328de8d0…`, 4 785 472 octets), sa
  ligne de `LIBRETRO_CORES.txt` et `identity.json` ; tous les autres fichiers sont identiques octet pour octet.
- **Vérifié sur l'archive téléchargée** : empreinte, contrat d'options sur les 35 binaires,
  `libretro_source_collections.verify`, DeSmuME arm64 iOS 14.0 avec `RenderFlush16Lines`, les aides de couleur SSE2
  compilées en NEON et les nouvelles mesures.
- **Livrée dans l'IPA 832** (comme la 831 : les corrections de cette session seules) : run
  [45382685674](https://github.com/TarbleFR/RewindBox/actions/runs/45382685674), IPA `4dfc2401…e5e5`
  (335 116 176 octets), reçu [docs/evidence/rewind832/delivery.json](evidence/rewind832/delivery.json).

## Après la 830 : la 3D se dessine pendant la composition 2D

*24 novembre 2026, session « JIT DS et ×10 ».* Détail : section 16.5 de
[desmume-arm64-jit-architecture.md](desmume-arm64-jit-architecture.md) et le README de `native/desmume`.

- **Cœur** `native/desmume` (24 fichiers ; `render3D.cpp`, `render3D.h`, `gfx3d.cpp` en plus) :
  - bandes dessinées de haut en bas, la 2D attend seulement ses lignes 3D ;
  - conversion de sortie NEON ;
  - mesures `engA`/`engB`/`end`/`over16`/`over33` ;
  - images identiques au bit près au cœur de la 830.
- **Collection compilée** : run [45356697338](https://github.com/TarbleFR/RewindBox/actions/runs/45356697338)
  (commit `6f969042`), artefact `LibretroCores-6f969042a533d53d41d7b79a5f98d8e4542ab63d`, id 14903781916,
  56 300 427 octets, SHA-256 `2fe56a69d52118d54ac42379ab487bc4d3999d334ebf68e6197ebd2af7ed9d02`, disponible jusqu'au
  8 décembre. Entrée ajoutée à `COLLECTIONS`.
- **Ce qui change** par rapport à `67ce2d3b` (830) : `desmume_libretro` seul (`5cd52a8e…`, 4 683 656 octets), sa
  ligne de `LIBRETRO_CORES.txt` et `identity.json` ; tous les autres fichiers sont identiques octet pour octet.
- **Vérifié sur l'archive téléchargée** : empreinte, contrat d'options sur les 35 binaires,
  `libretro_source_collections.verify`, DeSmuME arm64 iOS 14.0 avec `RenderFinishLines` et les nouvelles mesures.
- **App et pont** : inchangés depuis la 830.
- **Livrée dans l'IPA 831** (à la demande du mainteneur, la 830 avec ce seul changement) : run
  [45363528917](https://github.com/TarbleFR/RewindBox/actions/runs/45363528917), IPA `baf05722…28c9`
  (335 038 758 octets), reçu [docs/evidence/rewind831/delivery.json](evidence/rewind831/delivery.json).

## Après la 829 : suréchantillonnage 3D, mesures, envoi RGB565, cause du JIT absent

*24 novembre 2026, session « JIT DS et ×10 ».* Détail : section 16 de
[desmume-arm64-jit-architecture.md](desmume-arm64-jit-architecture.md).

- **Cœur** `native/desmume` (21 fichiers) : option `desmume_rb_3d_supersampling` (3D au double puis moyennée,
  jusqu'à ×5), lignes `[rb-perf]`, arène de 64 Mio (`jitArenaBytes`). Option désactivée : images identiques au cœur
  de la 829.
- **Collection compilée** : run [45304481777](https://github.com/TarbleFR/RewindBox/actions/runs/45304481777)
  (commit `67ce2d3b`), artefact `LibretroCores-67ce2d3b2dc6c479dbebf7da73d1f48a64f5f61b`, id 14881770592,
  56 295 241 octets, SHA-256 `9b5a949081f9138fc4d7a49b0b07d056da7f5932e18c2cb758c22c05d2027edc`, disponible jusqu'au
  8 décembre. Entrée ajoutée à `COLLECTIONS`. **C'est la collection à livrer** à la place de `ccd5f047` (id
  14872740403, celle de la 829).
- **Ce qui change** par rapport à `ccd5f047` : `desmume_libretro` seul, 4 666 752 octets (au lieu de 4 666 008),
  SHA-256 `09fd865a…01354`, et son `jitArenaBytes` dans `identity.json`. Azahar (`122f91a2…`), Beetle PSX
  (`743ea699…`) et Beetle PSX HW (`fbe2270f…`) ont les mêmes empreintes ; le constructeur annonce 232 autres
  fichiers inchangés.
- **Vérifié** : contrôles du constructeur dans le run (épingles, fichiers d'origine, Mach-O iOS 14.0, exports,
  chaînes attendues dont `desmume_rb_3d_supersampling` et `[rb-perf] desmume frames=%llu`, imports interdits) ;
  patch appliqué sur la source épinglée, identique à l'arbre mesuré sur le banc ; collection téléchargée (empreinte
  de l'archive vérifiée) et décompressée : `identity.json` (DeSmuME `jitInterface` 1, `jitArenaBytes` 67108864),
  contrat d'options sur les 35 binaires (`libretro_core_options_test.py --cores`, réglage
  `desmume_rb_3d_supersampling` compris), `libretro_source_collections.verify` (4 cœurs compilés, interface JIT et
  export d'installation), DeSmuME arm64 iOS 14.0 ; pont compilé pour iPhone (run
  [45304481770](https://github.com/TarbleFR/RewindBox/actions/runs/45304481770), job `native`).
- **Manifeste de la livraison qui l'adopte** : `components.libretro.origin` vers cet artefact ; `images.mustChange` :
  `Frameworks/desmume_libretro.framework/desmume_libretro`, `libretro_internal_bridge`, `App` ; Azahar et les deux
  Beetle PSX restent retenus.
- **App** : `libretro_internal_bridge` (images RGB565 envoyées en `B5G6R5Unorm` sans conversion ; ligne
  `load: JIT interface not installed: …` avec la cause), `App` (préparation du JIT qui rend sa cause, réglage
  « Suréchantillonnage 3D » de DeSmuME en douze langues).
- **À livrer ensemble** : le catalogue propose `desmume_rb_3d_supersampling`, que seul le nouveau cœur connaît (un
  ancien cœur l'ignore).

## Depuis la 828 : retours de l'iPhone, app seulement

Essai de la 828 par le mainteneur : DeSmuME démarre ; aucun message ne disait que le JIT était activé ; l'activation
de la surcouche passait par le menu ; Animal Crossing s'est figé à l'ouverture du menu en jeu (la même session
s'était déjà terminée sans retour au menu sur une IPA d'avant le JIT de DeSmuME).

- **Message JIT** : prêt dès la 20ᵉ image du jeu, affiché 5 s (2,5 s pour un cœur sans JIT) ; en français « JIT activé
  · DeSmuME (jit) ». Il partage le haut de l'écran avec l'état RetroAchievements du lancement : quand celui-ci est
  attendu (RetroAchievements activé ou demandé), le message JIT l'attend (5 s au plus) et s'affiche une fois ses
  notifications parties ; une notification qui arrive pendant le message JIT le remplace, il revient après. Journal :
  `jit: ready after …`, puis `jit: shown: …`.
- **Bouton de performances** à côté du bouton de menu (icône `chart.xyaxis.line`, comme Dolphin et RPCS3), vert
  quand la surcouche est affichée ; un toucher l'affiche ou la masque, réglage conservé. Placement par
  `LibretroChromeLayout` (jamais sur un écran tactile, une commande visible ou le bouton de menu ; à la place du
  bouton de menu quand l'habillage dessine son propre menu) ; vérifié sur tous les habillages par défaut par
  `test/libretro_host/frontend/chrome_layout_test.m`. Le réglage du menu reste.
- **Journal de session** pour le gel : `menu: opened after frame …`, `menu: closed, the game resumes`, et, si un
  jeu en cours ne produit plus d'image pendant 3, 10 puis 30 s, `stall: … emulation thread <état>, pc …, lr …`
  (image et symbole, ou « no image : JIT code or data »), puis `stall: frames again after …` s'il repart.
- **Images qui changent** pour la prochaine IPA : `libretro_internal_bridge`, `App`, et les deux Beetle PSX de la
  nouvelle collection ci-dessous.

## 3DS à 10× : plus aucune copie de l'image (Azahar et app)

Essai du mainteneur : 7× tient (« ça fonctionne super bien malgré quelques chutes très rares »), état thermique 1
seulement ; demande suivante : 10× à 60 images/s constantes. À 10×, une image fait 4000×4800 (76,8 Mo) ; la voie
« copie GPU » la copiait encore deux fois (image → tampon côté Vulkan, tampon → texture côté Metal), environ
18 Go/s de mémoire à 60 images/s.

- **Azahar** (`native/azahar`, `libretro_vk.{cpp,h}`) : une image de sortie par image du pool au lieu d'une seule
  partagée, choisie par l'index de synchronisation du frontend.
- **App** (`LibretroVulkanRenderer`, `LibretroSession`) : quand le cœur garde une image par index de synchronisation
  (vu pendant 8 images), son image est prêtée telle quelle au présentateur (sa `MTLTexture` par
  `vkGetMTLTextureMVK`, exporté par MoltenVK 1.2.8) : aucune copie. `wait_sync_index` attend que Metal l'ait rendue
  avant que le cœur redessine dedans. Autre format, autre famille de file ou cœur qui n'alterne pas : copie GPU comme
  avant. Journal : `vulkan: frames reach Metal directly, no copy (4000x4800)`.
- **Il faut les deux** : l'app seule avec l'Azahar de `416333ff` reste sur la copie GPU (une seule image).
- **Collection** : run [45425936501](https://github.com/TarbleFR/RewindBox/actions/runs/45425936501), artefact
  `LibretroCores-e5378e84a7b68a56830e6aaed04883857c54bca5`, id 14939297496, 56 385 054 octets, SHA-256
  `fb281c1c5f69d422cf07b86d1b37da2a890dca846e551a4d0d7f66a9809bcb1c`, entrée ajoutée à `COLLECTIONS`. Par rapport à
  `416333ff` : Azahar (images par trame) et DeSmuME (`native/desmume` à `665acae2`, autre session) changent ; les deux
  Beetle PSX sont identiques. Vérifié : empreinte, `verify` (4 cœurs compilés, interface JIT, export), contrat
  d'options sur les 35 binaires, `standard_delivery_contract_test.py` (OK, 4 ignorés).
- **Limite honnête** : sans les copies, le coût restant à 10× est le rendu 3D lui-même (100 fois les pixels
  natifs) ; 60 images/s constantes dépendent alors du GPU et de la chaleur de l'iPhone, non mesurés.

## Depuis la 828 : 3DS à 7×, image Vulkan copiée par le GPU (app seulement)

Journal du mainteneur (Mario Kart 7, Azahar, JIT actif) : 7× (images 2800×3360), état thermique 2 au bout de
75 s, résolution ramenée à 5×. Chaque image Vulkan (Azahar, Beetle PSX HW en Vulkan) était relue dans un tampon de
l'hôte puis recopiée **par le processeur**, sur le fil d'émulation, dans une texture Metal (`replaceRegion`) :
37,6 Mo par image à 7×, environ 4,5 Go/s de copies à 60 images/s, pris sur le temps d'émulation et en chaleur.

- **Correctif** (`LibretroVulkanRenderer`, `LibretroMetalPresenter`, `LibretroSession`) : la mémoire de relecture de
  chaque créneau est enveloppée dans un `MTLBuffer` (`newBufferWithBytesNoCopy`, mémoire alignée sur la page) ; le
  présentateur la copie dans sa texture **sur le GPU**, dans la commande qui dessine l'image. Le créneau est prêté
  jusqu'à la fin de cette commande (sémaphore, 2 s au plus) avant d'être réécrit ou libéré. Mémoire non enveloppable :
  copie processeur d'avant. Journal : `vulkan: frames reach Metal by a GPU copy (2800x3360)`.
- **Rien du cœur ne change** : pas de nouvelle collection pour cela ; images `libretro_internal_bridge` seulement.
- **Non mesuré sur iPhone** : gain attendu sur le fil d'émulation et la chaleur à 7× ; à vérifier avec le bouton de
  performances (`FPS`, `EMU`, `GPU`) et l'état thermique du journal.
- **Suite possible** : une seule copie GPU (image du cœur vers une image du créneau visible de Metal) au lieu de deux,
  en passant par l'API privée de MoltenVK (`VK_EXT_metal_objects` plante avec MoltenVK 1.2.8 sous ARC).

## Depuis la 828 : nouvelle collection pour les triches PS1 (feu vert du mainteneur)

- **Correctif** `416333ff` (`native/beetle-psx`, détail dans son README) : une triche qui réécrit du code déjà
  compilé par Lightrec prend effet ; Lightrec recompile ce code et reste actif, jamais de retour à l'interpréteur.
  Vérifié sous qemu (fonction compilée qui renvoie 1 ; avec la triche `80040000 0002`, 2 dès la trame suivante ;
  avant le correctif, 1 indéfiniment).
- **Collection** : run [45280386958](https://github.com/TarbleFR/RewindBox/actions/runs/45280386958), artefact
  `LibretroCores-416333ff6b623c789307b6679ca98c90a8c4c373`, id 14870941984, 56 287 018 octets, SHA-256
  `8cc3950e6c87523fe865e95ac24380260f8a36fdf25b0b2db06ed21e5bba13c5`, disponible jusqu'au 7 décembre. Entrée ajoutée
  à `COLLECTIONS`.
- **Par rapport à `66e232e0` (IPA 828)** : seuls `mednafen_psx_libretro` et `mednafen_psx_hw_libretro` changent, avec
  leur ligne de `LIBRETRO_CORES.txt` et `identity.json` ; DeSmuME, Azahar, les 31 autres cœurs, MoltenVK et les
  fichiers système sont identiques à l'octet près.
- **Vérifié dans cette session** : empreinte de l'artefact, `libretro_source_collections.verify` (4 cœurs compilés,
  interface JIT et export d'installation), contrat d'options sur les 35 binaires, `standard_delivery_contract_test.py`
  (120 tests, 4 ignorés).
- **Manifeste de la livraison qui l'adopte** : `components.libretro.origin` vers cet artefact ; `images.mustChange` :
  `Frameworks/mednafen_psx_libretro.framework/mednafen_psx_libretro`,
  `Frameworks/mednafen_psx_hw_libretro.framework/mednafen_psx_hw_libretro`, `libretro_internal_bridge`, `App` ;
  DeSmuME et Azahar restent retenus.

## Après la 828 : cœur DeSmuME corrigé, à compiler et à adopter

*23 novembre 2026, session « JIT DS et ×10 ».* Le gel d'Animal Crossing a une cause trouvée hors appareil : le JIT
de T écrivait hors de sa table (STM et PUSH vers la RAM principale) depuis l'étape 1, donc depuis la collection
`66e232e0` de la 828. Détail, reproduction et correctif : section 15 de
[desmume-arm64-jit-architecture.md](desmume-arm64-jit-architecture.md).

- **Correctif** `native/desmume/arm64-jit-abi.patch` (`139231f8…`, 20 fichiers) : écritures multi-registres par le
  crochet d'invalidation ; rendu plus rapide en haute résolution interne (effacement, tranches entrelacées, couche
  3D, conversion de sortie) ; `desmume_num_cores` à `auto` par défaut.
- **Catalogue** : inchangé. `auto` est la valeur par défaut du cœur lui-même ; RewindBox ne règle pas cette option.
- **Collection compilée** : run [45284351707](https://github.com/TarbleFR/RewindBox/actions/runs/45284351707)
  (commit `ccd5f047`), artefact `LibretroCores-ccd5f0476caa402823984be589185666d110e7a5`, id 14872740403,
  56 290 109 octets, SHA-256 `2255194bbbfc91c989aa9334bc73fe387dbb693a8d67c052cfa677baa8cee6bb`, disponible jusqu'au
  7 décembre. Entrée ajoutée à `COLLECTIONS`. **C'est la collection à livrer** à la place de `416333ff` (id
  14870941984), dont le DeSmuME est celui de la 828.
- **Ce qui change** par rapport à `416333ff` : `desmume_libretro` seul, 4 666 008 octets (au lieu de 4 665 664),
  SHA-256 `72778e09…d240ea`. Azahar, Beetle PSX et Beetle PSX HW ont les mêmes empreintes que dans le run
  45280386958 ; le constructeur annonce 232 autres fichiers inchangés.
- **Vérifié** : empreinte et taille de l'artefact (API GitHub) ; contrôles du constructeur dans le run (épingles,
  fichiers d'origine, Mach-O iOS 14.0, exports, chaînes attendues dont celle de `auto`, imports interdits) ;
  identités imprimées par le run ; origine acceptée par `libretro_source_collections.collection()`.
- **Non vérifié ici** : la collection décompressée (contrat d'options sur les 35 binaires, vérificateur de
  collection), l'hôte de stockage des artefacts n'étant pas joignable depuis cette session ; la recette de
  livraison refait ces contrôles. `test/standard_delivery_contract_test.py` n'a pas été mené à son terme
  (interrompu après dix minutes).
- **Par rapport à la 828** (collection `66e232e0`, id 14850324552), trois cœurs changent, à déclarer « doit
  changer » :
  - `Frameworks/desmume_libretro.framework/desmume_libretro` (ce correctif) ;
  - `Frameworks/mednafen_psx_libretro.framework/mednafen_psx_libretro` et
    `Frameworks/mednafen_psx_hw_libretro.framework/mednafen_psx_hw_libretro` (triches PS1, `416333ff`, mêmes
    empreintes que dans cette collection-là : `743ea699…` et `fbe2270f…`).
  Azahar (`122f91a2…`, identique à la 828), les 31 autres cœurs, MoltenVK et les fichiers système sont retenus.
- **Origine pour le manifeste** : `source` `ccd5f0476caa402823984be589185666d110e7a5`, `run` 45284351707 (essai 1,
  succès), `artifact` 14872740403, `bytes` 56290109, `sha256` ci-dessus, `expiresAt` `2026-12-07T23:08:59Z`.
  `ccd5f047` n'est alors plus différé.
- **À regarder sur iPhone** : Animal Crossing, menu en jeu ouvert puis fermé plusieurs fois ; lignes `stall:` du
  journal de session ; `[rb-jit] … engine=jit` ; surcouche de performances (`EMU`) en ×1, ×5 et ×10.
- **Non vérifié** : rien n'a tourné sur iPhone ; le lien entre l'écriture hors table et le gel au menu est cohérent,
  pas prouvé.

## La collection

- **Source.** Route source-cores de `.github/workflows/libretro-cores.yml`, commit `66e232e0`.
  - Run [45237317896](https://github.com/TarbleFR/RewindBox/actions/runs/45237317896).
  - Artefact `LibretroCores-66e232e00b980d5495c6d2d30233b13831596858` : id 14850324552, 56 286 779 octets,
    SHA-256 `b5816595ae8d02c4c493404e1803b7a73661ce4eedd0f41c9c74d00b7a65af26`, disponible jusqu'au 7 décembre.
- **Base.** La collection 14839590544 de l'IPA 827.
- **Ce qui change** par rapport à elle :
  - `desmume_libretro` : 4 665 664 octets (au lieu de 4 515 640), correctif `ce55baab…` ;
  - sa ligne dans `Libretro-Licenses/LIBRETRO_CORES.txt` et `identity.json`.
- **Identiques à l'octet près** : Azahar, Beetle PSX, Beetle PSX HW, les 31 autres cœurs, MoltenVK et les fichiers
  système.
- **Cœurs compilés par RewindBox** (`compiled: true`, `jitInterface: 1`) :

  | Cœur | Moteur | Arène | Épingle |
  | --- | --- | --- | --- |
  | `desmume` | JIT de T (`jit`), JIT RewindBox (`jit_exact`), interpréteur en cache sans JIT | 32 Mio | [native/desmume](../native/desmume/README.md) |
  | `mednafen_psx_hw` | Lightrec | 16 Mio | `native/beetle-psx` |
  | `mednafen_psx` | Lightrec | 16 Mio | `native/beetle-psx` |
  | `azahar` 2127.0-rc5 | dynarmic | 128 Mio | `native/azahar` |

- **Vérifié dans cette session.**
  - Identités : 4 cœurs `compiled`, iOS 14.0, `jitInterface: 1`.
  - `libretro_source_collections.verify` sur l'artefact décompressé : cœurs compilés conformes, export
    `_rewindbox_libretro_jit_install` présent dans chacun.
  - Chaînes de DeSmuME : `cached`, `jit_exact`, `engine=%s`, `[rb-jit] desmume installed=%d`.
  - Contrat d'options (`test/libretro_core_options_test.py --cores`) sur les 35 binaires, avec le catalogue de cette
    branche (`cached` sans JIT).
  - `test/standard_delivery_contract_test.py` : 120 tests, 4 ignorés.

## Déjà dans les sources

- **Entrée de la collection** dans `COLLECTIONS` de `.github/diagnostics/libretro_source_collections.py`.
- **Catalogue** (`lib/services/libretro_core_catalog.dart`) :
  - DeSmuME : `desmume_cpu_mode` vaut `jit` par défaut ; sans JIT, il est forcé à `cached` (l'interpréteur en
    cache, mêmes résultats que l'interpréteur, plus rapide) et `desmume_jit_block_size` à `12`. **À livrer avec
    cette collection** : le binaire de la 6cd6a89b ne connaît pas `cached`.
  - Beetle PSX et Beetle PSX HW : inchangés (`…_cpu_dynarec` à `execute`, `disabled` sans JIT).
- **Tests** : `test/libretro_core_options_test.py` et `test/libretro_core_catalog_test.dart` attendent ces valeurs.
- **App (commit `6c10d94d`)** : au lancement de chaque jeu libretro, une ligne d'état donne le mode JIT ; une
  surcouche de performances s'active depuis le menu en jeu. Voir « À regarder sur iPhone ».
- **Notices** : inchangées depuis la 827 (DeSmuME reste GPLv3 ; les fichiers `rb_*` sont GPLv2 ou ultérieure).

## À faire dans le manifeste de la livraison qui l'adopte

1. **Origine.** `components.libretro.origin` pointe vers l'artefact ci-dessus, en mode `retain-archive`.
   `jitHelper: true` est déjà acquis.
2. **Images qui changent** (`images.mustChange`) :
   - `Frameworks/desmume_libretro.framework/desmume_libretro` ;
   - `Frameworks/libretro_internal_bridge.framework/libretro_internal_bridge` (indicateur JIT, surcouche) ;
   - `Frameworks/App.framework/App` (catalogue, textes).
3. **Images retenues.** `images.retained.libretro` liste les 34 autres cœurs, Azahar et les deux Beetle compris.
4. **Entrées.** `native/desmume` a changé depuis la 827 ; c'est une entrée de recette, que l'IPA ne compile pas.
5. **Commits concurrents.** Les classer, revus ou « source seulement », comme pour la 827.

## À regarder sur iPhone

- **Indicateur JIT au lancement** (dès la 20ᵉ image du jeu, ligne d'état de 5 s), d'après ce que le cœur rapporte
  lui-même :
  - « JIT activé · DeSmuME (jit) », « JIT activé · Beetle PSX HW (lightrec) », « JIT activé · Azahar (dynarmic) » ;
  - « JIT inactif : interpréteur · … » si le cœur a choisi un interpréteur alors que le JIT était là ;
  - sans LocalDevVPN : l'avis « JIT indisponible » de toujours ;
  - cœurs officiels : « Sans JIT : interpréteur du cœur · … ».
  - Le journal de session note `jit: engine=… active=… capable=… expected=…`.
- **Surcouche de performances** (bouton à côté du bouton de menu, ou menu en jeu, « Affichage des performances »),
  en haut à gauche :
  - `FPS` et vitesse par rapport au rythme du cœur ;
  - `EMU` : temps du fil d'émulation par image ;
  - `GPU`, `RAM` (empreinte de l'app), `BAT`, `JIT` (moteur rapporté).
- **Journaux `[rb-jit]` de DeSmuME.**
  - Au démarrage : `installed=1 … wanted=1 jit=1 cached=0 engine=jit`.
  - Toutes les 30 s : `blocks`, `used`, `flushes`, `failures`. Si les rembobinages (`flushes`) reviennent souvent,
    monter `jitArenaBytes`.
- **DeSmuME sans JIT** : `engine=cached` ; à comparer avec l'interpréteur de la 827 (même résultat attendu, plus
  rapide).
- **`jit_exact`** (réglage du cœur) : résultat identique à l'interpréteur, pour un jeu qui se comporterait mal avec
  `jit` ; plus lent quand les deux CPU tournent ensemble.
- **Jeux DS de référence** : section 7.5 de [desmume-arm64-jit-architecture.md](desmume-arm64-jit-architecture.md).
- **Non vérifié.** Rien n'a encore tourné sur iPhone. La vérification hors appareil est décrite dans
  `native/desmume/README.md` (sections 13 et 14 du document d'architecture).
