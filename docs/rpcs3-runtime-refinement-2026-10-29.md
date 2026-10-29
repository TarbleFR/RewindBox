# RPCS3 — réduction des surcoûts runtime après le Core vérifié

Le lot repart de `Claude` **140f35c1**, qui reste la tête distante au début du travail. Le Core de référence est **5b2a5614**, SHA-256 `a45a9de84c7b3b82a43dc091a999da32316389f575a0afd8c983d69bd8a1f276`. Trois améliorations sont implémentées dans le delta canonique. Aucun Core, IPA, tag ni release n’est fabriqué par ce lot. Les résultats ci-dessous sont des mesures Linux et des contrôles de code généré, sans résultat de gameplay sur iPhone.

## Sources réellement modifiées

| Fichier / fonction | Travail retiré | Invariants conservés |
|---|---|---|
| `rpcs3/Emu/RSX/VK/vkutils/commands.cpp`, `update_descriptor_binding_cache()` | `memcmp`/`memcpy` de taille variable remplacés par des accès aux un ou deux handles | Bind point, layout exact, nombre, handles, offsets dynamiques, début d’enregistrement ; état et taille du command buffer inchangés |
| `rpcs3/Emu/Cell/SPUThread.cpp`, `spu_dec_intr_timer::operator()()` | Conversion entière en microsecondes une fois après le balayage, au lieu d’une fois par survivant | Compaction stable, ordre, tokens, rétention IDM, callbacks hors verrou, allocation avant déplacement, absence d’allocation sans expiration |
| `rpcs3/ios/IOSTexturePrehash.h`, `lookup()` | Miss de clé : cinq lectures atomiques → deux ; miss d’époque : cinq → trois | Chemin réussi identique : cinq lectures, acquire des champs et vérification finale de séquence ; publication CAS non bloquante inchangée |
| `rpcs3/Emu/CPU/JITCacheCompatibility.cmake` | Alias du seul nouveau hash exact de SPUThread | Identités PPU/SPU préservées uniquement après preuve des 41 entrées de codegen |

Le timer prend le minimum des **numérateurs après multiplication non signée** avant la division commune. Il conserve ainsi même les débordements modulo 2⁶⁴ de l’ancienne expression pour les échéances extrêmes ; choisir simplement la plus petite échéance aurait été incorrect dans ces cas. `clocks_scale` est un réglage non dynamique (`cfg::_int<10, 3000>`, sans option dynamic), stable pendant ce balayage. Les contrôles incluent aussi 0, 1 et UINT32_MAX dans le modèle arithmétique.

Le prehash ne change ni adresse/longueur, ni époques, invalidations, bypass après écriture, capacité, allocation, worker ou liste d’activation. Automatic reste limité à GOW3. Un miss peut toujours déclencher le hash synchrone ; aucun résultat partiel ou périmé n’est accepté. Les statistiques existantes ne sont pas renommées.

## Résultats et compromis

Mesures principales : **Linux x86_64, GCC 13.3.0**, sept séries, mêmes scénarios et mêmes options avant/après. Les wrappers descripteurs utilisent un driver réduit à un compteur ; les timers un mutex et des vecteurs hôte. Le banc de validation garde le worker garé, les observers désactivés et les buffers existants préparés. Ce lot ne garantit pas un CPU exclusif et n’impose pas d’affinité ; ses timings ne sont pas comparables directement aux anciennes médianes macOS.

Les séries complètes et leur dispersion figurent dans [measurements.json](evidence/rpcs3-runtime-refinement-20261029/measurements.json). Tous les cas sont conservés, y compris les médianes plus lentes. Les grosses différences du banc de validation peuvent aussi concerner des bypass ou tailles sous le seuil dont le programme utile ne change pas : elles ne prouvent pas un effet du nombre de lectures atomiques.

