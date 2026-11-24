# IPA 830 : fin de session, mémoire et compilations (SSBU puis Hogwarts Legacy, pid 21094)

24 novembre 2026. Sources : journaux privés de l'appareil (performance, core, stderr, launch, app) reçus le
24 novembre, sessions 12224 à 21094 de l'IPA 830 et des IPA précédentes encore présentes dans les mêmes fichiers.
Seuls des comptes, des tailles et des durées sont repris ici. Aucune mesure nouvelle n'a été faite sur l'iPhone.

## 1. La fin de la session 21094

- SSBU de 09:29:38 à 09:34:02, puis Hogwarts Legacy dans le même processus à partir de 09:34:12.
- Alertes mémoire d'iOS à 09:35:06, 09:38:10, 09:40:23, 09:41:13 et 09:41:16. À la dernière : empreinte
  4 812 Mio, marge du processus 1 843 Mio, appareil à 5 % de mémoire disponible.
- Dernières lignes du moteur à 09:41:37 (inventaire mémoire, rendu). Le journal de cycle de vie ne contient ni
  `willResignActive` ni `didEnterBackground` pour ce processus : l'application s'est arrêtée en jeu, au premier plan.
- La limite du processus n'était pas atteinte (1,8 Gio de marge) ; c'est l'appareil qui manquait de mémoire. Sans
  rapport « JetsamEvent » de l'iPhone, la cause exacte de l'arrêt n'est pas prouvée ; tout concorde avec un arrêt par
  iOS pour manque de mémoire du téléphone.
- La mémoire de la console (4 Gio) est portée par les processus « donneurs » de MeloNX (`MLXRamDonor`, deux vivants,
  4 294 967 296 octets prêtés) : les 4,8 Gio de l'empreinte sont la mémoire propre de l'application (moteur .NET,
  Metal, code traduit, tampons), dont environ 2,3 Gio compressés par iOS.

## 2. L'emballement mémoire de Hogwarts

Lignes par seconde du journal de performance (Hogwarts, pid 21094) :

| Temps de jeu | Images/s | Pages décompressées par iOS | Appareil disponible |
|---|---|---|---|
| 1 à 30 s | 9,0 (chargement) | 41 429 en 30 s | 13 % |
| 92 à 211 s | 25,9 à 27,6 | 77 213 à 125 248 par 30 s | 6 à 9 % |
| 212 à 241 s | 21,2 | 202 390 en 30 s | 7 % |
| 236 à 272 s | 0 la plupart des secondes | jusqu'à 231 813 en une ligne | 4 à 10 % |
| 278 à 369 s | 14,0, 9,4 puis 0 | 418 113, 961 424 puis 1 580 693 par ligne | 4 à 5 % |

Après 251 s, l'échantillonneur lui-même ne tient plus sa cadence (lignes à 263, 278, 308, puis 369 s) : le processus
passe son temps à faire relire par iOS de la mémoire compressée.

## 3. Les compilations ralentissent avec la pression mémoire

Statistiques de MoltenVK (cumuls toutes les 5 à 60 s, ramenés à chaque intervalle) :

| Moment (Hogwarts) | Bibliothèques Metal compilées | Temps moyen par bibliothèque |
|---|---|---|
| 09:35:14 | 330 | 44 ms |
| 09:36:04 | 17 | 521 ms |
| 09:37:12 | 14 | 719 ms |
| 09:38:47 | 294 | 222 ms |
| 09:39:37 | 84 | 710 ms |
| 09:41:08 | 114 | 1 057 ms |
| 09:41:33 | 9 | 1 409 ms |

- Pipelines compilés par les fils d'arrière-plan : 88 en 49,1 s (09:38:55), 42 en 64,3 s, puis 25 en 69,2 s, soit
  0,56 s, 1,5 s puis 2,8 s par pipeline.
- Bilan de la session Hogwarts : 220 créations de pipeline au moment du dessin (217 états jamais vus), 42 120 ms
  d'attente cumulée sur le fil de rendu.
