# Ordonnancement du préchauffage des pipelines

La simulation charge le véritable tri des recettes enregistrées du moteur. Le SHA-256 de rb_warm_order.h est `3fb98ca4818b6b86ad4c96ef9b1ac000aa889501da37218a7e2a4f90447316d7` aux points 0426, 0436 et 0447. Les recettes de rendu ont le même temps d’attente enregistré dans chaque groupe de même première image. Le candidat départage ces égalités en maximisant le nombre de nouveaux shaders vertex et fragment. Toutes les recettes et priorités entre groupes sont préservées.

Chacun des douze profils temporels est constitué de cinq créations de vrais pipelines Metal sur le Mac paravirtualisé. Les coûts de première utilisation des shaders sont pris dans la même paire pour chaque exécution simulée. Un pipeline déjà préparé est retrouvé sans nouvel appel pilote. Pour chacun des quatre ordres synthétiques de dessin, les deux variantes rencontrent exactement les mêmes recettes et les mêmes budgets de 4, 12 et 24 ms. Le modèle s’arrête avant une opération dépassant le budget. Il suppose ses coûts connus et exclut les coûts de planification, de concurrence, de rendu et d’accès aux fichiers.

| Ordre des dessins | Attente modélisée réduite | Identique | Augmentée |
| --- | ---: | ---: | ---: |
| Ordre prévu exact | 6 | 20 | 10 |
| Plusieurs fragments par vertex | 12 | 18 | 6 |
| Combinaisons croisées | 7 | 24 | 5 |
| Ordre de dessin dérivé d’un autre tirage | 7 | 22 | 7 |

Le pire surcoût modélisé est de 6,25 ms sur l’ensemble des premiers dessins. Le départage proposé est écarté. Les durées de construction sur le Mac sont mesurées. L’attente dans le jeu, la consommation et les FPS iPhone restent inconnus.

Pour reproduire les 288 lignes, exécuter `python3 replay_warm_order.py ARBRE stages-mac.csv nouveau.csv` depuis ce dossier. [Mesures du pilote](stages-mac.csv) et [résultats du modèle](order-model.csv).

Le second runner reconstruit les mêmes cinq classes de shaders et fournit douze nouveaux profils. Le même calendrier simulé gagne dans 30 scénarios, en perd 24 et donne 90 égalités. Le départage par nombre de shaders nouveaux reste écarté. [Coûts répétés](stages-repeat-mac.csv) et [calendriers répétés](order-model-repeat.csv).
