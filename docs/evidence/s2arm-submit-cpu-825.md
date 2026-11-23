# Coût CPU du fil de soumission (lot 825)

Session Mario Kart World sur l'IPA 824 : en course, le fil de soumission prend 16,7 à 19,0 ms par image pour un GPU à 13,9–15,0 ms. Il faut gagner 3 à 4 ms pour tenir 60 image/s à l'état thermique Fair. Mesure autour de `nvn_be_submit` : environ 45 500 instructions par dessin. L'horloge du cœur descend à 1,26–1,52 GHz quand le téléphone chauffe.

## Audit statique (arbre 0001–0311)

Candidats classés par gain estimé en instructions par dessin. Ce sont des estimations faites en lisant le code : rien n'est mesuré.

| Poste | Estimation | Suite dans ce lot |
|---|---|---|
| Échelle de rendu : après le premier état Fair, `rs_on()` reste vrai toute la session ; `rs_bind_check` / `rs_bad` font deux recherches d'objet associé par liaison de tableau de poignées | 0,3–3 k | Non : il faut d'abord un profil ; un raccourci sur la taille de la texture n'est pas sûr avec les stockages partagés |
| Échantillonnage de la cible en cours (`fb_prepare`) : `args_dirty_all()` à chaque dessin substitué | 0,6–1,5 k | Non : à mesurer d'abord |
| Anticipation des pipelines : une lecture d'horloge par commande parcourue | 0,7–1,5 k | Patch 0315 |
| Rétentions et libérations ARC sur les chemins chauds | 0,3–0,8 k | Commits amont `9ca83e5b1`, `89ab97043`, `cd9e28261`, `21f506c2f` : voir le tri de l'amont |
| Diagnostics dans la boucle des liaisons (`p20_check`, `rb_fresh_read`, `fsig_tex_note`) | 0,1–0,8 k | Non : des sorties rapides existent déjà ; gain faible |
| `rb_pso_bound` : objet associé et horloge à chaque changement de pipeline | 250–350 | Patch 0315 (horloge une fois par soumission) |
| `g_rmu` en mutex pthread | ~40–50 par paire | Commits amont `337056321` + `43d8b5fa4` : voir le tri |

Total estimé : 3 à 9 k instructions par dessin, soit 7 à 20 %. Atteindre 25 à 30 % demande un profil CPU pris en course : la capture d'écran écrit `captures/<capture>/cpuprof.txt`.

## Patch 0315

- L'anticipation des pipelines vérifie son échéance toutes les 8 commandes au lieu de chaque commande. Elle ne relit plus l'horloge avant chaque dessin ou dispatch qu'elle met en file. Le budget de 2 ms par soumission reste tenu, à 8 commandes près.
- `rb_pso_bound` lit l'horloge une fois par soumission. Cette heure ne sert qu'à vieillir des pipelines inactifs depuis plusieurs secondes.
- La ligne `[rb-look-budget]` donne désormais le nombre de parcours, leur temps total et leur moyenne par image. Le journal de l'IPA 824 ne donnait que le maximum par soumission (2,063 ms), si bien que le vrai coût de l'anticipation par image restait inconnu.
- Gain attendu : faible, non mesuré. Test : compilation et tests GPU de la CI ; pas de test unitaire dédié.

## Patch 0316 (amont S2Arm `cbf37ad7d`)

- **Le problème.** Une limite de segment (tous les 64 dessins) ne devait pas soumettre de tampon de commandes quand le GPU est encore occupé ; elle garde alors seulement un horodatage. Cette règle demande un tas de compteurs. Or ce tas n'était pas construit quand le fil d'encodage est actif, ce qui est le réglage par défaut sur iPhone. Chaque limite soumettait donc un vrai tampon, avec à chaque fois :
  - une validation du jeu de résidence ;
  - un rappel de fin ;
  - un nouveau tampon de commandes ;
  - un passage par le noyau.
- **Le correctif.** Le tas est construit même avec le fil d'encodage ; les horodatages sont enregistrés pour lui (`RO_R_TS` / `RO_C_TS`, déjà présents dans notre arbre). En Metal 3, rien ne change.
- **Gain attendu, non mesuré :** quelques soumissions de moins par image quand le GPU est occupé.
- **Test.** Le cas ⑥ de `t_nvn_cut_busy` est repris de l'amont, mais il appelle `mtl_init` et ne tourne que sur un Mac réel.
- **Retour arrière.** `DM_NVN_CUT_BUSY=0` fait soumettre chaque limite, comme avant.
