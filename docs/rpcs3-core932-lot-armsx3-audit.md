# RPCS3 Core 932 — lot ARMSX3 et premiers correctifs de l'audit du 11 novembre

Demandes du mainteneur (11 novembre 2026) : « intègre tout ce qui peut être utile » de l'IPA ARMSX3 21863, « Adapte ce que tu
penses qu'il n'a pas optimisé », « Je ne veux pas de plafonds de FPS ! », puis le chantier urgent transmis par Codex
(*RPCS3 — optimisation globale, profils, thermique*, 243 lignes, fichier privé, hors Git).

**Niveau de preuve.** Écrit et testé sur hôte (Linux, g++). Pas encore compilé pour iOS au moment de ce dossier ; rien n'a été
exécuté sur un iPhone ; aucun gain d'images par seconde, d'énergie ou de mémoire n'est annoncé.

Moteur : branche `core932-armsx3` (base Core 931 `605901a`), commits `f361e35`, `025a03a` (correctif de revue) puis
`94354ea` (les entrées MLAA de Killzone 3 gardent leur défaut de la base, § 2.9). Canonique `9a113440` (472 fichiers), delta
`702d293a`, build 932.

## 1. Rapprochement avec l'audit (snapshot `fd3c39ae`)

Depuis ce snapshot, rien n'a changé côté RPCS3 : le Core 931 est toujours épinglé (`83156c06`). Seul le Core MeloNX 735 a été
épinglé depuis (`4d391b8d`).

| Constat de l'audit | Dans le code courant | Core 932 |
|---|---|---|
| THERMAL931 classe une fenêtre avec l'état lu à sa fin | confirmé | registre des états par fenêtre (§ 2.2) |
| `thermal_comparison()` compare sans fixer les autres leviers | confirmé | comparaison à leviers égaux, ordre vérifié (§ 2.4) |
| un compteur qui recule devient 0 (`IOSEnergy931.h`) | confirmé, et le harnais 931 l'exigeait | métrique invalide, jamais 0 (§ 2.1) |
| harnais WFE : une borne globale de 5 s seulement | confirmé ; les commentaires affirmaient « ~1 µs » | durée réelle de chaque WFE mesurée, cas « autre adresse » (§ 2.3) |
| démarrage terminé en arrière-plan : pause au rapport (~5 s) | confirmé | pause demandée à la transition (§ 2.5) |
| BO2 reconnu sous BLES01717 seulement | confirmé (`IOSTitleLevers.h:69`) | six numéros (§ 2.8) |
| BLES01884 exclu de la correction LLVM d'AC IV | exclusion côté Dart seulement | conservée (§ 3) |
| 12 compilations bloquantes BO2 (IPA 725) | classées (§ 2.7) | compilation Metal concurrente au démarrage ; reste ouvert |
| familles = métadonnées, pas de moteur de décision | confirmé (enquête) | première règle partagée (§ 2.10) ; résolveur unifié au Core 933 |

## 2. Changements

### 2.1 Énergie : compteurs invalides, sans image, vrai zéro (`REWINDBOX_ENERGY_VALIDITY_932`, `REWINDBOX_DISK_IO_932`)

- **Symptôme.** Un compteur qui recule entre deux fenêtres (remise à zéro, autre comptabilité) s'affichait `0`, ce qui se lit
  comme une économie d'énergie.
- **Correction.** `IOSEnergy931.h`. Chaque métrique dont un compteur recule s'affiche `invalid`, ainsi que toutes celles qui en
  dérivent. La ligne les compte (`discontinuities=`). Les cas sans valeur sont nommés au lieu de valoir 0 :
  - fenêtre sans image : `mj_per_frame=no_frames` ;
  - sans temps CPU : `p_share=no_cpu` ;
  - sans cycles : `ipc=no_cycles`.

  `0` n'est imprimé que pour une vraie différence nulle. La ligne gagne aussi le trafic de stockage de la fenêtre, repris du
  journal d'ARMSX3 : `disk_read_mib`, `disk_write_mib`, `logical_write_mib` et `pageins`, lus dans le même `rusage_info_v6`.
- **Ce que mesure l'énergie.** L'énergie CPU que le système attribue au processus. Ce n'est pas la consommation totale de la
  batterie, et `gpu_utilisation_delta` est un compteur brut, pas des watts. L'analyseur l'écrit en tête de section.
