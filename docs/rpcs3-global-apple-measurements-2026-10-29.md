# RPCS3 — mesures du préflight Apple du 29 octobre 2026

Le préflight de la source `5b2a5614f634221ea896607b4686ad2afdd5ada3` réussit : **26 modes sont couverts, dont 12 exécutés dans ce run et 14 repris de checkpoints authentifiés**. Cette annexe analyse ses mesures avant/après. Le [rapport de compilation](rpcs3-global-core-2026-10-29.md) documente séparément le Core produit et vérifié. Les résultats montrent des économies de travail précises et plusieurs surcoûts. **Aucun gain de FPS, de temps d’image ou de stabilité sur iPhone n’est établi.**

La [synthèse JSON](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/apple-measurements.json) conserve les 44 cas chronométrés, les compteurs, les séries disponibles, les empreintes des 26 rapports et leur provenance. Le [fichier de preuve du préflight](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/preflight/runtime592-proof.json) authentifie ces rapports. La référence des optimisations globales est `3e4fcfa121e01fd08934486b833dde6a69a2d318`.

## Méthode et provenance

Les programmes s’exécutent sur **macOS ARM64 avec Clang Homebrew 22.1.8**. Les durées ci-dessous proviennent exclusivement des modes `plain`, avec sept séries par cas. Ce sont des médianes de microbenchmarks, sans intervalle de confiance ni répétition sur plusieurs sessions indépendantes. Une variation positive signifie que le candidat prend davantage de temps. Les modes ASan/UBSan et TSan apportent leurs vérifications fonctionnelles ; leurs durées ne servent pas à mesurer les performances.

MFC et timer SPU ont été exécutés dans le run `40900528171`, source `2a2bfc23`, puis repris sans rejouer leurs programmes inchangés. Descriptors, hashes et NeoSwap sont nouvellement exécutés dans le présent préflight, comme viewport/scissor et RSX write/sampler. Les 14 reprises comprennent également quatre modes du premier run `40897672646`. Les 16 modes Apple historiques conservés du Core précédent constituent une autre catégorie : ils ne sont pas de nouvelles exécutions de ce run.

## Toutes les médianes qui régressent

Douze des 44 cas chronométrés ont une médiane plus lente. Ils sont tous présentés ci-dessous, sans conclure que chaque différence est statistiquement significative. La dispersion explique pourquoi les petits écarts doivent rester qualifiés.

| Banc et scénario | Unité | Avant | Après | Variation de durée |
|---|---|---:|---:|---:|
| MFC, shuffle 0, file 16 | ns/masque | 1,13042 | 1,51875 | +34,35 % |
| MFC, shuffle 0, file vide | ns/masque | 1,26887 | 1,57179 | +23,87 % |
| MFC, shuffle 1, file 16 | ns/masque | 1,21513 | 1,57721 | +29,80 % |
| MFC, shuffle 16, file 16 | ns/masque | 1,96875 | 2,15871 | +9,65 % |
| Timer, 6 entrées, aucune échue | ns/balayage | 82,9133 | 91,9350 | +10,88 % |
| Timer, 32 entrées, aucune échue | ns/balayage | 53,0941 | 54,7716 | +3,16 % |
| Timer, 1 024 entrées, aucune échue | ns/balayage | 2 282,22 | 3 206,19 | +40,49 % |
| Descriptors iOS, hits graphiques | ns/opération | 1,44858 | 2,40867 | +66,28 % |
| Descriptors iOS, handles changeants | ns/opération | 3,31575 | 6,58317 | +98,54 % |
| Hash, plages distinctes de 32 Kio | µs/validation | 0,96248 | 0,96989 | +0,77 % |
| Hash, plages distinctes de 3 686 400 octets | µs/validation | 120,09116 | 125,21875 | +4,27 % |
| Hash, bypass après invalidation, 3 686 400 octets | µs/validation | 109,44531 | 111,50913 | +1,89 % |

## MFC : horloge supprimée, accélération non démontrée

Le [rapport MFC](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/preflight/spu-mfc-plain-result.json) valide 18 939 904 comparaisons de masques et 235 008 appels à `do_mfc`, répartis sur 78 336 scénarios. Les scénarios avec shuffle désactivé passent de **13 824 à zéro lecture d’horloge**, avec conservation des actions et de leur ordre, notamment 48 960 notifications de tags et 113 832 barrières.

La suite fonctionnelle compte les lectures avec un adaptateur déterministe. **Le chronométrage distinct utilise réellement `mrs ..., cntvct_el0`**, extrait du `utils::get_tsc()` de RPCS3, avec helpers `noinline` et barrières compilateur. Les quatre régressions Apple ne peuvent donc pas être écartées comme un simple coût de compteur simulé. Elles concernent le helper de masque et sa boucle ; ni les transferts DMA réels ni `do_mfc` complet ne sont chronométrés. Le nombre de lectures évitées ne prouve pas une accélération sur cet hôte.

## Timer SPU : compaction utile lors des expirations

