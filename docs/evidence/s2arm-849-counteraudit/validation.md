# Validations du lot 0530–0533

- Base Claude `08d20176`, état local initial propre. Les 521 patchs précédents s’appliquent au pin amont `6b6a5715`.
- Relecture indépendante 0530/0531 et 0532/0533 : terminée ; refus FI, sémaphores, tickets, compteurs et rétention des vues contrôlés.
- Parité de l’index d’orphelins : 24 000 mutations, 5 015 cas et 10 030 comparaisons, zéro écart ; ASan/UBSan réussis avec `-Werror`. LeakSanitizer indisponible sous ptrace. [Résultat ciblé](host-parity.json), sans nouvelle suite dans le dépôt.
- Réapplication exacte des quatre patchs : réussie, état de référence 849 et octets finaux identiques. Les 521 patchs déjà livrés gardent leur SHA-256. Compilation iPhoneOS à suivre.
- Mesures FPS, durée GPU, empreinte et énergie des nouveaux correctifs sur A18 Pro : **non mesurées**.
- IPA : aucune demandée ou produite. Pins et manifestes 848/849 historiques conservés.

## Comparaisons et limites des diagnostics

`S2A_RB_HEAP_CENSUS_GUARD=0` restaure le recensement 849 chaque minute. Par défaut, les compteurs d’allocation et le ledger mémoire léger restent actifs ; le recensement lourd demande `S2A_RB_HEAP_CENSUS=1` et reste espacé de cinq minutes. Les zones sont limitées à 32, avec vérification du budget de 8 ms entre appels ; un appel allocateur ne peut pas être interrompu sûrement. `partial_zones` indique une couverture incomplète. Le budget ne constitue pas une garantie de durée globale.

`S2A_RB_HEAP_MANAGED=1` ajoute explicitement l’entrée dans le runtime managé ; sa durée n’est pas bornable ici. Sans cette option, le compteur audio vaut indisponible, pas zéro. Les nouveaux champs séparent temps après zones et temps CPU du worker ; ils ne prouvent pas une pause identique sur un thread critique.

`S2A_RB_ORPHAN_REGISTRY_INDEX=0` restaure le parcours des ID de 849. La rétention des textures, les vérifications de génération et les verrous restent identiques. La protection FI 0532 corrige un défaut de sûreté et reste active ; 0533 ne modifie que le compteur de temps existant.

Banc C extrait de la source, sets CF simulés et vraie table de séries : 60 paires, registre synthétique de 1 048 576 emplacements / 4 096 ID actifs, moyenne hôte 1,074425 → 0,109331 ms. Ce cas clairsemé démontre une réduction de parcours ; il ne mesure ni les coûts CF/Metal réels ni le gain FPS sur iPhone.

Relecture finale : `gpu_go()` incrémente les admissions ; les vérifications FI anticipées lisent désormais `mtl_gpu_halted()` sans effet de bord. Seule l’admission finale après encodage réussi est comptée. Le premier candidat `e664d332` reste une compilation intermédiaire et ne doit pas être épinglé ; le producteur final est celui de la correction suivante.
