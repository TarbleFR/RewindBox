# RPCS3 551 — journaux 547 : profil God of War III enfin appliqué, file RSX et compilations Metal (25 octobre 2026)

Demande : à partir des journaux du build 547, obtenir des gains réels de FPS,
surtout dans God of War III et Dragon Ball Z HD Collection, sans sauter de
draw. Base : Core 547 (`1b5c278c`, run 40232640441), identités PPU/SPU
`a987639e9f838d1c` / `d070cb361bdef607`.

## 1. Journaux fournis (faits)

| Processus | Build | Contenu |
| --- | --- | --- |
| 31897 | 545 | 19:55, compilation PPU à froid (29 modules, 169 s de génération), puis 30–40 fps |
| 32192 | 547 | DBZ HD Collection `BLES01658` (`CONFIG_LAYERS`), 45 fenêtres |
| 32208 | 547 | Jeu restauré depuis une sauvegarde d'état (deux restaurations, 1,1–1,2 s), 96 fenêtres. Le titre n'apparaît dans aucun des fichiers fournis ; ses mesures correspondent à celles des sessions God of War III précédentes |

`RPCS3-performance.log` de la seconde exportation ne contient qu'une ligne :
le fichier venait de tourner. Les lignes détaillées du processus 32208 sont dans
`RPCS3-performance.1.log`, non fourni. La chronologie, elle, est complète.

**Processus 32208, scène lourde (fenêtres 26–91)** : 9–16 fps, médiane 60–95
ms ; SPU ≈ 3,4 cœurs (`spu_ms` 210–340 par image) ; **≈ 98 000 PUTLLC lourds
par seconde** (`wl_putllc` 0,4–0,56 million par fenêtre) : chacun prend le
verrou d'écriture exclusif, qui bloque chaque thread PPU en cours ; attentes de
plage PPU de 1,5 à 6,4 s par fenêtre de 5 s ; FIFO RSX occupé 85–97 %, sans
attente GPU. Fenêtres 19–25 : 25 compilations de pipeline bloquantes de
0,6 à 4 s, soit ≈ 28 s de gel en 35 s (0,95–2,4 fps).

**Pourquoi ce volume de verrous** : toutes les sessions God of War III des
builds 412 à 547 indiquent `CONFIG_LAYERS legacy_custom=1 database=0`. Un
ancien fichier complet `config_BCES00510.yml` (instantané de tous les réglages,
créé par la première modification d'un réglage du jeu dans une ancienne build)
désactivait toute la couche base de données. Le profil RewindBox de God of War
III n'a donc **jamais été appliqué** : réservations SPU détendues, blocs SPU
Mega, contournement officiel du MLAA, résolution 75 %, limite 30 fps, RSX
multithread, etc. Les valeurs de ce fichier sont celles de la configuration
globale (Legacy, Safe, Auto, 100 %, WCB false, `max_spurs` 6).

**DBZ (32192)** : 31–35 fps, temps d'image unimodal de 22 à 36 ms (médiane
29,5 ms) : ce n'est pas un plafond à 30 fps. Par image : 21 ms de CPU sur le
thread RSX et **deux attentes GPU** (7,3 ms au total). Les compteurs 547 de
l'attente bornée restent à 0 : ces attentes sont temporisées et passaient
déjà par `vkWaitForFences`. **Le correctif 547 n'avait aucun effet sur DBZ.**

## 2. Modifications

### 2.1 Les anciennes configurations complètes héritent du profil (`System.cpp`, `RPCS3IOSConfigInheritance.h`)

Quand un fichier complet est appliqué, la configuration de la base de données
n'est plus ignorée. Elle est filtrée : un réglage que le fichier a laissé à la
valeur globale est hérité, un réglage que le fichier a changé est conservé.
L'ordre devient celui des titres sans fichier : global < profil < changements
propres du fichier. Le même texte est relu pour un redémarrage `exitspawn`.
`CONFIG_LAYERS` ajoute `inherited=`, `kept=`, `accurate_res=`, `mt_rsx=`,
`spu_spin=` et `mlaa_bypass=`. Le chemin non-iOS est inchangé.

Le profil God of War III ne force plus aucun mode de shaders : « Async
Recompiler » saute les draws dont le pipeline compile, ce que tu exclus. Le
jeu garde le mode Legacy.

### 2.2 Soumissions MoltenVK asynchrones (option iOS Experimental, choisie par les profils GoW3 et DBZ)

Nouveau réglage `MoltenVK Asynchronous Submits` (Automatique = désactivé).
Activé, il pose `MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS=0` : `vkQueueSubmit`
rend la main dès que la soumission est en file, et MoltenVK encode les
commandes Metal sur son propre thread. Les files du device reçoivent la
priorité globale *high* (`VK_EXT_global_priority`) : dans MoltenVK 1.4.2
(`MVKQueue::initExecQueue`), ce thread est alors *user-interactive*, comme
les threads RSX et SPU, au lieu de *user-initiated*. Les fences, sémaphores
et l'ordre des soumissions sont inchangés.

### 2.3 Les compilations Metal à la priorité du thread qui attend (tous les jeux)

`MVKMetalCompiler::compile` (MoltenVK 1.4.2, `MVKSync.mm:451`) envoie chaque
compilation de bibliothèque et de pipeline sur
`dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT)`, puis bloque
l'appelant sur une variable de condition. GCD rétrograde un appelant
*user-interactive* en *user-initiated*, et la variable de condition ne
transmet aucune priorité. Le thread RSX attendait donc des compilations qui
tournaient sous les threads de l'émulateur.

