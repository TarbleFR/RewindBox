# Clippings noirs fugaces (IPA 824) et textures partagées

Session Mario Kart World sur l'IPA 824 (journal `c758810c`, moteur 0001–0311, 9 000 images). Le joueur voit en course des zones noires brèves qui disparaissent seules, trop rapides pour être filmées. Le journal ne donne pas l'instant où elles apparaissent : ce qui suit relie ce symptôme aux compteurs de la session, sans preuve image par image.

## Écarté par le journal

| Piste | Ce que le journal montre |
|---|---|
| Dessins sautés faute de pipeline ou de shader | `draws_skipped_pso` et `draws_skipped_shlib` à 0 dans les 30 fenêtres et les 368 lignes par image ; aucun message de saut à la première utilisation, ni « encore en compilation », ni « budget épuisé » |
| Image isolée (liste de dessins ou de passes différente de ses deux voisines) | aucune alerte du détecteur de signatures (patchs 0059–0067) sur toute la session |
| Textures creuses | 0 tuile non attribuée lue, 0 récupération, 0 rechargement |
| Textures envoyées en retard | sondes de demande sans repli (`0 fallbacks`), pages absentes lues de façon bloquante avant l'envoi |
| Élision des chargements et sauvegardes d'attachements | 0 sauvegarde scellée ou élidée |
| Résolution dynamique | la scène reste à 1248×700 pendant les courses |

## Ce qui reste : du contenu dessiné par le GPU perdu au partage d'un stockage

Mario Kart World pose plusieurs objets texture sur la même mémoire. Le moteur leur donne une seule texture Metal quand leurs clés (pool, décalage, description) concordent. Une clé différente au même endroit est traitée comme une autre texture qui écrase ce stockage : l'objet qui perd sa texture la refait à son prochain usage, et ce que le GPU y avait dessiné se relit comme zéro, donc noir, jusqu'à ce que le jeu le redessine.

| Compteur (session 824) | Valeur |
|---|---|
| Reprises de stockage | 2 659 en tout, dont 2 655 d'objets encore vivants (728 avant la première course) |
| Textures partagées libérées comme non référencées | 157 (271 Mo), toutes écrites par le GPU |
| Écritures du GPU dans des textures embarquées | 154 |

