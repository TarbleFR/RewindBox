# RPCS3 iOS — pauses observées en 553 et candidat 555

26 octobre 2026. Projet `TarbleFR/RewindBox`, branche `Claude`, base d'analyse
`b3955a21b8c23bca27251c49a5c73112cd790d95`, intégration sur
`eefd945fffb507a039f8d6dbe489a899624c79b6`. Cible : iPhone 16 Pro Max,
8 Go, God of War III `BCES00510`. **Les chiffres de jeu décrivent
le build 553, pas un gain du candidat 555.** La validation du cœur candidat,
son identité binaire finale et l'IPA privée restent à compléter.
Aucun essai physique avant/après 555 n'est disponible.

## Référence et antériorités conservées

Le [bilan 534](rpcs3-cell534.md) et ses preuves distinguent déjà microtests
hôtes et jeu sur appareil. Le montage ISO de restauration, le retrait des
`fsync` des archives NeoSwap temporaires et `SHADERCOST534` ne sont pas des
nouveautés 555. Les sauvegardes et caches persistants gardent leurs garanties.

Sont également antérieurs : réservations et recherches SPU 536/538 ; clés
graphiques et compteurs SPU 539/541 ; normalisation et publication différée
542/543 ; correctifs amont, compression JIT et journaux 545/546 ; attentes
hybrides 547 ; héritage GoW3 et diagnostics 551 ; repli des soumissions et
textures asynchrones 552. Le suivi incrémental JIT, NEON, MeloNX et interface
553 sont conservés. Ni `main` ni release publique ne sont concernés.

