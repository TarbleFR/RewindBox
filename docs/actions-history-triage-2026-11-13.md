# Tri de l’historique Actions — 13 novembre 2026

Le mainteneur demande un tri massif pendant la compilation du Core 745.
Instantané : 1 607 exécutions, 2 524 artefacts associés à 666 exécutions.
Le plan fixe a supprimé ses 360 candidats : 177 échecs, 101 réussites, 42 annulations
et 40 exécutions ignorées, sans artefact ni référence retenue.

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
## Résultat vérifié

Le run [43346257896](https://github.com/TarbleFR/RewindBox/actions/runs/43346257896)
est terminé avec succès, source `058c6fc33a53a13667579b9d4636524f9a644207`, tentative 1.
Les 360 demandes ont reçu HTTP 204 : aucun conflit, aucune absence préalable, zéro
candidat restant. Le total est passé de 1 611 au démarrage à 1 251 ; quatre nouveaux
runs avaient été créés depuis l'inventaire initial de 1 607.

Le ZIP du reçu (artefact 14003416137, 935 070 octets) est lié à son empreinte API
`ee935ec2cc0c7214afa907095fc7187f906e7c3de91baacd988b9d57d5949f9e`.
Le reçu, le journal et une nouvelle lecture complète de GitHub concordent : les 360
IDs supprimés sont absents ; les 1 247 IDs protégés, dont Core 745, la référence
Dolphin 41746963325 et les neuf anciens orphelins, sont présents. La revue
indépendante des résultats a passé ses 17 contrôles.

[Reçu exact](evidence/actions-cleanup-2026-11-13-bulk/receipt.json) ·
[Vérification](evidence/actions-cleanup-2026-11-13-bulk/verification.json) ·
[Origine](evidence/actions-cleanup-2026-11-13-bulk/origin.json) ·
[IDs restants vérifiés](evidence/actions-cleanup-2026-11-13-bulk/remaining-run-ids.json).
Le lanceur ponctuel est retiré après ce succès ; le plan et ses tests restent dans
le dépôt. Ce résultat n'autorise pas un nouveau passage ou la suppression des
preuves protégées.
