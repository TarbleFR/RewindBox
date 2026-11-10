# RPCS3 Core 921 — libération des textures périmées inactives (mémoire de Black Ops II sans plateau)

Suite de la mission du 10 novembre (réduire le travail CPU et la mémoire de Black Ops II par des corrections de
production vérifiées). Core 921 = Core 920 + une correction. **Aucune mesure iPhone n'a encore été faite avec ce Core** :
les chiffres de la section 4 viennent d'un banc hôte sur le vrai cache de textures, pas de l'appareil.

## 1. Données d'entrée

- **Export de l'IPA 722, Black Ops II sur la build 721 (Core 919)**, PID 47085, session 2 = `t6mp_ps3f.self`
  (multijoueur). Réglages : réservations exactes, résolution 100 %, limite d'images Auto, 6 SPURS, PPU et SPU LLVM,
  recompilateur de shaders Legacy, `levers627=010111011111111112000`. Les fenêtres 4 à 32 du fichier de performances sont
  dans la génération `.1`, absente de l'export : seuls la chronologie, les causes et la fenêtre 33 se lisent.
- En jeu : 30-38 images/s (médiane 31,2), p95 35-57 ms, pauses de 0,26 à 1,98 s (fenêtres 19, 21, 23, 32) qui sont des
  premières compilations de pipelines (bibliothèque de fragment 0,37-0,99 s ; aucune empreinte coûteuse ne revient d'une
  session à l'autre sur les 40 sessions de Black Ops II lues : le cache de pipelines fonctionne).
- **Mémoire** : empreinte 2,23 → 3,44 Gio en 2 min 30 de jeu. Sur toutes les sessions de Black Ops II des builds 620 à
  721, l'empreinte monte de 5 à 20 Mio/s sans plateau. Session 5 de la build 666 (la plus longue, 4,4 min de jeu) :

| Fenêtre | Empreinte | Compressée | Textures vivantes (`texture_mib`) | Réserve de textures (JITMEM) | Blocs VMA |
|---|---|---|---|---|---|
| 18 (entrée en jeu) | 2 327 Mio | 378 Mio | 21 Mio | 74 Mio | 544 Mio |
| 45 | 3 309 Mio | 851 Mio | 288 Mio | 347 Mio | 1 184 Mio |
| 71 | 3 564 Mio | 1 025 Mio | 527 Mio | 568 Mio | 1 376 Mio |

  La réserve de textures croît d'environ 2 Mio/s avec 200 à 450 nouveaux téléversements par fenêtre de 5 s, et ne
  redescend jamais ; les paliers de 64 Mio de l'empreinte sont des blocs VMA. `texture_trim_sections=0` dans tous les
  journaux : la purge ne libère rien. 527 Mio de sections dépasse toute la mémoire de la PS3 (512 Mo) : la plupart
  recouvrent des octets qui contiennent maintenant autre chose.
- Coût CPU associé : le temps de recherche de texture du thread RSX passe de 2,4-3,9 µs à 6-8 µs par recherche au fil de
  ces sessions (TEXMEMO660 `lookup_ms` / `lookups`) ; ce banc ne prétend pas en mesurer la part due aux sections mortes.

## 2. Défaut (code)

- Sur iOS, toute texture du CPU est confirmée par une empreinte de ses octets invités, jamais par la protection des pages
  (`rpcs3/Emu/RSX/Common/texture_cache_protection_policy.h`). Une texture dont le jeu a réutilisé la mémoire n'est
  trouvée périmée que si une recherche la redemande ; sinon elle garde son image et sa section jusqu'à la fin de la partie.
- La purge d'origine des sections hachées (`ranged_storage::trim_sections`) ne visite que les blocs de 1 Mio qui ont plus
  de 256 sections verrouillées : sur PC seules les textures de moins de 4 Kio sont hachées. Black Ops II n'atteint jamais
  ce seuil.
- La résidence du Core 573 (God of War III seulement) ne libère qu'au-dessus de 768 Mio de textures vivantes.

## 3. Correction (`REWINDBOX_STALE_TEXTURE_SWEEP_921`)

Une fois par image présentée, après la passe de résidence et avant la fin d'image du cache de textures
(`rpcs3/Emu/RSX/VK/VKPresent.cpp`), une passe bornée (`rsx::texture_cache::release_stale_idle_sections`,
`ios/IOSStaleTextureSweep.h`) :

- parcourt les blocs du cache depuis un curseur (bloc, emplacement) et reprend où la passe précédente s'est arrêtée ;
- n'examine que les textures du CPU validées par empreinte (lectures de shader, sources de blit), non sales, inutilisées
  depuis 64 images, non liées aux registres de texture actuels, et que la passe n'a pas trouvées intactes dans les 64
  dernières images ;
- recalcule leur empreinte avec la fonction et la comparaison des recherches (`buffered_section::sync_unpredicted` : sans
  les tables de pré-validation, qui prédisent les recherches de l'image suivante) et libère exactement celles dont les
  octets ne correspondent plus, comme leur prochaine recherche l'aurait fait (`sync_protection_swept`) ; une texture
  intacte est gardée, aussi longtemps qu'elle reste inutilisée ;
- s'arrête après 4 Mio hachés (0,25-0,31 ms au débit de 12,8-16,8 Gio/s mesuré sur l'appareil, builds 694, 718 et 721)
  ou 2 048 sections regardées ;
- purge les sections libérées ; les descripteurs d'échantillonneurs de ces deux types sont recherchés de nouveau avant leur
  prochain usage, comme après la passe de résidence.

Réglage **Stale texture release** (Experimental → FPS Experiments, `experimental.stale_texture_sweep`, Automatic = tous
les titres, pris en compte au démarrage suivant ; Disabled = comportement du Core 920). Ligne de politique `Resolved title
policy 921`, ligne par fenêtre `COREPROF TEXSWEEP921` (passes, sections regardées et examinées, libérées, Mio invités et
hôtes, révolutions, temps du thread RSX). L'analyseur d'exports (`tools/rpcs3/capture_analyzer.py`) ajoute les colonnes
`tex_mib`, `tex_misses`, `sweep_released`, `sweep_host_mib` et `sweep_ms`.

## 4. Contrôle avant/après (hôte)

`test/rpcs3_stale_texture_sweep921_test.py` compile le vrai `rsx::texture_cache` (recherches, sections,
`buffered_section::sync` et `sync_unpredicted`, `trim_sections`, le mémo de recherche) du harnais de
`test/rpcs3_texture_lookup_memo660_harness.py`, deux fois : l'arbre du Core 920 (témoin ; par défaut la source sans
l'incrément du Core 921) et l'arbre du Core 921. Chaque image se termine comme `VKGSRender::flip`. g++ ASan+UBSan et
clang ; mémo en `verify_all` (Black Ops II) et `active`.

| Flux façon Black Ops II (2 400 images, réserve de 24 Mio, 3 tours) | Core 920 | Core 921 |
|---|---|---|
| Sections vivantes à la fin | 2 408 | 525 |
| Octets vivants à l'image 1 200 → 2 400 | 56,8 → 113,0 Mio | 24,8 → 24,7 Mio |
| Sections périmées inactives à la fin | 1 930 | 47 |
| Téléversements | 2 408 | 2 408 |
| Emplacements servant des octets périmés | 0 | 0 |
| Sections libérées par la passe | — | 1 883 |
| Octets hachés par la passe | — | 339 Kio par image en moyenne, 464 Kio au plus |

Invariants, dans chaque scénario : aucune section libérée dont les octets correspondaient, aucune liée, aucune utilisée
dans les 64 dernières images, aucun appel aux tables de pré-validation, au plus 4 Mio + une section hachés et 2 048
sections regardées par passe. 32 textures inactives intactes pendant 400 images : aucune libérée, aucun téléversement à
leur retour, les mêmes images. 600 sections périmées : chacune examinée une fois, toutes libérées, 64 par passe. Une
texture écrasée puis rétablie : libérée pendant qu'elle diffère, puis un téléversement à son retour (le Core 920 la
réutilise : c'est le coût de la libération anticipée, celui qu'une faute d'écriture aurait sur PC). Le réglage coupé
reproduit le Core 920 image pour image. Contre-tests : un arbre qui libère sur une correspondance (2 333 sections valides
libérées), qui ignore les textures liées ou le délai d'inactivité échoue. Relecture indépendante du code (itération pendant
la libération, durée de vie des images, mémo, verrou, types de sections) : aucun défaut.