| Banc / scénario | Unité | Avant | Après | Variation de durée |
|---|---|---:|---:|---:|
| timer / 6 / all_due | ns/sweep | 30.283 | 32.165 | +6.22 % |
| timer / 6 / alternating | ns/sweep | 29.702 | 36.989 | +24.53 % |
| timer / 6 / none_due | ns/sweep | 20.763 | 18.668 | -10.09 % |
| timer / 32 / all_due | ns/sweep | 153.851 | 142.111 | -7.63 % |
| timer / 32 / alternating | ns/sweep | 139.228 | 195.843 | +40.66 % |
| timer / 32 / none_due | ns/sweep | 102.395 | 61.883 | -39.56 % |
| timer / 128 / all_due | ns/sweep | 202.130 | 199.326 | -1.39 % |
| timer / 128 / alternating | ns/sweep | 188.161 | 159.462 | -15.25 % |
| timer / 128 / none_due | ns/sweep | 235.923 | 176.248 | -25.29 % |
| timer / 1024 / all_due | ns/sweep | 2819.410 | 2590.220 | -8.13 % |
| timer / 1024 / alternating | ns/sweep | 2477.360 | 2275.940 | -8.13 % |
| timer / 1024 / none_due | ns/sweep | 2173.520 | 1692.600 | -22.13 % |
| descriptor / graphics_hits | ns/wrapper | 1.658 | 1.114 | -32.77 % |
| descriptor / changing_sets | ns/wrapper | 9.489 | 5.931 | -37.50 % |
| descriptor / alternating_bind_points | ns/wrapper | 1.639 | 2.407 | +46.84 % |
| lookup / hit | ns/lookup | 2.118 | 1.397 | -34.04 % |
| lookup / epoch_miss | ns/lookup | 3.041 | 1.586 | -47.84 % |
| lookup / key_miss | ns/lookup | 2.339 | 1.044 | -55.35 % |
| validation / 32768 / identical | ns/validation | 1350.704 | 1383.083 | +2.40 % |
| validation / 32768 / distinct | ns/validation | 1363.156 | 1406.944 | +3.21 % |
| validation / 32768 / scoped_bypass | ns/validation | 1483.006 | 1424.832 | -3.92 % |
| validation / 65536 / identical | ns/validation | 397.531 | 374.387 | -5.82 % |
| validation / 65536 / distinct | ns/validation | 2965.641 | 2719.114 | -8.31 % |
| validation / 65536 / scoped_bypass | ns/validation | 3067.902 | 2644.927 | -13.79 % |
| validation / 262144 / identical | ns/validation | 1284.439 | 1227.068 | -4.47 % |
| validation / 262144 / distinct | ns/validation | 10688.992 | 12592.492 | +17.81 % |
| validation / 262144 / scoped_bypass | ns/validation | 10639.191 | 11119.002 | +4.51 % |
| validation / 1048576 / identical | ns/validation | 5072.117 | 5005.688 | -1.31 % |
| validation / 1048576 / distinct | ns/validation | 44026.828 | 41830.539 | -4.99 % |
| validation / 1048576 / scoped_bypass | ns/validation | 41318.922 | 42511.391 | +2.89 % |
| validation / 3686400 / identical | ns/validation | 17354.578 | 18216.797 | +4.97 % |
| validation / 3686400 / distinct | ns/validation | 155930.609 | 150904.734 | -3.22 % |
| validation / 3686400 / scoped_bypass | ns/validation | 154837.594 | 155154.141 | +0.20 % |

**11 médianes régressent sur 33 cas.** En particulier, l’alternance graphics/compute du wrapper GCC et certains lots partiellement expirés restent plus coûteux. Aucun bind supplémentaire n’est éliminé par rapport au Core vérifié : les nombres de commandes sont identiques ; le travail réduit est celui du wrapper. Aucun seuil de performance n’est utilisé pour masquer une régression.

Une seconde compilation Linux avec **Clang 22.1.8 via Zig 0.17.0 / libc++** exécute les mêmes deux programmes descripteurs. Ses résultats bruts, plus coûteux pour la référence, sont conservés séparément dans `arm64/*-descriptor-clang.json` ; ils ne sont pas des mesures ARM64 et ne remplacent pas les résultats GCC. Les bibliothèques standard et frontières de driver diffèrent du Core réel.

Le code ARM64 est compilé avec Clang 22.1.8, cible **aarch64-linux-gnu**, scheduling **apple_a16**, à partir des corps extraits et des mêmes adaptateurs. Dans le helper descripteur, les appels `bcmp` et `memcpy` disparaissent, ainsi que le cadre de pile de 64 octets sur les chemins normaux. Le mock timer conserve une échelle constante : LLVM abaisse ses divisions en multiplications/décalages ; ces conversions quittent la boucle dans le candidat. Ce n’est ni une compilation avec le SDK iPhone ni une mesure sur A18 Pro. Sources, assembleurs complets compressés, extraits et empreintes : [arm64/receipt.json](evidence/rpcs3-runtime-refinement-20261029/arm64/receipt.json).

## Piste MFC étudiée puis retirée

Une variante teste shuffle_limit et taille avant de calculer le minimum. Les décisions des 18 939 904 masques et 235 008 appels à `do_mfc()` restent égales dans le modèle de transferts/canaux. Les assertions de lecture d’horloge de l’ancien adaptateur historique ont dû être adaptées : la nouvelle référence est déjà conditionnelle. Le premier échec de cet adaptateur et sa correction sont conservés comme tels.

Sur Linux, la différence du masque désactivé est minime (1,394 → 1,383 ns), et la file vide peut être légèrement plus lente. Sur ARM64, la variante ajoute un deuxième branchement conditionnel. Aucun bénéfice utile sur le chemin complet n’est démontré. **La variante est retirée : le masque MFC du Core vérifié reste exact à l’octet**, sans revendication d’accélération fondée sur le nombre de lectures d’horloge. Programme, résultat fonctionnel, sept séries et décision : [mfc-withdrawn/decision.json](evidence/rpcs3-runtime-refinement-20261029/mfc-withdrawn/decision.json).

## Vérifications exécutées et résultats réutilisés

