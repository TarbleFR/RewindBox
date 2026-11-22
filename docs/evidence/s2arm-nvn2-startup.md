# Première utilisation des shaders et pipelines NVN2

Le journal de Mario Kart World attribue 808,8 des 808,9 ms du premier draw à l’attente d’une compilation déjà en file. Le compteur de lookahead totalise 175,3 ms sur 59 scans. Le journal ne donne pas le temps de lookahead individuel de la trame 272. Les 43 compilations MSL sur le thread de soumission de cette fenêtre représentent 6,686 ms. La durée totale de soumission de 355,142 ms comprend d’autres travaux.

| Patch moteur | Chemin modifié | Observation à rechercher sur appareil |
| --- | --- | --- |
| 0283 | Les deux formes de `ProgramSetShaders` capturent les octets nécessaires à la traduction anticipée. Les workers produisent la bibliothèque à partir d’une copie détenue. Le replay vérifie l’identité effective du code mutable. Les entrées MSL effectivement compilées, y compris les variantes, alimentent le générateur AIR macOS. | Bibliothèques prêtes avant le premier bind, chargements binaires et temps MSL de soumission. |
| 0284 | La lecture des catalogues commence avant `nnMain`. La convention de profondeur et le device Metal conditionnent la construction des PSO. Les références, l’historique personnel et les recettes réordonnées passent avant le catalogue externe. Une compilation demandée par un draw peut reprendre une tâche encore en file avec la même clé. | Débuts et fins des phases, temps du premier draw, compilations déjà engagées et attentes résiduelles. |
| 0285 | Le premier scan et son unique reprise partagent le budget de 2 ms de la soumission. Le chemin borné exploite les métadonnées d’attachements déjà connues et mémorise les programmes absents jusqu’à ce que la génération des bibliothèques ou des programmes change. | Compteurs `[rb-look-budget]`, temps maximal par soumission et dépassements observés. |
| 0286 | L’inventaire des archives et la réouverture de 64 clés de démarrage au maximum passent sur une file d’E/S. Le thread de soumission consulte les objets publiés en mémoire. Au premier lancement après mise à jour, les recettes lentes puis les listes de référence et personnelles fournissent les clés à rechercher dans les archives existantes. Le chemin d’écriture tient compte du titre, du build, du GPU et de la chaîne de compilation. Les anciens fichiers restent réutilisables après une vérification stricte par Metal. | `[rb-archive-open]` indique les clés préouvertes, les accès prêts et les ouvertures reportées. La création du PSO Metal est mesurée séparément de la recherche. |
| 0287 | Le profil local conserve l’intervalle demandé pendant 120 présentations de jeu consécutives et les capacités des tables de textures sparse et de lectures bindless. Le titre, le build de l’exécutable et la chaîne de traduction identifient le fichier. Les réservations sont bornées et les choix explicites de présentation restent prioritaires. | `[rb-direct-profile]` signale l’apprentissage, l’écriture et la reprise au lancement suivant. |

Les deux dispositions de cache utilisent le répertoire parent du `pso_user.tsv` effectif. Le générateur `build-utils/s2arm/build_nvn2_shader_pack.py` produit les bibliothèques AIR avec la chaîne de compilation iPhoneOS du Mac. Les archives Metal du téléphone conservent les pipelines pour son GPU. Une source ou une combinaison de pipeline encore inconnue peut entraîner une compilation. Une compilation Metal déjà engagée pour le même PSO reste partagée.

## Configuration de comparaison

```text
S2A_RB_BIND_AHEAD=1
S2A_RB_REGISTER_LIBRARIES=1
S2A_RB_CAPTURE_COMPILED_MSL=1
S2A_RB_PREWARM_TIERS=1
S2A_RB_PSO_LANES=2
S2A_RB_PSO_LIVE_LANE=1
S2A_RB_LOOK_AGAIN=1
S2A_RB_LOOK_BUDGET=1
S2A_RB_ARCHIVE_PREOPEN=1
S2A_RB_ARCHIVE_WRITE_ALWAYS=1
S2A_RB_AUTO_PROFILE=1
```

