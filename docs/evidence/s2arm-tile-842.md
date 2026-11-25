# S2Arm : passes, tuiles et réveils — base 841

Objectif de validation : Zelda 0400486024DEC000 à 100 % / 60 images/s sur A18 Pro, avec une non-régression sur Mario Kart World (Coupe Champignon 150 cc) et Fire Emblem. Les nouveaux correctifs ne contiennent aucune condition par identifiant de jeu. Aucun gain FPS, watts ou thermique du nouveau lot n'est encore mesuré.

## Périmètre du lot

- Diagnostics des appelants `rp_flush`, des actions par attachement, de leur rôle/taille et de leur premier consommateur encodé observable. Les bindings shader ne prouvent pas l'exécution d'une branche GPU ; un consommateur ou une durée de vie inconnus restent explicitement inconnus.
- Table shader de 4096 entrées, avec émission d'un lot supplémentaire quand elle est pleine. Les dessins sont conservés dans les comptes au lieu d'être perdus par saturation.
- Demande early-Z issue du contrôle NVN2 lu de façon bornée, sans modifier le traducteur. Référence de format : [nxnative](https://github.com/seedds/nxnative/blob/main/dm/gfx/tools/dmsh_ampere.py).
- Première économie opt-in `S2A_RB_TILE_RASTER_CLEAR` : une sauvegarde devient `dontCare` seulement si un effacement complet avant toute lecture est prouvé dans le même morceau de soumission, avec uniquement des changements de viewport/depth-range intercalés. Identité, vues, alias, scissor, masques, état conditionnel, segments, landing et scaling sont vérifiés. Aucune barrière ne disparaît.
- Mesure échantillonnée 1/64 de la latence de réveil sur adresse et du dépassement des sommeils de yield. Leurs délais et les échéances du jeu restent inchangés.

Les fonctions existantes de load elision et de continuation sont conservées. Ce lot n'invente pas de nouvelle fusion à partir des seules réouvertures 854×480 ; leurs causes exactes restent à lire sur les nouvelles captures. Une absence de relecture dans un journal partiel n'est jamais une preuve suffisante pour éliminer un store.

## Contrôles

GCC local : 359 assertions réussies ; un contrôle négatif qui remplace la lecture du flag early-Z par « inconnu » échoue comme attendu. Les 252 entrées de traduction (2 943 682 octets), leur registre et l'ABI restent identiques ; empreinte `121d1bca8eb35c16`. Huit comparaisons de sources de vitesse/présentation passent après retrait des seules enveloppes de diagnostic. Les caches des joueurs sont conservés.

Compilation iOS sur macOS 15/26 réussie, run `45596018196`, source `e6a681a9`. Sur chacun des deux hôtes : 359 assertions Clang, 5000 observations shader comptées sans perte et 512 pixels Metal identiques. [Preuves et empreintes](s2arm-tile-842-checks.json). Cette comparaison porte sur des captures synthétiques identiques entre référence Store et candidat dontCare et exerce aussi le vrai setter du backend ; elle ne constitue pas un replay pixel exact des trois jeux. L'iPhone, les jeux et leur énergie ne sont pas exécutés en CI.

La première compilation a signalé une erreur de qualification ARC lors du parcours des parents d'une texture. Elle est corrigée en 0392 ; aucune IPA n'a été produite à partir de cette source en échec.

## Contre-expertise du lot

La revue a ajouté le suivi de la fermeture réelle, y compris différée, et les réaffectations de slots couleur. Les ressources sont identifiées par une génération numérique associée à une référence faible : une adresse réutilisée ne doit pas être confondue avec une ancienne texture, et le diagnostic ne retient pas leur mémoire. Le registre est protégé par son mutex et réservé au propriétaire de soumission ; les hooks provenant d’un autre fil ne modifient pas sa vue partielle.

Le candidat de store refuse les états conditionnels, les effacements partiels, les vues/alias exposés, les ressources élargies ou repliées et les coupures de soumission. Son suivi d’exposition est actif pour tout jeu S2Arm lorsque le candidat est demandé ; une preuve indisponible provoque un refus. Le test exerce le setter de store réel avant la capture Metal, puis les producteurs et les consommateurs de copie sur de vrais descripteurs d’attachement.

Le contrôle des 5000 observations vérifie les comptes après remplissage de la table, pas seulement sa capacité déclarée. Le dernier résumé de diagnostic est aussi réinitialisé à la fin d’une session pour éviter sa répétition au lancement suivant. Ces corrections sécurisent la preuve et le diagnostic ; elles ne constituent pas une mesure de gain en jeu.

## Nouvel essai combiné de la 841 fourni pendant ce travail

Le mainteneur observe un jeu légèrement plus fluide et moins de saccades avec `DISPATCH_ORDER=game`, `ALLOC_FRAME=1`, `PSO_WAIT_BOOST=1` et `ARCHIVE_ERROR_NIL=1`. Ce sont quatre paramètres modifiés ensemble, pas un A/B attribuable à une seule optimisation.

Les 21 rapports complets de synchronisation (images 300–6300) donnent tous 0 ms d'attente d'allocateur, et zéro attente de visibilité ou drain comptabilisé. Le rapport allocateur 6300 annonce trois objets / 76 721 680 octets ; ce n'est pas le pic mémoire de toute la session. Les 12 demandes de priorité PSO ont été acceptées. Le mode dispatch « game » annonce zéro barrière épargnée : aucun gain ne peut lui être attribué ici. Le footprint maximal des heartbeats est 3959 Mo, ce qui reste une mesure échantillonnée.

Dans les rapports 3D 3900–6600, les GPU p50 varient de 19,61 à 33,65 ms, avec une vitesse de 31,5 à 55,0 %. Les rapports de ces plages sont Fair. Les menus à 60 i/s ne sont pas une preuve de 60 i/s en 3D. Les différences de scène, de cache, de sonde et de départ thermique empêchent une comparaison causale aux deux diagnostics précédents.

## Gels du premier passage

Les captures antérieures distinguent des images dominées par les compilations et d'autres par les uploads et les lectures disque. Aucun nouveau changement de streaming ou de compilation n'est introduit dans ce lot avant une comparaison premier/deuxième passage sur les mêmes décors. Les journaux fournis ne donnent pas trois paires froid/chaud annotées identiques ; une baisse générale de ces gels n'est donc pas validée.

## Réveils : proposition et mesure

`S2A_RB_WAKE_LATENCY=1` collecte la latence publication/reprise sur adresse et le dépassement du sommeil de yield sans allonger un délai. Les comptes sont séparés des interruptions du noyau. Une piste ultérieure est un yield réveillable par notification (`S2A_RB_YIELD_EVENT`, proposé, non implémenté), avec deadline identique et un prédicat d'attente explicite. Elle ne peut pas être activée pour une boucle invitée qui ne fournit aucun événement fiable : un sleep du jeu ne signifie pas que le backend connaît sa condition de reprise. Aucun gain d'énergie CPU n'est revendiqué et aucune substitution spéculative n'est livrée.

## Fichiers de validation préparés

Les fichiers ont été préparés avant l’indisponibilité de l’espace de travail. Leur paquet 842 n’est pas encore remis ; la reprise ne nécessite pas de nouvelle compilation.

- Diagnostic : `S2A_RB_GPUDIAG=1`, `S2A_RB_PASS_DIAG=1`, `S2A_RB_PASS_DIAG_EVERY=30`, `S2A_RB_WAKE_DIAG=1`, `S2A_RB_WAKE_LATENCY=1`. Tous les octets des passes sont comptés ; les lignes détaillées ne portent que sur une image sur 30. Mettre EVERY=1 donne le détail exhaustif, avec un coût de journalisation élevé.
- Mesure référence : ces diagnostics coupés, candidat de store coupé.
- Mesure candidat : seul `S2A_RB_TILE_RASTER_CLEAR=1` diffère de la référence.

Les quatre options de l'essai combiné sont gardées identiques dans les trois fichiers ; la sonde est à 30 images dans les deux variantes de mesure. Les 46 anciens réglages sont conservés. Copier seulement le fichier `env.txt` choisi à la racine Documents/RewindBox, puis quitter complètement et relancer l'app.

Protocole : trois sessions de 180 s par variante et par jeu, même scène/parcours, départ Nominal, refroidissement entre les sessions, même luminosité et état des caches. MKW : Coupe Champignon 150 cc ; même repère de course. Fire Emblem : même sauvegarde et même scène. Séparer première visite et passage chaud. Comparer vitesse, FPS, GPU p50/p95/p99, passes, octets logiques, latence de reprise, énergie CPU, mémoire, audio, rendu et état thermique. Aucun résultat sur les trois jeux ne sera assimilé à une compilation ou à une capture synthétique.

## Statut actuel

Corrigé dans les sources : oui, patchs 0379–0393. Testé sur CPU : oui, portée ci-dessus. Compilé : oui sur macOS 15/26. IPA privée 842 : compilation, signature et contrôles de la recette CI réussis, run `45599445280`, source `52b7b912`. Les quatre archives de transport finales téléchargées sur le PC ont les tailles et SHA-256 annoncés par l’API. La vérification hors ligne de l’IPA après déchiffrement et sa remise restent bloquées par l’indisponibilité de l’espace d’exécution ; la voie de repli n’a pas accès au fichier de validation privée. **Livré : non.** Aucun reçu « livré et vérifié » n’est créé avant ce contrôle. Observé sur iPhone avec le nouveau lot : non. Le lot traducteur restera une livraison distincte avec une seule retraduction avant le jeu.

Le mainteneur précise que Frame Generation concerne uniquement MKW et améliore nettement son confort sur ce jeu. Son réglage MKW est conservé et reste identique entre variantes ; aucune activation pour Zelda ou Fire Emblem. FPS rendus, FPS interpolés et vitesse émulée restent des mesures distinctes. Les fichiers env de ce lot ne modifient pas Frame Generation.
