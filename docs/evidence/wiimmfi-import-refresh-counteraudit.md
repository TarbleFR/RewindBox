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
- Les fonctions Dart réelles d’import et de remplacement de snapshot passent avec le canal natif simulé. Refus TLS, sauvegarde invalide et annulation conservent la NAND et le profil courant. Un import accepté conserve le profil et crée la sauvegarde précédente.
- Analyse Dart ciblée réussie. Deux tentatives de test Flutter ciblé, dont une avec un dossier de compilation neuf, s’interrompent dans le compilateur local avant exécution. Aucun résultat de widget réussi n’est déduit de ces tentatives.
- Les fichiers TLS du contrôle utilisent les empreintes exigées par le Dolphin épinglé. Ce contrôle ne certifie pas la chaîne cryptographique de l’identité Wii.
- Core ABI 5 iPhoneOS arm64 et adaptateur d’import compilés au commit `d65376e07`, [run 46042143656](https://github.com/TarbleFR/RewindBox/actions/runs/46042143656). Les contrôles Apple du cycle de vie, du validateur BootMii et du réseau hors ligne passent. Le Core conserve 35 avertissements de compilation.
- Archive `15221387049` téléchargée et vérifiée, avec les neuf entrées source. SHA-256 du Core `34e322f6bcde3fcd2983189c8a060fb5a8f0abf1e6ec0c41b394bc5b726c8ebb`.

Le code 50130 reste une observation de l’iPhone avant installation de ces changements. La connexion Nintendo WFC, l’acceptation de l’identité et les courses réelles restent à vérifier sur appareil. [Parcours et protocole iPhone](wiimmfi-session-diagnostic.md).
