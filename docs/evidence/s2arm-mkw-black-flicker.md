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
- Test : `t_nvn_alias_orphan` ⑤ (échantillons 0 et 1), ⑥ (identifiant enregistré, puis contre-épreuve après désenregistrement) et ⑦ (disposition des blocs), en Metal 4 et Metal 3, lancé par l'étape GPU des contrôles de shaders.

Non porté, avec la raison :

- l'enregistrement des textures embarquées écrites par le GPU (`cb6853c50`) : l'amont a dû le corriger le lendemain (`648f62063`, texture sortie du jeu de résidence alors qu'elle restait lue) ;
- la réécriture dans le pool avant une éviction sous pression d'adresses (`0080169b7`) : aucune éviction de ce type dans cette session ;
- la copie à l'écriture des tables de pool de textures (`cecb3edcd`) : Mario Kart World ne passe pas par ces tables (aucune ligne `pool tables`, profil `bindless=0`).

## Limites et lecture du prochain journal

Rien n'est mesuré sur iPhone. Le lien entre ces reprises de stockage et les clippings vus en jeu reste une hypothèse. Dans le prochain `host.log`, comparer avec la session 824 :

- `evicted with pools …, on storage takeover N (live objects that lost theirs N)` : 2 659 et 2 655 sur l'IPA 824 ;
- les lignes `[alias] near-miss` : les champs qui séparent encore deux clés d'un même stockage ;
- la ligne `RewindBox (patch 0312): …` : passages qui ont gardé une texture lue par un identifiant, et nombre de quasi-collisions.
