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

## Non traité dans ce lot

- Pauses du ramasse-miettes (une toutes les 1,34 s en jeu dans Hogwarts, 13 d'au moins 300 ms) : la cause principale
  est dans le runtime (un ramassage éphémère attend le fil du ramassage d'arrière-plan). Retirer le maintien actuel
  sans runtime corrigé risque le repli bloquant ; cela ne se valide pas hors appareil.
- Décodage parallèle du cache de shaders, réservation anticipée de l'arène du JIT (1,7 à 1,9 s au premier jeu),
  capacité du journal des variantes (378 états perdus).
