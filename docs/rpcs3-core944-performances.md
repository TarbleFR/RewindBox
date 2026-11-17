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
  sont donc enregistrées (sous `lv2_obj::g_mutex`), et un thread enregistré est repris sans `cpu_flag::signal` :
  `check_state` n'a besoin que de la levée de `cpu_flag::suspend`. Si le thread s'endort avant sa reprise, `sleep_unlocked`
  efface son enregistrement, et son vrai réveil est signalé comme avant.
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

- Passe de syntaxe sur l'hôte des unités modifiées, comparée à celle du Core 943 : aucun nouveau message.
- Relecture indépendante de la règle de suspension (voir le message du commit d'empaquetage).
- Contrôles d'empaquetage : porte de la route Core (fermeture des sources), test de route, test d'épinglage (sources), règle
  des marqueurs, patch canonique rematérialisé et incrément réversible, tests de sources.

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
