# Wiimmfi et Mario Kart Wii sur iPhone

## Défauts confirmés

- ABI 4 contrôlait `User/Wii` mais l’amont peut modifier `D_WIIROOT_IDX` via `NANDRootPath`. IOS charge les clés depuis ce chemin, tandis que les certificats viennent de `D_SESSION_WIIROOT_IDX`. Le Core ABI 5 utilise la NAND importée pour toute la session Wiimmfi, vérifie les chemins avant la libération du jeu, observe l’identité réellement chargée par IOS et rétablit le chemin précédent après l’arrêt.
- L’ancien état « structure reconnue » acceptait des fichiers TLS à la bonne taille mais rejetés par IOS SSL. Le contrôle reprend les trois empreintes attendues par le Dolphin épinglé, sans écrire leurs valeurs dans le diagnostic. IOS conserve ses contrôles TLS. L’identité Wii et les fichiers TLS IOS sont des vérifications distinctes.
- Le relais DNS pouvait transmettre à `getaddrinfo` des champs de sortie non initialisés. Il initialise la structure et ne lit que les quatre champs d’entrée, conformément au [contrat iOS](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man3/getaddrinfo.3.html). Darwin n’expose pas forcément d’adresse de diffusion ni de masque IPv4 sur les interfaces point à point. La détection d’interface protège ces lectures et n’utilise pas l’adresse du pair VPN comme adresse de diffusion.
- Le site public et le réseau du jeu donnent des signaux différents. Le diagnostic Oui/Non/Non testé est remplacé par les signaux observables. Le code `23934` désigne un paramètre de connexion invalide et ne désigne pas à lui seul une identité Wii refusée.

Aucun code en jeu ni dump réel fourni pour cette revue. Les défauts ci-dessus sont reproductibles dans l’intégration, mais leur présence sur l’iPhone de l’utilisateur et le point de refus du serveur restent à déterminer.

## Contre-expertise des nouvelles tentatives

Sur `40f4de0f`, une seconde activation alors que le Core reste au repos remplaçait le dossier à restaurer par la NAND temporaire de Wiimmfi. Désactiver sans lancer le jeu gardait aussi ce dossier. Si la seconde activation échouait au contrôle TLS, les drapeaux réseau de la première pouvaient rester actifs. La reproduction sur les vrais corps C++ échouait avant correction. Chaque nouvelle configuration idle ferme désormais son autorisation précédente et rétablit le dossier d’origine avant de vérifier et armer la tentative suivante.

Le contrôle structurel de `keys.bin` regardait l’ID et la clé privée NG, mais acceptait les deux composantes ECC de signature NG vides ainsi que les identifiants CA/MS manquants. Dolphin emploie ces champs pour constituer le certificat de la Wii. Ils sont maintenant requis avant de reconnaître la NAND, d’importer la copie et d’autoriser son lancement. Le contrôle vérifie la présence des champs. La chaîne cryptographique et l’acceptation du serveur restent des étapes distinctes. Aucun identifiant n’est exporté.

Les tests exécutent la fonction de reconnaissance sur des données entièrement synthétiques. Ils couvrent le cas structurel complet et dix refus pour clé, signature et émetteurs absents ou remplis de `FF`. Le cycle de vie vérifie vingt alternances Wii/GameCube, doubles activations, désactivation avant lancement, refus TLS et restauration après arrêt. Les deux tests réussissent. Le second est inclus dans le producteur Dolphin existant.

## Préparation guidée

Pour `RMCP01` (Europe), `RMCE01` (Amérique du Nord), `RMCJ01` (Japon) et `RMCK01` (Corée), DiscIO lit la région et la révision de l’image déclarée. L’application vérifie à nouveau ces éléments et l’empreinte complète avant de lancer cette copie. Aucun patchage ou réencodage du jeu n’est effectué sur iPhone.

