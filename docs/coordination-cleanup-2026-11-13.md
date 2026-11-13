# Bilan du rangement RewindBox — 13 novembre 2026

## Résultat sur les branches

Seules `main`, `Claude` et `Backup` restent comme branches distantes à la vérification finale. **35 anciennes branches ont été supprimées**, après conservation de leurs travaux : 7 déjà intégrées, puis 28 archivées. Aucun historique de produit n'a été réécrit.

| Branche | Rôle | Référence vérifiée |
| --- | --- | --- |
| main | Référence existante, non modifiée par le nettoyage | `c60bcb5cad02626a85487f6577782784458d2fb9` |
| Claude | Intégration revue et livraisons | Avance avec les travaux de la session principale ; voir son HEAD courant |
| Backup | Index des anciens noms/SHA et conservation des historiques par les parents Git | `4e2ec7580e619e4c16c7e54182b912ef18ee4421` |

[Manifeste de récupération](https://github.com/TarbleFR/RewindBox/blob/4e2ec7580e619e4c16c7e54182b912ef18ee4421/branch-archive.json) · [Procédure](branch-archive.md).

Backup n'est pas une fusion fonctionnelle. Les sources non revues ne deviennent pas livrées en étant archivées. L'ancien commit Backup est un parent du nouveau ; les anciens instantanés restent accessibles. Le premier passage s'est arrêté lorsqu'une session MeloNX a avancé sa branche. La nouvelle tête `f5abc0ac1cc7c93882f08c4742c239679d046f21` a été conservée dans Backup, puis le nettoyage a repris. Sa récupération depuis GitHub a été testée dans un dépôt vierge après suppression de la branche.

Les trois reçus de suppression, téléchargés depuis Actions et vérifiés par SHA-256, comptent **7 + 7 + 21 noms distincts** :

- [Premier passage, branches intégrées](evidence/coordination-cleanup-2026-11-13/initial-merged-branches.json), run [43333183319](https://github.com/TarbleFR/RewindBox/actions/runs/43333183319).
- [Premier passage d'archive, arrêté sur l'avancée concurrente](evidence/coordination-cleanup-2026-11-13/archive-first-pass.json), job consolidation du run [43334427815](https://github.com/TarbleFR/RewindBox/actions/runs/43334427815).
- [Passage final, réussi](evidence/coordination-cleanup-2026-11-13/archive-final-pass.json), run [43334952735](https://github.com/TarbleFR/RewindBox/actions/runs/43334952735).

La PR Dependabot #163 a été fermée sans fusion, sa source conservée. Les alertes de sécurité sont inchangées. Ce rangement et les consignes communes ne retirent pas aux agents ou aux bots leurs droits de créer des branches.

## Coordination entre les deux comptes

- `AGENTS.md` renvoie au tableau commun comme contrat de travail. Les anciennes tâches restent consultables dans une version immuable du tableau ; son index actif est réduit d'environ 6 700 à 450 lignes.
- La [discussion de passation #179](https://github.com/TarbleFR/RewindBox/issues/179) est accessible aux deux comptes. Chaque remise identifie source complète, propriétaire, relecteur, chemins, dépendances, tests et run/attempt/job ; le destinataire accuse réception par `ACK <SHA>`.
- Les états source intégrée, Core compilé, moteur épinglé, IPA livrée et résultat sur iPhone sont séparés. Une nouvelle source demande une nouvelle revue. Un identifiant de session privée inaccessible n'est plus l'unique moyen de transmettre du travail.
- `tools/coordination/status.py --source <SHA>` rapporte les branches, Backup, les dernières passations et les exécutions existantes avant un nouveau déclenchement. Les worktrees restent locaux ; les lots non intégrés se sauvegardent dans Backup suivant le protocole documenté.

## Recette et compilations

Les producteurs XeniOS et S2Arm ont une route explicite depuis Claude, compatible avec les trois branches conservées. Un push ordinaire n'est pas une demande de compilation de moteur. Les producteurs identifient leur source et ne s'annulent pas mutuellement ; seuls les contrôles Xenia explicitement demandés peuvent remplacer leurs propres contrôles précédents. Les règles et marqueurs sont décrits dans la [recette standard](standard-delivery-recipe.md).

La ligne expérimentale S2Arm 801+ reste archivée : ses anciens gardes exigent toujours son ancienne branche. Elle ne doit pas être relancée telle quelle depuis Claude. Cette limite ne bloque pas la livraison commune ; une réactivation demanderait une migration séparée de ses gardes. Les producteurs de la livraison commune ont été adaptés à Claude, en conservant la provenance des composants historiques.

Le contrat S2Arm authentifie la branche du run producteur et conserve la compatibilité avec les anciens moteurs déjà épinglés. Le nettoyage n'a remplacé aucun moteur ou épinglage. Les 67 contrôles ciblés et 70 contrôles de réécriture ont passé ; les routes ont également été observées ignorées sur un push de maintenance ordinaire.

Le correctif de test macOS appartient à la session MeloNX : la version complète testée a été rétablie après une intégration partielle, puis l'avancée du propriétaire a été conservée par la session principale. Le contrôle natif macOS [43333183285](https://github.com/TarbleFR/RewindBox/actions/runs/43333183285), job `131582693867`, est réussi. Les quatre correctifs des tests du lot 10 ont été intégrés par la session principale en `30ee5beb` après transmission par le mainteneur. Le gel du Core 745 par cette même session en `f4fb22fd` a été conservé pendant la maintenance ; ce bilan ne le présente pas comme un moteur déjà livré ou un gain mesuré sur iPhone.

Le contrôle du Core 745 a ensuite échoué **avant compilation**, au run [43336528859](https://github.com/TarbleFR/RewindBox/actions/runs/43336528859/job/131593993742) : la dépendance historique `12883480724` est indisponible (404), avec une expiration archivée au 12 novembre 08:25:19Z. La cause et les empreintes ont été transmises à main dans [la passation #179](https://github.com/TarbleFR/RewindBox/issues/179#issuecomment-6840025797). La remise à disposition authentifiée de cette dépendance reste à traiter par le propriétaire ; relancer à l’identique ne corrige pas cette expiration. Le rangement des branches ne résout pas ce blocage. Main l’a repris dans `6716babd` et a transmis au propriétaire MeloNX la récupération authentifiée, avec des copies plus récentes à examiner ([passation](https://github.com/TarbleFR/RewindBox/issues/179#issuecomment-6840099916)).

## Actions et conservation des preuves

Quatre anciens workflows sont confirmés `disabled_manually` : `hogwarts606-host-recovery.yml`, `rewind608-retro-achievements-delivery.yml`, `rewind609-hogwarts-liveness-delivery.yml` et `rewind610-delivery.yml`. Le [reçu final](evidence/coordination-cleanup-2026-11-13/retirement-final.json) et la [vérification distante](evidence/coordination-cleanup-2026-11-13/workflows-final-state.json) distinguent les demandes de mutation de leur confirmation.

**532 anciens runs `skipped` supprimés**, zéro conflit et zéro candidat restant dans le plan. Le job history `131586909223` du run [43334427815](https://github.com/TarbleFR/RewindBox/actions/runs/43334427815) est réussi. Le [reçu complet](evidence/coordination-cleanup-2026-11-13/actions-history-final.json) a été téléchargé, son archive vérifiée par SHA-256 et l’absence des 532 identifiants contrôlée dans l’inventaire final. Chaque suppression exigeait une identité inchangée, aucun job exécuté et aucun artefact ; les 300 exécutions les plus récentes, les dépendances explicites et les nouveaux runs étaient protégés. Le nombre total est passé de 2 099 à 1 596 pendant que 29 nouvelles exécutions arrivaient.

**Neuf anciennes entrées vides restent en attente.** Leurs identités, ancienneté, jobs vides et absence d’artefacts ont été revérifiés. Les annulations ordinaires/forcées n’ont pas produit d’état terminal confirmé. Le passage final [43337757433](https://github.com/TarbleFR/RewindBox/actions/runs/43337757433) a reçu **HTTP 403 pour les neuf demandes de suppression**, sans répétition des demandes refusées. Son statut vert signifie que le traitement et le reçu sont terminés, pas que les suppressions ont réussi. [Reçu des refus](evidence/coordination-cleanup-2026-11-13/orphaned-runs-final.json). Ces neuf IDs ne sont pas comptés parmi les 532 suppressions. La raison détaillée du refus n’est pas établie par ce reçu ; aucune suppression n’est annoncée pour eux.

Les anciens YAML utilisés comme entrées de contrats historiques sont conservés. Les scripts ponctuels de lancement du rangement sont retirés après leurs exécutions ; leurs sources, plans, reçus et commits restent traçables. Aucun nettoyage d'artefact de moteur ou d'IPA n'a été demandé par cette maintenance.

## Limites du bilan

La maintenance améliore les passations, la sélection des travaux et les déclenchements. Elle ne prouve aucun gain FPS, thermique ou mémoire en jeu et ne livre pas une nouvelle IPA. Les résultats de compilation des sessions propriétaires et les essais iPhone doivent être rapportés avec leurs identités propres.
