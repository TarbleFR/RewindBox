# RPCS3 — ce qui a changé et ce qui a été testé, IPA 723 → 724 → 725 (constat du 11 novembre 2026)

Demande du mainteneur (11 novembre) : « c'est bizarre que depuis deux ipa plus rien ne fonctionne ! Les diagnostics et
les réglages fournis doivent démontrer ce qui as changer et ce qu'il as était tester depuis ! »

Sources : les journaux exportés par l'iPhone (A18 Pro, 2 cœurs performance + 4 cœurs efficacité, 8 Go) pour les builds
620 à 725 et l'enregistrement d'écran de la build 725. Journaux privés, hors Git. Chaque chiffre ci-dessous vient d'une
ligne de journal de l'appareil ; rien n'est une mesure sur PC.

## 1. Réglages réellement appliqués au démarrage (lignes `CONFIG_LAYERS` et `Resolved boot policy`)

### God of War III (BCES00510)

| Réglage | Builds 674 à 723 | Build 724 | Build 725 |
|---|---|---|---|
| Origine des réglages | fichier complet de l'ancien profil RewindBox | base RPCS3 | base RPCS3 |
| Résolution | 75 % | **100 %** | 100 % |
| RSX multithread | activé | **coupé** | coupé |
| Réservations SPU précises | coupées | **activées** | activées |
| Cache de lecture FIFO | 4 Kio | **1 Kio** | 1 Kio |
| Temporisation GETLLAR mobile | activée | **coupée** | coupée |
| Streaming asynchrone des textures | coupé | **activé** | coupé |
| Soumissions MoltenVK asynchrones | coupées (694-723) | coupées | **activées** |
| Contournement MLAA sur une sauvegarde d'état | non appliqué | **appliqué** | appliqué |
| Identiques partout | Write Color Buffers activé, précision Ultra, blocs SPU Mega, shaders Legacy, limite d'images Auto | | |

Six réglages ont changé d'un coup dans la build 724, quand le profil RewindBox du jeu a été supprimé et le fichier
complet ignoré (règle du 10 novembre : la base RPCS3 est la référence, 100 % par défaut, profil supprimé). Le
contournement MLAA à la reprise d'une sauvegarde d'état est arrivé dans la même build.

### Call of Duty: Black Ops II (BLES01717)

