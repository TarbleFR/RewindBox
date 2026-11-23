# Grand nettoyage de l’historique GitHub Actions — 23 novembre 2026

## Demande et résultat

Le mainteneur demande un grand nettoyage des Actions en gardant les 500 dernières
exécutions. **2 584 exécutions ont été supprimées** en deux passages, toutes
vérifiées. Le 23 novembre à 15:31 UTC, **940 exécutions restent** contre 3 485 au
départ :

- les **500 plus récentes**, depuis le 21 novembre à 04:58:09 UTC ;
- **416 plus anciennes encore utilisées** (détail ci-dessous) ;
- 24 exécutions sorties de la fenêtre des 500 parce que 24 nouvelles sont arrivées
  pendant le second passage.

| Exécutions supprimées | Nombre |
| --- | ---: |
| Ignorées (`skipped`) | 1 195 |
| Réussies | 916 |
| Échecs | 399 |
| Annulées | 74 |
| **Total** | **2 584** |

Aucune exécution supprimée n’est encore listée. Les 916 exécutions que protégeait le
second plan sont toutes présentes. Ni conflit, ni attente de quota.

## Ce qui reste et pourquoi

Supprimer une exécution supprime ses artefacts, ses journaux et ses jobs. Le code
actuel télécharge ou vérifie encore certains de ces éléments : les supprimer
casserait des compilations ou des livraisons. Les 416 anciennes exécutions
conservées au second passage sont classées par première raison applicable :

| Raison | Exécutions |
| --- | ---: |
| Citée par un fichier exécutable de `Claude` : workflows, diagnostics, épinglages, recettes, tests, sources | 363 |
| Dernier succès d’un workflow actif depuis le 13 novembre | 23 |
| Exécution non terminée, dont les neuf orphelins refusés le 13 novembre | 9 |
| Exécution de `main` | 8 |
| Citée seulement par un fichier exécutable de `main` | 7 |
| Citée par le manifeste de livraison courant `build-utils/delivery/826.json` | 4 |
| Citée par une preuve que lit une route active (MeloNX, S2Arm, XeniOS, reçu 608) | 2 |

Une mention purement historique ne protège pas une exécution : documentation,
preuves, anciens manifestes de livraison, inventaires des nettoyages précédents. Les
reçus restent dans Git, mais les liens vers les exécutions supprimées ne mènent plus
à rien. Les exécutions créées après un instantané restent toujours.

## Artefacts

Les 2 584 exécutions supprimées portaient 3 017 artefacts. À 15:31 UTC, GitHub en
listait encore **3 008 (131,3 Go)**. Ils sont détachés de leur exécution
(`workflow_run` vide), mais le compteur de stockage ne baisse pas encore.

Aucun artefact détaché ne subsiste des nettoyages précédents : GitHub les retire en
différé. Ce nettoyage ne supprime aucun artefact directement.

## Outil, garde-fous et déroulé

L’outil existant [`cleanup_actions.py`](../build-utils/maintenance/cleanup_actions.py)
n’autorise qu’une suppression d’exécution terminée figurant dans un plan revu, figé
par empreinte SHA-256. Il a reçu ces changements :

- **Seuil de conservation** : un plan peut garder plus de 300 exécutions
  (`keep_recent` ≥ 300, ici 500). La borne de suppression passe à 2 700.
- **Liste qui bouge** : une liste d’exécutions modifiée pendant sa lecture est relue
  entièrement, en six tentatives au plus, au lieu d’arrêter le nettoyage. `Claude`
  reçoit un push toutes les quelques minutes.
- **Garde de références** : `Claude` peut avancer pendant l’opération.
  - À chaque contrôle, chaque fichier modifié depuis le commit d’exécution est relu.
  - Une cible qu’il cite nouvellement (exécution ou artefact) est conservée. Le second
    passage ignore les citations que la version revue du même fichier contenait déjà.
  - Un plan modifié, un arbre incomplet ou un fichier illisible arrête tout.
- **Erreurs serveur** : une erreur GitHub 500, 502, 503 ou 504 est relancée trois
  fois (15, 30 et 45 s). Une exécution qui échoue encore est conservée et notée. Au
  delà de dix exécutions dans ce cas, le nettoyage s’arrête.

Les 48 tests de sécurité, dont 11 nouveaux, passent localement et dans chaque
lanceur avant toute suppression. Un passage à blanc local contre la liste réelle a
trouvé 2 556 candidats, identiques à la liste revue du premier plan.

Déroulé :

1. Le commit `19b8affb` a réintroduit l’ancien lanceur
   `.github/workflows/actions-history-cleanup.yml`. GitHub garde ce chemin désactivé
   depuis le rangement du 13 novembre (`disabled_manually`) : rien n’a démarré, rien
   n’a été supprimé.
2. **Premier passage** (commit `974031ea`, exécution
   [45188139428](https://github.com/TarbleFR/RewindBox/actions/runs/45188139428),
   [plan](../build-utils/maintenance/actions-cleanup-2026-11-23.json)) :
   - 1 008 suppressions sur 2 556 candidats ;
   - arrêt volontaire quand GitHub a répondu HTTP 500 à la suppression de
     `43544952449`, qui est restée listée.

   Le garde a retenu 20 cibles citées dans des fichiers modifiés par d’autres
   sessions (tableau de suivi, documentation de la boîte de jeu) :
   - 19 de ces citations existaient déjà avant le plan. Elles sont redevenues des
     cibles au second passage, puisqu’une mention historique ne protège pas.
   - La dernière, `39378255052`, citée par la documentation de la Build 494, était
     déjà supprimée quand la modification est arrivée.
3. **Second passage** (commit `10da90d7`, exécution
   [45195675761](https://github.com/TarbleFR/RewindBox/actions/runs/45195675761),
   [plan](../build-utils/maintenance/actions-cleanup-2026-11-23-pass2.json)) :
   - même politique, recalculée sur la tête de 14:32 UTC ;
   - 1 576 cibles, 1 576 suppressions, dont `43544952449` ;
   - zéro conflit, zéro erreur serveur restante.

Le lanceur ponctuel `.github/workflows/actions-cleanup-2026-11-23.yml` est retiré
après vérification. Les plans, l’outil et ses tests restent dans le dépôt.

Les commits `19b8affb`, `974031ea` et `10da90d7` touchent des chemins produit
(`build-utils/maintenance`, `test`), sans effet sur l’application :
- les deux premiers sont classés `sourceOnly` (cible 827) dans le brouillon de la 826 ;
- le troisième reste à classer à la prochaine livraison.

## Preuves

- Reçus ZIP téléchargés depuis Actions, vérifiés par l’empreinte API, liés aux plans
  par leur SHA-256 : [premier passage](evidence/actions-cleanup-2026-11-23/pass1-receipt.json)
  ([origine](evidence/actions-cleanup-2026-11-23/pass1-origin.json)) et
  [second passage](evidence/actions-cleanup-2026-11-23/pass2-receipt.json)
  ([origine](evidence/actions-cleanup-2026-11-23/pass2-origin.json)).
- [Vérification combinée](evidence/actions-cleanup-2026-11-23/verification.json) et
  [identifiants restants](evidence/actions-cleanup-2026-11-23/remaining-run-ids.json),
  d’après une relecture complète de GitHub après le second passage.

Ce nettoyage ne modifie aucune branche, release, définition de workflow ou autre
artefact. Il ne compile ni n’installe aucune IPA ou Core.
