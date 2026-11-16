# RPCS3 Core 935 et 936 — chauffe et consommation, correctifs issus des journaux de l'IPA 726 et d'ARMSX3

Demandes du mainteneur, 13 novembre 2026 : reprendre de l'IPA ARMSX3 0.0.2 (3) ce qui aide nos jeux, corriger à partir
des journaux iPhone (`PS3.zip`, IPA 723 à 726), puis mission unique : **réduire la chauffe et la consommation de RPCS3 sur
iPhone**, sans baisser la résolution, la qualité, les FPS ni la synchronisation PPU/SPU/RSX.

Statut : **écrit, contrôlé sur PC (syntaxe ARM64 et vérifications hôtes ciblées), compilé pour iOS par la route Core ;
rien n'a tourné sur un iPhone.** Aucune baisse de température n'est annoncée : les chiffres « avant » viennent de
l'appareil, les chiffres « après » sont des attentes à confirmer avec le protocole du §6.

## 1. Mesure de départ (IPA 726 = Core 933, `COREPROF ENERGY931`, fenêtres de 5 s, journaux privés hors Git)

Énergie = énergie CPU facturée par iOS au processus. Cœurs = temps CPU / temps réel. Appareil : 2 cœurs performance,
4 cœurs efficacité.

| Scène | FPS | Puissance CPU | dont cœurs P | mJ / image | Cœurs occupés (PPU / SPU / RSX) | Réveils / s (minuteries < 2 ms) | État thermique |
|---|---|---|---|---|---|---|---|
| Black Ops II, menus | 59,6 | 0,56 W | 0,51 W | 9,5 | 0,95 (0,12 / 0,60 / 0,10) | 47 250 (46 500) | correct |
| Black Ops II, en jeu | 40,2 | 2,89 W | 2,00 W | 72 | 4,62 (0,92 / 2,86 / 0,44) | 24 100 (23 400) | correct |
| Black Ops II, en jeu, plus tard | 37,1 | 2,45 W | 1,66 W | 66 | 4,93 (0,96 / 3,12 / 0,46) | 24 600 (23 800) | sérieux |
| Black Ops II **gelé** (bug du §2.1) | 0 | 2,61 W | 1,72 W | — | 5,36 (1,04 / 4,26 / 0,06) | 23 900 | sérieux |
| God of War III, écran léger | 54 à 58 | 0,84 à 1,10 W | 0,83 à 1,07 W | 15 à 21 | 0,39 à 0,54 | 77 600 à 80 600 | nominal, sérieux |
| God of War III, 60 FPS | 60 | 2,1 à 2,3 W | 2,1 à 2,2 W | 36 à 38 | 1,3 à 1,6 (0,6 à 0,9 / 0,4 / 0,1) | 50 400 à 56 400 | nominal à sérieux |
| God of War III, scènes lourdes | 17,3 | 2,30 W | 1,51 W | 137 | 4,62 (0,92 / 2,89 / 0,40) | 16 900 | sérieux |

Autres relevés des mêmes fenêtres : 42 000 à 89 000 changements de contexte et 42 000 à 90 000 appels système par
seconde ; 3 800 à 36 000 passages P ↔ E par seconde ; images de Black Ops II en jeu : médiane 25 à 29 ms, p95 36 à 38 ms,
p99 46 à 50 ms ; écritures disque régulières de 1,2 à 2 Mio par fenêtre (des rafales de 60 à 350 Mio existent aussi : lecture et
écriture y sont à peu près égales, ce ne sont pas des compilations de caches ; voir §8).

Ce que disent ces chiffres :

1. **En jeu, la dépense est le travail d'émulation** : 4,6 à 4,9 cœurs sur 6, dont 2,9 à 3,1 pour les six threads SPU.
   Le profil SPU (`SPUPROF923`, Black Ops II) montre des threads à 51 % en exécution et 49 % en attente (24 % sur
   GETLLAR, 20 % sur la boîte aux lettres), avec un code réparti sur plus de 350 adresses : pas de boucle unique à couper.
2. **Dans les écrans légers, la dépense est faite de réveils** : God of War III consomme 0,84 à 1,10 W avec moins d'un
   demi-cœur, pour 77 000 à 80 000 réveils par seconde, presque tous des minuteries de moins de 2 ms. Ce sont les threads
   SPU au repos : attente d'évènement bornée à 100 µs (`SPU_RdEventStat`, 97 % de leurs échantillons en `rdch_event`), ou
   file de travaux sondée toutes les 160 µs (Black Ops II : 181 000 sommeils de 152 µs en moyenne par fenêtre).
3. **Un jeu gelé consomme autant qu'un jeu qui tourne** : 5,4 cœurs et 2,6 W à 0 FPS pendant le gel de Black Ops II.
4. La mesure de latence des attentes WFE du Core 931 était fausse (`wfe_latency_us` dans le premier et le dernier
   intervalle seulement, `wfe_longest_us=18446744073`) : voir §2.5.

## 2. Correctifs qui servent la mission

| # | Marqueur | Source démontrée | Ce qui change | Portée |
|---|---|---|---|---|
| 1 | `REWINDBOX_FLIP_DONE_REPLAY_935` | Gel définitif de Black Ops II (IPA 723, 724, 726 ; PID 48320, 50194, 54406) : le thread `Backend` sonde le mot d'état du flip (0x40201100) pour toujours | Le jeu efface le bit « flip fait » après que le flip l'a déjà mis. Un flip qui trouve le bit déjà mis est rendu quand le jeu efface le bit dans les 250 ms | 6 numéros de Black Ops II |
| 2 | `REWINDBOX_SPU_IDLE_BACKOFF_935` | 47 000 à 80 000 réveils de minuterie par seconde dans les écrans légers | La borne de quatre attentes SPU au repos double après 8 attentes sans rien trouver (évènement : 100 → 800 µs ; file sondée : 160 → 640 µs). Les réveils par notification restent immédiats | Général, interrupteur existant |
| 3 | `REWINDBOX_NO_GDB_SERVER_935` (ARMSX3 d29f0afe) | Serveur de débogage GDB actif sur iPhone : une sonde toutes les 5 ms pendant toute la session | Serveur non démarré sur iOS (plus de port local ouvert) | Général |
| 4 | `REWINDBOX_CAMERA_IDLE_935` (ARMSX3 90a50f75) | Thread caméra : attente de 1 ms en boucle sans caméra | 100 ms quand aucun gestionnaire de caméra n'existe | Général |
| 5 | `REWINDBOX_EVENT_WAIT_COUNTER_935` | `"isb; mrs …"` : pour l'assembleur Apple, `;` ouvre un commentaire, le compteur n'était jamais lu | Lecture corrigée (et sans ISB : deux barrières de moins par WFE) | Mesure |
| 6 | Atomiques 16 octets (RPCS3 d4c236fc, b24a3229, 11bcaee2) | Core livré : 3 461 boucles LDAXP/STLXP, dont 2 128 simples lectures qui écrivent la ligne de cache, 0 CASPAL | Comparaison-échange en une instruction CASPAL, lectures et écritures LDP/STP (LSE2, garanti par la base armv8.4-a) | Général |

### 2.1 Le gel de Black Ops II
Dans les trois relevés de gel, `Backend` est à pc=0x716a54 dans une boucle `sys_timer_usleep(1000)` avec r9=0x40201100
(`RsxDriverInfo.head[1].flipFlags`), le thread principal attend un sémaphore, le RSX tourne sur un saut d'attente dans la
liste de l'image suivante, et les six threads SPURS sondent une file vide. Le jeu rend la commande de flip visible, puis
efface le bit (attribut 0x10a), puis l'attend. Sur PS3 le flip se termine à un retour de balayage, des millisecondes plus
tard ; ici le RSX le termine en quelques dizaines de microsecondes. Si `Backend` est retenu entre ses deux étapes, le flip
trouve le bit encore mis, puis l'effacement le retire. Le correctif mémorise ce flip (le deuxième depuis que le bit a été
vu à zéro) et remet le bit quand le jeu l'efface dans la fenêtre. Un titre qui efface avant de soumettre, ou qui n'efface
jamais, ne voit aucun changement. `FREEZE_DUMP rsx` publie `flip_flags= flip_replay= flip_absorbed= flip_replays=`.

### 2.2 Les attentes SPU au repos
La borne est un filet de sécurité : une écriture qui passe par une réservation réveille le dormeur tout de suite ; seule
une écriture ordinaire, ou une notification que le PPU a différée, est trouvée par le regard qui suit la borne. Le
correctif se contrôle lui-même, par thread : si ce que le thread attend est trouvé juste après une borne allongée, c'est
que la notification ne l'a pas porté ; le thread garde alors la borne de référence pendant 256 attentes, puis 512, …
jusqu'à environ un million. Une attente qui dépend du sondage revient donc au rythme d'avant ; chaque essai coûte au plus
un évènement en retard de moins de 0,7 ms. Réglage « Event Waits When Hot » sur Désactivé : tout est coupé. La
comparaison entre fenêtres du Core 931 pilote aussi ce levier. `THERMAL931` publie en fin de ligne
`spu_idle_backoff= spu_idle_lengthened_waits= spu_idle_late_finds=`.

