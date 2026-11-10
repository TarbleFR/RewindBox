# RPCS3 iOS 581 — pré-validation des textures par un thread auxiliaire (God of War III)

28 octobre 2026. Ce Core part des journaux du **build 575** et s'applique au
Core 579 (`1f82f9d`, run `40621029169`). **Aucun gain 581 n'est mesuré sur
iPhone.**

## 1. Ce que montrent les journaux

Sur iOS, le cache de textures vérifie par une empreinte (XXH3) que le jeu n'a
pas modifié une texture : la protection de pages est exclue à cause de
l'arène JIT scellée. Avec « Texture Validation Per FIFO Batch » (559), une
texture est hachée de nouveau à sa première utilisation après chaque point de
synchronisation : nouveau PUT du jeu, acquisition de sémaphore, fin d'image.
C'est le thread RSX qui fait ce travail.

| Build 575, God of War III (fenêtres de 5 s en jeu) | Valeur |
|---|---:|
| Temps de hachage sur le thread RSX | 461 à 815 ms |
| Par image | 2,8 à 10,4 ms (13 à 17 % de l'image) |
| Octets hachés | 7 à 10 Go |
| FIFO du RSX occupée | 72 à 95 % |

Dragon Ball Z et Black Ops II ne hachent rien. Une image valide presque les
mêmes plages, dans presque le même ordre, que la précédente.

## 2. Le changement

**`CELL581_TEXTURE_PREHASH`** (nouveau réglage *Texture Pre-Validation*,
Automatique = les titres à époques de validation : God of War III, Black Ops
II, Bladestorm).

- Le RSX note, image par image, les plages qu'il valide (64 Kio et plus).
- Dès qu'une époque commence, un thread auxiliaire hache les plages que
  l'image précédente a validées ensuite, avec la fonction de hachage du cache
  elle-même (résultats identiques bit à bit). Il publie chaque résultat avec
  l'époque, lue **avant** les octets.
- Le RSX utilise un résultat seulement dans cette même époque. Tout ce que les
  commandes d'une époque peuvent lire a été écrit avant qu'elle commence :
  c'est la garantie du 559, inchangée.
- Une section revalidée par une écriture du RSX à l'intérieur de l'époque
  (573) est toujours hachée par le RSX lui-même.
- Le thread lit la mémoire locale RSX, jamais démappée tant que le RSX
  tourne. Il ne lit la mémoire principale que sous un verrou de plage de la VM
  (`range_readable`) : un démappage l'attend, et un changement de carte
  mémoire en cours lui fait sauter la plage. Les écrivains atomiques SPU
  (PUTLLC) ne l'attendent pas.
- Tout ce que le thread n'a pas haché, le RSX le hache comme avant. Désactivé
  rend exactement le comportement 579.
- Le thread tourne dans la même classe QoS que les SPU et PPU, sous le RSX. Il
  s'arrête à la sortie du thread RSX et ne repart qu'au démarrage suivant.
- Profil : nouvelle ligne `COREPROF OPT581` (validations servies, ratées,
  octets et temps du thread auxiliaire).

Hors iOS, chaque fichier commun est celui du 579. Aucun fichier de l'identité
de codegen PPU/SPU n'est touché : **pas de recompilation à froid**.

## 3. Vérifications (hôte)

Rapport : [`evidence/rpcs3-cell581-host-linux.json`](evidence/rpcs3-cell581-host-linux.json).

- Delta canonique rematérialisé sur l'amont `22f1152` ; préimages 579
  authentifiées par la fixture inverse. Identités de codegen PPU
  `a987639e9f838d1c` et SPU `d070cb361bdef607`, inchangées.
- Modèle hôte : le vrai code (bloc du thread, `sync`, `protect`,
  `fast_hash_internal`, en-têtes) est compilé à côté de la version 579, sur
  une vraie réservation d'adresses, avec le protocole de verrou de plage de la
  VM et un « démappeur » qui retire la mémoire principale pendant que le
  thread la lit.

  | Mesure (GCC 13) | Sans sanitizer | ASan/UBSan | TSan |
  |---|---:|---:|---:|
  | Validations servies par le thread (régime établi) | 84 % | 81 % | 81 % |
  | Textures périmées acceptées | 0 | 0 | 0 |

  - Les modifications du « jeu » entre époques et les écritures RSX à
    l'intérieur d'une époque sont toutes détectées.
  - Sans le contrôle d'époque, ou sans le contournement après une écriture
    RSX, le modèle accepte une texture périmée : les deux mutations sont
    rejetées par le test.
  - Pendant les démappages, le thread saute la plage ou la lit entre deux
    démappages, sans aucune faute mémoire.
  - Désactivé, le 581 valide exactement comme le 579.
  - Après l'arrêt du RSX, aucune validation ne relance le thread.
- Les 8 unités touchées compilent pour ARM64 (`RPCS3_IOS`) avec exactement
  les diagnostics du 579.

Ce sont des vérifications sur l'hôte, pas des mesures sur iPhone.

## 4. Core iPhone (Mac de la CI)

Run `40631132527` depuis `0395645` (macOS 15, Apple Silicon, Apple clang 17,
Xcode 16.4) ; rapport :
[`evidence/rpcs3-cell581-macos.json`](evidence/rpcs3-cell581-macos.json).

- Le Core 579 (`1f82f9d`, run `40621029169`) est authentifié avant tout, puis
  le modèle 581 passe sur ARM64 :

  | Mesure (Apple clang 17, ARM64) | Sans sanitizer | ASan/UBSan | TSan |
  |---|---:|---:|---:|
  | Validations servies par le thread (régime établi) | 81 % | 79 % | 71 % |
  | Textures périmées acceptées | 0 | 0 | 0 |

  Les deux mutations sont rejetées. Pendant 1 771 démappages (sans
  sanitizer), le thread n'a jamais lu de mémoire retirée.
- Core iPhone compilé depuis la source vérifiée : SHA-256
  `a6e97d33…213c`, 88 exports, chargement passif. Les quatre marqueurs 581
  sont présents dans le binaire. Les identités de codegen sont inchangées :
  **pas de recompilation à froid**.

## 5. À relever sur iPhone (God of War III)

- `COREPROF OPT581` : `hits` contre `misses`, et `worker_skips` (mémoire
  principale indisponible).
- `JITMEM texture_hash_ticks` : le temps que le RSX passe encore à hacher.
- FPS, temps d'image, et occupation et CPU du thread RSX.

## 6. Premiers journaux iPhone (28 octobre)

Voir [`rpcs3-cell583.md`](rpcs3-cell583.md), section 1. Dans des scènes
comparables de God of War III (579 + 581 contre 575) :
- 26-30 fps au lieu de 18-20 ;
- `texture_ms` du RSX passé de 8,6-12,5 à 4,3-5,8 ms par image ;
- 56 % des validations servies par le thread auxiliaire, 48 % de son travail
  perdu.

Black Ops II est limité par les SPU, et le thread y sert 20 à 28 % des
validations : le 583 le retire de l'Automatique.

Correction de la section 1 : `JITMEM` ne compte que le hachage hybride (lot FPS
de God of War III). Black Ops II hache bien des milliers de textures par
fenêtre ; Dragon Ball Z n'est pas mesuré.
