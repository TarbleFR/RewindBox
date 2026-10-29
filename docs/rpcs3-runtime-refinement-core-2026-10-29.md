# RPCS3 — reprise du Core après l’échec Clang du 29 octobre 2026

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

## Périmètre du build demandé

La nouvelle tentative doit exécuter seulement **quatre modes Apple** : lookup optimisé et ASan/UBSan, puis RSX write/sampler optimisé et ASan/UBSan. Les sept modes de la tentative échouée sont réutilisés avec leur provenance d’origine. Les **17 modes globaux inchangés** et les **16 modes plus anciens** restent des preuves historiques séparées. Après le préflight, la recette construit le Core iOS ARM64 et vérifie le binaire, ses 88 exports, ABI 30 et identités PPU/SPU.

Les trois changements runtime déjà intégrés restent ceux décrits dans [le rapport de source](rpcs3-runtime-refinement-2026-10-29.md) : comparaisons/copies directes d’un ou deux handles de descripteurs, conversion du délai après le balayage du timer, et rejet précoce des misses de clé/époque du prehash. La présente réparation de build n’ajoute aucune optimisation native.

Aucun nouveau Core réussi, IPA, release, gain de FPS ou résultat de gameplay n’est encore établi par ce point de reprise. Les anciens avertissements de toolchain et la différence entre le minos 16.3 du dylib et les API `os_sync_*` requérant iOS 17.4 restent à distinguer de l’erreur de test corrigée ici.
