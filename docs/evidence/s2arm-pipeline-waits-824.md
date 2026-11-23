# Attentes de pipelines à la première utilisation (IPA 824)

Session Mario Kart World sur l'IPA 824 (journal `c758810c`, moteur 0001–0311). La session a construit 576 pipelines à la demande, pour 7 221,5 ms d'attente du fil de soumission. Lecture seule du journal, comparée à quatre sessions antérieures (22 et 23 novembre).

## Où passe le temps

| Groupe | Pipelines | Attente |
|---|---|---|
| Constructions de 50 ms ou plus | 8 | 5 369 ms (74 %) |
| dont l'attente de l'image 1010 (40 s de session) | 1 | 3 822,6 ms |
| dont la rafale des images 477–487 | 7 | 1 546 ms |
| Moins de 1 ms (trouvés dans l'archive) | 367 | — |
| De 5 à 20 ms | 85 | 1,0 s |

- `pso_reference.tsv` commence par `# RewindBox reference` : toute première utilisation est exacte et obligatoire, donc attendue sans limite. Le saut à la première utilisation et les limites `DM_NVN_PSO_WAIT*` ne jouent pas pour Mario Kart World. Aucun dessin n'a été sauté.
- Images 300 à 600 : 354 premières utilisations, 2 798 ms d'attente.

| Clés | Nombre | Attente | Préparables d'après les enregistrements ? |
|---|---|---|---|
| Jamais vues | 106 | 1 857,5 ms | non |
| Déjà attendues dans une session antérieure | 47 | 254 ms | oui, enregistrées mais pas atteintes |
| Déjà préparées dans une session antérieure | 201 | 686,5 ms | oui, enregistrées mais pas atteintes |

- Les 248 clés enregistrées n'ont pas été atteintes à temps à cause de l'ordre du préchauffage. Les lignes de l'historique des dessins passaient après les lignes de `pso_user.tsv`, dans l'ordre du dictionnaire (hachage). Les lignes déjà attendues au-delà des 64 premières passaient en dernier, alors que le journal annonçait « previous waits scheduled ahead of the generic list ».
- L'attente de 3,8 s (image 1010) :
  - pas de compilation de bibliothèque de shaders, pas d'attente derrière une autre construction, pas de verrou, pas d'entrées-sorties (61 lectures de pages) ;
  - cause la plus probable : une compilation à froid dans le service de compilation d'Apple (archive manquée) ou une construction bloquée sous la pression mémoire de Metal (8 983 Mo alloués pour 5 461 Mo recommandés à l'image 1018) ;
  - le journal ne permet pas de trancher : il n'a pas de résultat d'archive par clé, et la ligne détaillée n'est écrite que pour les attentes 1 à 64 puis aux puissances de deux.

## Patch 0313

- **Ordre de la liste générique du préchauffage** (`rb_warm_order.h`, en C pur), uniquement dans une session qui a un historique des dessins :
  1. les lignes de calcul et de maillage, dans l'ordre de la liste ;
  2. les lignes que l'historique a enregistrées, triées par image du premier dessin (la plus petite de ses deux traces), puis par plus longue attente enregistrée ;
  3. toutes les autres lignes, dans l'ordre de la liste.
  - Le tri est stable : deux lignes à égalité gardent l'ordre de la liste.
  - Les lignes déjà attendues au-delà des 64 premières prennent leur rang parmi les lignes enregistrées, au lieu de passer en dernier.
  - Une ligne de journal `RewindBox (patch 0313): generic prewarm list by recorded first use: …` donne les trois groupes et l'intervalle d'images.
  - `S2A_RB_WARM_FIRST_USE=0` rétablit l'ordre précédent.
- **Journal des longues attentes.** Toute attente d'une seconde ou plus pour un pipeline de la table est désormais écrite, sans limite de nombre : `【红】 RewindBox (patch 0313): long pipeline wait #N`. La ligne dit si la construction a trouvé le pipeline dans une archive, l'a compilé (avec le temps passé dans le compilateur) ou a attendu la même construction sur un autre fil. Elle donne aussi la durée de la construction et son début par rapport à l'attente. La ligne `first-use wait` est écrite elle aussi pour toute attente d'une seconde ou plus.
- **Gain attendu, non mesuré :**
  - environ 0,9 s d'attente en moins entre les images 300 et 600 (les 248 clés enregistrées), et peut-être l'attente de 3,8 s si sa construction était adossée à l'archive ;
  - rien pour les 106 clés jamais vues, qui demandent les pipelines hybrides de l'amont (hors de portée : traducteur et paquets à refaire).
- **Risque :** les mêmes lignes et les mêmes portes thermiques, seul l'ordre change ; le journal n'ajoute que quelques lignes par session.
- **Test :** `t_rb_warm_order`, en C pur, dans la liste des tests C purs de la CI. Il vérifie la forme de la session 824, la stabilité, les listes vides et un mélange de 9 018 lignes (permutation, groupes, tri). Il passe en local avec gcc, clang et les sanitizers.

## Laissé de côté, avec la raison

- **Laisser passer sous la retenue Fair les lignes adossées à l'archive :** gain incertain (0,3 s, plus l'attente de 3,8 s seulement si elle venait de l'archive). Le journal du patch 0313 le dira d'abord.
- **Démarrer tout de suite une ligne promue au moment du bind :** 0,1 à 0,3 s, à mesurer d'abord.
- **Limite extérieure pour une attente obligatoire** (l'amont `f432e0cc6` + `f74a47f7d` le fait pour le calcul) : seulement contre un service de compilation bloqué, et une attente de 60 s est déjà un gel pour le joueur.
- **Plafond de l'historique des dessins** (16 384 recettes ; la session en tient 5 138) : pas atteint.
- **Amont `2d4c5aa34`** (bibliothèques préparées dès `ProgramSetShaders`) : il compilerait toutes les clés tôt, ce que le patch 0311 a mesuré comme nuisible.
