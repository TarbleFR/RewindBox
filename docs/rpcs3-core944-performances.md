# RPCS3 Core 944 — décharger le processeur (journaux de l'IPA 767)

Retour du mainteneur (17 novembre 2026), IPA 767 (Core 943) :
- Black Ops II ne tient toujours pas assez d'images par seconde.
- Quelques artefacts légers apparaissent et disparaissent aussitôt.
- Le téléphone chauffe moins.
- God of War III : aucune évolution ressentie.
- Demande : « soulager le CPU et la charge de travail inutile », corriger tout ce que montrent les journaux.

Journaux privés (hors Git) : archive de l'IPA 767, PID 32585, trois sessions :
- session 1 : menu ;
- session 2 : Black Ops II BLES01717 en partie, fenêtres 6 à 37 ;
- session 3 : God of War III BCES00510 en partie, fenêtres 12 à 27.

Les fenêtres durent 5 s.

## 1. Ce que mesurent les journaux

### 1.1 Comparaison avec l'IPA 763 (Core 942)

| En partie | IPA 763 | IPA 767 |
| --- | --- | --- |
| Black Ops II, images par seconde | surtout 26-31 après 60 s | médiane 30 (28-31 la plupart du temps) |
| Black Ops II, puissance du processeur | 1,93-2,10 W | médiane 2,19 W |
| Black Ops II, fréquence des cœurs P | 1,7-1,9 GHz | médiane 2,03 GHz |
| God of War III, images par seconde | 9,7-12,8 | 15,4-23,7 (médiane ~18) |
| God of War III, cœurs P | 1,2-1,5 W pour la boucle d'attente | 1,4-1,6 GHz, boucle endormie |

Le Core 943 a donc :
- relevé la fréquence des cœurs P de Black Ops II d'environ 0,2 GHz à puissance égale ;
- rendu à God of War III environ 60 % d'images en partie, mesurées.

Le plafond reste le même : environ 2,2 W pour le processeur une fois le téléphone chaud. Chaque cycle de travail inutile retiré
rend de la fréquence au chemin critique.

### 1.2 Black Ops II : le planificateur PPU attend des accusés de réception

La fenêtre 20 de la session 2 donne la mesure (COREPROF SCHED943) :
- 8 260 suspensions de threads PPU.
- Pendant **804 ms sur 5 s**, `lv2_obj::schedule_all()` n'a réveillé aucun thread, parce que `g_pending` n'était pas nul.
- 9 547 réveils ont été retenus. Dans 5 426 cas, chaque thread qui devait son accusé de réception attendait sur l'hôte
  (`cpu_flag::wait`) ; dans 4 121 cas, il exécutait du code invité.
- Les échantillons PPU (PPUPROF912) trouvent Backend suspendu dans 46 % des cas, dont 2 456 juste après un
  `sys_semaphore_post`, et le thread principal dans 32 %.

La règle d'origine fonctionne ainsi :
- un thread repoussé au-delà des deux emplacements PPU reçoit `cpu_flag::suspend` ;
- il doit l'accuser lui-même, au prochain sommeil ou par `cpu_sleep` → `lv2_obj::awake` depuis `check_state` ;
- aucun réveil n'a lieu avant cet accusé.

Le cas fréquent est un thread que l'on vient de réveiller : il est déjà dans la file, mais dort encore sur l'hôte. Il doit être
planifié par iOS, sortir de son attente, puis accuser, soit environ 100 µs par épisode. Pendant ce temps, le thread qui a pris
sa place ne démarre pas.

### 1.3 Black Ops II : le thread RSX hache 8 à 10 Go de textures par fenêtre

TEXVAL943, fenêtres 10 à 34 de la session 2 :
- 55 000 à 72 000 validations par fenêtre dans des époques ouvertes par un nouveau PUT ;
- 150 à 240 changements trouvés ;
- 8,2 à 10,4 Go hachés par le thread RSX.

L'horizon PUT de REWINDBOX_PUT_HORIZON_910 réduit ces époques dans God of War III depuis le Core 910, mais il n'était pas actif
pour Black Ops II.

### 1.4 God of War III