## 3. Autres correctifs du lot (stabilité et rendu, sans lien avec l'énergie)

- `REWINDBOX_CANARY_PATCHES_935` : fichier de patchs de l'IPA ARMSX3 0.0.2 (3) ; deux patchs Black Ops III (BLES02166
  01.06 et 01.07, « profile load freeze fix ») actifs par défaut comme chez ARMSX3 (GPL-2.0, source publique).
- `REWINDBOX_ATOMIC_DMA_LINE_935` (RPCS3 82aaf08c, adapté) : un GET d'une ligne entière ne peut plus lire une ligne à
  moitié écrite ; un PUT d'une ligne entière est atomique **avec les réservations relâchées seulement** (avec les
  réservations exactes il prendrait le verrou d'écriture global à chaque PUT : coût non mesuré, non porté).
- RPCS3 officiel : cinq bogues d'état RSX d'une ligne (be7f357b, ac5c0e5a, 2dca003b, 048a59ec, c1b25a79), blits et draws
  perdus et clés de cache (7678217f, 23d28a4a, b3e3df36, a62b83de, 5a5f117a), drapeau d'attente autour des
  allocations HLE (7ae11e2e, 177deabd, 0991bacc), tri des sauvegardes (5dddfc03), lecture d'ISO (320c29a1, 556ed8d1,
  d540513e), vue de texture avec le mauvais remappage (85be81f0, f559420b, adapté à notre clé de cache), shaders float16
  (8b9a90a3, 2cef90e6), arrondi F32 → D24 (5eca8ab3), `tile.bank` (9b8974d3), état des passes SPU remis à zéro par
  compilation (965f4f58), FNID des patchs (de964191), journal RawSPU (90d8264e), effacement sans tampon de profondeur
  (a296c261).

Identités de génération de code inchangées (PPU `a987639e9f838d1c`, SPU `477a3fa442d27917`) : les caches PPU et SPU des
joueurs sont conservés. ABI 30 et 92 exports inchangés.

## 4. Bilan par correctif (attendu, à confirmer)

| # | Coût supprimé | Gain attendu | Risque |
|---|---|---|---|
| 1 | 5,4 cœurs et 2,6 W à 0 FPS pendant le gel, plus la partie perdue | Certain si le gel disparaît ; **le gel lui-même reste à vérifier sur l'appareil** | Titre seul ; un flip rendu à tort est borné à 250 ms après un flip réel |
| 2 | Jusqu'à 7 réveils sur 8 des threads SPU au repos (4 sur 5 pour une file sondée) | Écrans légers : de 47 000-80 000 vers 10 000-20 000 réveils/s ; la puissance de ces scènes (0,5 à 1,1 W) devrait baisser nettement, sans chiffre garanti. En jeu (17 000 à 24 000 réveils/s, threads rarement au repos) : faible | Un évènement non notifié arrive au plus 0,7 ms plus tard, puis le thread reste à la référence |
| 3 | ~200 réveils/s en permanence | Très faible, mais présent même en pause | Aucun (pas de débogueur sur iPhone) |
| 4 | ~1 000 réveils/s en permanence | Faible | Évènement « caméra absente » au plus 100 ms plus tard |
| 5 | 2 ISB par WFE (~730 000 WFE/s à chaud en jeu) | Faible ; rend `wfe_latency_us` exploitable | Aucun |
| 6 | Une écriture de ligne de cache par lecture atomique de 16 octets, boucles de reprise | Non mesuré ; touche les verrous de réservation (325 000 PUTLLC lourds/s dans Black Ops II) | Code sous tout le moteur ; livré par ARMSX3 depuis le 29 septembre et par RPCS3 depuis octobre |

## 5. Ce qui n'est pas fait, et pourquoi

- **Le travail SPU/PPU en jeu** (4,6 à 4,9 cœurs) : aucune dépense évitable démontrée par ces journaux ; le réduire
  demanderait de changer la précision des réservations, le nombre de threads SPU ou la cadence, exclus par la mission.
- Verrou d'écriture des PUTLLC exacts (325 000/s, 13 % d'un cœur de parcage PPU dans Black Ops II) : aucun saut
  supplémentaire sûr (voir Core 930).
- Compilations Metal de nouveaux shaders en jeu (350 à 985 ms) : premières rencontres, hors caches ; le mode asynchrone
  reste coupé (règle du projet).
