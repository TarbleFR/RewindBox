# BO2 : attentes de compilation et réutilisation des fragments — 29 octobre 2026

Ce candidat source prolonge les correctifs RPCS3 de `cf85c52e` / `7d1ca65c`.
Il est intégré après `cfba697b`, qui conserve le candidat MeloNX engine 81 et
son reçu Apple. Il modifie trois fichiers du Core :
`RPCS3IOSPerformance.cpp`, `ProgramStateCache.cpp` et `ProgramStateCache.h`.
Les treize fichiers du précédent correctif restent identiques.

Les journaux BO2 fournis proviennent de l’IPA 593, processus 47785 sur A18 Pro.
Ils ne testent ni le candidat `7d1ca65c`, ni les changements de ce document.
Aucun gain de FPS, disparition des saccades ou correctif visuel sur iPhone
n’est établi par les vérifications sur hôte.

## Ce que les journaux permettent de cibler

L’analyse réutilise les extractions déjà disponibles. Elle exclut les 3 488
premières lignes de `performance.1`, qui appartiennent à build 588/Bladestorm,
et les duplications des diagnostics et des milestones. Les références exactes
de fichier, ligne, fenêtre et heure figurent dans
[la corrélation détaillée](evidence/rpcs3-bo2-20261029/bo2-correlation.md) et
[ses données](evidence/rpcs3-bo2-20261029/bo2-correlation.json).

| Période observée | Résultat | Conséquence pour le travail |
|---|---|---|
| Phase SPU, session 2, fenêtres 7–13 | 6 221 lectures, 3 918,311 ms cumulées ; 128 codegens, 1 606,179 ms | Conserver l’optimisation des lectures déjà intégrée dans `7d1ca65c` et examiner séparément l’admission des compilateurs. `spu_build` inclut les lectures. |
| Rafale graphique, fenêtres 14–22 | 32 créations longues : 19 926,181 ms, sur 20 136,100 ms pour les 172 créations ; fragment : 15 750,841 ms | La première utilisation des shaders est une cause majeure des gros blocages de cette période. Les 32 paires de programmes sont distinctes ; aucune duplication exacte des compilations lentes n’est démontrée. |
| Fenêtres 9, 11 et 12 | 587 frames / 15,759493 s = 37,247 FPS ; 14 intervalles au-delà de 50 ms, aucun au-delà de 100 ms | Les petites saccades subsistent hors des grosses rafales. Il reste 176 lectures SPU ; cette sélection ne prouve pas une limitation GPU. |

Le premier appel graphique long commence dans la fenêtre 13 et se termine
dans la fenêtre 14. Les limites des compteurs ne coïncident pas avec chaque
frame. Dans la fenêtre 21, six appels occupent 3 654,210 ms d’une séquence
de 3 696,655 ms, avec un maximum de frame de 3 783,054 ms : cette concordance
est forte, sans donner une attribution individuelle de chaque appel.

Les 111 nouveaux programmes FP des fenêtres 19–20 coexistent avec huit
compilations de bibliothèque fragment et 115 succès de cache fragment. Les
compteurs sont distincts : on ne peut pas en déduire que précisément 103 des
111 programmes correspondent à des compilations évitées. Les publications du
cache sont déjà différées et coûtent seulement 1,357 ms au thread appelant
pour 172 opérations. Les réécrire n’attaquerait pas les 19,93 secondes observées.

## 1. Fermer la fenêtre de notification perdue à l’admission

Le destructeur de `compile_admission` libérait auparavant un ticket fourni
par l’hôte et notifiait les demandeurs sans prendre `compiler_wait_mutex`.
Un demandeur pouvait constater le refus d’admission, puis perdre cette
notification juste avant d’enregistrer son attente sur la condition. Il
pouvait alors attendre le timeout nominal de 20 ms alors qu’un ticket était
redevenu disponible.

La libération du ticket hôte prend maintenant le même mutex que le chemin
de repli. La notification a lieu après le déverrouillage. Le test du prédicat
et l’entrée en attente ne peuvent plus être séparés par une libération non
protégée. Les limites de concurrence, les estimations mémoire, l’annulation
et le timeout restent identiques. La compilation reste hors de cette section.

L’ordre des verrous est conservé : mutex du Core, puis budget de l’hôte.
Le callback hôte examiné ne revient pas synchroniquement dans le Core : il
signale une source GCD. Les fichiers de l’hôte sont inchangés et authentifiés
par leurs empreintes dans le contrat du candidat.

Le test extrait le constructeur et le destructeur de production, ainsi que
le budget hôte. Il impose la frontière réelle mutex/condition de manière
déterministe, sans assertion fondée sur une durée d’ordonnancement :

