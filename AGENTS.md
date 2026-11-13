# RewindBox — travailler simplement

La demande actuelle prime sur les anciennes consignes. Répondre en français.
Aller jusqu’au résultat demandé, sans élargir la mission.

## 1. Travailler sur Claude

- Développer, corriger, tester et compiler sur `Claude` (casse exacte).
- Ne créer ni branche, worktree, issue, PR ou équipe ; ne rien recréer automatiquement.
- Avant modification : vérifier branche, HEAD et changements locaux ; préserver le travail existant.
- Avant chaque push : relire la tête distante et résoudre les conflits sans perdre de travail.
- Commits et push ordinaires sur `Claude` autorisés ; aucun force-push, reset ou nettoyage destructif.

## 2. Corriger sans détour

- Lire uniquement les sources, [contraintes](docs/PROJECT_RULES.md) et [preuves](docs/AI_TASK_BOARD.md) pertinentes.
- Corriger la cause par le changement le plus simple, sans refonte hors sujet.
- Cores et IPA : aucun nouveau test ni suite approfondie automatique ; compiler les derniers ajouts.
- Conserver les contrôles indispensables ; marquer les tests non exécutés, sans masquer erreurs ni limites.
- Signaler une limite réelle sans la contourner ; poursuivre ce qui reste réalisable.
- Ne pas redemander une autorisation acquise ni imposer de procédure de suivi.

## 3. Compiler et livrer les tests

- Utiliser la [recette standard](docs/standard-delivery-recipe.md) et le manifeste courant ; aucun workflow copié par build.
- Vérifier source et runs existants ; suivre la compilation correspondante sans doublon.
- Recompiler uniquement si sources, dépendances, outils ou configuration changent ; réutiliser les autres moteurs avec leurs empreintes vérifiées. MeloNX : `build-smoke` ; IPA : groupes Flutter/natifs `not-run`.
- Conserver les contrôles de configuration, outils, ABI, signatures et empreintes.
- Documentation seule : `[skip ci]`, sans compilation.
- Garder les IPA de test privées, avec transport chiffré et protections existantes.
- Vérifier l’IPA finale avant livraison privée, puis la remettre aussitôt à l’utilisateur ; analyses et optimisations ensuite. Ne jamais publier une IPA de test.
- Aucun secret, clé privée, journal privé brut ni artefact IPA de test en clair dans GitHub.

## 4. Publier et sauvegarder

- `main` reçoit uniquement les releases publiques validées et autorisées ; aucun développement dessus.
- Avant chaque release : sauvegarder l’état validé sur `Backup` (version + SHA), puis vérifier.
- Préserver toutes les sauvegardes ; ne jamais fusionner `Backup` dans `Claude` ou `main`.

## 5. Garder les preuves utiles

- Conserver causes, pistes réfutées, résultats et limites dans les preuves techniques et l’historique.
- Consulter les archives au besoin ; vérifier leurs statuts sans réactiver leurs procédures.
- Préserver données utilisateur, rendu, synchronisation, compatibilité, crédits et licences.
- Distinguer corrigé, testé, compilé, livré et observé sur appareil ; aucun gain non mesuré.
- Une compilation réussie ne prouve pas que le jeu fonctionne sur iPhone.
- Bilan court : changement, vérification, résultat et éventuel blocage.
