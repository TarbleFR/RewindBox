# RPCS3 Core 924 — gel de Black Ops II : le SPU ne garde plus sa ligne verrouillée pendant qu'il cède la place au PPU

Core 924 = Core 923 + une correction du moteur (section 3). Côté application, la base RPCS3 ne déclenche plus le
streaming asynchrone des textures sur iOS (section 5). **Aucune mesure iPhone n'a encore été faite avec ce Core.**

## 1. Données d'entrée (export de l'appareil, build 724, PID 50194)

Black Ops II (BLES01717), session 8, entrée de la base + 1 réglage par jeu, réservations SPU exactes.

| Fenêtres de 5 s | Images/s | `putllc_ok` | `putllc_heavy` | `getllar_sleep` | Fenêtres de grâce ouvertes | Verrous d'écriture différés |
|---|---|---|---|---|---|---|
| 10 à 40 (jeu) | 20-35 | 2,0 M (fenêtre 38) | 1,4 M | 71 | 1 516 | 2 609 (499 ms) |
| 41 (gel) | 0 | 7,6 M | 6,0 M | 0 | 6 010 | 8 671 (994 ms) |
| 42 (gel) | 0 | 8,5 M | 6,7 M | 0 | 6 155 | 8 768 (1 012 ms) |

Avant le gel, quatre arrêts courts de la même forme : 1 067 ms (fenêtre 25), 601 et 598 ms (31, 32), 579 ms (39).

Relevé de gel (`FREEZE_DUMP`, 3,0 s sans image, 4,4 cœurs occupés) :

- le thread principal attend un sémaphore depuis 3,2 s ;
- le thread PPU `Secondary` (0,97 cœur) détient une réservation sur 0x2e208d8 au temps 0x83d1ee800, alors que le mot de
  cette ligne vaut 0x83d1ee840 — verrou d'un autre thread — sur deux lectures séparées de 27 µs ; entre les lectures
  précédentes le mot avançait d'un temps toutes les 1 à 1,3 µs ;
- les six SPU SPURS sont en GETLLAR/PUTLLC sur les lignes 0x2e20880 et 0x2e20c00, aucun ne dort.

Le mot de réservation ne recule pas : dans le relevé, les lignes de mémoire sont lues **avant** les threads (leurs `ts=` sont
antérieurs). L'écart relevé sur la build 723 (mot inférieur au temps détenu) venait de cet ordre de lecture ; l'hypothèse
d'un mot qui recule est écartée.

## 2. Défaut (code)

`spu_thread::do_putllc` (réservations exactes, PUTLLC qui change des données) :

