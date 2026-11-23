# MeloNX (RSwitch) après l'IPA 821 : lancement plus court, fil de rendu qui ne compile plus

22 novembre 2026. Journaux privés de l'appareil (IPA 816 à 821, Super Smash Bros. Ultimate et Hogwarts Legacy) : seuls
des comptes et des durées figurent ici. Rien de ce lot n'est mesuré sur iPhone ; aucune IPA ne le contient encore.

## Constats

Lancement (IPA 816 à 820, médiane et étendue) :

- SSBU : 17,9 s jusqu'à la première image [16,2 à 21,6], dont 10,5 s [9,2 à 10,7] dans `LoadShaders` (environ
  12 600 programmes, sur le seul fil GPU) puis 4,8 s [4,2 à 6,2] de démarrage du jeu, l'un après l'autre.
- Hogwarts : 10,5 s [7,4 à 13,0], dont 2,5 s de `LoadShaders`.
- L'invité n'exécute aucune instruction avant la fin du chargement, alors que pendant ses 3 à 5 premières secondes le
  fil GPU n'a rien à faire pour lui.
- Chaque programme chargé est inscrit dans la table de code de l'invité aussitôt compilé, dans l'ordre d'arrivée : la
  table hache et compare à nouveau les préfixes déjà inscrits à chaque taille nouvelle.

Saccades (Hogwarts, IPA 821, 174 s de jeu) :

- Le fil de rendu passe 24 s à obtenir des pipelines pour des dessins et 16 s pour des calculs ; 19 créations par
  minute y durent au moins 50 ms (582 ms en moyenne).
- Côté pilote : 2 647 conversions en bibliothèque Metal à 59 ms en moyenne (3,35 s au pire), 2 759 états Metal à
  17 ms ; 185 pipelines de calcul en 39,1 s. Pour SSBU, une bibliothèque coûte 7 ms.
- Un dessin qui peut être sauté tentait d'abord de créer son pipeline sur le fil de rendu
  (`FAIL_ON_PIPELINE_COMPILE_REQUIRED`) ; dans MoltenVK ce drapeau n'évite que la conversion SPIR-V, pas la
  compilation Metal.
- La relecture des variantes de pipelines connues n'en construit que 2 sur 2 028 : elle attend derrière 2 116
  préparations de programmes du cache sur l'unique worker de basse priorité. 2 027 dessins sont sautés.
- Un calcul attendait son pipeline sans rejoindre la préparation déjà lancée, sauf pendant l'échauffement.

## Correctifs

| Symptôme | Cause | Correctif | Preuve hors appareil |
|---|---|---|---|
| Arrêts du fil de rendu sur un dessin | Création du pipeline tentée sur le fil de rendu avant de sauter le dessin | `adapt_render_thread_compile_relief` : le pipeline est mis en file, le fil de rendu l'attend au plus 4 ms (et au plus un huitième du temps écoulé), puis saute le dessin | Porte `render-thread-compile-relief` : 41 vérifications ; une compilation rapide est obtenue en 1 ms, une lente est laissée après 4 ms et obtenue ensuite, aucune promotion |
| Variantes connues jamais prêtes | Relecture en basse priorité derrière les préparations du cache | Même adaptateur : file intermédiaire, servie après les demandes du jeu et avant les préparations | Même porte : ordre avant « demandé, prioritaires, préparations, relectures », après « demandé, prioritaires, relectures, préparations » |
| Arrêts sur un calcul | Le calcul ne rejoignait pas la préparation en cours | Même adaptateur : il la rejoint à tout moment | Même porte : 1 création au lieu de 2 |
| Lancement : deux attentes à la suite | L'invité attend la fin du chargement des shaders | `adapt_guest_start_during_shader_load` : l'invité démarre dès que le chargeur tient sa copie des mémoires ; ses commandes attendent dans la file GPU ; une attente infinie de barrière émise pendant le chargement dure jusqu'à sa fin | Porte `guest-start-during-shader-load` : 289 vérifications, 200 lancements tirés au sort par variante (arrêt avant, pendant, échec, sortie de l'invité), aucune commande traitée avant la fin du chargement, réveil en moins de 250 ms à l'annulation |
| Lancement : inscription des programmes | Table de code remplie programme par programme | `adapt_shader_code_table_load` : les programmes sont inscrits ensemble à la fin, tailles réservées d'abord, même ordre et mêmes appels | Porte `shader-code-table-load` : 707 vérifications (639 sans cache réel), état des tables identique par réflexion, 389 476 recherches identiques ; cache réel de 1 961 programmes : 523 ms → 61 ms sur l'hôte |

