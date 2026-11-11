# RPCS3 Core 929 — épingle vérifiée, gardée en repli

`core-pin.json` est l'épingle du Core 929 (run `43000618405`, tentative 1, source `1ea6cf4a`, job Core `130455539007`,
artefact `13850405143` de 30 515 188 octets, sha256 `c86e1a23…`; tests hôtes Apple du même run, 15 commandes passées).
Bibliothèque `libRPCS3Core.dylib` de 80 958 696 octets, sha256 `82d8ce7f…`, empreinte `eabb95f9…`; identités PPU
`a987639e` / SPU `477a3fa4`. Vérifiée hors ligne avec le vérificateur du dépôt dans un arbre à `1ea6cf4a` (`pin_errors`
sans erreur, `bundle` complet ; métadonnées par l'API REST publique, artefacts téléchargés et comparés aux empreintes de
l'API). Le fichier sha256 de cette épingle dans cet arbre : `b26232c8…`.

Elle n'est pas l'épingle courante : l'arbre `Claude` porte déjà la source du Core 930 (patch canonique `5078f1d4`), que
cette épingle ne décrit pas. Pour revenir au Core 929, remettre la source du Core 929 (patch canonique `f061803a`,
460 postimages) et ce fichier en `build-utils/rpcs3/core-pin.json`. Rien n'a tourné sur un iPhone.