1. verrouille sa ligne (`rsrv_unique_lock` sur le mot de réservation) ;
2. prend `vm::writer_lock`, qui commence par céder la place à un PPU affamé et à la fenêtre de grâce que ce PPU ouvre en
   repartant (`passive_gate::defer_writer`, CELL571 et REWINDBOX_PPU_GRACE_664 : jusqu'à 500 µs, 100 µs par fenêtre) ;
3. gare tous les PPU, compare, écrit, libère.

Pendant l'étape 2 la ligne reste verrouillée. Or l'écriture conditionnelle du PPU (`ppu_store_reservation`) échoue sur une
ligne verrouillée. Quand la prochaine étape du PPU porte sur la ligne que les SPU scrutent — ici la file de travaux —, le
premier SPU arrivé garde cette ligne pendant toute la fenêtre ouverte pour le PPU, et le PPU passe ses fenêtres à échouer.
Les SPU, sans travail, tournent à plein sur la ligne, ce qui gare le PPU plus souvent encore : le gel s'entretient.

## 3. Correction (`REWINDBOX_GATE_BEFORE_LINE_924`)

Le SPU cède la place **avant** de verrouiller sa ligne (`passive_gate::ahead_scope` dans `do_putllc`), et le verrou
d'écriture qui suit ne cède pas une seconde fois (`defer_writer_once`). Mêmes attentes, même borne de 500 µs. Le temps de
réservation et le contenu de la ligne sont validés après l'attente par le même `fetch_op` et la même comparaison sous le
verrou d'écriture : un PUTLLC dont la ligne a changé pendant qu'il attendait échoue, comme à tout autre moment.

Non modifiés : l'écriture conditionnelle de ligne entière du PPU et l'écriture de 128 octets (ni l'une ni l'autre n'est sur
le chemin observé, et `PPUThread.cpp` entre dans l'identité des caches PPU).

`SPUThread.cpp` ne change que dans le corps hôte de `do_putllc`, plus une inclusion, avec un alias exact vers l'empreinte
effective déjà livrée (procédure des Cores 911, 912, 914 et 916) : **identités de code généré PPU/SPU inchangées, les caches
du joueur restent valides.**

## 4. Contrôle (hôte)

`test/rpcs3_gate_line924_test.py` vérifie l'ordre dans la source et compile `test/native/rpcs3_gate_line924_model.cpp` avec
le vrai `ios/IOSPassiveLockGate.h` (g++, clang++, ASan+UBSan) :

- **déterministe** : pendant qu'un SPU cède la place à la fenêtre d'un autre thread, le mot de la ligne vaut 64 (verrouillé)
  dans l'ordre du Core 923 et 0 (libre) dans l'ordre du Core 924 ; l'écriture se termine et avance le temps une fois dans les
  deux cas ; un `ahead_scope` attend la fenêtre et le verrou suivant n'attend plus ; sans fenêtre personne n'attend ;
- **tempête** (3 SPU qui écrivent sans pause sur la ligne dont le PPU a besoin, 600 ms, hôte 4 cœurs, six exécutions) :
  écritures PPU réussies 77 000 à 362 000 avant, 522 000 à 1 172 000 après (×3 à ×13). Dans ce modèle les écritures SPU
  baissent (218-291 par ms avant, 42-162 après) : le PPU du modèle n'écrit que sur cette ligne, ce qui fait échouer les
  PUTLLC des SPU. Le modèle ne reproduit ni la cadence de l'iPhone ni un gel complet ; il ne dit rien des images par seconde.

## 5. God of War III : streaming asynchrone des textures retiré de ce que la base applique sur iOS

Build 724, BCES00510, premier lancement de l'entrée de la base telle quelle (`CONFIG_LAYERS database=1 legacy_custom=0`,
100 %, `async_tex=true`, `mt_rsx=false`) : défauts graphiques qui rendent le jeu injouable, au démarrage normal (sessions 1 à
3) comme à la reprise d'une sauvegarde d'état (sessions 4 et 6). La build 723, jouable, différait par `async_tex=false`,
75 % et `mt_rsx=true`. Le journal ne contient aucune ligne qui désigne le réglage fautif : **l'attribution au streaming
asynchrone est une hypothèse**, appuyée par deux retraits antérieurs du même réglage (builds 552 et 610, God of War III et
Assassin's Creed).

`Rpcs3ConfigAdapter.sanitiseForIOS` n'applique plus `Asynchronous Texture Streaming: true` venant de la base (179 entrées
sur 2 187 ; aucune entrée vidée). Toutes les autres valeurs de la base restent ; le réglage par jeu « Asynchronous texture
streaming » (GPU → Rendering) permet toujours de l'activer. Les tests Dart modifiés tournent dans le groupe Flutter de la
livraison (pas de Flutter ici) ; la règle a été recalculée en Python sur les 2 187 entrées.

Le bypass MLAA à la reprise d'une sauvegarde d'état (Core 922) est confirmé sur l'appareil : `GOW3MLAA909
ppu=savestate_applied`, plus aucune relecture du tampon 1280×720 après la deuxième fenêtre (72-107 par fenêtre avant).

## 6. Bilan

- **Coût supprimé** : le verrou de ligne tenu par un SPU pendant qu'il attend le PPU (115 µs par attente, 8 671 attentes par
  fenêtre de 5 s au moment du gel). Le PPU peut écrire sur la ligne scrutée pendant les fenêtres ouvertes pour lui.
- **Coût restant** : chaque PUTLLC exact qui change des données gare toujours tous les PPU (1,4 million par fenêtre de 5 s
  en jeu, soit 273 000 par seconde). C'est la limite des 20-35 images/s de Black Ops II et la cause de leur oscillation ;
  cette correction ne la retire pas.
- **Chemin critique** : thread PPU `Secondary` → file de travaux → SPU ; l'image attend le thread principal, qui attend ces
  travaux.
- **Mémoire** : inchangée par ce Core. Mesure nouvelle (MEMPARTS923) : en 2 minutes de jeu, l'empreinte de Black Ops II
  passe de 3,40 à 4,06 Go, dont la part graphique du noyau de 0,91 à 1,39 Go, alors que le cache de textures reste à
  100-110 Mo. Origine non attribuée.
- **Risques** : un SPU qui a cédé la place voit plus souvent son PUTLLC échouer (la ligne a changé) et recommence ; pas de
  mesure iPhone. Aucune réservation ignorée, aucune attente supprimée, aucun seuil GETLLAR, aucun mode relâché, nombre et
  priorités des SPU inchangés. Pour God of War III : si les défauts graphiques persistent sans le streaming asynchrone,
  l'hypothèse est fausse et il reste 100 % et le RSX monothread à départager.

## 7. God of War III : ce que disent les nouveaux relevés (pas encore corrigé)

`SPUPROF923`, sessions 4 et 6 (jeu, 11-17 images/s) : trois noyaux SPURS « Big » actifs 91-93 % du temps, le noyau « Little »
86-92 %, deux autres 10-13 % ; les échantillons se répartissent sur de nombreuses régions (0x4400, 0xd300, 0xd400, 0x10a00,
0x5b00, 0x9900 pour les « Big » ; 0x4900 pour 20-24 % du « Little »). C'est du travail réparti, pas une boucle d'attente sur
une adresse. Le jeu demande 3,3-3,4 cœurs de SPU sur un appareil à 2 cœurs performants ; 180 000 à 360 000 PUTLLC lourds par
fenêtre garent en plus le PPU principal (0,90-0,96 cœur).

## 8. Protocole iPhone

- Black Ops II : même partie, 10 minutes ou jusqu'à un gel, export aussitôt. À lire : durée maximale d'image par fenêtre
  (les arrêts de 0,6-1 s), `FREEZE_EPISODE`, `SPUWAIT551 putllc_ok/putllc_fail`, `PPUGRACE664`.
- God of War III : démarrage normal, dire si les défauts graphiques ont disparu ; `CONFIG_LAYERS async_tex=false` attendu.
