# RPCS3 Core 931 — chantier thermique

Demandes du mainteneur, 11 novembre 2026 : « Principal amélioration à faire serait au niveau thermique ! Avec tous les
diagnostics fais une audits et corrige tout ce que tu pourras trouver avec 10 correctifs cibler sans faire de régression
ou as toucher sur ce qui fonctionne. » puis « Cherche toute les pistes possibles et fais un vrai chantier d'innovation sur
la gestion thermique. »

Statut : **écrit, testé sur PC (hôte Linux), à compiler pour iOS ; rien n'a tourné sur un iPhone.** Aucun gain d'énergie
ou de FPS n'est annoncé ici : le Core 931 apporte la mesure (ENERGY931) qui le dira sur l'appareil.

## 1. Constat (journaux de l'IPA 725, privés, hors Git)

| Mesure (par seconde) | Black Ops II en jeu | Session presque au repos (60 FPS, 0,3 cœur) |
|---|---|---|
| Changements de contexte | ~80 000 | ~86 000 |
| Appels système BSD | ~68 000 | ~89 000 |
| Appels Mach (yield…) | 40 000 à 70 000 (150 000 à 245 000 pendant les compilations de pipelines) | 4 000 à 6 000 |
| Verrous d'écriture PUTLLC lourds | ~265 000 | — |
| Parcages PPU | ~340 000 | — |

- Black Ops II passe à l'état thermique 2 (« sérieux ») après environ 35 s et y reste ; le travail par image ne change pas
  mais les FPS tombent d'environ 45 à 30 ; 5 cœurs sur 6 sont occupés (SPU 3,2, PPU 0,9 à 1,0, RSX 0,5, autres 0,3 à 0,4).
- Le dernier `RPCS3-session.txt` de la 725 montre `app=background` avec le jeu qui émule encore à 8 images/s : en
  arrière-plan, seul le GPU était arrêté (Core 928), pas les threads PPU/SPU/RSX.
- Mémoire compressée de 265 à 803 Mio pendant la partie : environ 5 Mio/s, coût CPU faible (pas un levier principal).

## 2. Les 10 correctifs

| # | Marqueur | Ce qui change |
|---|---|---|
| 1 | `REWINDBOX_ENERGY_931` | Nouvelle ligne `COREPROF ENERGY931` par fenêtre de 5 s : énergie facturée par le système au processus (nJ → mJ), part des cœurs performance, temps CPU, cycles et instructions, réveils d'interruption et de veille, réveils de minuterie à moins de 2 ms et entre 2 et 5 ms, temps CPU par classe QoS, compteur GPU, **énergie par image**. Sources : `proc_pid_rusage(RUSAGE_INFO_V6)` (cherché à l'exécution), `TASK_POWER_INFO`, `TASK_POWER_INFO_V2`. Une source refusée est écrite « unavailable », jamais 0. |
| 2 | `REWINDBOX_HOT_COUNTERS_931` | Les compteurs du verrou d'écriture (phases, maximum, parcages lents) étaient des atomiques partagés, touchés ~6 fois par verrou : ils ont une ligne de cache par thread ; le rapport fait la somme. Mêmes valeurs imprimées. |
| 3 | `REWINDBOX_HOT_COUNTERS_931` | Idem pour l'histogramme des parcages et les parcages PPU (27 threads PPU qui sortent ensemble de chaque verrou se disputaient la même ligne). |
| 4 | `REWINDBOX_WRITER_RECORD_AFTER_RELEASE_931` | Les phases du verrou étaient enregistrées pendant que tous les PPU étaient encore parqués ; elles sont publiées après la libération (règle CELL536 déjà appliquée aux autres compteurs du verrou). Mêmes valeurs. |
| 5 | `REWINDBOX_THERMAL_POLICY_931` | Le Core suit l'état thermique du système (notification `NSProcessInfoThermalStateDidChangeNotification`) ; ligne `COREPROF THERMAL931` par fenêtre ; réglage « Event Waits When Hot » (Automatique par défaut : à partir de l'état sérieux). |
| 6 | idem | Attente active du verrou d'écriture sur chaque PPU (levier 917, budget 8 µs) : à partir de l'état sérieux, le cœur dort sur la ligne de l'état du PPU (LDAXR puis WFE) au lieu d'enchaîner des `yield` ; l'écriture qui parque le PPU le réveille. Même budget, horloge relue à chaque tour. |
| 7 | idem | Attente PPU de 6,7 µs avant le sommeil (passive lock) : même borne de temps, passée en WFE sur le mot des bits du verrou ; le PPU montre `cpu_flag::wait` **avant** de dormir (sinon l'auteur du verrou et le PPU s'attendraient l'un l'autre). |
| 8 | idem | File RSX vide depuis moins de 1 ms : entre deux `yield`, WFE sur le registre PUT quand la file est vide parce que PUT = GET ; le `yield` reste, donc les autres threads ont le cœur comme avant. |
| 9 | `REWINDBOX_BACKGROUND_PAUSE_931` | En arrière-plan (après la fermeture du gate GPU), le Core met l'émulation en pause avec `rpcs3_ios_pause_emulation` ; au retour (après la réouverture du gate), il la reprend, seulement si c'est lui qui l'a mise en pause. Le temps du jeu ne saute pas (`Emu.Resume` corrige le temps de pause). Les observateurs du gate restent ceux du Core 928, octet pour octet ; la pause a les siens, et la pause comme la reprise passent d'abord par la file principale : elles s'exécutent quand la notification a fini d'être distribuée, donc après l'observateur du gate quel que soit l'ordre (non documenté) dans lequel iOS appelle les observateurs. |
| 10 | analyseur | `tools/rpcs3/capture_analyzer.py` lit ENERGY931 et THERMAL931 : énergie par image par état thermique, et attentes par événement activées contre désactivées **dans un même état thermique** seulement (comparer une fenêtre chaude à une froide mesurerait la température, pas les attentes). |

