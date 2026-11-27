# IPA privée 848 — préparation, 27 novembre 2026

Base : IPA 847 livrée et vérifiée. Inclure les ajouts produit depuis cette base et promouvoir `025a688f` (versions des moteurs dans les playlists).

- Dolphin Wiimmfi ABI 4 : source `e19a37ac`, producteur `45979848094`, artefact `15189836303`. La recette authentifie les entrées hôte, les deux postimages de sources, l’architecture, les exports et l’empreinte avant installation.
- S2Arm 0464–0470 : producteur `45988137849`, source `e64d53205`. Trois archives téléchargées et vérifiées par `engine_pin.py`; préparation et données système conservées. Empreinte moteur `47029c26b8b93668e2b0cfccff4d28d8dfb553fd71e0cd0436331a4b2ab3e560`.
- Interface Wiimmfi partagée avec Nextendo, import NAND, sauvegardes/Mii, sessions et lancement : correctifs des contre-expertises précédentes inclus.
- Autres moteurs inchangés. Suites Flutter/natives non exécutées pour cette compilation ; contrôles indispensables conservés.

Statut : IPA 848 livrée et vérifiée, source `8847d7c86`, [run 46000133193](https://github.com/TarbleFR/RewindBox/actions/runs/46000133193). FPS, chauffe et multijoueur sur iPhone non mesurés. Maturité S2Arm inchangée : I/R/C/P/S = 50/60/65/35/25, estimation 50 % ; une compilation ne démontre pas un gain sur appareil.

## Premier essai et correction

Le run `45997541453` (source `e24166ebe`) passe le contrat de livraison puis échoue dans la compilation Objective-C : `LibretroInternalBridgePlugin.m:719`, identifiant `invalid` hors portée depuis la promotion `025a688f`. Le contrôle de console utilise maintenant `ValidCoreIdentifier(console)`, identique à l’ancien alphabet autorisé. Aucun moteur à recompiler ; nouvelle compilation application nécessaire. Aucun IPA produit par ce premier essai.

## Livraison vérifiée

IPA : 338 061 011 octets ; SHA-256 `6ac54187ef65243d1cd1f95db3d716c3664426b769f2746c1ab82efb5d060a5f`. Quatre pièces authentifiées, clé destinataire correspondante, déchiffrement et somme finale vérifiés ; 98 images natives, 11 bundles et 48 empreintes conservées contrôlés. Les six validateurs hors ligne réussissent. Clé permanente originale conservée ; copies temporaires de secrets de déchiffrement supprimées par le vérificateur.

Le seul écart additionnel est le pont MeloNX, dont les sources sont identiques à 847 : les références vers deux cases GOT équivalentes de `objc_msgSend` sont permutées (1 stub et 330 stubs Objective-C). Après ce seul échange en mémoire, l’empreinte complète rejoint exactement celle du reçu signé 847 ; code et données utiles inchangés, IPA originale non modifiée. [Preuve](rewind848/melonx-bridge-linker-equivalence.json). [Reçu final](rewind848/delivery.json).

Les sources S2Arm ajoutées après le gel de cette livraison restent hors de son moteur 0470.
