# IPA 833 : Hogwarts Legacy s'arrête encore faute de mémoire de l'appareil (pid 24974)

24 novembre 2026. Sources : journaux privés de l'appareil (core, stderr, performance, launch, crash) reçus le
24 novembre après l'essai de l'IPA 833 (Core `659f4f01`, empreinte `f6cc6f72`), session 24974 (Hogwarts Legacy,
processus neuf), comparée aux sessions des IPA 822 à 830 encore présentes dans les mêmes fichiers. Seuls des
comptes, des tailles et des durées sont repris ici. Aucune mesure nouvelle n'a été faite sur l'iPhone.

## 1. Déroulé

- Lancement à 15:12:55, première image à 15:13:04. Alertes mémoire d'iOS à 15:13:52, 15:14:34, 15:14:40,
  15:16:10, 15:16:27 et 15:16:52. Dernière ligne du moteur à 15:16:58. Le journal de cycle de vie ne contient ni
  `willResignActive` ni `didEnterBackground` : l'application s'est arrêtée au premier plan, comme sur la 830.
- Empreinte (relevés du moteur toutes les 30 s) : 2 641 Mio à 6 s, puis 3 624, 4 494, 4 787, 4 686, 4 897, 5 205
  et 5 262 Mio. Mémoire disponible de l'appareil : 31 %, 11 %, 8 %, 6 %, 6 %, 5 %, 5 %, 4 %. Marge du processus à
  la fin : 1,7 Gio. C'est l'appareil qui manque de mémoire, pas la limite du processus.
- 30 images/s au début ; 14 à 21 images/s à 171-173 s de jeu, quand l'échantillonneur saute 34 s : le processus
  attend qu'iOS relise de la mémoire compressée.
- Sessions Hogwarts précédentes, première alerte mémoire : 822 à 52 s (4 494 Mio), 830 à 54 s (4 425 Mio), 833 à
  55 s (4 467 Mio). Rien n'a changé sur ce point.

## 2. POOL_830 : pas d'effet sur le tas des gros objets

- LOH : 531 Mio à 4 s, compacté à la première image (506 → 265 Mio, sans espace libre), 543 Mio 20 s plus tard
  dont 221 Mio libres, puis 537 Mio jusqu'à la fin, dont 200 à 290 Mio libres. Sessions Hogwarts de la 830 :
  491 à 509 Mio, dont 153 à 255 Mio libres. Le pool n'a pas fait baisser le LOH.
- Allocations du fil GPU : 15 à 50 Mio par fenêtre de 5 s en jeu, 102 à 271 Mio pendant les chargements.
- La source principale du LOH n'est donc pas `MemoryOwner<T>`. Elle n'est pas identifiée.

## 3. Où est la mémoire (fin de session, environ 5,1 Gio)

- Graphique (registre « graphics » du noyau) : 1 192 Mio, plus 248 Mio compressés. MoltenVK compte 1 511 Mo
  alloués par Metal, dont 774 Mio par les allocations Vulkan du moteur (images 419 Mio, tampons 355 Mio) : il reste
  environ 700 Mo d'objets Metal hors de ces allocations.
- Tas .NET : environ 1 Gio engagé. Le LOH fait 537 Mio, dont environ 250 Mio libres. La gen2 passe de 166 à
  404 Mio.
- Code traduit par le JIT : au moins 640 Mio. Le journal écrit une ligne par tranche de 64 Mio atteinte : 7 avant
  la première image, 10 à 15:14:07. L'arène de code ne libère jamais de code. Le détail chiffré de ces lignes est
  masqué par le filtre de secrets du journal (une valeur qui commence par `clé=valeur`) ; il faut le rendre lisible.
- Tas natif : non relevé dans cette session. Sur la 830, en jeu (pid 19155, 150 s), la zone malloc par défaut
  utilise 498 Mio. Le relevé natif de SSBU (830, 120 s) compte 455 Mio vivants ; les plus grosses piles sont des
  allocations de Metal et du pilote GPU appelées par MoltenVK pendant la création des pipelines.
