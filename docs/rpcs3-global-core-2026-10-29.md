# RPCS3 iOS — Core recompilé et vérifié, 29 octobre 2026

Le Core demandé est compilé depuis la branche `Claude`, source
[`5b2a5614f634221ea896607b4686ad2afdd5ada3`](https://github.com/TarbleFR/RewindBox/commit/5b2a5614f634221ea896607b4686ad2afdd5ada3).
Le [run 40903365466](https://github.com/TarbleFR/RewindBox/actions/runs/40903365466),
tentative 1, et le job `123551374331` sont terminés avec succès. Le binaire et
les deux archives de validation ont été téléchargés, puis vérifiés séparément
du runner Apple. Aucune nouvelle IPA, release ou livraison numérotée n'est créée.

## Binaire disponible

| Élément | Résultat vérifié |
| --- | --- |
| Artefact | [12912380338 — RPCS3Core](https://github.com/TarbleFR/RewindBox/actions/runs/40903365466/artifacts/12912380338) |
| Fichier | `libRPCS3Core.dylib`, Mach-O ARM64, plateforme iOS |
| Taille du binaire | 77 268 488 octets |
| SHA-256 du binaire | `a45a9de84c7b3b82a43dc091a999da32316389f575a0afd8c983d69bd8a1f276` |
| Archive ZIP | 29 114 064 octets |
| SHA-256 du ZIP | `76e1e34b95882c5d91ca65fb8b85aa2a5ad130a3418035ba1bd53535b2a216d1` |
| ABI et exports | ABI 30 ; 88 symboles exportés exacts |
| Identité PPU | `a987639e9f838d1c`, conservée |
| Identité SPU | `d070cb361bdef607`, conservée |
| Source amont | XITRIX/rpcs3 `22f1152783cef1f7e04af7b1c895173e28fd5b03` |

La preuve lie le binaire aux **269 entrées de validation**, aux **92 entrées
de fabrication du Core**, aux **313 postimages natives** et aux **97 sources
complémentaires**. Les [métadonnées GitHub](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/github-metadata.json),
l'[identité du Core](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/core/identity.json)
et le [reçu de vérification des artefacts](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/artifact-verification.json)
conservent les valeurs complètes.

La fabrication réelle du Core prend **696 secondes (11 min 36 s)**. Le préflight
prend 174 secondes, les vérifications finales Apple 15 secondes et le job entier
1 022 secondes (17 min 02 s), préparation et téléversements compris. Ces durées
proviennent des étapes GitHub ; elles ne sont pas des mesures de gameplay.

## Modifications présentes dans ce Core

La [comparaison des postimages](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/native-source-delta.json)
avec le dernier Core livré dans l'IPA 594 (`fe587e27`) constate **11 fichiers
natifs modifiés et 302 identiques**, sans ajout ni retrait. Les correctifs
déjà livrés avant ce lot restent présents.

| Fichiers natifs | Modification intégrée |
| --- | --- |
| `rpcs3/Emu/RSX/RSXFIFO.cpp` | Retour FIFO vide explicite pour un paquet incomplet ; reprise de l'en-tête lorsque son premier argument n'est pas encore publié. |
| `rpcs3/Emu/RSX/Common/texture_cache_utils.h` | Retrait des anciennes plages avant recyclage, y compris sans ressource GPU ; recherche ordonnée pour le retrait ; suppression du parcours redondant à l'insertion. |
| `rpcs3/Emu/RSX/VK/VKGSRender.cpp`, `VKTextureCache.cpp` | Attente des uploads safe aux étapes transfert, vertex et fragment, sans ajout de `queue_wait_idle`. |
| `rpcs3/Emu/RSX/RSXThread.cpp` | Rafraîchissement des vues/filtrages et de l'état fragment lors des transitions BX2 et des changements de références aux textures. |
| `rpcs3/Emu/Cell/SPUThread.cpp` | Lecture d'horloge MFC conditionnelle et compaction stable des échéances SPU en un passage. Le coût du masque MFC isolé régresse dans les mesures Apple ci-dessous. |
| `rpcs3/Emu/RSX/VK/vkutils/commands.h`, `commands.cpp` | Caches de descripteurs graphics/compute indépendants, avec layout exact, nombre de sets et handles. |
| `rpcs3/Emu/RSX/Common/texture_cache.cpp`, `rpcs3/ios/IOSTexturePrehash.h` | Partage des hashes synchrones éligibles dans la même époque, avec une seule tentative atomique de publication. |
| `rpcs3/Emu/CPU/JITCacheCompatibility.cmake` | Alias limité aux changements runtime vérifiés, conservant les identités de cache PPU/SPU sans modifier l'émission LLVM ou NEON. |

Le détail des fonctions et des limites figure dans les rapports
[device594](rpcs3-device594-followup-2026-10-29.md) et
[optimisations globales](rpcs3-global-optimization-2026-10-29.md).

**L'optimisation de collecte dans `native/neoswap-storage/Store.cpp` appartient
au code hôte de l'application.** Elle est validée par le préflight, mais ce
fichier n'est pas intégré à `libRPCS3Core.dylib`. Elle deviendra effective dans
un nouveau binaire d'application après une future compilation de l'IPA.
Les clients et ABI NeoSwap existants du Core restent présents.

## Contrôles Apple et reprise des résultats existants

Les **26 modes ciblés sont réussis** : 12 plain, 12 ASan/UBSan et deux TSan.
Le run réussi en exécute **12** : cinq plain, cinq ASan/UBSan et deux TSan.
Les **14 autres** sont repris avec leurs commandes, programmes, sorties,
compilateur et provenance exacts : quatre du premier checkpoint, dix du second.
Les **16 modes historiques inchangés du Core précédent** restent une catégorie
distincte, réutilisée sans nouvelle exécution.

Les deux premières tentatives n'ont produit aucun Core et restent enregistrées
comme des échecs. Deux corrections de tests ont permis de poursuivre :

| Tentative / fichiers corrigés | Cause et correction |
| --- | --- |
| [40897672646](https://github.com/TarbleFR/RewindBox/actions/runs/40897672646) ; `test/rpcs3_texture_lifecycle_test.py` | Le compteur exact supposait un rang fixe dans un `unordered_set` de pointeurs. Il tient désormais compte du rang observé, sans changer les assertions sémantiques ni l'ordre du conteneur. |
| [40900528171](https://github.com/TarbleFR/RewindBox/actions/runs/40900528171) ; `test/native/rpcs3_descriptor_bind_cache.inc` | La constante du mock iOS était inutilisée dans la variante desktop avec Clang. Une annotation `[[maybe_unused]]` ciblée corrige ce cas ; `-Werror` reste actif. |

Les helpers `rpcs3runtime_global_resume.py` et `rpcs3runtime_global_resume2.py`,
le gate global et les hooks du pipeline de validation authentifient les reprises.
Ils n'admettent pas les modes qui avaient échoué. Le fichier de demande de build
enregistre les comptes et la source ; la recette de compilation et les 313
fichiers natifs restent inchangés pendant ces corrections de validation.
Les contrôles ciblés des helpers rejettent respectivement 18 et 27 altérations.
Les preuves des tentatives échouées sont conservées dans `apple-core/failed-*`.

Après téléchargement, les contrôles indépendants vérifient les tailles et SHA-256
des trois ZIP, leurs membres et CRC, le Mach-O réel, les exports, les marqueurs,
les deux hooks MoltenVK et les identités PPU/SPU du journal de fabrication.
La relecture complète des sources et compteurs passe également, sans relancer
de test natif, CMake ou compilation.

Le [reçu portable](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/reuse-verification.json)
documente une adaptation nécessaire hors du runner : le vérificateur d'origine
compare des chemins de rapport absolus. L'[échec local initial](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/reuse-verification-original-path-failure.json)
est conservé. Le wrapper accepte uniquement le remplacement du répertoire de
l'unique argument final `--report` par le répertoire Apple fixe, en comparant
tous les autres arguments exactement. Il appelle ensuite le vérificateur
d'origine, relit les fichiers locaux et conserve intégralement la preuve.
Le vérificateur sans cette adaptation avait déjà passé sur le runner Apple.

## Mesures avant/après : bénéfices locaux et régressions conservées

L'[annexe Apple](rpcs3-global-apple-measurements-2026-10-29.md) présente les
44 cas chronométrés et **les 12 cas dont la médiane régresse**. Les séries
disponibles, compteurs et empreintes sont dans la
[synthèse JSON](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/apple-measurements.json).
Les chiffres suivants sont des microbenchmarks macOS ARM64, pas des FPS iPhone.

| Scénario mesuré | Avant | Après | Portée |
| --- | ---: | ---: | --- |
| Timer SPU, six entrées toutes échues | 195,356 ns | 62,6064 ns | Balayage natif avec vecteurs et mutex hôte. |
| Descripteurs, alternance graphics/compute | 3,35854 ns/op | 2,55058 ns/op | Wrapper avec driver simulé ; émissions 128 → 2 dans le scénario fonctionnel. |
| Hash, huit sections partageant 1 Mio | 31,2331 µs/validation | 3,8021 µs/validation | Réutilisation conditionnelle ; Automatic reste réservé à GOW3. |
| Masque MFC, shuffle 0 et file 16 | 1,13042 ns | 1,51875 ns | **Régression**, avec véritable lecture `cntvct_el0` dans la référence. |
| Descripteurs, hits graphiques | 1,44858 ns/op | 2,40867 ns/op | **Régression du wrapper** ; aucun coût MoltenVK/GPU inclus. |
| Descripteurs, handles changeants | 3,31575 ns/op | 6,58317 ns/op | **Régression du wrapper** ; aucun bind évité dans ce cas. |
| Hash, grandes plages distinctes | 120,0912 µs/validation | 125,2188 µs/validation | **Régression de médiane**, avec dispersion qui se chevauche. |

Les quatre médianes du masque MFC régressent : la suppression de lectures
d'horloge ne prouve donc pas une accélération Apple. Certains balayages sans
échéance et contrôles de hash régressent également. La justesse des états,
barrières, bypass et invalidations exercés reste vérifiée. Aucun gain global
de CPU, GPU, RAM, FPS ou temps d'image sur iPhone n'est revendiqué.

## Compatibilité et limites restantes

Le Mach-O déclare `minos 16.3`, mais le build signale huit appels `os_sync_*`
disponibles à partir d'iOS 17.4, sans garde de disponibilité dans ce chemin.
La [configuration hôte RPCS3](../build-utils/configure_rpcs3_ios_v1.py) et le
[pod NeoSwap](../packages/neo_swap/ios/neo_swap.podspec) exigent déjà iOS 17.4.
**Le champ du Mach-O ne doit pas être présenté comme un support vérifié du
dylib isolé sur iOS 16.3–17.3.** Ce lot ne change pas la cible de déploiement.

Le build contient aussi 500 avertissements `ranlib` sur un attribut de bitcode
LLVM 22 inconnu du lecteur Apple LLVM 17, ainsi que des avertissements de
dépréciation ou de code inutilisé. Le lien final et les contrôles des exports
réussissent ; le build n'est pas présenté comme exempt d'avertissements.
Le [journal complet](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/diagnostics/build.log.gz)
est conservé sans perte. La recette est identique à celle du Core `fe587e27`.

Le contrôle de chargement passif est statique : il suit les branches ARM64
directes `B/BL` vers les fonctions interdites nommées, à profondeur maximale 16.
Il ne constitue pas un `dlopen` exécuté sur iPhone et ne couvre pas exhaustivement
les appels indirects. Aucun gameplay ni test prolongé sur appareil n'a été réalisé.

La suite du travail doit mesurer les mêmes scènes BO2, torches d'Assassin's Creed
et gel signalé de GOW3 sur iPhone, après intégration dans une IPA de test autorisée.
Les premières pistes à reprendre sont le coût complet du chemin MFC, les chemins
simples du cache de descripteurs, les balayages sans échéance et la fréquence réelle
des plages de hash réutilisées. La cohérence de la cible iOS et des outils
d'archivage mérite une correction de recette dédiée. Les glitches BO2, le
flickering AC et le gel GOW3 ne sont pas déclarés résolus par cette compilation.

Pour une prochaine IPA demandée, réutiliser ce Core si les entrées de fabrication
et de validation correspondantes sont inchangées. Les preuves documentaires
ajoutées après le build ne nécessitent pas de rejouer les suites ni de reconstruire
le moteur.
