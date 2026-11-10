# RPCS3 Core 916 — correctifs tirés des journaux du build 718

Mission du 10 novembre. Entrées : cinq journaux applicatifs du build 718 (Core 914), jamais dans Git. Les mesures
ci-dessous viennent de ces fichiers, relues sur les lignes d'origine après passage par
`tools/rpcs3/capture_analyzer.py`. **Aucune mesure iPhone n'a été faite avec le Core 916** : les résultats de ce
document sont des exécutions sur hôte du code livré ; le protocole de la section 7 dit ce qu'il reste à mesurer.

## 1. Ce que contiennent les fichiers fournis

| Fichier | Contenu pour le build 718 |
|---|---|
| performance (1 577 669 o, une rotation) | session 5 (GOW3 après restauration), fenêtres 15 à 64 ; les fenêtres 18 à 64 ont été écrites jeu arrêté : 91,5 % du fichier |
| diagnostic | session 5, 7 fenêtres |
| causes | `FRAMEPROF527`, `FRAMECAUSE`, `GPUTIME621` des sessions 2 (fin), 3, 4, 5 ; dump de blocage d'AC1 |
| milestones | démarrages et dumps (Black Flag PID 44597 ; PID 45272) |
| timeline | jalons de l'hôte |

La rotation `.1` n'est pas jointe. Conséquence : les lignes par fenêtre de BO2 (sessions 1 et 2) et d'AC1
(session 3) — CPU par thread, compteurs SPU, passes de rendu, mémo de textures — et la fenêtre 12 de GOW3 **ne sont
pas dans les fichiers reçus**. Les chiffres de la demande pour ces fenêtres n'ont donc pas pu être relus ici ; ils
ne fondent aucune modification de ce Core.

`PUTLLCTRACE912` et `PPUPROF912` sont absents pour une raison démontrée (lot 3) : aucune capture ne pouvait être
demandée sur le build 718.

## 2. Lot 1 — AC1 : arrêt de 6 s à la sortie du jeu (cause démontrée, corrigée)

**Symptôme chiffré.** PID 45272, session 3, `BLES00158`, `accurate_res=false`. Menu fermé à 620,709 s, dernier flip
vers 621,05 s, dump de blocage à 627,10 s, arrêt forcé vers 628,6 s. L'écart de 7,569 s relevé dans la demande est
celui de la **séquence d'arrêt**, pas un défaut en jeu : l'hôte a demandé la sortie (`EXITGAME`), le jeu a commencé
à fermer SPURS et n'a jamais fini ; la limite d'arrêt l'a tué.

