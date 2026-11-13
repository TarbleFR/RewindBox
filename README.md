# RewindBox — Backup

Cette branche conserve les historiques complets des anciennes branches distantes. Le manifeste `branch-archive.json` associe chaque nom à son commit exact et à ses éventuelles pull requests.

Les commits archivés sont des ancêtres de cette branche : leurs fichiers et leur historique restent accessibles. Cette arborescence est un index d'archives, pas une compilation ni une fusion fonctionnelle des travaux.

## Reprendre un travail

1. `git fetch origin Backup`
2. Lire le SHA exact dans `branch-archive.json`.
3. `git switch -c reprise-locale <SHA>` (branche locale).
4. Relire le delta avec le responsable du composant avant de sélectionner les corrections dans Claude.

**Ne jamais fusionner Backup dans main ou Claude.** L'archivage ne signifie pas que les modifications sont intégrées, testées ou livrées. Ne pas supprimer cette branche ni réécrire son historique. Tout ajout futur doit conserver son HEAD comme parent.

Les trois branches distantes durables sont `main`, `Claude` et `Backup`. Les commits de ce dépôt ne sauvegardent pas les fichiers locaux non commités ou non poussés des autres postes.
