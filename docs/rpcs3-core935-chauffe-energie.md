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