- **Vérification.**
  - Harnais 932 : neuf régressions de compteur testées une à une, plus les cas sans image, sans CPU et sans cycles, le vrai
    zéro, l'absence de données et la première fenêtre.
  - Le harnais 931 exigeait « un compteur qui recule vaut 0 ». Cette assertion encodait le défaut. Elle est remplacée, sur un
    arbre 932, par l'exigence stricte `invalid` ; l'ancienne reste pour un arbre 931.
  - Un mutant qui remet l'ancien calcul est détecté.

### 2.2 Registre thermique par fenêtre (`REWINDBOX_THERMAL_LEDGER_932`)

- **Symptôme.** Une fenêtre qui chauffe en son milieu comptait entièrement dans l'état le plus chaud.
- **Correction.** `IOSThermalPolicy931.h`. Chaque notification d'état alimente un registre : temps passé par état et nombre de
  transitions. THERMAL931 ajoute :
  - `window_state_begin` et `window_changes` ;
  - `ms_unknown/nominal/fair/serious/critical` ;
  - `window_mixed` ;
  - `event_waits_window` : `on`, `off`, ou `mixed` quand, en mode Automatique, la fenêtre a duré des deux côtés du seuil
    « serious ».
- **Fenêtres mixtes.** Elles ne peuvent pas être découpées, car la ligne d'énergie couvre toute la fenêtre. L'analyseur les
  exclut.
- **Vérification.** Harnais :
  - une fenêtre stable, une transition, une notification répétée qui n'est pas une transition, et la première fenêtre sans
    début ;
  - le mode des attentes pour chaque combinaison (Automatique, Activé, Désactivé, étape de comparaison).
  - Un mutant « fenêtre jamais mixte » est détecté.

### 2.3 Latence de réveil des attentes par événement (`REWINDBOX_EVENT_WAIT_LATENCY_932`)

- **Symptôme.** Le harnais 931 ne prouvait qu'un réveil sous 5 s. Le code affirmait qu'un WFE finit « en ~1 µs » sur iPhone,
  ce qui n'est pas établi.
- **Correction.** `IOSEventWait931.h` mesure, autour de chaque WFE, sa durée réelle sur le compteur générique. Il range chaque
  durée dans cinq classes (moins de 2 µs, 16 µs, 128 µs, 1 ms, plus), et garde la plus longue. THERMAL931 imprime
  `wfe_latency_us=` et `wfe_longest_us=`.
- **Commentaires corrigés.** Ceux de `vm.cpp` et `RSXFIFO.cpp` ne posent plus de latence comme un fait. Le test 917 accepte le
  nouveau texte ; le code est identique caractère pour caractère.
- **Vérification.** Harnais :
  - réveil par écriture sur la ligne surveillée ;
  - requête portée par une autre ligne (arrêt, vidage) : vue dans la borne de 2 s, durée imprimée et non affirmée ;
  - un mot déjà changé repart sans WFE et n'enregistre rien.
  - Sur ARM64 Apple, la CI exigera que des WFE soient mesurés.
- **Limite.** Aucun interblocage n'est annoncé, ni dans un sens ni dans l'autre. La latence réelle sur iPhone se lira dans les
  journaux.

### 2.4 Analyseur : comparaison à conditions égales (`tools/rpcs3/capture_analyzer.py`)

- **Fenêtres exclues et comptées :**
  - mixtes (`window_mixed=1`, attentes `mixed`) ;
  - à énergie invalide ;
  - sans image.
- **Comparaison.** Les attentes ne sont comparées qu'entre fenêtres du même état thermique et des mêmes autres leviers
  (`park_spin`, `busy_wait_scale`, passe de comparaison du Core).
- **Ordre des essais.** Si toutes les fenêtres d'un côté précèdent toutes celles de l'autre, la sortie indique « non
  contrebalancé » : la différence contient aussi le temps passé à jouer, pendant lequel l'iPhone chauffe.
- **Journaux du Core 931.** Ils n'ont pas de transitions ; la sortie dit qu'ils sont classés par l'état lu en fin de fenêtre.
- **Vérification.**
  - Le scénario 931 passe toujours.
  - Un scénario 932 vérifie : 1 fenêtre mixte et 1 fenêtre invalide exclues ; deux strates de leviers ; un ordre entrelacé ;
    un ordre non contrebalancé signalé ; le trafic disque.

### 2.5 Pause en arrière-plan à la transition (`REWINDBOX_BACKGROUND_PAUSE_TRANSITION_932`)

- **Symptôme.** Un démarrage qui se terminait en arrière-plan n'était mis en pause qu'au rapport suivant, environ 5 s plus
  tard.
