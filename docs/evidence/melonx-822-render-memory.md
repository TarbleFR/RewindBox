# MeloNX (RSwitch) après l'IPA 822 : coût du rendu, synchronisations, mémoire

23 novembre 2026. Journaux privés de l'appareil (IPA 822, une session de Hogwarts Legacy de 96 s) : seuls des comptes
et des durées figurent ici. Rien de ce lot n'est mesuré sur iPhone ; aucune IPA ne le contient encore.

## Ce que la 822 a confirmé

- Plus longue pause éphémère du ramasse-miettes : 105 ms (jusqu'à 1 736 ms sur les IPA 816 à 820).
- Cache de shaders de Hogwarts : 2 120 programmes lus en 1 252 ms ; tables de code remplies en 92 ms.
- Journal des variantes : 2 070 variantes prévues, 0 abandonnée pour des états plus récents.
- Lancement jusqu'à la première image : 8 s ; fermeture : 1,5 s.

## Constats (une fenêtre de 5,4 s, 85 images)

- GPU occupé 30 % du temps (19,2 ms par image), fil de rendu occupé 2,84 s sur 5 s, fil GPU 2,58 s sur 5,5 s : aucun
  n'est saturé ; la chaîne invité → fil GPU → fil de rendu → GPU se vide et se remplit à chaque attente.
- Fil de rendu : descripteurs des dessins 872,6 ms, des calculs 290,3 ms ; 290 087 jeux de descripteurs écrits
  (5 959 778 descripteurs) ; passes de références des tableaux de textures 28 027 (223,1 ms).
- Recherche de pipeline : 113 869 appels, 446,7 ms, dont 367,3 ms pour 2 dessins qui ont attendu une compilation ;
  le reste coûte 0,57 µs par appel.
- Synchronisations : 722 envois (vkQueueSubmit 349 ms, coût d'encodage de MoltenVK au moment de l'envoi) ; mode de
  vidage rapide actif sur 85 images sur 85 ; 1 087 ms d'attente, par des fils de l'invité qui relisent de la mémoire
  écrite par le GPU.
- Fil GPU : `bindings` 158 472 appels 716,5 ms, `bufLoad` 77 097 appels 645,7 ms, `compute` 665 ms.
- Mémoire : empreinte 4,4 à 4,6 Go, appareil à 7 à 10 % disponible, alertes mémoire dès 52 s ; tas des gros objets
  474 Mio dont 228 Mio libres en fin de session ; une coupure de 1 400 ms avec environ 24 600 décompressions de pages.
- Vulkan : 14 807 blocs, 633 Mio, tous dédiés.
- 408 + 410 exceptions `FileNotFoundException` pour /etc/resolv.conf.
- Les lignes `jitArena timing`, `reached` et `used` de la 822 sont remplacées par « [redacted key entry] » : le filtre de
  confidentialité du journal (`EmbeddedLaunchDiagnostics.Safe`) prend une ligne qui commence par `nom=` pour une clé.

## Correctifs

| Adaptateur | Effet | Preuve hors appareil |
|---|---|---|
| `adapt_buffer_texture_bindings` | Le fil GPU réutilise la recherche d'une texture de type tampon tant que rien ne l'a invalidée, comme pour les textures ordinaires | Porte `buffer-texture-bindings` (87 vérifications) : appels au rendu identiques octet pour octet sur 6 340 dessins et calculs ; recherches de textures 244 603 → 64 283 ; temps CPU du fil GPU −7 à −8 % ; une variante sans invalidation est détectée |
| `adapt_unblocked_sync_queries` | Le fil GPU et le fil de rendu ne restent plus bloqués derrière un fil de l'invité qui attend le GPU : une synchronisation tenue par un attenteur compte comme non terminée | Porte `unblocked-sync-queries` (80) : requête du fil GPU pendant une attente de 60 ms 54,0 → 0,018 ms ; fil de rendu bloqué 173 → 1,4 ms sur un flux de 45 images ; trace de 6 000 étapes identique |
| `adapt_large_buffer_native` | Les tampons temporaires de 85 000 octets ou plus que le pool n'a pas (données de textures, lectures de la mémoire de l'invité) sont pris en mémoire native, libérée au plus tôt 3 s après leur retour | Porte `large-buffer-native` (53), CoreCLR avec le ramasse-miettes « segments » comme sur iOS : allocations dans le tas des gros objets 452 → 67 Mo ; pic 301 → 240 Mio ; données identiques |
| `adapt_device_pressure_compaction` | La compaction existante agit aussi quand l'appareil est à 10 % ou moins disponible : au plus 3 par session, refusée si la pause prévue dépasse 300 ms, fermée après une pause longue ou un gain inférieur à 64 Mio | Porte `device-pressure-compaction` (58) : mémoire engagée 554 → 343 Mio pour une pause de 160 ms sur l'hôte ; un tas de 900 Mio est refusé sur sa prévision |
| `adapt_network_interface_snapshot` | Une énumération des interfaces réseau sert 5 s ; sans /etc/resolv.conf, la recherche d'interface locale répond sans énumérer | Porte `network-interface-snapshot` (41) : exceptions 480 → 4 sur 60 requêtes, 3 204 → 0 sur 400 requêtes de 8 fils ; réponses identiques |
| `adapt_descriptor_set_reuse_journal` | Mesure seule : combien de jeux de descripteurs auraient pu être gardés ou réutilisés, et répartition du temps d'une mise à jour de calcul | Porte `descriptor-set-reuse-journal` (277) : écritures, liaisons et ordre identiques au contrôle ; coût de la mesure environ 0,4 % du temps des descripteurs |
| `adapt_vulkan_memory_rounding_journal` | Mesure seule : mémoire perdue en arrondis de 16 Kio par liste, temps des allocations de mémoire Vulkan | Porte `vulkan-memory-rounding-journal` (98) : allocations identiques au contrôle ; compteurs exacts sur un flux modelé |
| `adapt_jit_arena_usage_journal` (corrigé) | Les lignes `jitArena` commencent par un mot et passent le filtre du journal | Porte `jit-arena-usage-journal` (751) : chaque ligne laisse `Safe` inchangé ; la forme de la 822 est vue comme masquée |

