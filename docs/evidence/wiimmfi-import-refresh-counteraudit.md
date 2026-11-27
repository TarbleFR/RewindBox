# Wiimmfi — import et diagnostic du 27 novembre 2026

Revue de `4526a952f`, après les correctifs du code 50130. Trois défauts supplémentaires sont corrigés.

| Défaut confirmé | Correction |
| --- | --- |
| L’import natif accepte des fichiers TLS de taille plausible que le contrôle de lancement rejette ensuite. Le remplacement de la NAND peut donc précéder le refus. | Les trois fichiers sont vérifiés dans le dossier temporaire avant le succès de l’import. Un refus renvoie une erreur TLS et la transaction conserve la NAND courante. |
| L’interface conserve la preuve de chargement et les compteurs de la console précédente après un nouvel import. | L’extraction réussie invalide ces éléments dans le bridge. Ils seront renseignés par une prochaine tentative. Une extraction annulée ensuite peut également les avoir invalidés. |
| Le bouton de diagnostic peut reprendre le cache réseau pendant cinq minutes après un changement de connexion. | Une demande explicite renouvelle la mesure. Les appels simultanés partagent la même mesure en cours. Le cache reste disponible pour les lecteurs ordinaires. |

## Vérifications

- Le banc de cycle de vie extrait les corps C++ du produit. L’ancien import accepte les fichiers TLS refusés et échoue au contrôle renforcé. Le correctif les rejette avant retour de succès. Les vingt alternances Wii/GameCube passent avec les contrôles d’identité existants.
- Le corps Dart de `diagnose` est exécuté avec une sonde déterministe dans un banc local. Cache, renouvellement, deux demandes simultanées, horloge reculée, état NAND frais et refus lorsque le service est désactivé passent.
- Les fichiers TLS du contrôle utilisent les empreintes exigées par le Dolphin épinglé. Ce contrôle ne certifie pas la chaîne cryptographique de l’identité Wii.

Le code 50130 reste une observation de l’iPhone avant installation de ces changements. La connexion Nintendo WFC, l’acceptation de l’identité et les courses réelles restent à vérifier sur appareil. [Parcours et protocole iPhone](wiimmfi-session-diagnostic.md).
