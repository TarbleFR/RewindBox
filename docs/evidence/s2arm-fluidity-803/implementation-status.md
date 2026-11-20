# Lot 0171 — état et limites de validation

## Périmètre

- 0170 : correction de la provenance du mode de présentation générique, avec retour explicite `S2A_RB_NATIVE_CADENCE=0` ajouté par 0171.
- 0171 : protocole de 180 s, menu générique, compteurs bornés, audio/GC, ledgers et parcours mémoire complet après le score.
- Nextendo : Core déjà compilé et authentifié du run 44753917742, source `8988ced5014dd23caae2eefac70b3d37f5a5b7f0`, à intégrer dans la même IPA.
- Aucun budget de textures/prélecture, ordonnanceur audio, pas de simulation ou traducteur de shaders modifié par 0171.

## Vérifications source

Le contrôle existant `tools/weak_link_decl.py check` a d’abord signalé trois déclarations faibles non enregistrées, déjà présentes à 0170. Leurs consommateurs ont un repli explicite ; les annotations manquantes sont ajoutées auprès des déclarations (`nvn_rb_route_read`, `s2a_rb_guest_input_release`, `s2a_rb_mkw_measure`). Le même contrôle passe ensuite : 31 symboles host enregistrés, aucun flag de liaison manuscrit. Le contrôle n’est ni modifié ni désactivé.

Les revues indépendantes couvrent les familles, les crochets de présentation, les métadonnées host, la mémoire et la concurrence du collecteur. Elles ont notamment corrigé l’identité amont confondue avec le moteur patché, les préférences confondues avec les réglages actifs, les rappels de minuterie périmés et l’arrêt pendant l’initialisation du banc. La lecture VM utilise l’API iOS déjà employée par le moteur, avec des adresses de 64 bits.

Le premier run 0171 (44771503834) a refusé l’interface avant compilation : le nouvel appel du banc n’était pas déclaré dans `S2ArmGuestABI.h`. La déclaration partagée est ajoutée et employée par le menu et le pont. Les deux fournisseurs NativeAOT restent des symboles internes recherchés par le collecteur ; leur conservation est exigée et la CI vérifie leur présence dans le framework final. Le contrôle d’exports existant n’est pas modifié ni contourné.

L’analyseur de comparaison a été appliqué à deux exports privés existants : [comparaison refusée](legacy-comparison-refused.json), car aucun ne porte les marqueurs du protocole. Aucune différence de performance n’est produite. Il ne s’agit ni d’un banc synthétique ni d’un test d’exécution du moteur.

## Statut du moteur compilé

| Étape | État |
| --- | --- |
| Correctifs et instrumentation dans les sources | Intégrés et relus ; application de 0171 sur 0170 et contrôle des déclarations faibles réussis |
| Compilation du moteur 0170 | Réussie sur macOS 15 et 26, run 44759330364 ; zéro avertissement sur ses lignes ajoutées |
| Compilation du lot 0171 | Réussie sur macOS 15 et 26, run 44772035018, source `342f534efc856eedeba9b085df291757bc942d41` ; zéro avertissement sur les lignes ajoutées |
| Pin et IPA privée 803 | Pin contrôlé par le run 44774890033 ; IPA 803 livrée en privé et vérifiée, run 44775472323 |
| Gain de fluidité, chaleur, son, attribution mémoire sur iPhone | Non observé ; il manque les nouvelles mesures appareil |
| Régression des deux autres jeux Switch 2 | Non vérifiée sur appareil avec 803 ; état satisfaisant rapporté sur les versions précédentes |

Les suites Flutter/natives approfondies ne sont pas exécutées, conformément à AGENTS.md. Les contrôles obligatoires de configuration, ABI, signatures, identité et livraison restent actifs. Aucun avertissement nouveau sur les lignes ajoutées n’est accepté lors de la revue des journaux CI.

## Décisions qui attendent les données

