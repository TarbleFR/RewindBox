# Trois branches, sans perdre les travaux

**Fonctionnement actuel :** travailler directement sur `Claude` selon
[AGENTS.md](../AGENTS.md). Aucune issue, branche ou worktree supplémentaire sans
demande explicite. Ce document conserve les reçus et la récupération des anciennes
archives ; il n'impose aucune passation ni publication dans Backup.

Le mainteneur a demandé le 13 novembre 2026 de conserver uniquement `main`,
`Claude` et `Backup` comme branches distantes durables.

- `main` : branche de référence existante, conservée.
- `Claude` : intégration revue, moteurs épinglés et recette commune.
- `Backup` : index des anciens noms et de leurs SHA exacts, avec les historiques
  complets conservés par les parents du commit d'archive. Ce n'est pas une fusion
  fonctionnelle et cela ne signifie pas que les lots sont approuvés ou livrés.

[Archive vérifiée](https://github.com/TarbleFR/RewindBox/blob/4e2ec7580e619e4c16c7e54182b912ef18ee4421/branch-archive.json)
· [Ancienne passation (référence historique, non requise)](https://github.com/TarbleFR/RewindBox/issues/179)

Le nettoyage a retiré 35 anciennes branches. Les sept premières étaient déjà
intégrées ; les 28 autres ont été archivées avant suppression. Le manifeste de
Backup couvre aussi les références conservées lors des instantanés. Une avancée
MeloNX concurrente a interrompu le premier passage ; sa nouvelle tête `f5abc0ac`
a été ajoutée à Backup avant de reprendre. [Bilan et reçus](coordination-cleanup-2026-11-13.md).

## Reprendre une branche supprimée

`git fetch origin Backup` récupère l'archive. Afficher son index avec
`git show origin/Backup:branch-archive.json`, lire le SHA de l'ancien nom,
puis inspecter les fichiers avec `git show <SHA>:<chemin>` ou les différences avec
`git diff origin/Claude <SHA> -- <chemins>`. Reprendre uniquement le delta utile
sur `Claude`, après revue. Aucune branche de reprise n'est nécessaire. Conserver les modifications locales déjà présentes ; ne pas
faire de reset ou de nettoyage de leur espace de travail.

Ne jamais fusionner Backup dans Claude ou main : ses parents conservent aussi des
travaux non revus. Le responsable sélectionne les commits à intégrer après revue.
Un ancien workflow lié à une branche supprimée peut nécessiter une nouvelle route
sur Claude ; son run et ses artefacts existants restent identifiables par ID/SHA.

## Continuer à deux comptes

Les deux comptes travaillent sur `Claude`, avec un seul auteur à la fois par
chemin partagé. Relire la branche distante avant de pousser et préserver les
changements concurrents. Une courte mise à jour de la tâche suffit.
L'ancien protocole Backup + issue #179 + ACK reste consultable dans l'historique
Git ; il n'est plus requis et l'issue ne doit pas être recréée automatiquement.

La PR Dependabot #163 est fermée sans fusion, sa tête et son historique sont
archivés. Les alertes de sécurité ne sont pas modifiées. Un nouvel agent ou bot
peut encore créer une branche : le présent nettoyage ne change pas ses droits.