**Chemin de production.** Dans le dump : le thread principal attend dans `sys_semaphore_wait` le sémaphore `_spuWkL`
depuis 6,125 s (attente de la fin d'une charge SPURS). La deuxième ligne d'en-tête SPURS (`0x102ec600`) contient
l'état « en cours d'arrêt » de la charge 1 et `sysSrvMsgUpdateWorkload = 0xff`, écrits par l'opération de réservation
du PPU. La première ligne (`0x102ec580`) contient `sysSrvMessage = 0xe0` : l'écriture simple d'un octet `0xff` que
le PPU fait ensuite pour réveiller les noyaux SPURS **n'est pas en mémoire**. Les cinq SPU attendent un événement de
perte de réservation sur cette ligne depuis 6,125 s, avec le temps de réservation actuel de la ligne.

Chaîne : PPU en attente (`_spuWkL`) → condition (les noyaux SPURS traitent l'arrêt) → producteur (écriture PPU de
`sysSrvMessage`) → publication (perdue) → réveil (jamais).

**Mécanisme.** Avec « Réservations SPU précises » désactivé, le PUTLLC d'un SPU sur les deux lignes d'en-tête SPURS
copiait ses 128 octets en mémoire dès que le temps de réservation n'avait pas changé, sans comparer la ligne
(`SPUThread.cpp`, `do_putllc`, branche `relaxed_spurs`, code amont). Une écriture simple du PPU n'avance pas ce
temps : faite entre le GETLLAR et le PUTLLC du SPU, elle était écrasée par la copie lue avant elle. Sur la console,
cette écriture fait perdre sa réservation au SPU et son PUTLLC échoue.

**Modification** (`REWINDBOX_SPURS_RELAXED_STORE_916`, `rpcs3/ios/IOSSpursRelaxedStore.h`, appelée par
`do_putllc`) :

1. la ligne entière est comparée à la copie du GETLLAR : toute écriture antérieure fait échouer le PUTLLC ;
2. chaque portion de 16 octets que le SPU a modifiée est échangée atomiquement contre sa valeur du GETLLAR ; une
   portion non modifiée n'est jamais écrite ;
3. une écriture qui atteint une portion modifiée pendant le stockage fait échouer le PUTLLC : les portions déjà
   écrites reprennent leur valeur du GETLLAR (un octet que l'invité y aurait écrit entre-temps est conservé). La
   ligne finit telle que le GETLLAR l'avait lue, plus les écritures de l'invité — l'ordre « écriture invité, puis
   PUTLLC qui échoue » — quelle que soit la largeur de l'écriture. Comme la mémoire a été écrite un instant, le temps
   de réservation avance et les threads en attente sur la ligne sont prévenus.

Même verrou qu'avant (le verrou exclusif du mot de réservation), pas de verrou d'écriture global, pas d'attente,
pas de délai, pas de résultat forcé. Le chemin « précis » et toutes les autres adresses sont inchangés.

Une première forme conservait l'écriture concurrente à côté des octets du SPU, octet par octet. La relecture
indépendante du 10 novembre a montré qu'une écriture de plusieurs octets pouvait alors finir coupée en deux (une
valeur que ni l'invité ni le SPU n'avait écrite) : cette forme est remplacée par le retour arrière ci-dessus et sert
de second contrôle négatif. La même relecture n'a trouvé aucun défaut de verrou, d'avance du temps de réservation,
de blocage ni de réveil manqué ; elle a vérifié que tous les autres écrivains de la ligne respectent le verrou.

**Test discriminant** (`test/rpcs3_spurs_relaxed_store916_test.py`, en-tête réel compilé) : 10 scénarios ordonnés
sur la ligne du dump et une exécution concurrente (deux écrivains simples à côté de cinq threads GETLLAR/PUTLLC).
Contrôles négatifs : le même banc avec l'ancien stockage, puis avec la fusion octet par octet.

| | Ancien stockage | Fusion octet par octet | Core 916 |
|---|---|---|---|
| Vérifications échouées (scénarios ordonnés) | 12 | 6 (dont l'écriture de deux octets coupée) | 0 sur 19 |
| Écritures invité perdues (exécution concurrente) | 344 320 à 364 010, sur 1,8 million | — | 0, sur 4,9 à 9,5 millions |
| PUTLLC interrompus puis annulés | — | — | 98 173 à 176 233, tous restitués |
| Incréments SPU en mémoire | — | — | exactement ceux des PUTLLC réussis |

Passe aussi sous ASan/UBSan.

**Limites.** Reproduit sur hôte, pas sur iPhone. Le correctif s'applique à tout titre SPURS dont le profil désactive
les réservations précises (AC1, GOW3) ; il n'est démontré comme cause que pour l'arrêt d'AC1. Compteur exporté :
`COREPROF SPUWAIT551 … spurs_relaxed=écrits:annulés:refusés` par fenêtre. Ce qu'une comparaison de données ne peut
pas voir reste comme partout dans cet émulateur : une écriture invité de la valeur déjà présente. S'y ajoute un cas
de second ordre : deux écritures invité pendant un même PUTLLC, dont l'une écrit, dans une portion en cours de
restitution, exactement l'octet que le SPU venait d'y écrire.

## 3. Lot 2 — GOW3 : le contournement MLAA n'était appliqué à rien (corrigé)

**Symptôme chiffré.** PID 45272, session 5 (`BCES00510`, restauration), fenêtre 15 : 11,2 images/s, GPU occupé
21,3 % du temps, thread PPU principal 0,931 cœur, SPU 2,99 cœurs, thread RSX 0,398. Ce n'est pas le GPU qui
limite. `READBACK555` : 58 relectures du tampon couleur par fenêtre de 57 images (3,8 ms en moyenne, 18 ms au
plus) : une par image.

**Chemin de production.** `COREPROF GOW3MLAA909` : exécutable `PPU-4d5c5150…` (application 01.00),
`spu_matched=0`. Le réglage du titre « God of War III MLAA Bypass » est activé dans le profil, mais sa moitié PPU ne
connaissait que l'exécutable 01.03 : sur l'exécutable installé, rien n'était appliqué, et le jeu continue de faire
son anti-crénelage MLAA sur SPU avec relecture du tampon à chaque image.

**Modification** (`REWINDBOX_GOW3_MLAA_100_916`, `rpcs3/ios/IOSGow3MlaaPatch.h`, `PPUModule.cpp`) : un plan par
exécutable, tiré du correctif « Disable MLAA » du dépôt de correctifs de RPCS3. 01.03 : inchangé. 01.00 : octet
`0x52BF2F` mis à 0 et appel en `0x231248` remplacé par `nop`, **seulement** sur cet exécutable exact, seulement si le
mot à remplacer est bien un appel relatif et l'octet 0 ou 1 ; sinon rien n'est écrit et le journal dit
`ppu=refused_guard`. Comme tout correctif d'exécutable, il s'applique à un démarrage à froid.

Ce n'est ni un changement de profil ni une baisse cachée : c'est le réglage déjà activé qui prend enfin effet. Son
effet visible est celui que le réglage annonce — l'anti-crénelage du jeu est désactivé. La résolution reste à 75 %.

**Test discriminant** (`test/rpcs3_gow3_mlaa100_916_test.py`, 26 vérifications, en-tête réel exécuté sur des images
des deux exécutables : application, ré-application, garde refusée sur contenu inattendu, autre exécutable
ignoré). Contrôle : le Core 914 ne nomme que 01.03.

**Limites.** Aucun gain n'est mesuré : il faut l'iPhone. Une sauvegarde d'état contient la mémoire du démarrage
dont elle est issue : la sauvegarde existante (faite sans le correctif) restera sans effet, et le journal le dit
(`savestate_patched=0`). Il faut un démarrage à froid, puis une nouvelle sauvegarde. La moitié SPU (`spu_matched=0`,
image `SPU-c551925d` non reconnue) reste inchangée : avec la moitié PPU appliquée, le jeu ne programme plus MLAA.

## 4. Lot 3 — collecte : quatre défauts qui privaient les décisions de données (corrigés)

| Défaut constaté sur 718 | Cause | Correction | Test |
|---|---|---|---|
| Aucune capture `PUTLLCTRACE912` / `PPUPROF912` | `CONFIG_LAYERS levers627=` exportait 18 chiffres sur les 21 composés depuis le Core 912 ; l'hôte lit les chiffres 20 et 21 sur cette ligne avant d'envoyer une demande | limite d'export portée à 48 (`REWINDBOX_LEVERS_EXPORT_916`) | `rpcs3_freeze_chain916_test.py` (le Core 914 coupe 21 chiffres à 18) |
| Dump de Black Flag : douze threads dans `_sys_lwcond_queue_wait`, aucune ligne `lwcond` | les attentes étaient rattachées par `r3` des threads, que l'appel système a déjà remplacé par sa valeur de retour (`r3=0x0` dans le dump) | les attentes sont lues dans la file de la condition, sous son verrou (seulement tenté) ; ajout de `FREEZE_DUMP ppu_stack` : adresses de retour des threads en attente (`REWINDBOX_FREEZE_CHAIN_916`) | idem (parcours de file, chaîne de pile, cas dégénérés) |
| Les fenêtres de BO2 et d'AC1 absentes de l'export | 46 fenêtres « jeu arrêté » de 54 lignes ont rempli la rotation | une fenêtre arrêtée après la première garde `FRAMEPROF527` et une ligne `COREPROF IDLE916` (`REWINDBOX_IDLE_WINDOWS_916`) ; sur ce fichier : 1 577 669 → 242 244 octets (−84,6 %) | `rpcs3_collection916_test.py` |
| GOW3 : thread PPU principal saturé, aucun profil | la page Tests refuse un titre au profil personnalisé hérité (`legacy_custom=1`) | le rapport demande lui-même, une fois par démarrage, le profil PPU borné du Core 912 quand le thread PPU le plus chargé dépasse 0,85 cœur deux fenêtres de suite (`REWINDBOX_AUTO_PPU_PROFILE_916`, `trigger=auto_ppu_bound`) | idem |

En relisant le rapport pour la compaction : la sortie « jeu arrêté » du rapport ne rétablissait pas le niveau du
canal abaissé par le « profil de mesure allégé » ; elle le rétablit maintenant.

Ces corrections ne closent rien à elles seules : elles rendent possibles les tests décisifs de la section 6.

## 5. Ce qui n'est pas modifié, et pourquoi

- **Aucun réglage de jeu** : résolution, précision, limite d'images (AC1 garde son plafond natif de 30, BO2 n'est
  pas plafonné), nombre et priorités des SPU, délais GETLLAR/PUTLLC, options LLVM.
- **Textures et époques de GOW3** : `put_horizon=0` dans la session 5 parce que le profil hérité n'utilise pas la
  précision FIFO « Fast » dont dépend l'horizon ; aucun bénéfice de l'horizon ne peut être affirmé et rien n'y est
  changé. Garanties des Cores 909 à 911 intactes (tests 909, 910, 911 repassés sur le Core 916).
- **Passes d'AC1** : les lignes `RPASS652`/`RPASS655` de la session 3 ne sont pas dans les fichiers. Ce qui s'y
  trouve (`GPUTIME621` : GPU occupé 78 %, 36 à 46 ms d'exécution GPU sur les images lentes) désigne le GPU. Le
  mémo à 16 voies n'est pas modifié ; le Core 915 reste un témoin séparé.
- **Cache de code** : `SPUThread.cpp` change dans le corps hôte de `do_putllc` et gagne un `#include` ; aucun
  émetteur, signature ou disposition ne change. Un alias exact pour ce fichier précis, audité
  (`test/rpcs3_core916_codegen_test.py`) : identités PPU `a987639e9f838d1c` et SPU `477a3fa442d27917` inchangées.

## 6. Hypothèses restantes et prochain test décisif

| Sujet | État | Preuve disponible | Prochain test décisif |
|---|---|---|---|
| **Black Flag** (`BLES01882`, `accurate_res=true`) : arrêt de progression | **non résolu** | 391 flips, dernier flip à 28,261 s, FIFO GET = PUT, thread principal dans `_sys_lwcond_queue_wait` depuis 9,615 s, six SPU dans `MFC_Events_read` ; même forme que sur 694. Le lot 1 ne s'y applique pas (réservations précises). Le dump seul ne démontre pas une perte de réveil | un blocage avec le Core 916 : les lignes `lwcond` (file réelle, mutex, compteur d'attente) et `ppu_stack` disent quelle condition, qui devait la signaler et d'où. Puis A/B d'un seul réglage par essai : boucles PPU 128 octets, minuteries « As Host » |
| **GOW3** : que fait le thread PPU principal | inconnu | 0,931 cœur, GPU à 21 % | `PPUPROF912 trigger=auto_ppu_bound` (automatique) sur un démarrage à froid, MLAA contourné |
| **GOW3** : blocages en jeu | hypothèse | même chemin SPURS que le lot 1 (`accurate_res=false`) | `spurs_relaxed=…:refusés` non nul et disparition des blocages ; sinon dump avec les nouvelles lignes |
| **BO2** : fenêtres lentes (20 à 28 images/s, GPU ≈ 30 %) | cause non établie | seules les lignes `causes` existent ; compteurs CPU/SPU hors rotation | captures B1 et B3 du protocole, désormais déclenchables, ou profil automatique si le thread PPU sature |
| **AC1** : cadence irrégulière en jeu | limite GPU probable, non réduite | `GPUTIME621` | export contenant `RPASS652/655` de la scène (la compaction les préserve), puis comparaison 914/915 |

## 7. Protocole iPhone restant

Même appareil, même sauvegarde ou même parcours, mêmes réglages qu'avec 718 ; exporter les journaux applicatifs
après chaque essai (avec la rotation `.1`). Comparer aux mêmes scènes de 718.

1. **AC1** : jouer 2 min, quitter par le menu. Attendu : arrêt sans dump de blocage ; relever le temps entre la
   fermeture du menu et la fin de session, et `spurs_relaxed` des fenêtres de jeu.
2. **GOW3** : démarrage **à froid** (pas la restauration), rejoindre la scène de la sauvegarde. Vérifier
   `GOW3MLAA909 … ppu=applied ppu_patch=100`, relever `wall_guest_fps`, `p95_ms`, `ppu_cores`, `spu_cores`,
   `READBACK555 fault_read`, et le profil `PPUPROF912`. Refaire une sauvegarde d'état depuis ce démarrage.
   Contrôle visuel : image sans MLAA, sans autre différence.
3. **Black Flag** : jusqu'au blocage, attendre 40 s, exporter. Puis les deux essais A/B de la section 6.
4. **BO2** : scène lente de la session 2 ; captures B1/B3 (ouvrir puis fermer le menu, attendre 10 s).

À relever pour chaque essai : `wall_guest_fps`, âge du dernier flip, médiane/p95/p99/max, images au-delà de 50, 100
et 500 ms, durée des gels, CPU par thread, couverture GPU, textures/passes/soumissions/compilations, mémoire et
état thermique. Une valeur absente ou `-1` reste écrite telle quelle.

## 8. Vérifications exécutées (hôte)

Audit des identités de code (4 alias exacts), chaîne de repli, 13 gardes hôte de la liste Apple, pilote complet
`test/rpcs3_core916_test.py` (qui rejoue les tests des Cores 906 à 914 et les quatre tests 916, avec et sans
assainisseurs), test de l'analyseur avec des lignes 916. Compilation iOS, artefact et épinglage : voir
`build-utils/rpcs3/core-pin.json` et le cahier.
