# S2Arm GPU — reprise manuelle A18 Pro

27 novembre. Travail exclusivement manuel sur `Claude`. Moteur amont `6b6a5715`. [Résultats et limites du lot GPU](../../docs/evidence/s2arm-gpu-0481/README.md). Pour le runtime et les services, voir [NEXT_CPU.md](NEXT_CPU.md).

- 0477/0478 vérifiés jusque dans les artefacts des deux runners. Sur le rejeu, 677 recherches évitées et 668 liaisons par changement de décalage, 32 liaisons complètes, zéro liaison identique sautée. Le débit en jeu reste inconnu.
- 0481 prépare seulement les rectangles GOB peu denses en 2D mono-niveau. 0485 étend ce traitement aux mips et tableaux lorsque toutes les plages sont dans un seul niveau et une seule couche sans remplissage. Cas CPU de 1 Mio à 16 Kio, 12/12 paires favorables.
- 0482 retire une barrière de groupe mesh/task. Le cache de secours utilise une nouvelle empreinte pour tous les étages. Les bibliothèques précompilées devront être régénérées pour en bénéficier.
- 0483 conserve une passe en présence d’un effacement profondeur/stencil sans écriture sur le chemin ordinaire, sous les gardes de continuation. Le rejeu final conserve les pixels des deux plans et passe de 11 à 9 encodeurs par image.
- [Run moteur 46015178063](https://github.com/TarbleFR/RewindBox/actions/runs/46015178063) vérifié. 0485 relit 24 sous-ressources exactes. 0482 donne 17 → 12 barrières AIR. Le runner ne sait pas exécuter les shaders mesh. FPS, énergie et comportement soutenu sur A18 Pro restent à mesurer.
- Axes manuels suivants : mises à jour de plusieurs niveaux à la fois, MSAA/resolve et ombres multi-passes. Conserver les 14 dépendances du premier rejeu. Vidage des tables et variations de coupure 0/4/16/64 déjà écartés.