Le moniteur exclusif ne peut pas bloquer indéfiniment : XNU active le flux d'événements du compteur à 1 µs par défaut,
comme délai maximal de WFE (`osfmk/arm64/machine_routines.c`, `wfe_timeout_configure` et `wfe_timeout_init`), et la
bibliothèque système d'Apple attend de la même façon dans ses verrous (`libplatform`, `OS_LOCK_SPIN_PAUSE`).

## 3. Bilan par correctif

- **Coût supprimé** : (2)(3) des écritures atomiques partagées sur ~600 000 événements par seconde (estimé 10 à 25 % d'un
  cœur, non mesuré) ; (4) ces écritures sortent de la fenêtre où tous les PPU attendent ; (6)(7)(8) l'activité d'un cœur
  pendant ses attentes actives quand l'iPhone est chaud ; (9) toute l'émulation quand l'application n'est plus visible.
- **Coût restant** : le travail du jeu lui-même (SPU 3,2 cœurs, verrous d'écriture exacts), inchangé ; une lecture
  d'horloge par tour dans les attentes WFE ; deux appels système par fenêtre de 5 s pour ENERGY931.
- **Chemin critique** : inchangé à froid (état nominal ou correct : exactement les attentes d'avant) ; à chaud, mêmes
  conditions et mêmes bornes, réveil sur l'écriture attendue ou au plus après environ 1 µs.
- **Mémoire** : quelques Kio de compteurs par ligne de cache (3 blocs de 32 lignes de 128 octets).
- **Risques** : (6)(7)(8) un réveil un peu plus tardif qu'une attente active pure (de l'ordre de la microseconde) si
  l'écriture attendue tombe sur une autre ligne ; (9) un bref silence audio à la reprise ; le menu en jeu ne met toujours
  pas en pause (décision produit qui reste la tienne).

## 4. Revue indépendante

Une relecture indépendante du commit `a47ab68` a trouvé un vrai défaut, corrigé dans `276f677`. Les trois attentes WFE
comparaient une relecture fraîche au lieu de la valeur sur laquelle leur condition venait d'être testée. Si l'écriture
attendue arrivait entre les deux, le cœur dormait sur la nouvelle valeur jusqu'au prochain événement, soit environ 1 µs
grâce au flux d'événements, mais c'était inexact. Chaque site teste désormais sa condition sur la valeur même que WFE
compare. Le test le vérifie dans la source, avec une contre-épreuve. Sont jugés corrects par la revue : les compteurs
répartis, l'enregistrement après libération, la séquence LDAXR/WFE/CLREX, la pause en arrière-plan sur sa file série.

Seconde relecture indépendante, sur le delta `276f677..2eaf39d` (source seule) :

- Pause en arrière-plan incomplète. Un jeu qui démarrait encore quand l'application est partie (première compilation
  PPU par exemple) n'émulait pas encore, donc la pause était refusée. Il se mettait ensuite à tourner en arrière-plan.
  De même, les observateurs installés avec le premier périphérique Vulkan pouvaient trouver l'application déjà en
  arrière-plan. Corrigé dans `a073925` :
  - l'installation lit l'état de l'application une fois ;
  - tant que l'application est en arrière-plan et que l'émulation tourne, le fil des rapports (une fenêtre toutes les
    5 s) redemande la pause ;
  - chaque pause est décidée sur le fil principal, seulement si l'application y est en arrière-plan.

  Une contre-épreuve vérifie qu'une pause décidée sans relire cet état est refusée par le test.
