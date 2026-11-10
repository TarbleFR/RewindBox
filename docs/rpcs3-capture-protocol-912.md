# RPCS3 — préparation des essais iPhone après Core 911 (référence Core 914, témoin AC1 Core 915)

Document de préparation : moyens de capture, disponibilité des observations, outil d'analyse et protocole. Aucune
mesure iPhone n'a été faite avec ces binaires ; aucune IPA n'a été produite dans cette mission. Les journaux bruts
restent hors de Git.

## 1. Binaires

| Rôle | Core | Identité | Différence |
|---|---|---|---|
| Référence (à épingler) | 914 | run `42736141716` (source `ce12d397`)  artifact 13728211847  dylib `14e6f691` (80 919 144 B)  fingerprint `df98e75d`, épinglé | Core 912 + corrections de collecte du 10 novembre (un événement n'entre que dans la capture où il a été préparé). Mémo de textures à 16 voies. |
| Témoin de comparaison AC1 (jamais épinglé) | 915 | run `42737889347` (source `b5f70a2a`), artifact 13728955880, dylib `b4ece6df` (80 919 144 B), fingerprint `b8759812`, jamais épinglé ; [identité](evidence/rpcs3-core915-ac1-ways4-witness/identity.json) | Core 914 avec une seule constante changée : `ways = 4` dans `rpcs3/ios/IOSTextureLookupMemo.h`. |
| Remplacés, ni épinglés ni livrés | 912 / 913 | runs `42728150899` / `42729856621` | Première paire référence/témoin, avant la correction de la collecte. Ne jamais comparer 913 à 914. |

Un témoin n'est comparable qu'à la référence dont il est issu : 915 avec 914 seulement.

**Core 916** (correctifs tirés des journaux du build 718 : [rpcs3-core916-build718.md](rpcs3-core916-build718.md))
change trois points de ce protocole :

- sur le build 718 (Core 914), **aucune capture ne pouvait être demandée** : `CONFIG_LAYERS levers627=` exportait
  18 chiffres sur 21 et l'hôte lit les chiffres 20 et 21 avant d'envoyer la demande. Les parcours B de la section 6
  ne sont exécutables qu'à partir du Core 916 ;
- le rapport demande lui-même un profil de régions PPU, une fois par démarrage, quand le thread PPU le plus chargé
  dépasse 0,85 cœur deux fenêtres de suite (`COREPROF AUTOPPU916`, puis `PPUPROF912 … trigger=auto_ppu_bound`) : il
  ne dépend ni de la page Tests ni du menu, et compte dans la limite de 3 profils par démarrage ;
- une fenêtre « jeu arrêté » après la première ne contient plus que `FRAMEPROF527` et `COREPROF IDLE916` ;
  l'analyseur l'affiche `stopped(compact)` et ses colonnes `compact` (ni absentes ni perdues). Le dump de blocage
  gagne les lignes `lwcond … queue=kernel` et `ppu_stack`.

Les deux exposent la variante dans les exports : `COREPROF TEXMEMO660 … ways=16` ou `ways=4`. Une IPA ne contient
qu'un Core : la comparaison AC1 demande deux IPA, identiques par ailleurs (même hôte, même MeloNX).

## 2. Où arrivent les lignes

Vérifié dans `Rpcs3InternalBridgePlugin.mm` et `Rpcs3Diagnostics.mm` : toute ligne contenant `COREPROF `,
`RANGELOCKPROF `, `SPUPROF `, `JITPROF `, `FREEZE_DUMP ` ou `CONFIG_LAYERS ` passe hors du filtre de niveau et du
budget de 128 lignes par seconde. Elles sont limitées par la file d'écriture (2 048 lignes + 512 réservées,
2 Mio) : une capture PUTLLC complète pèse au plus environ 700 lignes et 0,6 Mo.