Le format Riivolution est prévu dans le Core pour des modifications de disque sans réécriture, mais l’existence de cette API ne fournit ni un paquet de patch MKW vérifiable pour chaque révision, ni sa compatibilité actuelle avec le serveur. Le patcher de bureau et ses composants n’ont pas été qualifiés pour iOS. Le panneau Wiimmfi ouvre son parcours officiel et affiche la progression de la vérification de la copie. Appliquer l’outil sur une copie ISO/WBFS sur ordinateur. Pour un RVZ, convertir une copie en ISO dans Dolphin, puis importer et déclarer la sortie. Le diagnostic indique « déclaré » et ne déduit pas la version du patch de l’ID disque.

## Contrôles sur hôte

- Dix tests Flutter réussis, dont navigation simulée, stockage, annulation, progression et empreinte de l’image, refus TLS et export sans champs privés. Analyse Dart ciblée réussie.
- Vingt cycles natifs Wii/GameCube avec refus du mauvais chemin et de l’identité par défaut, restauration du dossier après arrêt et compteurs inactifs hors ligne. Les 27 requêtes IOS IP répétées 100 fois ne font aucun appel hôte hors ligne. Le banc de résolution contrôle les tailles 0, 8, 15, 16 et 32.
- UBSan sur les vrais corps du précontrôle TLS et de la lecture d’interface, avec entrées synthétiques : trois fichiers valides, neuf refus (absents, altérés ou trop grands), adresses nulle, IPv6 et IPv4.

## Validation iPhone 16 Pro Max

1. Avec une IPA autorisée intégrant le Core et l’interface de cette version, fermer Dolphin. Ouvrir **Wii → Wiimmfi → Préparer ma Wii**. Sélectionner son `nand.bin` BootMii et le `keys.bin` associé si séparé. Vérifier que la sauvegarde et les Mii sont présents.
2. Dans **Propriétés de Mario Kart Wii → Gérer → Wiimmfi**, déclarer la copie préparée, activer **Services en ligne** puis **Lancer avec Wiimmfi**. Conserver le pairing et la configuration Local Dev VPN utilisés pour le JIT. Démarrer sur un Wi-Fi stable.
3. Choisir **Nintendo WFC**. Noter le premier code affiché, même si une seconde tentative donne un autre résultat. À la fermeture du jeu, retourner dans **Aide et paramètres avancés → Code d’erreur Wiimmfi**, saisir le code puis **Exporter le diagnostic Wiimmfi**. Envoyer seulement ce JSON, sans dump ni clé. Les compteurs portent sur la dernière tentative de l’application ouverte.
4. Si le jeu s’authentifie, vérifier son profil et son code ami. Lancer une recherche mondiale et terminer une course. Refaire dans un salon privé avec un ami, puis plusieurs courses consécutives. Vérifier le retour au menu Nintendo WFC et quitter/reconnecter après relance. Enregistrer la vitesse affichée lors d’une désynchronisation.
5. Désactiver Wiimmfi. Relancer le jeu hors ligne et vérifier la sauvegarde, le profil, les Mii, les réglages et la manette. Lancer un jeu GameCube et vérifier un second démarrage de Mario Kart Wii.

Le succès DNS ou TLS, y compris côté jeu, ne démontre ni le login Nintendo WFC ni l’accès à un salon. ECC/HMAC du dump, chaîne cryptographique de l’identité Wii, NAT et courses réelles restent à vérifier sur appareil. Un dossier reconstruit manuellement n’est pas la voie prise en charge par le guide Dolphin pour Wiimmfi.

Sources : [Guide NAND Dolphin](https://dolphin-emu.org/docs/guides/nand-usage-guide/) · [Guide Wi-Fi Dolphin](https://dolphin-emu.org/docs/guides/wii-network-guide/) · [Patcher Wiimmfi](https://wiimmfi.de/patcher/iso) · [Codes Wiimmfi](https://wiimmfi.de/error).