- **11 modes natifs frais réussis sur Linux** : cinq plain, cinq ASan/UBSan et un TSan. Le stress TSan vérifie les vraies publications et recherches atomiques, sans suppression de race. LeakSanitizer est désactivé.
- Timer : 210 combinaisons historiques concernées, 1 792 nouveaux cas de limites/débordements/ordre, deux erreurs d’allocation, réentrance et arrêt ; 2 172 notifications identiques, 6 145 tokens obsolètes rejetés. Les deux contrôles utilisent déjà la compaction stable.
- Descripteurs : les 20 scénarios de justesse restent exacts dans les deux versions corrigées, dont 4 096 opérations mixtes, clés incompatibles, offsets dynamiques et cycles d’enregistrement. Aucun changement du chemin desktop.
- Hashes : 96 validations répétées restent à 12 hashes, 32 plages distinctes à 32, trois chevauchements modifiés sont rejetés. Chaque version exécute 500 000 tentatives de publication et 500 000 recherches, avec des résultats acceptés réellement observés et vérifiés. Le nouveau cas d’entrelacement place un changement d’époque entre lecture de l’époque et du payload ; la séquence finale doit le refuser.
- Scoped-write réellement affecté : ses deux modes sont rejoués, avec 2 808 écritures, 96 scénarios de bindings, 200 courses et zéro payload périmé accepté. Les parcours CPU/GPU sont des adaptateurs explicites.
- **Une exécution CMake en mode script**, sans configuration ni compilation du Core, vérifie PPU `a987639e9f838d1c`, SPU `d070cb361bdef607`, retrait de l’alias, source future inconnue et mauvais chemin. Les 40 sources physiques et le postimage LLVM externe épinglé sont authentifiés ; sans l’alias nouveau, SPU devient `dc320149b747f2a7`.
- Le patch unique est rematérialisé sur une copie amont propre et reproduit **313 postimages : quatre changées, 309 identiques**, sans ajout ni retrait. Les 88 exports et le contrat statique avec le pont hôte sont conservés.
- Le nouveau contrat authentifie 330 entrées du dépôt, les 313 postimages, les 97 suppléments et les rapports. Il rejette 14 reçus corrompus, sans compilateur ni nouvelle exécution native. Les erreurs préparatoires de tests restent dans les preuves, sans être comptées comme des succès.

Les **17 modes Apple globaux inchangés** conservent leurs programmes exacts ; les **16 modes Apple historiques plus anciens** restent une catégorie distincte. Les neuf anciens modes dont les programmes changent sont remplacés. Le prochain Core explicitement demandé exécutera uniquement **11 modes Apple** : ces neuf remplacements et les deux nouveaux contrôles lookup. Aucun ancien programme inchangé ni CMake n’est rejoué. Le nouveau gate reconstitue le Core de référence, authentifie les 269 entrées et les rapports de son préflight, et compare les programmes des suites conservées. Les changements de hash de fichiers entiers hors programmes MFC/viewport sont documentés.

La compilation Apple du nouveau lot reste **à faire sur autorisation**. Le Core vérifié précédent reste disponible pour ses entrées historiques ; il ne contient pas ces trois changements et ne doit pas être présenté comme leur binaire. Aucun numéro de livraison n’est réservé.

## Jeux et prochaines étapes

**BO2 :** les 46 adresses de modules fragment des longues créations 594 sont distinctes. Le cache déjà corrigé et ses clés nécessaires sont préservés ; aucune compilation redondante réellement établie n’a été trouvée dans ces preuves. Le présent lot réduit un coût de binding récurrent, sans supprimer les premières compilations Metal ni prouver la correction des armes/avant-bras. Prochaine piste : corréler contenu normalisé, variante et réutilisation d’une même bibliothèque avant toute déduplication supplémentaire.

**Assassin’s Creed :** aucune compilation graphique dans l’intervalle étudié ; les coûts textures/soumissions restent pertinents. Les stages d’attente des uploads et les transitions BX2/vues/filtrage du Core précédent restent exacts. La scène des torches doit être rejouée sur GPU avec le nouveau Core avant de conclure sur le flickering.

**GOW3 BCES00510 :** conserver WCB, les readbacks nécessaires et les réglages établis. Les 306,559 Go de hashes 594 incluent le worker ; les 1 491 readbacks ne deviennent pas évitables avec un lookup plus court. Le gain de validation dépend encore des plages réellement répétées. Le gel signalé reste sans cause démontrée, distinct du snapshot BO2 pendant les compilations. Prochaine piste : coût réel du chemin MFC complet sur ARM64 et fréquence des misses/hits dans une même scène GOW3, sans forcer de label ni sauter d’attente.

**Budokai :** l’early-submit déjà mesuré reste inchangé. Aucun nouveau contournement par titre, changement NEON/LLVM, cache permanent, allocation persistante, réglage joueur ou télémétrie applicative n’est ajouté.

Les limites de fabrication déjà signalées restent ouvertes : minos du dylib 16.3 contre appels os_sync_* requérant 17.4, et avertissements ranlib LLVM22/AppleLLVM17. Aucune recette de dépendance n’est changée dans ce lot. Les sources et preuves MeloNX/Core84/timer ainsi que l’IPA594 restent préservées.