Le [rapport timer](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/preflight/spu-timer-plain-result.json) constate **10 357 → 277 effacements non vides**, **1 065 → 277 allocations** et **960 340 → zéro décalage provoqué par les effacements**. Ce dernier compteur n’inclut pas les déplacements nécessaires à la compaction stable. Les échéances, l’ordre et les notifications restent vérifiés ; aucun callback n’est exécuté sous le verrou.

Pour six entrées toutes échues, la médiane passe de **195,356 à 62,6064 ns**, soit −67,95 %. Pour 128 entrées toutes échues : **4 911,29 → 694,032 ns**, soit −85,87 %. Le cas sans échéance est moins favorable. Pour six entrées, ses séries couvrent 36,54–109,97 ns avant et 35,31–114,96 ns après : la dispersion reste importante.

Le banc utilise le balayage natif, des `std::vector` et un mutex hôte. La région chronométrée comprend aussi la réaffectation du vecteur d’entrée et la création/destruction du lot temporaire. Elle ne reproduit pas le scheduler complet.

## Descriptors : correction d’état et compromis du cache

Le [rapport descriptors](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/preflight/descriptor-bind-plain-result.json) vérifie **1 141 divergences d’état → zéro** pour le chemin iOS. L’alternance graphics/compute passe de **128 à 2 émissions**. Le scénario utilisant `program::bind` passe de **32 à 2**, avec trois allocations inchangées ; le scénario modifié avec overlay passe de **36 à 5**, avec cinq allocations inchangées.

L’alternance est chronométrée à **3,35854 → 2,55058 ns/opération**, soit −24,06 %. Les hits graphiques et les handles changeants régressent comme indiqué plus haut. **Le driver est simulé par un compteur et un checksum** : aucun coût Vulkan, MoltenVK ou GPU n’est mesuré. Certaines émissions augmentent légitimement pour réparer des omissions incorrectes ; leur somme ne constitue pas un gain général.

Le command buffer iOS modélisé gagne 48 octets, passant de 288 à 336, sans allocation supplémentaire dans ces scénarios. Le chemin desktop reste inchangé et conserve les erreurs de référence comme contrôle explicite.

## Hashes : bénéfice conditionnel sur les plages identiques

Le [rapport hashes](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/preflight/texture-hash-reuse-plain-result.json) confirme **96 validations répétées : 96 → 12 hashes**, et **6 291 456 → 786 432 octets hachés**. Les 32 plages distinctes nécessitent toujours 32 hashes. Trois écritures chevauchantes imposent trois nouveaux calculs et trois rejets du contenu modifié dans les deux versions. Les quatre mutations volontairement incorrectes sont rejetées.

Avec huit sections partageant une plage de 1 Mio, la médiane passe de **31,2331 à 3,8021 µs/validation**, soit −87,83 %. À 64 Kio : **1,9536 → 0,2816 µs**, soit −85,59 %. Le contrôle 32 Kio reste sous le seuil d’éligibilité.

Ces mesures utilisent le harnais fonctionnel intégré, avec observateur désactivé et worker présent, sans spéculation de frame précédente. La notification d’époque est omise pour limiter les variations de réveil. Ce protocole diffère du benchmark Linux isolé antérieur. Les trois régressions affichées présentent des plages de séries qui se chevauchent. Automatic reste limité à GOW3 ; la fréquence réelle des plages réutilisables en jeu demeure inconnue. Les compteurs de hits peuvent inclure les producteurs synchrones.

## NeoSwap : économie locale, hors du dylib RPCS3

Le [rapport NeoSwap](evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/preflight/neoswap-discard-plain-result.json) couvre 96 000 opérations, 124 861 audits et **11 cas du Store complet**, avec vrais échanges POSIX et utilisation des bibliothèques Apple Compression et zlib sur Darwin.

Avec 1 024 entrées vivantes et aucun retrait, la collecte passe de **13 151,5 à 1,6875 ns** grâce au retour immédiat. Avec un retrait retenu : **15 052,1 → 4 306,1 ns**, soit −71,39 %. Le cas vide reste à 1,7125 ns. Aucune des dix médianes ne régresse, mais le rapport ne conserve pas les séries permettant d’en reconstruire la dispersion.

Le chronométrage couvre uniquement les métadonnées, hors I/O, compression et traitement complet du worker. Le cas synthétique « 4 096 vivantes + une retirée » dépasse la limite réelle de 4 096 entrées et ne représente pas une charge réalisable. **La modification de `Store.cpp` appartient au code hôte de RewindBox, hors du dylib RPCS3** : la compilation du Core seule ne livre pas cette modification dans un nouveau binaire d’application.

## Points à poursuivre

Les coûts ARM64 du masque MFC, les chemins descriptors sans alternance et les balayages timer sans échéance restent des pistes précises. Les mesures en jeu devront établir la fréquence des chemins concernés, les hits de hash utiles, les temps d’image extrêmes et les éventuelles régressions. Ce préflight ne permet pas de déclarer corrigés les artefacts BO2/Assassin’s Creed ni le gel GOW3.