L'archive statique épinglée est un seul objet pré-lié. Son unique
relocation vers `_dispatch_get_global_queue`, à 0xd2750, se trouve dans
`MVKMetalCompiler::compile` (vérifié par désassemblage). Au moment de
l'édition de liens, `build-utils/rpcs3/patch_moltenvk_compile_qos.py` renomme
ce symbole indéfini à longueur égale, en `_rbx_mvk_compile_qos_queue`
(SHA-256 de l'archive `245e7e05…` → `b91a46f7…`, 19 octets changés), sur une
copie : le paquet en cache reste intact. Le Core définit cette fonction : un
appelant *user-interactive* compile sur la file globale *user-interactive*,
les autres gardent la file d'origine. Le script vérifie après l'édition de
liens que le symbole est résolu.

### 2.4 Profils

- God of War III : tout le profil existant s'applique maintenant, avec en plus
  les soumissions asynchrones (19 réglages hérités sur l'ancien fichier observé).
- DBZ `BLES01658` (nouveau) : soumissions asynchrones, cache de lecture FIFO de
  4 Kio, lot d'optimisations ARM64 déjà utilisé pour God of War III, streaming
  asynchrone des textures.

### 2.5 Mesures

- `COREPROF RSXSYNC551` : attentes GPU par cause (`frame_cleanup`,
  `cb_reuse`, `hard_sync`, `texture`, `other`), `vkQueueSubmit` (l'encodage
  Metal en mode synchrone), acquisition du drawable, présentation, **délai
  soumission → fin de chaque image**, compilations Metal par priorité.
- `COREPROF RSXFRAME551` : statistiques d'image propres à RPCS3 (draws,
  soumissions, caches). Les minuteries des étapes (préparation, sommets,
  textures, exécution, flip) ne tournent qu'une image sur 8. S'y ajoutent les
  passages au repos du FIFO.
- `COREPROF SPUWAIT551` : sondages GETLLAR actifs, sommeils, attentes
  `RdEventStat`, PUTLLC réussis, échoués et lourds. Les compteurs sont tenus
  par thread et écrits seulement par leur propriétaire.
- `RPCS3-timeline.log` : `title` dans chaque ligne ; `config` (couches
  appliquées et valeurs du profil) dans la première ligne de chaque
  démarrage ; familles `rsx_sync`, `rsx_frame` et `spu_wait`.

`SPUThread.cpp` fait partie de l'empreinte SPU : l'alias de
`JITCacheCompatibility.cmake` associe cet instantané exact à l'empreinte 546.
Aucun cache n'est recompilé par ces changements. En revanche, God of War III
compilera ses objets SPU pour la taille de bloc Mega à la première session :
c'est un réglage du profil, pas un changement de code.

## 3. Vérifications (sans iPhone)

`test/rpcs3_cell551_test.py` (ASan+UBSan, puis TSan) :

- Héritage : le document de base de données GoW3 est reconstruit depuis le
  profil Dart et la GameDB hors ligne, exactement comme
  `Rpcs3ConfigAdapter.mergeScalarOverrides` l'écrit. Appliqué au fichier
  observé, il donne 19/19 réglages hérités : `Accurate SPU Reservations:
  false`, `SPU Block Size: Mega`, MLAA contourné, 75 %, 30 fps, Legacy
  conservé. Un réglage changé par le fichier est conservé, une section absente
  est héritée, les listes sont comparées et une entrée invalide n'applique
  rien. Le test utilise le yaml-cpp de RPCS3 et le `yaml_load` de production.
- Compteurs SPU : 120 threads sur 32 emplacements, totaux exacts, emplacements
  libérés. Les causes RSX respectent la portée la plus externe.
- `CONFIG_LAYERS` : formateur de production, 55 contrôles.
- Delta : chaque ligne ajoutée est sous `RPCS3_IOS` ou `__APPLE__`, sans
  attente ni exception ajoutée ; empreintes PPU/SPU recalculées inchangées.

Aucune mesure de FPS n'est possible hors iPhone. **Aucun gain n'est
revendiqué.**

## 4. Limites

- Restauration d'une sauvegarde d'état : le contournement du MLAA de GoW3 ne
  s'applique qu'au chargement normal du jeu (le correctif PPU officiel ne
  touche pas un exécutable restauré). Pour le tester : démarrer le jeu
  normalement, puis charger la sauvegarde du jeu.
- Le profil GoW3 met `Write Color Buffers: true` et `Shader Precision: Ultra`
  (recommandations RPCS3) : un coût GPU qui s'ajoute aux gains.
- Les soumissions asynchrones n'ont jamais tourné sur ton iPhone : à juger
  sur la stabilité et sur `rsx_sync`.

## 5. Protocole iPhone (551 contre 547)

1. God of War III : vérifier dans la première ligne de la chronologie
   `config.inherited ≥ 19`, `accurate_res=false`, `spu_block=Mega`,
   `mlaa_bypass=1`. Comparer ensuite `summary.avg_fps`, `range_lock.total_ms`,
   `range_lock.wl_putllc`, `spu_wait.putllc_heavy` et
   `pressure.blocking_builds` (durée par compilation) dans la même scène.
2. DBZ : `rsx_sync.frame_latency` (≈ 1 image = le GPU suit ; ≈ 3 images = le
   GPU est la limite), la cause des deux attentes, `rsx_sync.submit` et
   `rsx_frame` (étapes RSX), puis `summary.avg_fps`.
3. Exporter `RPCS3-timeline*.log` **et** `RPCS3-performance*.log`, y compris
   les fichiers `.1`.