Réglages identiques de la build 694 à la build 724 (base RPCS3, 100 %, Write Color Buffers coupé, blocs SPU Safe,
réservations précises, RSX multithread coupé, un réglage par jeu de l'utilisateur). Un seul changement en 725 :
soumissions MoltenVK asynchrones activées.

## 2. Ce que l'iPhone a mesuré

### Black Ops II, fenêtres de jeu (plus de 1000 dessins par image)

| Build | État thermique 1 : médiane (fenêtres de 5 s) | État thermique 2 : médiane (fenêtres) | Mémoire médiane |
|---|---|---|---|
| 643 | 31,8 (3) | 28,6 (21) | 4,1 Go |
| 662 | 26,6 (41) | 21,5 (59) | 3,2 Go |
| 666 | — | 25,3 (53) | 3,3 Go |
| 721 | 30,9 (29) | — | 3,1 Go |
| 723 | 41,0 (7) | 30,3 (26) | 3,4 Go |
| 724 | — | 28,8 (36) | 3,7 Go |
| 725 | 44,8 (5) | 30,1 (19) | 2,8 Go |

Dans chaque build la partie commence vers 50 images par seconde puis baisse : 721 : 53 puis 38-30 ; 723 : 51, 42-36
puis 36-28 ; 724 (téléphone déjà à l'état 2) : 55, 35 puis 23-33 ; 725 : 54, 47-38 puis 40-23. En 725, du début à la
fin de la partie, le travail par image est constant (12 000 à 15 000 PUTLLC réussis et 1 700 à 3 300 dessins par
image, environ 5 cœurs occupés sur 6), alors que le coût d'un même dessin sur le thread RSX monte de 30 à 60 % et le
temps GPU par image de 10 à 12-14,5 ms ; l'état thermique passe de 1 à 2 après 35 s de partie. Lecture : la puissance
disponible baisse quand le téléphone chauffe. C'est une déduction ; la fréquence du processeur n'est pas dans les
journaux.

Autres mesures de la build 725 : aucun épisode de gel en 127 s de partie (724 : gel à la fenêtre 41, environ 3 min 25) ;
`RSXSYNC551 submit` 0,06-0,08 ms par image (724 : 3,2-5,6) ; aucun délai d'acquisition ni d'encodage dépassé
(`OPT587`) ; empreinte 2,6 → 3,0 Go (724 : 3,4 → 4,1), blocs graphiques inutilisés 32-106 Mio (724 : 45 → 360) ;
mémo de textures : 35 000 à 104 000 réutilisations par fenêtre, 600 à 1 700 vérifiées, 0 différence ; 12 compilations
de pipeline bloquantes en 2 minutes (images de 0,5 à 1,7 s).

### God of War III, fenêtres de jeu (plus de 500 dessins par image)

| Build | Résolution | État thermique | Médiane (fenêtres) | Image |
|---|---|---|---|---|
| 723 | 75 % | 1 | 14,4 (69) | correcte (aucun défaut signalé) |
| 724 | 100 % | 1 | 13,4 (28) | erreurs graphiques signalées |
| 725 | 100 % | 2 | 8,0 (5, pendant l'enregistrement d'écran) | erreurs graphiques (vidéo) |

Vidéo de la build 725 (reprise de la même sauvegarde d'état que les sessions de la build 724) : image correcte
pendant 3 s ; à l'ouverture du menu pause, textures du menu avec le rouge et le bleu échangés et formes correctes ; au
retour en jeu, géométrie opaque en aplat jaune-olive, ciel et brume corrects ; l'état reste faux. Dans la fenêtre du
menu : 22 189 copies RSX traitées par le processeur, 254 Mio de textures dont les octets ont changé, 152 vidages
d'un tampon de rendu vers la mémoire du jeu.

## 3. Ce qui a été modifié dans chaque IPA et son niveau de vérification

| IPA | Modification | Vérifié sur PC | Observé sur l'iPhone |
|---|---|---|---|
| 724 | Contournement MLAA écrit dans la mémoire d'une sauvegarde d'état (Core 922) | 13 vérifications sur le chargeur réel | appliqué (`savestate_applied`) ; relectures du tampon couleur 72-75 → 0 par fenêtre |
| 724 | Règle de la base RPCS3, profil God of War III supprimé (Core 922 + application) | 9 vérifications : la règle applique bien la base | appliquée (tableau 1). **L'image du jeu avec ces réglages n'avait été vérifiée nulle part avant la livraison** ; les erreurs graphiques commencent à cette build |
| 724 | Relevé de gel avec les mots de réservation, échantillonnage SPU (Core 922-923) | tests des lignes | lignes présentes et exploitées |
| 725 | Base RPCS3 : le streaming asynchrone des textures n'est plus appliqué sur iOS | tests Dart | appliqué (`async_tex=false`) ; **les erreurs graphiques persistent : cette cause, donnée après la 724, était fausse** |
| 725 | PUTLLC : attente avant le verrou de ligne (Core 924) | modèle hôte | aucun gel en 127 s ; à confirmer sur une partie de plus de 4 minutes |
| 725 | Mémoire graphique compacte (Core 925) | modèle sur l'allocateur réel | blocs inutilisés 32-106 Mio au lieu de 45-360 |
| 725 | Mémo de textures de Black Ops II (Core 926) | 4,68 millions de réutilisations rejouées | 600 à 1 700 vérifications par fenêtre de 5 s, 0 différence |
| 725 | Soumissions MoltenVK asynchrones pour chaque titre (Core 927) | modèles hôte | envoi 3,2-5,6 → 0,06-0,08 ms par image, aucun délai dépassé |
| 725 | Arrêt du rendu à la désactivation de l'application (Core 928) | modèle hôte | 2 désactivations (centre de contrôle), aucune perte du périphérique graphique |

Aucune de ces modifications n'avait tourné sur un iPhone avant sa livraison : le seul banc est l'hôte, et l'appareil
est observé par les journaux renvoyés après chaque IPA.

## 4. Conclusions

- **Black Ops II n'a pas régressé** : mêmes réglages, images par seconde égales ou meilleures à état thermique égal,
  moins de mémoire, pas de gel observé. La baisse après le début de partie existe dans toutes les builds mesurées et
  suit l'échauffement.
- **God of War III a régressé à la build 724**, au moment exact où ses réglages ont changé (tableau 1) et où le
  contournement MLAA s'est appliqué aux sauvegardes d'état. Aucun fichier du moteur graphique (`rpcs3/Emu/RSX`) n'a
  changé entre les Cores 921 et 923 : la cause est un chemin du moteur choisi par ces réglages, jamais exécuté sur
  l'iPhone auparavant. Elle n'est pas encore identifiée.
- Les images par seconde de God of War III sont les mêmes en 723 et 724 à état thermique égal (14,4 et 13,4).

## 5. Suite

1. Relecture du moteur sur les chemins propres à 100 % et au RSX non multithread (transfert direct du tampon de rendu
   vers la mémoire du jeu, copies RSX, ordre des canaux), en cours.
2. Contrôle possible sur l'IPA 725 sans nouvelle compilation, par les réglages par jeu de God of War III : (a)
   Résolution 75 % seule ; (b) si l'image reste fausse, RSX multithread activé en plus. Le réglage qui rend l'image
   correcte désigne le chemin fautif.
3. Correction du moteur avec une preuve hôte du chemin fautif, puis une IPA ; la règle « base RPCS3, 100 % par
   défaut » reste en place.

## 6. Mise à jour du 11 novembre 2026 (après les deux messages suivants du mainteneur)

- « Je n'ai pas l'option Multithreaded RSX » : exact. Le menu en jeu de RewindBox ne propose que l'échelle de résolution,
  l'étirement, l'affichage des performances, les tests de précision et la langue. Le contrôle suggéré en section 5 était
  impossible ; il est retiré.
- « la résolution à 75 % n'est pas la solution car je l'avais déjà avant sur ce curseur » : les journaux des builds 724 et
  725 montrent `rsx_res=100` et aucun réglage par jeu enregistré (`sparse_overrides=0`) ; le 75 % des builds 674 à 723 venait
  de l'ancien fichier complet du profil. Le menu n'affichait aucune valeur : il affiche maintenant la valeur appliquée au
  dernier démarrage et la coche dans la liste (`REWINDBOX_MENU_RESOLUTION_729`).
- « le problème de GW3 n'arrive que lorsque je charge une sauvegarde » : **cause trouvée**. Le Core 922 écrivait le
  contournement MLAA dans la mémoire restaurée d'une sauvegarde d'état faite sans lui, ce que RPCS3 ne fait jamais ; le jeu
  reprenait avec son MLAA en place et son drapeau effacé, et l'image cassait au premier menu pause. Les réglages changés en
  724 s'appliquent aussi aux démarrages normaux, qui sont corrects : ils ne sont pas la cause. Le Core 929 retire cette
  écriture ([compte rendu](rpcs3-core929-gow3-savestate-untouched.md)). La section 4 ci-dessus est corrigée d'autant.
