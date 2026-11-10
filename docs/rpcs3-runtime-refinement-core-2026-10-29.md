# RPCS3 — Core recompilé et vérifié après l’échec Clang du 29 octobre 2026

**Le build est réussi.** Le commit [`f42573af`](https://github.com/TarbleFR/RewindBox/commit/f42573afc25842ca9a0068f4ad505bbfe5342623) passe le [run 40917423708](https://github.com/TarbleFR/RewindBox/actions/runs/40917423708), job `123601264700`, tentative 1. Les trois archives ont ensuite été téléchargées et vérifiées indépendamment, ainsi que le véritable Mach-O, ses entrées source et les rapports natifs. Le Core contient les trois raffinements runtime du lot `5af78bb3`.

| Résultat | Valeur vérifiée |
|---|---|
| Artefact Core | [`12917652510`](https://github.com/TarbleFR/RewindBox/actions/runs/40917423708/artifacts/12917652510) |
| Source exacte | `f42573afc25842ca9a0068f4ad505bbfe5342623` |
| Cible | Mach-O ARM64, plateforme iOS |
| Taille du dylib | 77 268 488 octets |
| SHA-256 du dylib | `05459149444fe5be32ffb8218ada79dd6a3b531377bd3d19e1bf34294dd0fbb8` |
| Taille ZIP | 29 118 830 octets |
| SHA-256 ZIP | `4956f76388cbe2da7eeb87f45980a91391d05e3f71af16fdb163668efe3e2cad` |
| Interface | ABI 30, 88 exports réels |
| Identité PPU | `a987639e9f838d1c` |
| Identité SPU | `d070cb361bdef607` |

| Étape | Durée mesurée |
|---|---:|
| Prévalidation Apple | 79 s |
| Compilation du Core | 574 s — 9 min 34 s |
| Vérifications finales Apple | 12 s |
| Job complet | 779 s — 12 min 59 s |

Le cache de dépendances/ccache restauré contient 779 317 434 octets et provient de la tentative `5796e165`. Aucun compteur de hits/misses ccache n’est enregistré ; ces durées ne permettent pas de quantifier le nombre d’objets réutilisés ni d’attribuer un gain de temps à un mécanisme précis.

La reprise est demandée explicitement par le mainteneur après l’échec du [run 40914849302](https://github.com/TarbleFR/RewindBox/actions/runs/40914849302), source `5796e165cc0b355e779309f8a20360dc0e969f0d`, job `123592224611`. Le Core précédent `5b2a5614` reste un résultat historique réussi ; il ne contient pas les trois raffinements runtime du lot `5af78bb3`.

## Cause vérifiée et correction

Le préflight Apple a réussi sept modes : timer optimisé et ASan/UBSan, descripteurs optimisé et ASan/UBSan, hashes optimisé, ASan/UBSan et TSan. Le huitième mode, `refined-lookup-plain`, s’arrête lors de la compilation du programme de référence : Clang 22.1.8 rejette les constantes inutilisées `min_bytes`, `max_sequence` et `lookahead` avec `-Werror,-Wunused-const-variable`. La compilation du Core, son édition de liens et son contrôle final n’ont pas été lancés.

`test/rpcs3_runtime_refinement_test.py` annote ces trois déclarations avec `[[maybe_unused]]` dans la copie du header utilisée par ce seul test. Chaque déclaration doit apparaître exactement une fois. Retirer ces trois annotations restitue exactement les anciens programmes lookup. Le header de production, les valeurs, les accès atomiques, le hook d’entrelacement, les assertions et `-Werror` sont conservés.

Le gate `.github/diagnostics/rpcs3runtime_refinement_core.py` utilise le nouveau `.github/diagnostics/rpcs3runtime_refinement_resume.py` pour authentifier les sept résultats partiels. Les commandes d’origine, le compilateur, le SDK, les programmes générés, les fichiers source et les octets des rapports restent vérifiés. Seul le hash du script de test complet est rattaché à sa correction lookup exacte ; aucun programme réutilisé ne change. Une modification imprévue de la source, du script, d’un rapport ou de la provenance invalide la reprise.

## Validations réalisées avant la reprise Apple

- Archive d’échec téléchargée et vérifiée : **56 287 octets**, SHA-256 `565b1af2d73692e410e863656a5dceae8d1214508263f1852950f7b19b289650`, artefact `12914878675`, 16 fichiers. Métadonnées GitHub, rapports et erreur d’origine préservés dans [failed-5796e165](evidence/rpcs3-runtime-refinement-20261029/apple-core/failed-5796e165/).
- Les **313 postimages natifs et 97 suppléments** du candidat correspondent au préflight échoué. La recette, le workflow et le patch canonique restent inchangés pendant cette reprise.
- GCC 13.3 Linux, avec `-Wunused-const-variable=2`, reproduit les trois diagnostics sur l’ancien programme à la compilation objet. Un essai préalable `-fsyntax-only` n’émettait pas les avertissements ; ce résultat reste conservé et n’est pas compté comme reproduction réussie.
- Les deux modes lookup corrigés, optimisé et ASan/UBSan, passent pour la référence et le candidat : **quatre exécutions**, sans benchmark ni résultat Apple/iPhone revendiqué par ces essais locaux.
- Le contrat de reprise authentifie **349 entrées**, conserve les **sept programmes Apple exacts** et rejette **36 preuves corrompues**. Aucun ancien programme natif ni CMake n’est exécuté par ce contrôle.

Preuves locales : [lookup-portability](evidence/rpcs3-runtime-refinement-20261029/apple-core/lookup-portability/) et [resume-contract.json](evidence/rpcs3-runtime-refinement-20261029/apple-core/resume-contract.json).

## Périmètre du build réalisé

La nouvelle tentative a exécuté seulement **quatre modes Apple** : lookup optimisé et ASan/UBSan, puis RSX write/sampler optimisé et ASan/UBSan. Les sept modes de la tentative échouée sont réutilisés avec leur provenance d’origine. Les **11 modes du candidat sont validés** ; les **17 modes globaux inchangés** et les **16 modes plus anciens** restent des preuves historiques séparées. Après le préflight, la recette a construit le Core iOS ARM64 et vérifié le binaire, ses 88 exports, ABI 30 et identités PPU/SPU.

Les trois changements runtime déjà intégrés restent ceux décrits dans [le rapport de source](rpcs3-runtime-refinement-2026-10-29.md) : comparaisons/copies directes d’un ou deux handles de descripteurs, conversion du délai après le balayage du timer, et rejet précoce des misses de clé/époque du prehash. La présente réparation de build n’ajoute aucune optimisation native.

Le lookup corrigé rejette l’entrelacement qui change l’époque entre les lectures. Le banc RSX confirme ses 96 scénarios de bindings, 200 courses d’enregistrement/écriture et zéro payload périmé accepté par le candidat. Ces résultats utilisent les adaptateurs du banc ; ils ne représentent pas un rendu réel sur GPU. Le TSan des hashes reste celui du run initial réussi individuellement, sans suppression et sans nouvelle exécution dans la reprise.

## Vérification indépendante des artefacts

Les trois ZIP ont été contrôlés par taille, SHA-256, CRC et contenu extrait : Core `12917652510`, prévalidation `12917655550` et diagnostics `12917722288`. Leurs identités figurent dans [artifact-verification.json](evidence/rpcs3-runtime-refinement-20261029/apple-core/success-f42573af/artifact-verification.json). Les rapports du préflight et des diagnostics finaux sont identiques ; les sept rapports réutilisés sont également identiques aux fichiers de la tentative échouée.

Le contrôle indépendant authentifie **349 entrées de validation**, **92 entrées de fabrication du Core**, **313 postimages natifs**, **97 suppléments**, les 88 exports réellement présents et les identités PPU/SPU. Par rapport au précédent Core vérifié `5b2a5614`, quatre postimages changent : les trois corps runtime et l’alias exact de compatibilité SPU ; **309 restent identiques**. Aucun postimage ne change pendant la réparation de cette tentative.

La vérification complète des sources et reçus utilise le validateur original. Sur Linux, seule la valeur du dernier argument `--report` est adaptée, depuis le répertoire local vers le répertoire Apple fixé, pour comparer les quatre commandes exécutées. Tous les autres arguments doivent être strictement identiques ; les rapports, les sources et le proof original ne sont pas modifiés. Cette vérification ne relance aucun test natif ni CMake. Reçu : [reuse-verification.json](evidence/rpcs3-runtime-refinement-20261029/apple-core/success-f42573af/reuse-verification.json).

Le contrôle de chargement passif parcourt les branches directes ARM64 `B/BL` jusqu’à une profondeur de 16 : 2 974 initialisateurs et 918 symboles d’initialisation, sans atteinte interdite détectée dans cette portée. Il ne couvre pas exhaustivement les appels indirects et n’est pas un `dlopen` exécuté sur iPhone.

## Mesures Apple du lot runtime, avec leurs compromis

Mesures macOS ARM64, Clang 22.1.8, sept séries par cas. Le timer et les descripteurs proviennent des modes réussis de la tentative initiale ; le lookup provient de la reprise réussie. Les programmes timer/descripteurs sont identiques à l’octet dans les deux commits. Les médianes, séries et dispersions complètes sont conservées dans [apple-measurements.json](evidence/rpcs3-runtime-refinement-20261029/apple-core/success-f42573af/apple-measurements.json).

La référence de ces bancs contient déjà les corrections du Core `5b2a5614`. Les timers incluent le balayage réel avec mutex/vecteurs hôte, les descripteurs utilisent un driver modélisé et le lookup ne mesure ni le hash d’une texture ni le temps d’une image. Aucun GPU ou gameplay iPhone n’est chronométré. Plusieurs séries se recouvrent ; aucun intervalle de confiance entre sessions ni seuil masquant une régression n’est utilisé.

| Banc / cas | Avant (ns) | Après (ns) | Variation de durée |
|---|---:|---:|---:|
| timer / 6/all_due | 57.2395 | 58.1787 | +1.64 % |
| timer / 6/alternating | 58.6017 | 59.1733 | +0.98 % |
| timer / 6/none_due | 57.1083 | 42.8130 | -25.03 % |
| timer / 32/all_due | 150.4680 | 156.4490 | +3.97 % |
| timer / 32/alternating | 119.1420 | 112.8030 | -5.32 % |
| timer / 32/none_due | 51.4851 | 47.6898 | -7.37 % |
| timer / 128/all_due | 444.8390 | 393.1190 | -11.63 % |
| timer / 128/alternating | 235.9680 | 235.5920 | -0.16 % |
| timer / 128/none_due | 152.4190 | 144.0850 | -5.47 % |
| timer / 1024/all_due | 2928.2700 | 2893.4700 | -1.19 % |
| timer / 1024/alternating | 1593.6500 | 1581.6100 | -0.76 % |
| timer / 1024/none_due | 1060.1400 | 1048.9700 | -1.05 % |
| descriptor / graphics_hits | 2.2844 | 2.4354 | +6.61 % |
| descriptor / changing_sets | 4.2415 | 4.1451 | -2.27 % |
| descriptor / alternating_bind_points | 2.3223 | 2.5314 | +9.00 % |
| lookup / hit | 2.8873 | 2.8858 | -0.05 % |
| lookup / epoch_miss | 2.8350 | 2.1662 | -23.59 % |
| lookup / key_miss | 3.0120 | 1.5658 | -48.01 % |

**Cinq médianes sont plus lentes sur dix-huit cas.** Les misses de clé/époque du lookup baissent respectivement d’environ 48 % et 24 % dans ce banc, et le cas réussi reste presque égal. Certains timers sans expiration baissent, tandis que trois autres petits lots et deux parcours descripteurs sont plus coûteux. Ces mesures ne prouvent aucun FPS supplémentaire sur iPhone.

## Limites et suites concrètes

Le journal de compilation conserve **500 avertissements ranlib** liés au bitcode LLVM 22 lu par Apple LLVM 17 et **huit avertissements de disponibilité iOS 17.4**. L’édition de liens et les vérifications du binaire réussissent ; la compilation n’est pas présentée comme exempte d’avertissements. Le Mach-O annonce toujours minOS 16.3 et SDK 18.5, alors que le chemin `os_sync_*` requiert 17.4 ; Runner et NeoSwap exigent déjà 17.4. Ce build n’établit pas le support isolé du Core sur iOS 16.3–17.3. Détails exacts, empreintes et répartition des 544 lignes d’avertissement : [log-review.json](evidence/rpcs3-runtime-refinement-20261029/apple-core/success-f42573af/log-review.json).

Le prochain travail de performance pertinent reste la réduction du coût des hits/alternances descripteurs et la mesure des chemins complets sur appareil. Les saccades BO2, le rendu des armes/avant-bras, le flickering des torches d’Assassin’s Creed et le gel GOW3 restent à vérifier avec les mêmes scènes sur l’iPhone. Leur résolution n’est pas établie par ce build. Le changement NeoSwap `Store.cpp` est du code de l’application hôte et nécessite une prochaine compilation de l’application ; il n’est pas livré dans ce dylib.

Le Core réussi peut être réutilisé pour une prochaine IPA autorisée tant que ses entrées exactes correspondent. Les mises à jour de documentation ne justifient ni une recompilation du moteur ni un rejeu de tests inchangés. **Cette reprise n’a produit aucune IPA, release ou tag et ne comporte aucune mesure de FPS sur iPhone.** Le Core historique `5b2a5614`, les tentatives échouées, l’IPA594 et les travaux MeloNX restent préservés.
