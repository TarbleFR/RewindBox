# Tri de l’historique Actions — 13 novembre 2026

Le mainteneur demande un tri massif pendant la compilation du Core 745.
Instantané : 1 607 exécutions, 2 524 artefacts associés à 666 exécutions.
Le plan fixe retient 360 candidats : 177 échecs, 101 réussites, 42 annulations
et 40 exécutions ignorées, sans artefact ni référence retenue. Ce sont des
candidats, pas un nombre de suppressions déjà effectuées.

Sont conservés les 300 plus récents, toute exécution non terminale, tous les
runs de main/Backup, les producteurs ayant un artefact, les 720 IDs cités par
les sources/preuves courantes, et le dernier succès/échec de chaque workflow
présent. Les inventaires des nettoyages précédents ne sont pas traités comme
des dépendances produit. Les neuf anciennes files refusées avec HTTP 403
sont exclues et ne seront pas retentées. Les références de main/Backup n’ont
pas été entièrement relues : leurs propres exécutions restent toutes protégées.

Avant chaque suppression : identité du run inchangée, statut terminé, aucun
artefact même expiré et historique complet des jobs sans job actif. Une
réponse ambiguë préserve le run. La borne, le plan par empreinte et la branche
sont vérifiés ; un refus non lié au quota arrête le traitement. Toute évolution
de Claude arrête ce plan : attendre sa fin avant de publier un nouvel épinglage.

Code : revue indépendante sans blocage, 37 tests de sécurité exécutés avec succès.
Core 745 reste au run 43344184896 ; aucun moteur n’est recompilé par ce nettoyage.
La relecture indépendante de12 967 fichiers a protégé en plus le run41746963325,
cité par DolphinMenuOrientationTests.mm ; il est exclu du plan final.
Résultat réel, reçu et inventaire final à renseigner après le run.
