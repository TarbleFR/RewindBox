# RPCS3 iOS 583 — pré-validation des textures affinée d'après les journaux iPhone du 581

28 octobre 2026. Ce Core part des **premiers journaux iPhone du build 581**
(God of War III et Black Ops II) et s'applique au Core 581 (`0395645`, run
`40631132527`). **Aucun gain 583 n'est mesuré sur iPhone.**

## 1. Ce que montrent les journaux 581

### God of War III (`BCES00510`)

Fenêtres de 5 s en jeu, scènes d'environ 700 appels de dessin par image,
comparées à la 575 (`RSXFRAME551`, `FRAMEPROF527`, `JITMEM`, `COREPROF OPT581`) :

| | 575 (fenêtres 5-8) | 581 (fenêtres 4-7) |
|---|---:|---:|
| Images par fenêtre (fps) | 90-102 (18-20,4) | 132-153 (26,4-30,6) |
| Intervalle médian | 48,8-54,0 ms | 32,3-38,1 ms |
| `texture_ms` du RSX par image | 8,6-12,5 ms | 4,3-5,8 ms |
| Hachage restant au thread RSX par image | 6,5-9,1 ms | 2,1-3,2 ms |

Dans les scènes chargées (2 100-2 600 appels de dessin), le gain est faible :
61-64 images par fenêtre (12-13 fps, médiane 77-80 ms) contre 60 (médiane
82-84 ms) en 575. Le 579 est aussi entre ces deux mesures : les chiffres sont
ceux du 579 + 581 ensemble, sur des scènes comparables, pas identiques.

Le thread auxiliaire a servi **56 %** des validations de 64 Kio et plus
(hits/(hits+misses) des fenêtres 2-10 de la session 5). Il a haché 82,7 Go
pour 42,9 Go servis : **48 % de son travail n'a servi à rien**. À 17 Go/s, il
tourne sur un cœur de performance.

Les compteurs `JITMEM texture_hash_*` comptent tout hachage hybride, celui du
RSX comme celui du thread. Le hachage restant au RSX est donc
`texture_hash_ticks - worker_ms`.

### Black Ops II (`BLES01717`)

- **Limité par les SPU, pas par le RSX.** Les threads SPU prennent 3,4 à 4,1
  cœurs, le thread RSX 0,1 à 0,5 (`COREPROF frames=`, session 7).
- **Le thread auxiliaire y sert peu.** Il fournit 20 à 28 % des validations,
  pour jusqu'à 0,13 cœur de travail, et saute 1 756 à 4 602 plages de mémoire
  principale par fenêtre en session 6 : des verrous d'écriture exclusifs des
  SPU sont posés.
- **Les gels sans image** (`FREEZE_DUMP no_frames` de 3,0, 6,6 et 7,6 s)
  coïncident avec des compilations de pipelines Vulkan (jusqu'à 15 par
  fenêtre, 5,5 s cumulées, 0,66 s au plus) et de blocs SPU pendant le jeu.
  C'est le premier passage dans ces zones (règle mainteneur n° 5) : un second
  lancement du même mode doit trouver les caches remplis.

**Correction.** Le doc 581 disait « Dragon Ball Z et Black Ops II ne hachent
rien », d'après `JITMEM`. Or ce compteur ne voit que le hachage hybride, actif
seulement avec le lot FPS de God of War III. Black Ops II hache en réalité des
milliers de textures par fenêtre (5 000 à 20 000 validations). Pour Dragon
Ball Z, aucun compteur ne le mesure.

## 2. Le changement

**`CELL583_PREHASH_PACING`** (Core 581, mêmes fichiers iOS) :

- **Automatique = God of War III seul**, dont le thread RSX limite les images.
  Black Ops II et Bladestorm repassent au hachage sur le thread RSX. *Activé*
  reste possible pour tout titre avec « Texture Validation Per FIFO Batch ».
- **Le thread ne hache plus une plage que le RSX a déjà dépassée.** Il lit la
  position du RSX dans les validations de l'image (`g_position`, atomique),
  hors verrou ; compteur `worker_passed`.
- **Réveil par la progression du RSX.** Quand le RSX atteint la moitié des
  plages préparées, il réveille le thread pour la suite, au lieu d'attendre
  le délai de 4 ms ; compteur `worker_refills`.
- Nouvelle ligne de profil **`COREPROF OPT583`**. `OPT581` est inchangée.

Contrat inchangé : un résultat ne sert que dans l'époque où il a été calculé,
jamais après une écriture du RSX (573), et la mémoire principale n'est lue que
sous verrou de plage. Hors iOS, chaque fichier commun est celui du 581.
Identités de codegen PPU/SPU inchangées : **pas de recompilation à froid**.

## 3. Vérifications (hôte)

Rapport : [`evidence/rpcs3-cell583-host-linux.json`](evidence/rpcs3-cell583-host-linux.json).

- Delta canonique rematérialisé sur l'amont `22f1152`. Préimages 581
  authentifiées par la fixture 583, préimages 579 par la fixture 581.
