# S2Arm : chantier d'optimisation globale (A18 Pro, Metal 4)

Demande du mainteneur (24 novembre 2026) : fluidité, stabilité des fréquences et efficacité sur
Apple A18 Pro, selon cinq axes (streaming, synchronisation CPU ↔ GPU, fréquence GPU, coût du
chemin chaud, exploitation de la puce). Contraintes : aucune régression, aucune réduction de
résolution, ne plus toucher à la vitesse ni au rythme des jeux, pas de bricolage propre à un titre.

Statut de ce document : audit et plan. Rien n'est encore mesuré sur iPhone après changement. Les
gains cités viennent d'autres projets (presque tous mesurés sur Mac) : ce sont des ordres de
grandeur attendus, pas des résultats.

## Point de départ mesuré (IPA 836, moteur 0351)

Médianes des fenêtres de 300 images après l'image 600, journaux du 24 novembre (MKW 011ae443,
Fire Emblem 507443b3, Zelda e23a1776), réglages par défaut, batterie 45–55 %, débranché.

| | Mario Kart World | Fire Emblem | Zelda (0400486024DEC000) |
|---|---|---|---|
| Temps d'image p50 / p95 | 19,7 / 31,6 ms | 43,3 / 68,7 ms | 30,2 / 40,6 ms |
| GPU p50 / p95 | 12,5 / 16,1 ms | 30,0 / 34,8 ms | 24,4 / 31,5 ms |
| Soumission + présentation p50 | 12,4 ms | 18,6 ms | 15,3 ms |
| Images par seconde observées | 47,0 (25,7–60) | 21,6 (20–29,9) | 29,2 (15,7–60) |
| Vitesse du jeu (`[rb-speed]`) | 86,4 % | 72,3 % | 50,7 % |
| Cœurs CPU utilisés / part sur cœurs performance | 2,73 / 44 % | 2,01 / 7 % | 1,89 / 21 % |
| Énergie CPU (mJ par image) | 0,86 W (19,1) | 0,32 W (14,5) | 0,50 W (13,8) |
| Réveils par seconde | 3 297 | 2 356 | 13 410 |
| État thermique | 1 toute la session | 2 toute la session | 1 puis 2 |

- Zelda avance son temps de jeu image par image : à 24 ms de GPU par image, il tourne à moitié
  de sa vitesse. Le remède est un GPU plus rapide, pas un changement de rythme.
- Fire Emblem (jeu à 30 images par seconde) dépasse 33,3 ms : GPU 30 ms, soumission sur les cœurs
  efficaces, état Serious dès le lancement.
- Mario Kart World est limité par le CPU à pleine fréquence GPU : la relecture des commandes du jeu
  (14–17 ms) tourne sur le fil de présentation, cœurs performance à 1,26–1,30 GHz.
- Le téléphone est sous iOS 27.0 : le chemin NVN y utilise Metal 4. Les appareils en iOS 26.x
  prennent le chemin Metal 3 (plantage backboardd n° 311).

## Où part le temps (cinq audits, lecture seule)

**GPU et passes**
- Barrière complète à l'entrée de chaque passe de rendu : 132 par image dans MKW, aucune
  épargnée. Le mode « ordonné par les barrières du jeu » existe déjà dans le moteur, éteint.
- La cible principale 854×480 de Zelda est rouverte 27 à 35 fois par image ; celle de MKW
  (1248×700) 9 fois, avec une profondeur D32S8 créée avec `PixelFormatView`, ce qui désactive la
  compression sans perte (documentation Apple).
- Les lectures mémoire brutes de 64 et 128 bits des shaders de Zelda sont éclatées en lectures de
  32 bits ; la marque de lecture des pools de textures passe par une opération atomique.
- Calcul : 14–19 % du temps GPU de MKW et 16–19 % de celui de Zelda, avec une barrière avant
  chaque dispatch.

**Synchronisation CPU ↔ GPU**
- Zelda fait environ 14 tampons de commandes par image pour 8 mémoires de commandes : le fil de
  soumission dort sur le GPU en milieu d'image, 4,4 à 7,2 ms par image (2 258 attentes à l'image
  5 100 ; Fire Emblem 989 à l'image 3 300 ; MKW 0).