- Seize entrelacements forcés sur l’API hôte reproduisent seize notifications
  perdues dans la baseline et aucune avec le correctif.
- Seize cas du chemin de repli restent corrects dans les deux versions.
- Quatre cas d’annulation et 768 admissions concurrentes par version passent,
  avec au plus trois admissions actives et aucun ticket restant.
- GCC 13, Clang 22, ASan/UBSan et TSan passent. Les rapports conservent les
  empreintes des corps de production, de l’adaptateur et du programme exécuté.

Les deux fenêtres d’admission étudiées dans BO2 ont des maxima de 7,469 et
6,619 ms, inférieurs à 20 ms. Elles motivent l’examen de ce chemin mais ne
prouvent pas que la fenêtre de course y a été rencontrée. Le résultat est
une correction de concurrence reproduite sur hôte, pas une économie de
20 ms mesurée sur une frame iPhone.

## 2. Réutiliser les fragments dont seules des propriétés inutilisées changent

La clé privée du cache FP conserve toutes les propriétés pouvant modifier le
shader. Elle retire seulement les propriétés dont les consommateurs de
production prouvent l’inutilité pour le microprogramme considéré :

- Bits de coordonnées 2D et de sprites pour les entrées TEX0–TEX9 jamais lues.
- Éclairage des deux faces et interpolation plate lorsque COL0/COL1 ne sont
  jamais lus.

Le programme RSX d’origine reste transmis au compilateur. Les constantes,
les textures, les données sérialisées et les callbacks conservent leurs
entrées originales. Seule la recherche interne peut retrouver un programme
déjà compilé sous une autre combinaison de propriétés inutilisées.

Le masque des entrées lues est calculé à la demande, uniquement si les
propriétés peuvent être simplifiées. Il est mémorisé dans le hint jusqu’à
l’invalidation du microcode. Un hit du hint n’effectue aucune lecture du
microcode. Des propriétés déjà neutres n’entraînent aucun scan ; une clé
inchangée n’est pas copiée. L’analyse historique du programme et `RSXThread`
restent identiques à la baseline.

Le préchargement, qui n’a pas de hint, utilise un parcours borné par la taille
du microcode. Les instructions indirectes, le contrôle de flux, les opcodes
non reconnus et les longueurs ambiguës gardent la clé originale. `TXD` lit
trois opérandes : le scanner le traite explicitement, même si la table
générique en annonce un seul. Les blocs de constantes sont sautés et ne
deviennent jamais des instructions.

Une première variante ajoutait le calcul du masque à chaque analyse de
microprogramme. Son coût sur les programmes longs a conduit à la remplacer
par le calcul paresseux, afin de conserver le chemin commun historique.

## 3. Publier une clé fragment immuable avant les recherches concurrentes

La revue du préchargement a identifié une mutation possible de la clé après
son insertion dans la table : `clone_data()` remplaçait le pointeur des données
hors verrou. Un autre travailleur pouvait comparer cette clé pendant la copie.
La barrière entre préchargement des shaders et compilation des pipelines ne
protège pas ces recherches intermédiaires.

Le clone du microcode a maintenant lieu sous le verrou d’écriture, seulement
lors d’une nouvelle insertion FP. Les lecteurs ne voient plus cette mutation.
Aucune copie n’est ajoutée aux hits et la compilation reste hors verrou.
Cette correction accompagne la convergence des variantes vers une même clé.

## Validation et intégration

Les deux suites passent sous GCC 13 et Clang 22, ainsi que sous ASan/UBSan et
TSan avec GCC 13, sur hôte x86_64. Elles exécutent les corps de production
extraits, avec des adaptateurs explicites pour le SIMD, les mutex, les
annotations de registre et les frontières mémoire/compilation de l’hôte.
Il ne s’agit pas d’une compilation complète du Core ni d’une exécution iOS.

| Vérification du cache FP | Résultat du candidat final |
|---|---:|
| Variantes sans effet comparées aux consommateurs GLSL de production | 5 400 équivalences exactes |
| Variantes actives conservées distinctes | 4 320 |
| Replis conservateurs | 49 |
| Cas de parseur ciblés | 28 |
| Trace synthétique de propriétés inutilisées | 2 048 appels du callback de compilation → 1 |
| Préchargements convergents | 9 requêtes, une compilation |
| Recherches concurrentes après compilation | 8 000 |
| Clé empruntée observable pendant sa transformation | Reproduite avant ; empêchée après |

Les 67 fragments GLSL uniques du test final sont identiques, octet pour octet,
aux entrées déjà compilées et validées avec glslang, SPIRV-Tools et SPIRV-Cross.
Les sorties SPIR-V/MSL et leurs empreintes sont réutilisées sans nouvelle
traduction. Ces fragments sont synthétiques, assemblés à partir des vrais
consommateurs du générateur ; ils ne sont pas des shaders complets extraits
de BO2. Les versions de laboratoire ne sont pas celles du moteur embarqué et
aucune compilation Metal native n’a été exécutée.

