# IPA privée 848 — préparation, 27 novembre 2026

Base : IPA 847 livrée et vérifiée. Inclure les ajouts produit depuis cette base et promouvoir `025a688f` (versions des moteurs dans les playlists).

- Dolphin Wiimmfi ABI 4 : source `e19a37ac`, producteur `45979848094`, artefact `15189836303`. La recette authentifie les entrées hôte, les deux postimages de sources, l’architecture, les exports et l’empreinte avant installation.
- S2Arm 0464–0470 : producteur `45988137849`, source `e64d53205`. Trois archives téléchargées et vérifiées par `engine_pin.py`; préparation et données système conservées. Empreinte moteur `47029c26b8b93668e2b0cfccff4d28d8dfb553fd71e0cd0436331a4b2ab3e560`.
- Interface Wiimmfi partagée avec Nextendo, import NAND, sauvegardes/Mii, sessions et lancement : correctifs des contre-expertises précédentes inclus.
- Autres moteurs inchangés. Suites Flutter/natives non exécutées pour cette compilation ; contrôles indispensables conservés.

Statut : préparation, aucune IPA livrée. FPS, chauffe et multijoueur sur iPhone non mesurés. Maturité S2Arm inchangée : I/R/C/P/S = 50/60/65/35/25, estimation 50 % ; une compilation ne démontre pas un gain sur appareil.

## Premier essai et correction

Le run `45997541453` (source `e24166ebe`) passe le contrat de livraison puis échoue dans la compilation Objective-C : `LibretroInternalBridgePlugin.m:719`, identifiant `invalid` hors portée depuis la promotion `025a688f`. Le contrôle de console utilise maintenant `ValidCoreIdentifier(console)`, identique à l’ancien alphabet autorisé. Aucun moteur à recompiler ; nouvelle compilation application nécessaire. Aucun IPA produit par ce premier essai.