- **Correction.** Au passage `starting → running` (`Emulator::FinalizeRunRequest`), le Core demande la pause si l'application est
  en arrière-plan et que la pause n'est pas déjà la sienne.
  - La décision reste prise sur le fil principal, selon l'état de l'application : un retour rapide au premier plan l'annule.
  - Le gate GPU et l'ordre des opérations sont inchangés.
  - La reprise automatique ne reprend que sa propre pause ; une pause manuelle n'est jamais reprise.
  - L'appel ne fait que mettre en file : il n'attend jamais, donc pas d'interblocage.
- **Vérification.** Harnais :
  - au premier plan : rien ;
  - en arrière-plan : une demande ;
  - déjà en pause par le Core : aucune nouvelle demande ;
  - après une pause manuelle : refus, et jamais de reprise.
  - Un mutant « demande au premier plan » est détecté.
- **Non changé.** La pause des menus RewindBox reste un choix produit ; elle n'a pas été modifiée.

### 2.6 Moins de travail spéculatif à chaud (`REWINDBOX_PREHASH_THERMAL_932`)

- **Symptôme.** Le pré-calcul des empreintes de textures était dimensionné seulement par son taux d'utilisation. Or un calcul
  inutilisé, c'est de la chaleur pure.
- **Correction.** `IOSTexturePrehash.h` et `texture_cache.cpp`.
  - Dès l'état « fair » (échauffement modéré), la profondeur gardée par la règle du Core 910 est divisée par deux tant que moins
    des deux tiers des empreintes sont utilisées. Au nominal, le seuil reste la moitié.
  - Dès « serious », elle est plafonnée à la moitié du maximum.
  - Le calcul à la demande par le fil RSX reste intact : le résultat est identique, seule l'avance change.
- **Vérification.**
  - `static_assert` dans l'en-tête.
  - Suites de frames dans le harnais : au nominal, inchangé ; « fair » à 60 % d'utilisation, la profondeur descend au plancher ;
    « serious », plafonnée.
  - Le test 909 garde son texte exact.
  - Un mutant sans réduction est détecté.

### 2.7 Compilations bloquantes de BO2 : classement et premier correctif

