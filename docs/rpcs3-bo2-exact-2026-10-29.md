# RPCS3 : accès direct aux textures et clés de framebuffer — 29 octobre 2026

Ce cycle prolonge les corrections BO2 de `a732853d` et le lot récurrent
`64ca0a0`, dont le reçu source est conservé dans `6d80aaa`. Deux chemins
moteur changent : la recherche des textures non compressées et la construction
de la clé des framebuffers Vulkan. Les changements sont dans le patch
canonique unique ; aucune nouvelle étape de patch historique n'est ajoutée
à la fabrication du moteur.

Les preuves ci-dessous concernent les corps de production exécutés sur hôte.
L'IPA 593 demeure la version livrée. Aucun nouveau Core Apple, IPA ou release
n'est produit par ce cycle, et aucun gain de FPS sur iPhone n'est mesuré.

## Pourquoi ce chemin

Les fenêtres BO2 9, 11 et 12 des journaux de l'IPA 593 représentent 582 frames
RSX, dont 72 échantillonnées. La préparation des textures y prend en moyenne
4,569 à 5,717 ms par frame échantillonnée selon la fenêtre. Cette observation
justifie l'examen des recherches répétées, mais ne permet pas d'attribuer ce
temps à une fonction précise : les journaux ne donnent ni distribution des
tailles de blocs ni proportions de hits compressés/non compressés.

Les faits déjà extraits sont réutilisés dans
[existing-log-facts.json](evidence/rpcs3-bo2-warm-20261029/existing-log-facts.json).
Le présent travail n'ajoute pas de télémétrie. Les longues premières
compilations Metal restent un problème distinct de ces coûts récurrents.

## 1. Recherche exacte des textures non compressées

Dans `fast_texture_search()`, le parcours précédent visitait les sections
chevauchant une plage et constituait progressivement `overlapping_locals`
avant de trouver une correspondance exacte. L'index d'adresses du cycle
précédent était utilisé uniquement pour les textures compressées.

Pour un bloc de plus de 16 sections, lorsque la plage est valide et commence
à l'adresse demandée, le nouveau chemin consulte cet index existant. Il
examine uniquement les sections de même adresse, dans leur ordre d'origine.
Un succès évite le parcours des autres sections et la constitution de la
liste des chevauchements. Le stockage `simple_array` possède huit entrées
internes : seules les listes qui dépassaient cette capacité pouvaient allouer.
Il serait donc incorrect de compter une allocation supprimée pour chaque hit.

Le chemin conserve les contrôles locked/dirty, le contexte, le pitch, le
format, les dimensions, la validation du contenu et le contrôle de swizzle.
Les vérifications `TEXTURE_CACHE_DEBUG` et le retour d'une vue nulle sont
également préservés. Les petits blocs et les plages qui ne satisfont pas
les gardes conservent textuellement l'ancien parcours, avec le test de garde
supplémentaire.

Cette utilisation de l'index repose sur le verrou lecteur déjà détenu par
`upload_texture()` et ses recherches de mipmaps. Les sections `unowned`, qui
commencent dans un bloc précédent, ne peuvent pas avoir la même adresse de
base. Le chemin `find_cached_texture()` n'est pas modifié : ses appelants
ne fournissent pas tous la même garantie de verrouillage.

### Repli exact après une invalidation

Un premier prototype a échoué au test différentiel. `simple_array::erase_if()`
échange une entrée retirée avec la dernière entrée ; retirer plus tôt un
candidat devenu dirty changeait donc l'ordre de fusion et des validations.

La version finale retient les seuls candidats exacts invalidés et les replace
à leur position historique avant cet effacement. Un curseur suit leur ordre,
sans recherche quadratique. Le repli inclut les sections déverrouillées
uniquement lorsque ces candidats doivent être conservés. Aucun état mémoire
réel n'est restauré et aucune validation obligatoire n'est supprimée.

### Vérification et coût observé

Les tests exécutent les véritables classes de stockage, index, plages,
correspondances, pitch, callbacks et tableau dynamique. Les ressources GPU et
le hachage de la mémoire invitée restent des frontières adaptées à l'hôte.
Les deux versions utilisent le même stockage restauré entre les requêtes,
ce qui conserve aussi l'ordre réel de l'ensemble `unowned`.

Clang 22.1.8 en `-O3` et GCC 13.3 sous ASan/UBSan passent **13 492 requêtes**,
dont **3 365 en mode debug**, et **4 036 mutations**. Le premier résultat,
l'ordre complet des validations et du merge, la vue sélectionnée et les états
dirty/locked/confirmed/last-use sont identiques. Les tests couvrent les
doublons d'adresse, les changements de plage sans ressource, les différences
de format/pitch/swizzle, les overlaps interblocs, le clear/recyclage, plus de
huit invalidations exactes successives et un succès tardif après celles-ci.

Médianes de sept répétitions sur hôte x86_64, nanosecondes par recherche :

| Sections | Hit uniforme avant → après | Miss avant → après | Premier slot avant → après |
|---:|---:|---:|---:|
| 8 | 29,35 → 30,78 | 29,22 → 28,66 | 18,97 → 20,27 |
| 16 | 54,31 → 55,82 | 69,71 → 72,89 | 28,41 → 29,66 |
| 17 | 33,92 → 19,88 | 46,43 → 73,63 | 27,89 → 32,18 |
| 64 | 89,81 → 22,74 | 141,77 → 160,53 | 17,03 → 18,80 |
| 256 | 304,35 → 26,87 | 589,81 → 662,85 | 16,55 → 24,64 |
| 1 024 | 1 169,35 → 47,43 | 2 374,09 → 2 323,99 | 31,36 → 41,86 |

