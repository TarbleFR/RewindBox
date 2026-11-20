# Attribution mémoire avant livraison 803 — revue de la source 0001–0170

**État : proposition examinée en lecture seule, non intégrée, non compilée et non mesurée sur appareil.** Aucun budget, rendu, cache de shaders ou fichier du dépôt n’a été modifié. Les fichiers `.inc` joints sont des propositions d’intégration, pas un patch prêt à livrer. L’analyse porte sur la source appliquée `engine170-mod` fournie par le responsable du chantier ; ses fichiers sont identifiés par SHA-256 dans `memory-evidence.json`.

## 1. Décision et périmètre minimal de 0171

La prochaine instrumentation doit d’abord rendre les mesures comparables, puis attribuer les octets. Les données actuelles **ne permettent pas de dire à quel composant appartiennent les quelque 1,1–1,36 Go évoqués**. Réduire un budget Metal, une réserve, un cache ou la lecture anticipée maintenant reviendrait à choisir une cause sans attribution.

Le changement minimal utile comporte trois éléments séparables :

1. **Ledgers supplémentaires dans le prélèvement TASK_VM_INFO existant**, toutes les dix secondes. Il fournit déjà une vue globale du processus ; l’ajout de champs n’exige ni parcours VM, ni lecture de page, ni énumération de ressources Metal.
2. **Un parcours récursif complet des métadonnées VM, demandé après la fin de la fenêtre chronométrée**, jeu actif, sur une file série de priorité utilitaire. Il donne les catégories et la couverture qui manquent à 0108, avec des limites explicites sur les alias et le temps de prélèvement. Il ne participe jamais au score de cadence.
3. **Observation bornée des conseils de lecture anticipée et de leur réutilisation ultérieure**, en réutilisant les résultats `mincore` déjà obtenus et les points où les lecteurs naturels terminent. Les opérations de lecture et leurs budgets restent identiques. Le suivi est une phase diagnostique après le score, désactivable indépendamment ; ses pertes de mesure doivent être comptées.

Interrupteurs proposés :

| Interrupteur | Valeur 1 | Valeur 0 |
|---|---|---|
| `S2A_RB_VM_LEDGERS` | Ajoute les champs du résultat TASK_VM_INFO existant | Ligne antérieure et aucune mesure supplémentaire |
| `S2A_RB_VM_CENSUS` | Arme une demande explicite après la fenêtre chronométrée | Aucun nouveau parcours ; comportement 0108 conservé |
| `S2A_RB_POOL_USE_PROBE` | Arme le suivi borné des hints/demandes après le score | Aucun événement, table ou parcours supplémentaire |

Le coupe-circuit existant `S2A_RB_VM_TAGS=0` doit continuer à supprimer tout parcours VM, y compris le nouveau. Pendant un census nouveau, ne pas lancer en parallèle une tranche 0108. Pour le banc de comparaison, conserver les mêmes réglages d’observation dans les deux bras ; ne pas comparer un bras instrumenté en continu à un bras sans diagnostic.

## 2. État réellement observé dans MKW 802

Identité de la capture : app 802, moteur Actions 44746620489. Les relevés viennent de `engine/0400C3F00006E000/host.log` ; aucune scène synchronisée ne confirme une conduite continue.

| Constat | Preuve |
|---|---|
| 20 relevés TASK_VM_INFO | Entre les lignes 2635 et 16082 ; détails et hash dans `memory-evidence.json` |
| Après la frame 2046 : **1 240–1 331 Mio** de compressed logique | 15 relevés des frames de heartbeat 2069–6400 ; exemples lignes 8817, 14276 et 16082 |
| 20 tranches 0108, **aucun parcours complet** | Toutes terminées `time-limit`, slices 1–20 |
| 30 080 régions visitées au fil des tranches | Observations séparées d’environ dix secondes ; ce n’est pas un recensement à un instant donné |
| Une tranche annoncée avec budget de 5 ms dure **10,5 ms** | Ligne 15684, slice 19, 192 régions |
| À la frame 6300, 0089 : **342 spans / 1 966 Mio** demandés, **99 387 pages absentes** observées par le worker, 1 552 Mio arrondis | Ligne 15918 |
| File 0096 au même point : 0 Mio en attente, pic 63 Mio, 61 spans refusés | Ligne 15919 |