Le poste compressé dominant, le taux d’usage de la prélecture et les trous audio réellement entendus ne sont pas encore attribués. Il n’est pas justifié de réduire arbitrairement un cache ou de changer une échéance audio avant ces relevés. Le mode endurance et les retraits/désactivations de familles sont des propositions classées dans [l’audit](audit-803.md). La première IPA instrumentée est une référence ; elle ne transforme pas les anciens essais non appariés en un avant/après.

## Preuve de compilation

[Identité moteur et artefact](engine171-build.json) : 171 patchs correspondent exactement au dépôt. La chaîne shaders `0be3f28548fd` et la charge NS2Pro sont identiques à la base 802. Les trois nouveaux exports sont présents dans le framework final. Les 12 avertissements par plateforme existaient dans 0170, sur des lignes inchangées ; aucun sur les ajouts 0170/0171. L’annotation Actions relative à Node.js existait également avant ce lot.

## Livraison privée 803

La [livraison](../rewind803/delivery.json) provient de `c5422386b72ec4ea88b010dab3826075ee7e79f8`, run 44775472323, tentative 1. Les quatre pièces chiffrées, les reçus, les 97 images natives et les 10 identifiants de bundles concordent. [Identités exactes de S2Arm et Nextendo](../rewind803/s2arm-identity803.json). IPA : 333553734 octets, SHA-256 `d7d2cb41d3683bc20d804adfdf346aa3d12cf34abe3b55b83f5e669c9f90510b`.

La [revue de compilation application](../rewind803/application803-warnings.json) ne trouve aucun avertissement dans les cinq fichiers modifiés, soit 249 lignes ajoutées. Les sources des avertissements S2Arm ailleurs sont inchangées depuis 802 ; leur émission dans 802 n’a pas été vérifiée, son journal étant indisponible. Les diagnostics du moteur sont documentés [séparément](../rewind803/engine171-warnings.json). Le framework libretro recompilé a des relais générés par le linker différents mais équivalents : code principal et données identiques, mêmes destinations `_objc_msgSend`, avec UUID et signature différents. Le [classement binaire](../rewind803/libretro-image-difference.json) conserve les détails.

L’IPA a été remise en privé après vérification ; la clé privée de transport a été supprimée après conservation des reçus. Aucun essai physique iPhone, aucune validation de partie, aucun gain de FPS ou de chaleur n’est déclaré. La comparaison 803/802 selon le protocole reste indisponible : 802 n’avait pas ce protocole. 803 constitue la première référence instrumentée.

## Tas hôte iOS — lots 0172 à 0176

Référence fournie par le mainteneur pour Mario Kart World (`0400C3F00006E000`) sur iPhone17,2, 8 Go, iOS 27, IPA 803. Footprint 4 346 Mo, compressed logique 1 205 Mo, graphics compressed 212 Mo. Tranches communiquées en Mio par tag : 2 = 755, 0 = 243, 100 = 163, 88 = 64. Environ 22 500 page-ins / 10 s et 31 % de CPU système. En session longue sur 802, jusqu’à 85 000 page-ins, 312 000 compressions / 10 s et 63 % de CPU système. Ces relevés motivent le choix du tas. Ils ne déterminent ni un propriétaire ni un résultat apparié.

| Propriétaire suivi | Octets comptabilisés en mémoire au moment du relevé |
| --- | --- |
| Traduction | Allocations des descripteurs de modules, tables de symboles, traps et sauts lointains. Code exécutable mappé exclu. |
| Pages et fenêtres | Plages de suivi des écritures, tableaux courants et retirés, index de plages et répertoire de la fenêtre lointaine. Réservation virtuelle du jeu exclue. |
| Vues de textures | Capacité allouée du registre de textures et des deux index, plus la taille structurelle des jeux de vues vivants. Une acquisition du verrou impossible donne une valeur indisponible. |
| Pipelines | Capacité malloc des clés et pointeurs de la table de rendu. Taille superficielle des objets retenus publiée séparément par référence. Plusieurs références peuvent désigner le même objet. Les allocations privées de Metal sont inconnues. |
| Commandes | Enregistrements NVN, nœuds de l’index de pages, intervalles alloués et table d’internement. Les blocs de commandes mmap relèvent d’une autre comptabilité. |
| Son | Capacité demandée des buffers AudioQueue effectivement alloués et encore détenus, toutes sorties confondues, sans travail ajouté au callback audio. Le tas managé et les allocations privées de Core Audio sont hors couverture. |

