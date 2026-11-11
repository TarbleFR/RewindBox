# RPCS3 Core 929 — la mémoire d'une sauvegarde d'état de God of War III n'est plus modifiée

Core 929 = Core 928 sans l'écriture du Core 922 (`REWINDBOX_GOW3_MLAA_SAVESTATE_922`) dans la mémoire restaurée d'une
sauvegarde d'état. Marqueur : `REWINDBOX_GOW3_MLAA_SAVESTATE_UNTOUCHED_929`. **Rien n'a encore tourné sur un iPhone avec
ce Core.**

## 1. Ce que l'appareil montre (journaux privés, hors Git)

| Build | Reprise de la sauvegarde d'état de 2 098 179 072 octets | Contournement MLAA à la reprise | Image |
|---|---|---|---|
| 723 (PID 48721) | oui | non (`GOW3MLAA909 ppu=savestate_memory savestate_patched=0`, MLAA actif) | aucun défaut signalé |
| 724 (PID 50194, sessions 4 et 6) | oui | écrit dans la mémoire restaurée (`ppu=savestate_applied`) | défauts graphiques |
| 725 (PID 52378, session 4, vidéo) | oui | écrit dans la mémoire restaurée (`ppu=savestate_applied`) | correcte 3 s, puis au premier menu pause : textures du menu avec le rouge et le bleu échangés, puis décor opaque en aplat jaune-olive, de façon durable |

Mainteneur, 11 novembre 2026 : « le problème de GW3 n'arrive que lorsque je charge une sauvegarde ». Les démarrages
normaux des builds 724 et 725 appliquent le même contournement au démarrage, avant que le jeu ne s'initialise, et ne
présentent pas le défaut.

## 2. Cause (code)

Le contournement est la paire officielle « Disable MLAA » du dépôt de correctifs de RPCS3 : l'octet 0x52BF2F (le drapeau
MLAA du jeu) mis à 0 et l'appel 0x231248 remplacé par un nop. RPCS3 n'applique jamais un correctif d'exécutable à une
sauvegarde d'état : `ppu_load_exec` passe un nom vide au moteur de correctifs quand une sauvegarde est restaurée
(`patch_engine::apply(applied, !ar ? hash : std::string{}, …)`, `rpcs3/Emu/Cell/PPUModule.cpp`). Le Core 922 a fait
exception pour God of War III et a écrit la paire dans la mémoire restaurée d'une sauvegarde faite sans elle : le jeu
reprenait avec son MLAA déjà mis en place (tampons, travaux SPU, chaîne de rendu) et son propre drapeau effacé sous lui.
L'image casse au premier changement d'état qui relit ce drapeau (le menu pause), ce que la vidéo montre.

Les réglages changés en 724 (résolution 100 %, RSX multithread coupé, cache FIFO de 1 Kio, réservations précises,
streaming asynchrone puis coupé en 725) s'appliquent aussi aux démarrages normaux, qui sont corrects : ils ne sont pas
la cause. L'attribution précédente au streaming asynchrone des textures était fausse (réfutée par la build 725).

## 3. Correction

Le chargeur revient à la règle du Core 921 et de RPCS3 : la paire est écrite au démarrage normal seulement. Une sauvegarde
d'état reprend telle qu'elle a été faite : `ppu=savestate_memory`, avec `savestate_patched=0` (MLAA actif, comme en 723)
ou `savestate_patched=1` pour une sauvegarde faite après un démarrage normal avec le contournement (pas de MLAA). La
valeur `savestate_applied` du rapport reste définie pour lire les journaux des builds 724 et 725 ; elle n'est plus
produite. Deux fichiers : `rpcs3/Emu/Cell/PPUModule.cpp` (le chargeur redevient celui du Core 921, avec le commentaire de
la règle) et `rpcs3/ios/IOSGow3MlaaReport.h` (commentaire). Aucune entrée de génération de code ; identités PPU a987639e /
SPU 477a3fa4 inchangées.

## 4. Contrôle (hôte)

`test/rpcs3_gow3_mlaa_savestate929_test.py` extrait du chargeur réel sa condition d'application et la compile avec la
vraie table `rpcs3/ios/IOSGow3MlaaPatch.h` sur un modèle de mémoire (g++ ASan+UBSan, clang) : 13 vérifications — la
mémoire restaurée d'une sauvegarde, avec ou sans la paire, garde passée ou refusée, 01.00 ou 01.03, n'est pas modifiée
d'un octet ; un démarrage normal écrit exactement ce que le Core 921 écrivait. Contre-épreuve toujours exécutée : la règle
du Core 922 remise dans le modèle est détectée ; le test refuse la source du Core 928. Le pilote du Core 929 remplace le
test du Core 922 par celui-ci ; les tests 909 et 916 acceptent les deux formes.

## 5. Bilan

- **Coût supprimé** : aucun ; c'est un retour en arrière d'un défaut d'image.
- **Coût restant** : sur une sauvegarde faite sans le contournement, le MLAA du jeu tourne de nouveau (une relecture du
  tampon couleur 1280×720 par image, 206-266 ms par fenêtre de 5 s en 723). Une sauvegarde faite après un démarrage
  normal n'a pas ce coût.
- **Chemin critique** : inchangé par rapport à la build 723 sur une sauvegarde ancienne ; inchangé par rapport à la 725 au
  démarrage normal.
- **Mémoire** : inchangée.
- **Risque** : aucun connu ; le comportement est celui des builds 721 à 723 pour les sauvegardes d'état.
- **À observer sur l'iPhone** : reprise de la même sauvegarde, ouverture et fermeture du menu pause, `GOW3MLAA909
  ppu=savestate_memory`.

## 6. Menu en jeu (même livraison, pont hôte)

`REWINDBOX_MENU_RESOLUTION_729` : la ligne « Échelle de résolution » affiche la valeur appliquée au dernier démarrage du
jeu (lue dans sa ligne `CONFIG_LAYERS`) et la liste coche ce choix. En 724 et 725 God of War III tournait à 100 % alors que
le menu n'affichait aucune valeur ; le 75 % des builds 674 à 723 venait de l'ancien fichier complet du profil, retiré par
le Core 922, et non d'un choix enregistré par jeu.