La livraison est renumérotée **555** : le build 554 d'import RPCS3,
`9f6892b9`, a été intégré depuis `Claude`. Son [correctif d'import](rpcs3-import554.md)
installe ou relie les disques PS3 du dossier de bibliothèque avant le lancement ;
il est préservé, avec MeloNX et les autres changements de la branche jusqu'à
`eefd945f`. Les tests et runs expérimentaux de hachage conservent leurs noms
historiques **554**. Ce changement de numéro ne transforme aucun journal 553
ni microtest hôte en mesure de performance du build 555.

## Pièces, processus et périodes

L'extraction reproductible est
`build-utils/analyze_rpcs3_cell555_logs.py --logs <dossier> --output <fichier>`.
Le [reçu observé](evidence/rpcs3-cell555-observed.json) conserve empreintes,
lignes, histogrammes, pertes et ancres, sans chemins privés ni configurations
intégrales. Neuf contrôles vérifient notamment le bin chevauchant 500 ms et
l'union des durées parents/enfants.

Pièces : `RPCS3-performance.log` (3151 lignes), `RPCS3-timeline.log` (241),
`RPCS3-restore-trace.log` (1954). Tailles et SHA-256 figurent dans le reçu.

547 contient les PID 32192/32208 ; 548 le PID 32449 ; 551 quelques lignes des
PID 33884/33896/33901. En 553, **34285 est `BLES01658`**, **34342 est
`BCES00510`** : leurs résultats restent séparés. Les titres absents de
certains groupes historiques ne sont pas inventés.

GoW3 553 se décompose ainsi, sans fusionner deux périodes de préparation
séparées par une exécution invitée :

| Session / fenêtres | Phase au moment du rapport | Durée des fenêtres |
| --- | --- | ---: |
| 1 / 1–23 | Préparation, zéro intervalle invité | 117,009 s |
| 1 / 24–26 | `guest_unclassified`, 191 intervalles | 15,952 s |
| 1 / 27 | Préparation/transition, zéro intervalle | 5,061 s |
| 2 / 1–2 | Préparation après restauration | 10,484 s |
| 2 / 3–44 | `guest_unclassified`, 3 019 intervalles | 217,618 s |

La phase est un **instantané du rapport**, pas une étiquette de chaque image.
Aucun classement gameplay/cinématique n'est déduit du FPS. Capture GoW3 :
15:37:36–15:43:44 UTC, 16:37:36–16:43:44 à Paris. L'ancre Unix–monotone varie
de 1,561 ms, encadrement maximal 727 µs. Utiliser ancres locales et processus,
pas l'heure d'export ou l'égalité supposée des sessions entre composants.

## Temps d'image et attribution des coûts

| Mesure GoW3, session 2 invitée | Observation 553 |
| --- | ---: |
| Intervalles conservés | 3 019 |
| p50 agrégé, bornes du bin | 56–56,999 ms |
| p95 agrégé | 88–88,999 ms |
| p99 agrégé | 424–431,999 ms |
| Maximum | 4 519,908 ms |
| Intervalles >50 / >100 / >500 ms | 1 941 / 81 / 25 |
| Pic d'empreinte échantillonnée | 5 013,05 MiB |
| État thermique maximal exporté / pression maximale | 0 / 2 |

Les histogrammes sont fusionnés, jamais leurs percentiles. Le compte >500 ms
est exact ici : aucun bin ambigu rempli. Thermique 0 n'est ni une température
ni une fréquence CPU/GPU. Mémoire compressée et empreinte se recouvrent.

**La reprise JIT et les pipelines occupent des périodes différentes.**
Fenêtre 4 : image de 4 123,337 ms, sans compilation shader. Fenêtre 5 : maximum
4 519,908 ms, avec seulement un pipeline de 1,632 ms. Les fenêtres 3–4
comptent 513 puis 590 générations SPU, soit 9,636 et 6,842 s de travail
cumulé entre threads. Cela justifie d'examiner la préparation SPU à la
reprise ; ce ne sont pas des secondes murales à ajouter aux pauses.

Ensuite, `SHADERCOST534` compte **110 créations graphiques, 29,045 s de
durées cumulées** dans les fenêtres invitées. Les 80 événements >50 ms
conservés couvrent une union de 29,006667 s, sans chevauchement entre eux,
maximum **689,732 ms**. GLSL/SPIR-V : 92 appels, 433,709 ms au total, maximum
24,633 ms ; modules Vulkan : 4,229 ms. Le poste dominant de compilation est
le pilote. Les attentes de présentation, callbacks et durées enfants ne sont
pas additionnées. Les 25 pauses >500 ms ne lui sont pas toutes attribuées.

Au démarrage initial : 841 pipelines, 624,917 s cumulées entre compilateurs,
663 événements longs conservés, union 97,717 s ; ce ne sont pas 624 s de gel en
jeu. Session 2 : 842 pipelines de préparation/835,633 ms ; contexte et caches
diffèrent, sans comparaison avant/après contrôlée.

## Un coût persistant quand les shaders ne compilent plus

Les dix dernières fenêtres 35–44 comprennent **831 intervalles en 51,605 s**
de fenêtres et zéro compilation source/module/pipeline. Leurs p50/p95/p99
restent respectivement **61–61,999 / 82–82,999 / 89–89,999 ms**, maximum
138,529 ms, 667 intervalles >50 ms et trois >100 ms. Optimiser seulement les
premières compilations ne peut donc suffire.

Le hachage hybride traite **235 339 459 256 octets = 219,177 GiB**, soit
**270,081 MiB/intervalle**, 4,247 GiB/s de fenêtres : du travail cumulé, pas de
la RAM allouée. Temps textures RSX échantillonné : 17,413 ms/image pondérés ;
sommets 3,261 ms, préparation 1,104 ms. Environ 1 600–2 000 dessins/image lourde.

Les 12 605 557 810 ticks viennent de `cntvct_el0`, sans fréquence exportée en 553 :
**pas de conversion en secondes inventée**. Le compteur couvre seulement
le chemin hybride ≥4 KiB. La validation de fin d'image peut le recouvrir ; sa
part reste inconnue. Sauter les vérifications de cohérence serait injustifié.

## NeoSwap, attentes et restauration

Demandes VDEC, préchargements et attentes consommateur restent à zéro.
Sans journal d'opérations NeoSwap, les compteurs cumulatifs — 1 621 tentatives,
1 456 échecs, 165 succès — ne décrivent ni restauration ni latence. Les anciens
2,04 s du PID 25548 ne sont pas la cause démontrée des pauses actuelles.
Ni réserve supplémentaire ni changement d'éviction justifié ici. L'effet
du retrait des `fsync` sur pages sales, latence et pression iOS reste non mesuré.

`FREEZE_DUMP`, performance ligne 1985 : **4,538 s sans image**, 6,555 s avant la trace
de restauration disponible. FIFO RSX vide (`get=put`), PPU principal dans
`cellSpursRemoveWorkload` `[s]`, six SPU dans `MFC_Events_read`. Aucune preuve
d'interblocage/réveil perdu ; changement de session ensuite. Les barrières,
réservations et synchronisations invitées restent nécessaires.

Restauration 553, lignes 1305–1954 : **13 réouvertures réussies**, sans erreur
ancienne `id=5/0x80010006`. L'elapsed va déjà de 391 489 à 923 318 µs : durée
complète inconnue. VKGSRender 239,738 ms, spu_runtime 183,346 ms, objets
fichiers 13,823 ms ; les parents incluent leurs enfants.

JIT boot, performance ligne 2038 : 45 modules PPU, **43 en cache/deux compilés**,
7,297 s murales ; codegen 7,478 s cumulées, maximum 6,230 s, recouvrantes. Les 40 modules
en cache du boot frais/693,600 ms forment un autre ensemble. `ppu_pipeline=0`
désigne la variante amont, pas l'absence de génération ARM64/NEON.

## Candidat 555 : changements ciblés et vérifiables

**Le delta retenu corrige et complète le diagnostic.** Aucun gain de FPS,
p95/p99, compilation shader ou instrumentation SPU n'est démontré. Les
candidats de hachage ARM64 ont été rejetés après vérification avec LLVM 22
et les options du cœur : aucun gain robuste justifiant leur intégration.
Le hachage de production 551 reste inchangé octet pour octet ; les variantes
et mesures hôtes restent des expériences, pas des optimisations livrées.

**Attribution du travail textures.** Quatre nouveaux compteurs fixes de
64 bits, soit 32 octets, exportent appels/sections/octets/ticks de
`trim_sections`. `JITMEM` ajoute la fréquence du compteur déjà utilisé par le
hachage hybride, permettant de convertir ses ticks en durée. Aucun nouveau
compteur atomique par hash n'est retenu. Le chronométrage du trim encadre une
passe entière, avec deux lectures d'horloge, compteurs locaux puis publication groupée.
La vérification et les lectures restent identiques : ce n'est pas un
échantillonnage qui laisserait passer une texture modifiée. `texture_trim_*`
peut inclure `texture_hash_*` ; les deux coûts ne doivent pas être sommés.
Cette mesure doit départager les lectures utiles des revalidations répétées
avant toute suppression de travail.

**Attribution des transferts GPU→CPU.** `IOSReadbackProfile` ajoute 200 octets
de compteurs fixes, répartis entre cinq origines : `texture_cpu`,
`blit_source_cpu`, `blit_destination_dma`, `presentation_cpu` et `unknown`.
Quatre points d'appel attribuent explicitement l'origine ; les autres restent
visibles dans `unknown`, y compris sur les autres threads. L'origine courante
est locale au thread et restaurée après les appels imbriqués. Un lot DMA non
vide coûte deux lectures d'horloge, sans allocation par événement ; aucune
lecture d'horloge n'est ajoutée à un dessin ordinaire ou à un hit du cache.
Une ligne bornée `READBACK555` par fenêtre donne lots, sections, octets demandés
confirmés, durée totale et maximum par origine. Les octets ne sont pas le
trafic DMA réel : pitch, tiling et chevauchements peuvent différer. Cette durée
parente comprend la fence et les traitements du lot ; ne pas l'ajouter aux
attentes GPU ni aux durées d'autres threads. La mesure ne retire aucun
transfert, verrou ou événement et ne prouve pas encore qu'une copie est évitable.

**Suivi des pipelines après préchauffage.** En 553, la table de 64 empreintes
reste saturée ; le dernier rapport porte `fingerprint_dropped=886`. Ce sont
des observations perdues, pas 886 annulations ou compilations identiques.
Le candidat garde 64 entrées avec remplacement FIFO, compte distinctement
évictions, contention et contextes incomplets, et marque les répétitions
comme une borne inférieure. Les pipelines sans contexte vertex/fragment
complet ne sont plus regroupés sous une empreinte artificielle commune.
Le verrou reste tenté sans attente et aucune allocation par événement
n'est ajoutée. Cette correction du diagnostic ne change pas les clés du
cache GPU et ne prouve aucune accélération de compilation.

Le mode Legacy configuré/appliqué 0 observé est conservé. `database=1` confirme
l'application du profil GoW3, avec résolution 75 %, limite 30, WCB et MT RSX ;
les soumissions et textures asynchrones restent désactivées après 552. Aucun
mode qui supprime des dessins n'est forcé. Les identités de cache sont
**PPU `a987639e9f838d1c`, SPU `d070cb361bdef607`**, conservées : ces
observations hôtes n'imposent pas de recompilation invitée globale.

## Pertes, validation et livraison à compléter

En préparation 553 GoW3, **177 événements shader longs** sont perdus par
saturation du ring 32. La suite invitée session 2 en déclare zéro ; le compteur
général à zéro ne remplace pas ce contrôle. Deux pertes `LOG_BUDGET` concernent
l'autre jeu/PID 34285. L'historique 547 conserve une timeline mais ses détails
performance ont tourné : pas de p95/p99 agrégés inventés. En fin 553,
diagnostic/milestones signalent une rotation, performance/timeline zéro.

Les tests doivent exécuter production et témoins authentifiés : équivalence
textures, concurrence, saturation/remplacement, contextes incomplets et
attribution des lots DMA. Les microtests Linux/Apple sont distingués selon
architecture, compilateur et options ; le rejet des variantes de hachage est
documenté séparément. Ils ne deviennent pas des gains en jeu. **Compilation
et validation du cœur final, reçu de l'IPA : à compléter.** Le delta canonique/manifeste
doit correspondre aux sources testées ; le paquet doit conserver les bons
octets du cœur et des autres composants. Vérifier versions et signatures ;
l'IPA déchiffrée exige encore sa re-signature SideStore.

## Protocole iPhone avant/après

1. Garder 553, caches et sauvegardes originaux. Utiliser une **copie** du même
   état et le même disque BCES00510 ; séparer boot, préparation, restauration
   réussie et exécution. Un échec de restauration n'est pas du gameplay.
2. Même scène/trajet, résolution, limite FPS, shader, SPU/SPURS et audio.
   Thermique comparable ; alimentation/refroidissement notés. Trois passages
   par build et par scène jouable/cinématique, identifiées et horodatées.
3. Caches froids dédiés puis chauds, sans supprimer les originaux ; alterner
   l'ordre 553/555. Exporter journaux courants/tournés, opérations NeoSwap et
   app.log. Compter les pertes et vérifier rendu, textures, objets et audio.
4. Comparer histogrammes fusionnés p50/p95/p99, maxima, >50/100/500 ms, temps
   sans image, shader/JIT, attentes, volume haché/image, trim, origines et
   octets des readbacks, pics mémoire et pression. Examiner latences I/O et restaurations sans compter les enfants
   deux fois. Prolonger 30 minutes ; vérifier croissance des caches et relance.
   Toute régression de rendu, mémoire ou stabilité invalide le gain apparent.

Les cases **p95/p99 avant/après 555, stabilité 30 minutes, restauration réelle
et effet des pages sales sur iPhone restent non mesurées** jusqu'à ce test.

## Complément : nouvel export DBZ/GoW3, toujours build 553

Le [bilan DBZ séparé](rpcs3-cell555-dbz.md) et son
[reçu distinct](evidence/rpcs3-cell555-dbz-observed.json) analysent les fichiers
suffixés `(1)`, sans remplacer les pièces ci-dessus. `restore-trace(1)` est
strictement identique au premier export : aucune restauration DBZ nouvelle.

DBZ `BLES01658`, PID 34675/session 2, dernières dix fenêtres : 2 182 intervalles,
p50 22–22,999 ms, p95 29–29,999 ms, p99 30–30,999 ms ; maximum 39,058 ms,
aucun intervalle >50 ms. Les 4 364 attentes fence texture représentent
**deux attentes/image et 8,305 ms/image**. Shader/JIT et hachage hybride sont
nuls dans cette période. Le chemin à départager est le transfert GPU→CPU
synchronisé sous verrou textures. `cpu_gpu_fence` recouvre cette attente ;
`frame_latency` mesure l'âge soumission→cleanup, pas une attente à ajouter.
Ces chiffres n'identifient pas les scènes et ne mesurent aucun gain 555.


## Sélection du hachage ARM64 : variantes rejetées

**Aucune nouvelle optimisation du hash n'est retenue en production.** Le
[fichier de preuve](evidence/rpcs3-cell555-hash-selection.json) conserve les
quatre exécutions, leurs révisions sources, empreintes d'archives, mesures
brutes et analyse des assembleurs. Les expériences restent identifiées par
`test/rpcs3_texture_hash554_test.py` et
`.github/workflows/rpcs3-cell554-bench.yml` ; elles précèdent la renumérotation
de la livraison en 555. Leurs IDs, commits, chemins et SHA ne sont pas renommés :

| Exécution | Source | Vérifications d'égalité | Protocole hôte |
| --- | --- | ---: | --- |
| [Initiale](https://github.com/TarbleFR/RewindBox/actions/runs/40356210883) | `11c4abd7` | 86 625, 4 variantes | Apple clang 17, 256 MiB/essai |
| [Hybride](https://github.com/TarbleFR/RewindBox/actions/runs/40357407856) | `f9ffcd90` | 144 375, 6 variantes | Apple clang 17, 256 MiB/essai |
| [Essais prolongés](https://github.com/TarbleFR/RewindBox/actions/runs/40358423398) | `49f580d6` | 202 825, 8 variantes | Apple clang 17, 4 GiB/essai |
| [Compilateur du cœur](https://github.com/TarbleFR/RewindBox/actions/runs/40359425106) | `55df61c3` | 231 800, 9 variantes | LLVM 22.1.8, 4 GiB/essai, temps CPU compagnon |

Les deux dernières sélections utilisent douze rondes, six variantes
chronométrées dans un ordre de Williams équilibré, quatre tailles de 4 KiB à
8 MiB, puis un parcours de 64 MiB. Le mode `streaming` n'assure pas un cache
matériel froid. Les ratios sont appariés au témoin de chaque ronde ; les
exécutions ne sont pas mélangées. Le dernier essai applique
`-mcpu=apple-a7 -march=armv8.4-a -fstack-protector -fno-exceptions`, comme le
cœur. `tuned6` ajoute uniquement `-mtune=apple-m1` à son unité de traduction,
sans étendre l'ISA. Les lectures de l'horloge CPU du thread encadrent chaque
essai entier, en complément du temps mural.

| Variante | Variation du temps mural médian selon les huit conditions | Conditions avec une médiane plus lente |
| --- | ---: | ---: |
| Ordonnancement `tuned6` | −3,1 % à +7,9 % | 5/8 |
| Regroupement `group4` | −5,3 % à +6,4 % | 5/8 |
| Hybride `hybrid4` | −8,1 % à +9,8 % | 5/8 |
| Deux chaînes `twins6` | +3,1 % à +23,3 % | 8/8 |
| Deux chaînes `twins8` | +3,0 % à +23,8 % | 8/8 |

Un pourcentage négatif désigne un essai plus court, pas un gain de FPS. Pour
`tuned6` et `group4`, les plages p10/p90 des ratios recouvrent 1 dans les huit
conditions ; elles décrivent la dispersion, pas des intervalles de confiance.
Le temps CPU compagnon ne met pas en évidence de gain robuste masqué par la
préemption. Les validations d'égalité et ASan/UBSan passent, mais elles ne
valident pas le débit en jeu.

L'assembleur LLVM 22 confirme que le témoin conserve déjà ses accumulateurs
en registres, sans accès à la pile dans la boucle. `group4` réduit de 130 à
90 les instructions pour quatre stripes, tout en déplaçant les multiplications
vers NEON ; cela n'a pas produit d'amélioration stable. Les deux chaînes de
produits raccourcies et le réglage d'ordonnancement sont également rejetés.

`IOSTextureHash.cpp` reste exactement identique à la référence précédant les
expériences 554 et conservée pour la livraison 555,
SHA-256 `561c3a31438f3c492493c778bbeebba8291e180a29defab75a34c86b45688e72`.
L'ajout expérimental du compteur atomique d'appels est retiré, et aucun
réglage de compilation du hash n'est ajouté. Les tests de sélection sont
conservés ; aucun gain ARM64/NEON, de p95/p99 ou de FPS sur iPhone n'est
revendiqué à partir de ces mesures hôtes.

## Validation du candidat natif555

Le Core555 est construit depuis le commit `f508f1bf87542fe6e9649d7240cbafbbeb8c2c2d`,
après conservation du produit import554 et de MeloNX. Le [rapport Linux final](evidence/rpcs3-cell555-host-linux.json)
correspond à la fixture555 et aux postimages canoniques ; ASan/UBSan et TSan
passent pour les observations de maintenance textures, les empreintes de pipelines
et les origines de readback. Il couvre notamment 800 passes concurrentes de
maintenance, 4 000 lots de readback et 16 000 événements shader attribués plus
16 000 sans contexte. Il ne mesure ni rendu, ni FPS, ni thermique sur iPhone.

La compilation et la validation de l'IPA sont consignées séparément dans le
reçu final de livraison. Aucune accélération ARM64 expérimentale n'est retenue.