- Fire Emblem attend à l'acquisition de l'image (copie de présentation placée derrière le travail
  suivant) : GPU inactif environ 15 ms entre deux images.

**Pipelines et shaders**
- Les plus gros à-coups viennent d'un seul shader nouveau : traduction 100–435 ms, compilation
  Metal 600–900 ms (jusqu'à 8,7 s en arrière-plan pour Zelda), pipeline 130–180 ms.
- Les traductions sont bien conservées d'une session à l'autre ; l'archive des pipelines sert
  (MKW 3 016, Zelda 1 475).
- Le cache de shaders d'iOS est à environ 1,33 Go et semble saturé : les jeux s'évincent l'un
  l'autre (Fire Emblem recompile 606 bibliothèques au lancement, 31,9 ms chacune). Non vérifié.

**Streaming**
- Coût principal : relire des pages de la mémoire du jeu évincées, sur le fil de soumission, une
  texture à la fois (MKW 1,49 Go manquants = 3,28 s, 56 % du temps d'envoi des longues images ;
  Zelda 69 % ; Fire Emblem 78 %).
- Tuiles creuses au premier chargement de course de MKW : image 740 de 912 ms, 54 141 fautes de
  page pour 62 Mo lus ; 960 Mo recopiés par le CPU puis réécrits par le GPU.

**Fréquence et énergie**
- MKW : bridage du GPU après environ 100 s de course ; les cœurs performance montent alors à
  2,8–3,6 GHz et l'énergie CPU par image est multipliée par 2,3.
- Les menus sont la phase la plus chaude du CPU (1,4–2,5 W contre 0,3–0,9 W en jeu).
- Deux hypothèses pour le bridage, non départagées : plafond de puissance, ou boucle entre la
  cadence des images et la gestion de fréquence (les deux bridages de l'IPA 836 suivent une rafale
  de 35 à 80 changements d'intervalle pour 100 images).

## Plan priorisé

Chaque changement a son interrupteur `S2A_RB_*` (à placer dans `Documents/env.txt` pour le
couper). Aucun ne touche à la vitesse, au rythme de présentation ou à la résolution.

**Lot 1 envisagé — moteur, sans retraduction des shaders**

| État | Changement | Interrupteur mis en place ou proposé | Gain attendu (source, non mesuré chez nous) | Risque |
|---|---|---|---|---|
| Intégré 0353 | Passes ordonnées par les barrières du jeu ; étages objet et mesh dans la barrière de fin ; remise à zéro au changement de file | `S2A_RB_DRAW_BARRIERS` (`game`) | Zelda 25 → 18 ms (référence amont), un iPhone 29,7 → 27,2 ms | moyen : scintillement |
| Proposé | Une mémoire de commandes par image, visibilité seulement pour les morceaux qui comptent des échantillons | `S2A_RB_ALLOC_FRAME` (activé) | Zelda −3 à −6 ms par image quand le GPU n'est pas saturé | faible ; mémoire bornée |
| Proposé | Compilation attendue par un dessin en priorité maximale ; écriture d'archive sans lecture d'erreur ; origine des compilations | `S2A_RB_PSO_WAIT_BOOST`, `S2A_RB_ARCHIVE_ERROR_NIL`, `S2A_RB_COMPILE_ORIGIN` (activés) | moins d'attente sur les 600–900 ms d'un shader | faible |
| Proposé | Dispatchs ordonnés par les barrières du jeu | `S2A_RB_DISPATCH_ORDER` (`game`) | MKW −0,4 à −1,2 ms, Zelda −0,8 à −3 ms | faible à moyen |
| Intégré 0352 | Type et format des vues de textures en cache | `S2A_RB_VIEW_META` (activé) | −2 à −3 % de CPU par dessin | faible |
| Proposé | Diagnostics GPU : coupures de passes, profondeur précoce perdue, occlusions connues | `S2A_RB_GPUDIAG` (activé) | décide les patchs suivants | aucun |
| Copie seule, 0355 sur demande | Tuiles creuses et doublons non recopiés, copie de tuiles plus rapide | `S2A_RB_SPARSE_ZERO_TILES`, `S2A_RB_SPARSE_FAST_COPY` | Part du décodage dans les 912 ms à mesurer | faible (texels identiques) |
| Proposé | Lecture anticipée groupée dans les parcours de pools (Zelda, Fire Emblem) | `S2A_RB_POOL_SCAN_AHEAD` | Zelda première scène −0,4 à −0,8 s | faible |
| Proposé | Voie de lecture anticipée des textures pour tous les titres, sans le verrou de soumission | `S2A_RB_BIND_LANE_FIRST_USE` | MKW −1,3 à −2,3 s d'envois par session | faible à moyen |
| Proposé | Cibles gardant la compression sans perte sauf vue d'un autre format déjà vue | `S2A_RB_DS_COMPRESS` | −40 à −53 Mo logiques par image (hypothèse MKW), watts à mesurer | moyen |
| Proposé | Mises à jour de mémoire résidente hors du fil de soumission | `S2A_RB_RES_QUEUE` | −0,3 ms par image quand le CPU limite | faible |
| Proposé | Sonde de fréquence GPU toutes les 30 images | `S2A_RB_PROBE_EVERY` (30) | départage les deux hypothèses du bridage | aucun |

Les réglages des pistes proposées sont des choix à évaluer. Voir le premier lot vérifiable pour les réglages effectivement intégrés.

**Lot 2 — traducteur de shaders (livraison séparée)**
- Lectures brutes 64/128 bits en une lecture vectorielle (nxnative, MIT : Zelda 16,3 → 12,6 ms de
  GPU sur M4 Pro), marque de pool sans atomique et rassemblement 2×2 (S2Arm amont, Apache-2.0 :
  passe de couleur 13,0 → 9,2 ms sur iPad Pro M5), puis fonctions NoContraction en ligne,
  MulExtended en ligne, test de profondeur précoce NVN2, retrait du point d'entrée de profondeur
  inutilisé des shaders de sommets (−41 % de CPU Metal par compilation chez nxnative).
- Toute modification du traducteur change son empreinte : chaque appareil retraduit tous les
  shaders au lancement suivant. Ce lot sera donc livré seul, avec une retraduction faite avant le
  lancement du jeu pour ne pas dégrader la première session.

**Lot 3 — synchronisation**
- Ligne de mesure `[rb-sync]` ; fusion des morceaux soumis pendant que le GPU travaille
  (OoT sur iPhone 17 chez nxnative : 54,5–70 → 42–45 ms à l'état lent) ; présentation sur sa propre
  file (Fire Emblem −2 à −5 ms attendus) ; réveil sur l'événement partagé.

**À étudier avant tout changement (structurel)**
- Relecture des commandes hors du fil du jeu (MKW +20–25 % attendus, risque élevé).
- Compilateur et archives Metal 4 avec états de pipeline souples.
- Profondeur et stencil séparés, alternative à un changement des usages des textures de profondeur.
- Consommation CPU des menus (1,4–2,5 W) : profil d'abord, puis seulement un changement.

**Écartés avec preuve** : attentes de copie, de relecture, de verrou et de surfaces d'affichage
(0,0 ms) ; file d'envoi asynchrone (rien à retirer) ; mémoires de commandes portées à 32
(0,4–0,7 Go) ; cibles sans mémoire ; compression avec perte (pixels changés) ; affichage à 30 Hz ;
clé ProMotion ; regroupement des validations ; décodage BC (natif sur cette puce) ; génération
d'images comme levier d'énergie ; patch 0343 (aucun cas dans cinq journaux).

## Limites imposées par iOS

- Aucun contrôle de la fréquence GPU, du régulateur CPU (CLPC) ni de la politique thermique ; à
  l'état Serious, iOS déplace même les fils temps réel sur les cœurs efficaces.
- Seulement 2 cœurs performance ; les autres processus et la pagination du noyau prennent 13 à
  26 % des cœurs.
- La mémoire du jeu (9,2 Go de pools pour environ 6,2 Go de place) doit vivre dans des fichiers :
  les relectures sont structurelles, on ne peut que les avancer et les paralléliser.
- Le chemin actuel de compilation MSL à la volée dépend du cache système pour ses bibliothèques
  exécutables. Metal 4 permet aussi de sérialiser les pipelines capturés par un
  `MTL4Compiler`. La sérialisation des bibliothèques dynamiques fait l’objet d’une API distincte.
  [Archives de pipelines](https://developer.apple.com/documentation/metal/mtl4pipelinedatasetserializer)
  · [Bibliothèques dynamiques](https://developer.apple.com/documentation/metal/mtldynamiclibrary)
- En amont, des tampons en attente derrière un autre travail ont attendu 22 à 37 ms sur iPhone 17.
  La topologie des files du noyau sur A18 Pro reste indéterminée. Une file de présentation
  supplémentaire demanderait une trace montrant que le travail peut réellement se chevaucher.

## Protocole de mesure

- Même scène ou même course, batterie 40–60 %, débranché depuis 10 minutes, départ à l'état
  Nominal, 10 minutes de jeu, un seul interrupteur changé entre deux sessions.
- Lignes à comparer : `timing up to frame` (GPU p50 et sonde), `power up to frame`,
  `[rb-speed]`, `[longframe]`, `[pso-frame-shaders]`, `residency set up to frame` (barrières
  complètes ou épargnées), `translation detail` (attentes GPU), `[rb-bind-lane]`, et les lignes
  propres à chaque patch.
- Corrigé, testé (tests purs gcc et clang), compilé (CI macOS), livré et observé sur iPhone restent
  distingués dans le suivi.

## Premier lot vérifiable

Base distribuée 836 à 838, moteur 0351. La branche a ensuite reçu le cache des métadonnées de vues (0352) et les barrières ordonnées par le jeu (0353). Les valeurs de l’IPA 836 sont les médianes des fenêtres consignées dans le relevé. La vitesse émulée et les intervalles réellement affichés sont deux mesures distinctes.

| Priorité | Coût observé ou défaut de code | Décision et résultat recherché sur appareil |
|---|---|---|
| 1. Comparaison fiable | Le mode de barrières et le mode de lecture des vues restaient ceux du premier accès du processus. Le rapport de vues et le chemin de rendu pouvaient initialiser simultanément le même entier. | 0354 relit chaque choix au premier accès de la session, y compris après le chargement du profil. Objectif de correction fonctionnelle. |
| 2. Streaming | MKW, première course, image 740 à 912 ms. Le diagnostic existant mêle mappages, réservation de staging et contenu décodé. | 0355 accélère la conversion CPU des tuiles empaquetées complètes de 64 Kio. 0356 mesure son temps et son volume exacts. Viser au moins 15 % de temps en moins par tuile complète sur A18 et vérifier les longues images du chargement. |
| 3. Synchronisation et passes | Zelda attend 4,4 à 7,2 ms par image le GPU en cours de soumission. MKW ne signale aucune attente de ce type. Zelda rouvre sa cible principale 27 à 35 fois par image. | Comparer 0353 en modes full et game avec captures. Puis attribuer l’attente au recyclage d’un allocateur ou à une dépendance réelle. Pour changer les allocateurs, viser au moins 1 ms de moins sur le temps de trame de Zelda, empreinte stable. Conserver la retraite GPU. |
| 4. Coût par dessin et compilation | MKW, relecture des commandes de 14 à 17 ms. Pour un shader nouveau, 100 à 435 ms de traduction et 600 à 900 ms de compilation Metal observées. | Isoler 0352, viser 2 % de moins de CPU par dessin à nombre de dessins et pixels égaux. Pour la compilation, comparer séparément la première utilisation à froid et la relance à chaud. Mesurer le p95 d’attente du premier dessin et le volume de travail spéculatif. |
| 5. Énergie et architecture | MKW, 0,86 W CPU et 19,1 mJ CPU/image. La sonde GPU ralentit après environ 100 s. Sa variation seule ne départage pas les causes. | Sur au moins 10 minutes, comparer l’énergie par image, le temps en Serious et la vitesse du jeu. Une baisse de 0,05 W CPU représenterait 5,8 % de cette référence, à cadence égale. C’est un seuil d’intérêt. Mesurer le trafic GPU avant de modifier les usages des attachements. |

MKW doit gagner 3,03 ms pour passer de 19,7 à 16,67 ms. Fire Emblem doit gagner 9,97 ms pour passer de 43,3 à 33,33 ms. Zelda doit gagner 13,53 ms pour passer de 30,2 à 16,67 ms, avec un GPU médian déjà à 24,4 ms. CPU et GPU peuvent travailler en parallèle. Sur MKW, gagner 1 ms sur le chemin critique ferait passer la cadence équivalente à cette seule médiane de 50,8 à 53,5 i/s. Le FPS moyen et les trames longues demandent leur propre mesure.

### Décodage des tuiles

Quand le décodeur est appelé, les octets de l’invité ont déjà été copiés vers une tuile temporaire. Le candidat groupe les copies de 16 octets selon la disposition du bloc et écrit le même nombre d’octets dans le staging. Les tuiles de bord, les petits mips regroupés en fin de texture, les alias déjà produits par le GPU et les remplissages GPU suivent leurs chemins existants.

Le test de textures compare tout le tampon de sortie à un oracle d’adressage par octet, gardes et padding inclus. Il couvre les deux ordres NVN/NVN2, six formats et huit hauteurs de blocs. Le banc ci-dessous effectue neuf passages alternés de 1 024 tuiles par mode après échauffement et compare les sommes de contrôle. La commande en tête du fichier s’exécute depuis l’arbre moteur patché. [Source du banc](../../build-utils/s2arm/engine/benchmarks/sparse_tile.c)

| Hôte et compilateur | Ensemble parcouru | Référence, µs/tuile | Candidat, µs/tuile |
|---|---|---:|---:|
| AMD EPYC 9V74, GCC 14.2, -O2 | 1 tuile de 64 Kio réutilisée | 31,159 | 4,083 |
| Même hôte | 64 Mio de sources et 64 Mio de destinations | 35,891 | 9,458 |

Ces mesures portent sur la conversion CPU. Pour `S2A_RB_SPARSE_FAST_COPY`, zéro ou absence sélectionne le chemin de référence et un sélectionne le candidat. `S2A_RB_SPARSE_DECODE_STATS=1` mesure les lots dans les deux modes. Chaque ligne `[rb-sparse-decode]` donne le nombre de tuiles décodées, le nombre de tuiles complètes, les octets de sortie et les temps muraux. Comparer `sum(full_wall_ns) / sum(full_tiles)` et les volumes réellement décodés. Zéro tuile complète signifie que la scène n’a pas exercé le candidat. La trame identifiée par `frame_at_report` est celle du rapport.

### Validation sur iPhone

Comparer trois fenêtres de 180 s par variante et par scène, ordre alterné A/B puis B/A, avec refroidissement. Utiliser la Coupe Champignon de MKW en 150 cc au même repère, une scène de Zelda qui rouvre souvent la profondeur et une scène de Fire Emblem qui utilise ses tableaux de textures. Conserver jeu, version, sauvegarde, résolution, état initial des caches et luminosité. Relancer l’app après un changement de `Documents/env.txt`. Séparer le premier passage des répétitions à cache chaud et conserver les caches du joueur. Distinguer la vitesse émulée, le FPS présenté et les éventuelles images interpolées. [Protocole de 180 s](../s2arm-benchmark-protocol.md)

Publier chaque fenêtre avec sa couverture, p50/p95/p99, dépassements de 100 ms/min, manques audio, footprint maximal, temps en Serious et erreurs GPU. Un écart plus petit que la dispersion des répétitions reste indéterminé. Une différence de pixels sur un replay déterministe, un blocage ou une hausse reproductible du p99, de l’empreinte ou du temps en Serious empêche l’activation par défaut. Effectuer le contrôle visuel et les diagnostics séparément du passage chronométré, puis confirmer en endurance. Les compteurs Instruments mesurent la bande passante GPU. Power Profiler exprime la consommation système en fraction de batterie par heure. [Bande passante GPU](https://developer.apple.com/documentation/xcode/measuring-the-gpus-use-of-memory-bandwidth) · [Puissance sur batterie](https://developer.apple.com/documentation/xcode/measuring-your-app-s-power-use-with-power-profiler) · [Validation Metal](https://developer.apple.com/documentation/xcode/validating-your-apps-metal-api-usage)

L’A18 Pro est Apple9 et accepte les formats BC natifs. Pour les autres puces, garder les vérifications du périphérique, des formats et des dimensions de tuiles avant d’entrer dans le chemin sparse. La QoS exprime une priorité pour l’ordonnanceur iOS. Mesurer le travail CPU et GPU et les octets par image, à vitesse de jeu égale. [Familles GPU Apple et formats](https://developer.apple.com/metal/Metal-Feature-Set-Tables.pdf)
