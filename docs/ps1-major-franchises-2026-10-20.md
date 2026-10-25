# PS1 HD : priorité aux grandes séries — 20 octobre 2026

La priorité demandée porte sur Crash, Final Fantasy, Suikoden, Tekken et Tomb Raider. La première passe ci-dessous couvrait 19 jeux cibles et 44 requêtes. La continuation ajoute 97 requêtes web et 14 recherches de dépôts GitHub à l’inventaire général. Aucun nouveau téléchargement vérifié pour ces séries ; Tomb Raider dispose désormais d’une piste technique qualifiée, sans pack publié.

| Jeu PS1 | État établi | Auteurs / source |
|---|---|---|
| Crash Bandicoot | DuckStation · HUD en chantier | StuD44 · [publication](https://www.reddit.com/r/crashbandicoot/comments/1rzl4sy/updates_regarding_texture_replacements/) |
| Crash Bandicoot 2: Cortex Strikes Back | Aucun pack PS1 qualifié retrouvé | À rechercher |
| Crash Bandicoot 3: Warped | Piste technique, aucun pack séparé établi | À rechercher |
| Crash Team Racing | Aucun pack PS1 qualifié retrouvé | À rechercher |
| Crash Bash | DuckStation · icônes en chantier | StuD44 · [publication](https://www.reddit.com/r/crashbandicoot/comments/1rc94rq/finally_successful_hd_textures_and_bad_news/) |
| Final Fantasy VII | DuckStation · publication originale, archive non inspectée | TheSoulTear · [publication](https://www.moddb.com/mods/final-fantasy-vii-hd-remaster/addons/scus-94163) |
| Final Fantasy VIII | DuckStation · pack partiel publié | Curse_Arms · [publication](https://gbatemp.net/threads/my-hd-remaster-packs.630347/) |
| Final Fantasy IX | Aucun pack PS1 qualifié retrouvé | À rechercher |
| Final Fantasy Tactics | Aucun pack PS1 qualifié retrouvé | À rechercher |
| Suikoden | Aucun pack PS1 qualifié retrouvé | À rechercher |
| Suikoden II | Beetle · archive installée et vérifiée | Faospark · [publication](https://sites.google.com/view/hub-of-faospark/project-kyaro) |
| Tekken | DuckStation · fichier séparé non vérifié | Big Deal / EstudioCases / Steven Castro · Electronic_Rave (now deleted forum account) · [publication](https://www.estudiocases.com/post/tekken-1-de-psx-con-doblaje-en-castellano-ahora-con-texturas-hd) |
| Tekken 2 | DuckStation · même famille, intégration créditée | Bl4ckH4nd · [publication](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) |
| Tekken 3 | DuckStation · projets publiés, archives à vérifier | Bl4ckH4nd · Curse_Arms · [publication](https://docs.google.com/spreadsheets/d/1IX8k_4HU6xvbkod0ZrhlRd1DumgTLVS0NJFmW42hPxw/edit?usp=sharing) |
| Tomb Raider | Démonstration DuckScaler / DuckStation ; aucun pack publié confirmé | Kabson · [outil et comparatifs](https://variatkowo.pl/autoit/nasze-skrypty/duckscaler/) |
| Tomb Raider II | Aucun pack PS1 qualifié retrouvé | À rechercher |
| Tomb Raider III | Aucun pack PS1 qualifié retrouvé | À rechercher |
| Tomb Raider: The Last Revelation | Aucun pack PS1 qualifié retrouvé | À rechercher |
| Tomb Raider: Chronicles | Aucun pack PS1 qualifié retrouvé | À rechercher |

Suikoden II Project Kyaro2.6 est déjà présent dans NeoStation :437 PNG vérifiés par le véritable installateur. Il améliore une partie de l’interface, des portraits et des fonds ; ce n’est pas une refonte intégrale du jeu. La couverture régionale et le rendu sur iPhone restent des vérifications distinctes.

FFVII TheSoulTear1.0 est publié pour DuckStation :470667042 octets annoncés, anglais/russe, SCUS-94163. FFVIII Curse_Arms annonce les dossiers USA des quatre disques, mais exclut beaucoup de fonds, polices, effets, cartes et une partie des personnages. Les archives ne deviennent pas compatibles Beetle du fait de leur format PNG.

La publication EstudioCases de Tekken2 crédite explicitement Bl4ckH4nd et son accord d’intégration. Elle rejoint sa famille existante : la première passe a corrigé le total de 180 à 179 familles, avec 216 fiches, 140 jeux/éditions et 46 groupes crédités. La continuation documente une autre famille, Resident Evil: Survivor HQ : état courant 180 familles, 228 fiches, 141 jeux/éditions et 47 groupes crédités. La version2.0 désigne le paquet EstudioCases ; aucun nouveau style graphique indépendant n’est démontré. Tekken1 crédite séparément Big Deal et l’équipe d’intégration. Aucun installateur combinant jeu et localisation n’a été téléchargé.

Crash1 et Crash Bash restent des démonstrations partielles sans archive publique confirmée. Les mentions de Warped/CTR concernent des mécanismes de sprites et de coloration ; elles ne prouvent pas deux nouveaux packs. Une vidéo en4K ou un filtre xBR ne prouve pas un remplacement HD publié.

Pour Tomb Raider, la collection originale [Tomb Raider Xtra](https://www.tombraiderxtra.com/downloads.php) vise Glidos/TombATI sur PC. Les collections Antonijadis, JC, Matthew Hill et Silverlok sont des ressources PC connexes, pas des packs PS1. Les recherches consacrées à TRIII–V sont encore au niveau de la série ; aucune absence absolue n’est affirmée.

## Pourquoi les formats ne sont pas interchangeables

DuckStation associe les images aux empreintes de leurs données et palettes, aux dimensions des transferts VRAM et à leurs sous-zones. Ses options de découpage dépendent parfois du jeu. Beetle attend les identifiants de ses propres dumps et sa structure de remplacement. Copier ou renommer des PNG ne suffit donc pas à établir une compatibilité. Une adaptation demanderait des correspondances avec les dumps cibles, parfois du découpage ou de la recomposition, puis une vérification des palettes, transparences, animations et régions. Aucun convertisseur générique n’est validé ici.

Un patch qui modifie directement les fichiers du jeu utilise un autre mécanisme : son fonctionnement dépend de l’édition du disque, du patch et de la précision du cœur.

- [Documentation DuckStation](https://github.com/stenzek/duckstation/wiki/Texture-Replacement).
- [Documentation Beetle PSX HW](https://docs.libretro.com/library/beetle_psx_hw/).

## Intégration et preuves

Catalogue courant : **38 références PS1, 8 téléchargements vérifiés et 30 pages d’auteurs**. Resident Evil: Survivor HQ ajoute une page manuelle, hors des 19 cibles de ce tableau. Validation ciblée [39496716743](https://github.com/TarbleFR/neostation-ios/actions/runs/39496716743) : 189 contrôles Foundation, zéro échec. L’IPA 500 déjà livrée reste figée avec ses 37 références. Aucun rendu physique iPhone n’est revendiqué.

Kabson présente également Dino Crisis et Toy Story 2 dans DuckScaler : trois démonstrations d’outil, pas trois packs téléchargeables. Le tutoriel public GeniusBug pour Tekken 3 apporte un lien secondaire ; l’archive originale reste non vérifiée. [Détail de la continuation](ps1-hd-continued-research-2026-10-20.md).

- [Matrice et journal JSON](../tools/textures/research/ps1-major-franchises-2026-10-20.json).
- [Inventaire JSON général corrigé](../tools/textures/research/ps1-hd-inventory-expanded-2026-10-20.json).
- [Export CSV général corrigé](../tools/textures/research/ps1-hd-inventory-expanded-2026-10-20.csv).

Les résultats de recherche sont distingués des pages effectivement lues. Le403 rencontré lors de la lecture HTML directe du fil Tekken3 est conservé ; aucun nouvel essai visant ses fichiers intégrés n’a été effectué. Les objectifs50/100/200/300 restent des objectifs de prospection et ne justifient aucun ajout fictif.