| Fichier exporté | Contenu utile ici |
|---|---|
| `RPCS3-performance.log` (+ `.1.log`, 2 Mo chacun) | fenêtres `COREPROF …`, `RANGELOCKPROF`, `SPUPROF`, `JITPROF`, captures `PUTLLCTRACE912` et `PPUPROF912`, épisodes et dumps de blocage |
| `RPCS3-causes.log` (+ `.1.log`) | `FRAMEPROF527`, `GPUTIME621`, `RSX_ACQUIRE`, dumps de blocage, `CONFIG_LAYERS` (titre, réglages, `levers627`) |
| `RPCS3-diagnostic.log` (+ `.1.log`) | journal complet, `HOST_STATE` (menu ouvert/fermé), `CAPTURE_REQUEST`, `LOG_BACKLOG`, `LOG_ROTATION` |
| `RPCS3-milestones.log`, `RPCS3-timeline.log`, `RPCS3-session.txt` | jalons de démarrage, dumps de blocage, synthèse de session |

Les lignes « Resolved title policy » ne sont pas exportées : l'état d'un levier se lit dans `levers627=` de
`CONFIG_LAYERS part=rsx` (un chiffre par levier : 1 = actif, +2 = valeur explicite) et dans les champs des sondes.
Le profil « Profil de mesure allégé » supprime les lignes de fenêtre et les dumps de blocage : le laisser
désactivé pour tous les essais ci-dessous.

## 3. Matrice de disponibilité