Les trois adaptateurs s'appliquent à tous les titres ; aucun ne lit un identifiant de jeu.

## Suite complète sur la source finale

Les 124 portes du plan ont été exécutées sur la source préparée finale (148 adaptateurs), contre 121 sur la source du
Core précédent :

- 85 passent : les 81 qui passaient avant, les 3 nouvelles et `gc-events` (rouge au passage de référence, sensible à
  la charge de la machine).
- 39 échouent, toutes déjà en échec avant ce lot : attentes écrites à la main sur des adaptateurs plus récents que
  d'autres lots n'ont pas mises à jour. Aucune porte verte n'est devenue rouge.
- `shader-load-binary-release` compile le chargeur de production contre ses propres doubles : ses deux tables doubles
  reçoivent `AddRange` et le journal de lancement un double ; elle repasse (28 vérifications).
- `fragmented-reads` (compilation finale de l'assemblage GPU) lie les quatre fichiers de tables ajoutés.
- Le contrat du Core est recalculé par le code du gel à partir de ces reçus, sans gel complet (39 portes sans reçu
  « passed ») ; son test passe (601 vérifications).
- `test/melonx_adapter_preimages.py` enregistre, pendant la préparation réelle, les fichiers de chaque adaptateur
  avant son application ; `melonx_adapter_control` les restaure pour reconstruire un contrôle, au lieu d'annuler du
  texte que trois adaptateurs ne permettent plus d'annuler.

## Ce que les portes ne montrent pas

- Le temps de lancement et la fluidité sur iPhone. Les gains attendus (jusqu'à 3 à 4 s pour SSBU, environ 2,5 s pour
  Hogwarts au lancement) sont des estimations tirées des journaux, pas des mesures.
- `PipelineBase.CreatePipeline` est lié par son texte et par la compilation de l'assemblage de production, pas exécuté ;
  le chargeur réel (`ParallelDiskCacheLoader`) est remplacé par un double dans la porte du démarrage de l'invité.
- Le jeu de 12 600 programmes de la porte des tables est synthétique : il a la taille d'un cache SSBU, pas sa forme.
- Risques connus : un dessin sauté apparaît une image plus tard ; l'invité avance (son, horloge) derrière l'écran de
  chargement ; les pics de mémoire du démarrage et du chargement s'additionnent ; les attentes à durée finie de
  l'invité échouent encore deux fois avant l'attente forcée.

## À lire dans les journaux de la prochaine IPA

- Ligne des étapes de rendu : `skippable draws that waited briefly N (obtained in time M, T ms)` ; T doit rester de
  l'ordre de quelques millisecondes par image, et les durées « draw prepare » de plusieurs secondes disparaître.
- `pipelineVariants summary` : le nombre de variantes construites par la relecture doit approcher le nombre connu.
- `launch guestStartedDuringShaderLoad` une fois par lancement avec cache ; `launch syncpointWaitHeldForShaderLoad`
  si le jeu a atteint une barrière avant la fin du chargement.
- `shaderCache codeTable` : durée et nombre de programmes inscrits.
- Inchangé attendu : `teardown guestCompilesCancelled`, fermeture en 1 à 2 s, `sessionRetention released`.

## Second lot (23 novembre)

Même base de journaux privés (IPA 816 à 821) ; seuls des comptes et des durées figurent ici. Rien n'est mesuré sur
iPhone.

| Symptôme | Cause | Correctif | Preuve hors appareil |
|---|---|---|---|
| Pauses de 318 à 1 736 ms pour moins de 16 Mio promus (9 sur les 816 à 820, 2 sur la 821) | Un ramassage gen0 ou gen1 attend la fin d'une phase du ramassage d'arrière-plan : son fil ne cède que si `g_fSuspensionPending` est levé, et NativeAOT 10.0.0 ne le lève jamais | `adapt_bgc_suspension_pending` : le `sched_yield` du Core (un fichier C déjà lié) tient ce compteur à 1 tant qu'un ramassage d'arrière-plan tourne ; aucun code du runtime n'est remplacé | Porte `bgc-suspension-pending` (53 vérifications), NativeAOT 10.0.0 linux-x64, charge de 16 s : pauses d'au moins 250 ms promouvant moins de 16 Mio 5 à 9 → 0 ; plus longue pause éphémère 1 383 à 1 626 ms → 35 à 64 ms ; temps à l'arrêt 8,7 à 10,2 s → 2,1 à 2,8 s ; vérification du tas après 24 à 26 ramassages d'avant-plan pendant un ramassage d'arrière-plan |
| Lancement : lecture du cache de shaders | 72 % du chargement est la décompression Brotli du code hôte, en série sur le fil GPU | `adapt_shader_cache_parallel_read` : des fils lisent en avance (cœurs / 2 − 1, de 1 à 3), le fil GPU consomme dans l'ordre ; au plus 8 programmes en attente, aucun de plus de 2 Mio lu en avance | Porte `shader-cache-parallel-read` (5 655 vérifications, 41 scénarios : entrée corrompue ou tronquée, reconstruction, annulation, mémoire) ; cache synthétique de 1 000 programmes : 485 ms → 212 ms avec 2 fils ; cache réel de 1 877 programmes : 1,15 à 1,32 s → 0,52 à 0,63 s |
| 378 états de pipeline évincés du journal des variantes en une session | Plafond de 2 048 états par titre ; la session en demandait 2 426, tous vus dans les 8 dernières sessions | `adapt_variant_journal_capacity` : 4 096 états, fichier borné à 8 Mio, format inchangé | Porte `variant-journal-capacity` (198 vérifications) : 378 évictions avant, 0 après ; journal plein chargé en 19 à 30 ms, 2,5 Mo en mémoire |
| Arène du JIT : 1 409 à 2 437 ms au premier jeu d'un processus (médiane 1 760, 101 préparations de 1 024 Mio) | Une écriture du débogueur par page de 16 Kio (65 536 pour 1 Gio), processus entier à l'arrêt pendant chacune | Aucun changement de comportement. `adapt_jit_arena_usage_journal` journalise le temps de la préparation et l'usage maximal de l'arène par jeu | Porte `jit-arena-usage-journal` (748 vérifications) : taille, appels, refus et quarantaine identiques au contrôle |

Écartés, avec leur raison :

- Préparer l'arène du JIT en parallèle du reste du lancement : sans effet, tous les fils sont arrêtés pendant chaque
  écriture.
- Réserver 512 Mio au lieu de 1 024 au premier lancement : dépend d'un titre précis, et l'usage réel par jeu n'est pas
  mesuré ; les lignes `jitArena used` et `jitArena reached` le mesureront.
- Le maintien périodique du ramassage d'arrière-plan reste en place : 68 demandes dans les journaux, aucun repli
  bloquant.
- La compaction `presentationGap` n'a jamais tourné parce qu'elle est réservée à une marge de 256 Mio ou moins, jamais
  atteinte dans ces journaux ; elle n'est pas cassée.

Limites :

- L'hôte exécute la variante « regions » du ramasse-miettes, l'iPhone la variante « segments » : les ramassages
  d'avant-plan au milieu d'un marquage concurrent s'exécuteront pour la première fois sur l'appareil. Réfuté si des
  pauses de 300 ms ou plus promouvant moins de 16 Mio restent dans les lignes `gcPause`, ou si des sessions se ferment
  seules avec ce Core et pas avec le précédent.
- Le correctif de concurrence de la table du stockage invité (lecture en avance) est présent mais la porte ne détecte
  pas son retrait de façon déterministe (40 répétitions sans échec).
- Non traités : les pauses de vrai travail de promotion (100 à 615 ms pour 50 à 104 Mio promus) et les alertes
  mémoire (tas des gros objets : 453 Mio dont 192 à 207 libres sur la 821).

Lignes à lire : `shaderCache read`, `jitArena timing`, `jitArena used`, `pipelineVariants` (« given up for newer
states 0 »), et dans les `gcPause` existantes l'absence de pause éphémère longue à faible promotion.

## Reste à faire

- Écriture par paire de pages dans l'aide JIT (côté application), à valider sur appareil.
- Sources d'allocation managée en jeu, non attribuées de façon fiable dans ces journaux.
