# Wiimmfi et Mario Kart Wii sur iPhone

## Défauts confirmés

- ABI 4 contrôlait `User/Wii` mais l’amont peut modifier `D_WIIROOT_IDX` via `NANDRootPath`. IOS charge les clés depuis ce chemin, tandis que les certificats viennent de `D_SESSION_WIIROOT_IDX`. Le Core ABI 5 utilise la NAND importée pour toute la session Wiimmfi, vérifie les chemins avant la libération du jeu, observe l’identité réellement chargée par IOS et rétablit le chemin précédent après l’arrêt.
- L’ancien état « structure reconnue » acceptait des fichiers TLS à la bonne taille mais rejetés par IOS SSL. Le contrôle reprend les trois empreintes attendues par le Dolphin épinglé, sans écrire leurs valeurs dans le diagnostic. IOS conserve ses contrôles TLS. L’identité Wii et les fichiers TLS IOS sont des vérifications distinctes.
- Darwin n’expose pas forcément d’adresse de diffusion ni de masque IPv4 sur les interfaces point à point. La détection d’interface protège ces lectures et n’utilise pas l’adresse du pair VPN comme adresse de diffusion.
- Le site public et le réseau du jeu donnent des signaux différents. Le diagnostic Oui/Non/Non testé est remplacé par les signaux observables. Le code `23934` désigne un paramètre de connexion invalide et ne désigne pas à lui seul une identité Wii refusée.

Aucun code en jeu ni dump réel fourni pour cette revue. Les défauts ci-dessus sont reproductibles dans l’intégration, mais leur présence sur l’iPhone de l’utilisateur et le point de refus du serveur restent à déterminer.

## Préparation guidée

Pour `RMCP01` (Europe), `RMCE01` (Amérique du Nord), `RMCJ01` (Japon) et `RMCK01` (Corée), DiscIO lit la région et la révision de l’image déclarée. L’application vérifie à nouveau ces éléments et l’empreinte complète avant de lancer cette copie. Aucun patchage ou réencodage du jeu n’est effectué sur iPhone.

Le format Riivolution est prévu dans le Core pour des modifications de disque sans réécriture, mais l’existence de cette API ne fournit ni le patch MKW signé/autorisé pour chaque révision, ni sa compatibilité actuelle avec le serveur. Le patcher de bureau et ses composants n’ont pas été qualifiés pour iOS. Le panneau Wiimmfi ouvre son parcours officiel. Appliquer l’outil sur une copie ISO/WBFS sur ordinateur. Pour un RVZ, convertir une copie en ISO dans Dolphin, puis importer et déclarer la sortie. Le diagnostic indique « déclaré » et ne déduit pas la version du patch de l’ID disque.

## Validation iPhone 16 Pro Max

1. Avec une IPA autorisée intégrant le Core et l’interface de cette version, fermer Dolphin. Ouvrir **Wii → Wiimmfi → Préparer ma Wii**. Sélectionner son `nand.bin` BootMii et le `keys.bin` associé si séparé. Vérifier que la sauvegarde et les Mii sont présents.
2. Dans **Propriétés de Mario Kart Wii → Gérer → Wiimmfi**, déclarer la copie préparée, activer **Services en ligne** puis **Lancer avec Wiimmfi**. Conserver le pairing et la configuration Local Dev VPN utilisés pour le JIT. Démarrer sur un Wi-Fi stable.
3. Choisir **Nintendo WFC**. Noter le premier code affiché, même si une seconde tentative donne un autre résultat. À la fermeture du jeu, retourner dans **Aide et paramètres avancés → Code d’erreur Wiimmfi**, saisir le code puis **Exporter le diagnostic Wiimmfi**. Envoyer seulement ce JSON, sans dump ni clé. Les compteurs portent sur la dernière tentative de l’application ouverte.
4. Si le jeu s’authentifie, vérifier son profil et son code ami. Lancer une recherche mondiale et terminer une course. Refaire dans un salon privé avec un ami, puis plusieurs courses consécutives. Vérifier le retour au menu Nintendo WFC et quitter/reconnecter après relance. Enregistrer la vitesse affichée lors d’une désynchronisation.
5. Désactiver Wiimmfi. Relancer le jeu hors ligne et vérifier la sauvegarde, le profil, les Mii, les réglages et la manette. Lancer un jeu GameCube et vérifier un second démarrage de Mario Kart Wii.

Le succès DNS ou TLS, y compris côté jeu, ne démontre ni le login Nintendo WFC ni l’accès à un salon. ECC/HMAC du dump, chaîne cryptographique de l’identité Wii, NAT et courses réelles restent à vérifier sur appareil. Un dossier reconstruit manuellement n’est pas la voie prise en charge par le guide Dolphin pour Wiimmfi.

Sources : [Guide NAND Dolphin](https://dolphin-emu.org/docs/guides/nand-usage-guide/) · [Guide Wi-Fi Dolphin](https://dolphin-emu.org/docs/guides/wii-network-guide/) · [Patcher Wiimmfi](https://wiimmfi.de/patcher/iso) · [Codes Wiimmfi](https://wiimmfi.de/error).