Le dépôt amont S2Arm a corrigé ces mécanismes entre le 18 et le 22 novembre (tickets #427 et #674) ; notre moteur, épinglé sur `6b6a5715`, n'avait aucun de ces correctifs :

- `5863a69cf` : dans la clé, un nombre d'échantillons de 0 vaut 1 (deux objets d'une même mémoire devenaient deux textures, l'une jamais écrite) ;
- `cb6853c50` : dans la clé, la disposition embarquée et `MINIMAL_LAYOUT` sont remplacées par la disposition des blocs qu'elles produisent ;
- `50f032a62` : une texture qu'un identifiant de texture enregistré lit encore n'est pas libérée comme orpheline.

## Patch 0312

- Clé normalisée comme en amont, à partir de la disposition déjà calculée à l'initialisation de la texture (`t->L`), sans calcul supplémentaire par dessin. `S2A_RB_ALIAS_LAYOUT_KEY=0` rétablit l'ancienne clé.
- Le passage des orphelines et la restitution d'adresses gardent les textures que lit un identifiant enregistré : sa vue, les vues faites pour un autre type, l'alpha depuis le rouge ou une classe d'image, et leurs textures de base. `g_rmu` est pris avant `g_smu`, comme partout. `S2A_RB_ORPHAN_ID_HELD=0` rétablit l'ancien comportement.
- Journal : `[alias] near-miss` pour deux clés qui commencent au même stockage (champs qui diffèrent ; les 32 premières, puis aux puissances de deux) et une ligne `RewindBox (patch 0312): …` quand ses compteurs bougent.
- La normalisation de la clé est dans `rb_alias_key.h`, en C pur, et `nvn_mtl.m` l'appelle.
- Tests :
  - `t_rb_alias_key` (C pur) vérifie 8 cas. Les échantillons 0 et 1 donnent la même clé. Une disposition embarquée qui retombe sur la même hauteur de blocs aussi. Une hauteur de blocs différente donne une autre clé. `MINIMAL_LAYOUT` prend la clé automatique en 1920×1024 et la clé à blocs d'un GOB en 1920×1080. L'alignement de largeur embarqué reste dans la clé, comme la profondeur de blocs en 3D. Les textures linéaires et les tampons gardent leur description. Le format, la taille, les niveaux et la cible séparent toujours deux clés. Une seconde normalisation ne change rien. Il passe en local avec gcc, clang et les sanitizers d'adresses et de comportement indéfini, et il tourne dans la liste des tests C purs de la CI.
  - `t_nvn_alias_orphan` ⑤ (échantillons), ⑥ (identifiant enregistré, puis contre-épreuve après désenregistrement) et ⑦ (disposition des blocs), en Metal 4 et Metal 3, ne tournent que sur un Mac réel. Sur le GPU virtuel des machines de la CI, `mtl_init` s'arrête à la création du `MTLResidencySet` (run 45150625321) ; ce test est donc retiré de l'étape GPU.
- Compilation iOS du patch vérifiée (job macos-15 du run 45148099154).

Non porté, avec la raison :

- l'enregistrement des textures embarquées écrites par le GPU (`cb6853c50`) : l'amont a dû le corriger le lendemain (`648f62063`, texture sortie du jeu de résidence alors qu'elle restait lue) ;
- la réécriture dans le pool avant une éviction sous pression d'adresses (`0080169b7`) : aucune éviction de ce type dans cette session ;
- la copie à l'écriture des tables de pool de textures (`cecb3edcd`) : Mario Kart World ne passe pas par ces tables (aucune ligne `pool tables`, profil `bindless=0`).

## Limites et lecture du prochain journal

Rien n'est mesuré sur iPhone. Le lien entre ces reprises de stockage et les clippings vus en jeu reste une hypothèse. Dans le prochain `host.log`, comparer avec la session 824 :

- `evicted with pools …, on storage takeover N (live objects that lost theirs N)` : 2 659 et 2 655 sur l'IPA 824 ;
- les lignes `[alias] near-miss` : les champs qui séparent encore deux clés d'un même stockage ;
- la ligne `RewindBox (patch 0312): …` : passages qui ont gardé une texture lue par un identifiant, et nombre de quasi-collisions.

## IPA 825 : flash noir et récupération GPU

Vidéo de 7,45 s et journal `de0a5911`. L'enregistrement commence à l'image 6 543 (197,25 s).

- **Ce que montre la vidéo.**
  - Entre 2,78 et 3,47 s, 8 images noires alternent avec des images normales.
  - Sur une image noire, la scène éclairée a disparu (sol, kart, personnage, décor). Le ciel reste visible mais plus sombre, avec les silhouettes du décor. Les flammes, les traits de vitesse et le HUD sont intacts.
  - De 4,87 à 6,73 s, l'image est figée (écart moyen entre images de 0,02 à 0,3 sur 255), puis l'écran s'assombrit jusqu'à la fin.
- **Ce que montre le journal.**
  - Les images 6 544 à 6 566 durent 55 à 108 ms. L'image 6 568 dure ensuite 10,09 s : de l'image 6 550 à l'image 6 574, l'horloge du jeu avance de 11,6 s.
  - Le moteur reçoit alors 5 erreurs de tampons de commandes, toutes « Discarded (victim of GPU error/recovery) » (`kIOGPUCommandBufferCallbackErrorInnocentVictim`).
  - Aucun tampon du moteur ne porte d'erreur de blocage, de délai ou de faute de page. Sinon le moteur se serait arrêté par sécurité (`mtl_gpu_cb_error`), ce qu'il n'a pas fait. Le travail fautif n'est pas identifié : rien n'exclut qu'il vienne d'un autre processus.
  - L'image figée de la vidéo correspond à ce blocage. L'alignement exact entre les images de la vidéo et celles du journal reste incertain de quelques secondes : le flash précède le gel d'environ 1,4 s, sans que le journal dise ce qui l'a produit.
- **Pas introduit par 0312–0318.**
  - La même récupération apparaît dans la session 824 (`c758810c`, vers l'image 6 832, 15 tampons rejetés comme victimes, sans enregistrement d'écran) et le 16 novembre (`801d9562`).
  - Les sessions 822 (`549fdcf9`, 7 800 images), 823 (`f909c983`, 22 200 images) et la relance 825 (`b7d5aa42`, 11 100 images) n'en ont aucune.
- **Écartés par le journal :**
  - saut à la première utilisation : `draws_skipped_pso` et `draws_skipped_shlib` à 0 dans toutes les lignes ;
  - attachements non chargés : aucune erreur de prévision (`not loaded but written`) ;
  - drapeaux `gpu-pass` : sans effet, mode tuiles coupé ;
  - préchauffage : il ne tourne plus pendant les courses.
- **Juste après la récupération (images 6 572 à 6 585, après la fin de la vidéo).**
  - La scène change de taille : 1 248×700, puis 1 268×712, 1 276×716, puis retour à 1 248×700.
  - L'image 6 572 porte 52 conditions au lieu de 8, dont 31 effacements écartés.
  - La passe principale est coupée en deux aux images 6 575, 6 580 et 6 585.
- **Signatures image par image (`frames.txt` de la même session).**
  - Le blocage se place entre l'image 6 567 et la suivante : 10 080 473 µs avant la première commande de l'image 6 568.
  - Les images 6 528 à 6 567 ont des listes normales : 1 087 à 1 362 dessins, 133 passes (139 tous les 51 images environ), aucun dessin sauté, 8 conditions sauf aux changements de taille de la scène (29 à 52 conditions, dont 14 à 31 effacements écartés, aux images 6 528, 6 530, 6 531, 6 572, 6 574, 6 575, 6 578 et 6 579). Rien dans le flux de commandes ne marque une image noire.
  - Durée GPU rendue au jeu : 33 à 42 ms par image de 6 528 à 6 567, puis 10 à 16 ms dès la reprise (16 180, 11 114, 10 782, 10 036, 10 136 µs), puis le plancher de 16,6 ms du maintien. La charge est la même (1 062 à 1 410 dessins, scène 1 248×700). Le GPU était donc ralenti, pas surchargé, et la réinitialisation l'a rendu rapide.
  - Session 824 : même enchaînement, avec un verrou à 30 avant la récupération (fenêtres 5 701–6 600, 27 à 28 images par seconde) et 57 à 58 images par seconde juste après (6 901–7 800).
- **Suite :**
  - savoir si les flashs arrivent aussi sans gel ;
  - à la prochaine récupération, consigner l'état de chaque encodeur des tampons rejetés et la liste des tampons en vol, pour désigner le travail fautif.