Avec un préfixe de 64 chevauchements, le hit passe de **539,32 à 18,14 ns**.
Les appels d'allocation/réallocation de `simple_array` passent de **4 000 à
zéro pour 1 000 hits**, soit 1 536 000 octets de demandes d'allocation évitées
dans cette charge. Ce volume n'est ni un pic de RAM ni une économie de
footprint sur iPhone. Aucun index persistant supplémentaire n'est ajouté.

Le compromis est visible : les succès dispersés dans un bloc dense coûtent
moins cher ; certains misses et succès au premier slot coûtent davantage.
Le bruit des mesures hôte et la distribution inconnue dans BO2 interdisent
de convertir ce tableau en gain net par frame ou en pourcentage de FPS.

Preuves finales :
[texture-exact-clang.json](evidence/rpcs3-bo2-exact-20261029/texture-exact-clang.json)
et [texture-exact-asan.json](evidence/rpcs3-bo2-exact-20261029/texture-exact-asan.json).

## 2. Clé déterministe pour les framebuffers

Dans `VKFramebuffer.cpp`, le constructeur de `framebuffer_storage_key`
initialisait largeur, hauteur et présence d'attachements en entrée, soit
33 bits, puis utilisait l'entier complet de 64 bits comme clé du cache.
Les 31 bits restants n'étaient pas définis par le constructeur.

La branche iOS initialise maintenant explicitement l'entier complet. Le
masque du flag conserve exactement la troncature historique sur un bit.
Les deux surcharges de `get_framebuffer`, les comparaisons d'attachements,
les verrous, les références, les invalidations et les destructions restent
inchangés. Les chemins concernés sont utilisés pour les cibles de rendu,
les overlays et la présentation.

Le véritable type est construit dans une mémoire préremplie de 256 motifs.
Avec Clang 22 à `-O3`, les 405 combinaisons de paramètres révèlent la
dépendance de l'ancienne clé aux octets préexistants. Pour les mêmes paramètres
`1280 × 720, input=0`, le test produit **256 clés avant, une seule après**.
Ce résultat mesure la fragmentation possible de la clé, pas la fréquence
des misses dans un jeu. GCC 13 à `-O3` choisissait déjà des bits supérieurs
nuls dans une exécution intermédiaire ; aucun gain n'est déduit de ce cas.

Les rapports finaux Clang et GCC ASan/UBSan couvrent **103 936 constructions
par version**, **1 026 recherches**, **1 011 hits**, **15 créations et
15 destructions**, les deux surcharges, les invalidations ciblées et la
conservation des références. Le vrai `ref_counted` est extrait : son
post-incrément entraîne l'expiration au troisième contrôle sans référence.
Les appels Vulkan sont des adaptateurs hôte. LeakSanitizer est désactivé
dans cet environnement ; ASan et UBSan sont actifs dans le mode instrumenté.

Preuves finales :
[framebuffer-key-clang.json](evidence/rpcs3-bo2-exact-20261029/framebuffer-key-clang.json)
et [framebuffer-key-asan.json](evidence/rpcs3-bo2-exact-20261029/framebuffer-key-asan.json).

## Intégration et continuité

Le patch canonique couvre **313 fichiers**. Par rapport au lot précédent,
311 postimages sont identiques, une est modifiée (`texture_cache.h`) et
`VKFramebuffer.cpp`, déjà présent en amont, entre dans le delta. Une nouvelle
matérialisation depuis l'amont authentifié `22f1152783cef1f7e04af7b1c895173e28fd5b03`
reproduit chaque octet des 313 sources revues. Les branches hors iOS restent
identiques.

La fixture `test/fixtures/rpcs3_bo2_exact_20261029.diff` sert à reconstruire
les préimages pour les tests ; elle s'inverse avant les fixtures plus anciennes.
La compilation continue d'utiliser le seul `embedded-core.patch`.

La gate Apple existante partage désormais explicitement son pipeline avec
le nouveau delta, sans duplication ni remplacement dynamique de fonctions.
Le contrat rassemble 190 entrées et préserve les programmes des tests
antérieurs à l'octet. Un futur Core demandé exécutera les vingt modes encore
en attente sur Apple et les quatre nouveaux modes ; les suites du Core
historiquement livré ne sont pas rejouées ici.

Les identités PPU `a987639e9f838d1c`, SPU `d070cb361bdef607`, ABI 30 et
88 exports sont conservées, ainsi que les corrections CPU-write/samplers,
compilation, index compressé, viewport/scissor et notifications précédentes.
Le candidat MeloNX engine 81 reste inchangé. La reconstruction et les résultats
sont liés aux sources exactes dans
[canonical-integration.json](evidence/rpcs3-bo2-exact-20261029/canonical-integration.json)
et le reçu de contrat commis du même répertoire.

```text
Patch SHA-256   d7e8921e513dcb7caaf90ef6f903b1f9a28eb749b41fa668762304d90f876b2d
Fixture SHA-256 634375a7e51f7ce05ef840dfde32f8a28d67e9774f18495c2f6a51ebf205dd26
Texture SHA-256 1ee38e8848f5100263165ab77df3eb1d856d732256fe64bb0bdbcd970fb08347
```

La fréquence des misses FBO sur iPhone, le gain net BO2 et l'effet sur les
artefacts des armes demandent encore une mesure du candidat sur appareil.
Ce cycle ne constitue pas non plus une preuve de correction du gel GoW3 ni
de disparition des premières compilations Metal.