## 5. Bilan

- **Coût supprimé** : la mémoire des sections de textures périmées et de leurs images, que rien ne libérait. Sur le banc,
  113 → 24,7 Mio et une croissance arrêtée ; sur l'appareil, la part périmée de la réserve de Black Ops II (568 Mio à
  4,4 min sur la build 666, toujours en hausse), plus les blocs VMA qu'elle forçait et les pages mortes que le noyau
  compressait (1,03 Gio compressés). Le gain iPhone n'est pas encore mesuré.
- **Coût restant ou déplacé** : du hachage sur le thread RSX, au plus 4 Mio par image (≈ 0,3 ms), 339 Kio en moyenne sur
  le banc (≈ 0,02 ms au débit de l'appareil) ; une texture intacte inactive est rehachée une fois toutes les 64 images ;
  un téléversement quand les octets d'une texture libérée reviennent.
- **Chemin critique** : l'image de Black Ops II suit le PPU (thread RSX 0,52-0,59 cœur, GPU 30-36 %) ; la passe s'exécute
  sur le thread RSX en fin d'image. Moins de sections dans les blocs allège aussi les recherches, sans que le banc le
  chiffre.
- **Mémoire** : la réserve de textures redevient bornée par ce que la mémoire invitée contient ; à lire sur l'appareil.
- **Risques et vérification** : libération anticipée d'une texture dont les octets reviennent (un téléversement) ; aucune
  texture périmée servie, aucune liée examinée, descripteurs recherchés de nouveau ; tests hôte, contre-tests et relecture
  ci-dessus ; la compilation iOS et le Core sont vérifiés par la recette standard.

## 6. Inchangé

Aucune recherche, téléversement, empreinte ou comparaison des recherches, aucun verrou ni attente, aucune réservation,
aucun réglage de résolution, de précision, de limite d'images, de nombre ou de priorité de SPU ou d'option LLVM. Aucun
fichier d'entrée des identités de code généré PPU/SPU n'est modifié : les caches du joueur restent valides. ABI 30, 92
exports.

## 7. Identités

Moteur `8e8f90a` (base Core 920 `4c4961b`), incrément `build-utils/rpcs3/core921-from-920.patch` (12 fichiers, que des
ajouts), correctif canonique `ea8bb09d`, delta `core921-delta.patch` `039777d7`. Compilation, empreintes et état sur
l'appareil dans `build-utils/rpcs3/core-pin.json` et `docs/AI_TASK_BOARD.md`.

## 8. Protocole iPhone (la question que l'appareil doit trancher)

Black Ops II multijoueur, mêmes réglages et même partie que l'export de l'IPA 722, réglage Stale texture release laissé sur
Automatic. Au moins 20 minutes de jeu depuis l'entrée en partie, puis export aussitôt avec les fichiers `.1`.

- **La croissance s'arrête-t-elle ?** `TEXCACHE621 texture_mib` et JITMEM `gpu_textures_requested` doivent se stabiliser
  après les premières minutes au lieu de monter d'environ 2 Mio/s ; `MEMPROF527` (empreinte, compressée) doit cesser ses
  paliers de 64 Mio ; `TEXSWEEP921 released` > 0.
- **Ce que cela coûte** : `TEXSWEEP921 sweep_ms` par fenêtre (attendu : quelques ms par 5 s), images/s et p95 comparés à
  la build 721.
- Ce qui réfuterait la correction : `texture_mib` toujours linéaire avec `released` proche de 0 (alors la croissance ne
  vient pas de sections périmées et le résultat est rapporté tel quel).