`[RB-VM-HEAP]` associe les lignes de zone et la synthèse par horodatage monotone et génération. Les valeurs de zone et les compteurs internes se recouvrent. `over_threshold` utilise le seuil strict de 100 Mo décimaux sur les sites suivis. Les références superficielles PSO ont leur propre indicateur. Aucun propriétaire dépassant réellement ce seuil sur la 803 n’est établi par les données disponibles. Les octets rendus par `malloc_zone_pressure_relief` ont leur propre ligne `[RB-HEAP-RELIEF]`.

Le cache des archives ouvertes gardait les objets et des alias de lot jusqu’à la fin du processus. Son plafond candidat est de 128 fichiers distincts, avec les huit plus récents conservés sur une alerte système. Ces deux plafonds d’essai devront être confrontés aux temps d’image. Les descripteurs Metal en cours conservent leurs archives. Les entrées de traduction utilisées par le traitement de fautes restent actives jusqu’au retrait des lecteurs. Aucun changement de format de fichier, de sauvegarde ou d’identité shader.

Revue avant livraison : les victimes de la LRU restent retenues dans une collection possédée jusqu’après la libération du verrou des archives. Leur destruction ne se produit donc plus sous ce verrou. Une archive dont l’ouverture échoue est retirée de l’index de présence pour autoriser sa reconstruction ; le mode actif conserve le fichier jusqu’au remplacement réussi. Le fournisseur audio protège également sa nouvelle branche contre les exceptions à la frontière native, avec un retour indisponible. Les lignes malloc distinguent le heartbeat d’origine, l’intervalle réel de collecte et le retard de la file. Le comportement 803 reste derrière `S2A_RB_HEAP_TRIM=0`.

