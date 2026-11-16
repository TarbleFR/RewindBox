# RPCS3 Core 943 — performances de Black Ops II et God of War III (journaux de l'IPA 763)

Demande du mainteneur (16 novembre 2026) : Black Ops II démarre à 50 FPS puis descend à 20-30 ; God of War III, en nouvelle
partie, tourne entre 10 et 20 FPS dès la première image de jeu et à 10 FPS contre les premiers ennemis ; « tous les leviers
essayés n'ont rien changé », il faut une analyse profonde et de vrais correctifs.

Journaux privés (hors Git) : archive de l'IPA 763, Core 942. God of War III BCES00510 01.00 (PID 27597, trois démarrages,
468 s) et Black Ops II BLES01717 (PID 27739, deux démarrages, 280 s). Fenêtres de 5 s. Aucune erreur fatale, aucun gel.

## 1. Ce que mesurent les journaux

### 1.1 La puissance du processeur fixe le nombre d'images

Dans les deux jeux, le processeur est plafonné vers 2 W une fois le téléphone chaud, et le nombre d'images par seconde vaut
cette puissance divisée par l'énergie d'une image.

| Black Ops II, partie | Fenêtres 8-16 | Fenêtres 17-44 (à partir de ~60 s de partie) |
| --- | --- | --- |
| Images par seconde | 39,5-48,2 | 24,2-37,0 (surtout 26-31) |
| Puissance du processeur (ENERGY931) | 2,77-3,78 W | 1,93-2,10 W |
| Cœurs P : occupation, fréquence | 1,6-1,9 cœur, 3,0 → 2,3 GHz | 1,7-1,9 cœur, 1,7-1,9 GHz |
| Cœurs E : occupation, fréquence | 2,4-2,7 cœurs, 2,42 GHz | 2,7-2,8 cœurs, 2,11 GHz |
| Énergie d'une image | 64-95 mJ | 53-81 mJ |
| État thermique déclaré | nominal | **nominal** |

- La chute de 45 à 28 FPS se produit d'un coup, fenêtre 17, quand la fréquence des deux grappes est abaissée (cœurs E fixés à
  2,11 GHz, cœurs P vers 1,8 GHz). L'état thermique public reste « nominal » : c'est la régulation interne du système, pas une
  décision du Core. L'énergie d'une image ne change presque pas ; seule la puissance disponible baisse.
- Sur toute la partie, FPS ≈ 16 à 18 × fréquence des cœurs P (GHz) : le chemin critique tourne sur les deux cœurs P.
- Un cycle de cœur P coûte 0,40-0,53 nJ, un cycle de cœur E 0,10-0,13 nJ (4 fois moins) au point plafonné.

God of War III, troisième démarrage (nouvelle partie, état « fair » du début à la fin) :

| | Introduction (fenêtres 5-43, ~3 min) | Jeu (fenêtres 44-54) |
| --- | --- | --- |
| Images par seconde | 59,9-60,1 | 9,7-12,8 |
| Puissance du processeur | 1,64-2,00 W | 1,74-2,33 W |
| Énergie d'une image | 27-39 mJ | 157-233 mJ |
| Cœurs P : occupation, fréquence | 1,3 cœur, 3,3-3,4 GHz | 1,7-2,0 cœurs, **1,27-1,41 GHz** |
| Cœurs E : occupation, fréquence | 0,4 cœur | 2,8-3,3 cœurs, 1,8-2,1 GHz |
| Puissance des cœurs P | 1,57-1,74 W | 1,07-1,48 W |

