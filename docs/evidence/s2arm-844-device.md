# S2Arm : observations iPhone A18 Pro sur l’IPA privée 844 (Zelda et Mario Kart World)

26 novembre 2026. Observations dérivées des journaux privés remis par le mainteneur après installation de l’[IPA privée 844](rewind844/delivery.json) (moteur S2Arm `0400–0417`, `S2ArmShaderXfp = ecd99354f03b846d`, `S2ArmDirectChain = 0be3f28548fd`) sur iPhone A18 Pro. Aucun journal brut ni chemin personnel n’est conservé dans le dépôt.

Sessions non appariées selon le protocole 3 × 180 s ; les relevés ci-dessous servent de preuve diagnostique pour séparer les gains confirmés des régressions introduites par le lot structurel `0404–0408` et préparer la vague `0418–0421` (IPA 845).

## 1. Synthèse des deux titres observés

| Métrique (journaux IPA 844) | Zelda (`0400486024DEC000`, 4 800 images) | Mario Kart World (`0400C3F00006E000`, 3 900 images) |
| --- | --- | --- |
| Préparation connue au démarrage (`0400` / `0414`) | `release=time_budget`, `elapsed_ms=30014.2`, `1253/1664` prêts, `12` échecs, **`399` restants** | `release=completed`, `elapsed_ms=3310.2`, **`1674/1674` prêts**, `0` échec |
| Anneau de versions UBO (`0415`, `[rb-ubo-ring]`) | **`recovered=8829`**, `fail_wrap=0`, `fail_opaque=0`, `fail_unknown=9` | **`recovered=1222`**, `fail_wrap=0`, `fail_opaque=0`, `fail_unknown=32` |
| Worker CPU de relecture (`0404`, `[rb-replay]`) | `20034` soumissions, **`admission_wait_ms=135728.741`** (135,7 s cumulés) | `8032` soumissions, **`admission_wait_ms=67218.746`** (67,2 s cumulés) |
| Erreurs d’archives Metal 4 (`0406`/`0408`, `PersistentState`) | **`33` échecs** (`cannot open ... PersistentState`) | **`1` échec** (`cannot open ... PersistentState`) |
| `WindowAcquireTexture` image encore à l’écran (`0405`) | **`7` occurrences** (image 1 rendue encore active) | Aucune ligne rouge observée, mais Frame Generation partage la file GPU |
| Cadence / temps d’image (fenêtres tardives) | Présents 4200–4800 : `p50 38,09–45,08 ms`, `p95 76,40–122,48 ms`, `max 2,36–4,53 s`, vitesse jeu `15,0–30,1 %` (`32,2–39,4 %` hors pauses > 4 vsyncs), `9,0 fps` (fenêtre 4800 avec gels), `Serious`, `0,60 W`, `4856 wakeups/s` | Présents 3300–3900 : `p50 41,58 ms`, `p95 97,90 ms`, `max 178,97 ms`, vitesse jeu `67,1–71,0 %` (`69,3–76,8 %` hors pauses), `21,1 fps` (fenêtre 3900), `Fair`, `0,49 W`, `2964 wakeups/s` |
| Interpolation d’images (Frame Generation `0345`) | Désactivée (et la règle `dm_fi_tier` refuse de toute façon tout jeu en intervalle 1 / 60 Hz) | Activée (`454` interpolées / `445` refusées jusqu’à l’image 900) |

## 2. Gains confirmés sur appareil (conservés dans la 845)

1. **`0415` (anneau UBO 64 soumissions / 512 plages)** : sur Zelda 843, plus de 5 100 ombres partielles d’uniformes par fenêtre de 300 images étaient refusées avec `0` récupération. Sur la 844, `8 829` récupérations sur Zelda et `1 222` sur MKW avec `fail_wrap=0` et `fail_opaque=0` confirment que la cause des coupures de passes multi-pièces est éliminée.
2. **`0414` + `0400` sur MKW** : les `1 674` pipelines connus de MKW sont préparés en `3,31 s` avant la première soumission (`pending=0`).
3. **`0416` (`early_z` NVN2) et `0417` (activations par défaut validées)** : actifs sans régression fonctionnelle observée dans les journaux ; l’empreinte `xfp = ecd99354f03b846d` est conservée à l’identique dans la 845 pour ne pas déclencher une nouvelle reconstruction de shaders.

## 3. Causes racines des régressions observées sur la 844

1. **Worker CPU de relecture `0404` actif par défaut** : l’attente d’admission atteint `135,7 s` sur Zelda et `67,2 s` sur MKW. De plus, `RB_REPLAY_GUARD` / `rb_replay_enter` acquéraient un mutex même lorsque le worker n’était pas actif, et le découplage créait une pression d’admission sur le thread invité qui soumet.
2. **File Metal 4 dédiée à la présentation `0405` active par défaut** : l’exécution de la présentation et de MetalFX Frame Generation hors de `g_q4` a produit des anomalies visuelles (corruption du fond de l’écran des réglages, `7` remises d’image encore à l’écran dans `WindowAcquireTexture` sur Zelda, silences DisplayLink, double commit de `residencySet` et découpage GPU concurrent avec Frame Generation sur MKW).
3. **Archives natives Metal 4 `0406`/`0408` actives par défaut** :
   - `par_ga_remove_new` supprimait des dossiers `gpuarchiver-*` encore détenus par des captures Metal 4 en cours (`33` erreurs `PersistentState: No such file or directory` sur Zelda, `1` sur MKW) ;
   - l’instanciation répétée de `MTL4Compiler` hors capture alourdissait la compilation à la volée.
4. **Plafond de 30 s au démarrage (`0400`) + blocages de compilation en jeu sur Zelda** : la préparation connue s’interrompt à `30,014 s` en laissant `399` pipelines connus non compilés (`pending=399`), ce qui entraîne des gels de `2,36 s` à `4,53 s` en jeu (`max 4527,29 ms` sur la fenêtre 4800) parce que les dessins de rendu attendent encore de façon synchrone sans plafond.
5. **17 optimisations CPU/rendu déjà codées limitées à MKW dans le pont iOS** : `S2ArmEngineBridgePlugin.m` n’activait 17 drapeaux agnostiques du titre (`S2A_RB_UP_PRESSURE_TRIM`, `S2A_RB_PSO_HOT_FIRST`, `S2A_RB_FRAME_SHADER_KEY`, `S2A_RB_UNIFORM_BOUNDS_REUSE`, etc.) que lorsque `marioKartWorld` était vrai (`"0"` sur Zelda et tout autre titre), et laissait `S2A_RB_AUTO_PROBE` actif hors MKW (sondes par suspension de thread à 500 Hz).

## 4. Suite engagée

Les causes 1 à 5 ci-dessus, ainsi que la réduction du trafic de résidence/clears/TBDR et les leviers universels de performances NVN2 (Frame Generation adaptatif, qualité d’ombres universelle, mode de compilation fluide et profils de performance) sont traités dans la [vague 845 (`0418–0421` + pont + Flutter)](s2arm-845-wave.md). Notes de maturité S2Arm inchangées (**50 %**).
