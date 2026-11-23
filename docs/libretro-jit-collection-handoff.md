# Passation : collection libretro avec DeSmuME (JIT, étapes 1 à 4), Beetle PSX (Lightrec) et Azahar 2127.0-rc5

*23 novembre 2026 — branche `Claude`. Note pour la session qui construit les IPA : consigne du mainteneur, « pas
d'ipa c'est une autre session qui la fera ». Cette session n'a lancé aucune livraison.*

*La collection précédente, `LibretroCores-6cd6a89b…` (id 14839590544, étape 0 de DeSmuME), est livrée dans
l'IPA 827. Celle-ci la remplace ; elle est livrée dans l'IPA 828.*

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
