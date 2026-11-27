# S2Arm GPU — reprise manuelle A18 Pro

27 novembre. Travail exclusivement manuel sur `Claude`. Moteur amont `6b6a5715`. [Résultats et limites du lot GPU](../../docs/evidence/s2arm-gpu-0481/README.md). Pour le runtime et les services, voir [NEXT_CPU.md](NEXT_CPU.md).

- 0477/0478 vérifiés jusque dans les artefacts des deux runners. Sur le rejeu, 677 recherches évitées et 668 liaisons par changement de décalage, 32 liaisons complètes, zéro liaison identique sautée. Le débit en jeu reste inconnu.
- 0481 prépare seulement les rectangles GOB peu denses en 2D mono-niveau. Étendre aux mips/tableaux uniquement après preuve des origines, strides et aliases par sous-ressource.
- 0482 retire une barrière de groupe mesh/task. Le cache de secours utilise une nouvelle empreinte pour tous les étages. Les bibliothèques précompilées devront être régénérées pour en bénéficier.
- 0483 conserve une passe en présence d’un effacement profondeur/stencil sans écriture sur le chemin ordinaire, sous les gardes de continuation. Suivre le rejeu de cette charge, les deux plans et son A/B.
- Relever le détail des étapes du run moteur, y compris les matériels indisponibles. Une compilation et un résultat sur Mac ne donnent pas les FPS sur A18 Pro.
- Axes manuels suivants : mips et tableaux tuilés, MSAA/resolve et ombres multi-passes. Conserver les 14 dépendances du premier rejeu. Vidage des tables et variations de coupure 0/4/16/64 déjà écartés.