- **Les SPU font du vrai travail.** Ils occupent 3,4 à 3,6 cœurs. En partie, les échantillons SPU (SPUPROF923 capture 2)
  trouvent les noyaux SPURS 0 à 2 en exécution dans 93 % des cas. Les régions chaudes sont du calcul en virgule flottante,
  pas une attente active : les attentes passent par `rdch_event`, un vrai sommeil.
- **Les cœurs P sont pleins à basse fréquence.** Les deux cœurs P sont occupés (p_cpu_ms ≈ 10 000 par fenêtre) à 1,4-1,6 GHz.
  Le processeur consomme 2,2 W, dont 1,47 W sur les cœurs P.
- **Le thread principal fait encore 10 000 tours de planificateur par seconde.** Sa boucle d'attente du Core 943 dort 30 µs,
  48 810 fois par fenêtre. On compte 45 000 changements de contexte par seconde.
- **Le hachage des textures pèse lourd sur le thread RSX.** Il hache 11 à 17 Go par fenêtre, soit 12,5 ms d'étape de texture
  par image sur environ 55 ms. Cela représente 89 changements pour 19 490 validations, ouvertes surtout par des sauts corrigés
  (put_patched).

## 2. Modifications du Core 944

### 2.1 Suspension sans accusé d'un thread qui attend (REWINDBOX_WAITING_SUSPEND_944)

Fichiers : `rpcs3/ios/IOSWaitingSuspend944.h`, `Emu/Cell/lv2/lv2.cpp` (boucle de suspension de `awake_unlocked`, `schedule_all`, `sleep_unlocked`, `cleanup`) et `Emu/Memory/vm.cpp`.

**Le principe.** Un thread en `cpu_flag::wait` n'en sort que dans `cpu_thread::check_state()`. Son opération atomique garde
`cpu_flag::wait` tant que `cpu_flag::suspend` est posé, sauf si `cpu_flag::temp` dit que le thread ne peut pas encore
s'arrêter.

**La modification.** Une seule opération atomique vérifie que le thread porte `cpu_flag::wait`, sans `cpu_flag::temp` ni
`cpu_flag::suspend`, et ajoute alors `cpu_flag::suspend`.
- Le thread ne peut plus exécuter de code invité avant d'avoir vu la suspension. L'emplacement qu'il occupait est déjà libre,
  donc aucun accusé n'est demandé : `ack_suspend` reste faux et `g_pending` ne change pas.