Le coût de la nouvelle recherche est également conservé dans les preuves.
Pour un programme synthétique de 2 048 instructions, avec compilation GPU
remplacée par un callback vide :

| Parcours mesuré avec GCC 13 | Baseline, µs | Candidat, µs |
|---|---:|---:|
| Première recherche, propriétés nécessitant l’analyse | 4,490 | 13,865 |
| Première recherche, propriétés neutres | 4,455 | 4,660 |
| Changement d’état avec masque déjà mémorisé | 0,595 | 0,696 |

Le scan ajoute donc environ 9,38 µs à cette première recherche longue. Ce
coût est payé à nouveau après invalidation du microcode ; il n’est pas payé
à chaque hit du hint. Le gain prouvé porte sur les appels de compilation
évités dans la trace synthétique. Aucune économie nette de temps dans BO2
n’est déduite de cette mesure. Le corps de l’analyse commune est identique
à la baseline ; ses fluctuations de timing ne constituent pas une optimisation.

Preuves conservées :

- Admission : [GCC](evidence/rpcs3-bo2-20261029/compile-admission-gcc.json),
  [Clang](evidence/rpcs3-bo2-20261029/compile-admission-clang.json),
  [ASan/UBSan](evidence/rpcs3-bo2-20261029/compile-admission-asan.json),
  [TSan](evidence/rpcs3-bo2-20261029/compile-admission-tsan.json).
- Fragments : [GCC et benchmark](evidence/rpcs3-bo2-20261029/fragment-key-gcc.json),
  [Clang](evidence/rpcs3-bo2-20261029/fragment-key-clang.json),
  [ASan/UBSan](evidence/rpcs3-bo2-20261029/fragment-key-asan.json),
  [TSan](evidence/rpcs3-bo2-20261029/fragment-key-tsan.json),
  [SPIR-V/MSL](evidence/rpcs3-bo2-20261029/fragment-key-shader-proof.json).
- Choix du calcul paresseux :
  [mesure du prototype rejeté](evidence/rpcs3-bo2-20261029/rejected-eager-analysis.json).
- Intégration :
  [matérialisation canonique](evidence/rpcs3-bo2-20261029/canonical-integration.json).

Une matérialisation fraîche à partir de l’amont authentifié reproduit les
311 fichiers canoniques. Les 308 autres postimages, dont les treize précédents
correctifs, sont identiques en octets. La fixture inverse restitue exactement
les trois préimages. Les sources hors gardes iOS, le header ABI et les
88 déclarations d’exports restent identiques. Les identités PPU
`a987639e9f838d1c` et SPU `d070cb361bdef607` sont conservées à partir de leurs
entrées de génération inchangées, sans relancer CMake.

La recette du prochain Core authentifie 170 entrées, les 311 sources et
27 compléments natifs. Elle reconstruit deux baselines explicites : celle
des nouveaux tests BO2 et celle des treize correctifs device593. Lors d’une
future compilation Apple, elle exigera les huit modes device593 qui n’ont
pas encore tourné sur Apple et les six nouveaux modes BO2. Les anciennes
suites déjà vérifiées ne sont pas rejouées. La recette n’est pas déclenchée
par cette intégration source.

## Prochaines optimisations

Le coût des premières bibliothèques Metal reste la priorité pour les gros
blocages. La normalisation des propriétés inutilisées évite du travail
redondant en amont ; elle ne démontre pas la suppression des 32 appels
graphiques longs observés, dont 30 comportent une compilation FS froide.
Toute simplification du
code shader lui-même devra conserver les résultats numériques, les dérivées,
les exports et les formats utilisés par le jeu.

Pour les saccades plus petites, les fenêtres étudiées contiennent 3 590
soumissions, soit environ 6,17 par frame RSX, et des temps texture échantillonnés
de 4,57 à 5,72 ms. Les attentes explicites de fence, readback et hard-sync sont
nulles. Le travail suivant doit cibler les parcours texture et les soumissions
redondantes en conservant l’ordre des commandes et les invalidations CPU
corrigées précédemment. Ces compteurs se chevauchent et ne s’additionnent pas
pour prédire des FPS.

La validation iPhone devra comparer le même passage avec le même état des
caches et contrôler aussi les armes et avant-bras. Aucune activation globale
de l’async, modification des réservations SPU, effacement de cache ou nouveau
réglage joueur n’est introduit. L’IPA 593 reste l’application livrée ; ce
candidat n’ajoute ni Core compilé, ni IPA, ni release.