- Relevés de blocage en jeu (#5 et #6) : le fil de rendu attend une tâche ; les deux fils de compilation de pipelines
  attendent dans MoltenVK la réponse du compilateur Metal ; le fil GPU attend que la file de commandes se vide.

Les nouveaux états de Hogwarts doivent être compilés : ils n'ont jamais été vus. Le ralentissement d'un facteur 30 de
chaque compilation suit la pression mémoire de l'appareil.

## 4. Où est la mémoire

- Tas .NET : 921 Mio engagés en fin de session ; tas des gros objets (LOH) 466 Mio, dont 174 à 216 Mio libres ;
  gen2 396 à 405 Mio.
- Mémoire graphique (registre « graphics » du noyau) : 1 037 à 1 405 Mio, plus 129 à 258 Mio compressés. MoltenVK
  compte 1 516 Mo de mémoire GPU allouée à la fin. Les caches de textures (158 Mio) et de tampons (201 Mio) sont
  petits ; les purges sous pression ne libèrent que 2 à 12 Mio à chaque fois.
- Tas natif (relevé des 120 premières secondes, fenêtre SSBU) : 455 Mio vivants ; la plus grosse pile, 102 Mio, est
  une allocation de Metal et du pilote GPU appelée par MoltenVK pendant la création des pipelines.

## 5. Le tas des gros objets se refragmente en continu : correction POOL_830

- Dans les dix sessions Hogwarts lues, le LOH fait 491 à 509 Mio cinq secondes après le lancement, dont 153 à
  255 Mio libres.
- Pid 19616 : un compactage du moteur pendant un chargement (07:22:38) ramène le LOH de 506 à 265 Mio, sans espace
  libre, et le tas engagé de 781 à 467 Mio. Quinze secondes plus tard, le LOH refait 504 Mio, dont 181 Mio libres.
- En jeu, le fil GPU alloue jusqu'à 263 à 267 Mio par fenêtre de 5 s.
- Les collections gen2 de la session sont toutes « background » (`adapt_bgc_keepalive`) ; elles ne compactent jamais.
  Un gros tableau libéré devient de l'espace libre que le LOH garde engagé ; un nouveau gros tableau est remis à zéro,
  ce qui touche des pages qu'iOS a pu compresser.
- Cause dans le code : le pool `MemoryOwner<T>` (envois de textures, copies DMA, lectures et écritures fragmentées).
  Un échec allouait la longueur exacte demandée, et chaque tableau quittait le pool 3 s après son retour, le premier
  de sa longueur compris.
- Correction (`adapt_streaming_memory`, POOL_830, tous les titres) :
  - un échec de 85 000 octets ou plus alloue sa classe de taille, au plus 25 % de plus ;
  - les gros tableaux gardés, principaux et doublons, tiennent dans 96 Mio, les plus anciens partent en premier ;
  - un gros tableau gardé est relâché 30 s après son retour au lieu de 3 s ; un petit tableau, hors LOH, toujours
    après 3 s ;
  - le contenu rendu aux appelants, la recherche et les doublons (64 Mio au plus) sont inchangés.
- Vérifications sur hôte (.NET 10, x64) :
  - banc de 6 rafales de 48 envois de 32 tailles de 64 Kio à 8 Mio, 8 en vol, séparées de 3,5 s : 248,1 Mio alloués
    par le pool livré, 65,4 Mio par le nouveau, au plus 65,2 Mio gardés ;
  - LOH final : 33,9 Mio libres avec le pool livré, 0 avec le nouveau ;
  - exclusivité des tampons sous 8 fils, `RentCleared`, `RentCopy` et délais (petit tableau relâché, gros gardé)
    contrôlés ;
  - mesure du test `melonx_streaming_memory` (base : préimages de l'adaptateur, candidat : préparation finale) :
    toutes ses assertions passent, 96 octets alloués au lieu de 524 464 pour ses trois envois réutilisés ;
  - compilation du vrai projet `Ryujinx.Common` : 0 erreur, 0 avertissement ; contrat du Core : 549 vérifications.
- Ce test échoue sur la tête actuelle pour une autre raison, avec ou sans ce changement : sa comparaison finale
  ignore les adaptateurs plus récents qui partagent ses fichiers. C'est un des 38 tests notés en échec avant le lot
  du 23 novembre. Les préimages d'adaptateurs ont été enregistrées par `test/melonx_adapter_preimages.py`.
- À lire au prochain essai : `lohAfterBytes` et `lohFreeAfterBytes` (gcEvent, memoryInventory), octets alloués du fil
  GPU (`gpuDispatch`, core-performance), empreinte et alertes mémoire. Aucun gain n'est mesuré sur l'iPhone.

## 6. Pistes écartées ou reportées

- Rendre à iOS les pages libres de malloc (`malloc_zone_pressure_relief` à l'alerte mémoire, au passage en
  arrière-plan, à la fermeture) : abandonné. Dans libmalloc (sources publiques d'Apple), iOS libère déjà les pages
  au moment même de la libération (`DEFAULT_AGGRESSIVE_MADVISE_ENABLED`). Pour la même raison,
  `CONFIG_MADVISE_PRESSURE_RELIEF` vaut 0 : le soulagement automatique n'y a rien à faire. Le code n'a pas été livré.
- Pool privé pour les grosses entrées GPFifo : mécanisme réel (le pool partagé de .NET 10 vide ses tableaux à chaque
  gen2 sous forte charge mémoire), volume inconnu (taille des entrées non journalisée) ; non livré.
- Allègement de `RegionHandle` (−28 % par page suivie sur hôte, environ −12 Mio pour 200 Mio de tampons) : gain
  faible, demande un nouveau test du contrat ; reporté.
- Moins de compilations (états dynamiques, clés MSL par étage, verrou du cache principal) : leviers les plus forts
  pour les saccades et la mémoire Metal, mais leur part réelle n'est pas mesurée. Il faut d'abord classer les états
  tardifs d'une vraie session avant d'y toucher. Ajouté au même Core, journal seul (VARIANT_CAUSES,
  `adapt_render_thread_compile_relief`) : chaque état nouveau en jeu est comparé à tous ceux que son programme avait.
  Les champs qui le séparent du plus proche tombent dans un groupe : état que Vulkan peut rendre dynamique ou que
  MoltenVK ignore (par nom), entrée des sommets, mélange, attachements, autre. Une ligne `pipelineVariants/causes`
  par minute au plus. Classement vérifié sur la DLL compilée du moteur (9 cas, dont la topologie de même classe ou
  non) ; projet `Ryujinx.Graphics.Vulkan` compilé sans erreur.
- Les purges et compactages du moteur se déclenchent sur la marge du processus ; sur cet iPhone, c'est l'appareil
  qui manque de mémoire en premier (5 % disponibles avec 1,8 Gio de marge). Constat consigné, aucun seuil n'est
  changé.

## 7. SSBU dans la même session

- 1 655 états rejoués au lancement en 1 575 ms (cache Metal chaud).
- En jeu : 51 créations tardives à 09:32 (1 065 ms) et 71 à 09:33 (1 965 ms), soit environ 28 ms chacune sur le fil
  de rendu : les légères saccades.
- Fils d'arrière-plan : 34 pipelines sur 40 « compilés à nouveau » en une minute (4 404 ms), malgré le cache.