Les anciens logs écrivent « MB » mais les expressions utilisent `bytes >> 20` : ce sont des **Mio**. Le volume « compressed » est une comptabilité à la taille d’origine des pages, **pas la place physique du compresseur**. Apple décrit cette distinction dans sa session sur la mémoire des jeux. [Apple WWDC22, mémoire et coût des pages compressées](https://developer.apple.com/videos/play/wwdc2022/10106/).

Les compteurs de 0089 ne donnent ni des pages uniques, ni la réussite de chaque `madvise`, ni des octets effectivement lus sur disque, ni une consommation ultérieure. La fonction ignore actuellement le résultat de `madvise`. Les 1 966 Mio ne représentent donc pas 1 966 Mio de RAM retenus et ne doivent pas être soustraits du footprint.

## 3. Ledgers : ce que l’API permet d’affirmer

Source primaire inspectée : Apple XNU **12377.1.9**, commit **f6217f891ac0bb64f3d375211650a4c1ff8ca1ea**, obtenu dans le dépôt officiel Apple. Ce commit documente l’implémentation publique étudiée ; il n’est pas identifié comme le kernel exact de l’iPhone utilisé.

### Compteurs à conserver séparés

- `phys_footprint` reste le total de référence du processus.
- `resident_size`, `internal`, `external`, `reusable` et `compressed` décrivent d’autres vues. Le total de ces colonnes n’est pas un footprint.
- `ledger_tag_graphics_footprint` et `ledger_tag_graphics_footprint_compressed` distinguent les composantes résidente et compressée des objets graphiques comptés dans le footprint. Les deux variantes `nofootprint` doivent rester séparées.
- Recueillir de même media, neural, réseau et les états purgeable volatile/nonvolatile. Les champs réseau ne doivent pas être renommés arbitrairement « footprint » : le code d’attribution XNU les traite à part.
- Ne jamais calculer un résidu `compressed - graphics_compressed` puis l’appeler « CPU » ou « cache de shaders ». Le premier champ est alimenté par `internal_compressed`; les ledgers de catégories reposent sur les tags, l’ownership et la purgeabilité des objets. Les seules valeurs publiques observées ne prouvent pas une partition additive entre ces vues.

Références : [TASK_VM_INFO et révisions de la structure, task_info.h](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/mach/task_info.h#L363-L452), [lecture des ledgers, task.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/kern/task.c#L6035-L6209), [règles des catégories d’objets, vm_object.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/vm/vm_object.c#L8675-L8832).

### Lecture sûre et coût

Le point d’accroche est **`ios/app.m:708`** : réutiliser `vi`, `vn` et `kr` déjà obtenus dans la file `s2a.heartbeat`. Initialiser la structure à zéro, passer `TASK_VM_INFO_COUNT` en unités de `natural_t` et contrôler le **count effectivement renvoyé**. Les champs de catégories demandent `TASK_VM_INFO_REV3_COUNT`; le footprint, REV1. Une donnée indisponible est `valid=0`, jamais un zéro implicite. Les ledgers sont signés : garder leur type, sans convertir une éventuelle valeur négative en énorme nombre non signé.

Le fichier `ledger-snapshot.inc` fournit le format et les gardes proposés. Il conserve le nom réel, mal orthographié dans l’API, `ledger_purgeable_novolatile_compressed`. Fractionner les sorties par catégorie limite le risque de troncature ; toutes portent génération, frame et horodatage du même prélèvement. Ajouter la durée de l’appel `task_info` existant, pas un second appel uniquement pour l’instrumenter.

Les ledgers ne donnent pas l’identité d’une texture, d’un pipeline, d’un tableau C ou d’un objet .NET. Ils permettent de choisir la famille à examiner ensuite. Les compteurs déjà présents du renderer, de l’upload, de la résidence et du heap géré servent à corréler une hausse ; ils ne constituent pas une preuve de propriété des pages compressées.

## 4. Pourquoi 0092/0108 restent incomplets

**`runtime/src/vawin.c:1290–1361`** expose plusieurs limites distinctes :

1. `depth` est réinitialisé à zéro à chaque appel, puis les `is_submap` sont sautées. Le parcours décrit le niveau supérieur, pas toutes les feuilles des sous-cartes.
2. `user_tag == 32` est toujours ignoré. Dans les en-têtes Apple, 32 est `VM_MEMORY_SHARED_PMAP`, pas un synonyme de « mémoire toujours gratuite ». L’ignorer exclut potentiellement des pages privées ou COW observables sous la sous-carte.
3. Le budget est vérifié toutes les 64 régions. Un seul appel détaillé peut être long. La valeur 5 ms est donc une limite coopérative, pas une échéance dure.
4. 0108 poursuit son curseur au heartbeat suivant, dix secondes plus tard. Chaque tranche remet ses totaux à zéro et les données peuvent changer entre tranches. Additionner ces lignes pour les comparer au TASK_VM_INFO d’une seule frame serait incorrect.
5. Les tableaux à 256 tags rabattent les autres valeurs sur 0 ; la classification mélange alors un tag inconnu et la mémoire sans tag. Le nouveau census doit garder un compartiment `other_tag`, et distinguer les éventuels tags synthétiques.

Références : [constantes de tags VM et ledger](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/mach/vm_statistics.h#L603-L658), [contrat de récursion et structure](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/mach/vm_region.h#L215-L321).

### Attention au mot « sans scan de pages »

Le parcours proposé **ne lit pas le contenu des pages invitées**, ne les faute pas volontairement, ne les décompresse pas pour mesurer leur contenu et ne crée aucun checksum. En revanche, XNU calcule les compteurs détaillés en parcourant les métadonnées des pages sous verrous VM. Il peut aussi parcourir les aliases de l’objet. Il faut donc écrire « sans lecture des octets » et non « coût nul » ou « aucune activité par page ». Le budget ne peut pas interrompre un appel Mach déjà entré dans le kernel. [vm_map_region_walk et lecture de l’état du pager](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/vm/vm_map.c#L15948-L16213).

## 5. Parcours complet après le score : contrat précis

Le fichier `vm-walk-proposal.inc` donne le cœur de l’algorithme. Les paramètres proposés (2 ms coopératives, au plus 64 appels par tranche, reprise environ 25 ms plus tard, 262 144 appels et 30 s par passe) sont **des bornes de prudence à mesurer**, pas des seuils validés. Une limite atteinte produit un résultat incomplet et n’autorise aucun total global supposé.

### Déclenchement et déroulement

Après le marqueur explicite de fin du segment chronométré, armer une seule passe, jeu toujours actif. Capturer génération, frame, temps monotone, bornes de fenêtre et TASK_VM_INFO initial. Demander une nouvelle file série `QOS_CLASS_UTILITY`; aucune attente côté UI ou rendu. Coalescer ou refuser un deuxième lancement tant qu’un worker existe. Ne pas déclencher sur un nom d’asset, un nombre de frames supposé représenter une course ou le seul passage d’une minute.

Utiliser `mach_vm_region_recurse` à partir de zéro, conserver le niveau de récursion renvoyé, descendre à la même adresse quand `is_submap` est vrai, avancer de `address + size` uniquement après une feuille. Ne pas sauter le tag 32. Les champs pages des sous-cartes ne sont pas valides et ne s’ajoutent pas à ceux de leurs feuilles.

Contrôler `KERN_SUCCESS`, le count, taille non nulle, dépassement arithmétique, progression de l’adresse et profondeur. `KERN_INVALID_ADDRESS` signifie la fin normale du parcours. Un autre échec, une région fusionnée revenant avant le curseur, un dépassement de profondeur ou de budget garde un état explicite d’échec/changement/incomplétude. Pas de retry sans borne. Éviter de remettre le curseur au début et de sommer une seconde fois des zones déjà comptées.

### Classification et alias

Pour chaque feuille, conserver seulement les métadonnées nécessaires à des agrégats : tag, mode de partage, indicateur external-pager, pages résidentes/compressées/dirty, taille et côté de la fenêtre. Une région qui traverse une limite reste `crossing` : proratiser ses pages à partir de sa taille serait inventer leur emplacement.

`external_pager` peut venir d’une chaîne de shadows ; il ne signifie pas que toutes les pages comptées sont des pages de fichier propres et gratuitement évictables. Le nom du compartiment doit refléter ce fait. Les tags VM **100 (IOAccelerator), 88 (IOSurface), 21 (IOKit), 1/2/3… (malloc), 30 (stack)** et 240–255 ne sont pas les tags de ledger ; notamment `VM_LEDGER_TAG_GRAPHICS` vaut 4, dans un espace de noms différent. [Tags Apple](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/mach/vm_statistics.h#L603-L862).

Les alias de la même mémoire peuvent figurer plusieurs fois. Un couple `object_id_full + offset + size` peut détecter des plages identiques dans la même passe, quand la version renvoyée inclut l’identifiant complet. Il ne déduplique pas toutes les plages partielles, tous les shadows COW, ni les objets évoluant pendant la passe. **Ne pas annoncer une somme physique dédupliquée.** Au minimum publier les comptes par mode de partage, les doublons exacts détectés, la saturation de la table de détection et l’avertissement de recouvrement. Un census complet signifie « fin de l’espace d’adresses atteinte », pas « égal à phys_footprint ».

XNU comporte aussi, dans certains modes de reporting, une région synthétique pour des objets purgeables ou ledger-tagged dont le processus porte l’ownership. Cela confirme qu’un simple recensement de mappings et les ledgers ne sont pas interchangeables. Ne pas activer ici de politique privée de `task_self_region_footprint` pour tenter de forcer une égalité. [Région synthétique dans vm_map.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/vm/vm_map.c#L15364-L15438).

### Cycle de vie et annulation

Réutiliser les API existantes de **`runtime/src/session.c:114–118`** : `s2a_host_session_state()`, `s2a_session_stop_requested()` et `s2a_session_generation()`. Vérifier RUNNING, absence d’arrêt et génération identique avant **et après** chaque appel Mach, puis avant la publication finale. La transition vers RESTARTING précède `s2a_window_session_reset` ; les générations changent à la reconstruction. Ne pas utiliser seulement `s2a_rb_guest_session_over()`, qui ne vaut pas nécessairement vrai pendant un park réussi.

Le worker ne détient ni texture, ni pool, ni pointeur vers le contenu invité. Il garde seulement des bornes copiées, des entiers et ses propres agrégats. Un appel Mach déjà en cours peut finir après le début du retrait : jeter alors son résultat et arrêter. Aucun `dispatch_sync`, attente de groupe, annulation de thread ou attente sur l’UI. L’état du worker est libéré par son dernier bloc ; une reprise du jeu n’efface pas la mémoire de travail d’un ancien worker encore vivant.

Une course entre la vérification d’état et le syscall reste possible, mais aucun octet de mapping libéré n’est relu par notre code. Le kernel gère la requête sur la carte courante ; le contrôle après retour empêche d’attribuer ce résultat à l’ancienne session. Si une annulation stricte avant toute nouvelle requête kernel est requise, elle nécessiterait une coordination supplémentaire et un verrou ; ce n’est pas le périmètre minimal recommandé.

### Résultat publiable

Une passe doit porter : ID local de mesure, génération, frame/temps de début et fin, états thermiques, statuts foreground/capture, état final et code kernel, nombre d’appels/feuilles/sous-cartes, profondeur maximale, taille de page, tags/catégories, couverture, alias possibles, pertes/troncatures, durée murale, temps passé dans les appels, durée de l’appel le plus long et CPU du worker. Garder TASK_VM_INFO avant/après. Une variation entre les deux rappelle que la passe est temporelle, non atomique.

Publier les agrégats et la provenance ; ne pas publier les adresses, identifiants d’objets, UUID personnels, chemins de fichiers ni journaux bruts. Garder les captures originales privées.

## 6. Mesurer l’utilité de 0089 sans nouvelle lecture des pages

Points d’accroche exacts : **`nvn_mtl.m:5095–5136`** (`rb_wn_` et résultat `mincore`), **5404–5420** (`rb_pa_post`), **5423–5472** (`rb_pool_ahead`), **6021–6022** (demande de l’upload), **5149–5164** (pages écrites et niveaux), puis résumé **5480–5524**. Le lifecycle de lecture anticipée existant est dans **`nvn_session.inc:93–110`**.

Le fichier `prefetch-observation-design.md` détaille un suivi d’événements borné. Le point essentiel est de distinguer :

- page initialement absente, couverte par un `MADV_WILLNEED` **retourné avec succès** ;
- page ultérieurement demandée par un lecteur de texture, déjà résidente ou encore absente selon le `mincore` existant ;
- lecture effective confirmée au retour du lecteur naturel, pour les chemins dont la couverture peut être prouvée sans nouveau parcours ;
- hint jamais suivi d’une lecture **observée dans la couverture et la durée retenues**, qui n’est pas une preuve de page inutile.

`MADV_WILLNEED` n’est pas une notification d’E/S achevée et `mincore` ne révèle pas la cause de la résidence. Même une page résidente à sa demande peut avoir été chargée par une autre lecture, un write, une autre file ou le pager. La métrique doit s’appeler « réutilisation observée d’un hint », jamais « fautes économisées » ou « pages chargées grâce à 0089 ». La causalité demande ensuite un A/B de 0089 seul dans un protocole identique, sans changer le cache de shaders ni les autres budgets.

## 7. Ordre de mesure comparable et acceptation

1. **Avant comparaison**, figer identité IPA/moteur/jeu, résolution 1×, intervalle de présentation natif, profil et overrides, parcours/état initial, mode docké, état des caches et durée. Les comparaisons après 0170 doivent séparer les demandes intervalle 1 et 2 ; un FPS plus bas après restauration de la cadence peut être le comportement demandé.
2. **Pendant le segment scoré**, garder les relevés légers existants et les ledgers à dix secondes ; aucun nouveau census ou suivi de pages. Associer moteur/écran, délais p95/p99, pauses, CPU/GPU, audio, chauffe et mémoire à la même identité. Ne pas purger les caches pour simuler une première visite.
3. **Après le marqueur de fin**, jeu actif, effectuer le census et une fenêtre diagnostique de réutilisation. Identifier clairement cette période pour l’exclure du score. Un échantillonnage TASK_VM_INFO à une seconde, s’il est utile, appartient à cette période séparée et doit publier son coût.
4. **Aux points de lifecycle**, snapshots légers avant retour au menu, après park, puis lors d’une reprise. Une reprise dans le même processus et un lancement neuf sont deux conditions différentes ; ne pas fusionner leurs mémoires et leurs caches.
5. **Attribuer avant agir** : choisir le premier composant à examiner seulement après une catégorie mesurée, une couverture déclarée et une corrélation reproductible. Une marche incomplète, un ledger non supporté ou une table d’observation saturée produit « non attribué », pas une taille à récupérer.

L’intégration pourra être déclarée corrigée/compilée séparément d’une observation iPhone. Le présent rapport ne démontre ni mémoire récupérable, ni gain de FPS, ni réduction de chauffe. Aucun nouveau test ou suite n’est proposé ; la compilation des derniers ajouts et les contrôles de provenance/ABI/signature suivent la recette existante.

## Intégration retenue pour 0171

La proposition de parcours et de ledgers est intégrée dans les nouveaux modules `ios/rb_vm_audit.m` et `ios/rb_benchmark.m` du patch 0171. Le parcours complet suit la fenêtre chronométrée, avec annulation par génération et exclusion mutuelle des anciens scans. Les crochets de lecture anticipée restent une [proposition de mesure](prefetch-observation-design.md) : aucun taux d’utilisation ni gain ne peut encore être produit. Aucun budget n’est modifié. Voir le [protocole](../../s2arm-benchmark-protocol.md) et l’[audit des familles](audit-803.md).