États : **A** déjà observable et vérifié dans Core 911 (ligne présente dans des exports iPhone existants, ou
émetteur et route d'export vérifiés dans le source) ; **B** instrumentation ajoutée dans Core 912 et corrigée dans Core 914 ; **C** observation
physique nécessaire après préparation ; **D** limite technique identifiée.

| Question | Observation nécessaire | Champs réellement émis | Producteur | Activation | Core min. | État |
|---|---|---|---|---|---|---|
| BO2 : effet de l'attente SPU | temps SPU, PUTLLC, FPS avec et sans l'attente | `SPUWAIT551` `getllar_sleep=n:ms` `putllc_ok` `putllc_fail` `putllc_heavy` ; `COREPROF frames=` `spu_cores` `ppu_cores` `top=` ; `FRAMEPROF527` `wall_guest_fps` `p95_ms` | `SPUThread.cpp` (`spu_wait::add`), `RPCS3IOSPerformance.cpp` | par défaut ; A/B par la ligne « SPU : attendre au lieu de sonder » (chiffre 4) | 911 (chemin exact) | A, puis C |
| BO2 : phases du verrou d'écriture | acquisition, drapeau, parcage, tenue | `RANGELOCKPROF` `wl_putllc=n:acq_ms:hold_ms` `wl_putllc_phases` `wl_putllc_flagged` `wl_putllc_slow_parks` `wl_putllc_park_max_us` `wl_putllc_avoided` | `Emu/Memory/vm.cpp`, `ios/IOSWriterLockPhases.h`, `RPCS3IOSPerformance.cpp` | par défaut | 908 | A, puis C |
| BO2 : contenu des PUTLLC lourds | par thread SPU : suite ordonnée, PC, ligne, portions changées, résultat, valeurs lue/demandée/trouvée | `PUTLLCTRACE912 part=events thread= first= last= of= after_full= t0_us= ev=dt_us:pc:addr:résultat:lanes:lane:rtime:snapshot:written:observed` | `ios/IOSCapture912.h`, `SPUThread.cpp do_putllc`, `RPCS3IOSFreezeDump.cpp` | ligne « Capture : PUTLLC lourds » (chiffre 20) puis fermeture du menu en jeu | 912 | B, puis C |
| BO2 : attente du thread principal | part d'attente et appel système en cours | `PPUPROF912 part=thread … running= waiting= wait_calls=` ; en blocage `FREEZE_DUMP ppu … func= wait_s=` et `FREEZE_DUMP sema … ids=` (sémaphores du thread principal en premier) | `RPCS3IOSFreezeDump.cpp` | ligne « Capture : régions PPU » (chiffre 21) puis fermeture du menu ; dump automatique en blocage | 912 | B, puis C |
| GOW3 : CPU du thread PPU principal | répartition par région de code et attente | `PPUPROF912 part=thread … running= waiting= same_pc= distinct= overflow= top=région:échantillons:premier_pc` ; `COREPROF frames=` `ppu_cores` `top=` | idem | idem | 912 | B, puis C ; D pour le PC exact (§ 8) |
| GOW3 / Black Flag : blocages | premier maillon inconnu : objet, threads en attente, durées, PC, FIFO | `FREEZE_DUMP ppu` (id, état, pc, func, wait_s), `ppu_poller`, `lwcond`, `sema` (32 collectés, 12 listés, ceux du thread principal d'abord), `rsx … get= put= fifo_pos= last_cmd= args_left= in_begin_end=`, `spu`, `waits` ; `FREEZE_EPISODE` | `RPCS3IOSFreezeDump.cpp`, `RPCS3IOSPerformance.cpp` | automatique (profil allégé désactivé) | 909 pour `ppu_poller`/`lwcond` ; 912 pour FIFO et ordre des sémaphores | B, puis C ; D : l'auteur d'un signal n'est pas enregistré |
| GOW3 : horizon PUT et pré-hachage | époques déclenchées par PUT, différées, corrigées ; résultats du worker utilisés | `EPOCH909` `put` `put_horizon` `put_deferred` `put_patched` ; `OPT583` `lookahead` `worker_used` ; `OPT581` `hits` `misses` `worker_hashes` `worker_ms` | `RSXFIFO.cpp`, `ios/IOSTextureValidationProfile.h`, `texture_cache.cpp`, `ios/IOSTexturePrehash.h` | par défaut ; A/B par « Revérification des textures à l'horizon PUT » (chiffre 19) | 910 (`worker_used` 911, ligne A/B 912) | A, puis C |
| AC1 : 16 voies ou 4 | temps d'image et compteurs du mémo, même scène | `TEXMEMO660` `ways` `lookups` `hits` `miss_empty` `miss_evicted` `lookup_ms` ; `FRAMEPROF527` ; `GPUTIME621 busy_share` | `IOSTextureLookupMemo.h`, `RPCS3IOSPerformance.cpp` | constante de compilation : deux Cores | 912 et 913 | B (témoin construit), puis C |
| AC1 : fermetures de passes | fins de passe par cause et par destination | `RPASS652` `begins` `same_target` `ended_empty` `same_target_after_empty` `sites=` ; `RPASS655` `ended_*` `to_color` `to_depth` `to_transfer_dst` `to_transfer_src` `to_general` | `ios/IOSRenderPassCensus.h` (appelé par `VKRenderPass.cpp`, `VKDraw.cpp`, `VKGSRender.cpp`), `RPCS3IOSPerformance.cpp` | par défaut | 910 | A, puis C |

## 4. Les deux captures (Core 912, corrigées dans Core 914)

Désactivées par défaut. Une ligne de la page Tests du menu en jeu les active **pour le titre** ; le jeu redémarre
(comme pour toute ligne de test). Ensuite, **chaque fermeture du menu en jeu** démarre une capture : le menu ne
met pas l'émulation en pause, donc l'hôte envoie au Core une demande explicite (`CAPTURE_REQUEST` dans le journal)
et le Core répond par `part=armed trigger=menu_closed` ou par `part=refused reason=…`. Aucune pause, aucun réglage
modifié par la demande.

| | PUTLLC lourds (`PUTLLCTRACE912`) | Régions PPU (`PPUPROF912`) |
|---|---|---|
| Ce qui est enregistré | par thread SPU, dans son ordre, chaque PUTLLC « exact » qui change des données, jusqu'à 512 | toutes les ~1 ms, PC et état d'attente des threads PPU suivis (le principal d'abord, 4 au plus) |
| Arrêt automatique | tous les tampons pleins, 3 s, ou jeu arrêté | 5 000 échantillons (5 s) ou jeu arrêté |
| Par démarrage | 2 captures | 3 captures |
| Mémoire | 8 threads × 512 × 80 octets = 327 680 octets, alloués une fois | 4 histogrammes de 512 régions |
| Coût capture inactive | une lecture atomique par PUTLLC exact modifiant des données | aucun |
| Coût capture active | une copie et deux comparaisons de 128 octets, un horodatage, une entrée de 80 octets ; ni verrou, ni allocation, ni texte | un thread qui lit deux champs par thread PPU chaque milliseconde |
| Export | par le thread de diagnostic, une fois les écrivains sortis | idem |

Lecture d'un événement PUTLLC : `résultat` 1 écrit, 2 temps de réservation déjà changé, 3 réservation prise ou
déplacée, 4 pré-contrôle (la ligne différait avant le verrou), 5 comparaison sous verrou, 6 échange 16 octets
échoué sous verrou. `snapshot` = la portion lue au GETLLAR, `written` = la portion demandée, `observed` = `-` mémoire
non lue, `=` égale au snapshot, sinon 16 octets de la copie, le masque des portions différentes et la portion
montrée. Rien n'est relu après coup. `t0_us` place le premier événement de chaque ligne par rapport au début de la
capture et `dt_us` le suivant par rapport au précédent : tous les threads partagent une base de temps (chaque
événement est horodaté à son enregistrement, après la décision : la base commune rapproche les threads, elle ne
garantit pas un ordre global entre deux événements voisins de threads différents). Le périmètre n'est filtré par
aucune adresse : les lignes des anciens dumps (0x2e20880, 0x2e20c00…) ne sont que des repères, la capture montre
celles de la session. « Consécutif » signifie : PUTLLC exacts modifiant des données d'un même
thread, sans trou, jusqu'à son tampon plein ; `after_full` compte ceux qui ont suivi sans être enregistrés ; les
threads au-delà de huit sont comptés dans `threads_dropped`.

### Identité d'une capture et parcours du déclenchement (Core 914)

- Chaque capture a une génération (`part=begin … generation= stale_rejected=`). Un événement prend la génération de la
  capture en cours quand sa préparation commence ; il n'est enregistré que si cette capture collecte encore. Un thread
  retenu entre son PUTLLC et l'enregistrement, pendant que la capture est exportée et qu'une autre démarre, voit son
  événement refusé et compté dans `stale_rejected`, jamais rangé dans la nouvelle capture. Un horodatage antérieur au
  début de la capture s'écrit `t0_us=before_start`, pas 0.
- Fermeture du menu → l'hôte envoie **une** demande par capture activée (passage d'ouvert à fermé seulement), avec la
  clé exacte `experimental.heavy_putllc_trace` ou `experimental.ppu_region_profile` et la valeur `Enabled`, et l'inscrit
  au journal (`CAPTURE_REQUEST … status=`). Sans capture activée au démarrage, rien n'est envoyé.
- Le Core répond `part=armed trigger=menu_closed` ou `part=refused reason=limit_per_boot` /
  `previous_capture_not_exported` / `thread_list_unavailable`. Les limites (2 et 3 par démarrage) repartent à chaque
  démarrage de jeu ; une demande laissée par le jeu précédent est abandonnée.

## 5. Parcours A — mesurer les correctifs livrés (captures désactivées)

Binaire : Core 914 de référence. Réglages : ceux du profil du jeu, « Profil de mesure allégé » désactivé, les deux
lignes « Capture : … » sur le profil par défaut. Une fenêtre de rapport dure 5 s.

Limite d'images, par jeu (ne rien forcer pour simplifier une mesure) :

- **AC1** : conserver son plafond natif de 30 FPS.
- **BO2** : ne pas imposer de plafond à 30 FPS ; les essais cherchent justement un gain au-delà. Garder le réglage du
  profil.
- **GOW3** : conserver ses réglages effectifs de référence.

Le réglage réellement appliqué est exporté à chaque démarrage (`CONFIG_LAYERS … frame_limit=`, `Auto` pour les trois
jeux dans les exports 694) et l'analyseur l'affiche sur la ligne `config:` de chaque session ; une comparaison liste
les réglages qui diffèrent. Le relever pour chaque essai plutôt que de le supposer.

| Essai | Question | Ligne à basculer | Scène | Durée minimale | Fichiers |
|---|---|---|---|---|---|
| A1 | BO2 : l'attente SPU réduit-elle le temps SPU sans baisser les FPS ? | « SPU : attendre au lieu de sonder » activé / désactivé | menus 60 s, puis la scène lente (fenêtre 11 de 694) | 60 s par phase | performance, causes, diagnostic |
| A2 | BO2 : parcage ou capacité CPU ? | aucune | même passage que A1 | 60 s | idem |
| A3 | GOW3 : l'horizon PUT et le pré-hachage gagnent-ils ? | « Revérification des textures à l'horizon PUT » activé / désactivé | scène de la sauvegarde | 60 s | idem |
| A4 | AC1 : quelles fins de passe dominent ? | aucune | scène à 21 FPS (fenêtre 41 de 694) | 60 s | idem |
| A5 | GOW3 / Black Flag : premier maillon du blocage | aucune | jusqu'au blocage, puis attendre 40 s | un blocage | performance, causes, milestones, diagnostic |

Ordre A/B : un premier lancement d'échauffement non mesuré (caches de shaders et de code compilés), puis
A, B, B, A sur la même scène ; appareil branché, luminosité fixe, même état thermique au départ (noter l'état
affiché). Chaque bascule redémarre le jeu : rejoindre la scène par le même parcours ou la même sauvegarde.

## 6. Parcours B — investigation ciblée (capture explicite)

| Essai | Question | Activation | Déclenchement | Fin | Fichiers |
|---|---|---|---|---|---|
| B1 | BO2 : que contiennent les PUTLLC lourds ? | « Capture : PUTLLC lourds » activé | dans la scène lente, ouvrir puis fermer le menu en jeu | attendre 10 s après la fermeture | performance (+ `.1`), diagnostic |
| B2 | GOW3 : où le thread PPU principal passe-t-il son temps ? | « Capture : régions PPU » activé | dans la scène lente, ouvrir puis fermer le menu | attendre 10 s | idem |
| B3 | BO2 : le thread principal attend-il, et quoi ? | « Capture : régions PPU » activé | idem dans la scène lente | attendre 10 s | idem |

Il n'y a pas d'indicateur à l'écran : la règle des 10 s couvre la capture (3 s ou 5 s) et son export. Une
deuxième capture du même démarrage sert de contraste (par exemple B1 une fois dans les menus à 60 FPS, une fois
dans la scène lente). Exporter avant de relancer : les fichiers tournent à 2 Mo.

## 7. Comparaison AC1 16 voies / 4 voies

Deux IPA (référence 914, témoin 915) qui ne diffèrent que par le Core ; la livraison commune ne contient que la
référence. Même iPhone, même dump, même sauvegarde ou même parcours jusqu'à la scène à 21 FPS, même résolution et
mêmes réglages, plafond natif de 30 FPS d'AC1 conservé, caches chauds des deux côtés (un lancement d'échauffement
par IPA), même état thermique. Ordre 914, 915, 915, 914. Mesurer 60 s dans la scène. Compteurs :
`FRAMEPROF527` (`wall_guest_fps`, `p95_ms`), `GPUTIME621 busy_share`, `TEXMEMO660` (`lookups`, `hits`,
`miss_empty`, `miss_evicted`, `lookup_ms`). `miss_evicted` lit un historique borné des 16 dernières évictions d'un
emplacement : c'est une borne inférieure des échecs dus à la capacité, pas leur décompte.

## 8. Outil d'analyse

```bash
python3 tools/rpcs3/capture_analyzer.py DOSSIER_DES_EXPORTS --title BLES01717
```

```bash
python3 tools/rpcs3/capture_analyzer.py DOSSIER --label PID:SESSION:12-24=scene --label PID2:SESSION2:10-22=scene --compare PID:SESSION PID2:SESSION2
```

Il regroupe par titre, build de l'application, PID, **processus** réellement distinct, session de démarrage et
fenêtre. La paire (PID, session) n'est pas une identité : dans un processus la session compte les démarrages et
`CONFIG_LAYERS` nomme le titre de la session qui commence ensuite, mais un PID peut être réutilisé. Un autre processus
est reconnu à un changement de build, à une fenêtre répétée ou à des numéros de fenêtre qui recommencent ; les entrées
sont alors nommées `PID:SESSION#N`, et celle qui n'est séparée que par ses fenêtres, sans `CONFIG_LAYERS`, garde le
titre `unknown` et n'est jamais comparée. Une session vue seulement à partir d'une fenêtre tardive a un titre marqué
incertain et n'est pas comparée non plus. Une ligne qui porte `session=` ne rejoint qu'une fenêtre de cette session ;
sans fenêtre, elle est gardée comme ligne non rattachée. Il garde le fichier et la ligne d'origine de chaque valeur ; écrit `absent` pour une ligne
manquante, `absent_or_lost` quand le journal du processus annonce des pertes, et `inactive` pour une sonde qui se
déclare désactivée, jamais 0 ; signale les pertes annoncées par le
journal (`LOG_ROTATION`, `LOG_BACKLOG`, `LOG_BUDGET`) et les captures incomplètes (lignes reçues / déclarées, trous
de séquence) ; refuse une comparaison entre deux titres ; limite une comparaison à la scène étiquetée des deux
côtés et affiche les réglages qui diffèrent et la variante du mémo. Les temps cumulés sur plusieurs threads
(`wl_putllc`) sont présentés comme du temps de thread, pas comme du temps récupérable par image. Les phases
viennent du journal (`phase=`, épisodes de blocage) ou d'une étiquette, jamais du nombre d'images par seconde.

Vérifications : `test/rpcs3_capture_analyzer_test.py` (journaux synthétiques, marqués comme tels) et les exports
iPhone existants (694 : AC1 PID 41776 fenêtre 41 retrouvée avec sa provenance).

## 9. Limites identifiées

- **PC du thread PPU.** Le recompilateur LLVM n'écrit `cia` qu'aux transferts indirects, appels système et
  instructions de réservation. `PPUPROF912` attribue donc un échantillon à la région du dernier de ces points
  (`pc_scope=last_indirect_transfer_syscall_or_reservation`), par régions de 256 octets : il sépare le travail de
  l'attente et désigne des zones de code, pas des instructions. `same_pc`, `distinct` et `overflow` mesurent la
  finesse obtenue. Si la répartition reste trop grossière, l'alternative est un échantillonnage du PC hôte du thread
  avec la table des fonctions compilées ; elle n'est pas dans Core 912.
- **Auteur d'un signal.** Le dump de blocage liste objets, threads en attente et durées ; le thread qui aurait dû
  signaler n'est enregistré nulle part : il reste une attribution, pas une observation.
- **PUTLLC.** `written` est lu dans la mémoire locale du SPU au moment de l'enregistrement ; `observed` du
  pré-contrôle est une copie prise sans verrou (c'est elle que le contrôle compare pendant une capture). Des valeurs
  qui alternent ne prouvent pas qu'une attente serait sûre.
- **Validation hôte et coût sur appareil.** Les collecteurs sont exécutés sur l'en-tête réel (séquences, capacité,
  publication concurrente à dix threads, arrêt et reprise, export relu, histogramme sur une distribution connue,
  demandes de démarrage ; simple, TSan, ASan/UBSan, contrôles négatifs). Le coût réel d'une capture active sur
  l'iPhone 16 Pro Max (perturbation du minutage SPU, thread d'échantillonnage) n'est pas mesuré.
- **Pont hôte.** La demande de capture à la fermeture du menu est du code Objective-C++ ; il est vérifié par des
  contrôles statiques et par une compilation (syntaxe et types) avec le SDK iPhone, sans édition de liens ni
  exécution (`test/rpcs3_host_bridge_ios_syntax_test.py`, workflow `rpcs3-host-bridge-check.yml`). Le parcours
  complet menu → demande → capture → export n'a pas été exécuté sur un appareil.
