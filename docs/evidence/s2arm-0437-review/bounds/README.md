# Comparaison synthétique des tables de bornes

Le banc extrait les fonctions `len_fill`, `ubolen_vec4_cap` et `sbsz_bound` de deux arbres moteur, ainsi que leur code de réflexion commun. Il les compile avec Clang sous Linux et le runtime Objective-C GNU. Les liaisons sont créées par un générateur déterministe. Le substitut de tampon répond aux deux sélecteurs Objective-C et expose les mêmes adresses mises en cache par son arène.

Avec Python 3, Clang, GCC, le paquet de développement du runtime GNU Objective-C et `taskset`, lancer depuis ce dossier en donnant les deux arbres déjà préparés et un dossier de résultats.

```sh
python3 compare_ubolen.py /chemin/base /chemin/candidat resultats
python3 report.py resultats/forward.tsv resultats/reverse.tsv resultats/control.tsv
```

`--cpu N` choisit un cœur autorisé. Le banc vérifie sous ASan et UBSan, à chaque appel, l’égalité de l’adresse retournée et des 256 octets de la tranche correspondante, remplissage compris. Il compare 2 048 appels dans chacune des quatre charges, avec 14 slots, six stages, des bornes de fin de tampon variables, des pointeurs nuls, des longueurs extrêmes et une alternance d’arènes. La détection de fuites du runtime GNU est désactivée. Le bench vérifie également une somme des adresses et compteurs dans les séries chronométrées.

Les mesures utilisent le temps CPU du thread épinglé. Chaque fichier contient une paire de chauffe, puis 64 paires de 500 000 appels par variante et par charge. Les quatre colonnes indiquent la paire, la charge (0 à 3), la variante (0 pour la base) et les millisecondes. La première disposition place la fonction de référence avant le candidat, la deuxième inverse cet ordre. Le témoin compile deux fois la fonction de référence. Les quatre charges couvrent UBOLEN sans cache, SBSZ, UBOLEN avec cache stable et UBOLEN avec changements de taille et de disponibilité. Le rapport donne les médianes de temps et la médiane du ratio de chaque paire. Son intervalle non paramétrique nominal de 96,72 % suppose des paires indépendantes ; la charge d’un hôte partagé peut corréler plusieurs résultats. La dispersion du témoin et la sensibilité à la disposition du code doivent accompagner les gains. Le banc ne mesure ni la vitesse de jeu, ni l'énergie, ni un GPU.

Dans `ubolen_vec4_cap`, la division entière par 16 est monotone. La borne en vec4 vaut donc exactement `min(size + 15, cap, 65536) >> 4` pour un slot présent, avec la même addition non signée que dans la référence. Les deux fonctions calculent zéro pour une adresse nulle. Le GPU lit les mêmes tables aux mêmes adresses simulées. Le candidat utilise pour l'écriture les adresses CPU et GPU du tampon que `arena_new` a copiées lors de l'allocation. Le calcul, l'invalidation et l'activation optionnelle du cache de bornes gardent les conditions de la référence.