- **Classement des 12 constructions bloquantes** (journaux privés de l'IPA 725, BO2, PID 52378, fenêtres 11, 23, 26 et 27),
  d'après `SHADERPIPE543`, `SHADERCOST534` et `PRESSURE547` :
  - 8 pipelines contenaient un programme réellement nouveau (1 vertex, 7 fragment). Le temps passe dans
    `vkCreateGraphicsPipelines`, donc la compilation Metal de MoltenVK : 435 à 581 ms chacune. La compilation GLSL → SPIR-V
    prend seulement 7 ms pour 2 shaders.
  - 4 variantes d'état sur des programmes connus : 1,5 à 2,5 ms, négligeables.
  - Aucune attente d'un travail déjà en cours (`pending_wait=0`). Aucune recompilation (`repeated_builds=0`).
  - Les 3 enregistrements de la fenêtre 11 ont été écrits durablement (`SHADERPUB543 failures=0 durable_fsync=1`), donc
    restaurés au lancement suivant.
- **Pas de piste « vu mais non restauré ».** L'hypothèse d'une perte à la fermeture est réfutée : le cache écrit en continu,
  pas seulement à la sortie.
- **Correctif (`REWINDBOX_METAL_CONCURRENT_COMPILATION_932`).** MoltenVK demande à Metal de compiler plusieurs shaders en même
  temps (`MVK_CONFIG_SHOULD_MAXIMIZE_CONCURRENT_COMPILATION`). La restauration au démarrage construit chaque pipeline enregistré
  sur plusieurs workers : leurs compilations Metal ne s'attendent plus les unes les autres quand le cache du pilote est froid.
- **Limite.** Une compilation en jeu sur le fil RSX reste seule et ne gagne rien. Le seul chemin asynchrone sans dessin perdu
  serait l'interpréteur de shaders, qui reste désactivé sauf accord séparé.

### 2.8 Variantes de Black Ops II (`REWINDBOX_TITLE_VARIANTS_932`)

- **Correction.** Les leviers BO2 s'appliquent aux six numéros que la liste officielle de compatibilité RPCS3 regroupe sous
  « Call of Duty: Black Ops 2 » : BLES01717, BLES01718, BLES01719, BLES01720, BLUS31011 et BLUS31140.
- **Pourquoi c'est sûr.**
  - La base de configuration RPCS3 donne la même entrée à ces six numéros (le test le vérifie).
  - Chaque levier agit sur le comportement du moteur du jeu (attentes ZCULL, plage de profondeur, validation des textures,
    attentes SPU, soumissions), aucun sur une adresse d'exécutable.
  - Le mémo de textures garde ses vérifications échantillonnées.
- **Exclusion.** Aucune édition numérique, car aucune source ne la nomme.
- **Limite.** Au premier lancement d'une variante, les shaders de sommets corrigés (Z-clip, invariance) sont compilés une fois.
- **Test mis à jour.**
  - La garde d'invariance de position, relancée par la CI Apple, gardait BLUS31011 comme témoin non ciblé et échouait donc
    sur l'arbre 932.
  - Elle attend maintenant les six numéros et garde comme témoins négatifs les numéros voisins (BLES01716, BLES01721,
    BLUS31010, BLUS31141) et des numéros tronqués ou allongés, car la correspondance est exacte.
  - Elle passe sur le 932 et échoue sur le 931, comme prévu.
  - Les anciens tests `cell575` et `cell589`, qui nomment aussi BLUS31011, échouaient déjà sur l'arbre 931. Ils ne sont pas
    lancés.

### 2.9 Correctifs de jeux d'ARMSX3 (`REWINDBOX_CANARY_PATCHES_932`)

- **Source.** Le fichier `canary_patches.yml` d'ARMSX3 21863 est embarqué octet pour octet : SHA-256 `1955e1d8…`, 55 715 octets,
  licence GPL-2.0-only comme RPCS3, auteurs nommés dans chaque entrée. Il est chargé après `patch.yml` et
  `imported_patch.yml`, et la liste des patchs iOS le charge dans le même ordre.
- **Activés par défaut : 42**, la liste d'ARMSX3 lue dans son binaire, sans ses deux entrées Killzone 3 ; chacun répare un
  défaut documenté (gel, plantage, blocage, image absente ou noire).
  - Sonic 06.
  - HAWX 2.
  - Ratchet & Clank, 10 exécutables.
  - SoulCalibur V.
  - Burnout Paradise.
  - NBA 08, ×2.
  - Gran Turismo 6 : MLAA et flou de mouvement, 8 exécutables.
  - Splatterhouse.
  - GTA IV.
  - The Idolm@ster 2.
  - Blitz : The League II, ×2.
  - Naughty Bear.
  - J-Stars.
  - Skylanders.
  - Journey.
- **Laissés désactivés : 7.**
  - La règle de salon de Batman : Arkham Origins.
  - Les 5 options de LittleBigPlanet 2.
  - Tales of Graces f : ARMSX3 l'associe à une limite à 60 FPS, et RewindBox n'en fixe aucune.
  - Hors fichier, les deux « Disable MLAA » de Killzone 3 de la base officielle, qu'ARMSX3 active : aucun défaut documenté
    sans eux, et ils changent l'image. Ils gardent le réglage par défaut de la base (désactivés).
- **Choix de l'utilisateur.** Désactiver un correctif est enregistré (`Enabled: false` dans `patch_config.yml`) et conservé,
  même quand un autre patch est modifié ensuite.
- **Vérification.**
  - Empreinte du fichier.
  - Analyse avec les règles du moteur : scalaires bruts, numéros, versions, types.
  - Table par défaut = fichier − 7 ; les entrées Killzone 3 n'y sont pas.
  - Aucune entrée liée à une limite de FPS n'est active.
  - Contrôles de source.
  - Deux mutants détectés : correctifs non chargés, désactivation non enregistrée.
- **Revue.** Une revue indépendante n'a trouvé aucun défaut sur ce point.

### 2.10 Première règle partagée : lever un réglage devenu inutile (`REWINDBOX_PATCH_RELIEF_932`)

Catalogue de règles :

| Règle | Mécanisme corrigé | Préconditions | Exclusions | Moment | Preuve | Retour arrière |
|---|---|---|---|---|---|---|
| `gt6_mlaa_buffers` | GT6 relit chaque image pour son MLAA SPU, donc la base active Write/Read Color Buffers | « Disable MLAA » appliqué en entier à l'un des 8 exécutables v01.22 ; valeur venue de la base | réglage choisi par l'utilisateur, fichier de configuration explicite, sauvegarde d'état | chargement de l'exécutable, avant la création du moteur graphique | base RPCS3 de chaque numéro GT6 ; patch `be32` unique (testé) | désactiver le patch |
| `gta4_collision_xfloat` | collisions : `0x7FFFFFFF` est un NaN en XFloat Approximate, donc la base impose Accurate | correctif de collision actif pour BLUS30682 v01.02, BLUS30127 ou NPUB30702 v01.08 ; valeur venue de la base | mêmes exclusions, autres versions | démarrage, avant toute compilation SPU | base RPCS3 des trois numéros (testé) | désactiver le patch |

- **Journal.** Chaque décision écrit `PATCHRELIEF932` : la règle appliquée, ou la raison du refus (sauvegarde d'état, choix de
  l'utilisateur, autre version…).
- **Correctif de revue.** La copie de configuration du démarrage (`g_backup_cfg`) suit la valeur levée. Sinon le menu d'accueil
  la verrait changée et remettrait la valeur de la base en pleine partie.
- **Pas de règle pour SoulCalibur V.** Son entrée de base porte aussi Write Depth Buffer, et rien ne prouve que ces réglages ne
  servent qu'au MLAA.

### 2.11 Zone JIT (`REWINDBOX_JIT_STEP_932`)

- **Correction.** Quand l'espace d'adressage est fragmenté, la réservation descend par pas de 16 Mio au lieu de 64. Toutes les
  tailles de l'ancienne suite restent essayées dans le même ordre : la zone n'est jamais plus petite qu'avant. Une fenêtre de
  380 Mio donne 368 Mio de code au lieu de 320.
- **Vérification.** La vraie fonction `reserve_capacity_layout` est confrontée à l'ancienne sur 1 035 cas de taille. Un mutant au
  pas de 64 Mio est détecté.
- **Limite.** Le crash d'AC IV, qui demande environ 376 Mio, demande toujours une zone en plusieurs segments.

## 3. Reste à faire, avec la prochaine action

- **Couche unifiée identité, règles et comportement, avec persistance (priorité 3).** D'après l'enquête :
  - aujourd'hui, Dart fusionne la base et ses corrections par numéro (`_serialOverrides`), qui entrent dans le Core comme « base » ;
  - le Core ne voit ni la version ni l'exécutable à ce niveau.

  **Prochaine action (Core 933)** :
  - le Core porte seul la résolution : catalogue de règles après la base, profil local borné et versionné, choix de
    l'utilisateur en dernier, contraintes du moteur ;
  - le fichier `fs::get_config_dir()/local_profiles/<numéro>.yml` est écrit par `fs::pending_file` et invalidé selon ses vraies
    dépendances ;
  - une ligne de diagnostic indique chaque valeur et son origine.

  Côté application, il faudra ensuite retirer `_serialOverrides` et transmettre la version et l'empreinte de l'exécutable.
- **BLES01884.**
  - La liste de compatibilité le nomme bien AC IV, mais la correction LLVM n'a été validée sur appareil que pour BLES01882.
  - L'exclusion Dart reste donc en place jusqu'à un essai.
- **Compilations (priorité 2).**
  - Séparer, par compteurs, le démarrage du jeu et un programme « connu sur disque » d'un programme « nouveau ».
  - Décomposer le coût dans MoltenVK (statistiques de performance) avant toute autre piste.
- **Mémoire (priorité 5).** Repartir des mesures du Core 925+ du bon jeu, puis relier le balayage des textures obsolètes à la
  pression et à la chaleur.
- **Revue.**
  - Domaines 1, 2 et 5 relus sans défaut, plus un risque corrigé.
  - Le format THERMAL931 a été vérifié : 31 spécificateurs pour 31 arguments, types cohérents.
  - Domaines testés sur hôte sans revue indépendante complète : l'attente WFE, la ligne d'énergie, le pré-calcul, le JIT.

## 4. Protocole iPhone (15 à 20 minutes, à 100 %)

**Séquence à jouer.** BO2, GOW3, Assassin's Creed et un titre témoin sans correctif. Pour chaque jeu :
- même scène, référence (Core 931) puis candidat (Core 932) ;
- caches froids puis chauds ;
- noter le chargeur, l'enregistrement vidéo et le mode économie d'énergie.

**À lire dans les journaux :**
- `THERMAL931` : `window_mixed`, les `ms_*`, `wfe_latency_us`, `wfe_longest_us`, `background_transition_requests` ;
- `ENERGY931` : `discontinuities`, `disk_write_mib` ;
- `PATCHRELIEF932` : pour GT6 et GTA IV ;
- `SHADERPIPE543` et `PRESSURE547` : constructions bloquantes ;
- la section énergie de l'analyseur : strates, ordre.

Un gain n'est attribué qu'après répétition, à conditions égales.
