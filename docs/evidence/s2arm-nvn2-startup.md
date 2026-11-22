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