- Le thread s'arrête ensuite dans `check_state` et `schedule_all()` le reprend, comme tout thread suspendu.
- Tout autre état (code invité en cours, section qui ne peut pas s'arrêter) suit le chemin d'origine, avec accusé.

**Ce que l'accusé protégeait aussi.** La relecture indépendante a montré deux autres rôles de l'accusé ; ils sont conservés
autrement.
- **Le signal de reprise.** Un thread entré dans un appel système (sys_semaphore_wait, par exemple) porte `cpu_flag::wait` avant
  d'atteindre `lv2_obj::sleep`. Si `schedule_all()` le reprenait avec `cpu_flag::signal` avant ce sommeil, ce sommeil échouerait
  comme « signalé » : l'attente rendrait CELL_OK sans `post` et le compte du sémaphore serait faussé pour de bon. Ces suspensions
  sont donc enregistrées (sous `lv2_obj::g_mutex`) jusqu'au prochain sommeil du thread. Là, `sleep_unlocked` efface un
  `cpu_flag::signal` en attente avant son test : aucun réveil de ce sommeil ne peut le précéder, puisqu'un thread ne trouve
  l'endormi dans la file de l'objet que sous le verrou de cet objet. La reprise garde `cpu_flag::signal`, comme à l'origine :
  `check_state` en a besoin pour rappeler `cpu_sleep()` lors d'une suspension suivante. Une première version reprenait le
  thread sans signal ; la seconde relecture a montré que `g_pending` pouvait alors ne plus jamais revenir à zéro.
- **Les emplacements du verrou mémoire.** Un thread qui détient un emplacement du verrou passif (`vm::g_locks`) garde le chemin
  d'origine. Sinon, le thread réveillé à sa place tournerait dans `vm::_register_lock` jusqu'à la libération de cet emplacement.
  Les threads qui ont dormi l'ont libéré (`prepare_for_sleep`) : c'est le cas fréquent des 5 426 réveils retenus.
- **Le débogueur.** Il n'affiche pas la mention « (LV2 suspended) » pour ces threads.

**Ce qui ne change pas.** Le nombre d'emplacements, les priorités et l'ordre de la file.

**Réglage.** « PPU suspension of waiting threads » (Experimental, PPU) : en Automatique, Black Ops II et God of War III ;
Activé pour tous les titres ; Désactivé, la règle d'origine.

**Compteur.** COREPROF SCHED943 `acks_skipped=` compte les suspensions qui n'ont pas demandé d'accusé.

### 2.2 Horizon PUT pour Black Ops II (REWINDBOX_PUT_HORIZON_BO2_944)

Le réglage existant « PUT epoch horizon » passe en Automatique pour Black Ops II, comme pour God of War III. La règle est celle
du Core 910 : une époque de validation n'est ouverte que lorsque la FIFO atteint les commandes visibles au PUT de l'époque
précédente. Les données qu'une commande lit sont écrites avant que la commande devienne visible ; une validation faite après
cela sert donc toutes les commandes au-dessous de l'horizon.

Les acquisitions de sémaphore, les écritures RSX, les vidages, les invalidations et les fins d'image ouvrent leurs époques comme
avant. Le résultat attendu est moins de hachage des textures sur le thread RSX, sans changer ce qui est validé.

### 2.3 Plancher des attentes courtes pour God of War III

La règle du Core 943 (REWINDBOX_PPU_WAIT_FLOOR_943) s'applique désormais aussi à God of War III en Automatique.
- Elle vise la même attente refaite par le même thread, avec le même appel système, le même objet et le même délai, après que
  la précédente est allée jusqu'à son terme.
- Cette attente dure quatre fois le délai demandé, au plus 200 µs.
- Une attente signalée se termine toujours aussitôt.

Effet attendu : la boucle du thread principal, qui dormait 30 µs, dort 120 µs à partir de la deuxième attente. Elle fait donc
quatre fois moins de tours de planificateur et voit la fin du travail SPU au plus 90 µs plus tard.

### 2.4 Ce qui n'est pas changé, et pourquoi

- **Hachage des textures de God of War III.** Sur iOS, les pages ne peuvent pas être protégées en écriture (voir
  `texture_cache_protection_policy.h`), le hachage est donc la seule détection des écritures de l'invité. Des textures changent
  en mémoire locale RSX (862 dans la session 3, 4 688 dans Black Ops II) comme en mémoire principale. Aucune exemption par
  région n'est donc sûre, et allonger la durée de validité produirait justement des artefacts d'une image.
- **Travailleur de pré-hachage.** Environ 85 % de ses octets sont perdus, mais il coûte 265 ms de cœur par fenêtre hors du
  chemin critique et retire environ 0,44 Go par fenêtre au thread RSX. Il est conservé.
- **PUTLLC SPU lourds de God of War III.** Ils sont 78 000 par seconde. Les réservations précises restent actives : leur
  relâchement a déjà produit un gel.
- **Calcul SPU.** C'est du vrai travail ; le réduire demanderait de changer la génération de code SPU, dont les identités
  restent inchangées.
- **Vidage de gel à la fin de God of War III (6 s sans image).** Il se produit après la fermeture du menu, pendant la sortie,
  avec le thread principal dans `sys_ppu_thread_join` : c'est le chemin de sortie du jeu, pas un gel en partie.
- **Pics d'image et compilations.** Black Ops II a six arrêts de 0,5 à 1,1 s liés à la compilation de nuanceurs (fs-library),
  plus un pic de 949 ms en fenêtre 36. God of War III a un pic de 1 138 ms en fenêtre 5 de la session 3, pendant le chargement.
- **Artefacts de Black Ops II.** La mémoïsation des textures ne compte aucune discordance, et les journaux ne permettent pas d'en
  trouver la cause. Il faut une description ou une capture : endroit, forme, couleur.

## 3. Contrôles

- Passe de syntaxe sur l'hôte de `lv2.cpp` et `vm.cpp`, comparée à celle du Core 943 : aucun nouveau message.
- Trois relectures indépendantes de la règle de suspension.
  - La première a trouvé le signal de reprise périmé (bloquant).
  - La deuxième a trouvé le blocage de `g_pending` causé par une reprise sans signal (bloquant).
  - La troisième ne trouve plus de bloquant. Elle a vérifié que le signal effacé ne peut pas être un vrai réveil et que
    l'enregistrement ne peut pas devenir périmé.
- Porte de la route Core (fermeture des sources), test de route, test d'épinglage (sources) et règle des marqueurs : tous
  réussis.
- Patch canonique 97e47ec5 (519 fichiers) rematérialisé sur une copie amont propre. L'incrément depuis le Core 943 (9 fichiers)
  s'inverse sur l'arbre canonique.
- Les 26 tests de sources qui tournent sur cet hôte réussissent. Le contrôle statique de `rpcs3_put_horizon910_test` vérifie
  désormais la règle Automatique étendue à Black Ops II ; ses scénarios et ses contrôles négatifs sont inchangés et réussissent.

Aucune entrée de génération de code ne change : PPU a987639e9f838d1c, SPU 477a3fa442d27917.

Non exécuté ici : la compilation iOS (commit suivant) et tout essai sur appareil. Aucune affirmation de fréquence d'images ni
de chauffe.

## 4. Comparaison sur la prochaine IPA

- **Black Ops II.**
  - SCHED943 : `pending_ms` et `gate_blocked` doivent baisser, `acks_skipped` approcher les cas « waiting » de l'IPA 767.
  - TEXVAL943 et EPOCH909 : moins de validations en époques PUT, `put_deferred` non nul.
  - Fréquence des cœurs P et images par seconde à puissance égale.
- **God of War III.**
  - PPUWAITFLOOR943 : des attentes `raised`.
  - Moins de changements de contexte par seconde.
  - Fréquence des cœurs P et images par seconde.

## 5. Core 945 — gestion du processeur (demande du mainteneur, 17 novembre : « avant toute nouvelle IPA »)

### 5.1 Ce que montrent les journaux de l'IPA 767

Black Ops II en partie, fenêtre 20 de la session 2 :
- 1,55 million de PUTLLC exacts (SPUWAIT551 `putllc_heavy`), soit 310 000 par seconde. Chacun prend le verrou d'écriture :
  - l'écrivain SPU attend que chaque thread PPU en cours s'arrête ;
  - les threads PPU attendent ensuite qu'il ait fini.
- Le Build 676 mesurait déjà 2,4 à 2,9 s de temps SPU par fenêtre pour acquérir ces verrous, et le Core 935 530 ms de temps
  PPU par fenêtre derrière eux.
- Les échantillons SPU (SPUPROF923) trouvent chaque noyau SPURS en attente dans `mfc_getllar` ou `mfc_putllc` dans environ
  16 % des cas.

Ces deux attentes tournent sur le cœur. L'attente économe du Core 931 (WFE : le cœur est mis en veille jusqu'à l'écriture
attendue) ne s'active qu'à partir de l'état thermique « serious ». Or, depuis les correctifs thermiques, le téléphone est resté
« nominal » ou « fair » dans les 239 fenêtres des journaux : `event_waits=off` partout, et ces attentes n'ont jamais reposé un
cœur.

