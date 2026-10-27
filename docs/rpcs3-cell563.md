# RPCS3 iOS 563 — A/B en jeu de la soumission anticipée (Dragon Ball Z Budokai HD)

27 octobre 2026. Ce document fait suite à la mesure du Core 561 sur DBZ
([`rpcs3-cell561.md`](rpcs3-cell561.md) §9). Le Core 563 ne change aucun
rendu : il fait mesurer le réglage 561 par l'appareil lui-même.
**Aucun gain n'est mesuré sur iPhone.**

## 1. Pourquoi

Les journaux de la 562 (Core 561) montrent DBZ plus lent qu'en 560 :
- en combat : 35,4 FPS contre 41,7 ;
- mais aussi dans les menus où le 561 n'a rien fait : 43,0 FPS contre 51,9.

La session 562 diffère donc de la session 560 au-delà du réglage (nouveau
conteneur d'application, état de l'appareil). Comparer deux sessions ne permet
pas d'isoler l'effet du 561.

## 2. Le changement 563 (`CELL563_EARLY_AB`)

**Principe.** En Automatique sur DBZ (`BLES01658`), le réglage 561 alterne
d'une fenêtre de profilage à la suivante (environ 5 s) : activé, désactivé,
activé… Une seule partie compare ainsi les deux états, dans les mêmes scènes et
les mêmes conditions d'appareil.

- **Frontière.** `early_submit::window_boundary()` est appelé dans
  `report_profile_window`, sous le même verrou que l'instantané de la fenêtre.
  Il renvoie l'état de la fenêtre qui se termine et bascule la suivante.
- **Export.** Dans `COREPROF OPT561`, `early_submit` est l'état avec lequel
  la fenêtre a tourné, et `ab=1` signale l'alternance. Le FPS de la même
  fenêtre (`COREPROF frames=`) vient du même instantané.
- **Journal de démarrage :** il ajoute `early_submit_ab=`.
- **Inchangés :** la décision 561, ses seuils (32 dessins, 6 par image), ses
  gardes et son point d'appel dans le renderer. Chaque fin de dessin lit l'état
  pour son propre compte : une bascule entre deux dessins ne change aucune
  commande, seulement l'endroit où peuvent tomber les frontières suivantes.
- **Réglages explicites.** *Enabled* garde le réglage actif, *Disabled* le
  garde éteint, sans alternance. Les autres jeux sont inchangés.

## 3. Mesure attendue sur appareil

Pour chaque fenêtre de combat, apparier les valeurs avec ses voisines de
l'autre état :
- FPS, temps d'image et p95 ;
- attente de relecture `fault_read` (`READBACK555`) et `frame_latency`
  (`RSXSYNC551`) ;
- `early_submits` et `gpu_busy_checks` dans les fenêtres actives.

Si les fenêtres actives sont plus lentes que leurs voisines inactives, le 561
coûte plus qu'il ne gagne et doit être retiré. Si elles sont égales, il est
neutre. S'il y a un gain, il est mesuré dans les mêmes conditions.

## 4. Validation

**Delta canonique.**
- Il est régénéré depuis l'amont `22f11527` et touche 4 fichiers Core :
  `ios/IOSEarlySubmit.h`, `RPCS3IOSExperimentalPolicy.cpp`,
  `RPCS3IOSPerformance.cpp` et `RPCS3IOSSettings.cpp`.
- Les 288 empreintes de post-image sont vérifiées après application sur une
  source vierge. Les 284 autres sources, dont le renderer 561, sont identiques
  au 561.
- La fixture `test/fixtures/rpcs3_cell563.diff` reconstruit exactement les
  préimages 561.
- Les identités de codegen sont inchangées : PPU `a987639e9f838d1c`, SPU
  `d070cb361bdef607`.

**`test/rpcs3_cell563_test.py`.** Il compile l'en-tête de production et
exécute, copiés mot pour mot, le bloc de politique, le prédicat de titre,
`resolve_mode`, la bascule de fenêtre et le bloc d'export. Il tourne sous
ASan+UBSan puis TSan :
- **politique :** 7 cas ; l'alternance n'existe qu'en Automatique sur DBZ ;
- **alternance :** 12 fenêtres `101010101010`. Chaque fenêtre rapporte l'état
  vu par tous ses dessins et ses propres compteurs, et la première est active ;
- **réglages explicites et autres jeux :** un seul état, `ab=0` ;
- **concurrence :** 400 fenêtres pendant que le thread RSX lit l'état.
  Chaque soumission anticipée est rapportée une fois, et l'état alterne à
  chaque frontière ;
- **contrat :** la bascule est sous le verrou de l'instantané, avant les lignes
  `OPT561` et `frames=`, et le rapporteur ne change pas au-delà ;
- **mutations :** sept altérations d'une ligne de production sont toutes
  détectées par leur comportement (état suivant rapporté, bascule sans
  alternance, jamais de bascule, alternance en mode explicite ou pour tout
  titre, export de l'état suivant, drapeau `ab` absent).

**Pilote et ARM64.**
- **Pilote CI :** `rpcs3cell563_core.py` a été exécuté de bout en bout sur une
  source fraîchement matérialisée. Il authentifie l'artefact de diagnostics du
  Core 561 (`12725733046`, run `40486026315`), et `--verify-reuse` passe.
- **ARM64 :** même banc compilé par LLVM 22.1.8 pour
  `aarch64-linux-gnu -mcpu=apple-a7 -march=armv8.4-a` et exécuté sous qemu,
  avec UBSan en mode trap. Les résultats sont identiques au run hôte.
- **Syntaxe de production (ARM64, `RPCS3_IOS`, `-Werror` du projet et
  `-Wshadow`) :** les 8 unités compilent sans erreur. Les diagnostics sont ceux
  du 561, aux numéros de ligne près.
- **Tests de source existants :** les 9 tests passent.
  `neo_swap_core_pin_test.py --source-only` passe ; le mode complet échoue
  comme sur la base (pin public `cfe92344`).

Reçu : [`evidence/rpcs3-cell563-host-linux.json`](evidence/rpcs3-cell563-host-linux.json).

## 5. Limites

- Ce n'est pas une optimisation : la 563 mesure. Une fenêtre sur deux tourne
  sans le réglage 561, soit au comportement 560.
- Les fenêtres de transition de scène sont à écarter de l'appariement.
- Rien n'est mesuré sur iPhone tant que les journaux de la 563 ne sont pas
  revenus.
