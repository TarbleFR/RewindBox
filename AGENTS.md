# RewindBox — consignes uniques

Ce fichier remplace toutes les anciennes consignes d’orchestration.
La demande actuelle de l’utilisateur prime ; répondre en français.

## Travail
Travailler, corriger, tester et compiler directement sur `Claude` (casse exacte).
Ne créer ni branche, worktree, issue, PR, équipe d’agents ou procédure de passation.
Ne pas recréer automatiquement les éléments supprimés.
Lire l’état de Git et préserver les modifications locales et concurrentes.
Commits et push ordinaires sur `Claude` autorisés ; jamais de force-push ni de reset destructif.
En cas de conflit, conserver les deux travaux et résoudre avant de pousser.
Corriger la cause, exécuter les contrôles utiles puis poursuivre la livraison autorisée.
Ne pas redemander une autorisation déjà donnée.
Si l’environnement bloque une action, décrire la limite réelle sans la contourner.
## Compilation et IPA de test
Réutiliser les workflows existants et la recette standard ; aucun workflow copié par build.
Suivre la compilation existante ; ne pas lancer de doublon.
Recompiler les composants modifiés et vérifier l’identité de ceux réutilisés.
Conserver les contrôles de sources, dépendances, ABI, signatures et empreintes.
Une compilation réussie ne prouve pas que le jeu fonctionne sur iPhone.
Les IPA de test restent privées : aucune release publique ni artefact IPA en clair sur GitHub.
Conserver le chiffrement du transport, les contrôles finaux et l’envoi privé du fichier vérifié.
Ne jamais enregistrer de clé privée, secret ou journal privé brut dans Git.

## Releases et sauvegardes
`main` reçoit uniquement l’état validé destiné à une release publique ; aucun développement dessus.
À chaque release, sauvegarder l’état exact livré sur `Backup`, avec sa version et son SHA.
Conserver les sauvegardes précédentes ; ne jamais fusionner `Backup` dans `Claude` ou `main`.
Vérifier la sauvegarde avant de publier la release et conserver ses preuves.
Publier uniquement dans le périmètre autorisé par l’utilisateur.

## Raisonnements et vérifications
Relire seulement les preuves pertinentes : causes établies, pistes réfutées et limites connues.
Conserver les résultats utiles dans leurs documents techniques et dans l’historique Git.
Ne pas refaire une enquête ou un test inchangé sans raison nouvelle.
Préserver données utilisateur, rendu, synchronisation, compatibilité, crédits et licences.
Distinguer corrigé, testé, compilé, livré et observé sur appareil ; aucun gain inventé.
Terminer par un bilan court : changement, vérification, résultat et éventuel blocage.