- Attentes audio, tranches du parcage RSX, passages P ↔ E (20 000/s) : pas de mesure qui isole leur coût.
- Écritures disque régulières de 1,2 à 2 Mio par fenêtre : origine trouvée et corrigée ensuite, voir §8.
- ARMSX3 non repris : FNMADD/FNMSUB exacts (ralentit le PPU, recompile tous les caches), repli de profondeur pour tous les
  titres (recompile tous les shaders), plafond des tampons Vulkan et gestion de VRAM pleine (à faire à part), liste
  blanche PUTLLC16, shaders asynchrones (interdit), « Preferred SPU Threads 2 » pour Black Ops II, garde MGS4, PSF plus
  strict (66f94a1b : rejetterait des fichiers lus aujourd'hui). Ils ne servent pas la mission énergie.
- RPCS3 20ce0fa6 (draw d'un seul point indexé ignoré) : non repris, `VKVertexBuffers.cpp` est une entrée « fichier entier »
  d'un contrôle réutilisé du Core 610 (`vertex-range`) ; le reprendre demanderait de rejouer ce contrôle.

## 6. Protocole d'appareil (comparaison avant / après)

Même iPhone, luminosité fixe, débranché, batterie au-dessus de 50 %, appareil froid (5 minutes d'écran éteint), mêmes
réglages de jeu, caches de shaders déjà remplis (faire le parcours une fois avant de mesurer).

1. **Écran léger** : God of War III, menu principal, 2 minutes ; Black Ops II, menu multijoueur, 2 minutes. Lire
   `ENERGY931` : `interrupt_wakeups`, `timer_wakeups_2ms`, `cpu_energy_mj`, `mj_per_frame`, et `THERMAL931` :
   `spu_idle_lengthened_waits`, `spu_idle_late_finds`. Référence 726 : tableau du §1.
2. **Jeu** : Black Ops II multijoueur 10 minutes (même carte), God of War III même passage 5 minutes. Lire W, mJ/image,
   FPS, médiane/p95/p99 des images, minutes avant l'état « sérieux » (`ms_fair`, `ms_serious`).
3. **Gel** : jouer à Black Ops II jusqu'au moment habituel du gel ; s'il revient, exporter : `FREEZE_DUMP rsx` dit si le
   bit était effacé (`flip_flags`) et si un flip a été rendu (`flip_replays`).
4. **A/B dans la même session** : « Lever Comparison Between Report Windows » sur Activé ; l'analyseur
   (`tools/rpcs3/capture_analyzer.py`) compare alors l'énergie par image avec et sans attentes allongées dans un même état
   thermique.
5. Son et entrées : vérifier à l'oreille l'absence de craquement dans les menus (les attentes allongées ne touchent pas le
   thread audio).

## 7. Vérifications effectuées (PC)

- Contrôle de syntaxe de chaque fichier C++ modifié avec clang 18, cible ARM64, libc++, `-DRPCS3_IOS` (les blocs
  `__APPLE__` et les fichiers qui incluent LLVM 21 ne sont pas couverts). Il a trouvé et fait corriger deux erreurs de
  compilation avant la CI.
- Vérifications hôtes jetables (hors dépôt) : automate du flip rendu (g++ et ThreadSanitizer), automate des attentes
  allongées (ASan/UBSan) : 0 échec.
- Identités de génération de code recalculées : inchangées. Contrôle de fermeture des sources de la route Core.
- Tests non exécutés : suites hôtes historiques du Core (règle du dépôt : compilation seule), aucun essai sur iPhone.

## 8. Second lot (Core 936 et pont iOS) : les points restants de la mission, un par un

Ordre du mainteneur, 13 novembre : finir tous les points restants avant toute IPA RPCS3. Cinq enquêtes sur les mêmes
journaux et sur le code du Core 935. Chaque point a maintenant un verdict : corrigé, non évitable (avec la preuve), ou à
mesurer sur l'appareil (avec la sonde ajoutée pour cela).

| Point | Ce que les journaux mesurent | Verdict |
|---|---|---|
| Écritures disque | 1,2 à 1,9 Mio écrits par fenêtre pour ~67 Kio de texte de journal ; écritures = 18,6 Kio × lignes + 221 Kio (R² 0,99 sur 55 fenêtres), ~1,15 Gio par heure | **Corrigé** (pont iOS, `REWINDBOX_LOG_APPEND_HANDLES_936`, commit e5ecdfac0) : `appendLine:` ouvrait, écrivait et fermait le fichier à chaque ligne de trois journaux ; ils restent ouverts. Effet attendu sur la chauffe : faible ; non mesuré |
| Pré-hachage de textures, God of War III à 60 FPS | L'ouvrier hache 0,87 à 0,96 Go par fenêtre pour 0 résultat servi (52 à 62 ms de CPU) | **Corrigé** (`REWINDBOX_PREHASH_IDLE_936`) : pause de 120 images après trois périodes sans usage ; scènes lourdes inchangées. Gain attendu 17 à 94 ms de CPU par fenêtre |
| Pré-hachage en scènes lourdes | 277 à 624 ms d'ouvrier par fenêtre pour 23 à 116 ms épargnés au RSX | À mesurer : le couper peut allonger une image de 0,2 à 1,6 ms. A/B « Texture pre-hash » sur la même scène |
| Hachage des textures par le RSX (God of War III lourd) | 9 à 27 ms par image, ~la moitié du CPU RSX ; 88 à 99 % confirment des octets inchangés | Non évitable : pas de protection de pages sur iOS, les points de synchronisation sont de vraies publications du jeu |
| Soumissions, attentes CPU-GPU, cadencement | 5 à 10,5 soumissions par image à 10 µs ; aucune attente active ; présentations = flips du jeu, jamais plus de 60,2/s | Rien d'évitable |
| Shaders recompilés d'une session à l'autre | Trois caches concordent, `repeated_builds` = 0 sur 11 sessions ; cache pilote inchangé sur 15 démarrages | Non : premières rencontres. Coût en énergie non démontré (fenêtre des 8 compilations : 10,1 J contre 11,8 à 13,0 J) : c'est une saccade |
| Recompilation PPU/SPU | 36 démarrages sur 37 sans module compilé ; chaque bloc SPU compilé une fois | Rien à corriger |
| Démarrage de Black Ops II (12 à 14 s, 2 cœurs) | Relecture de 22 856 objets SPU, cœurs efficacité, 8 à 9 J | Travail réel, hors jeu ; non retenu |
| Réveils restants | Parcage RSX estimé à 4 900-8 200/s en jeu et 14 000-17 000/s en écran léger (aucun compteur) ; 27 à 54 % des 23 500 minuteries/s de Black Ops II sans site | À mesurer : `COREPROF WAKE936` (`REWINDBOX_WAKE_CENSUS_936`) compte les attentes minutées des PPU invités, les tranches du parcage RSX et les sondages ZCULL. Allonger la tranche de 50 µs retarderait chaque début d'image (PUT jamais notifié) |
| Audio, manette | 187 attentes/s (une par bloc) ; 880/s | Non touchés (son et entrées) |
| Passages P ↔ E | 2 700 à 3 800/s à 80 000 réveils/s, 18 500 à 21 100 en jeu : ils suivent la surcharge des deux cœurs P | Rien de possible proprement sur iOS (ni affinité ni choix de grappe ; QoS déjà réglée) |
| Verrou d'écriture des réservations exactes (Black Ops II) | 427 ns par prise, 321 000/s ; coût hôte imputable ≈ 0,24 cœur sur 4,81 (4,9 %) ; God of War III lourd 0,07 cœur | Rien de supprimable dans le chemin (aucune dépense au-dessus de 0,25 %) |
| Mode exact de Black Ops II | Le mode relâché supprimerait par fenêtre 1,64 M prises, 768 000 parcages PPU, 3 180 reports ; la raison d'origine (gel lu comme mise à jour perdue) ne tient plus | À mesurer, sans build : flip corrigé en mode exact d'abord, puis la même carte en relâché par le réglage par jeu |
| Thread principal de God of War III à 60 FPS | Facturé 0,6 à 0,9 cœur performance, « en exécution » dans 4,4 à 4,8 % des échantillons ; 89 % en attente hors appel nommé ; IPC ≤ 0,4 | Dépense démontrée, lieu inconnu. À mesurer : `REWINDBOX_PPU_WAIT_SITE_936` ajoute drapeaux, dernier appel et pc de ces attentes au profil PPU |
| Mémoire, allocations, copies | Compression 4 à 5,6 Mio/s (< 1,1 % d'un cœur, estimé), marge ≥ 3 071 Mio, aucun tampon par draw | Rien d'évitable. Allocations GPU de God of War III lourd (13 à 46 Mio par image) : coût non démontré |
| Assassin's Creed, AC IV, Bladestorm | Aucune sonde d'énergie dans les journaux (IPA 718 et incidents) ; Assassin's Creed : GPU occupé 75 à 83 % | Énergie jamais mesurée : menu 2 min puis jeu 5 min avec un Core ≥ 931 |
| Limiteur d'images (thread RSX) | Lecture du code : sur iOS le reste d'attente sous 500 µs est fait en `yield` puis en attente active (≈ 2 % d'un cœur à 60 FPS, estimé) | Non touché : le remplacer par un sommeil risque une image en retard ; gain trop petit pour ce risque |

Ce qui reste donc ouvert ne peut se fermer qu'avec une session sur l'iPhone : le thread principal de God of War III à
60 FPS, le parcage RSX, le mode de réservation de Black Ops II, le pré-hachage en scènes lourdes, et l'énergie des trois
autres jeux. Les sondes nécessaires sont dans le Core 936 ; elles ne changent aucune attente.

## 9. Journaux de l'IPA 737 (14 novembre) : avant / après, et Core 937

Journaux privés hors Git, IPA 737 = Core 936. Sessions : Black Ops II (PID 4302, session 2 : environ 80 s de jeu, puis
gel de 95 s, puis arrêt ; deux sessions plus courtes, PID 3973 et 4302 session 1) ; God of War III (PID 4076, session 2 :
2 min 30 de jeu lourd, **reprise d'une sauvegarde d'état**). État thermique « fair » puis « serious ». Comparaison avec
l'IPA 726 phase par phase (fenêtres de 5 s, `COREPROF ENERGY931`, `SPUWAIT551`, `COREPROF WAKE936`).

| Mesure | IPA 726 | IPA 737 | Lecture |
|---|---|---|---|
| Écritures disque, Black Ops II, menus | 1,45 à 1,64 Mio par fenêtre | 0,13 à 0,18 Mio | **−89 %, mesuré** (journaux gardés ouverts, e5ecdfac0). Les rafales au démarrage du jeu restent |
| Réveils de minuterie < 2 ms, Black Ops II, menus | 44 000 à 49 000/s | 45 700 à 48 000/s (session 1 : 53 600 à 64 500) | **Inchangé** |
| dont attentes d'un SPU qui sonde (compteur `getllar_sleeps`) | 35 000 à 36 300/s | 35 000 à 38 000/s | **Corrigé au §10** : ce sont surtout les attentes après un PUTLLC qui n'écrit rien (Cores 627/911), pas l'attente GETLLAR de 100 µs ; la règle du Core 935 ne s'y déclenche jamais dans les menus |
| dont parcage RSX (nouvelle sonde) | — | 7 000 à 9 400/s | Tranches de 50 µs ; non touché (allonger retarde chaque début d'image) |
| dont attentes minutées des PPU invités | — | 3 000 à 3 400/s | Demandées par le jeu ; non touchées |
| Black Ops II en jeu | 2,54 W, 4,72 cœurs, 100 mJ/image à 35 FPS | 2,23 à 2,94 W, 4,4 cœurs, 86 à 95 mJ/image à 26 à 34 FPS | Pas de différence démontrable (scènes différentes) |
| Black Ops II, menus : puissance CPU | 0,46 à 0,60 W pour ~1 cœur | 0,83 à 2,68 W pour 0,5 à 1,8 cœur | **Plus haut pour le même temps CPU** (fréquence plus haute). Cause non établie : GPU occupé 6 à 11 % contre 23 à 46 % (écran de menu peut-être différent), état thermique différent. À vérifier par A/B dans la même session (§6) |
| Black Ops II, gel | 2,65 W, 5,4 cœurs, 0 image | 2,2 à 2,6 W, 5,0 cœurs, 0 image, 95 s | **Le gel reste** (voir plus bas) |
| God of War III lourd | 2,42 W, 120 mJ/image, 70 000 à 96 000 PUTLLC/s | 2,38 W, 158 à 168 mJ/image, 0,7 à 1,7 million de PUTLLC/s dont 330 000 échecs/s | Session reprise d'une sauvegarde d'état faite sans la dérivation MLAA (`GOW3MLAA909 ppu=savestate_memory savestate_patched=0`) : le MLAA tourne sur les SPU. Voir plus bas |

**Gel de Black Ops II : la cause proposée au §2.1 est réfutée.** Le relevé de la 737 montre `flip_flags=0x40000003`
(bit « flip fait » absent), `flip_absorbed=0` et `flip_replays=0` : aucun flip n'a été absorbé pendant les 2 935 images de
la session, le correctif `REWINDBOX_FLIP_DONE_REPLAY_935` n'a jamais eu à agir. Le RSX est arrêté sur un saut sur
lui-même dans une liste de commandes en flux (`get=0x83fa5a0`, `last_cmd=0x283fa5a0`) et n'a donc jamais atteint le flip
suivant ; le thread `Backend` attend ce flip. Ce qui tourne : le thread PPU `Secondary` (0,96 cœur, boucle CAS sur la tête
d'une file de travaux, `pc=0x73ccdc`) et les six SPU de SPURS dans le code de la file de travaux (GETLLAR/PUTLLC sur
0x2e20880, 0x2e20c00, 0x2e20500 ; 1,9 million de PUTLLC/s). Même signature que les gels des builds 624, 657, 723, 724,
726 et 736. Lecture : un interblocage dans le gestionnaire de travaux du jeu, du même genre que celui de Black Ops III
documenté par ARMSX3 (deux types de travaux qui se renvoient en file l'un l'autre ; correctif ARMSX3 = patch du code du
jeu). Le code du jeu n'est pas disponible ici : pas de correctif possible sans lui. Le correctif 935 est gardé (inoffensif,
limité à Black Ops II) mais ne corrige pas ce gel. ARMSX3 livre pour BLES01717 le réglage « Preferred SPU Threads: 2 »
sans explication publique ; ARMSX3 a aussi constaté sur Killzone 3 qu'une telle limite peut faire apparaître d'autres
courses : c'est un essai par jeu, pas un correctif.

**God of War III.** Le §929 a choisi de ne pas écrire la dérivation MLAA dans la mémoire d'une sauvegarde d'état faite sans
elle (image cassée sinon). Une sauvegarde d'état faite après un démarrage normal la contient (`savestate_patched=1`). Les
10 à 20 fois plus de PUTLLC et les 330 000 échecs par seconde de la 737 n'ont été vus que dans cette session reprise ; le
lien avec le MLAA est probable mais non démontré (une seule session).

**Thread principal de God of War III** (sonde `REWINDBOX_PPU_WAIT_SITE_936`) : 55 % des échantillons en exécution, 22 %
dans `sys_timer_usleep` (demandé par le jeu), 19 % suspendus par les opérations mémoire exclusives des réservations
exactes (`suspend` 348, `memory` 592 échantillons) ; les parcages mesurés ne font que ~3 % du temps (courts). Ce n'est pas
une attente active coûteuse : rien à corriger.

### Core 937 : `REWINDBOX_SPU_IDLE_BACKOFF_937`

L'attente de 100 µs d'un GETLLAR qui sonde une ligne inchangée suit la même règle auto-vérifiée que les attentes du
Core 935 : 100, 200 puis 400 µs tant qu'elle va au bout sans rien trouver ; une écriture qui notifie la ligne la termine
toujours aussitôt ; un changement trouvé juste après une attente allongée ramène 100 µs pour un nombre d'attentes qui
double à chaque fois. Désactivée avec « Event Waits When Hot » = Disabled, comme la règle 935. Le corps de
`process_mfc_cmd()` est une entrée figée d'un banc de test réutilisé (porte de la route Core) : il garde ses octets du
Core 610. La borne est donc choisie autour de lui : le chien de garde MFC compte la commande en cours,
`register_cache_line_waiter()` (appelée juste avant cette attente) pose une borne à usage unique que
`atomic_wait_engine::wait()` ne prend que pour un délai d'exactement 100 µs (`ios/IOSAtomicWaitBound937.h`),
`deregister_cache_line_waiter()` (juste après) comptabilise l'attente et signale une ligne changée.

Effet attendu dans les menus de Black Ops II : de 35 000-38 000 à environ 9 000-12 000 attentes GETLLAR par seconde, soit
de ~48 000 à ~20 000 réveils de minuterie par seconde. Effet sur la puissance et la température : **inconnu tant que ce
n'est pas mesuré sur l'iPhone**. En jeu, ces attentes sont rares (400 à 2 200/s) : pas d'effet attendu.

**Correction (journaux de l'IPA 745, 15 novembre) : cet effet attendu ne s'est pas produit, et il ne pouvait pas se
produire.** Dans les menus, les 37 700 à 38 300 attentes par seconde mesurées sur la 745 ne sont pas l'attente GETLLAR de
100 µs : ce sont les attentes de 150 µs après un PUTLLC qui n'écrit rien (Cores 627/911), comptées par le même compteur.
La borne du Core 937 n'y est jamais armée. Le Core 937 est gardé (il est juste, et sans effet ailleurs) ; la suite est au
§10.

Vérifié sur PC : syntaxe ARM64 des deux fichiers C++, contrôle hôte jetable de la séquence (borne 100 → 200 → 400 µs,
remise à zéro sur notification, maintien à 100 µs après une trouvaille tardive, aucune fuite vers une autre attente ;
ASan/UBSan), identités de génération de code recalculées (PPU a987639e9f838d1c, SPU 477a3fa442d27917, par un alias
exact), porte de la route Core (code 0), correctif canonique re-matérialisé octet pour octet (498 fichiers), étape Metal
du workflow. Non exécutés : bancs historiques, compilation iOS de ce lot (demandée à la route Core), appareil.

### Core 938 : les points laissés de côté (demande du mainteneur, 14 novembre : « finis ce que tu n'as pas touché »)

| Point | Verdict |
|---|---|
| Parcage RSX pendant un long repos | **Corrigé** (`REWINDBOX_RSX_LONG_IDLE_938`) : après 250 ms de FIFO vide sans interruption, la tranche de parcage passe de 50 µs à 1 ms. Gel de Black Ops II : 16 600 réveils/s pour rien (83 348 tranches par fenêtre) ; chargement de God of War III : 9 600/s. Attendu : ~1 000/s dans ces états. Aucun jeu ne laisse son RSX inactif 250 ms entre deux salves en jouant (moins de 4 images/s) ; le premier PUT après un tel repos est vu au plus 1 ms plus tard ; vidage, flip et ZCULL réveillent toujours aussitôt. En jeu et dans les menus (repos de 2 à 10 ms par image) : inchangé |
| Gel de Black Ops II | **Pas corrigeable sans le code des travaux du jeu.** `REWINDBOX_FREEZE_SPU_MEMORY_938` (mesure seulement) : un gel « occupé » de 20 s écrit une fois par démarrage la mémoire locale et les registres de chaque SPU dans `Documents/Diagnostics/PS3/RPCS3-freeze-spu.bin`, à côté des journaux (environ 1,5 Mio). C'est là que se trouve la vérification de dépendance que les travaux renvoient en file sans fin ; avec ce fichier, un correctif du jeu du même type que celui d'ARMSX3 pour Black Ops III peut être écrit. Écartés : ralentir les SPU pendant un gel (un long chargement sans image serait pris pour un gel), la piste ZCULL du ticket RPCS3 #13602 (pendant le gel de la 737, aucune lecture de rapport ZCULL : `faults=0`, `waits=0`) |
| Limiteur d'images et fil VBlank | **Correction du §8** : il n'y a pas d'attente active. Sur iOS, « Sleep Timers Accuracy » vaut « As Host » : le limiteur dort par `lv2_obj::wait_timeout` sans boucle ; le fil VBlank dort aussi le reste sous 500 µs ; `fifo_wake_delay` ne sert qu'avec un « Driver Wake-Up Delay » non nul (0 par défaut). Rien à corriger |
| Minuteries courtes des PPU du jeu (3 000/s dans les menus, 15 000/s en jeu, moins de 200 µs) | Demandées par le jeu ; avec « As Host » elles dorment déjà sans boucle. Les allonger changerait le temps du jeu : non touchées |
| God of War III repris d'une sauvegarde d'état | Pas de correctif sûr dans le Core (écrire la dérivation dans une mémoire restaurée casse l'image, §929). Action sans build : démarrer le jeu normalement, charger la partie, refaire une sauvegarde d'état |
| Menus de Black Ops II plus coûteux par seconde de CPU dans la 737 | Cause non établie (fréquence plus haute ; écran de menu peut-être différent) : A/B dans la même session avec « Event Waits When Hot » |

Vérifié sur PC pour le Core 938 : syntaxe ARM64 de `RSXFIFO.cpp`, `RSXZCULL.cpp` et `RPCS3IOSFreezeDump.cpp` (le rapport `RPCS3IOSPerformance.cpp` dépend d'en-têtes Apple ; l'appel ajouté a été relu contre `RPCS3IOSFreezeEpisode.h`), identités de génération de code inchangées (PPU a987639e9f838d1c, SPU 477a3fa442d27917), porte de la route Core (code 0), correctif canonique re-matérialisé octet pour octet (498 fichiers), étape Metal du workflow. Non exécutés : bancs historiques, appareil.

## 10. Journaux de l'IPA 745 (15 novembre) et Core 939

Journaux privés hors Git, IPA 745 = Core 938. Black Ops II (PID 9077, sessions 1, 2, 4 et 5) et God of War III
(session 3). État thermique « serious » presque tout le temps. Le mainteneur précise : pas d'anomalie graphique, surtout de
l'instabilité. Priorité donc aux gels et aux à-coups, puis à la régularité des images.

| Constat (mesuré) | Cause | Suite |
|---|---|---|
| Black Ops II en partie (session 5) : **chaque image de plus de 100 ms est la première construction d'un pipeline graphique**. 51 constructions, 23,9 s, 19 % du match ; médiane 516 ms, dont 88 % dans la compilation Metal de la bibliothèque du fragment shader ; chaînes jusqu'à 18 constructions (9,3 s sans image : le « gel » de la session 5) | Mode « Legacy Recompiler » : le fil RSX attend chaque construction, le jeu s'arrête. Les caches marchent (rien n'est compilé deux fois, ils survivent aux mises à jour) : ce sont de vraies premières rencontres | **Core 939 : mode asynchrone** (décision du mainteneur) |
| Cache MoltenVK de Black Ops II : 126 279 131 octets, **94 % de la limite de 128 Mio** (45 bibliothèques ajoutées en une session, ~39 ko chacune) | Au-delà de la limite, la sauvegarde est refusée : les nouvelles bibliothèques ne seraient plus gardées et les à-coups reviendraient à chaque partie | **Core 939 : limite 256 Mio** |
| Première analyse GLSL d'une session : 140,4 ms, 136,5 ms et 55,3 ms sur le fil RSX en jeu, contre 5 à 9 ms ensuite | glslang construit ses tables de symboles intégrés au premier shader « #version 450 » | **Core 939 : préchauffage au démarrage** |
| **Le vrai gel de Black Ops II** (session 2, flip 1960) | Le gestionnaire de travaux du jeu tourne en rond : les sept travailleurs (thread PPU « Secondary » et six noyaux SPURS) reprennent un travail, voient qu'il ne peut pas encore tourner et le remettent en file ; la tête de la réserve de nœuds (0x2e208a0) avance, la somme des compteurs en file / en cours reste la même. Même forme que Black Ops III (corrigé par ARMSX3 par un patch du jeu). Causes émulateur examinées et réfutées. Aucun réglage par jeu défendable | **Core 939 : capture de la mémoire du jeu à 3 s** ; le patch du jeu suivra |
| Black Ops II en partie : 33 ms par image à ≥ 2,0 GHz, 50 ms quand iOS bride les cœurs P à 1,6-1,8 GHz (p95 35-36 ms contre 50,5 ms) | Le jeu est limité par le CPU invité sur les deux cœurs P (93 % occupés) ; 572 millions d'instructions par image, comme sur la 726 : **pas de régression du moteur** | Pas de correctif dans le Core. Essai sur l'iPhone : « Accurate SPU Reservations » désactivé pour Black Ops II (12 300 verrous d'écriture par image ; PPU parqué 5,5 ms par image) |
| Menus de Black Ops II : 37 700 à 38 300 attentes SPU par seconde | Attentes après un PUTLLC qui n'écrit rien (correction du §9) ; la règle du Core 935 demande ~2 ms de silence et ne se déclenche jamais (les six threads repartent toutes les ~1,2 ms) | Voir le correctif de chauffe ci-dessous |
| Placement des threads et politique thermique | Déjà justes : les SPU sont sur les cœurs E ; la seule vraie attente active sur les cœurs P est le parcage du PPU (0,166 cœur) | Rien à changer |
| God of War III | Sauvegarde d'état faite sans la dérivation MLAA (§9) | Démarrer normalement, puis refaire une sauvegarde d'état |

### Core 939 : le lot

**`REWINDBOX_ASYNC_SHADERS_939` (mode asynchrone, décision du mainteneur du 15 novembre).** Le mode par défaut sur iOS
devient « Async Recompiler » : la construction d'un pipeline se fait sur le fil de travail RSX.W et le jeu continue ; les
dessins qui ont besoin d'un pipeline encore en construction sont sautés jusqu'à ce qu'il soit prêt (un objet peut
apparaître un instant en retard la première fois qu'il est rencontré). L'étape GLSL vers SPIR-V reste sur le fil RSX (les
12 % restants). Les pipelines déjà construits, le cache disque et son préchargement au démarrage ne changent pas. Un jeu dont
la base RPCS3 fixe un autre mode le garde (28 titres « Legacy Recompiler » aujourd'hui) et le choix du joueur pour un jeu
passe toujours en dernier. RPCS3 écrit tous les réglages dans `config.yml` : une installation existante garde donc
l'ancienne valeur ; une migration unique la remplace au premier lancement (« Legacy Recompiler » devient « Async
Recompiler », toute autre valeur reste ; un marqueur à côté de `config.yml` empêche de la refaire, un choix global ultérieur
est donc respecté ; ligne de journal `REWINDBOX_ASYNC_SHADERS_939`). L'interpréteur de shaders n'est pas un défaut.

**`REWINDBOX_PIPELINE_CACHE_LIMIT_939`.** Limite du cache MoltenVK sauvegardé : 256 Mio au lieu de 128 (l'en-tête du fichier
garde la taille sur 32 bits). Effet visible seulement quand le cache aurait dépassé l'ancienne limite.

**`REWINDBOX_GLSLANG_PREWARM_939`.** Un shader de fragment vide « #version 450 » est compilé une fois, sur son propre
thread, pendant le démarrage du rendu ; le thread est attendu avant la fermeture de glslang. Sur PC (même glslang) : après
lui, le premier shader 450 suivant prend 0,5 à 1,0 ms au lieu de 96 à 118 ms.

**`REWINDBOX_FREEZE_GUEST_939` (mesure seulement).** Au premier relevé d'un épisode « occupé sans image » (3 s ; les
joueurs arrêtent le jeu après 8 à 11 s, bien avant les 20 s de la capture du Core 938), si le relevé a la signature du gel
de la file de travaux (FIFO RSX sur un saut sur lui-même hors d'un dessin, un thread PPU dans le code du jeu, deux SPU sur
la même ligne ; Black Ops II seulement depuis la demande 2), le Core écrit `Documents/Diagnostics/PS3/RPCS3-freeze-guest-<n>.bin` : les lignes de la file et ce qu'elles
désignent (enregistrements des types de travaux, images des travaux, noms), les commandes RSX autour de GET, le code, la
pile et les registres du thread qui tourne, les registres de chaque PPU, les mémoires locales des SPU. Un fichier
numéroté par capture (jamais écrasé), au plus 16 Mio de mémoire du jeu plus 1,6 Mio de mémoires locales, quatre captures
par démarrage ; une ligne `FREEZE_DUMP guest_memory` dit ce qui a été écrit ou pourquoi rien ne l'a été. Rien n'est écrit
dans la machine émulée. C'est ce fichier qui permet d'écrire le patch du jeu.

### Core 939 : la chaleur (demande du mainteneur, 16 novembre : « le téléphone doit rester en mode nominal », menus et jeu)

Ce que disent les journaux de la 745 (fenêtres de 5 s, `ENERGY931` et `THERMAL931`, état « serious » tout le long) :

| Phase de Black Ops II | Travail CPU | Puissance CPU | dont cœurs P | Part du temps sur les cœurs P |
|---|---|---|---|---|
| Menus à 60 images/s | 0,47 à 1,44 cœur | 1,32 à 2,37 W | 1,29 à 2,18 W | 60 à 77 % |
| Partie (25 à 37 images/s) | 4,7 à 4,9 cœurs | 1,8 à 1,9 W | 1,2 à 1,3 W | 37 à 39 % |

**Les menus coûtent autant ou plus que la partie, pour cinq fois moins de travail.** iOS y fait tourner les cœurs P à 3,6-3,96
GHz (contre 1,7 GHz pour le même menu sur l'IPA 726, 0,46 à 0,60 W) ; les six threads SPU qui sondent la file de travaux du
jeu (0,29 à 0,86 cœur) y sont réveillés sur des cœurs P inoccupés, 38 000 fois par seconde. C'est souvent là que le
téléphone passe en « serious », avant même le match. En partie, au contraire, iOS donne une enveloppe d'environ 1,25 W aux
cœurs P : le temps CPU qu'on leur retire y revient en fréquence (images plus rapides) plutôt qu'en chaleur.

Ce que le lot change :

- **`REWINDBOX_SPU_POLL_IDLE_939`** (menus) : un thread SPU est « au repos » après huit attentes de suite sans prendre de
  travail ; les écritures faites pendant son sommeil ne relancent plus son sondage, et son attente s'allonge à 320 puis
  640 µs. Une écriture qui notifie la ligne le réveille toujours aussitôt ; une trouvaille réellement tardive ramène la
  règle d'avant pour un nombre d'attentes qui double à chaque fois. Modèle : de 37 000-39 000 à 19 000-23 000 sommeils
  SPU par seconde, de 47 700 à environ 26 000-31 000 réveils de minuterie par seconde. En partie, les threads prennent
  sans cesse du travail : rien ne change.
- **`REWINDBOX_SPU_IDLE_EFFICIENCY_939`** (menus, et threads SPU au repos en partie) : un thread SPU au repos (même règle)
  dort dans la classe « utility », qu'iOS garde sur les cœurs économes, et reprend la classe des SPU dès son réveil. Son
  sommeil et son réveil se font donc sur un cœur économe ; tout ce qu'il fait ensuite, y compris le travail qu'il trouve,
  se fait dans sa classe habituelle. Les cœurs P restent au PPU et au RSX. Depuis la demande 2 : seulement pour les
  attentes allongées, seulement quand le jeu est léger (menus, salons, chargements ; jamais pendant une partie chargée),
  avec une auto-surveillance par fil (voir plus bas). Coût : deux changements de classe par tel sommeil (un appel
  système d'environ 1 µs chacun, sur un cœur économe).
- **`REWINDBOX_PREHASH_QOS_939`** (God of War III en jeu) : l'ouvrier de pré-validation des textures passe dans la classe
  des SPU. Il dépensait 0,07 à 0,11 cœur dans la classe du PPU pour servir 14 à 18 % des validations, pendant que les cœurs
  P étaient occupés à 97 % à 1,28 GHz et que le thread RSX était parqué 45 % du temps. Ce qu'il calcule ne change pas.
- **`REWINDBOX_WFE_PROBE_939`** (mesure, pour le prochain gain en jeu) : en partie, le PPU attend en boucle derrière chaque
  écriture exacte des SPU (166 500 attentes par seconde, 0,166 cœur P). Les attentes basse consommation (WFE) de la
  politique thermique rendent la main aussitôt (au plus 76 ns par tour) au lieu de dormir. La sonde dit pourquoi, une fois
  par démarrage (au plus 6 ms) : selon la réponse, ces attentes pourront vraiment dormir, ou être retirées.
- **`REWINDBOX_OTHER_TOP_939`** (mesure) : les threads du groupe « autres » (0,29 cœur en partie, jamais nommés) sont
  désormais listés dans `COREPROF frames … other_top=`.
- Le **mode asynchrone** compte aussi : une construction de pipeline ne bloque plus le fil RSX ; le jeu continue.

Ce que le lot ne peut pas promettre : en partie, Black Ops II occupe vraiment les deux cœurs P (93 %) et trois cœurs
économes. Garder l'état « nominal » pendant un long match demanderait de faire moins de travail ; le lot retire le travail
inutile. Effets sur la puissance et la température : **à mesurer sur l'iPhone** ; aucun gain n'est annoncé avant.

Essais proposés sur l'iPhone (réglages par jeu existants, à comparer dans la même session, téléphone **non branché** : la
charge chauffe à elle seule) :
1. Black Ops II, « Accurate SPU Reservations » désactivé. C'était l'état de ce jeu des builds 587 à 656 ; il a été remis
   parce qu'on soupçonnait ce mode d'être la cause du gel, mais le gel est revenu avec les réservations exactes (723 à 745),
   donc ce soupçon tombe. Effet attendu : les 166 500 attentes PPU par seconde (5,5 ms par image) et 0,19 cœur de verrous
   SPU disparaissent ; risque : un défaut propre au jeu dans ce mode.
2. Black Ops II, « Preferred SPU threads » à 2 (le choix d'ARMSX3 pour ce jeu) : moins de SPU en même temps sur la même
   instruction, moins de contention sur la file de travaux (18 % des échantillons SPU attendent une ligne verrouillée).
   Risque : moins de débit SPU si le jeu en manque.

### Core 939, demande 2 : la relecture approfondie avant l'IPA

Avant de produire l'IPA, le Core 939 compilé a été relu par quatre relecteurs indépendants (un par domaine : mode
asynchrone, capture du gel, chaleur SPU, le reste). Ce qu'ils ont trouvé, et ce que corrige la demande 2 (la première compilation, run 43788845920, ne contient pas ces
corrections) :

| Point | Risque | Correction |
|---|---|---|
| Un dessin sauté (pipeline encore en construction) cédait le cœur par `yield()` | Sur iOS, `sched_yield` est `swtch_pri(0)` : le fil RSX peut tomber en priorité 0 jusqu'à ~10 ms à chaque dessin sauté ; une rafale de premières rencontres aurait pu devenir un diaporama | `REWINDBOX_ASYNC_SKIP_NO_YIELD_939` : plus de `yield` sur iOS à cet endroit ; le fil RSX passe aux commandes suivantes |
| À l'arrêt, le fil RSX.W terminait tout le lot de constructions déjà retiré de sa file | Un arrêt, une sauvegarde d'état ou un changement de réglage pendant une rafale (20 × 0,5 s) pouvait dépasser les 10 s que l'application accorde | `REWINDBOX_ASYNC_TEARDOWN_939` : le fil vérifie l'arrêt avant chaque construction et abandonne le reste |
| L'origine d'une construction différée était perdue (`SHADERSTALL538_EVENT origin=0`) | Mesures fausses dans les prochains journaux | `REWINDBOX_ASYNC_ORIGIN_939` : l'origine voyage avec la tâche |
| La signature du gel se retrouvait dans les longs chargements de God of War III (noyaux SPURS au repos sur leur propre instance) | Quatre fausses captures de 17 Mio, ou la vraie capture écrasée | Capture réservée à Black Ops II (six numéros de disque), lignes des noyaux SPURS au repos ignorées, un fichier numéroté par capture (`RPCS3-freeze-guest-1.bin` à `-4.bin`), jamais d'écrasement |
| Stockage presque plein | `fs::file::write` arrête l'application sur un disque plein | Les deux captures (939 et la capture SPU du 938) refusent d'écrire avec moins de 64 Mio libres |
| Une page du jeu libérée pendant la copie | Sur iOS, la vue « sudo » est démappée avec la page : faute de lecture sur le fil du profileur | Copie par `vm_read_overwrite` (une page disparue est écrite comme des zéros) |
| En-tête RBGUEST1 | Compteurs SPU et régions différents des enregistrements écrits | En-tête réécrit à la fin avec les comptes réels |
| Fils SPU au repos dans la classe « utility » (`REWINDBOX_SPU_IDLE_EFFICIENCY_939`) | Sous l'ordonnanceur Clutch d'iOS, un fil « utility » rendu exécutable attend qu'aucun fil de classe supérieure ne soit prêt sur son groupe de cœurs : en partie, un SPU réveillé pour un travail aurait pu démarrer des dizaines de millisecondes trop tard | La classe « utility » ne sert plus que pour les attentes allongées (320 et 640 µs), seulement quand le jeu est léger (le processus utilise au plus 2 cœurs, mesuré toutes les 0,5 s ; levé à partir de 3 ; menus de Black Ops II : 0,5 à 1,8 cœur, partie : 4,3 à 5,0), prise juste avant de bloquer ; un sommeil qui finit plus tard que sa borne + un quart + 50 µs remet ce fil dans sa classe pour 256, 512, … attentes. Compteurs `THERMAL931 spu_efficient_late` et `spu_light_load` |
| Sonde WFE | La somme de la fenêtre pouvait déborder après une suspension de l'application de plus de 12 min | Conversion sans produit intermédiaire |

Limite connue, non corrigée : si MoltenVK échoue à créer un pipeline en différé (échec de compilation Metal), le fil RSX.W
s'arrête et les nouveaux pipelines restent sautés jusqu'à la fin de la session (le même échec arrêtait le fil RSX en mode
Legacy). Corriger demanderait de rendre non fatale l'erreur au cœur de la création des pipelines : pas sans essai sur
l'appareil.

### Vérifications du Core 939 (PC)

- Test statique du moteur `ios/tests/RPCS3IOSGPUDefaultsTests.cpp` (défaut asynchrone, règle de migration) compilé et
  exécuté avec g++ et clang++ (`-Wall -Wextra -Werror`).
- Vérification de syntaxe ARM64 (cible aarch64, libc++, `RPCS3_IOS`) de `device.cpp`, `SPIRVCommon.cpp`, `VKGSRender.cpp`,
  `RPCS3IOSFreezeDump.cpp`, `texture_cache.cpp` et `SPUThread.cpp` ; la fonction de migration de `RPCS3IOS.cpp`, la liste
  `other_top` de `RPCS3IOSPerformance.cpp` et la sonde WFE, compilées seules contre les vrais en-têtes du moteur (ces deux
  fichiers dépendent d'en-têtes Apple) ; la vérification signale bien une erreur volontaire.
- Identités de génération de code recalculées : PPU a987639e9f838d1c, SPU 477a3fa442d27917 (alias exact de
  `SPUThread.cpp`).
- Porte de la route Core (`--check-source-closure`, code 0) ; correctif canonique 53790583 (507 fichiers, demande 2) re-matérialisé
  octet pour octet sur une copie propre de l'amont 22f1152 ; étape Metal du workflow rejouée localement (PASS, source
  inchangée après le retour et la ré-application des étapes).
- Relecture contradictoire du correctif des attentes SPU (un relecteur indépendant, modèle hôte rejoué) : le défaut
  trouvé (trouvailles tardives aveugles aux écritures ordinaires du jeu) est corrigé dans ce Core.
- Non exécutés : bancs historiques, compilation iOS de ce lot (demandée à la route Core), appareil. **Aucun gain de
  température, de puissance ou d'images par seconde n'est annoncé avant les journaux de l'iPhone.**

### Livraison 756 (16 novembre 2026)

IPA privée de test 756 (run `43798159829`, IPA `1ef938b7…`, 331 043 649 octets), vérifiée hors ligne puis remise ; reçu
`docs/evidence/rewind756/delivery.json`. Base : l'IPA 754. Contenu : le Core 939 demande 2 (empreinte `e6e8e273`, à la
place du Core 938), la barre de performance minimaliste (FPS, CPU, RAM, NeoSwap) et le moteur S2Arm des correctifs
0001-0047 (pin vérifié `e1ffb7e5`). Ce moteur est repris parce que son pin a changé après la 754 : la recette (§ 3.12)
demande alors de classer ses commits comme revus. Le mainteneur voulait de toute façon une seule IPA 756 avec RPCS3 et
S2Arm (message de la session S2Arm). Le récepteur Cast de NeoPlay (étape 2) reste pour la 757.
Vérifications :
- contrat du serveur (préflight) réussi ;
- les quatre morceaux égaux à leurs empreintes API ;
- déchiffrement, IPA contre `SHA256SUMS` et le reçu du signataire, 97 images ;
- versions 0.0.8 / 756 ;
- validateurs melonx, neoplay, shaders, legal, no-kartpad et no-dusklight à 0.

Images changées : S2ArmEngine, `libRPCS3Core.dylib`, `rpcs3_internal_bridge` et Runner (déclarées). `melonx_internal_bridge`
a aussi changé, sans changement de ses sources (signalé, non bloquant ; même cas que les builds 732, 735, 737, 747, 748, 751
et 752). Rien n'a encore tourné sur un iPhone : le protocole ci-dessus s'applique tel quel avec cette IPA.

### Protocole sur l'iPhone (Core 939)

1. Premier lancement après la mise à jour : le journal doit contenir `REWINDBOX_ASYNC_SHADERS_939 global Shader Mode:
   Legacy Recompiler (single-threaded) -> Async Recompiler (multi-threaded)` (ou `-> …` identique si la valeur était déjà
   autre).
2. Black Ops II, téléphone non branché, coque retirée si possible : 2 à 3 minutes dans les menus, puis un match. Attendu :
   plus d'arrêt de plusieurs secondes aux premiers effets (un objet peut apparaître un instant en retard) ; dans les
   menus, `THERMAL931 spu_efficient_sleeps` non nul et moins de réveils (`ENERGY931 timer_wakeups_2ms`).
3. Si Black Ops II gèle : **attendre au moins 5 secondes** avant d'arrêter, puis envoyer
   `Documents/Diagnostics/PS3/RPCS3-freeze-guest-1.bin` (et `-2`, `-3`, `-4` s'il y en a) avec les journaux. C'est le
   fichier qui permet d'écrire le patch du jeu.
4. Essais facultatifs (un à la fois, même session si possible) : « Accurate SPU Reservations » désactivé pour Black Ops II,
   puis « Preferred SPU threads » à 2.
5. God of War III : démarrer normalement, charger la partie, refaire une sauvegarde d'état (§9).

## 11. Journaux de l'IPA 756 (16 novembre) et Core 940

### Le gel de Black Ops II : la cause, lue dans la capture

La capture `RPCS3-freeze-guest-1.bin` de l'IPA 756 (BLES01717 t6mp, exécutable PPU-fa8ffe9a…) a été lue hors appareil.
Mesuré dans la capture : le RSX tourne sur un saut vers lui-même (JTS) à l'adresse 0x385165c0 (offset d'E/S
0x084165c0 ; adresse = offset + 0x30100000). Ce bloc est l'image, octet pour octet, de la mémoire locale du SPU5
(0x2f980..0x306ff), écrite par le travail SPU `r_draw_lit`. Déduit du code des quatre images `r_draw_*` : en fin de
travail, elles empilent d'abord la demande {A,B,C,D} dans la file 0x2e1f400 (pour que `r_shaderpatch_ps3` remplace le
JTS par un saut vers la suite), puis seulement vident leur bloc de commandes en mémoire. Si `r_shaderpatch_ps3` passe
entre les deux, la vidange tardive réécrit le JTS par-dessus la libération : le RSX attend alors pour toujours. C'est
une course rare, côté jeu, qui colle au gel « après plusieurs minutes ». Pourquoi l'hôte laisse cet intervalle s'ouvrir
n'est pas mesuré.

Correctif (Core 940, `REWINDBOX_BO2_RDRAW_FLUSH_940`) : sur cet exécutable seulement, au démarrage à froid, les quatre
images vident leur bloc avant d'empiler la demande (44 mots, 11 par image). Chaque mot d'origine est comparé au contenu
de la capture avant toute écriture ; sinon rien n'est écrit et une ligne le dit (`CONFIG_LAYERS part=bo2_rdraw_flush
state=refused_guard`). Une sauvegarde d'état garde la mémoire du démarrage d'où elle vient (`state=savestate`). Écrire
dans les données de l'exécutable désactive l'optimisation d'analyse PPU, comme pour tout patch de jeu : le premier
démarrage peut recompiler. Non testé sur iPhone.

### Chaleur : ce que le Core 940 ajoute

- `REWINDBOX_WFE_SLEEP_940` : la 756 montre que l'attente WFE ne dormait jamais (CLREX vidait le moniteur). La séquence
  devient sevl, wfe, ldaxr, puis wfe seulement si la ligne n'a pas changé, sans CLREX, et seulement après un auto-test
  qui voit un vrai repos (entre 100 ns et 20 µs en moyenne). Sinon l'attente reste un simple indice d'attente.
- `REWINDBOX_SPU_LR_BACKOFF_940` : l'attente après une réservation perdue rend la main à la borne du recul d'inactivité
  du Core 935, qui peut alors l'allonger.
- `REWINDBOX_WORK_INTERVAL_PROBE_940` (mesure seulement) : une fois par lancement, sur son propre fil, l'app essaie de
  donner à iOS une échéance d'image (« work interval » avec FINISH_AT_DEADLINE). La ligne `CONFIG_LAYERS
  part=deadline_probe` dit si iOS 27 l'accepte. Rien ne s'en sert encore : c'est la condition de la piste « finir à
  l'échéance plutôt qu'au plus vite ».

Identités de cache inchangées (PPU a987639e9f838d1c, SPU 477a3fa442d27917, alias exact de SPUThread.cpp), ABI 30,
92 exports. Vérifié sur PC : contrôle de fermeture des sources (code 0), contrôle Metal replié (PASS), syntaxe ARM64 de
PPUModule.cpp, en-tête du correctif compilé et essayé sur l'hôte. Non exécuté : harnais historiques, iPhone. Aucun gain
de chaleur, d'énergie ou d'images par seconde n'est revendiqué.

### Livraison 760 (16 novembre 2026)

Core 940 : demande 1 (run 43838124437) arrêtée par le contrôle de syntaxe iOS (canal de journal dans un espace de noms
anonyme), demande 2 compilée (run 43841141271), vérifiée et épinglée (empreinte 73235b7e, identités de cache
inchangées). IPA 760 sur la base 759 : première demande (run 43845801508) refusée à l'intégration (moteur S2Arm déclaré
« ajouté » alors qu'inchangé), seconde demande verte (run 43849717506). IPA `5a60cc20…`, 331 176 688 octets, vérifiée
hors ligne après téléchargement et remise au mainteneur ; clé privée supprimée. Groupes Flutter et natif non exécutés.
Non testée sur iPhone : gel de Black Ops II, chaleur et images par seconde restent à observer.

## 12. Journaux de l'IPA 760 (16 novembre) et Core 941

Demande du mainteneur, 16 novembre : rester en état « nominal », ne pas s'arrêter à deux correctifs. Journaux privés hors
Git, IPA 760 = Core 940 : Black Ops II (PID 24522, 306 s) puis God of War III (PID 24610, 109 s), 78 fenêtres de 5 s.

### Ce que mesurent les journaux

| Scène | Images/s | Puissance CPU | Cœurs occupés (dont cœurs P) | Fréquence des cœurs P | Réveils de minuterie/s | État |
|---|---|---|---|---|---|---|
| Black Ops II, menus | 60 | 0,60 à 2,12 W | 1,0 à 1,2 (0,72 à 0,82) | 1,75 à 3,42 GHz | 42 000 | nominal |
| Black Ops II, partie, 15 premières secondes | 40 à 47 | 2,8 à 3,4 W | 4,3 (1,8) | 2,4 à 2,7 GHz | 21 000 | nominal |
| Black Ops II, partie, ensuite | 20 à 30 | 1,9 à 2,0 W | 4,4 à 4,6 (1,9) | 1,6 à 1,8 GHz | 24 000 | fair |
| God of War III, écran-titre | 60 | 0,53 W | 0,21 (0,18) | 3,93 GHz | 43 000 | fair |
| God of War III, scènes lourdes | 14 à 21 | 2,0 à 2,25 W | 4,8 à 5,0 (1,95) | 1,26 à 1,45 GHz | 10 000 à 22 000 | fair |

Lecture :

1. **Les menus coûtent selon la fréquence qu'iOS donne aux cœurs P, pas selon le travail.** Quatre fenêtres de menu de
   Black Ops II font le même travail pour 0,60, 1,35, 1,68 et 2,12 W. La grappe P est facturée 0,75 J par seconde de CPU
   à 1,75 GHz et 2,7 J à 3,4 GHz ; la grappe E, 0,18 J. 73 % du temps CPU des menus est sur les cœurs P.
2. Les 42 000 réveils par seconde des menus : 29 600 sommeils de sondage des six fils SPU (la règle du Core 939 n'en
   allonge que 9 % : chaque fil prend un travail toutes les 0,64 ms), 11 300 tranches de parcage du RSX, 2 750 attentes
   du jeu.
3. La partie passe en « fair » environ 15 s après son début ; iOS baisse alors les cœurs P de 2,4-2,7 à 1,6-1,8 GHz et le
   jeu, qui cale ses images sur des multiples de 16,7 ms, alterne entre 33 et 50 ms : c'est l'oscillation ressentie.
   En partie le travail est réel (SPU 2,7 à 2,9 cœurs, PPU 1,0, RSX 0,36, encodage Metal 0,26) : aucun gaspillage du
   même ordre que dans les menus n'y est mesuré.
4. L'attente basse consommation (WFE) repose réellement le cœur depuis le Core 940 (`WFEPROBE939` : 1,33 µs par tour,
   `wfe_verdict=1`), mais la politique ne l'emploie qu'à partir de « serious » : `event_waits=off` dans les 78 fenêtres.
5. Les sommeils pris en classe « utility » par le Core 939 (IPA 756 et 760) : 11 893, dont 134 en retard (1,1 %), aucun
   changement de classe en échec.
6. La sonde d'échéance du Core 940 répond `status=ok chosen=0x47` : iOS 27 accepte qu'une app donne une échéance d'image.
   Rien ne s'en sert encore.

### Ce que change le Core 941

- **`REWINDBOX_LIGHT_LOAD_941` (menus, écrans-titres, salons).** Quand le jeu est léger, ses fils PPU, SPU et RSX passent
  dans la classe « utility », qu'iOS garde sur les cœurs E. « Léger » : pendant 3 s, au plus 1,25 cœur, aucun fil au-dessus
  de 0,40 cœur, et une cadence d'images stable d'au moins 15 images/s (un chargement ou une image fixe n'est pas « léger » :
  son travail n'est pas cadencé, le ralentir ne ferait que l'allonger). Sortie immédiate (un échantillon de 500 ms) à
  2,5 cœurs, ou quand la cadence passe sous 95 % de celle d'avant l'entrée pendant deux échantillons ; une cadence perdue
  dans les 5 s qui suivent l'entrée est imputée à la classe : la prochaine entrée attend 20 s, puis 40, … jusqu'à 320 s.
  Chaque fil applique la classe là où il teste déjà son état, et reprend la sienne de la même façon. Fils audio,
  compilation, MoltenVK et application hôte : non touchés.
- **`REWINDBOX_RSX_IDLE_941`, tranches de parcage.** La tranche suit la durée du repos : 50 µs, 100 µs à partir de 2 ms,
  200 µs à partir de 4 ms, 1 ms à partir de 250 ms (Core 938). Un parcage de 6,6 ms prend environ 50 tranches au lieu de
  104 ; un de 8,2 ms environ 58 au lieu de 131. Un PUT du jeu après 2 ms de repos est vu au plus 100 µs plus tard, après
  4 ms au plus 200 µs plus tard ; vidage, flip et ZCULL réveillent toujours aussitôt.
- **`REWINDBOX_RSX_IDLE_941`, délai de grâce.** Pendant la milliseconde qui précède un parcage (341 périodes par fenêtre
  en partie, 430 dans les menus, en appels d'ordonnanceur dos à dos sur un cœur P), l'attente sur la ligne du registre PUT
  sert dans tous les états thermiques dès que l'auto-test du Core 940 a vu qu'elle repose le cœur, six tours entre deux
  `yield` ; un PUT vu pendant un tour est lu sans `yield`.
- `THERMAL931` publie `light_class`, `light_entries`, `light_leaves` (charge:cadence:imputée), `light_ms`,
  `light_class_changes`, `light_class_failures`.

Tout le lot se coupe avec « Event Waits When Hot » = Disabled. Aucun fichier d'entrée de génération de code n'est
modifié : identités PPU `a987639e9f838d1c` et SPU `477a3fa442d27917` inchangées, caches des joueurs conservés.

### Core 941, demande 2 : la relecture indépendante avant l'IPA

La première compilation (run 43922916468, épinglée puis remplacée, jamais livrée) a été relue par un relecteur
indépendant. Ce qu'il a trouvé, et ce que corrige la demande 2 :

| Point | Risque | Correction |
|---|---|---|
| Les images comptées étaient les présentations de l'hôte, dialogues natifs compris | Un dialogue sur image fixe ou un chargement donnait une « cadence stable » et permettait l'entrée | Compteur des flips du jeu (`m_guest_frames`) |
| Une fois « léger », le fil le plus chargé n'était plus regardé et la cadence de référence restait celle de l'entrée | Un chargement animé derrière un menu, avec un fil saturé, restait en classe « utility » ; une chute de 60 à 40 après une entrée à 30 n'était pas vue | Sortie quand un fil atteint 0,80 cœur sur deux échantillons ; la référence suit la cadence à la hausse |
| Un fil PPU ou SPU qui calcule sans drapeau d'état ne repasse pas par `check_state()` | Il gardait la classe « utility » après la sortie, sans borne de temps | À la sortie, chaque fil PPU et SPU enregistré reçoit le drapeau `notify` (que `check_state()` ne fait qu'effacer) ; `check_state()` resynchronise aussi à son retour |
| Une sortie pour charge juste après l'entrée n'était retenue que 5 s | Si la classe elle-même fait monter la charge, entrée et sortie toutes les 8,5 s | Une sortie pour charge dans les 5 s est imputée comme une sortie pour cadence (20 s, puis doublement) |
| MoltenVK choisit la file de compilation d'après la classe du fil qui attend | Avec le fil RSX en « utility », une compilation synchrone serait partie en file par défaut | La classe d'origine du fil est testée (`RPCS3IOSPlatform.mm`) |
| L'auto-test WFE admet des tours jusqu'à 20 µs en moyenne | Six tours pouvaient retarder une demande de vidage de 120 µs | Au plus six tours et 8 µs mesurés entre deux `yield` |
| `test/rpcs3_thermal931_test.py` exigeait l'ancienne forme (un seul tour) | Test existant en échec sur le Core 941 | Le test accepte le tour unique (Cores 931 à 940) ou la boucle bornée |

Rien trouvé sur : la compilation des en-têtes, les 46 conversions de la ligne `THERMAL931`, les cycles d'inclusion, les
fils du pool, `scoped_priority`, la paire `enter()`/`leave()` du Core 939, le comportement avec le réglage Disabled.
Après correction : les 104 tests `--source` existants donnent le même résultat sur l'arbre 940 et sur l'arbre 941.

### Ce que le lot ne change pas, et pourquoi

- **Les attentes WFE des fils PPU et des écrivains SPU restent à partir de « serious ».** Elles durent moins de 0,5 µs
  dans 94 % des cas (1,15 million sur 1,22 par fenêtre) ; aucune fenêtre « serious » de l'IPA 760 ne mesure ce que le vrai
  repos du Core 940 leur fait. Les avancer sans cette mesure pourrait coûter des images. À lire dans les prochains
  journaux : `wfe_latency_us` et les images par seconde d'une fenêtre « serious ».
- **Réservations SPU exactes de Black Ops II.** Les fils PPU y passent 10,6 % de leur temps à attendre derrière les
  écritures exactes des SPU (530 ms par fenêtre, dont 183 ms pour le fil principal), et les SPU 603 ms dans le verrou. Le
  réglage par jeu « Accurate SPU Reservations » désactivé les supprime ; la base RPCS3 reste la référence (règle du
  Core 922), le défaut n'est donc pas changé ici. C'est l'essai le plus utile contre l'alternance 33/50 ms.
- **Travail en partie** : pas de dépense évitable mesurée ; rester « nominal » pendant un long match demanderait de faire
  moins de travail (cadence plafonnée), ce qui est une décision du mainteneur, pas un correctif.

### Vérifications (PC)

- Contrôle hôte jetable du contrôleur et des tranches (g++ avec ASan/UBSan et clang++, `-Wall -Wextra -Werror`) :
  entrée après six échantillons, sortie sur charge, sur cadence, imputation et doublement des attentes, écran de
  chargement et fil chargé jamais « légers », suivi par fil.
- Syntaxe des fichiers C++ modifiés avec `-DRPCS3_IOS` sur l'hôte : `RSXFIFO.cpp`, `CPUThread.cpp` et `RSXThread.cpp`
  n'ont que les erreurs que le Core 940 a déjà sur cet hôte ; `Thread.cpp` et `RPCS3IOSPerformance.cpp` dépendent
  d'en-têtes absents ici (asmjit, Apple) : relus à la main, compilés par la route Core.
- Porte de la route Core (`--check-source-closure`, code 0), test de route, test du pin (source), règle des marqueurs ;
  correctif canonique re-matérialisé octet pour octet sur une copie propre de l'amont (510 fichiers) ; l'incrément se
  retire proprement de l'arbre canonique.
- Non exécutés : bancs historiques, appareil. **Aucun gain de température, de puissance ou d'images par seconde n'est
  annoncé avant les journaux de l'iPhone.**

### À lire dans les prochains journaux

Menus de Black Ops II, 2 minutes, téléphone débranché : `THERMAL931 light_class=1`, `light_ms` proche de 5000 par
fenêtre, `ENERGY931 p_share` en baisse nette (0,73 aujourd'hui) et `cpu_energy_mj` sous 3 000 par fenêtre ; images à 60.
Si `light_leaves` compte des sorties « imputées » à répétition, la classe « utility » coûte des images sur ce jeu : le
dire avec les journaux.