Aucune nouvelle fenêtre A18 Pro n’est disponible pour cette révision. Les deux points de comparaison à relever sur un parcours identique sont la trame 0 et le chargement de circuit, au premier puis au second lancement.

## Mémoire et température

Le gouverneur compare les octets alloués par Metal au budget recommandé du GPU. Il suit séparément la marge du processus. Sur l’exemple fourni de 5 461 Mio recommandés, le seuil de 85 % vaut environ 4 642 Mio. Le budget de croissance volontaire plafonne à 5 120 Mio. Une allocation indispensable à la validité d’une texture peut dépasser le budget de placement. Le nombre total de tas et la mémoire Metal réellement allouée permettent de repérer ces exceptions.

| Composant moteur | Décision |
|---|---|
| Gouverneur et tuiles sparse | Viser deux ou trois tas de 256 Mio. Conserver une copie valide et attendre la fin du travail GPU avant de rendre une page réutilisable. |
| Staging et lecture anticipée | Réutiliser des tranches partagées après la fin de leur upload. Soumettre hors du thread de rendu des indications de lecture sur les plages physiques mappées. |
| Constantes traduites | Enregistrer la fin exclusive prouvée par binding dans la réflexion du stage. Vérifier le digest du source, la clé du stage et la version du traducteur. Un accès indirect sans borne conserve la taille complète. |
| TBDR | Vérifier le prochain effacement, les lecteurs bindless, les alias et les attentes avant de supprimer un store. Une texture couleur neuve peut se dispenser du remplissage initial si une passe l’efface intégralement. |
| Température | En Fair, admettre un worker de recettes chaudes et suspendre les prédictions. En Serious, suspendre aussi ce worker. Une cadence invitée inférieure peut reprendre après deux fenêtres GPU consécutives en retard. |
| Profil du titre | Enregistrer le pool invité déclaré par le runtime, le GPU, le mode TBDR, la cible des tas et le format des bornes vérifiées. Le budget disponible au nouveau lancement reste prioritaire. |

Les conteneurs AIR construits sur Mac, les archives de pipelines écrites sur l’appareil et les réflexions par stage ont des usages distincts. Une modification de l’ABI du traducteur peut demander une nouvelle traduction. Les comparaisons de cache chaud doivent conserver le même appareil, l’exécutable du jeu et la même chaîne de traduction. Les 175,3 ms du log initial couvrent 59 recherches cumulées. La comparaison par soumission demande la durée d’une seule soumission.

Le [contrôle du moteur 0287](s2arm-fluidity-803/engine287-build.json) conserve les preuves de réouverture des archives en Fair et Serious et les résultats du banc de pixels. Le correctif 0293 transporte l’obligation d’initialiser la texture jusqu’à la création du véritable encodeur sur le worker. Une pression Metal critique ferme aussi l’admission des recettes anticipées lorsque la marge du processus reste élevée.

Le [banc du moteur 0293](s2arm-fluidity-803/engine293-build.json) a rouvert un PSO écrit en Fair et un autre écrit en Serious. Les deux images uploadées restent correctes sur 128 pixels avec le premier lot en vol. Le test d’uniformes mesure 288 octets de c1 initialisés, vérifie le pixel RGBA attendu et maintient 65 536 octets pour un accès opaque. Le backend Mac, les frameworks iOS arm64 et le pont UIKit compilent.

L’[IPA privée 817 vérifiée](rewind817/nvn2-817.json) contient 97 images natives. Trois empreintes diffèrent de la 816. Outre Runner et S2ArmEngine, le pont rpcs3_internal_bridge reprend exactement l’empreinte des builds 811 à 815. Son répertoire source est identique entre les deux révisions de livraison. La cause de la différence de compilation de la 816 reste indéterminée. Les 48 identités imposées par le manifeste concordent.

## Blocage au démarrage de la 817

La trace signalée sur iPhone place le thread invité dans `nvn_be_prog_bound`, en attente du `dispatch_once` de la table des shaders. Sur le worker d’enregistrement qui détient ce jeton, `shmap_load_once` entre dans `warm_start_mode`. Six workers sont garés et le compteur reste à 0 sur 9 502.

