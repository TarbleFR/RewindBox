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

**Lot 1 — moteur, sans retraduction des shaders (IPA 839, base 838)**

| Patch | Changement | Interrupteur (défaut) | Gain attendu (source, non mesuré chez nous) | Risque |
|---|---|---|---|---|
| 0352 | Passes ordonnées par les barrières du jeu ; étages objet et mesh dans la barrière de fin ; remise à zéro au changement de file | `S2A_RB_DRAW_BARRIERS` (`game`) | Zelda 25 → 18 ms (référence amont), un iPhone 29,7 → 27,2 ms | moyen : scintillement |
| 0353 | Une mémoire de commandes par image, visibilité seulement pour les morceaux qui comptent des échantillons | `S2A_RB_ALLOC_FRAME` (activé) | Zelda −3 à −6 ms par image quand le GPU n'est pas saturé | faible ; mémoire bornée |
| 0354 | Compilation attendue par un dessin en priorité maximale ; écriture d'archive sans lecture d'erreur ; origine des compilations | `S2A_RB_PSO_WAIT_BOOST`, `S2A_RB_ARCHIVE_ERROR_NIL`, `S2A_RB_COMPILE_ORIGIN` (activés) | moins d'attente sur les 600–900 ms d'un shader | faible |
| 0355 | Dispatchs ordonnés par les barrières du jeu | `S2A_RB_DISPATCH_ORDER` (`game`) | MKW −0,4 à −1,2 ms, Zelda −0,8 à −3 ms | faible à moyen |
| 0356 | Type et format des vues de textures en cache | `S2A_RB_VIEW_META` (activé) | −2 à −3 % de CPU par dessin | faible |
| 0357 | Diagnostics GPU : coupures de passes, profondeur précoce perdue, occlusions connues | `S2A_RB_GPUDIAG` (activé) | décide les patchs suivants | aucun |
| 0358 | Tuiles creuses et doublons non recopiés, copie de tuiles plus rapide | `S2A_RB_SPARSE_ZERO_TILES`, `S2A_RB_SPARSE_FAST_COPY` | MKW premier chargement −0,8 à −0,9 s | faible (texels identiques) |
| 0359 | Lecture anticipée groupée dans les parcours de pools (Zelda, Fire Emblem) | `S2A_RB_POOL_SCAN_AHEAD` | Zelda première scène −0,4 à −0,8 s | faible |
| 0361 | Voie de lecture anticipée des textures pour tous les titres, sans le verrou de soumission | `S2A_RB_BIND_LANE_FIRST_USE` | MKW −1,3 à −2,3 s d'envois par session | faible à moyen |
| 0362 | Cibles gardant la compression sans perte sauf vue d'un autre format déjà vue | `S2A_RB_DS_COMPRESS` | −40 à −53 Mo de trafic par image (MKW), 0,1–0,2 W | moyen |
| 0363 | Mises à jour de mémoire résidente hors du fil de soumission | `S2A_RB_RES_QUEUE` | −0,3 ms par image quand le CPU limite | faible |
| 0364 | Sonde de fréquence GPU toutes les 30 images | `S2A_RB_PROBE_EVERY` (30) | départage les deux hypothèses du bridage | aucun |

Les numéros sont provisoires : ils seront rendus contigus à l'intégration. Un patch qui ne passe
pas la relecture adverse sort du lot.

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
- Profondeur et stencil séparés, alternative lourde au patch 0362.
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
- Pas d'API publique pour enregistrer une bibliothèque Metal compilée : le cache système, opaque
  et partagé entre jeux, est le seul moyen de ne pas recompiler.
- Une seule file de soumission Metal au noyau : les tampons en attente derrière du travail en cours
  peuvent attendre 22 à 37 ms (mesure amont sur iPhone 17).

## Protocole de mesure

- Même scène ou même course, batterie 40–60 %, débranché depuis 10 minutes, départ à l'état
  Nominal, 10 minutes de jeu, un seul interrupteur changé entre deux sessions.
- Lignes à comparer : `timing up to frame` (GPU p50 et sonde), `power up to frame`,
  `[rb-speed]`, `[longframe]`, `[pso-frame-shaders]`, `residency set up to frame` (barrières
  complètes ou épargnées), `translation detail` (attentes GPU), `[rb-bind-lane]`, et les lignes
  propres à chaque patch.
- Corrigé, testé (tests purs gcc et clang), compilé (CI macOS), livré et observé sur iPhone restent
  distingués dans le suivi.
