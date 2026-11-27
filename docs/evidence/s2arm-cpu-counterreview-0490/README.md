# S2Arm — contre-expertise CPU complémentaire du 27 novembre 2026

Base RewindBox `5ed52e8d92a56e3099297ffef338b287075724e7`, moteur `6b6a5715`, patchs CPU 0472–0476, 0479, 0480 et 0484 relus. Aucune nouvelle erreur démontrée dans le bitmap des pages, le saut des blocs vides ou l’allocation des handles. Les nouveaux défauts ci-dessous préexistent à ces optimisations.

| Patch | Cause et résultat vérifié sur hôte |
| --- | --- |
| 0490 | `CreateThread` relâchait le verrou après le contrôle du quota. 100 courses forcées donnaient 607→609 threads ; le correctif donne 607→608, un succès et un refus `0x10801`. L’allocation refusée et l’échec de condition renvoient `0xCE01`, sans handle ni objet publié. |
| 0491 | Les lectures de l’usage et du pic n’étaient pas protégées contre les écritures. Avant : 10/10 lectures voient l’état intermédiaire 32 Kio pendant l’écriture verrouillée ; après : 10/10 attendent et voient 64 Kio. 33 cas d’API et erreurs conservés. |
| 0492 | Repli oublié : `S2A_RB_TMEM_COUNT=0` rétablit le scan sans désactiver quota ni garde 0480. 1 941 cas par mode, même résultat et même suffixe de prêt/attribution. |
| 0493 | Repli oublié : `S2A_RB_SESSION_SCAN=0` rétablit le modulo historique. 102 500 opérations séquentielles et 128 000 cycles concurrents par variante, mêmes cookies et fermetures. |
| 0494 | Même absence de verrou dans les relevés mémoire de `GetInfo` et `GetSystemInfo`, avec deux lectures distinctes pour la mémoire libre. Instantanés protégés et lecture unique : 657 cas fonctionnels et 20 lectures concurrentes passent après correction. |

Les bancs extraient les fonctions ou branches réelles depuis les sources du moteur. Dépendances mémoire et handles remplacées par des substituts, concurrence pthread réelle ; aucune opération Mach ni création de thread invité complète. Linux x86-64, GCC 14, ASan et UBSan sur les reproductions natives ; fuites non vérifiées. Les mesures de sessions sont synthétiques et ne chronomètrent aucune requête IPC complète.

Les correctifs de sûreté 0490, 0491 et 0494 restent actifs dans tous les modes ; les interrupteurs ne réactivent que les algorithmes de recherche précédents. La réserve JIT et les fichiers graphiques ne changent pas dans ce lot. Sauvegardes et caches du joueur préservés. [Compilation iPhoneOS réussie](https://github.com/TarbleFR/RewindBox/actions/runs/46021383946) sur macOS 15 et 26, source `7c476455` ; aucune IPA. FPS, mémoire physique, chauffe et consommation sur iPhone non mesurés ; estimation maintenue à 50 %.

## Vérification du repli des sessions

NativeAOT .NET 10.0.15 sur Linux x86-64, six paires alternées. Médianes en ns par ouverture/fermeture :

| Sessions préexistantes sur 1 024 | Référence 0479 | Repli `0` | Défaut `1` |
| ---: | ---: | ---: | ---: |
| 0 | 24,61 | 25,64 | 23,99 |
| 512 | 25,82 | 27,65 | 24,09 |
| 1 023 | 651,54 | 1 870,81 | 623,26 |

Aucune régression du chemin par défaut détectée sur ces charges. Ce contrôle mesure le coût du commutateur et le repli historique, sans établir de gain additionnel en jeu. Le digest séquentiel des trois variantes est `ff0c3dcacbd556bc`, avec croissance de 1 024 à 4 096 emplacements. Le comptage des handles donne `374107a08eb53937` pour les deux modes.

## Reproduire

`thread_create.py --source SOURCE_THREAD_C --output SORTIE_C` extrait le préfixe de création ; compiler avec `cc -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -pthread`. Le binaire sans argument rejoue les courses ; arguments `1` et `2` injectent les échecs d’allocation et de condition.

`memory_resource.py` et `memory_info.py` prennent `--reference SOURCE_MEM_AVANT --candidate SOURCE_MEM_APRES --output DOSSIER` ; compiler les C produits avec les mêmes options, avec `-DFIXED` pour le candidat. `memory_info_main.inc` accompagne son générateur.

`check.py` et `native.py` prennent `--reference DISPATCHER_AVANT --candidate DISPATCHER_APRES --output DOSSIER --dotnet DOTNET` ; `native.py --help` décrit le remplacement local facultatif de la tâche MSBuild. `tmem.py` prend les mêmes arguments de sources pour `thread.c`, sans `--dotnet`. Les références sont les fonctions avant le patch concerné. Les fichiers JSON conservent les résultats, conditions et limites des exécutions. `source-proof.json` vérifie les trois sources finales contre le pin et les patchs pertinents.

[Reçu CI](ci.json) : `t_svc_mem 213/213`, `t_far 111/111`, fixture pthread QoS réussie, 153 exports, aucun symbole hôte manquant. Aucun nouvel avertissement CPU par rapport au run 46012990218. Ce reçu porte sur le lot 0490–0494, distinct des ajouts RAM ultérieurs.
