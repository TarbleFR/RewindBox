# RPCS3 iOS 569 — les threads gardent leur QoS

27 octobre 2026. Ce Core corrige le Core 567. **Aucun gain 569 n'est mesuré
sur iPhone.**

## 1. Ce que montrent les journaux 567

- `RPCS3-diagnostic.log` (build 567) contient 1 486 fois
  `pthread_set_qos_class_self_np() failed: 1` (EPERM). Aucune build antérieure
  n'a cette erreur.
- Elle touche les débuts de travail des workers, le thread RSX, `cellAudio`,
  `RsxAudioData` et les workers SPU. La priorité 567 (RSX et audio avant PPU et
  SPU) n'a donc jamais été appliquée.

## 2. La cause

- `thread_ctrl::set_thread_affinity_mask` appelle
  `thread_policy_set(THREAD_AFFINITY_POLICY)` :
  - à la fin de chaque travail d'un worker ;
  - au démarrage des threads CPU et RSX quand l'ordonnanceur n'est pas celui
    du système.
- iOS ne gère pas les ensembles d'affinité : l'appel échoue toujours.
- Avant d'appliquer la politique, `thread_policy_set()` d'XNU retire la QoS du
  thread. Sur échec, il la rétablit avec la priorité relative stockée, sans en
  inverser le signe.
- Une priorité relative de 0 (jusqu'au 565) se rétablit. −2 (le 567) est
  refusée : le thread reste hors QoS.
- Ensuite, chaque `pthread_set_qos_class_self_np()` échoue avec EPERM, et le
  thread tourne à la priorité par défaut d'iOS, image et son compris.

## 3. Le changement (`CELL569_QOS_KEEP`)

- Sur iOS, `set_thread_affinity_mask` n'applique plus rien (`Utilities/Thread.cpp`).
- Les threads gardent leur classe QoS, et la répartition 567 s'applique enfin :
  - RSX et audio en *user-interactive* ;
  - PPU et SPU juste en dessous ;
  - compilateurs en *utility*.
- Les appelants restent inchangés.
- Les identités de codegen sont inchangées, donc aucune recompilation à froid.
- Hors iOS, rien ne change.

## 4. Vérifications

Rapport hôte : [`evidence/rpcs3-cell569-host-linux.json`](evidence/rpcs3-cell569-host-linux.json).

- Le delta canonique est rematérialisé sur l'amont `22f1152`. La fixture
  reconstruit exactement le `Thread.cpp` 567.
- La branche iOS est compilée telle quelle sous ASan/UBSan et TSan.
- Le contrat de placement vérifie :
  - aucune politique appliquée sur iOS ;
  - le reste de `Thread.cpp` identique au 567 ;
  - quatre appelants inchangés.
- La vérification syntaxique iOS ARM64 de `Thread.cpp` ne donne aucune erreur
  et aucun avertissement nouveau.
- Sur le Mac de la CI, le test exécute les vrais appels :
  - la séquence 569 (−2, affinité, +1) doit garder la QoS et la relever ;
  - la séquence 567 et la séquence à priorité relative 0 sont enregistrées.

## 5. À relever sur iPhone

- Plus aucune ligne `pthread_set_qos_class_self_np() failed`.
- God of War III : FPS, `rsx_thread_cpu`.
- DBZ : aucune régression.
- Son : aucun craquement.
