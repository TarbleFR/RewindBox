# Trois branches, sans perdre les travaux

Le mainteneur a demandé le 13 novembre 2026 de conserver uniquement `main`,
`Claude` et `Backup` comme branches distantes durables.

- `main` : branche de référence existante, conservée.
- `Claude` : intégration revue, moteurs épinglés et recette commune.
- `Backup` : index des anciens noms et de leurs SHA exacts, avec les historiques
  complets conservés par les parents du commit d'archive. Ce n'est pas une fusion
  fonctionnelle et cela ne signifie pas que les lots sont approuvés ou livrés.

[Archive vérifiée](https://github.com/TarbleFR/RewindBox/blob/d6374597dc2d209fe4bb55febd16bb89c44f2594/branch-archive.json)
· [Passations entre comptes](https://github.com/TarbleFR/RewindBox/issues/179)

## Reprendre une branche supprimée

`git fetch origin Backup` récupère l'archive. Afficher son index avec
`git show origin/Backup:branch-archive.json`, lire le SHA de l'ancien nom,
puis créer une branche **locale** avec
`git switch -c reprise-locale <SHA>`. Le code, les commits antérieurs et les fichiers
restent accessibles. Conserver les modifications locales déjà présentes ; ne pas
faire de reset ou de nettoyage de leur espace de travail.

Ne jamais fusionner Backup dans Claude ou main : ses parents conservent aussi des
travaux non revus. Le responsable sélectionne les commits à intégrer après revue.
Un ancien workflow lié à une branche supprimée peut nécessiter une nouvelle route
sur Claude ; son run et ses artefacts existants restent identifiables par ID/SHA.

## Continuer à deux comptes

Les branches locales et worktrees isolent les modifications. Un lot non intégré
peut être publié comme commit sauvegardé dans Backup : conserver l'ancien HEAD
Backup comme premier parent, ajouter le SHA du lot comme parent supplémentaire,
mettre à jour son entrée dans le manifeste et avancer Backup sans réécrire son
historique. Relire la référence distante et vérifier que le SHA du lot est son
ancêtre avant de déclarer la passation. Une mise à jour concurrente impose de
repartir du nouveau HEAD, jamais de forcer.

La discussion #179 porte source complète, propriétaire, chemins, dépendances,
preuves exécutées et prochaine action ; le destinataire répond `ACK <SHA>`.
Le tableau commun conserve les tâches. Une source nouvelle invalide l'ancienne
relecture. La session principale intègre les commits choisis dans Claude avant de
figer les contrats et déclencher les routes existantes des moteurs.

La PR Dependabot #163 est fermée sans fusion, sa tête et son historique sont
archivés. Les alertes de sécurité ne sont pas modifiées. Un nouvel agent ou bot
peut encore créer une branche : le présent nettoyage ne change pas ses droits.
