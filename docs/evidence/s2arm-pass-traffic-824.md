# Trafic mémoire des passes de rendu (IPA 824)

Session Mario Kart World sur l'IPA 824 (journal `c758810c`, moteur 0001–0311, A18 Pro). Le journal donne environ 321 Mio chargés et 364 Mio stockés par image. Lecture seule, à partir du profil GPU par passe des images 2522 et 5642.

## Ce que le compte recouvre

L'essentiel de ce chiffre est de la comptabilité, pas du trafic réel.

| Poste (image 2522) | Chargé Mio | Stocké Mio |
|---|---|---|
| Atlas creux 6144² et ses niveaux jusqu'à 768² (4 passes, 2 dessins chacune) | 191 | 191 |
| Passe principale 1248×700 couleur + profondeur, 7,5 Mio par ouverture, ouverte 11 fois | 79 | 79 |
| Présentation et mise à l'échelle (1920×1080 ×2, 2560×1440) | 30 | 38 |
| Ombres 2048² D16 ×3 | 0 | 48 (24 en réalité : D16 compté à 4 octets) |
| Effets en demi et quart de résolution, flou lumineux | ~19 | ~25 |
| Passes de 512² ou moins | ~6 | ~8 |

- Les passes de l'atlas durent quelques dizaines de microsecondes : le GPU saute les tuiles sans géométrie et compresse les tuiles effacées.
- Le trafic réel est dans :
  - les passes qui couvrent tout l'écran (environ 150 Mio par image hors atlas) ;
  - la passe principale rouverte 6 à 11 fois par image ;
  - les copies de la profondeur échantillonnée dans sa propre passe, 4 à 6 par image, qui ne figurent pas dans ce compte.
- Le mode tuiles (TBDR) est coupé pour les titres hébergés (patch 0296). Les économies qui en dépendent ne jouent donc pas, et les drapeaux NVN2 (`store`, `liveness`, `producer`…) ne trouvent aucun cas.

## Patch 0314 (amont S2Arm `864e92cf1`)

- **Ce qui change.** Avant, toute écriture de stencil rendait périmée la copie de la profondeur qu'un dessin échantillonne dans sa propre passe. Désormais, elle ne la rend périmée que si cette copie est lue par une vue stencil, et seulement quand une opération de stencil n'est pas KEEP.
- **Pourquoi.** Une passe d'éclairage différé dessine un volume de lumière par dessin, avec le test de stencil actif et sans écriture de profondeur, chaque dessin échantillonnant la profondeur. Elle fermait la passe et recopiait toute la profondeur pour chaque lumière.
- **Mesuré par l'amont, pas par nous :**
  - en relecture d'image sur Mac : 194–196 passes ramenées à 69, plus de 100 copies de profondeur ramenées à 1, 0 pixel différent ;
  - sur iPhone : CPU 0,510 → 0,299 W, GPU occupé 763 → 518 ms/s, à 29,89 image/s inchangé.
- **Pour Mario Kart World :**
  - l'effet attendu est de 10 à 40 Mio par image, si ses dessins qui échantillonnent la profondeur écrivent du stencil ;
  - rien n'est mesuré ;
  - le compteur `same-pass depth sampling` et les réutilisations de copie du prochain journal le diront.
- **Mise en œuvre et retour arrière.** La règle est dans `rb_dsnap_rule.h`, en C pur. `DM_NVN_DSNAP_STRICT=1` rétablit l'ancienne règle.
- **Tests :**
  - `t_rb_dsnap_rule` (C pur) passe dans la liste des tests C purs de la CI ;
  - le cas amont de `t_nvn_feedback_snapshot` (deux dessins qui écrivent le stencil réutilisent la copie) est repris, mais ce test appelle `mtl_init` et ne tourne que sur un Mac réel.

## Pistes suivantes, non faites dans ce lot

1. **Continuer la même cible sans mode tuiles** (amont `fb96ab7db`, section 3, avec trois adaptations) : 30 à 75 Mio par image. Risque moyen : il faut une anticipation qui refuse la continuation dès qu'un dessin lit en bindless.
2. **`DontCare` au chargement quand le premier dessin couvre toute la cible, et plans de profondeur ou de stencil inutilisés laissés de côté, sans mode tuiles :** jusqu'à 30–35 et 5–20 Mio par image. Les deux preuves ne dépendent que de l'état du dessin, mais leur taux de réussite n'est pas connu.
3. **Zone de rendu bornée pour les très grandes cibles** (amont `f83afb3ef` + `f77af8a45`) : environ −100 Mio par image au compte, mais 30 à 150 µs de GPU seulement.
4. **Ne plus périmer la copie de profondeur à chaque changement de cible :** elle serait périmée aux dispatchs et aux copies vers texture. Ce n'est pas un correctif amont : il faut d'abord un compteur des causes.
5. **Comptabilité :**
   - `mtl_pf_bytes` ignore les formats de profondeur : les copies de profondeur sont sous-comptées d'environ 5 fois ;
   - `att_bytes` compte 4 octets par pixel par défaut ;
   - l'étiquette « shape » des refus de regroupement est la valeur zéro par défaut.
6. **À vérifier :**
   - les correctifs amont de couverture des effacements (`62f501d06`, `5f2e7cb94`) ;
   - la compression des textures D32S8 créées avec `PixelFormatView`.