Conséquence : aucun réglage graphique ne peut ramener 50 FPS durables. Seule une baisse de l'énergie d'une image (moins
d'instructions, ou des instructions exécutées sur les cœurs E plutôt que sur les cœurs P) relève les FPS une fois le
téléphone chaud. C'est pourquoi les leviers précédents (textures, ZCULL, soumissions, FXAA) n'ont pas changé les FPS : le
GPU n'est occupé qu'à 26-45 %.

### 1.2 God of War III en jeu : le thread principal attend en boucle sur un cœur P

Capture de 12,3 s pendant le jeu (PPUPROF912/SPUPROF923, 5 000 échantillons) :

- trois noyaux SPURS (BigCellSpursKernel0-2) exécutent du code 93 % du temps, deux autres 13 %, le petit noyau 79 % ;
- le thread PPU principal exécute du code 70 % du temps, dont 52 % de tous ses échantillons au retour 0x2eafe8 de la boucle
  `0x2eafd8 : mr r3,r30 ; li r4,3 ; mr r5,r31 ; bl 0x2e7b18 ; … ; cmpwi cr7,r3,0 ; beq cr7,0x2eafd8`, qui appelle
  0x2e7b18(objet, 3, objet->0x2a) jusqu'à ce qu'il réponde : il attend la fin d'un travail des SPU ;
- relevé des threads (census) : PPU principal 0,67-0,89 cœur, SPU 3,3-3,65 cœurs (0,71-0,81 par noyau chargé, alors qu'ils
  sont « en exécution » 93 % du temps : ils attendent un cœur), RSX 0,33-0,53, autres 0,22-0,27.
- Classes de service : le thread principal est « user-interactive », les SPU un cran en dessous (REWINDBOX_SPU_QOS_627). Le
  thread qui attend garde donc un cœur P, le plus coûteux, pendant que les noyaux qu'il attend tournent sur les cœurs E.

### 1.3 Black Ops II : les threads PPU coûtent deux fois leur travail

- Census : threads PPU 0,93-0,98 cœur, SPU 2,8-3,1, RSX 0,29-0,43, autres 0,30-0,33 (dont un thread sans nom 0,27-0,30).
- Échantillons (capture de 11 s) : les threads PPU n'exécutent du code que 0,41 thread en moyenne. main : 75 % dans
  `sys_timer_usleep`, 17 % suspendu ; Secondary : 29 % en exécution, 13 % suspendu ; Backend : 27 % suspendu, juste après
  `sys_semaphore_post`.
- En moyenne 0,56 thread attend une des deux places du planificateur lv2 (`PPU Threads` = 2) alors que 0,6 place est occupée :
  des threads restent suspendus alors qu'une place est libre.
- Les six SPU exécutent 52-55 % du temps et attendent 20 % une réponse du PPU dans leur boîte aux lettres
  (`rdch_in_mbox`, après `sys_spu_thread_send_event`) : le chemin critique passe par les threads PPU, donc par les cœurs P.
- Verrou d'écriture des PUTLLC exacts : 1,41 million par fenêtre, 646 ms de détention, PPU mis en attente 657 000 fois
  (538 ms) : 0,25 cœur environ, réel mais minoritaire.

Deux règles d'origine peuvent retenir un thread alors qu'une place est libre : `schedule_all()` ne réveille personne tant
qu'un thread prié de céder sa place ne l'a pas confirmé (`g_pending`), et `vm::_register_lock()` tourne sans pause tant que
les deux emplacements mémoire des PPU sont pris. Les journaux actuels ne permettent pas de dire laquelle joue : c'est ce que
mesure le Core 943 (§ 2.2) avant toute modification du planificateur.

### 1.4 God of War III, introduction : le thread principal consomme un cœur sans travailler

Pendant les 3 minutes à 60 FPS avant le jeu, le thread principal prend 0,93-0,97 cœur alors qu'il n'exécute du code que 7 %
du temps : 58 % des échantillons le trouvent suspendu, 20 % en reprise (`cpu_flag::memory`), 11 % dans `sys_timer_usleep`,
presque toujours au même endroit (0x1cdad4), avec 57-58 000 changements de contexte par seconde pour le processus. Cette
phase chauffe le téléphone avant le jeu (1,6-1,7 W sur les cœurs P à 3,4 GHz). Cause non établie ; le Core 943 enregistre le
code à 0x1cdad4 et les comptes du planificateur.

## 2. Modifications du Core 943

### 2.1 God of War III : la boucle d'attente du thread principal dort (REWINDBOX_GOW3_POLL_SLEEP_943)

- **Problème constaté** : en jeu, 52 % des échantillons du thread principal sont dans une boucle d'attente du travail des SPU
  (§ 1.2), sur un cœur P, pendant que les trois noyaux SPU chargés manquent de cœur et que le processeur est plafonné.
- **Cause** : le jeu attend en appelant sans arrêt la même vérification ; sur PS3 cela n'occupe qu'un fil matériel du PPU, sur
  l'iPhone cela consomme un cœur P et la puissance qui manque aux SPU.
- **Correction** : sur l'exécutable 01.00 seulement (PPU-4d5c5150…), à un démarrage neuf, et seulement si les onze mots
  0x2eafd4-0x2eaffc sont ceux lus sur l'appareil, la boucle rappelle aussitôt pendant 100 µs (une attente courte ne change
  pas), puis dort 30 µs (`sys_timer_usleep`) entre deux appels. Le début de l'attente est noté dans le cadre de pile de la
  fonction (0x70(r1), emplacement local que son prologue n'écrit jamais) ; le `nop` de 0x2eafd4 y pose une marque. Le reste
  est une « caverne de code » construite comme celles du moteur de patchs (code_alloc), atteinte par un saut lointain depuis
  0x2eaff4. Une attente finit toujours au premier appel qui répond ; une longue attente finit au plus un sommeil plus tard.
  Réglage « God of War III wait loop sleep » (Expérimental → PPU ; Automatique = cet exécutable ; Désactivé = la boucle du
  jeu). La caverne revient dans la boucle par des branches absolues réelles (`ba 0x2eafd8`, `ba 0x2eaff8`), que garde une
  sauvegarde d'état ; à la reprise d'une sauvegarde faite depuis un démarrage corrigé, le chargeur retrouve la caverne à
  ses mots exacts et réenregistre ce que l'hôte seul gardait (sa table d'exécution, le saut d'entrée), sans rien écrire
  dans la mémoire restaurée (`state=savestate_restored`) ; une sauvegarde faite sans correctif garde la boucle du jeu.
- **Coût connu** : une fonction qui contient un saut lointain sort de LLVM et passe par l'interpréteur, comme toute fonction
  qu'atteint un patch code_alloc ; ici la fonction de 0x2eafb0, celle de la boucle. Le premier démarrage corrigé recompile
  la partie du cache PPU qui la contient. Chaque sommeil est un vrai `sys_timer_usleep` (sortie et retour dans
  l'ordonnanceur lv2) : la latence d'une longue attente peut dépasser 30 µs de la marge du minuteur et de la reprise d'une
  place ; c'est ce que `SCHED943` mesure dans la même fenêtre.
- **Vérifications** : encodage des 23 mots de la caverne désassemblé (branches, comparaisons, compteurs, appel système 141),
  aussi décodé à la main par le relecteur ; analyse syntaxique des fichiers modifiés comparée à celle du Core 942 (aucune
  nouvelle erreur) ; relecture indépendante (§ 3). Non exécuté sur iPhone.
- **À lire dans les prochains journaux** : `CONFIG_LAYERS part=gow3_poll943 state=applied`, `COREPROF GOW3POLL943`
  (attentes et sommeils de la fenêtre), la part du thread principal dans le census, la puissance des cœurs P et les FPS dans
  la même scène. Effet attendu, non mesuré : rendre aux SPU une partie des 0,7 cœur P que prend l'attente.

### 2.2 Mesure du planificateur PPU (REWINDBOX_SCHED_CENSUS_943)

- **Problème constaté** : § 1.3 et § 1.4, des threads PPU qui coûtent beaucoup plus que leur travail et restent suspendus
  alors qu'une place semble libre.
- **Cause** : à établir ; deux candidats d'origine (attente de confirmation `g_pending`, emplacements mémoire pleins).
- **Correction** : mesure seulement, rien ne change dans l'ordonnancement. `COREPROF SCHED943` par fenêtre : suspensions,
  confirmations, réveils retenus par `g_pending` (et si le thread qui doit confirmer exécute du code ou attend sur l'hôte),
  reprises, temps avec `g_pending` > 0, enregistrements mémoire qui ont trouvé les deux emplacements pris et le temps passé
  à attendre, attentes de threads suspendus ; `ppu_top=` donne les six threads PPU les plus coûteux. Les captures de profil
  ajoutent `part=callee` (le code de la fonction appelée juste avant un point chaud : 0x2e7b18 pour God of War III) et
  `part=wait_code` (la région du point où attend un thread : 0x1cdad4).
- **Vérifications** : compilation comparée ; compteurs relâchés, mis à jour sous le verrou du planificateur pour le temps
  `g_pending`. Non exécuté sur iPhone.

### 2.3 Ce qui n'est pas changé, et pourquoi

- Réservations SPU exactes de Black Ops II : gardées (le mode relâché a gelé le jeu 40,8 s sur l'IPA 657).
- `PPU Threads` = 2 : la valeur d'origine ; `vm::_register_lock()` suppose qu'au plus deux threads PPU exécutent du code à la
  fois, en lever la règle ferait tourner le troisième. Décision après les mesures du § 2.2.
- Classes de service des threads (REWINDBOX_SPU_QOS_627) : leur effet sous plafond de puissance dépend du jeu (Black Ops II a
  besoin des cœurs P pour ses PPU, God of War III pour ses SPU) ; pas de changement sans mesure.
- Nombre de threads SPURS : pas de mesure sur l'appareil ; inchangé.

## 3. Compilation, relecture et livraison

Relecture indépendante du changement avant compilation : encodages, registres écrasés, usage de 0x70(r1), ordre des sauts,
compteurs et cadrage jugés corrects. Ses remarques, toutes appliquées :
- **bloquante** : une sauvegarde d'état prise pendant que le thread principal dort dans la caverne plantait à la reprise
  (table d'exécution et sauts lointains perdus). Corrigé : branches absolues réelles et réenregistrement à la reprise (§ 2.1) ;
- **majeure** : le rapport lisait la mémoire invitée sans protection depuis un thread non émulateur ; il passe par
  `copy_if_mapped` ;
- **mineures** : caverne rendue si le saut d'entrée échoue ; chargement virtuel (création du cache PPU d'un autre
  exécutable) sans effet ; commentaires des compteurs `acks`, `self_acks`, `suspend_waits` corrigés ; coût de
  l'interpréteur et latence décrits (§ 2.1). Restent notés sans changement : compteurs de la caverne non atomiques
  (diagnostic) et le vidage `part=callee`, qui suit le premier pc relevé dans la région chaude.

Compilation du Core, épinglage et IPA : à compléter.
