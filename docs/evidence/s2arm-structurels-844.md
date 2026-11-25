# S2Arm : correctifs Zelda et implémentation S1–S5

25 novembre 2026. Base livrée : IPA 843, moteur 0399. Le mainteneur demande
les correctifs des gels puis engage explicitement les cinq chantiers structurels.
Cette autorisation remplace la mention « à valider avant écriture » du plan.
Les [mesures 843](s2arm-zelda-843-device.md) restent la référence ; aucun gain
sur appareil n'est attribué à ce nouveau lot.

Le mainteneur précise ensuite que, sur MKW, la reconstruction visible ne démarre
qu'au troisième essai : téléphone chaud lors des deux premiers, froid lors du
suivant. C'est une observation utilisateur, sans les journaux correspondants.
Elle est compatible avec la suspension thermique du travail spéculatif ; elle
ne prouve ni une suppression de cache ni l'absence totale de compilation lors
des deux premiers essais. Les anciens journaux MKW de l'archive ne datent pas
ces trois essais et ne permettent pas de leur attribuer un état thermique précis.

## Coupures uniformes in-pass, `early_z` NVN2 et activations par défaut (0415–0417)

À la demande du mainteneur, trois chantiers complémentaires entrent dans le même lot IPA 844 (sans configuration `env.txt` côté joueur, chaque point conservant son interrupteur de repli) :

1. **Coupures de passes sur uniformes in-pass (`0415`)** : dans les journaux Zelda 843 (`residency set`, images 6000–7500), 5 121 à 5 282 ombres partielles d'uniformes par 300 images étaient refusées pour « earlier submission running » avec **0** récupération `[rb-ubo-ring]` (~17,5 coupures de passes/image). Cause prouvée dans `rb_ubo_versions.h` : `RB_UB_FRAMES = 5` (seulement 4 soumissions commitées conservées avant écrasement par `g_fence + 1`), alors que Zelda soumet 7 à 17 pièces par image (donc 15 à 35+ fences en vol), et `RB_UB_SPANS = 128`. `0415` porte l'anneau à `64` soumissions, `512` plages de hasard par soumission et un pool partagé de `512` pages à bitset 64 bits (~2,80 Mio statiques, éviction conservative en plage opaque), avec compteurs de diagnostic `[rb-ubo-ring]`. Vérifié en C (`t_rb_ubo_versions` + stress 35 fences/200 plages/éviction, `-Wall -Wextra -Werror`).
2. **`early_z` NVN2 dans le traducteur (`0416`)** : `Dsh.cs` ne propageait `early_z` que pour Switch 1 (`ctl[0x718] & 1`). `0416` ajoute `Nvn2.EarlyZ(ctl)` (`ctl[0x5b] != 0` sur en-tête `0x98761234` / `0xc9`), le relie dans `Nvn2Job` vers `GpuGraphicsState.EarlyZForce` → `ExecutionMode.EarlyFragmentTests` → `[[early_fragment_tests]]` (repli `S2A_RB_NVN2_EARLY_Z=0` via `libc getenv` avec `xfp` dédié), renseigne `early_z` dans la réflexion JSON et évite tout doublon d'attribut dans `PoolArrays`. Compilé localement en C# Release (.NET 10, 0 erreur, 0 avertissement ; `xfp = ecd99354f03b846d`).
3. **Activation par défaut des optimisations déjà encodées (`0417`)** : active par défaut en mode NVN2 hébergé (`nvn_rb_thermal_scope()`, tests autonomes inchangés) :
   - `S2A_RB_DISPATCH_ORDER=game` — avec correction préalable d'un bug critique de `0371` qui avait placé la garde dans `blit()` (copies texture) au lieu de `dispatch_enc()` (dispatches compute), risquant de supprimer les barrières entre copies `texture→buffer→texture` sans optimiser les dispatches compute ;
   - `S2A_RB_SPARSE_FAST_COPY=1` ;
   - `S2A_RB_TILE_RASTER_CLEAR=1` (cohérent avec `rb_tile_session_begin()`) ;
   - `S2A_RB_PSO_WAIT_BOOST=1` ;
   - `S2A_RB_ARCHIVE_ERROR_NIL=1`.

