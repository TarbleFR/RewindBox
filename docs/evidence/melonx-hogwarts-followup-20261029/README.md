# Preuves du deuxième lot Hogwarts — 29 octobre 2026

Le [rapport principal](../../melonx-hogwarts-followup-2026-10-29.md) décrit les mécanismes, les résultats et les limites. Cette collection concerne douze adaptateurs sur `c609b0d05a583d2d39f636f328830a6256439807` / engine82 ; le précédent lot local de onze adaptateurs n'y est pas inclus.

## Points d'entrée

- `integration.json` : delta des dix-sept sources, 86 entrées de préparation, empreintes des douze reçus, exceptions de composition documentées et huit assemblies vérifiées.
- Les douze `*-checks.json` : résultats des tests exécutés, entrées, préimages, postimages et frontières simulées.
- `managed-library-build.json` et les journaux associés : compilation complète initiale, sortie finale incomplète conservée et passe finale réussie.
- `source-recovery.json`, `dotnet-sdk-provenance.json`, `libhac-package-provenance.json` : récupération et identité des dépendances exactes.
- `independent-gpu-review.json`, `independent-texture-review.json`, `texture-integration-review.json` : revues et composition, sans replay des tests.
- `multirange-review.json` et `multirange-benchmark/` : comparaison supplémentaire ayant résolu le doute de coût CPU sur la première variante de découpage. Les quatre implémentations et le programme effectivement mesurés sont conservés ; seule `TwoPass` correspond au candidat final.
- `gpu-audit.md` : résultats GPU détaillés et pistes écartées.

Les timings sont ceux d'un hôte Linux x64/.NET 10.0.100. Les octets alloués ne sont pas la mémoire résidente du jeu. Aucun test de ce lot n'établit un gain de FPS sur iPhone. Le journal de restore public échoué et la sortie de compilation incomplète sont conservés pour ne pas transformer les étapes partielles en succès.