| Étape | État du lot |
| --- | --- |
| Corrigé dans les sources | Relevé malloc par minute, propriétaires, plafond LRU, libération des tables du chargeur au retrait et restitution à malloc sur alerte. Repli global au lancement avec `S2A_RB_HEAP_TRIM=0`. |
| Compilé pour iOS | Premier moteur `6bdf6fec` conservé dans la [preuve initiale](engine176-build.json), avec son contrôle du pin. Révision `f956b7d8` réussie sur macOS 15 et 26 : [run 44790771355](https://github.com/TarbleFR/RewindBox/actions/runs/44790771355), [empreintes et vérifications](engine176-review-build.json). Les 176 patchs correspondent au dépôt ; les 171 premiers, les exports, la charge NS2Pro, la préparation, les données système et la chaîne shaders restent identiques à 803. [Revue des avertissements](engine176-review-warnings.json) : mêmes 12 diagnostics par plateforme que 803, zéro sur les 374 lignes nouvelles. [Contrôle CI du pin](https://github.com/TarbleFR/RewindBox/actions/runs/44793831852) réussi sur les trois archives ; fichier régénéré strictement identique au pin intégré dans `b47339a9`. |
| IPA privée livrée | [804 livrée et vérifiée](../rewind804/delivery.json), source `5f8fc02a`, [run 44803751366](https://github.com/TarbleFR/RewindBox/actions/runs/44803751366), tentative 1 réussie. Contrat frais, gel et compilation application réussis ; quatre pièces chiffrées authentifiées, puis six validateurs hors ligne réussis. 97 images natives et 10 identifiants de bundles contrôlés. La clé privée existante correspondant au destinataire déjà versionné `delivery-798-nextendo-recipient.pem` est réutilisée à la demande du mainteneur ; aucune nouvelle clé ajoutée à GitHub. |
| Observé sur appareil | Aucune fenêtre candidate disponible. Objectif non validé. |

### Livraison privée 804

L’IPA remise dans la conversation privée contient 333 563 097 octets, SHA-256 `eedf87f8fb75698cad30e405a9d7318861fc77202157a71f085943f2d4690763`. L’[identité du moteur signé](../rewind804/s2arm-identity804.json) correspond à la révision revue `f956b7d8`, avec 176 patchs et les 171 premiers identiques à 803. Le Core Nextendo `8988ced5`, les autres moteurs, la préparation et la chaîne shaders `0be3f28548fd` sont conservés. Les identifiants des dix bundles restent ceux de 803. Le fichier privé de transport original est conservé hors dépôt ; seule sa copie de travail temporaire a été supprimée. Le reçu indique donc explicitement que la clé originale n’a pas été supprimée.

La [revue Xcode](../rewind804/application804-warnings.json) compare les deux journaux de compilation complets : 457 lignes contenant `warning:` dans chaque version, 307 textes normalisés distincts, aucun texte nouveau ni changement d’occurrences, aucune erreur compilateur réelle. Les avertissements existants restent présents. Les 1 894 entrées effectives de l’hôte examinées sont identiques. Le journal global du job n’a pas été obtenu par l’API ; cette conclusion couvre Xcode seulement. Aucun journal brut n’est versionné.

Les deux [écarts binaires des ponts ARMSX2 et RPCS3](../rewind804/bridge-image-difference804.json) sont entièrement expliqués avant enregistrement : code principal et données identiques, destinations `_objc_msgSend` équivalentes démontrées pour chaque relais modifié, UUID et signatures différents. Aucun octet inexpliqué ne subsiste. Cette analyse statique et les contrôles de livraison ne prouvent ni une installation Apple ni l’exécution du jeu sur iPhone. Les groupes Flutter et natifs restent `not-run`, conformément à la recette ; le contrat de livraison et les validateurs indispensables ont été conservés. Aucun gain du tas ni baisse des page-ins n’est déclaré.

Pour statuer, conserver trois fenêtres valides de 180 s **par version**. Utiliser le même circuit nommé, le même appareil et le même état de cache chaud, avec refroidissement et ordre alterné, selon le [protocole](../../s2arm-benchmark-protocol.md). Pour chaque fenêtre, associer le parcours VM post-score complet à son identifiant et convertir les pages comprimées du tag 2 avec la taille de page déclarée. Comparer les médianes des relevés par version et les médianes des débits de page-ins du processus ramenés à 10 s. Publier aussi les valeurs individuelles, le p95 affiché et les images affichées >100 ms/min. Acceptation : baisse du tag 2 d’au moins 250 000 000 octets, baisse de la médiane des page-ins, sans hausse des deux métriques de temps d’image. Un tag manquant, une couverture manquante ou une fenêtre invalide laisse le résultat en attente.

### Comparaison des six fenêtres

L’outil hors moteur [compare_heap_windows.py](compare_heap_windows.py) réutilise les validations de `compare_benchmarks.py` pour les quinze paires possibles. Il exige trois UUID distincts par version, la référence 803, des identités homogènes et les mêmes conditions. Chaque parcours VM doit être complet et suivre le score du même UUID ; ses catégories doivent totaliser les compteurs publiés. Le tag 2 absent reste indisponible, jamais zéro.

Compatibilité de lecture 803 : seuls `end.complete` et `mapping_tag.external_pager_or_shadow`, construits par des expressions C de type `int` dans `rb_vm_audit.m`, acceptent aussi les entiers JSON exacts `0` et `1`. Le rapport conserve les valeurs sources correspondantes. Les autres booléens restent stricts ; chaînes, nombres flottants, compteurs booléens et autres valeurs sont refusés. Le producteur 803 et les validations du comparateur existant restent inchangés.

Pour les page-ins, l’outil prend la médiane des dix-huit débits réels par fenêtre, ramenés à dix secondes, puis celle des trois fenêtres. Pour le tag 2, le p95 affiché et les images >100 ms/min, il prend la médiane des trois valeurs de fenêtre. Les valeurs individuelles et leur dispersion restent dans le JSON ; aucun quantile fusionné n’est inventé. Résultats distincts : comparaison refusée, objectif non atteint, objectif atteint sur ce scénario. Ce dernier résultat exige les quatre critères, sans extrapolation aux FPS, à la chauffe ni aux autres circuits.

Usage : répéter `--baseline JOURNAL UUID` trois fois et `--candidate JOURNAL UUID` trois fois, puis donner `--output RAPPORT.json`. Les journaux restent privés. Vérification syntaxique réussie et refus confirmé sur un export historique sans protocole ; aucune fenêtre appareil valide fournie, aucun résultat positif fabriqué. Aucune nouvelle suite de tests n’est ajoutée.

## Pipelines Metal vivants

Le relevé fourni pour Mario Kart World compte environ 5 500 pipelines sur 803 et 2 900 sur 779. La préparation 803 annonce zéro ligne transférée en arrière-plan. Le mainteneur indique n’avoir observé aucune compilation en course. Ces chiffres décrivent la référence et motivent la mesure de rétention.

| Étape | État |
| --- | --- |
| Corrigé dans les sources | 0177 compte les objets de pipeline du jeu et leurs octets malloc superficiels jusqu’à leur destruction. 0178 sélectionne le préchauffage par utilisation récente ou contexte. 0179 retire les entrées froides reconstructibles et chronomètre chaque reconstruction. 0180 agrège les images longues du banc. |
| Compilé pour iOS | Première révision `80f4c5d6` compilée sur macOS 15 et 26 dans le [run 44812716345](https://github.com/TarbleFR/RewindBox/actions/runs/44812716345). Douze diagnostics compilateur ou linker sur chaque plateforme, mêmes textes que la 804. La révision retenue `5bc7fa90` a compilé sur les deux plateformes dans le [run 44814628866](https://github.com/TarbleFR/RewindBox/actions/runs/44814628866), avec les mêmes douze diagnostics par plateforme. Les [empreintes vérifiées](engine180-build.json) couvrent les 180 patchs, les trois archives productrices, les exports, NS2Pro, la chaîne shaders et la notice livrée. Le [contrôle CI du pin](https://github.com/TarbleFR/RewindBox/actions/runs/44816718062) a régénéré la même empreinte SHA-256. |
| IPA privée livrée | [805 déchiffrée et vérifiée](../rewind805/delivery.json), issue du [run 44825625217](https://github.com/TarbleFR/RewindBox/actions/runs/44825625217) au commit `3f2bffa8`. Le destinataire permanent du mainteneur a permis de déchiffrer les quatre pièces authentifiées. L’empreinte de l’IPA correspond au reçu de signature. Le contrôle hors ligne a vérifié 97 images natives et 10 bundles. Le [premier transport](../rewind805/transport.json) conserve son propre reçu. |
| Observé sur appareil | Aucune fenêtre candidate. Nombre d’objets, footprint et durée cumulée en attente. |

Dans les ponts ARMSX2 et RPCS3 recompilés, la comparaison aux empreintes des sections de la 804 confirme le même agencement et les mêmes octets de `__TEXT,__text`. Parmi les 32 sections de chaque pont, seules `__TEXT,__stubs` et `__TEXT,__objc_stubs` diffèrent.

Les compteurs `guest_pipelines` couvrent les constructeurs du jeu passant par les archives de rendu/calcul, les objets admis dans la table de rendu et les constructeurs mesh. Les objets fixes du présentateur et les pipelines internes du pilote sont hors périmètre. Les octets malloc superficiels, le footprint du processus et les octets Metal mesurent trois grandeurs différentes. Relever aussi les entrées de la table de rendu dans le compteur de ressources commun à 803 et à la candidate.

Le délai candidat est de cinq minutes depuis le dernier bind ou la création. Seuls les hits vérifiés par Metal avec `MTLPipelineOptionFailOnBinaryArchiveMiss` sont éligibles. La libération attend la soumission GPU. Les objets sans archive éprouvée, dont les pipelines mesh, restent détenus. La nouvelle liste d’indices conserve au plus 8 192 identités par session à côté du manifeste du joueur. Les recettes de rendu fusionné sans clé d’archive conservent leur identité dans cet historique dès leur bind. Les deux sessions précédentes, les indices de scène courante et les dépendances obligatoires de migration alimentent le préchauffage. La première exécution peut reprendre les traces de rendu déjà disponibles sur 803. Chaque ligne privée `[RB-PSO-RECREATE]` donne le temps de construction, l’identité d’archive et l’issue. Une attente sur le thread de rendu a sa propre mesure.

### Décision sur appareil

Suivre le [protocole du banc](../../s2arm-benchmark-protocol.md) avec trois fenêtres valides de 180 secondes par version sur le même circuit nommé, sur iPhone17,2 avec iOS 27. Garder la même résolution, le même état thermique et les mêmes caches chauds, puis alterner les versions. Amener les deux sessions au même point après au moins cinq minutes de jeu. Relever par fenêtre la médiane des footprints, le compteur de ressources commun aux deux versions, le p95 affiché et les images de plus de 100 ms. La référence 803 ne fournit pas le compteur distinct `guest_pipelines`. Comparer directement les entrées des mêmes tables pour mesurer la rétention du cache. Pour conclure sur le nombre exact d’objets Metal vivants, joindre aussi un recensement de même périmètre sur les deux IPA. Une entrée de table peut partager son objet avec une autre référence.

Le champ `pipeline_display.overlapping_long_display_ns` additionne chaque intervalle affiché supérieur à 100 ms qui recouvre une attente instrumentée (rendu, calcul, mesh). La simultanéité seule ne démontre pas la cause, et une file GPU peut décaler l’affichage. `all_causes_upper_bound_ns` ajoute aux images longues complètes les portions de fenêtre aux deux bords, quelle qu’en soit la cause. S’il est strictement inférieur à 1 000 000 000 ns sur chacune des trois fenêtres candidates valides, le budget PSO est respecté. Sinon, il faut attribuer les images restantes à partir d’une trace synchronisée avant de conclure. Une couverture absente ou un débordement ne vaut jamais zéro. La baisse des compteurs comparables et du footprint reste à vérifier face à 803. La candidate hérite du lot tas de 804. Pour isoler l’effet PSO, consigner un passage supplémentaire avec `S2A_RB_HEAP_TRIM=0`. Le repli global `S2A_RB_PSO_CAP=0` s’applique dès le lancement.

## Textures Metal

La 779 contient 87 patchs, la 802 en contient 169 et la 803 en contient 171. Les plafonds, compteurs de réutilisation et allocations dédupliquées répondent à des questions différentes. Les chiffres transmis pour 802/803 sont de 1,64 à 1,9 Go de textures, 664 à 884 Mo de tampons de pool, 1 Go de tas Metal et 3,58 à 3,93 Go de résidence. Ils ne constituent pas six fenêtres de comparaison. [779](../rewind779/delivery.json) · [802](../rewind802/delivery.json) · [803](../rewind803/delivery.json)

| Variation historique | Effet à isoler sur le même circuit |
| --- | --- |
| 0088, antérieur à la plage 0090–0171 | La politique 779 de 48 Mio/120 images devient 192 Mio/900 images dès 0088. Le plafond augmente de 144 Mio. Les observations consignées dans 0088 rapportent davantage de relectures et moins de reprises dans le petit cache. Comparer la 803 par défaut à la 803 avec `S2A_RB_TXR_SMALL=1`. La candidate conserve ce cache aux réglages 803. |
| 0103, 0107 | Comparer séparément `S2A_RB_TEX_FIT_FAST=0` puis `S2A_RB_FB_DIRECT_SNAPSHOT=0`. Vérifier la distinction entre références de vues, textures physiques dédupliquées et instantanés réutilisés. |
| 0132 | Le chemin GPU avance les envois de textures de 256 Kio au plus, avec 32 Mio de plages sources par session. Les octets sources ne donnent pas la taille de leur allocation Metal. Comparer sur la candidate avec `S2A_RB_TEX_UPLOAD_AHEAD=0`. |
| 0149, 0160 | Prélecture des pages hôtes sur des indications de liaison. Comparer séparément avec `S2A_RB_TEX_PAGE_HINTS=0` sur la candidate. Relever les page-ins et les textures séparément. |
| 0151, 0163, 0166/0169 | 0151 retire les vues lors du retrait de leur texture. Les mécanismes de conservation et de réutilisation de vues se comparent avec `S2A_RB_VIEW_KEEP=0` puis `S2A_RB_VIEW_RID_REUSE=0`. Une vue peut prolonger la vie du parent. |

**Corrigé dans les sources.** 0181–0185 adaptent le budget des instantanés GPU et des destinations secondaires et suivent les copies préparées avant la première demande. Age et budget s’appliquent aux textures facultatives. Un instantané peut être recopié depuis un attachement GPU et une destination secondaire est réécrite lors d’un envoi déjà requis. Seules des copies anticipées privées, encore sans liaison, peuvent devenir volatiles. Leur prochain usage contrôle le résultat de Metal avant de les soumettre. Le plafond dynamique s’applique à ces caches et les textures actives peuvent porter le total au-delà de 1,45 Go. `S2A_RB_TEX_BUDGET=0` rétablit les chemins 803 au lancement.

**Compilé / livré / observé sur appareil.** Moteur iOS compilé et contrôlé sur macOS 15 et 26. Livraison privée en attente. Aucune fenêtre de la candidate sur iPhone. Aucun responsable de la hausse dans 0090–0171 n’est établi.

**Critères de comparaison.** Appliquer le [protocole du Banc d’essai](../../s2arm-benchmark-protocol.md) avec Mario Kart World `0400C3F00006E000`, le même circuit, la même séquence, les mêmes caches joueur et le même iPhone17,2 sous iOS 27. Comparer trois fenêtres valides de 803 à trois de la candidate. Pour l’attribution, répéter trois fenêtres par configuration en ne changeant qu’un interrupteur au redémarrage. Geler les réglages de chauffe et de résolution. Pour isoler les textures des évolutions 804/805, employer aussi la candidate avec `S2A_RB_PSO_CAP=0` et le budget textures actif.

Mesurer les octets textures sur le recensement complet des propriétaires `[mem_detail]` commun aux deux versions. Activer `DM_NVN_MEM_DETAIL=1` avec le même `DM_NVN_MEM_DETAIL_INTERVAL`. Sa cadence dépend du nombre d’images. Aligner les observations sur les fenêtres et consigner les mêmes unités et la même position dans le parcours. Consigner les maximums de chaque fenêtre. Exiger moins de 1 450 000 000 octets dans les trois fenêtres candidates avec une cible proche de 1 350 000 000. Utiliser le timestamp du recensement pour exclure une valeur périmée. Le sous-ensemble du registre de résidence et la capacité des tas sont publiés séparément.

Comparer les taux par minute des ré-envois complets et partiels 803 et ajouter les envois réussis après abandon ou purge sur la candidate. Prendre les différences des compteurs aux bornes. Exiger une hausse inférieure à 10 % et, pour une référence nulle, zéro ré-envoi supplémentaire. Consigner les octets envoyés, les relectures invitées disponibles, les page-ins du processus, le p95 et les images affichées >100/200/500 ms par minute. Le p95 et les images longues ne doivent pas augmenter. Les octets de la plage source après éviction et les page-ins n’identifient pas à eux seuls les octets réellement relus du jeu. Une mesure de relecture manquante laisse ce critère ouvert. Garder les traces détaillées sur l’appareil.

## Pagination sur dix minutes

**Corrigé dans les sources.** Le moteur échantillonne `os_proc_available_memory` sur une horloge monotone et traite immédiatement les avertissements et événements critiques de la source `memorypressure`. Le mot de politique publié contient le niveau et le budget total. Les quatre propriétaires calculent leur part à partir de cette même valeur. Le mécanisme vise la mémoire facultative. Les commandes en vol, les ressources actives du jeu et les octets internes du pilote ne peuvent pas être plafonnés par cet instrument.

| Niveau | Déclencheur indicatif hors maintien d’alerte | Total maximum | Préchargement / envois / textures / pipelines |
| --- | --- | ---: | --- |
| Normal | Marge supérieure à 2 Gio après récupération | 512 Mio | 4/16 · 4/16 · 7/16 · 1/16 |
| Avertissement | Marge ≤ 2 Gio, marge indisponible ou événement WARN | 128 Mio | 0 · 3/16 · 12/16 · 1/16 |
| Critique | Marge ≤ 768 Mio ou événement CRITICAL | 32 Mio | 0 · 2/16 · 13/16 · 1/16 |

Le total suit un huitième de la marge, par paliers de 16 Mio, avec un plancher de 16 Mio. Une marge indisponible conduit à 64 Mio en avertissement. Les événements maintiennent l’état critique au moins 15 s et l’avertissement au moins 30 s. La reprise exige dix secondes continues au-dessus du seuil de sortie. Les quotas et refus concernent les lectures facultatives. Les lectures demandées par le jeu continuent.

En baisse de budget, la politique ferme d’abord l’admission du préchargement. Le thread de soumission récupère ensuite les tampons d’envoi dont le GPU a fini de se servir, ajuste les caches de textures reconstructibles puis examine les pipelines froids dont la reconstruction via archive est vérifiée. Les lignes `[RB-MEM-GOV]` distinguent quotas, octets de slots restants, textures par classe et compteurs de PSO. Les chemins d’urgence de la 803 restent disponibles sur l’alerte système, y compris quand le GPU est arrêté. Une part de 4 Kio par pipeline fixe un plafond de **nombre** indépendant du compteur de mémoire hôte superficielle. Le pilote peut garder d’autres octets. `S2A_RB_MEM_GOV=0` redonne les chemins 803 au lancement, y compris pour le tas, les PSO, les textures et la mesure supplémentaire.

**Compilé / livré / observé sur appareil.** Compilation et livraison privées en attente. Aucune partie instrumentée de dix minutes sur iPhone17,2. La session 802 rapportée (environ 9 min, jusqu’à 2,3 Go lus par 10 s, 85 000 page-ins et 63 % de CPU système) motive le seuil de marge. Elle ne suffit pas à calculer la pente demandée pour 803.

**Critère appareil.** Garder le [Banc d’essai de 180 secondes](../../s2arm-benchmark-protocol.md) et ses règles. Pour chaque version, faire trois parties continues de dix minutes avec une fenêtre officielle valide au début de chaque partie. Garder le même iPhone17,2 sous iOS 27, Mario Kart World `0400C3F00006E000`, le circuit, le parcours répété, le cache et l’état initial. Continuer à jouer après les 180 secondes, sans ouvrir le menu ni changer les conditions. Sur la candidate, associer la fenêtre au fichier privé `<id>-paging-600s.json` par son identifiant. Exiger les deux documents complets et la même génération de session. Sur la 803, aligner la série continue des compteurs de processus `ri_pageins` et des ticks CPU système/total de la machine sur le même repère. Conserver la précision disponible dans le journal 803. Un manque de couverture ou un arrondi décisif empêche la conclusion.

Comparer les sommes des intervalles 1–18 (0–180 s) et 43–60 (420–600 s), et la médiane des **60** pourcentages CPU système calculés à partir des ticks de tous les cœurs. Les 24 intervalles centraux participent à la médiane. Exiger `derniers ≤ 1,5 × premiers` et une médiane strictement inférieure à 25 % pour chaque partie candidate. Pour zéro page-in au départ, seule une fin à zéro respecte le seuil et le ratio reste indéfini. Le fichier conserve les horodatages et les compteurs ; un écart au repère de plus d’une seconde, une interruption ou un compteur illisible invalide la série. Les page-ins globaux de la machine sont une autre mesure.
