# RPCS3 Core 917 — Black Ops II : le coût du verrou d'écriture exact

Suite de la mission du 10 novembre (demande du mainteneur : plus de performances pour Black Ops II et God of War III).
Core 917 = Core 916 + ce document. **Aucune mesure iPhone n'a été faite avec ce Core** : ce qui suit vient des
journaux applicatifs existants et d'exécutions sur hôte ; la section 5 dit ce que le prochain export doit montrer.

## 1. Ce que disent les journaux

Le dernier export qui contient encore les fenêtres de rapport de BO2 en jeu est celui du build 676 (Core 905,
`BLES01717`, réservations SPU précises, PID 25658, session 3, fenêtres 9 à 17). Les exports 694 et 718 n'ont plus
ces lignes (rotation des fichiers) ; ils confirment seulement la cadence (718, session 2 : 20 à 28 images/s, GPU
vers 30 %).

| Fenêtre de 5 s (676) | Valeur |
|---|---|
| Images | 20 à 26 par seconde |
| GPU occupé | 30 à 36 % |
| PUTLLC « lourds » (changent des données, verrou d'écriture) | 1,08 à 1,60 million |
| Temps SPU passé à **acquérir** ces verrous | 2,4 à 2,9 s (1,8 à 2,5 µs par verrou) |
| Temps SPU passé à les **tenir** | 13 à 19 ms (12 ns par verrou) |
| Threads PPU en attente longue derrière ces verrous | 15 000 épisodes, 1,06 s |
| Threads SPU | 6, entre 0,46 et 0,58 cœur chacun |
| Thread RSX | 0,52 à 0,59 cœur, FIFO occupée 42 à 51 % |
| Thread PPU principal | hors des cinq threads les plus chargés (le cinquième est entre 0,46 et 0,57 cœur) |

Détail de la fenêtre 12 (20,5 images/s, 1 076 602 verrous) : 2 238 967 PUTLLC réussis dont 1 076 569 lourds — les
autres réécrivent une ligne inchangée, c'est de la scrutation ; 14 268 épisodes d'attente longue des threads PPU
(990,6 ms, 21 891 attentes temporisées de 39 µs en moyenne, jusqu'à 7,8 ms) ; `PPUGRACE664` : 3 839 fenêtres de
grâce, 4 551 reports d'écrivains, 726 ms ; les six SPU n'attendent presque jamais un événement (407 attentes,
119 ms) alors qu'ils n'occupent que 0,53 cœur chacun.

Aucun thread n'est saturé : la cadence n'est limitée ni par le GPU, ni par un cœur. Les lignes disputées
(`0x2e20c00`, `0x2e20880`…) sont la file de travaux du jeu — une file sans verrou à pointeurs étiquetés, avec
environ 190 travaux en attente dans les dumps. Chaque retrait ou dépôt par un SPU est un PUTLLC qui change des
données, soit 8 000 à 13 000 par image.

## 2. Le mécanisme

Avec les réservations précises, un tel PUTLLC prend `vm::writer_lock` : il publie son bit exclusif, demande à chaque
thread PPU de s'arrêter à son prochain point de contrôle, et attend qu'ils le soient tous. Tant que son bit est posé,
aucun thread PPU n'exécute de code du jeu. C'est ce qui rend l'écriture exacte face aux écritures simples du PPU, et
c'est ce que le mode « relâché » ne garantit pas : **il reste refusé**, et rien dans ce Core ne s'en approche.

L'attente du SPU (`vm.cpp`, `reservation_lock_wait`) tourne 128 itérations de l'indication `yield` du processeur —
une fraction de microseconde — puis cède son cœur par un appel système (`thread_switch`) toutes les 32 itérations.
Or un thread PPU en code compilé s'arrête au bloc suivant, et un thread PPU dans une fonction hôte (appel système
du jeu, opération de réservation) s'arrête à son retour, en un temps du même ordre ou un peu plus long. Le SPU
paie donc une cession de cœur alors que le thread qu'il attend est en train de tourner — c'est cohérent avec les
1,8 à 2,5 µs mesurés par verrou — et il peut perdre son cœur pendant que son bit exclusif garde tous les threads PPU
arrêtés.

## 3. La modification

`REWINDBOX_WRITER_PARK_SPIN_917` (`rpcs3/ios/IOSWriterParkSpin917.h`, `vm::writer_lock`) : le SPU tourne pendant
8 µs dans une boucle placée devant l'attente précédente ; celle-ci n'est pas modifiée et repart de sa première
itération (revue indépendante du 10 novembre : la première forme, qui remettait le compteur à zéro dans la boucle
d'origine, la faisait repartir de la deuxième ; corrigé avant toute compilation). Ce que le SPU attend ne change
pas : tous les threads PPU arrêtés avant l'écriture, le verrou tenu comme avant. Un thread PPU qui n'est pas sur un
cœur reçoit toujours les cessions, 8 µs plus tard — contre les 50 µs et plus que coûte déjà un tel arrêt.

Réglage « Writer lock park spin » (Expérimental → FPS Experiments) : Automatique l'active pour tous les titres,
Désactivé rétablit l'attente précédente. Aucun autre réglage, aucun nombre ou priorité de SPU, aucun délai
GETLLAR/PUTLLC du jeu n'est modifié.

### Comparaison dans la même scène (`REWINDBOX_PARK_SPIN_COMPARE_917`)

Ce que vaut ce budget dépend de l'ordonnanceur de l'iPhone : aucun hôte ne le mesure, et comparer un export 917 à
l'export 676 confondrait le levier avec la scène et avec les Cores intermédiaires. Le rapport fait donc lui-même la
comparaison, sans rien demander au joueur. Avec le réglage sur Automatique, tant que dure une tempête de PUTLLC
lourds (au moins 100 000 par fenêtre de 5 s) :

| Fenêtres de tempête du démarrage | Levier |
|---|---|
| 1 à 6 | actif (les captures demandées par le rapport s'y déroulent) |
| 7 à 22 | 2 fenêtres inactif, 2 fenêtres actif, tour à tour : 8 fenêtres de chaque côté |
| ensuite | actif |

Les deux côtés sont exacts : « inactif » est l'attente du Core 916. `RANGELOCKPROF` imprime `park_spin=` pour la
fenêtre qu'il rapporte et `COREPROF PARKCMP917` chaque étape. Une fenêtre hors tempête tourne levier actif et n'est
pas comptée. Sur Activé ou Désactivé, rien n'alterne : c'est le choix de l'utilisateur. `tools/rpcs3/capture_analyzer.py`
imprime les deux côtés (médianes par fenêtre : images/s, temps d'acquisition et d'arrêt par verrou, temps des arrêts
lents, verrous au-delà du budget, temps d'arrêt du thread principal).

## 4. Test discriminant (hôte)

`test/rpcs3_writer_park917_test.py`, 27 vérifications sur l'en-tête réel :

- l'attente sur une horloge comptée : désactivée, elle ne tourne jamais et ne lit pas l'horloge ; activée, elle
  tourne jusqu'à la fin du budget puis plus jamais ; une attente qui n'a pas lieu ne lit pas l'horloge ;
- la poignée de main sur deux vrais threads, étalonnée sur la machine (un thread qui s'arrête 2 à 6 fois plus tard
  que ne durent les 128 itérations) :

| 20 000 verrous, cinq exécutions | Attente précédente (contrôle) | Avec le budget |
|---|---|---|
| Verrous ayant cédé leur cœur au moins une fois | 19 906 à 19 970 | 11 à 97 |
| Cessions au total | 151 980 à 189 087 | 2 041 à 17 481 |

Les cinq exécutions ont eu lieu pendant que les autres tests occupaient la machine : un thread désordonnancé
pendant un verrou coûte à lui seul des centaines de cessions, d'où l'étendue de la dernière colonne.

- un thread qui ne s'arrête pas dans le budget (pas sur un cœur) : 200 verrous sur 200 cèdent encore leur cœur.

- la comparaison : les six premières fenêtres de tempête levier actif, puis huit fenêtres de chaque côté par paires,
  puis actif ; une fenêtre sous la borne, arrêtée ou sans image n'est pas comptée ; un nouveau démarrage recommence ;
  un titre sous la borne (GOW3) n'alterne jamais.

Ces chiffres montrent le mécanisme sur un PC Linux ; ils ne prédisent pas le gain sur iPhone.

## 5. Ce que le prochain export montrera

`RANGELOCKPROF` gagne, par fenêtre :

| Champ | Lecture |
|---|---|
| `wl_putllc_park_hist=a:b:c:d:e:f:g:h` | arrêts des PPU par durée (bornes 0,5, 1, 2, 4, 8, 16, 50 µs, puis au-delà) |
| `wl_putllc_slow_park_ms` | temps des arrêts de 50 µs et plus (thread PPU hors d'un cœur) |
| `wl_putllc_over_budget` | verrous dont l'attente a dépassé le budget |
| `ppu_parked`, `ppu_main_parked` | nombre:temps des threads PPU (tous, et le principal) arrêtés derrière un verrou |
| `park_spin`, `park_spin_budget_us` | état du réglage |

Critères, lus sur les deux côtés de la comparaison (même scène, même Core, même session) :

- **le levier agit** si, levier actif, le temps d'acquisition par verrou (`wl_putllc`, deuxième valeur divisée par
  la première) et le temps des arrêts lents baissent, sans baisse des images par seconde ;
- **il n'agit pas** si les deux côtés se valent : les cessions de cœur n'étaient pas le coût ;
- si, levier actif, `wl_putllc_over_budget` et `wl_putllc_slow_park_ms` portent l'essentiel du temps d'arrêt, le
  coût vient de threads PPU qui ne sont pas sur un cœur. Indice déjà mesuré sur l'iPhone, pour GOW3 (718, session 5,
  fenêtre 15) : 3 325 verrous, 12,1 ms de phase d'arrêt dont un seul arrêt de 3,9 ms et dix arrêts de plus de 50 µs.
  Le correctif suivant est alors une cession dirigée vers le thread attendu ;
- `ppu_main_parked` donne enfin la part du temps où le thread principal est arrêté : c'est elle qui dit si la
  cadence est bornée par ces arrêts.

`REWINDBOX_AUTO_STORM_CAPTURE_917` : quand deux fenêtres de suite comptent au moins 100 000 PUTLLC lourds, le
rapport demande lui-même, une fois par démarrage, la trace des PUTLLC lourds et un profil des régions PPU
(`COREPROF AUTOSTORM917`, `trigger=auto_heavy_putllc`). Il n'y a rien à activer. Sur GOW3 (2 029 à 4 484 par
fenêtre) rien n'est demandé.

## 6. Écarté, avec la raison

- **Refaire tourner le thread PPU après chaque attente temporisée.** Dans la fenêtre 12, un thread PPU réveillé ne
  teste le mot du verrou qu'une fois avant de se rendormir 50 µs, et échoue une fois sur trois (1,53 attente par
  épisode). Le faire tourner à nouveau raccourcirait ces épisodes, mais il sortirait alors avant d'être marqué
  affamé, donc sans la fenêtre de grâce du Core 664 — celle qui a mis fin aux arrêts de 9 à 40 s de BO2 quand le
  verrou est tenu 87 % du temps. Pas de changement de cette attente sans mesure.
- **Cession dirigée dès ce Core.** Elle vise un thread PPU hors d'un cœur ; rien ne dit encore que c'est le cas de
  BO2. La comparaison et l'histogramme ci-dessus le diront.
- **PUTLLC relâché, comparaison sans verrou, protection de page** : refus maintenus (un écrivain PPU simple entre la
  comparaison et l'écriture est perdu ou ignoré).

## 7. Limites

- Le gain en images par seconde n'est pas connu. Si le thread PPU principal n'est pas le maillon lent, raccourcir
  ses arrêts ne changera pas la cadence.
- Le nombre de PUTLLC lourds par image est une propriété du jeu ; ce Core n'y touche pas.
- Les exports doivent contenir les fenêtres de BO2 : exporter juste après la session, avec le fichier `.1`.
- La comparaison demande environ deux minutes de jeu continu dans la scène lente (22 fenêtres de 5 s) ; plus court,
  elle est partielle et l'analyseur n'imprime que les côtés qui ont au moins une fenêtre.
- La première fenêtre de chaque côté contient la bascule (quelques millisecondes sur 5 s).

## 8. Protocole iPhone

1. Black Ops II, réglage « Writer lock park spin » laissé sur Automatique : lancer la partie et rester environ deux
   minutes dans une scène lente, sans ouvrir le menu.
2. God of War III : **démarrer le jeu normalement (pas depuis une sauvegarde d'état)**, jouer une minute dans la
   scène lente, puis créer une nouvelle sauvegarde d'état si besoin. Une sauvegarde d'état créée avant ce Core
   garde la mémoire du démarrage sans le contournement MLAA.
3. Quitter le jeu puis exporter les journaux aussitôt, avec les fichiers `.1`.

Ce que l'export doit contenir : BO2 — `COREPROF AUTOSTORM917`, `COREPROF PARKCMP917` (étapes 1 à 16),
`RANGELOCKPROF … park_spin=`, les deux captures (`trigger=auto_heavy_putllc`) ; GOW3 —
`COREPROF GOW3MLAA909 … ppu=applied ppu_patch=100`, `COREPROF AUTOPPU916` si le thread principal dépasse 0,85 cœur.