## Écartés, avec leur raison

- Réutilisation des jeux de descripteurs : gain estimé à 1,4 % du temps du fil de rendu sur un taux de répétition
  modelé, plus lent sur l'hôte dans le flux modelé, et une erreur afficherait de mauvaises textures. Remplacée par la
  mesure ci-dessus ; à activer si au moins 10 % des jeux écrits sont réutilisables.
- Regroupement des petits tampons Vulkan : au mieux −26 Mio, peut-être +7 à +11 Mio selon l'arrondi réel de Metal,
  et les nettoyages sous pression rendraient 35 à 70 Mio de moins. La mesure des arrondis tranchera.
- Vidage rapide, envois « helper », redémarrages de passes de rendu : chacun est justifié par les attentes réelles, les
  requêtes d'occlusion ou une opération qui ne peut pas s'exécuter dans une passe.

## À lire dans les journaux de la prochaine IPA

- `gcEvent` : octets alloués dans le tas des gros objets par 15 s sous 30 Mio (822 : 19 à 164) ; `memoryInventory` :
  tas des gros objets sous 350 Mio dont moins de 120 libres (822 : 452/217).
- `memory heapCompacted: devicePressure` : 1 ou 2 par session de Hogwarts, pause sous 300 ms, mémoire engagée en baisse
  d'au moins 150 Mio. Réfuté si une ligne `pressureCompactionClosed` cite une pause longue.
- « Vulkan host sync waits » : « passed a sync being waited for » au-dessus de 0, requêtes les plus longues sous 1 ms.
- Phases du fil GPU : `bindings` (716,5 ms dans la 822), `compute` (665 ms), `gpuDispatch` par dessin (≈17 µs).
- « Vulkan descriptor set reuse measured (not applied) » et la ligne `vulkanMemory` (arrondis, temps d'allocation).
- `jitArena timing` et `jitArena used` lisibles.
- Exceptions réseau : au plus deux par interface et par 5 s quand le jeu passe en ligne.

## Risques

- Mémoire native : un tampon utilisé plus de 3 s après son retour ferait planter au lieu de lire des données périmées.
  Si un plantage nomme `NativeBuffer`, c'est ce correctif.
- La première compaction sous pression peut dépasser sa prévision (sur l'hôte : 246 ms pour 161 prévues).
- nifm voit un changement de réseau jusqu'à 5 s plus tard.