- Au début de la session, avant le chargement du jeu, l'empreinte est déjà de 1 386 Mio, comme pour toutes les
  sessions lues (1 371 à 1 402 Mio).

## 4. Pipelines

- Cache de shaders : 2 274 programmes lus au lancement (1 734 graphiques, 540 de calcul), 267 Mio de code hôte.
- 2 410 variantes graphiques rejouées au lancement (2 509 prévues pour 616 programmes). En 3 min 20, 1 170 sont
  utilisées avant leur premier dessin, 175 sont créées en jeu (7,8 s d'attente au total) et 337 sont compilées pour
  des dessins sautés.
- MoltenVK, cumul du processus : 5 032 objets de pipeline Metal compilés (9,4 ms en moyenne) et 4 088
  bibliothèques Metal compilées depuis le MSL (49 ms en moyenne). Aucune fonction spécialisée.
- Première lecture de VARIANT_CAUSES (classement des états nouveaux en jeu) : 508 états nouveaux pour leur
  programme. Pour 203 d'entre eux (40 %), l'état le plus proche que leur programme avait déjà ne diffère que par un
  état que MoltenVK applique en dehors de l'objet de pipeline Metal : face éliminée (54), comparaison de profondeur
  (13), stencil (136). 302 diffèrent par l'entrée des sommets, 3 sont le premier état de leur programme.
- Dans MoltenVK 1.4.2, chaque pipeline Vulkan demande une nouvelle `MTLFunction` à sa bibliothèque et compile son
  propre objet de pipeline Metal. Ces 203 variantes donnent donc des descripteurs identiques à un pipeline existant,
  mais Metal compile et garde un second objet de pipeline : 2 374 ms de compilation en jeu pour ces seules
  variantes.

## 5. Suite

- Partager un même objet de pipeline Metal entre pipelines Vulkan dont le descripteur Metal est identique
  (dixième partie du correctif MoltenVK), et une même `MTLFunction` par bibliothèque. Les états propres à chaque
  pipeline Vulkan (face éliminée, profondeur, stencil) restent appliqués à chaque dessin. Vérification sur macOS :
  pixels, mémoire et temps de création.
- Rendre lisibles les lignes `jitArena` du journal.
- Rien n'est mesuré sur l'iPhone.

## 6. Dixième partie de MoltenVK : vérifiée sur macOS, épinglée

- Commits `f0d7a051b` (la partie) et `1d413b0a5` (la ligne de journal écrite par le pipeline : la première version ne
  compilait pas).
- Mesure macOS (run 45440045776, vrai GPU Metal du runner) : 11 variantes de rasterisation d'un même programme
  dessinées avec et sans la partie donnent les mêmes pixels ; l'élimination des faces et le sens de rotation restent
  appliqués pipeline par pipeline. 192 pipelines sur 12 programmes : 11 objets de pipeline Metal compilés au lieu de
  192 (2 au lieu de 11 pour les variantes dessinées). Création des 192 pipelines : 91 ms au lieu de 168 ms, cache
  Metal déjà chaud.
- Mémoire : aucun gain mesurable avec ces petits shaders de test (empreinte +4,8 Mio avec la partie, +3,9 Mio sans).
  La mémoire que Metal déclare allouée ne bouge pas pour 192 objets de pipeline : ils n'y sont pas comptés. Les
  environ 700 Mo que Metal compte en plus des allocations Vulkan de Hogwarts ne viennent donc probablement pas des
  objets de pipeline. Prochain relevé : les allocations Metal de MoltenVK lui-même, par catégorie.
- Le gain attendu de cette partie est donc sur les compilations en jeu (saccades), pas sur la mémoire.
- Recompilation iOS : run 45440044434, artefact 14944176196, binaire `06df5df1…` (4 862 600 octets), 10 marqueurs sur
  10, 8 points d'entrée sur 8, 428 exports Vulkan sur 428 ; épinglée dans `build-utils/melonx/moltenvk-rebuild-pin.json`
  (64 contrôles de parité). Contrôle du cache mappé (run 45440044387) vert. Rien n'est mesuré sur l'iPhone.