- Hypothèse d'interblocage, réfutée sur pièces. `Emu.Pause` et `Emu.Resume` attendent chacun une fois le fil principal :
  l'hôte fournit bien un rappel de fil principal, `RPCS3Dispatch`, par l'ABI d'initialisation. Elles tournent sous
  `g_api_mutex`. Or l'hôte appelle toutes les fonctions qui prennent ce verrou depuis ses propres files, jamais depuis
  le fil principal. Le fil principal n'attend jamais ces files, et l'entrée manette ne prend pas le verrou.
- Défauts mineurs corrigés : THERMAL931 publie aussi `background_resume_refused=` et `background_late_requests=`, et
  PARKCMP917 nomme chaque levier comparé (`compared=event_waits`…).

Deuxième correction, trouvée en adaptant les tests existants : la première version reprenait l'émulation dans le même
bloc que la réouverture du gate, en modifiant l'observateur du Core 928. Les observateurs du gate sont revenus à leur
texte d'origine ; l'ordre « après le gate » est maintenant garanti par la file principale (voir le correctif 9) et un
contrôle négatif du test 931 vérifie qu'une reprise envoyée directement sur sa file est refusée.

## 5. Compatibilité avec les tests existants (aucun contrôle retiré)

- Test 917 : il exige le texte exact de la boucle d'attente du verrou d'écriture. Il accepte maintenant le texte 917 ou le
  texte 931, chacun exact (même condition, même budget, même attente d'avant intacte), et l'enregistrement différé du 931
  à condition que `IOSWriterLockRecord931.h` publie la même durée de parcage.
- Son harnais lit les compteurs comme des atomiques (`counters.ppu_parks == 2`) : les compteurs répartis se lisent de la
  même façon (somme des lignes, sans les remettre à zéro) ; seul `take()` les vide. Le test 931 vérifie les deux.
- Tests 919 et 920 : le Core 931 ajoute ses lignes à côté de celles du 920 (réglage, catalogue, politique) ; leurs chaînes
  d'inversion retirent d'abord le Core 931, comme elles retiraient déjà 925 puis 921.
- Test 921 : il inverse son correctif seul ; l'include et la ligne de journal du 931 ont été déplacés hors de son contexte.
- Tests 927 et 928 : observateurs du gate inchangés, trois observateurs comme avant dans leur fonction.

## 6. Pistes étudiées et écartées

- Effacement noir de toute l'image d'affichage avant la mise à l'échelle (≈ 3 Mpx par image) : une variante exacte au
  pixel près n'est pas démontrable hors appareil ; changer la taille de l'image d'affichage changerait l'image.
- Écriture des journaux sans réouvrir le fichier : ~150 appels système par seconde, négligeable face aux 68 000 mesurés.
- Attentes de l'audio (`cellAudio`, 500 à 1000 µs) : conception amont, chemin sensible, gain faible.
- Tranches plus longues du parcage RSX (50 µs) : ajouterait du retard sur les sémaphores RSX (God of War III).
- Seuils GETLLAR, mode relâché, nombre ou priorité des SPU, plafond de FPS, fréquence d'affichage, résolution, interpréteur
  de shaders : exclus par tes règles.
- Menu en jeu qui met l'émulation en pause : grosse économie potentielle (les menus restent ouverts longtemps), mais c'est
  une décision produit — à ta demande seulement.

## 7. Protocole d'appareil (prochaine IPA)

1. Black Ops II en multijoueur 5 à 10 minutes (jusqu'à l'état thermique sérieux), puis exporter les journaux.
2. Sortir de l'application 30 s pendant une partie, revenir : `Pausing the current PlayStation 3 emulation session`,
   `background_pauses=1` dans THERMAL931, le jeu reprend au même point.
   Puis sortir pendant le démarrage d'un jeu (compilation PPU) et revenir après la fin de celui-ci : la pause arrive
   quand le jeu commence à tourner (`background_late_requests=` au moins 1, `background_pauses=` augmenté), et la
   reprise se fait au retour.
3. Pour une mesure A/B : « Lever comparison between report windows » sur Activé ; l'analyseur compare alors l'énergie
   par image avec et sans attentes par événement dans un même état thermique.
