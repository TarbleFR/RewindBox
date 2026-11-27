# S2Arm GPU — reprise (boucle A18 Pro)

Périmètre : GPU seulement (passes Metal/TBDR, load/store, barrières, encodage, transferts). Runtime CPU, RAM et services : voir `NEXT_CPU.md` (Sol).
Rappel : iOS 26 tourne sur **Metal 3** (`nvn_be.h`, `ios26x`), le chemin à optimiser en priorité pour A18 Pro.

## État au 27 novembre 2026
- Rejeu synthétique (CI 46001412062, `0471`) : `load_bytes = 0`, `store_bytes = 1,65 Mo` (6 passes, toutes `store`),
  6 encodeurs de rendu, 14 barrières/fences, 700 liaisons Metal 3, 677 allocations d’arène (173 Ko) pour 372 dessins.
- Stores restants : non prouvables morts dans la soumission (lecture finale, preuve inter-soumissions = `xv`, coupée pour les titres hébergés bindless).
- `0477` (cette passe) : `bind_args` donne son tampon d’arène à `tab_addr`, plus de `m3_buf_at` (verrou `g_res_mu` + recherche binaire) par bloc d’arguments.
  Preuve attendue : `m3_arg_hints` ≈ liaisons de blocs par image, variante `m3_arg_hint_off` pixels/état identiques. CI à relire au prochain tour.

## Prochaine action
1. Relire le run CI du commit `0477` (`[s2arm-replay-metrics]`, homebrew, thermique). Si rouge ou pixels différents : corriger ou retirer `0477`.
2. Puis Metal 3 `m3_table_apply` : même tampon, autre décalage → `set*BufferOffset:atIndex:` (ajouter les sélecteurs au proxy `nvn_rec.h`,
   drapeau dans `RO_M3_BUF`). Gain seulement côté pilote : pas de preuve de temps sur runner paravirtuel → ne garder que si un compteur exact suffit.
3. Ensuite : 14 fences par image (m3_wait/m4_end entre encodeurs) — vérifier lesquelles ne protègent aucune dépendance réelle.
4. Ne pas refaire : coupures 0/4/16/64, vidage des tables de ressources (retiré), comparaisons de temps mural du runner (bruit ±30 %).
