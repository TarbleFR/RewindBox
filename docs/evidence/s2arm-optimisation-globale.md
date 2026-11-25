# S2Arm : chantier d'optimisation globale (A18 Pro, Metal 4)

Demande du mainteneur (24 novembre 2026) : fluidité, stabilité des fréquences et efficacité sur
Apple A18 Pro, selon cinq axes (streaming, synchronisation CPU ↔ GPU, fréquence GPU, coût du
chemin chaud, exploitation de la puce). Contraintes : aucune régression, aucune réduction de
résolution, ne plus toucher à la vitesse ni au rythme des jeux, pas de bricolage propre à un titre.

Le premier lot est livré dans l’[IPA privée 839 vérifiée](rewind839/delivery.json). Les mesures du décodeur sur Mac figurent en fin de document. Les estimations de la feuille de route et les observations de l’IPA 836 gardent leurs sources propres. La comparaison du candidat sur iPhone reste à réaliser.

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
- Zelda fait environ 14 tampons de commandes par image pour 8 mémoires de commandes : les attentes de fence sur la
  soumission représentent 4,4 à 7,2 ms par image (2 258 attentes à l'image
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
- Sur les longues images, les uploads associés à des pages absentes représentent 56 % du temps d’envoi de MKW, 69 % sur Zelda et 78 % sur Fire Emblem. Sur MKW, 1,49 Go ont été signalés absents et ces uploads ont occupé 3,28 s. La part exacte des fautes de page dans ce temps reste à isoler.
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
| Implémenté 0367, essai sur demande | Une mémoire de commandes par image ; visibilité déjà réservée à la demande depuis 0359 | `S2A_RB_ALLOC_FRAME=1` | Cible : réduire les 2,01 ms/image d’allocateur mesurées dans la 840 ; FPS à mesurer | empreinte des allocateurs à mesurer |
| Implémenté 0372–0376, essai sur demande | Compilation attendue priorisée ; écriture d’archive sans sortie d’erreur Metal | `S2A_RB_PSO_WAIT_BOOST=1`, `S2A_RB_ARCHIVE_ERROR_NIL=1` | Attente de première utilisation à comparer ; aucun gain chiffré établi | priorité du travail requis, refus d’archive conservés |
| Proposé | Origine détaillée des compilations | `S2A_RB_COMPILE_ORIGIN` | attribution | diagnostic |
| Implémenté 0371, essai sur demande | Dispatchs invités consécutifs ordonnés par les barrières du jeu | `S2A_RB_DISPATCH_ORDER=game` | Hypothèses initiales MKW −0,4 à −1,2 ms, Zelda −0,8 à −3 ms ; non mesurées | replay pixels et barrières à confirmer sur Metal 4 |
| Intégré 0352 | Type et format des vues de textures en cache | `S2A_RB_VIEW_META` (activé) | −2 à −3 % de CPU par dessin | faible |
| Implémenté 0369/0378, diagnostic sur demande | Coupures de passes, réouvertures, early_z demandé et annotation MSL | `S2A_RB_GPUDIAG=1` | décide le lot traducteur suivant | journalisation à couper pour l’A/B |
| Copie seule, 0355 sur demande | Tuiles creuses et doublons non recopiés, copie de tuiles plus rapide | `S2A_RB_SPARSE_ZERO_TILES`, `S2A_RB_SPARSE_FAST_COPY` | Part du décodage dans les 912 ms à mesurer | faible (texels identiques) |
| Proposé | Lecture anticipée groupée dans les parcours de pools (Zelda, Fire Emblem) | `S2A_RB_POOL_SCAN_AHEAD` | Zelda première scène −0,4 à −0,8 s | faible |
| Proposé | Voie de lecture anticipée des textures pour tous les titres, sans le verrou de soumission | `S2A_RB_BIND_LANE_FIRST_USE` | MKW −1,3 à −2,3 s d'envois par session | faible à moyen |
| Proposé | Cibles gardant la compression sans perte sauf vue d'un autre format déjà vue | `S2A_RB_DS_COMPRESS` | −40 à −53 Mo logiques par image (hypothèse MKW), watts à mesurer | moyen |
| Proposé | Mises à jour de mémoire résidente hors du fil de soumission | `S2A_RB_RES_QUEUE` | −0,3 ms par image quand le CPU limite | faible |
| Implémenté 0370, diagnostic sur demande | Travail GPU fixe sondé toutes les 30 images | `S2A_RB_PROBE_EVERY=30` | éclaire les deux hypothèses du bridage ; durée, pas fréquence absolue | sonde elle-même active ; cadence identique entre variantes |

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

### Ce que la relecture du moteur permet d’attribuer

**Pages de l’invité.** Dans `rb_texture_ahead.inc`, la voie 0329 des liaisons de textures vérifie `rb_course_exact()`, qui exige le manifeste et le build de Mario Kart World. Une autre voie fichier générique existe derrière `S2A_RB_TEXTURE_PAGER=1`. Les identifiants découverts uniquement lors du parcours d’une table de descripteurs échappent au conseil sur liaison directe. Avant d’élargir la couverture, comparer par titre les pages réellement conseillées puis utilisées, encore absentes au premier upload, expirées et invalidées. `cold_upload_offcpu_upper_ms` est une borne supérieure. Le temps de lecture disque isolé reste inconnu. Une expérience d’anticipation doit revalider série, backing et génération, céder sur contention, respecter le quota et les arrêts mémoire/thermiques. La mémoire unifiée ne rend pas une page évincée immédiatement résidente.

**Allocateurs et occlusion.** Dans `nvn_be_sub_begin`, le pool de huit allocateurs et l’anneau de huit tampons de visibilité peuvent attendre des fences distinctes. `g_alloc_waits` compte les passages à la limite du pool, tandis que le temps de `nvn_be_wait` agrège plusieurs causes. `sub_cut` peut encoder plusieurs command buffers successifs avec le même allocateur. L’attribution des 4,4 à 7,2 ms de Zelda au seul allocateur reste donc ouverte. Chronométrer les deux emplacements, leurs fences et les achèvements avant d’augmenter un pool ou de prolonger sa durée de vie. Le reset attend le dernier consommateur GPU. [Modèle de commande Metal 4](https://developer.apple.com/documentation/metal/understanding-the-metal-4-core-api)

**Acquisition de l’image.** Dans `h_nvnWindowAcquireTexture`, le chemin exécuté depuis un autre thread peut attendre le ticket de présentation puis retourner avant la comptabilité `g_pq_wait_ns`. Sur Fire Emblem, mesurer les deux chemins et corréler le ticket à la période GPU inactive avant de déplacer la présentation sur une autre file. Un zéro dans la ligne de présentation ne ferme pas cette piste.

### Banc Apple Silicon

Le premier essai du [run 45499482706](https://github.com/TarbleFR/RewindBox/actions/runs/45499482706) identifie le runner comme Apple M1 virtuel, macOS 26.7.2. La médiane sur 1 024 tuiles distinctes est passée de 23,963 à 5,957 µs par tuile (neuf passages, plage 19,111–31,510 puis 5,193–10,516 µs). Pour une seule tuile réutilisée, la médiane est passée de 20,600 à 1,338 µs. Les 1 354 contrôles CPU passent. Le test Metal RGBA8 lit 16 384 pixels exacts dans chacun des quatre cas après copie vers une texture privée et retour en mémoire partagée. Le test isolé de la session réussit ses cinq assertions. Le redémarrage avec initialisation complète a alors échoué à la création du MTLResidencySet sur le périphérique paravirtualisé. Les mesures de ce paragraphe précèdent cet échec et concernent uniquement les étapes nommées.

La [CI finale, commit `fddb985b`](https://github.com/TarbleFR/RewindBox/actions/runs/45500619250), a compilé le moteur iPhoneOS sur macOS 15 et 26. Sur le M1 virtualisé, 1 354/1 354 contrôles CPU et 65 536/65 536 comparaisons de pixels Metal ont réussi. Le banc de redémarrage a exercé la vraie file Metal avec ressources suivies du runner et a réussi ses huit assertions. Le matériel physique conserve le chemin de test normal du backend. Sur cette répétition, les 1 024 tuiles distinctes sont passées de 25,526 à 9,142 µs par tuile (plages 22,683–37,229 et 6,164–13,734). Les deux exécutions donnent une réduction médiane de 64 à 75 % sur ce microbanc. La taille et la durée des uploads dans les jeux, le trafic DRAM, les FPS affichés, la mémoire et l’énergie sur A18 Pro restent à mesurer. L’[inventaire signé de la 839](rewind839/signed-payload-identity.json) confirme les empreintes du moteur S2Arm et du Core MeloNX issus des deux compilations. La [comparaison avec la 838](rewind839/bridge-comparison.json) attribue les différences des trois ponts ARMSX2, MeloNX et RPCS3 aux références équivalentes à `_objc_msgSend` produites par l’éditeur de liens.

## Synchronisation CPU/GPU 0357–0360

Le lot part du contenu vérifié de la 839 et embarque son Core MeloNX `693c9c94`.

| Priorité | Cause établie dans le chemin exécuté | Modification | Vérification recherchée |
|---|---|---|---|
| 1 | Un wait Metal 4 rencontré pendant le replay peut appeler `rec_drain` pour mettre les morceaux précédents sur la queue. Le CPU rejoint alors dm-encode avant de poursuivre la traduction. | 0357 enregistre le wait avec les opérations de queue existantes. L'ordre devient commit précédent, wait, commit du morceau courant. La fin de l'appel de soumission continue à attendre l'encodeur. | Le fixture existant vérifie l'ordre des appels, la rétention de l'événement et l'absence de drain intermédiaire. Les appels externes et Metal 3 effectuent un drain synchrone. |
| 2 | Un poll de fence prend `g_mu`, également utilisé par le registre des pools et la retraite des ressources. Plusieurs lecteurs de `g_done` accèdent au nombre sans synchronisation C. | 0358 publie la fence terminée avec release et la lit avec acquire. Un poll à zéro et une fence déjà atteinte prennent zéro verrou du registre. Un vrai wait positif garde son sommeil conditionnel. | Poll effectué avec `g_mu` déjà verrouillé, valeur encore en attente et timeout positif. L'absence de donnée terminée reste observable. |
| 3 | `nvn_be_sub_begin` réserve un tampon d'occlusion pour chaque morceau, y compris un morceau de calcul ou sans passe de rendu. Les huit places peuvent attendre le GPU même si la pièce ne lit ni n'écrit de compteur. | 0359 réserve le tampon lors de la première passe qui en a besoin. Un morceau sans réservation laisse le ring disponible. Le ring d’occlusion utilise huit tampons. | Le fixture de visibilité vérifie le cumul, la réutilisation d'un buffer terminé et une réservation unique par morceau. |
| 4 | Le temps `nvn_be_wait` agrège plusieurs causes. | 0360 expose séparément le temps d'attente des allocateurs et des tampons d'occlusion, avec les nombres de waits enregistrés et de drains synchrones. | Lire les différences des compteurs cumulés entre le début et la fin de chaque fenêtre. |

Les trois modifications sont génériques NVN/NVN2. Elles s'activent par défaut. Pour comparer au
chemin de la 839, mettre à zéro l'interrupteur de la modification étudiée.

| Interrupteur | Valeur de référence | Valeur candidate |
|---|---|---|
| `S2A_RB_QUEUE_WAIT_RECORD` | `0` | `1` |
| `S2A_RB_FENCE_FAST` | `0` | `1` |
| `S2A_RB_VISIBILITY_LAZY` | `0` | `1` |

Le rapport existant inclut désormais `[rb-cpu-gpu-sync]`. Les nombres
`queue_wait_records` et `queue_wait_drains` attribuent les jointures du thread d'encodage.
`allocator_wait_ms` mesure le blocage à la limite des huit allocateurs. `visibility_wait_ms`
mesure celui des tampons d'occlusion. `pieces_without_visibility` dénombre les morceaux qui
ont évité cette réservation. Les sommes sont cumulées depuis le début de la session.

Le premier objectif de comparaison reste au moins 1 ms gagnée sur le chemin critique de Zelda,
avec footprint et p99 stables, sur les trois fenêtres de 180 s décrites plus haut. Les 4,4–7,2 ms
des journaux de référence agrègent des causes que ces compteurs doivent départager. La réduction
exacte du nombre de mutex pour un poll terminé est établie par le code. Les gains FPS, watts et
latence en jeu sur A18 Pro restent non mesurés à ce stade.

La réutilisation d'un allocateur et d'un tampon utilisé reste liée à sa fence GPU. Le wait
enregistré conserve le même événement, sa valeur et sa place parmi les commits. Les barrières de rendu 0353 ordonnent les passes selon les dépendances du jeu. Les changements de dimensions, le cumul
des résultats d'occlusion et la fin de session suivent leurs gardes existantes.

### Vérifications du lot de synchronisation

La [CI du moteur `c9e6d4ea`](https://github.com/TarbleFR/RewindBox/actions/runs/45553147358)
a compilé le moteur iPhoneOS sur macOS 15 et 26. L'archive du moteur est authentifiée par
l'API, numéro `14996120007`, SHA-256
`b2d1fb0c9d39c4cefd7bb58a3fcf04b58207ca12b839a01be6d338dc91ceda69`.
L'empreinte de NS2Pro correspond à celle de la 839.

- Les neuf contrôles ciblés de `t_nvn_wait_event --rb-cpu-sync` passent. Ils couvrent le mutex
  déjà tenu, un poll encore en attente, le timeout positif, le chemin de référence, l'ordre
  des opérations enregistrées et la durée de vie de l'événement. Ce mode utilise une simulation
  des appels de queue et exécute le vrai code d'enregistrement.
- Les sept contrôles de `t_nvn_visfold` passent avec un vrai buffer partagé Metal. Le cumul de
  100 000 résultats reste exact, le cumul est plié avant réutilisation et la seconde passe
  conserve la même réservation.
- Le contrôle local de l'en-tête de poll concurrent a effectué 2 000 000 évaluations sur quatre
  threads, dont 1 000 000 encore en attente, comptées exactement.
- Les groupes généraux Flutter et natifs de l'IPA restent déclarés non exécutés. La compilation
  et les contrôles ciblés du moteur sont ceux du producteur ci-dessus.

Les tests GPU complets de rendu et les waits Metal 4 sur A18 Pro restent à exercer sur appareil.
Les 9 et 7 assertions ne constituent pas une mesure de FPS, de consommation ou de bande passante.

### Livraison privée 840

L'[IPA 840 vérifiée](rewind840/delivery.json) embarque le moteur `c9e6d4ea`, patchs 0357–0360,
avec les trois options actives par défaut. Elle part de la 839 et embarque son Core MeloNX
`693c9c94`. Le [run 45555451366](https://github.com/TarbleFR/RewindBox/actions/runs/45555451366)
a réussi à la tentative 2 après un HTTP 503 lors du téléchargement de MeloNX à la tentative 1.
Le preflight et ses dépendants ont été relancés sur le même commit `d436aac8`.

Le fichier privé pèse 335 268 154 octets et son SHA-256 est
`83e34eb69229bbd67a4c28cddf23035b5bbc7916121bb7128e4867df7ff25d62`.
L'[inventaire signé](rewind840/signed-payload-identity.json) contient 98 images.
Les six validateurs de la vérification finale ont réussi. Les différences des ponts
ARMSX2 et MeloNX avec la 839 sont expliquées par les références équivalentes à
`_objc_msgSend` dans le [calcul de comparaison](rewind840/bridge-comparison.json).

Le fixture d'occlusion appelle directement la réservation et le cumul des slots.
Le parcours complet de soumission et le rendu en jeu sur A18 Pro restent à valider
sur appareil. Les interrupteurs comparent les chemins d'attente. La publication atomique
des résultats fournit l'ordre mémoire C dans les deux variantes.

## Contre-expertise 0361–0365

La contrainte du mainteneur du 25 novembre est de garder la vitesse initiale des jeux.
Le lot part du moteur vérifié de la 840, source `c9e6d4ea`.

| Point revu | Constat dans la 840 | Correction |
|---|---|---|
| Retraite d'allocateur | Après l'annulation d'un `nvn_be_wait`, le drainage de dm-encode était suivi d'un `reset` même si le GPU n'avait pas terminé. Le défaut remonte au chemin de 0337. | 0361 autorise le reset après completion. Sur annulation, le CPU finit son encodage puis réutilise séquentiellement l'allocateur en ajoutant des commandes. Sa mémoire en vol est protégée jusqu'à la fence. |
| Réservation de visibilité | Le helper retournait sans statut sur annulation. L'ouverture de passe pouvait alors tenter une allocation d'overflow. | 0361 retourne l'échec à la passe. Un échec d'allocation possède un diagnostic. |
| Changement de session | Le cache local `read` de `rb_piece_option` n'était pas réinitialisé. Une ancienne valeur `S2A_RB_PIECE_DRAIN=1` pouvait imposer des jointures dans la session suivante. | 0362 réinitialise choix, profondeur et compteurs au début d'une session drainée. |
| Comparaison A/B | `rc_done` prenait toujours le chemin atomique, y compris avec `S2A_RB_FENCE_FAST=0`. | 0362 applique aussi ce choix aux lectures de timestamps. La publication atomique garantit l'ordre mémoire dans les deux modes. |
| Coût par wait | 0357 créait un bloc Objective-C et ses captures pour chaque wait différé. | 0363 utilise un record de taille fixe contenant l'événement retenu et sa valeur. La sélection exige un proxy dont le commit passe également par dm-encode. |
| Attribution des attentes | Le rapport comptait les drains intra-soumission, avec une couverture incomplète des appels externes. Une dépendance externe déjà satisfaite drainait aussi l'encodeur. | 0364 compte les deux voies et leur blocage réel. Une dépendance externe terminée rend la main immédiatement en mode optimisé. |
| Qualité du contrôle d'occlusion | Une assertion contrôlait des variables que le fixture venait lui-même de mettre à zéro. | 0365 appelle le vrai helper de début de soumission après avoir installé un état antérieur. Il exerce également le ring occupé, l'annulation et le mode de référence. |
| Contrôle GPU | Les neuf assertions de queue de la 840 utilisaient une simulation d'appels. | 0365 ajoute un mode du fixture existant avec la vraie queue Metal 4, le vrai worker et des command buffers vides. Il vérifie la progression avant le wait, le blocage de ses consommateurs puis leur libération, avec un allocateur partagé sans reset. |

Metal 4 permet d'associer séquentiellement un allocateur à plusieurs command buffers après
la fin de leur encodage. Le reset intervient après la fin de l'utilisation GPU. Cette règle
est celle du [modèle de commandes Apple](https://developer.apple.com/documentation/metal/understanding-the-metal-4-core-api).

### Respect de la vitesse d'origine

Les [huit comparaisons de sources](s2arm-sync-review-speed.json) portent sur l'intégralité de
`hle_nvn.c` et les corps de `gpu_ticks`, `nvn_be_fps_target`, `nvn_be_link_wait_tick`,
`present_enqueue`, `rb_depth_keep_queue`, `present_m3` et `present_now`. Leurs empreintes
correspondent exactement au moteur de la 840. Ce contrôle porte sur les horloges, la cadence
cible et la présentation. La fidélité et le débit effectifs en jeu demandent une mesure sur
l'iPhone.

### Contrôles ciblés de la contre-expertise

Les fixtures existants couvrent les lectures atomiques et le chemin de référence,
l'annulation, la rétention des événements, la réinitialisation des choix après session
et le cycle de vie des buffers de visibilité. Le mode GPU utilise des command buffers vides
pour exercer les événements sans dépendre d'un residency set du runner virtuel.
Un périphérique sans queue Metal 4 renvoie explicitement le statut indisponible.
La [CI 45562902054](https://github.com/TarbleFR/RewindBox/actions/runs/45562902054) du moteur
`c98c57e7` compile sur macOS 15 et 26. Les contrôles CPU sont 12/12, ceux de visibilité
10/10 et ceux de changement de session 9/9. La création de la queue Metal 4 est refusée par
le périphérique virtuel avec `Device does not support Metal 4`. Ce test GPU est indisponible.

0366 complète le fixture existant avec le vrai worker dm-encode et une queue simulée.
Il contrôle la publication du bloc, l'ordre des opérations, le thread consommateur et la
libération de l'événement avant le signal idle. La CI finale ci-dessous valide ses quatre assertions sur le vrai worker.


### Résultats finaux de la contre-expertise

La [CI 45565566639](https://github.com/TarbleFR/RewindBox/actions/runs/45565566639) a compilé
le moteur iPhoneOS `31726e1b` sur macOS 15 et 26. Le [reçu des contrôles](s2arm-sync-review-checks.json)
lie la source, les deux jobs et les empreintes des archives téléchargées.

| Contrôle | Résultat |
|---|---|
| Prédicats de fences, référence et annulation | 12/12 |
| Publication et consommation sur le vrai dm-encode, queue simulée | 4/4 |
| Cycle de vie des buffers de visibilité partagés Metal | 10/10 |
| Choix et compteurs après changement de session | 9/9 |
| Queue GPU Metal 4 native | Indisponible, device du runner incompatible |
| Horloges, cadence cible et présentation comparées à la 840 | 8/8 identités de sources |

Le premier essai du contrôle worker, source `e2e1f1e5`, exécutait son helper de queue avant
l'amorçage du worker et a échoué sur deux assertions. Le fixture démarre maintenant dm-encode
par `rec_put`, comme les méthodes des proxies. Les quatre assertions passent après cette
correction. Cette erreur concernait l'amorçage du contrôle.

Les waits différés utilisent un record fixe et un événement retenu. L'allocation d'un bloc
Objective-C par wait a été supprimée. Cette différence est établie par le code. Une dépendance
externe déjà terminée évite aussi la jointure avec l'encodeur en mode optimisé.

Les mesures de FPS, de latence, de mémoire et de consommation en jeu, la validation visuelle
et l'endurance thermique sur A18 Pro restent à effectuer. Les résultats ci-dessus distinguent
les assertions CPU, la mémoire partagée Metal et l'indisponibilité du test GPU Metal 4.

Le moteur corrigé est compilé et épinglé sur `Claude`. L'[attestation des trois producteurs](https://github.com/TarbleFR/RewindBox/actions/runs/45567968359)
a reconstruit un pin de 76 421 octets, identique au fichier commité. Son SHA-256 est
`4af72f8129e3676e495cfe2736222bdef394f09a55d0d6cf284683c7c1868e20`.
L'empreinte du moteur est `65ff9a82e791b679df36a7148ad278e45ddc5a462d37ca784c714c302435310f`.
Le résultat de cette mission comprend les correctifs sources, le moteur compilé, son pin
vérifié et ce rapport de contre-expertise.

## Zelda 840 : attente restante et lot 0367–0378

Journaux transmis le 25 novembre : [deltas par fenêtre](s2arm-zelda840-sync.json).
Le format identifie les compteurs 0357–0360 ; l’étiquette IPA 840 vient du mainteneur,
le journal ne contient pas l’empreinte cryptographique de l’IPA.

| Images de début → fin | Δ allocateur, ms | ms/image | Δ visibilité, ms | Δ waits enregistrés | Δ drains comptabilisés |
|---|---:|---:|---:|---:|---:|
| 0 → 300 | 18.936 | 0.0631 | 0.000 | 103 | 0 |
| 300 → 600 | 4.611 | 0.0154 | 0.000 | 107 | 0 |
| 600 → 900 | 10.336 | 0.0345 | 0.000 | 137 | 0 |
| 900 → 1200 | 17.946 | 0.0598 | 0.000 | 97 | 0 |
| 1200 → 1500 | 0.000 | 0.0000 | 0.000 | 120 | 0 |
| 1500 → 1800 | 52.960 | 0.1765 | 0.000 | 121 | 0 |
| 1800 → 2100 | 801.917 | 2.6731 | 0.000 | 188 | 0 |
| 2100 → 2400 | 567.016 | 1.8901 | 0.000 | 227 | 0 |
| 2400 → 2700 | 330.883 | 1.1029 | 0.000 | 203 | 0 |
| 2700 → 3000 | 643.364 | 2.1445 | 0.000 | 239 | 0 |
| 3000 → 3300 | 454.010 | 1.5134 | 0.000 | 249 | 0 |
| 3300 → 3600 | 1172.889 | 3.9096 | 0.000 | 272 | 0 |
| 3600 → 3900 | 804.602 | 2.6820 | 0.000 | 237 | 0 |
| 3900 → 4200 | 51.210 | 0.1707 | 0.000 | 149 | 0 |

Sur 1800–4200 : 4825,891 ms / 2400 images = **2,010788 ms/image** d’allocateur.
Le seuil de 1 ms/image est dépassé : le mode par image est ajouté sous interrupteur.
Les anciennes 4,4–7,2 ms/image agrègent plusieurs causes, et les scènes/conditions ne
sont pas appariées. Une baisse causale de cette attente globale n’est donc pas établie.
Le zéro `queue_wait_drains` de la 840 ne couvre pas les drains externes prêts ;
0364 corrige cette attribution. La visibilité mesurée reste à zéro.

Dans les fenêtres 3D (2100–3900), les médianes GPU sont 25,77–31,35 ms, vitesse
27,9–55,5 % suivant la fenêtre, état Serious. Le téléphone commence déjà à l’état
Fair. L’objectif 100 % / 60 images/s / absence de Serious n’est pas atteint.
Les trois profils CPU de quatre secondes ne constituent pas trois fenêtres de
180 secondes ; aucun gain FPS ou watts n’est attribué à ces seuls relevés.

Le [lot moteur et ses sept interrupteurs](../../build-utils/s2arm/engine/README.md#zelda--diagnostic-et-moteur-03670378-25-novembre-2026)
0367–0378 est implémenté et compilé sur les deux hôtes macOS. Les tests purs GCC passent 342 assertions
(cas négatifs inclus : copie/encodeur/barrière, source inconnue, option coupée,
epoch de session et délais conservés). Clang passe 347 assertions sur macOS 15 et 26 ; le moteur iPhoneOS est compilé sur les deux hôtes.
Le diagnostic ajoute une charge de journalisation ; le couper pour les mesures A/B.
Aucun correctif du rythme des jeux ni aucune correction spéculative des réveils.

Le traducteur attend un relevé `S2A_RB_GPUDIAG`. Le lot TBDR et la file de résidences
restent ensuite à instruire. Le cache système iOS de ≈1,33 Go reste une hypothèse :
aucune purge ni modification de sa politique.

Relecture du lot : la première CI `45571726110` a passé les 327 premiers contrôles
Clang sur macOS 15/26, puis a refusé le pointeur `NSError **` non qualifié ARC.
0376 conserve la propriété `__autoreleasing` du paramètre. 0374 ajoute les attentes
placées dans les helpers de fences et de files secondaires ; 0375 complète les
propriétaires de compilation calcul et les jobs de rendu encore en file.
Le test GCC final couvre aussi le vrai helper de fence : 337 assertions. Un
contrôle négatif supprimant les barrières nécessaires échoue comme attendu.
Huit comparaisons des sources de vitesse/cadence sont identiques après retrait
mécanique des seules enveloppes de comptage ; `hle_nvn.c` est identique octet par octet.
[Empreintes de ces contrôles](s2arm-zelda-speed-preservation.json).

0377 affine l’attribution des syscalls : un événement `kevent64` réussi ne doit
pas être compté comme une erreur pthread ; retour natif et `errno` sont préservés,
avec un chemin direct quand le diagnostic est coupé. GCC final : 342 assertions.
La dernière compilation doit inclure ce correctif pour que les chiffres soient
interprétables. Le premier intervalle 0–300 du tableau infère les zéros du reset
0360 ; les treize autres différences utilisent deux relevés effectivement présents.

Le contrôle du registre `DshXfpInput` retrouve **252 fichiers, 2 943 682 octets**,
avec les mêmes octets qu’avant ce lot et le même en-tête ABI. Son expansion explicite
reproduit l’empreinte `121d1bca8eb35c16`. Il ne s’agit pas d’une exécution MSBuild.
[Preuve de l’identité des entrées](s2arm-zelda-translator-identity.json).

Pour attribuer les réveils dans un relevé court de la 841, fusionner ces lignes dans les réglages
existants, puis relancer l’app :

```ini
S2A_RB_WAKE_DIAG=1
S2A_RB_GPUDIAG=0
S2A_RB_PROBE_EVERY=30
```

Les variantes `S2A_RB_ALLOC_FRAME=1`, `S2A_RB_DISPATCH_ORDER=game`,
`S2A_RB_PSO_WAIT_BOOST=1` et `S2A_RB_ARCHIVE_ERROR_NIL=1` sont indépendantes.
Leur absence conserve les chemins de référence. Pour l’A/B, couper les deux
diagnostics, garder la même cadence de sonde entre variantes et ne modifier qu’un
seul de ces modes. Trois fenêtres de 180 s par variante restent nécessaires sur
le téléphone, puis endurance thermique d’au moins dix minutes. Le lot traducteur
ne doit être figé qu’après lecture de ces nouveaux diagnostics.

0378 lit le champ `early_z` du JSON **déjà produit**. Le rapport donne sa valeur
connue/inconnue et `missing_requested_early=1` lorsque le jeu demandait le test
précoce mais que l’annotation manque dans la source connue. La présence de
l’annotation ne prouve toujours pas le comportement matériel de chaque entrée.
Le test pur final comporte 347 assertions.

Recalcul du relevé avec les deux bornes réellement journalisées :

```sh
python docs/evidence/s2arm-sync-window-reader.py host.log --from-frame 1800 --to-frame 4200
```

Les champs width/height des lignes de cible décrivent la vue Metal ; le niveau
mip est rapporté séparément. Pour un mip non nul, ramener les dimensions au
niveau attaché avant de comparer des cibles. `allocator_bytes` borne l’observation
mémoire ; le plafond de huit objets allocateurs ne borne pas à lui seul la taille
de leurs heaps. L’essai par image reste sur demande tant que le pic n’est pas mesuré.

### Validation finale de 0378

[CI 45574225411](https://github.com/TarbleFR/RewindBox/actions/runs/45574225411),
source `35eb173f`, tentative 1 : compilations iPhoneOS réussies sur macOS 15 et 26.
347 assertions GCC, 347 Clang par hôte, 34 contrôles du vrai sérialiseur avec
archive de protocole Foundation par hôte, et 35 contrôles de fences, worker,
visibilité et sessions. [Détails et portée](s2arm-zelda-0378/checks.json).
Le GPU du runner refuse Metal 4 : le replay de pixels et les mesures A18 Pro
restent non exécutés. Les trois archives productrices sont vérifiées ; NS2Pro
conserve son empreinte de la 840. L’[IPA privée 841](rewind841/delivery.json) est vérifiée et livrée ; la mesure du nouveau lot sur iPhone reste à faire.

### Livraison privée 841

[Rapport autonome](s2arm-zelda-841.md) · [Reçu](rewind841/delivery.json).
Source application `a019a0b7`, run `45578695343`, tentative 1. Les 98 images natives,
six validateurs et les octets signés de l’IPA sont contrôlés. Les quatre ponts
libretro/MeloNX/RPCS3/ARMSX2 sont strictement identiques à la 840. S2Arm 0361–0378
est livré ; MeloNX `693c9c94` et NS2Pro sont conservés. Le moteur conserve ses 252
entrées de traducteur identiques. Aucun résultat A/B du nouveau lot sur téléphone.

Pour la capture GPU suivante, `S2A_RB_WAKE_DIAG=0` et `S2A_RB_GPUDIAG=1` séparent
la journalisation des passes de l’attribution des réveils. Les passages A/B se font
ensuite avec les deux diagnostics coupés, sans changer la cadence de sonde entre variantes.