L'attente du thread RSX au repos suit la même règle depuis le Core 941, dans tout état thermique une fois l'auto-test WFE
réussi. Sur l'IPA 767, elle se termine en moins de 2 µs dans 99,7 % de ses 74 000 attentes par fenêtre.

### 5.2 Modification (REWINDBOX_EVENT_WAITS_ALWAYS_945)

Fichiers : `rpcs3/ios/IOSThermalPolicy931.h` (`event_waits()`) et le texte du réglage dans `ios/RPCS3IOSSettings.cpp`.

**La règle.** En Automatique, les deux attentes deviennent des attentes WFE dans tout état thermique, dès que l'auto-test du
démarrage a constaté que la séquence repose le cœur (`wfe_verdict=1`, REWINDBOX_WFE_SLEEP_940) :
- l'écrivain qui attend l'arrêt des threads PPU ;
- le thread PPU qui attend derrière un écrivain.

**Ce qui ne change pas.**
- Chaque attente attend la même écriture, avec la même borne et le même repli.
- L'écriture attendue vide le moniteur et met fin à l'attente WFE.
- Avant l'auto-test, ou s'il échoue, la règle reste celle du Core 931 (« serious »).
- Activé, Désactivé et une étape de comparaison de leviers restent comme avant.

**Effet attendu.** Ces cœurs tournaient à vide ; ils sont désormais mis en veille pendant l'attente. La puissance économisée
revient au chemin critique, sous le même plafond d'environ 2,2 W. Il n'y a aucun changement de synchronisation.

