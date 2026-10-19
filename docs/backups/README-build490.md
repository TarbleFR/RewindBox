# Sauvegarde du travail non poussé de la Build 490 (boîtiers 3D)

Le mainteneur a demandé, le 19 octobre 2026, d'attendre la livraison de la Build 489 avant de pousser la Build 490 (boîtiers 3D de la vue Jaquette, lecture du dos en douze langues, ouverture au lancement), pour ne pas bloquer la porte de livraison 489. Ce dossier ne contient qu'une sauvegarde durable de ces commits, hors des chemins produit et des entrées vérifiées par la porte 489 : aucun fichier de l'application n'est modifié par ce commit.

- `build490-gamebox.patch` : sortie de `git format-patch` des commits produit et documentation, faits sur `96e1ed4` ; SHA-256 `71beebe7fbd8dd564b95ff37a192d95ba940800d91984f86610e2f13597f7fc1`.
- Restauration : `git am docs/backups/build490-gamebox.patch` sur la tête de `Claude`, puis suppression de ce dossier dans le même cycle.

Ce patch n'est pas une livraison et n'a pas été construit en IPA.