| Patch | Changement |
| --- | --- |
| 0294 | Le chargeur termine la table avant de la publier. Son initialisation et l’enregistrement des shaders ne lancent plus le préchauffage. Le premier bind abandonne son anticipation si la carte est froide, si un verrou est occupé ou si la file est pleine. Une file bornée traite les copies des stages. Le replay conserve la résolution à la demande. |
| 0295 | Les deux diagnostics lisent les octets de `MTLDevice.currentAllocatedSize`. Une valeur supérieure à la RAM physique de l’iPhone reste visible dans le journal. Dans ce cas, le gouverneur utilise la marge du processus pour établir le budget. À température nominale et avec plus de 3 000 Mio disponibles, le préchauffage prioritaire dispose d’un worker. |
| 0296 | Le moteur hébergé applique `DM_NVN_TBDR=0` dès la configuration. La première recherche de pipeline déclenche la lecture de l’index. Le thread de soumission peut poursuivre si l’index est froid ou si le verrou est occupé. Le hook de lecture anticipée avant `nnMain` est supprimé. |
| 0297 | Pour une génération graphique déjà publiée, le pont reporte le contrôle d’intégrité des fichiers sur le thread hôte après l’initialisation des services. Une génération endommagée suit le chemin de réparation dans un autre répertoire. |
| 0298 | Avant de créer un buffer d’upload, le moteur reprend une mesure Metal et lui applique la même règle que le gouverneur. La taille du buffer reste limitée par le quota et par la marge disponible. |
| 0299 | Le banc macOS de l’enregistrement garde son verrou pendant deux binds, avec une table froide puis publiée. Après libération, il vérifie que la file traite le même programme. |

Dans la 817, les lignes à 179 et 29 703 Mio lisaient déjà le compteur du même périphérique à deux moments distincts. La trace ne permet pas d’attribuer leur différence à une allocation précise. Le jalon de réservation de la fenêtre d’adresses précède le hook de lecture anticipée de la 817. Le délai de 23 à 80 s inclut aussi le travail de l’application avant la configuration du moteur. La durée du nouveau démarrage et la progression des premières recettes restent à mesurer sur A18 Pro.