### 5.3 Ce qui n'est pas changé

- **GETLLAR SPU** (`busy_wait(300)` en attente d'une ligne verrouillée). Le code est dans `SPUThread.cpp`, une entrée de la
  génération de code SPU : le modifier invaliderait les caches SPU compilés.
- **Réservations exactes de Black Ops II.** Le mode relâché a gelé le jeu (IPA 657).
- **Migrations entre grappes** (`pset_switches`, 12 000 par seconde). Les journaux ne disent pas quels threads migrent.

### 5.4 À lire dans les prochains journaux

- THERMAL931 : `event_waits=on`, ainsi que `writer_park_waits` et `ppu_passive_waits` non nuls.
- `wfe_latency_us` doit rester presque entièrement sous 2 µs.
- ENERGY931 : la puissance des cœurs E, et la fréquence des cœurs P à puissance égale.
- Les images par seconde de Black Ops II.

## 6. Journaux de l'IPA 771 (Core 945) et Core 946

L'IPA 771 a été construite par la session S2Arm et contient le Core 945. Journaux du 17 novembre, PID 35822, quatre
sessions :
- session 1 : God of War III, démarrage normal ;
- session 2 : God of War III, reprise d'une sauvegarde d'état ;
- sessions 3 et 4 : Black Ops II (solo, puis passage au multijoueur).

### 6.1 Ce qui a changé par rapport à l'IPA 767

| Mesure | IPA 767 | IPA 771 |
| --- | --- | --- |
| Black Ops II, réveils bloqués par `g_pending` (SCHED943 `pending_ms`) | 804 ms / 5 s | 53-65 ms / 5 s |
| Black Ops II, suspensions sans accusé (`acks_skipped`) | — | 2 141-2 405 / 5 s |
| Black Ops II, images par seconde | médiane 30 (cœurs P à 2,03 GHz) | 29-38, surtout 31-34 (cœurs P à 1,6-1,9 GHz) |
| Black Ops II, images par GHz des cœurs P | ≈ 14,8 | ≈ 19,4 |
| Black Ops II, état thermique | nominal | **serious**, après deux sessions de God of War III |
| Attentes WFE de l'écrivain et du PPU | jamais (`event_waits=off`) | 0,9 et 1,1 million / 5 s |
| `wfe_latency_us` sous 2 µs | — | 99,9 % |
| God of War III (démarrage normal), images par seconde | 15-24 (médiane ≈ 18) | 21-27 (médiane ≈ 24) |
| God of War III, plancher des attentes courtes | — | 10 573 attentes 30 → 120 µs / 5 s |

- **Black Ops II produit le même nombre d'images avec des cœurs P plus lents.** Le téléphone était en état « serious » toute
  la session, après deux sessions de God of War III, et les cœurs P tournaient 0,4 GHz plus bas. À fréquence égale, il fait
  environ 30 % d'images en plus.
- **L'horizon PUT ne diffère rien dans Black Ops II** (`put_deferred=0`). Black Ops II tourne avec la précision FIFO par
  défaut (Atomic), qui ne lit PUT qu'au remplissage du cache. En revanche, l'horizon ouvre maintenant une époque à chaque saut
  corrigé (`put_patched`, environ 200 par fenêtre). Ces époques trouvent environ 118 textures réellement modifiées par
  fenêtre, que l'IPA 767 ne revalidait pas avant la prochaine époque. C'est une cause possible des artefacts brefs signalés sur
  la 767. Le volume haché ne change pas (9,3 Go par fenêtre, contre 8,2 à 10,4 Go) : le réglage est conservé.

### 6.2 Défaut : la boucle de God of War III n'est pas corrigée après une sauvegarde ancienne (REWINDBOX_GOW3_POLL_SAVESTATE_946)

En session 2, God of War III reprend une sauvegarde d'état faite avant le Core 943. Le journal donne
`CONFIG_LAYERS part=gow3_poll943 state=savestate cave=0x0`.
- La mémoire restaurée ne contient pas le correctif, et le chargeur ne voulait rien y écrire.
- Le thread principal retourne donc à son attente active : 0,70 à 0,83 cœur.
- Les SPU font 8,6 millions de PUTLLC par fenêtre, avec 4,9 millions d'échecs, contre 0,55 million après un démarrage
  normal.
- Les images tombent de 20 à 7 par seconde à mesure que le téléphone chauffe.

**Correctif.** Une sauvegarde dont la mémoire contient encore la boucle d'origine est corrigée comme au démarrage : même
contrôle des onze mots, même code ajouté, même repère et même saut (`state=savestate_applied`).
- Un thread sauvegardé au milieu de la boucle n'a pas écrit son repère. Il trouve dans sa pile une valeur plus ancienne, donc
  il dort 30 µs entre deux appels dès l'appel suivant resté sans réponse, ce qui est la règle. Son attente suivante écrit le
  repère normalement.
- Une sauvegarde qui contient déjà le correctif le retrouve et le réenregistre, désormais quel que soit le réglage : un thread
  sauvegardé dans ce code ne pourrait sinon pas reprendre.

**Relecture indépendante :** aucun bloquant.
- La mémoire est restaurée avant ce point, et l'analyse et la compilation PPU viennent après.
- L'allocation du code ajouté respecte la carte restaurée.
- Ses remarques sont appliquées : le réenregistrement quel que soit le réglage, et le texte du réglage et des commentaires.

### 6.3 Contrôles

- Passe de syntaxe sur l'hôte de `PPUModule.cpp` et `RPCS3IOSSettings.cpp` : aucun nouveau message.
- Contrôles d'empaquetage : la route Core, son test, le test d'épinglage (sources) et les marqueurs réussissent.
- Patch canonique rematérialisé ; l'incrément depuis le Core 945 s'inverse ; les 26 tests de sources réussissent.
- Identités de génération de code inchangées.

Non exécuté ici : l'iPhone.

### 6.4 À lire dans les prochains journaux

- God of War III repris d'une sauvegarde : `state=savestate_applied`, un thread principal sous 0,6 cœur et des PUTLLC SPU
  revenus à l'ordre d'un démarrage normal.
- Black Ops II dans un état thermique comparable à celui de l'IPA 767, pour séparer l'effet des correctifs de celui de la
  chaleur.

## 7. Core 947 — ce qu'il restait (demande du mainteneur, 17 novembre : « avant toute compilation corrige ce qu'il reste »)

### 7.1 L'horizon PUT diffère aussi en précision FIFO Atomic (REWINDBOX_PUT_HORIZON_ATOMIC_947)

**Le défaut.** Black Ops II tourne avec la précision FIFO par défaut (Atomic). Sur l'IPA 771, on mesure `put_deferred=0` pour
1 916 époques PUT par fenêtre. Dans ce mode, la FIFO lit les commandes par un cache et ne lit PUT qu'au remplissage de celui-ci ;
l'horizon ne pouvait donc rien différer sans risquer de franchir l'horizon sans le voir.

**Le correctif** (`RSXFIFO.cpp` `read_put` et `fetch_u32_refill`).
- Tant qu'une époque est différée, un remplissage du cache s'arrête à l'horizon. Cette limite s'applique après la limite au PUT
  lu, puis de nouveau après une lecture partielle.
- Le mot situé à l'horizon ne peut donc être lu qu'au travers d'un nouveau remplissage. Celui-ci lit PUT et ouvre l'époque
  différée avant la première commande concernée.
- Le cache ne contient jamais de mot au-delà du PUT lu, et les arguments lus directement (`get_current_arg_ptr`) restent bornés
  au cache. Rien d'autre ne peut donc franchir l'horizon.
- Les modes Fast et Atomic diffèrent ; les modes ordonné et « As PS3 » ne diffèrent jamais.

**Le test** `rpcs3_put_horizon910_test` modélise maintenant aussi le mode Atomic : lecture de PUT au remplissage seulement, cache
de 16 mots arrêté au PUT et à l'horizon, invalidé par les sauts, appels, retours, sauts sur eux-mêmes et remises à zéro.
- Aucune des 16 séries ne sert de version de texture illégale.
- Le contrôle négatif `no_atomic_clip` (le cache n'est plus arrêté à l'horizon) en sert 71.
- Dans ce modèle, le mode Atomic retire 2 à 16 % des époques et 1 à 6 % des hachages. Le modèle lit déjà PUT moins souvent
  que la FIFO réelle ; le gain réel se lira dans `EPOCH909 put_deferred` et `TEXVAL943`.

### 7.2 Où tournent les threads (REWINDBOX_CLUSTER_CENSUS_947, mesure)

Les 61 000 changements de grappe par fenêtre (`pset_switches`) ne disent pas quels threads migrent. Chaque fenêtre, la ligne
`COREPROF CLUSTER947` donne le temps processeur et l'énergie des threads PPU, SPU, RSX, JIT et autres, sur les cœurs P et sur
les cœurs E. Ces chiffres viennent de `proc_pidinfo(PROC_PIDTHREADCOUNTS)` (iOS 16), recherché au lancement comme
`proc_pid_rusage`. C'est une mesure seulement : elle dira quel placement corriger.

### 7.3 Autres points

- **La ligne de rapport de la boucle de God of War III** porte `resumed=`, qui distingue un refus sur une sauvegarde d'un refus
  au démarrage.
- **La liste `applied`** ne sert qu'à un compte affiché dans le journal, ignoré lors d'une reprise. La différence relevée par la
  relecture n'a aucun effet, elle reste telle quelle.
- **Réservations exactes de Black Ops II.** Le mode relâché a gelé le jeu (IPA 657), il n'est pas réessayé. Les attentes qui
  les entourent sont en WFE depuis le Core 945.
- **GETLLAR SPU.** Le code est dans `SPUThread.cpp`, une entrée de la génération de code SPU. Le modifier invaliderait les caches
  SPU compilés de tous les jeux : ce n'est pas un défaut à corriger ici.

### 7.4 Relecture et contrôles

**Relecture indépendante du Core 947 : aucun bloquant dans le code.**
- **La règle Atomic tient sur tous les chemins qui passent par le cache.**
  - En mode Atomic, `read_put` n'est appelé qu'au remplissage du cache. Quand une époque est différée, la fin du cache reste
    à l'horizon ou avant.
  - La taille du cache coupé reste supérieure ou égale à `addr - m_cache_addr + 4`, et il n'y a pas de remplissage sans fin.
  - `get_current_arg_ptr` et ses appelants (nv4097, nv308a) restent bornés au cache.
  - Les sauts, les sauts sur eux-mêmes modifiés et les remises à zéro sont couverts.
- **La structure de `proc_threadcounts` est conforme.** Un échec de l'appel donne `available=0`, sans plantage.
- **Remarques appliquées.**
  - La mesure de répartition a sa propre continuité entre fenêtres.
  - Le nombre de niveaux est remis à zéro à chaque relevé.
  - Le bloquant signalé portait sur le test étendu, qui n'était pas encore sur la branche ; il est dans ce commit.
- **Remarques laissées en l'état.**
  - nv4097 saute les méthodes d'un bloc begin/end d'après le PUT brut. Les arguments ne sont relus qu'au dessin, après
    l'époque que la commande END démarre en remplissant le cache. Le mode Fast fait déjà de même.
  - Les lignes du cache situées au-delà de l'horizon sont lues puis jetées. C'est un petit coût seulement.

**Contrôles.**
- Passe de syntaxe sur l'hôte de `RSXFIFO.cpp`, `PPUModule.cpp` et `RPCS3IOSPerformance.cpp` : aucun nouveau message. Le bloc
  Apple de la mesure de répartition a été compilé seul, depuis le texte réel, avec des déclarations Mach de substitution.
- Contrôles d'empaquetage : la route Core, son test, le test d'épinglage (sources) et les marqueurs réussissent.
- Patch canonique 98cc2a98 (519 fichiers) rematérialisé sur une copie amont propre, et l'incrément depuis le Core 946 s'inverse.
- Les 26 tests de sources réussissent, dont `rpcs3_put_horizon910_test` avec ses 16 séries et le contrôle `no_atomic_clip`.
- Identités de génération de code inchangées.