- Le modèle du 581 (bloc du thread, `sync`, `protect`, hachage, vraie
  réservation, protocole de verrou de plage, démappeur) tourne deux fois :
  avec le thread 581 et avec le thread 583.

  Le rapport du test (un passage, GCC 13) donne 70,6 % contre 83,3 % en
  régime établi (ASan 80,6 %, TSan 79,4 %) et 29 % contre 67 % en boucle
  serrée. Ce modèle est bruité sur un hôte partagé : sur six passages
  répétés (GCC 13, sans sanitizer) :

  | Modèle, 6 passages | Thread 581 : médiane (min-max) | Thread 583 : médiane (min-max) |
  |---|---:|---:|
  | Validations servies, régime établi | 81,3 % (51,6-82,1) | 84,1 % (82,5-89,7) |
  | Validations servies, boucle serrée | 66,7 % (57,1-74,6) | 77,8 % (69,0-79,4) |
  | Textures périmées acceptées | 0 | 0 |

  En régime établi, l'écart est faible et un passage Clang isolé a même donné
  81,7 % au 581 contre 77,4 % au 583. Le gain net du modèle est surtout dans
  la boucle serrée (le RSX dépasse le thread), qui est le cas des scènes
  chargées de God of War III.

- Les deux mutations du 581 (sans contrôle d'époque, sans contournement après
  une écriture du RSX) sont toujours rejetées avec le thread 583.
- Pour la course avec le démappage, la boucle du modèle est plus longue
  (40 000 images au lieu de 4 000). Sur un hôte chargé, le démappeur pouvait
  gagner toutes les courses dans la borne du 581.
- Les 4 unités touchées compilent pour ARM64 (`RPCS3_IOS`) avec les mêmes
  diagnostics que le 581.
- Contrat d'épinglage, ordonnancement des Cores et contrat du pilote 583 :
  139 entrées.

Ce sont des vérifications sur l'hôte, pas des mesures sur iPhone.

## 4. Core iPhone (Mac de la CI)

Run `40683438937` depuis `8ebca28` (macOS 15, Apple Silicon, Apple clang 17,
Xcode 16.4) ; rapport :
[`evidence/rpcs3-cell583-macos.json`](evidence/rpcs3-cell583-macos.json).

- Le Core 581 (`0395645`, run `40631132527`) est authentifié avant tout, puis
  le modèle passe sur ARM64 avec les deux threads (un passage chacun) :

  | Modèle (Apple clang 17, ARM64) | Thread 581 | Thread 583 | 583 ASan/UBSan | 583 TSan |
  |---|---:|---:|---:|---:|
  | Validations servies, régime établi | 69,8 % | 83,7 % | 62,7 % | 72,6 % |
  | Validations servies, boucle serrée | 37 % | 85 % | 59 % | 64 % |
  | Textures périmées acceptées | 0 | 0 | 0 | 0 |

  Les passages avec sanitizers sont lents et bruités : ils servent à la
  sûreté (aucune faute, aucune course signalée), pas à la mesure. Les deux
  mutations sont rejetées. Pendant 1 677 démappages (thread 583, sans
  sanitizer), aucune lecture de mémoire retirée.
- Core iPhone compilé depuis la source vérifiée : SHA-256
  `9aa3c7ee…57f4`, 88 exports, chargement passif, 139 entrées enregistrées.
  Les marqueurs 581 et 583 sont dans le binaire. Identités de codegen
  inchangées : **pas de recompilation à froid**.
- Le pilote du run vérifie deux fois `COREPROF OPT583` et pas
  `COREPROF OPT581` (erreur de recopie) ; la présence de `OPT581` dans le
  binaire est vérifiée par la preuve Mac et par le validateur RPCS3 de l'IPA.

## 5. À relever sur iPhone

- **God of War III** :
  - `OPT581` : hits contre misses, `worker_ms` ;
  - `OPT583` : `worker_passed`, `worker_refills` ;
  - hachage restant au RSX : `JITMEM texture_hash_ticks - worker_ms` ;
  - `RSXFRAME551 texture_ms` et FPS, dans les mêmes scènes qu'en 581.
- **Black Ops II** : `OPT581 texture_prehash=0`, puis cœurs SPU et FPS en jeu,
  au second passage dans les mêmes zones.

## 6. Relecture de God of War III : piste retirée, remplacée par le 585

Dans les journaux 581 (session 5, fenêtres 2 à 10), God of War III relit
**une cible de rendu de 3,69 Mo par image** (1280 × 720 × 4 octets) :
`READBACK555 fault_read` compte une relecture par image, pour 2,1 à 7,2 ms
par image. C'est la GameDB qui active `Write Color Buffers` pour ce titre ;
le backend Vulkan protège alors chaque cible de couleur liée, et la lecture
du jeu attend le GPU.

Désactiver ce réglage n'est **pas** retenu : le mainteneur l'a retiré des
réglages proposés aux joueurs, aucun réglage ne doit leur être demandé, et le
jeu en a besoin (éclairage, cinématiques, d'après une source communautaire).
Le Core 585 ([`rpcs3-cell585.md`](rpcs3-cell585.md)) s'attaque à l'attente
elle-même : la soumission anticipée des commandes (561) devient automatique
pour God of War III.