Vérifications locales : `git apply` 0001–0417 (413 patchs) OK, `t_rb_ubo_versions` + stress OK, `S2A.Dsh` Release OK, `s2arm_prepare_identity_test.py` 20/20, `s2arm_engine_bridge_test.py` 274/274, `s2arm_pinned_engine_test.py` 25/25. Compilation CI iPhoneOS moteur ([45672467487](https://github.com/TarbleFR/RewindBox/actions/runs/45672467487)), attestation d'épingle ([45675386809](https://github.com/TarbleFR/RewindBox/actions/runs/45675386809)) et livraison privée IPA 844 ([45676121964](https://github.com/TarbleFR/RewindBox/actions/runs/45676121964)) réussies ; aucun gain mesuré sur iPhone.

## Reconstruction visible au changement de `xfp` et preuve stricte (0414 + pont)

Le mainteneur signale ensuite que, **même téléphone froid, Zelda ne lance aucune
reconstruction visible des shaders et pipelines**, tandis que MKW ne l'a lancée
qu'au troisième essai (téléphone froid). L'inspection du code établit quatre
causes exactes, corrigées par **0414**, `guest.mk` et `S2ArmGraphicsGeneration` :

1. **Zelda / tous titres (`loadprog.c`, `fr.lproj/S2ArmHost.strings`, `nvn_mtl.m`)** :
   `S2ArmGraphicsGeneration` et son bandeau « Reconstruction des shaders et des
   pipelines graphiques » sont réservés à MKW (`0400C3F00006E000`). Sur les autres
   titres, la page de chargement du moteur (`ios/loadpage.m`) n'affiche barre et
   compteur que si `s2a_load_first_run` renvoie `1`, or `docs/wire/warm_done` ne
   stockait que l'empreinte du pack sans `s2a_dsh_xfp()`. De plus, sans historique
   `.binds` ou lorsque le catalogue personnel contient des shaders à retraduire
   (`g_warm_rekept > 0`), `0400` pouvait ne pas admettre les lignes personnelles
   restantes au démarrage. **0414** lie `warm_done` à `<pack>:<xfp>`, ajoute les
   libellés français `loadpage.*` et complète la file connue avec les lignes
   `pso_user.tsv` restantes (après les binds récents) lors d'un changement `xfp`
   ou sans historique `.binds`.
2. **MKW lancement 1–2 (`guest.mk`, `S2ArmGraphicsGeneration.m`)** :
   `_identity` ne contenait que `revision=3` et `chain=0be3f28548fd`, sans `xfp`.
   Après un changement de traducteur (843 puis 844/0411), `active.json` restait
   valide jusqu'à ce qu'un shader de `pso_reference.tsv` soit réécrit en jeu et
   casse son SHA-256. `guest.mk` embarque désormais `S2ArmShaderXfp.txt` dans
   `S2ArmEngine.framework`, inclus dans l'identité de `S2ArmGraphicsGeneration`
   sans toucher à `S2ArmDirectChain.txt` ni invalider la préparation CPU.
3. **MKW à chaud (`rb_reference.inc`)** : `rb_ref_checkpoint` appelait
   `rb_spec_may(0)`, qui bloque à `Serious`. Il admet désormais la voie unique
   requise jusqu'à `Serious` si la marge mémoire est suffisante, tout en restant
   en pause à `Critical`.
4. **Incompatibilité 0406/0408 ↔ `rb_ref_verify` (`pso_archive.h`)** : `0406`
   routait aussi les cibles `rebuild` de MKW vers `.metal4archive` sans peupler
   `g_par_have` (`.metalarchive`), ce qui aurait fait échouer la preuve stricte
   `rb_ref_verify`. **0414** contourne Metal 4 pour les cibles de migration
   stricte (`rebuild` ou `S2A_RB_PREPARE_PROFILE`) et vérifie la place disponible
   (seuil 16) avant d'allouer un serializer afin de conserver le repli d'archivage
   classique au lieu de perdre silencieusement un pipeline compilé.

Vérifications locales exécutées : `git apply` 0001–0414 OK, `t_loadprog` 13/13 +
contrôle C d'invalidation `xfp` OK, `s2arm_prepare_identity_test.py` 20/20,
`s2arm_engine_bridge_test.py` 274/274, `s2arm_pinned_engine_test.py` 25/25.
Compilation iPhoneOS moteur + pont (avec `s2arm_graphics_generation_host.sh`)
demandée ; comportement sur iPhone non encore observé.

## Admission du premier submit (0413)

La revue finale relève une course réelle entre le lancement du préchauffage et
la publication de sa liste connue : `g_warm_started` pouvait être visible alors
que `g_rb_known_active` était encore nul. Le premier submit évitait alors l'attente.
0413 publie explicitement la fin de cette initialisation ; le premier submit
attend cette publication puis les achèvements connus sous les mêmes limites
(30 s maximum, arrêt, choix du joueur, pression critique). Une simple liste
lancée ne vaut pas une liste terminée. Une libération sur limite reste consignée
avec le nombre prêt, échoué et restant ; elle ne promet pas zéro compilation en jeu.
Les jointures du worker sont attribuées à l'attente de soumission dans le relevé
de longue image, au lieu d'être diluées dans le temps invité non expliqué.

## Correction de compilation (0412)

La [compilation 0408–0410](https://github.com/TarbleFR/RewindBox/actions/runs/45659945710)
a atteint le code Metal sur les deux runners, puis refusé la réaffectation d'un
paramètre `objc_externally_retained` dans le découpage des lots d'archives mixtes.
0412 conserve ce sous-lot dans une référence locale `__strong`, sans modifier
l'ordre ni les règles d'admission. Les branches render/compute sont typées
séparément pour supprimer leurs nouveaux avertissements de types incompatibles.
Compilation finale demandée ; les suites approfondies restent non exécutées.

## Quatrième lot (0411) — variantes réellement utilisées sur appareil

Le traducteur sur appareil n'émettait pas `_bv` ni la réflexion `vin` ; le backend
possédait pourtant déjà le routage des formats vers les entrées shadow. 0411
raccorde ce générateur existant à la sortie sur appareil : base et shadow partagent
un seul fichier et une seule bibliothèque. Le host charge la fonction shadow dans
la bibliothèque déjà ouverte ; aucun chargement ni compilation d'une seconde
bibliothèque à la première conversion compatible. Couches, capture géométrique,
transform feedback et sorties de sommets complétées dynamiquement gardent leur ABI.

L'unification des corps intervient **après** la réécriture de l'instance de base,
qui doit voir les lectures dans chaque entrée. Corps commun `always_inline`,
convention de profondeur constante à chaque appel ; conversion de profondeur et
élargissement restent à leur emplacement à chaque retour. Les corps GS/TF/layer
ne sont pas déplacés. Une forme inconnue ou un refus Metal conserve le source
complet. Le couple profondeur/shadow inutilisé est retiré de l'unité compilée.
Cette adaptation s'inspire de [nxnative b989137a51](https://github.com/seedds/nxnative/commit/b989137a51d0801e4f1bb6620b400493211f3f28)
(MIT, crédit conservé). Le backend DSH examiné n'a pas la famille de bibliothèques
pulling de cette référence ; aucune famille fictive n'est ajoutée.

Les sources C# 0411 ont compilé localement en Release (.NET 10, zéro erreur,
deux avertissements existants dans Ryujinx.Common). Aucun nouveau test ajouté.
La modification DSH change `xfp` : les traductions obsolètes seront reconstruites
par la préparation existante avant le lancement, avec sa durée et ses limites
thermiques explicites. La compilation iPhoneOS finale reste nécessaire.

`MTLDynamicLibrary` n'est pas employée dans ce lot : l'API sérialise une
[bibliothèque de fonctions auxiliaires liée aux entrées](https://developer.apple.com/documentation/metal/shader-libraries),
pas arbitrairement la bibliothèque exécutable DSH. Externaliser le corps des
sommets changerait l'inlining et exigerait une validation numérique distincte.
La persistance intégrée ici est celle du premier binaire PSO via le serializer
Metal 4. Il ne faut donc pas déclarer la sérialisation des bibliothèques MSL faite,
ni promettre la disparition de toute compilation à froid.

## Troisième lot (0408–0410)

La [compilation 0404–0407](https://github.com/TarbleFR/RewindBox/actions/runs/45657158404)
a échoué sur les deux runners : déclaration de `nvn_rb_thermal_scope` manquante
avant le worker C. 0410 corrige cet ordre et donne au worker une pile de 8 Mio,
comme aux workers Metal existants. Ce résultat ne valide pas encore le code Metal.

0408 sépare les archives natives `.metal4archive` des `.metalarchive` historiques.
L'ancien préchargement ne peut plus ouvrir puis supprimer une archive native
avec l'API Metal 3. Le writer conserve au maximum huit captures en attente,
sous ses règles existantes d'admission, d'arrêt et d'identité.

**S3 / 0409** active les cibles profondeur/stencil compressibles sur NVN2 hébergé
Apple9. Une lecture stencil compatible extrait seulement ce plan vers une texture
`Stencil8` séparée ; elle n'impose plus la mise à niveau définitive de la profondeur
vers `PixelFormatView`. Le stockage combiné reste l'autorité pour les écritures,
clear et copies : aucune recomposition de profondeur à chaque passe. Cache de
quatre plans, 8 Mio retenus au maximum comptés avec le tampon intermédiaire et
les tailles Metal réelles. Une entrée n'est évincée qu'après sa dernière fence GPU ;
les références au stockage source sont faibles. Alias écrits et changement de
session invalident les vues. Feedback de l'attachement courant, tableaux, MSAA,
mips, textures sparse ou adossées à un heap gardent la voie existante. Ce choix
cible la perte de compression sur lecture stencil ; ce n'est pas une séparation
générale des attachements de rendu. Son intérêt sur Zelda n'est pas mesuré.

Source écrite ; compilation demandée. Replays pixels et mesures iPhone non exécutés.

## État du deuxième lot (0404–0407)

Le mainteneur demande des correctifs effectivement intégrés, pas des fichiers
`env` ni des options dormantes. Les nouveaux chemins ci-dessous sont sélectionnés
automatiquement dans leur périmètre. Aucune manipulation de configuration n'est
requise côté joueur. Ce lot est **écrit, compilation demandée**, pas encore livré
ni observé sur appareil. La [compilation 0400–0403](https://github.com/TarbleFR/RewindBox/actions/runs/45653081904)
a réussi sur macOS 15 et 26 ; elle ne contient pas 0404–0407.

- **S1 / 0404** : soumission NVN2 hébergée transférée à un worker CPU ordonné.
  File de huit paquets, tableaux de handles copiés (256 maximum par paquet),
  blocs de commandes conservés tant qu'une relecture est en cours. Les API
  d'objets joignent le replay sous le verrou d'admission avant mutation ; les
  attentes GPU relâchent l'admission pour laisser passer les producteurs.
  Capture de frames, tableaux hors limite et échec de création gardent la voie
  synchrone. Admission de session transférée au worker, join avant destruction.
- **S4 / 0405** : vraie file Metal 4 de présentation, fence productrice dans
  chaque ticket, texture et résidence conservées jusqu'à fin GPU. La fin des
  tickets devient contiguë : fusionner des images en attente ne libère plus une
  image antérieure encore lue. Le passage en arrière-plan attend aussi les
  encodeurs déjà en cours ; la suppression de frames reste limitée à la file.
  FI utilise la même file de présentation. Aucun gain de recouvrement revendiqué.
- **S2 / 0406** : les fonctions conservent bibliothèque, nom et constantes exactes.
  Descripteurs render/compute portés au compilateur Metal 4 sur NVN2 hébergé ;
  les archives existantes restent réutilisables. Le serializer capture la première
  compilation et le writer existant persiste ces binaires sans seconde compilation.
  Mélanges, vertex descriptor, multisampling, fonctions spécialisées et propriété
  des objets sont conservés ; un descripteur non convertible garde la voie existante.
  L'unification des variantes sur appareil est complétée par 0411 ; la bibliothèque dynamique n'est pas utilisée, pour les raisons précisées plus haut.
- **S5 / 0407** : sommeil sur progression actif pour les polls stables de plus de
  2 ms des threads secondaires de priorité invité >=44, hors propriétaire d'image.
  Maximum demandé 1 ms, réveil anticipé après publication du prédicat hôte, timer
  conservé pour les écritures mémoire sans notification. La soumission asynchrone
  protège toujours le rôle du thread invité d'origine. Les sleeps positifs restent
  inchangés. Latence et énergie sur appareil non mesurées.

Avant 0409, S3 restait à implémenter après analyse des alias profondeur/stencil, des copies et
des invalidations ; aucune séparation coûteuse par copie systématique de chaque
passe n'est présentée comme une optimisation. Les observations 843 ne prouvent
pas que les mises à niveau `X32_Stencil8` sont fréquentes sur Zelda.

## Premier lot écrit (0400–0403, historique)


| Patch | Changement | Repli et limites |
|---|---|---|
| 0400 | Les recettes effectivement liées dans les deux dernières sessions, validées par l'historique existant, sont admises comme travail connu. Les demandes du jeu passent avant elles. Deux voies au maximum à Fair, une à Serious, aucune à Critical, avec les gardes mémoire existantes. Au démarrage, une attente bornée suit les **achèvements**, pas seulement les tâches distribuées. | `S2A_RB_PREPARE_KNOWN=0`. Limite existante de préparation, plafonnée à 30 s, choix de jouer, arrêt et pression conservés. Le bilan distingue réussites, échecs et travail restant ; la libération ne certifie pas que tout le catalogue est prêt. |
| 0401 | Active la réutilisation d'un allocateur dans une même image NVN2 hébergée. Rotation au changement d'image ou lorsque les heaps retenus atteignent 16 Mio. | `S2A_RB_ALLOC_FRAME=0`. Huit places, fence du dernier consommateur et protection de l'encodeur conservées. 16 Mio est un seuil de rotation, pas un plafond de mémoire : un encodage peut le dépasser. Les 9,288 ms/image observées ne sont pas un gain promis. |
| 0402 / S2 | À la compilation de source MSL, retire seulement l'entrée vertex de profondeur non choisie pour cette identité. Préserve l'entrée de capture géométrique. Les bibliothèques déjà compilées restent utilisables. | `S2A_RB_VERTEX_ENTRY=0`. Formes non reconnues, bibliothèques groupées/préfixées et variantes de couche restent intactes. Vérification des fonctions attendues et recompilation du source original si le candidat échoue. Ni changement du traducteur ni purge globale. |
| 0403 / S5 | Candidat de sommeil sur événement de progression hôte, pour une boucle de yield stable d'un thread secondaire de faible priorité. Réveil anticipé sur notification, timer de secours d'au plus 1 ms demandé, arrêt de session et compteurs. | `S2A_RB_YIELD_EVENT=1`, **désactivé par défaut**. Ne change pas les sleeps positifs de l'invité ni ses prédicats de synchronisation. Les écritures mémoire seules n'ont pas de notification : le timer reste obligatoire. Une limite de backoff explicitement personnalisée exclut ce candidat. La latence réellement obtenue dépend de l'ordonnanceur. |

0400 réutilise les identités et caches existants. Une ligne de catalogue personnel
n'est pas, à elle seule, une preuve d'utilisation : la nouvelle marque `known`
reste distincte de l'ancienne marque `recent`, plus large. Une ligne ne peut être
réclamée qu'une fois ; le groupe de préparation attend aussi ses tâches transférées
avant de remplacer son index ou de terminer la session.

La mémoire d'un [MTL4CommandAllocator](https://developer.apple.com/documentation/metal/mtl4commandallocator)
peut servir à plusieurs buffers ; son reset est une opération de réutilisation des
heaps. Le changement 0401 conserve donc la fence GPU, et non un simple numéro
d'image, comme condition de reset.

## Audit initial avant 0404–0407 (historique)

| Chantier | Travail engagé dans ce lot | Reste nécessaire |
|---|---|---|
| S1 — relecture hors du fil du jeu | Audit de `hle_nvn.c: nvnQueueSubmitCommands`, `queue_finish` et `nvn_xqueue.inc`. Contrat de transfert défini ci-dessous. | Implémentation de la propriété des commandes et ressources puis du worker. Aucun replay asynchrone activé ni gain CPU annoncé. |
| S2 — compilation et variantes | 0402 écrit. Référence nxnative vérifiée ; inventaire de la voie Metal 4 déjà présente dans l'autre backend `graphics/metal/gal_core.m`. | Unification base/pulling/shadow et adaptation complète des descripteurs NVN au `MTL4Compiler`. Le serializer n'est pas branché artificiellement sur les appels Metal 3. |
| S3 — profondeur/stencil | Audit du passage de 0399 à une texture avec vue `X32_Stencil8`, des alias et des actions de passe. | Capture `S2A_RB_DS_COMPRESS=1` sur les cibles principales : aucune ligne de ce diagnostic dans le Zelda 843 fourni. Séparer les stockages exige aussi de synchroniser copies, clear, lectures stencil et alias. Non implémenté dans ce lot. |
| S4 — file de présentation | Audit de `present_now`, des trois slots, des tickets et de l'interpolation. Contrat de synchronisation dans les deux sens défini ci-dessous. | Trace A18 Pro et relevé Fire Emblem `cross_thread_wait_ms`. Une file supplémentaire seule ne démontre aucun recouvrement ; le transfert n'est pas activé. |
| S5 — énergie des menus | 0403 écrit comme candidat mesurable. Compteurs de réveils effectifs, timers et durée réellement dormie. | Profil de menus et `S2A_RB_WAKE_LATENCY=1` : baisse de CPU/énergie et absence de régression p99 à démontrer avant activation. |

### S1 : propriété avant retour à l'invité

L'appel de soumission tient `g_sub_mu`, utilise les handles et streams pointés
par l'invité, capture les commandes pour l'enregistreur puis appelle
`nvn_be_submit`. Les continuations de `OP_CALL`/`OP_JUMP`, événements et états
parqués conservent des adresses ; une simple copie du tableau de handles ne
copie pas les streams. `xq_state` retient actuellement les plages de vertex
nécessaires aux continuations, pas toutes les ressources d'une soumission future.

Le premier changement structurel doit fournir un paquet possédant ses streams,
les références de programmes, pools, textures et objets de sync, avec la même
identité de session. La capacité de la file doit exercer une contre-pression.
`QueueFinish`, fences et attente de présentation doivent joindre le numéro de
soumission réellement publié. Les callbacks, compteurs TLS et uploads doivent
appartenir au worker qui les exécute. L'arrêt ferme l'admission, rejoint le worker
puis libère les objets. Sans ces éléments, retourner plus tôt autoriserait le jeu
à modifier ou libérer des données que le host n'a pas encore lues.

### S2 : références et migration

Le commit MIT [nxnative b989137a51](https://github.com/seedds/nxnative/commit/b989137a51d0801e4f1bb6620b400493211f3f28)
unifie base, pulling et shadow dans une compilation puis découpe les bibliothèques.
Son message donne 240,4 → 188,8 s pour BOTW et 466,5 → 363,1 s pour TOTK, sur
M5 Pro. Ce n'est pas le correctif 0402 et ce ne sont pas des résultats iPhone.
Le « −41 % CPU Metal » de l'ancien résumé n'est pas confirmé par ce commit ;
il ne sert pas d'estimation pour ce lot.

Un [MTL4PipelineDataSetSerializer](https://developer.apple.com/documentation/metal/mtl4pipelinedatasetserializer)
capture les pipelines du compilateur auquel il est attaché. La voie NVN actuelle
utilise `MTLRenderPipelineDescriptor`, des `MTLFunction` spécialisées et les
archives existantes. Il faut porter aussi les constantes, formats, mélanges,
vertex pulling, tessellation/mesh et l'identité de cache. Les appels synchrones
de `gal_core.m` signalent en outre un ancien problème Metal avec serializer et
compilation asynchrone. Les bibliothèques dynamiques relèvent d'une autre API ;
la persistance de PSO n'est pas une sérialisation de `MTLLibrary` compilée depuis
MSL. Ces migrations restent distinctes de 0402.

### S4 : deux dépendances GPU

La présentation utilise aujourd'hui `g_q4`, dont l'ordre assure la disponibilité
de la source et l'ordre des usages suivants. Sur une autre file il faut :

1. Capturer la fence du producteur de la source dans le ticket de présentation.
2. Attendre cette fence sur la file de présentation, en conservant textures,
   buffers, allocateurs et residency sets jusqu'à l'achèvement GPU.
3. Empêcher le réemploi/écriture de la source avant la fin de sa lecture par la
   présentation, y compris pour les images fusionnées ou abandonnées, le passage
   en arrière-plan et l'interpolation.
4. Distinguer ticket pris, soumis, achevé GPU et réellement affiché.

Remplacer seulement `g_q4` par une nouvelle queue supprimerait l'ordre implicite
sans ajouter ces garanties. Ce transfert n'est donc pas inclus dans le candidat.

## Vérification et livraison

- **Moteur S2Arm 0001–0417 (413 patchs, source `197dd41ab`)** : compilation iPhoneOS réussie sur `macos-15` et `macos-26` ([run 45672467487](https://github.com/TarbleFR/RewindBox/actions/runs/45672467487), artefact `15052180211`, `25 650 657` octets, SHA-256 `09c6229357309786a54476809165cdaa579de103c64c50158227544cc9e38f80`).
- **Épingle `engine-pin.json` (`d9811f9ba`)** : attestée bit-à-bit en CI ([run 45675386809](https://github.com/TarbleFR/RewindBox/actions/runs/45675386809), SHA-256 `328b9024…8d58b`) ; `S2ArmEngine` `40132146ce8c73d72946045c69cb5e2b82cf827fba8b5409d2491a084ae3e7b1`, `NS2Pro` inchangé (`8a3320df…8654`), `S2ArmShaderXfp.txt = ecd99354f03b846d`, `S2ArmDirectChain.txt = 0be3f28548fd`.
- **Livraison privée IPA 844 (`ed9c3c570`, base vérifiée 843)** : [run 45676121964](https://github.com/TarbleFR/RewindBox/actions/runs/45676121964) tentative 1 (`preflight`, `republish`, `application` verts ; groupes `flutter` et `native` marqués `not-run`). Déchiffrée et vérifiée hors ligne ([reçu](rewind844/delivery.json), [vérification](rewind844/download844-verification.json), [ponts](rewind844/bridge-comparison.json)) : `335 477 432` octets, SHA-256 `0e1c0abbb14e14dec2800348f3537f6525756aec0640646af2038b1a694f45e5`, 11 bundles `0.0.8 (844)`, 98 images natives, 49 empreintes retenues vérifiées, 6/6 validateurs hors ligne à `0`, `S2ArmShaderXfp.txt` / `S2ArmDirectChain.txt` / `fr.lproj/S2ArmHost.strings` vérifiés dans `Payload/NeoStation.app/Frameworks/S2ArmEngine.framework/`. `S2ArmEngine` et `Runner` changés et déclarés ; `dolphin_internal_bridge` (`9d9ef0fe…`) sans changement de source correspond exactement à la variante connue d'éditeur de liens déjà observée dans les IPA 830 et 836, les quatre autres ponts étant identiques octet par octet à la 843.
- **Limites** : aucun nouveau test ni suite approfondie automatique ajouté ; replay pixels, cadence, mémoire, chauffe et comportement visuel sur iPhone A18 Pro **non mesurés**. La maturité pondérée reste **50 / 60 / 65 / 35 / 25**, soit **50 %**.
