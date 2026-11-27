# S2Arm 0476 — contrôle du quota de mémoire de transfert

Le SVC `CreateTransferMemory` parcourait les 8 191 cellules possibles de la table sous le verrou `G`. Le runtime maintient déjà le compteur de chaque type lors de l’attribution et de la fermeture. Le SVC lit le compteur de mémoire de transfert sous le même verrou. Le seuil de 128 et les chemins de refus et de retour arrière restent en place.

- Référence immédiate `65f122925`, série jusqu’à 0475 sur le moteur épinglé `6b6a5715`. Le scan de référence est identique sur `da0e8f7a9`.
- Linux x86-64, AMD EPYC 9V74, GCC 14.2.0, `-O2 -march=native`, un processeur logique. À environ 1 000 handles de types mixtes, **4 667,58 → 2,21 ns** de médiane pour le comptage, candidat favorable sur **12/12** paires dans un ordre alterné. Cette mesure isole le parcours ou la lecture du compteur. Elle exclut verrouillage, allocation et traitement du SVC.
- ASan et UBSan, **17 382** états à résultat identique avec remplissage, saturation, fermeture et ouverture de nouvelles sessions. Détection de fuites indisponible sous le traceur Linux.
- Les cas (0x15) de `t_thread` vérifient le plafond, les erreurs et la restitution du prêt. CI macOS et compilation iPhoneOS à suivre. Effets sur FPS, empreinte et chauffe sur iPhone non mesurés.
