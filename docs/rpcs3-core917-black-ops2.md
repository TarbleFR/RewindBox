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

## 4. Test discriminant (hôte)

`test/rpcs3_writer_park917_test.py`, 20 vérifications sur l'en-tête réel :

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

Critères, sur la même scène que 676/718 (jeu en cours, scène lente) :

- **le levier agit** si le temps d'acquisition par verrou (`wl_putllc`, deuxième valeur divisée par la première)
  descend nettement sous 1,8 µs et si l'histogramme se concentre sous 1 µs ;
- **il n'agit pas** si `wl_putllc_over_budget` et `wl_putllc_slow_park_ms` dominent : le coût vient alors de
  threads PPU hors d'un cœur, et le correctif suivant est une cession dirigée vers le thread attendu ;
- `ppu_main_parked` donne enfin la part du temps où le thread principal est arrêté : c'est elle qui dit si la
  cadence est bornée par ces arrêts.

`REWINDBOX_AUTO_STORM_CAPTURE_917` : quand deux fenêtres de suite comptent au moins 100 000 PUTLLC lourds, le
rapport demande lui-même, une fois par démarrage, la trace des PUTLLC lourds et un profil des régions PPU
(`COREPROF AUTOSTORM917`, `trigger=auto_heavy_putllc`). Il n'y a rien à activer. Sur GOW3 (2 029 à 4 484 par
fenêtre) rien n'est demandé.

## 6. Limites

- Le gain en images par seconde n'est pas connu. Si le thread PPU principal n'est pas le maillon lent, raccourcir
  ses arrêts ne changera pas la cadence.
- Le nombre de PUTLLC lourds par image est une propriété du jeu ; ce Core n'y touche pas.
- Les exports doivent contenir les fenêtres de BO2 : exporter juste après la session, avec le fichier `.1`.