Sur le GPU du Mac, le thread de test a conservé le verrou d’enregistrement jusqu’au retour du bind, une fois avec une table froide puis une fois avec une table publiée. Après libération du verrou, le même programme a rejoint la file. Le rejeu a compilé le pipeline demandé pendant la suspension des tâches spéculatives, puis a retrouvé deux pipelines exacts sur disque avec les pixels attendus. Ce scénario active sur le périphérique de test Metal 3 la voie réservée aux programmes enregistrés sur l’hôte NVN2. [Journal du banc GPU](https://github.com/TarbleFR/RewindBox/actions/runs/44980382168/job/137079378851).

Le rejeu des valeurs mémoire, avec 8 192 Mio de RAM et 3 400 Mio de marge simulées, conserve cette marge pour les échantillons à 179 et 29 703 Mio. L’échantillon à 4 650 Mio épuise le budget Metal. Sous suspension spéculative, le premier des six workers obtient la seule place prioritaire à température nominale. Le banc du pont a aussi vérifié l’ouverture d’une génération intacte et la réparation isolée d’un index ou d’une archive endommagés. [Vérification du pont iOS arm64](https://github.com/TarbleFR/RewindBox/actions/runs/44979339911/job/137076183469).

Le moteur issu de `1f66a2d0` compile sur les runners macOS 15 et 26. Le manifeste identifie les 299 patchs par leur SHA-256 dans l’ordre d’application. L’empreinte du framework arm64 est `78b5bd0178bc265255f9ad5ed74db6b81304e33da1467698a8eb1cf8e01e996a`. L’export de la taille de configuration du pont est présent dans ce binaire. [Compilation iOS](https://github.com/TarbleFR/RewindBox/actions/runs/44979639172) · [Manifeste du moteur](../../build-utils/s2arm/engine-pin.json).

## Échec graphics_prepare de la 818

Journal iPhone de la 818, Mario Kart World, cache graphique déjà publié. `S2A_Init` rend la main à +499 ms. La ligne suivante indique `[RB-PSO-WORKERS] thermal=1 startup_limit=0` avec le travail spéculatif retenu par l’état Fair. Les battements restent à l’image 0 pendant toute la session. Les lectures disque, jusqu’à 1 702 Mo sur 10 s pour un seul thread, n’ont lieu que pendant les fenêtres en état thermique 0. La session finit sur `graphics_prepare`.

| Constat | Source |
| --- | --- |
| 0297 lance la vérification et la préparation du cache après `S2A_Init`, sur le thread hôte | patch 0297 (`host_main.c`), pont `postInitGraphics` |
| `rb_ref_checkpoint` attend tant que `rb_spec_may(0)` refuse | `rb_reference.inc` |
| En mode strict, l’état Fair donne `RB_SPEC_HOLD` | `rb_spec_gate.h`, `rb_spec_thermal_tier` |
| Le mode strict exige `S2A_RB_DIRECT_GAME_ID`, posé par `s2a_rb_guest_configure`, et le device Metal | `rb_kart_option`, `nvn_rb_thermal_scope` |
| Avant 0297, la préparation tournait avant la configuration, hors mode strict | pont avant `381b09af` |
| `pendingGPU` faux pour une génération à vérifier : pas de renouvellement JIT après une préparation longue | `S2ArmEngineBridgePlugin.m` de `381b09af` |

Le journal ne distingue pas un abandon du joueur d’une erreur de préparation comme source du code de retour non nul. Le correctif retire 0297 et le report de vérification du pont. La vérification et la préparation reviennent avant la configuration, avec le renouvellement JIT existant. 0296 rétablit l’ouverture de l’index des archives quand le device Metal est prêt. `rb_archive_preopen_start` ne prend plus de verrou depuis 0296.

Pistes examinées et écartées :

- `DM_NVN_TBDR=0`, posé par `s2a_rb_guest_configure`, n’est pas redondant. `rb_legacy_store_override` le lit et choisit le chemin d’effacement legacy quand le drapeau MRT est absent. Il est conservé.
- `safe_tbdr` reste couvert par le banc Mac autonome. Il est conservé.
- `row.UTF8String + 2` est borné par `rb_pso_hot_read`, qui ne garde que des lignes `R\t` de 866 caractères.
- `rb_device_allocated_bytes` enveloppe seulement `currentAllocatedSize`. Les lectures directes n’ont aucun effet sur le comportement.
- La reprise d’une session ne rappelle pas le rappel de 0297.

## Patch 0300 : incohérences de la vague 0270–0299

Six relectures en lecture seule ont couvert les changements hors tests de 0270 à 0299 (`nvn_mtl.m` en trois parties, fichiers inclus, runtime, outils, ABI du pont). Chaque constat retenu a été vérifié dans le code avant correction.

| Problème | Origine | Correction |
| --- | --- | --- |
| La préparation de référence obligatoire n'obtient aucun worker en Fair : la première soumission attend indéfiniment. C'est le motif du blocage 817 (« six workers garés, 0 sur 9 502 »). | 0291, 0295 | Le travail de premier plan prend le worker 0 sous tout plancher de démarrage. La file chaude facultative ne le prend que sous le plancher Fair, jamais sous pression Metal. |
| Après un park/resume, l'index des archives ne se rouvre plus à l'avance. | 0294, 0296 | Ouverture à chaque configuration de profondeur ; le device survit au park. |
| Les ouvertures d'archives ignorent l'arrêt alors que la fermeture les attend (jusqu'à 10 s). | 0286 | Elles s'arrêtent avec la session. |
| La file des pages de textures n'est vidée à l'arrêt que si une indication de plage a été postée. `g_treg` peut être libéré avec un job en vol. | 0289 | La file est toujours vidée. |
| Une plage de vidage hors limites saute aussi la publication des textures. | 0289 | La publication reste inconditionnelle ; seule l'indication de préchargement est bornée. |
| L'anneau d'upload attend le GPU de l'image précédente dès que ses tranches sont occupées, et pas seulement à la limite mémoire. C'est le blocage que 0082 avait retiré. | 0289 | L'attente est réservée au cas où la marge Metal ne permet plus une tranche. |
| En lecture anticipée bornée, les prédictions de rendu et de compute terminées mais non prises ne sont jamais rendues : la lecture anticipée s'éteint au fil de la session. | 0285 | Les emplacements terminés sont réutilisés. L'objet Metal est relâché après le verrou. |
| `DM_NVN_TBDR=0` forcé dans `configure` n'agit que sur le chemin d'effacement legacy quand MRT est coupé, et écrase `env.txt`. | 0296 | Retiré ; le comportement redevient celui de la 817. |

Constats laissés en l'état, sans effet sur le comportement observé ou rares : l'appel par soumission de `rb_guest_heat_monitor` pour un titre non éligible, le verrou d'échantillonnage du mode strict, l'écart entre `present_itv` et `nvn_present_fps` sous maintien thermique, le cache disque des stages pour un titre NVN1 hébergé, l'anneau d'upload éteint par le quota en Fair, la marge Metal inconnue avant le premier échantillon, la taille des tas sparse, le bilan `[rb-look-budget]` et la relance du bind anticipé après un trylock refusé.

## Génération graphique jamais activée depuis la 817

Journal de l'app, Mario Kart World : jusqu'à la 816, les lancements suivants restent en `reused` et `graphics verified`. À partir de la 817, chaque lancement repasse par `graphics copy` puis `graphics pending`. Le moteur refait donc la migration complète à chaque fois : `RewindBox reference: real functions 298/298, source library builds 281, exact PSOs 200/200, strict disk archive 200`, 498 lignes en premier plan, puis le reste en arrière-plan.

Cause. Le patch 0286 active le stockage par jeu et par appareil des archives (`RB_PAR_STORAGE_SCOPE`) pour tout titre NVN2 hébergé. Les archives de pipelines passent de `pipelines/` à `pipelines-v2/<empreinte>/`. Le manifeste `pso_reference.archives.tsv` que le moteur écrit après sa preuve stricte ne liste que des noms de fichiers. Le pont les cherchait toujours sous `pipelines/`, avec `pipelines/identity.json` et `pipelines/batches.tsv`. `activateWithGPU` échouait donc sur « fichiers manquants » et `active.json` n'était jamais écrit.

Correctif.

- Patch moteur 0301 : le manifeste commence par `D\t<dossier>`, le dossier réellement ouvert par la preuve, relatif au cache graphique.
- Pont : `outputsForCount` lit ce dossier (`pipelines` ou `pipelines-v2/<40 hex>`, rien d'autre) pour les archives, `identity.json` et `batches.tsv`. Un manifeste sans cette ligne garde `pipelines`, donc les générations activées avant la 817 restent valides.
- Pont : une génération de remplacement copie aussi `pipelines-v2`, pour ne pas repartir sans archives.
- Le journal `graphics incomplete` indique l'état de la preuve et l'origine du refus.

Limite. Sur l'appareil, les bibliothèques de shaders viennent des sources MSL traduites : `static_air_directory=0`, aucun paquet AIR construit sur Mac. Un lancement vérifié recrée donc ces bibliothèques depuis leur source ; Metal n'expose pas d'export binaire d'une `MTLLibrary`. Ce correctif supprime la migration répétée et ses 281 compilations forcées. `msl_source_count` ne tombe pas à zéro pour autant.

Vérification. La série complète des patchs s'applique et les contrats du pont passent (`test/s2arm_engine_bridge_test.py`). Le pont compile pour iOS arm64 sur le commit `31d09fdd1` (run 45036469087). Le test hôte `test/s2arm_graphics_generation_host.sh` couvre le dossier `pipelines-v2` : refus de `D\t../pipelines`, refus si les fichiers nommés manquent, activation depuis le dossier nommé, invalidation quand une archive de ce dossier change, puis retour à un manifeste sans ligne `D`. La CI ne lance ce test que sur un commit marqué `[s2arm-first-race]` qui touche un chemin surveillé par le workflow du pont ; ni `31d09fdd1` ni `18856f61c` ne remplissaient les deux conditions. Le commit `9fcd1a3cf` ajoute les fichiers du test à ces chemins et l'exécute : vert (run 45036946760). Le moteur compile sur macOS 26 et 15 (run 45036469078) et il est épinglé (artefact 14759968072).

Observation sur iPhone, IPA 820 (sans ce correctif). Mario Kart World atteint la course (image 10804). Le journal du moteur montre la cause décrite ici : archives ouvertes dans `pipelines-v2/ea0c0edcf2611b6451499cb012059c15b4365266` (3348 pipelines, 194 Mo), sous le même dossier de génération que `pso_reference.tsv`, preuve stricte réussie (`strict disk archive 200`, statut 1), puis 498 lignes en premier plan et 9131 en arrière-plan. Pendant ce travail d'arrière-plan, le chargement de la course bloque : 161 soumissions attendent 6,8 s de compilation MSL à l'image 1166 (`submit_msl_blocked_ms=6815.529`). `draws_skipped_pso` reste à 0 sur tout le journal.

Non mesuré. Aucune IPA ne contient encore ce correctif. Le second lancement (génération activée, `graphics verified`) et l'effet sur le blocage de l'image 1166 restent à observer sur iPhone.

## Pipelines connus construits au dessin sous chauffe

Journal iPhone d'une session Mario Kart World reçue après la livraison 821 (9 431 images, numéro de build absent du journal moteur). La ligne `RewindBox reference: real functions …` des lancements 817 à 820 n'y figure plus : la migration n'est pas refaite.

Mesures de cette session.

| Mesure | Valeur |
|---|---|
| Pipelines servis par l'archive | 2 037 sur 2 048 constructions |
| Premiers dessins de pipelines | 1 170, dont 258 prêts d'avance et 912 construits au dessin |
| Attente de ces 912 constructions | 2,8 s |
| Compilations MSL sur le thread de soumission | 573, 8,7 s |
| État thermique | Fair dès la première image, Serious à partir de l'image 3 300 environ |
| Travail spéculatif suspendu | 3 695 mises en attente, 1 076 s cumulées |
| Lignes avancées à l'enregistrement d'un programme | 2 275, dont 1 417 construites depuis la tête de file |

Cause. La politique stricte suspend tout le préchauffage dès Fair (`rb_spec_thermal_tier`). Les lignes que le jeu vient d'enregistrer et qu'il a déjà dessinées lors d'une session précédente passaient par une seule voie jusqu'à Fair, et par aucune à Serious (`warm_pick_row`). Leur construction n'était donc pas évitée : elle était reportée au premier dessin, sur le thread de soumission. L'archive répond déjà presque toujours ; ce qui manquait est le moment de la construction.

Patch 0302.

- `rb_spec_gate.h` : `rb_spec_registered_lanes` donne les voies ouvertes à ces lignes, deux jusqu'à Fair, une à Serious, aucune à Critical. Les lignes facultatives gardent leur admission et les contrôles de mémoire Metal de l'appelant restent en place.
- `warm_pick_row` applique cette règle à la place de « voie zéro, jusqu'à Fair ». Les lignes prises ainsi s'exécutent toujours dans le groupe à deux compilateurs.
- `[rb-pso-ready]`, toutes les 300 images et pour tout titre NVN2 hébergé : `prepared`, `demand`, `demand_ms`, `front_moved`, `front_taken` depuis le début de la session.

Aucune règle par titre. La clé de pipeline n'est pas modifiée : `pso_norm_masks` retire déjà du `pso_key` les attributs de sommet non lus, les flux inutilisés et l'état de fusion des cibles non écrites.

Vérification. `t_rb_spec_gate.c` couvre la règle (deux voies jusqu'à Fair, une à Serious, aucune à Critical, aucune voie au-delà de la deuxième) et passe sur l'hôte. `t_nvn_warmbump.m` vérifie sur le GPU du Mac de CI que la deuxième voie sert une ligne enregistrée à Fair, que la voie zéro continue à Serious et qu'un worker ordinaire reste suspendu. Rien n'est mesuré sur iPhone avec ce patch : le rapport `prepared` / `demand` et la chauffe à Serious restent à observer.

## Gouverneur mémoire : fausse saturation du budget Metal

Deux journaux iPhone 16 Pro Max de Mario Kart World.

| Journal | Ligne `[RB-MEM-GOV]` | Marge réelle au même instant |
|---|---|---|
| IPA 820 | `tier=2 metal_MiB=6265 target_MiB=4642 remaining_MiB=0 budget_source=metal+process` | `headroom_MiB=5757` ; empreinte du processus 917 Mo à l'image 250 |
| Session après la 821 | `metal_MiB` : 238, puis 22343 (`process`), 6121 (`tier=2`), 7621 (`process`), 7616 (`tier=2`), 7639 (`process`) | `headroom_MiB=5813` ; « resident 892 MB, GPU allocated 6280 MB » à l'image 300 |

Effets relevés à `tier=2` : `prefetch=0`, `upload=4194304`, `texture=4194304`, puis « speculative shader work held: little memory left before the process limit (… 5726 MB left …) ». Le même palier ferme aussi l'admission des lignes enregistrées (`rb_gov_admit_registered`).

Cause. `rb_gov_sample` compare `MTLDevice.currentAllocatedSize` à la cible du jeu de travail (85 % de `recommendedMaxWorkingSetSize`). Ce total compte de l'espace d'adressage : tampons qui enveloppent la mémoire invitée, tas de placement, stockage purgeable. Le patch 0295 écartait déjà l'échantillon quand il dépasse la mémoire installée (7619 Mio) ; en dessous, la même valeur gonflée était prise pour des octets résidents. Le palier basculait donc selon que le total passait au-dessus ou au-dessous de 7619 Mio.

Patch 0303.

- `rb_ws_resident` : Metal ne peut pas détenir plus d'octets résidents que le processus n'en est facturé. L'échantillon utilisé est le plus petit du total Metal et de l'empreinte du processus (`phys_footprint`, lue par la sonde existante, une fois par seconde, hors du thread de soumission). Empreinte inconnue : le total Metal reste tel quel. Les trois lecteurs passent par cette valeur : gouverneur, anneau de transit des envois, tas de placement.
- `rb_gov_stressed` ne lit plus l'état thermique. La chaleur est l'entrée du régulateur spéculatif (`rb_spec_gate.h`) ; des caches plus petits ajoutent des reconstructions à un appareil chaud. La compression du processus (plus de 512 Mio) garde le plafond de 96 Mio du patch 0246.
- Le premier échantillon publie le palier mesuré. Le plan initial (128 Mio, `tier=1`) n'est qu'une valeur d'attente : il imposait dix secondes de `tier=1` à chaque premier lancement.
- La ligne `[RB-MEM-GOV] tier=` porte `resident_MiB` à côté de `metal_MiB`.

Ce qui ne change pas : le palier critique à 768 Mio de marge ou moins, l'avertissement à 2048 Mio ou moins, les événements de pression mémoire du système, le plafond sous compression, et le palier critique quand l'empreinte elle-même atteint la cible.

Vérification. `t_rb_working_set.c` rejoue les valeurs des deux journaux (6265 Mio alloués, empreinte de 900 Mio : il reste la cible moins 900 Mio) et garde le cas saturé (empreinte au-dessus de la cible : aucune marge). `t_rb_gov_stress.c` vérifie que seule la compression active le plafond. Les deux passent sur l'hôte. Rien n'est mesuré sur iPhone : à observer, `tier=0` avec `prefetch=134217728 upload=134217728 texture=234881024` tant que la marge dépasse 2 Go et que la compression reste sous 512 Mio, et l'évolution de l'empreinte réelle.

