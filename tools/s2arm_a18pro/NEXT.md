# S2Arm GPU — reprise (boucle A18 Pro)

Périmètre : GPU seulement (passes Metal/TBDR, load/store, barrières, encodage, transferts). Runtime CPU, RAM et services : voir `NEXT_CPU.md` (Sol).
Rappel : iOS 26 tourne sur **Metal 3** (`nvn_be.h`, `ios26x`), le chemin à optimiser en priorité pour A18 Pro.

## État au 27 novembre 2026
- Rejeu synthétique (CI 46001412062, `0471`) : `load_bytes = 0`, `store_bytes = 1,65 Mo` (6 passes, toutes `store`),
  6 encodeurs de rendu, 14 barrières/fences, 700 liaisons Metal 3, 677 allocations d’arène (173 Ko) pour 372 dessins.
- Stores restants : non prouvables morts dans la soumission (lecture finale, preuve inter-soumissions = `xv`, coupée pour les titres hébergés bindless).
- `0477` (cette passe) : `bind_args` donne son tampon d’arène à `tab_addr`, plus de `m3_buf_at` (verrou `g_res_mu` + recherche binaire) par bloc d’arguments.
  Preuve attendue : `m3_arg_hints` ≈ liaisons de blocs par image, variante `m3_arg_hint_off` pixels/état identiques.
- `0478` : état lié par étage dans `m3_table_apply` → liaison identique sautée, `set*BufferOffset` si même tampon (`RO_M3_BOFF` en fin d’énumération).
  Preuve attendue : `m3_bind_skips` > 0, `m3_buffer_offset_binds` > 0, `m3_buffer_binds` en baisse ; variante `m3_bind_cache_off` pixels/état identiques.
  Arbre de travail patché : `/tmp/s2arm-loop/cur` (base `work` 0468 + 0469–0478).

## Prochaine action
1. Relire le run CI 46006446704 (commit 26562819e, `0478`, couvre aussi `0477` ; run 0477 46005579324). Si rouge ou pixels/état différents sur
   `m3_arg_hint_off` / `m3_bind_cache_off` : corriger ou retirer le patch fautif.
2. Ensuite : 14 fences par image (m3_wait/m4_end entre encodeurs). Attention : sauter un `waitForFence` casse la transitivité de la chaîne
   (l’encodeur suivant n’attendrait que le précédent) → ne retirer qu’une paire wait+update prouvée sans dépendance, ou abandonner l’axe.
3. Ne pas refaire : coupures 0/4/16/64, vidage des tables de ressources (retiré), comparaisons de temps mural du runner (bruit ±30 %).
