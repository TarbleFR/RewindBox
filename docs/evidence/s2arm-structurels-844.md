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
  L'unification base/pulling/shadow et la bibliothèque dynamique restent en travail.
- **S5 / 0407** : sommeil sur progression actif pour les polls stables de plus de
  2 ms des threads secondaires de priorité invité >=44, hors propriétaire d'image.
  Maximum demandé 1 ms, réveil anticipé après publication du prédicat hôte, timer
  conservé pour les écritures mémoire sans notification. La soumission asynchrone
  protège toujours le rôle du thread invité d'origine. Les sleeps positifs restent
  inchangés. Latence et énergie sur appareil non mesurées.

S3 reste à implémenter après analyse des alias profondeur/stencil, des copies et
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

Écriture et revue de source effectuées ; compilation iPhoneOS à lancer sur les
deux runners du workflow existant. Aucun nouveau test ou suite approfondie ajouté,
conformément à la consigne du dépôt. Les contrôles de configuration, outils,
licences, ABI, signature et empreintes restent requis. Replay pixels et mesures
iPhone non exécutés. La maturité pondérée reste 50 / 60 / 65 / 35 / 25, soit 50 %.
