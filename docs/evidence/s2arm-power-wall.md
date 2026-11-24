# Ennemi n°1 : tenir 60 i/s en session longue malgré le plafond de puissance d'iOS

Épinglé le 24 novembre 2026 à la demande du mainteneur. Jeu mesuré : Mario Kart World 1.0.0
(`0400C3F00006E000`) sur iPhone 16 Pro Max (A18 Pro). Le mainteneur constate le même comportement
sur ses autres jeux Switch 2 ; aucun journal d'un autre jeu n'est encore analysé.

**Statut :** diagnostic tiré de quatre journaux de l'IPA 830 (réglages par défaut sur deux
lancements, tests A, B et C) et des journaux de course des IPA 759 à 827. Rien n'est corrigé ici et
aucun gain n'est mesuré. Les journaux bruts restent privés ; seuls les chiffres en sont repris.

## Ce que voit le mainteneur

En course, 25 à 30 i/s, que la limite d'images soit « sans limite » ou 60. Ce réglage n'est qu'un
plafond, et aucun réglage du moteur n'impose 30. Le jeu choisit lui-même : il demande 60 dès que ses
images passent sous 16,7 ms et passe à l'intervalle 2 (30 i/s) quand elles sont trop lentes. Le
mainteneur ne veut pas de 30 i/s, ni de baisse de résolution.

## Deux murs

Fenêtres de 300 images en course (au moins 900 dessins par image) dans les quatre journaux 830.
Médiane, puis premier et neuvième déciles entre crochets.

| | Course à pleine fréquence (33 fenêtres) | Course plafonnée (61 fenêtres) |
| --- | --- | --- |
| Image p50 | 23,7 ms [19,0–31,2] | 41,5 ms [36,6–51,6] |
| GPU p50 | 12,0 ms [10,4–13,3] | 34,2 ms [31,5–37,5] |
| Sonde GPU fixe | 0,24 ms [0,19–0,51] | 0,82 ms [0,79–0,95] |
| Images par seconde | 39,1 [29,5–48,7] | 24,1 [19,6–27,0] |
| Cœurs P : travail @ fréquence | 1,19 cœur @ 1,81 GHz | 0,69 cœur @ 3,65 GHz |
| GPU occupé | 457 ms/s | 800 ms/s |
| CPU du processus | 1,19 W | 1,43 W |

1. **À pleine fréquence, la course ne tient déjà pas 60.** Le GPU n'a besoin que de 10 à 13 ms,
   mais l'image en prend 19 à 31. Le processeur soumet l'image morceau par morceau, puis le jeu
   attend la fin du GPU avant de préparer l'image suivante : les deux travaillent l'un après
   l'autre au lieu de se chevaucher.
2. **Après 15 à 38 s de course, iOS plafonne la puissance de la puce.** Sur 11 phases de course d'au
   moins 3 fenêtres, 8 passent au plafond après 15 à 38 s. Deux autres commencent déjà plafonnées,
   parce que le menu précédent n'a pas rendu la fréquence. La dernière s'arrête après environ 30 s
   sans plafond.
   - La sonde GPU fixe fait toujours le même calcul (16 384 fils, 2 048 itérations en registres,
     une seule écriture). Sa durée passe de 0,24 à 0,82 ms, soit 3,4 fois plus.
   - Toutes les passes du profil GPU ralentissent, de 2,2 à 3,2 fois en médiane. Les passes de 1×1
     pixel ralentissent de 2 à 4 fois. C'est l'horloge du GPU qui baisse, pas une passe qui coince.
   - Le plafond apparaît aux états thermiques 0, 1 et 2. L'état thermique iOS ne le prévient pas.
   - Le processeur monte alors à 3,65 GHz pour 0,69 cœur de travail. Le test C, sans échéances
     temps réel ni priorité élevée, montre le même sprint : il ne vient pas de nos réglages.

Sortir du plafond demande une phase plus légère, de durée variable. Dans le test C, environ 28 s de
menu à 53 i/s ne suffisent pas ; le GPU y reste occupé 590 à 810 ms par seconde.

## Pistes écartées par la mesure

| Hypothèse | Vérification | Résultat |
| --- | --- | --- |
| Patchs 0333, 0335 et 0337 de la 830 | Test A : `S2A_RB_ACQUIRE_FENCE=0`. Test B : A + `S2A_RB_GUEST_QOS_THERMAL=1` et `S2A_RB_PIECE_DRAIN=1` | Plafond après 24 puis 20 s (A), 21 puis 15 s (B) |
| Échéances temps réel et priorités des fils | Test C : `DM_RT=0`, `S2A_RB_ENC_RT=0`, `S2A_GUEST_QOS=initiated` | Plafond après 38 puis 27 s |
| Un correctif précis | Historique 759 à 830, ci-dessous | Piège présent dès la 759, présent ou absent d'une session à l'autre dans une même IPA |
| Le passage à 30 i/s ferait ralentir le GPU | IPA 765, 778, 779, 785, 786, 795, 802 | En 795, 5 700 images à 30 avec un GPU normal ; une limite manuelle à 30 n'a jamais déclenché le piège ; image par image, le GPU ralentit d'abord, de 16,6 à environ 35 ms en 10 à 15 images, le jeu passe à 30 ensuite |
| Batterie | Historique | Piège à 85–90 % de charge, aucun à 35 % |
| Déclarer les échéances à iOS (`S2A_WORKGROUP`) | Mesure de l'auteur de S2Arm | La consommation monte de 1,69 à 2,47 W |
| `S2A_RES_SCALE` | Journaux 827 | En course, le jeu annule la réduction ; le mainteneur refuse de toute façon les baisses de résolution |

## Historique du piège en course

| IPA (dates) | Piège GPU | Changements côté GPU à ce moment |
| --- | --- | --- |
| 731–758 (12–16 nov.) | Pas de course exploitable | — |
| 759, 762, 765, 773 (16–17 nov.) | Oui, même signature que la 830 | 0068 (770) : sonde GPU fixe ; 0073 (770) : fil d'encodage en priorité temps réel |
| 775–783 (17–18 nov.) | Non | 0083 (778) : temps GPU lus par le jeu maintenus à 16,6 ms, ou à 33,2 ms après 1 s à 30 i/s |
| 785, 786 (18 nov.) | Oui (785 : 1 session sur 2 ; 786 : 2 sur 2) | Lu à l'époque comme « charge GPU + passage à 30 Hz », d'où 0115 (787) : écran gardé à 60 Hz |
| 787–799 (18–20 nov.) | Non, sur une douzaine de courses | — |
| 801–803 (20 nov.) | Oui (802 : 1 session sur 2) | 0170 (803) : le moteur suit l'intervalle demandé par le jeu |
| 804–819 | Inconnu, aucun journal de course | 0240 (813) : fils secondaires du jeu en priorité réduite à l'état Fair |
| 820–825 (22–23 nov.) | Oui (825 : 2 sessions sur 3) | Lu comme un « verrou à 30 i/s », d'où 0309 (823) puis 0319 (827) : retours à 60 tentés sur quelques images |
| 827 (23 nov.) | Non, un seul épisode d'environ 120 images | — |
| 830 et tests A, B, C (24 nov.) | Oui, dans les 4 journaux | 0333, 0335 et 0337 écartés par les tests A et B |

Les correctifs 0115, 0309 et 0319 visaient le symptôme, le jeu resté à 30, et non la baisse
d'horloge. Le maintien à 33,2 ms de 0083 aggrave le blocage : une fois à 30, le jeu ne lit plus de
temps GPU sous 33 ms, même quand le GPU retrouve sa fréquence.

## Ce que font les autres projets

- **Plumber Racer 2** fait tourner Mario Kart World sur iPhone 18 Pro (A20 Pro). Une course tient
  60 i/s pendant 53 à 70 s. Ensuite, à nombre de dessins égal, soit le GPU passe de 8 à 21 ms par
  image (environ 38 i/s), soit le processeur tombe de 4,7 à 2,1 GHz (environ 46 i/s), téléphone
  froid compris. Le projet ne l'a pas résolu.
- **nxnative**, dont Plumber Racer 2 est issu, remplace dans Mario Kart World la fonction qui choisit
  d'avancer d'une ou de deux synchros d'écran. Un stub lui donne le pas du moteur : le jeu avance
  alors du temps réellement écoulé, entre 0,99 et 1,02 fois le temps réel sur Mac. Le choix entre 60
  et 30 se fait sur une moyenne, pas sur une image isolée. Code sous licence MIT.
- **S2Arm amont** n'a ni ce stub ni ce choix par moyenne. Mesures publiées par son auteur :
  l'attente des fils inactifs par courts sommeils fait passer la consommation de 5,24 à 1,69 W ; ce
  réglage est déjà actif chez nous. Un correctif de passes du même type que 0314 fait passer le GPU
  occupé de 763 à 518 ms par seconde.

## Où part l'énergie évitable

**Trafic des cibles de rendu.** Sur 95 fenêtres de course des quatre journaux 830, le moteur charge
puis écrit 652 Mio par image en médiane (546 à 703 ; 302 Mio chargés et 350 Mio écrits). Une centaine
de passes par image chargent puis réécrivent toutes leurs cibles (68 à 112). Hors course (menus et
chargements), le moteur en déplace encore 505 Mio par image en médiane, avec 47 passes de ce type.

La cause : depuis 0296, les optimisations de mémoire tuile sont coupées pour les jeux hébergés. Ces
optimisations évitent des chargements et des écritures, et continuent une passe au lieu de la
rouvrir. Les jeux Switch 2 lisent
beaucoup de textures par poignée indirecte, rangée dans un tampon d'uniformes (38 % des shaders de
Mario Kart World), et le moteur ne peut plus prouver qu'une cible ne sera pas relue.

Ces octets sont des octets logiques. D'après l'[analyse 824](s2arm-pass-traffic-824.md), une bonne
part est de la comptabilité, notamment un atlas d'ombres de 6144×6144 presque vide. Le trafic réel,
150 à 250 Mio par image, vient de trois sources :
- la passe principale de 1248×700, rouverte 6 à 11 fois par image ;
- 4 à 6 copies de la profondeur par image ;
- les passes plein écran.

Trois réductions y sont chiffrées, sans avoir été faites, pour 65 à 130 Mio réels par image :
- continuer sur la même cible au lieu de la rouvrir : 30 à 75 Mio ;
- ne pas recharger une cible que le premier dessin recouvre entièrement : 30 à 35 Mio ;
- laisser de côté les plans de profondeur ou de stencil inutilisés : 5 à 20 Mio.

**Maintien à 33,2 ms.** Une fois l'intervalle 2 tenu une seconde, le jeu lit au moins 33,2 ms de GPU
et ne revient plus à 60 de lui-même. Les sorties bornées de 0319 ne durent que quelques images.

## Plan validé le 24 novembre 2026

1. **Moins d'énergie par image, pour tous les jeux.** Trois réductions de trafic, sûres malgré les
   textures lues par poignée indirecte : continuer la même cible, ne pas recharger une cible
   recouverte, laisser les plans inutilisés. Ensuite, plus de maintien à 33,2 ms pour un jeu qui
   alterne 60 et 30. Chaque changement a son interrupteur `S2A_RB_*`.
2. **Faire travailler le processeur et le GPU en parallèle**, pour tenir 16,7 ms par image à pleine
   fréquence.
3. **Filet de sécurité, jeu par jeu :** avancer du temps réellement écoulé quand les i/s baissent,
   d'après le stub de nxnative.

La baisse de résolution est exclue à la demande du mainteneur.

**Mesures attendues à chaque IPA**, en courses de 10 minutes :
- trafic des cibles par image ;
- GPU p50 et sonde fixe ;
- délai avant le premier plafond ;
- part des fenêtres plafonnées ;
- images par seconde tenues.

**Objectifs :**
- à pleine fréquence, image p50 sous 16,7 ms ;
- plafond plus tardif que les 15 à 38 s mesurés ici, puis aucune fenêtre plafonnée en 10 minutes.

**Limite.** Rien ne garantit 60 i/s tenus en longue session sur un iPhone 16 Pro Max. La Switch 2
a un ventilateur et une enveloppe d'énergie bien plus large qu'un téléphone. Chaque étape doit en
revanche augmenter les i/s tenues dans la durée, et chaque IPA dira de combien.

## Étape 1 : patchs 0342 à 0344

**Statut :** écrits le 24 novembre 2026, relus par deux relectures adverses indépendantes, corrigés,
puis complétés (limites ci-dessous). La version relue compile pour iOS (run 45378584979, macOS 15
et 26, tests thermiques, DRS et passes GPU verts) ; les compléments et 0345–0346 sont à recompiler.
Rien n'est observé sur iPhone ; aucun gain n'est mesuré.

| Patch | Changement | Interrupteur (`env.txt`) |
| --- | --- | --- |
| 0342 | Quand le jeu rebinde les cibles déjà en place, la passe continue au lieu d'être fermée, écrite en mémoire puis rechargée. Idée reprise de l'amont S2Arm (`fb96ab7db`, section 3). Visé : 30 à 75 Mio réels par image. | `S2A_RB_RT_CONT=0` |
| 0343 | Pas de chargement d'une cible couleur que le premier dessin de la passe recouvre entièrement. Visé : 30 à 35 Mio réels par image. | `S2A_RB_COVER_LOAD=0` |
| 0344 | La garde anti-verrou à 30 i/s de 0319 vaut pour tout jeu vu alterner 60 et 30, plus seulement Mario Kart World. | `S2A_RB_NO_LOCK_SEEN=0` |

**Pourquoi c'est sûr malgré les textures lues par poignée indirecte (0342).** Avant chaque dessin
d'une passe continuée, le moteur résout les textures que ce dessin va lire, comme il le fait pour les
lier : emplacements liés, poignées lues dans les tampons d'uniformes, tableaux de poignées. Si l'une
est une cible de la passe (n'importe quelle couleur, ou la profondeur), la passe est coupée avant ce
dessin, comme elle l'était avant le patch. Les dessins de tessellation et les dessins task/mesh
passent par le même test. Coupent aussi :
- une texture choisie par un index calculé dans le shader ;
- un shader sans liste de liaisons ;
- DrawTexture.

La preuve « couleur jamais écrite jusqu'à la fin de passe » suit la passe prolongée. Elle ne peut
qu'en prouver moins qu'avant, jamais plus ; elle ne faisait gagner que 0,7 à 1,4 Mio par image.

La passe n'est pas continuée s'il reste des effacements en attente, des mises à niveau d'images en
attente, une barrière du jeu en attente, des textures à remettre en taille réelle (résolution
interne) ou un effacement juste après. Même chose pour une passe en couches, l'écran élargi et les
cibles d'affichage, de vidéo, linéaires ou creuses.

**0343.** La preuve existante ne lit que l'état du dessin : pas de mélange, tous les canaux écrits,
aucun rejet de fragment, sommets lus côté processeur. Le patch ajoute des refus pour le test alpha,
le « rasterizer discard », les étages géométrie et tessellation, les passes en couches, le swizzle
de viewport, le redémarrage de primitive et une résolution interne dont l'échelle ne tombe pas
juste sur le stockage. Si le premier dessin n'est finalement pas dessiné (pipeline en compilation,
pas de pipeline, rien à dessiner), la passe se termine aussitôt : la cible n'est pas écrite et la
mémoire garde son contenu.

**0344.** Un jeu est « vu alterner » après 8 passages entre les intervalles 1 et 2 en 600 images,
le critère de l'essai 0309. Les passages entre 2 et 3 (Donkey Kong Bananza) ne comptent pas. Après
1 800 images sans passage 1↔2, la garde s'éteint ; l'essai 0309 continue. Un jeu à 30 i/s par
conception ne change presque jamais d'intervalle : il garde son maintien à 33,2 ms.

**Relectures adverses du 24 novembre.** Deux relectures indépendantes ont trouvé deux vrais défauts
par patch ; tous sont corrigés :

| Patch | Défaut trouvé | Correction |
| --- | --- | --- |
| 0342 | Les marques « cible modifiée » ratent DrawTexture, la tessellation, l'effacement dessiné en triangle et les shaders sans liste de couleurs : un dessin aurait pu lire une cible pas encore écrite en mémoire. | Toute cible de la passe compte, modifiée ou non. |
| 0342 | Les shaders task et mesh (Mario Kart World en a) n'étaient pas vérifiés. | Leurs liaisons sont résolues aussi ; la tessellation passe par le même test. |
| 0342 | Risques : barrière du jeu reportée, remise en taille réelle reportée, indicateur « en couches » toujours à 0. | La porte refuse ces cas ; l'indicateur vient de la passe ouverte. |
| 0343 | Un premier dessin couvrant non dessiné, suivi d'une autre écriture dans la passe, aurait écrit en mémoire un contenu indéfini. | La passe se termine aussitôt ; la cible n'est plus marquée « fraîche ». |
| 0343 | Risques : arrondi de la résolution interne (dernière colonne non dessinée), redémarrage de primitive. | Refus dans les deux cas. |
| 0344 | Un jeu qui alterne 2 et 3 serait passé sous la garde, qui ne recule jamais dans ce cas. | Seuls les passages 1↔2 comptent. |
| 0344 | Risque : un jeu à 30 par conception, vu alterner dans un menu, gardé toute la session. | La garde s'éteint après 1 800 images sans passage 1↔2, et à chaque nouvelle session. |

Gains de la relecture : le balayage « jamais écrit » s'arrête là où la porte refusera de toute
façon (effacement juste après, cibles externes), au lieu de ne rien prouver. L'anticipation des
multi-dessins masqués (0072) traverse un rebind des mêmes cibles : sinon son calcul aurait coupé la
passe continuée.

**Limites relevées par les relectures, corrigées ensuite :**

| Limite | Correction | Interrupteur |
| --- | --- | --- |
| Une passe continuée perdait, à sa fin, l'économie d'écriture d'un rejet du jeu juste avant. | Le rejet s'applique aussi à la fin d'une passe continuée (cibles identiques). | `S2A_RB_RT_CONT=0` |
| Le test par dessin résolvait toutes les liaisons à chaque dessin (quelques centaines de µs à 2 ms par image, estimation de la relecture). | La réponse du dessin précédent est gardée tant que ses arguments n'ont pas changé, aux mêmes conditions que la réutilisation du bloc d'arguments. Compteur dans la ligne `[gpu-pass] same-target continuations`. | `S2A_RB_RT_CONT_MEMO=0` |
| Les marques « cible modifiée » rataient DrawTexture, la tessellation, les effacements dans la passe et les shaders sans liste de couleurs (défaut antérieur à 0342). | Patch 0346 : toute écriture de la passe marque sa cible, comme le registre des écritures. | `S2A_RB_FB_MARKS=0` |
| 0343 ne refusait pas un shader qui choisit son viewport. | Refus dès que le jeu a réglé un autre viewport différent du premier. | `S2A_RB_COVER_LOAD=0` |
| 0344 n'avait pas de désactivation par jeu (`env.txt` vaut pour tous les jeux). | `S2A_RB_NO_LOCK_SEEN_OFF=<identifiant>[,…]` désactive la garde pour ces jeux seulement. | — |

**Reste ouvert :** une passe continuée garde les économies liées à un effacement qui suit désactivées
(elles lisent la frontière d'une passe non continuée).

**Pas fait : laisser de côté les plans de profondeur ou de stencil inutilisés.** Le gain visé n'était
que de 5 à 20 Mio par image. Ces plans font partie de la description des pipelines Metal : une passe
sans eux demande de nouvelles variantes, compilées au premier dessin, donc un risque de saccades.

**Ce que le prochain journal doit montrer :**
- lignes `[gpu-pass] same-target continuations` : continuations par image et coupures (lecture d'une
  cible, liaison non résolue, DrawTexture) ;
- lignes `[gpu-pass] loads left out under a covering first draw` : chargements évités, en nombre et
  en Mio par image, et premiers dessins non dessinés ;
- trafic des cibles par image (référence 830 en course : 652 Mio) et passes « tout chargé, tout
  écrit » (référence : une centaine) ;
- aucune ligne « lookahead wrong » ;
- GPU p50, sonde fixe, délai avant le premier plafond, part des fenêtres plafonnées, i/s ;
- lignes `[gpu-pass] loads left out under a covering first draw` : « pass ended at once » compte les
  premiers dessins non dessinés ;
- pour un autre jeu : la ligne « the game alternates present intervals 1 and 2 », puis les sorties de
  la garde, et « no longer alternates » s'il s'arrête.

## Zelda et Mario Kart World : diagnostic croisé (24 novembre)

Sources : journal Zelda `0400486024DEC000` (moteur 0332–0340 des IPA 830 et 831, trois sessions) et ses 24 profils de capture,
comparés aux journaux 830 de Mario Kart World. Les deux jeux ne butent pas sur le même mur :

| | Mario Kart World | Zelda |
| --- | --- | --- |
| GPU | plafonné par iOS : sonde fixe ×3,4 après 15 à 38 s | à pleine fréquence (sonde 0,21 à 0,25) mais saturé : GPU p50 21 à 31 ms, occupé 77 à 95 % du temps |
| Images par seconde en jeu | 24 à 39 | 27 à 36 (jeu à 30 en pratique) |
| Fil de traduction | 13,5 à 19,5 ms par image | 15 à 23 ms par image pour 1 300 à 2 300 dessins, presque sans cœur performance (0,01 à 0,3 cœur à 1,26 GHz) en état thermique « serious » |
| Shaders à accès mémoire brut | aucun | 7 à 16 ms de GPU par image |
| Cible principale rouverte | 1248×700, 6 à 11 fois par image | 854×480, 24 à 36 fois par image (cible de 0342) |

Points communs : environ 33 000 instructions par dessin sur le fil de traduction, environ 97 000 par
ouverture de passe, et 13 700 réveils par seconde de fils qui attendent en boucle (Zelda).

**Profil du fil de traduction de Zelda** (trois captures de la session 1, 298 échantillons) :
- dessin : 51 % (liaisons et arguments 32 %, dont recherche de textures 9 %) ;
- fin de sous-lot : 12 %, dont 9 % dans la fonction elle-même ; 17 de ses 27 échantillons tombent
  sur une seule adresse. Le désassemblage du binaire 830 la place dans `gw_commit` : à chaque
  sous-lot, chaque page que les shaders ont écrite est reportée une à une dans la table des
  écritures GPU (16 384 cases de 24 octets, accès dispersés). Avec `_sbw_note` (4,7 %), qui note ces
  pages à chaque dessin, le suivi des écritures GPU prend environ 14 % du fil. Les shaders à accès
  mémoire brut de Zelda écrivent beaucoup de pages ; Mario Kart World n'en a pas. Piste : noter et
  reporter des plages contiguës au lieu de pages ;
- Objective-C et noyau : environ 20 % ;
- anticipations (balayages de la liste de commandes) : 4 %.

**Patch 0348** (`S2A_RB_GW_RANGES`, actif ; `=0` rétablit l'ancien chemin) :
- une écriture GPU d'au moins 8 pages est gardée en une plage au lieu d'une entrée par page,
  pendant la soumission puis jusqu'à la fin de son travail GPU ; les contrôles répondent pour
  la plage comme pour ses pages ;
- listes pleines (64 plages par soumission, 128 vivantes) : retour page par page, compté, jamais
  perdu ;
- réponses jamais moins prudentes que la réalité : un test pur compare l'ancien chemin, le
  nouveau et une référence exacte sur des millions de requêtes (gcc et clang) ; le nouveau a moins
  de faux « écrit » que l'ancienne table (collisions) ;
- compteurs ajoutés à la ligne `[nvn] submit costs`. Gain non mesuré : le profil de Zelda est à
  refaire sur iPhone.

**Conséquence.** Pour Mario Kart World, l'ennemi est l'énergie : moins de travail par image retarde
le plafond. Pour Zelda, il faut d'abord du temps GPU (shaders à accès mémoire brut, passes) et un fil
de traduction plus léger. 0342 vise les deux ; la suite (ci-dessous) vise surtout Zelda.

## Fire Emblem (24 novembre)

Source : journal `04007EF01F8AE000` (moteur 0332–0340, deux sessions, mode portable), avec ses neuf
images capturées. La session tournait au réglage de résolution 0,5 choisi dans le menu (rendu en
960×540 au lieu de 1920×1080 ; la valeur par défaut est 1).

- Le jeu demande 30 i/s (intervalle 2 dès l'image 7, jamais changé) : jeu à 30 par conception, que
  0344 ne touche pas.
- En jeu : 20 à 27 i/s ; 16 à 32 % des images ratent leur créneau de 33,3 ms et restent affichées
  deux fois (p95 à 66,7 ms).
- GPU : p50 de 18 à 33 ms presque à pleine fréquence, état thermique Nominal ou Fair, pas de plafond
  iOS. Une image capturée : environ 145 passes, 2 500 dessins, 24 à 25 ms de GPU ; 39 passes sur la
  cible 960×540 à une couleur (environ 6 dessins chacune), 37 passes sans dessin, 20 mini-passes.
- Processeur : traduction 11 à 20 ms par image pour 1 000 à 2 300 dessins, surtout sur les cœurs
  efficaces (environ 1,5 GHz) ; processeur à 0,3–0,9 W seulement.
- Compilations de pipelines en jeu : au moins 256 attentes ; 45 détaillées, médiane 20 ms, jusqu'à
  244 ms.

**Correction du même jour, sur les neuf images profilées (lignes `[gpuprof]`).**
- Les durées des passes se chevauchent sur le GPU : leur somme (19 à 22 ms) surestime le temps réel.
- Occupation réelle du GPU (union des intervalles) : 14,5 à 17 ms par image, alors que l'image
  s'étale sur 22 à 48 ms. Le GPU attend donc le processeur.
- Les 34 à 37 passes sans dessin (des effacements) n'occupent le GPU seules qu'environ 1 ms par image.

Ce qui empêche Fire Emblem de tenir 30, c'est le fil de traduction : 9 à 23 ms par image, sur des
cœurs performants à 1,3–1,9 GHz alors que le téléphone est froid (0,3 à 0,7 W). Le système ne
connaît pas l'échéance des images : le groupe de travail d'image (`S2A_WORKGROUP`) est coupé
depuis 0097, parce qu'il empêchait la mise en pause. L'amont mesurait 1,9 → 3,5 GHz avec lui, et
1,69 → 2,47 W au même 60 i/s.

Pistes :
- rendre le groupe de travail compatible avec la mise en pause, puis mesurer ;
- 0342 sur la chaîne 960×540, si les mêmes cibles y sont réattachées ;
- listes de pipelines.

C'est le meilleur candidat de l'interpolation d'images une fois les 30 i/s tenus.

## Gels de compilation en jeu (24 novembre)

Sources : journaux de Zelda (`0400486024DEC000`) et de Fire Emblem (`04007EF01F8AE000`) du
24 novembre, avec deux journaux de Mario Kart World du même jour pour comparer.

**Ce qui fige.**
- Zelda : 1 268 images longues, 170 s en tout, dont 102 s dans des images qui attendaient de
  nouveaux shaders ou pipelines.
- Pires images de Zelda : 8,5 s (23 pipelines et 17 bibliothèques de shaders) et 8,25 s
  (13 bibliothèques compilées en 5,3 s, dont 4,4 s d'attente du fil de rendu).
- Fire Emblem : jusqu'à 1,9 s.

**Le coût vient de la compilation Metal, pas de la traduction.**
- Zelda a compilé 2 042 bibliothèques depuis leur source MSL dans la session, pour 332 s de calcul.
- Au démarrage (état thermique 1) : 1 335 bibliothèques en 51 s, 38 ms chacune.
- En jeu (état thermique 2) : 390 à 410 ms chacune.
- La traduction en MSL ne prend qu'environ 11 s en tout (101 ms en moyenne par shader de pixels).

**Le cache système de Metal suffit quand il garde les shaders.**
- Une bibliothèque déjà vue revient en environ 1 ms : Fire Emblem 321 en 0,2 s, Mario Kart World
  3 893 en 3,4 s.
- Les shaders vraiment nouveaux coûtent 89 à 155 ms (états thermiques 0 et 1).
- Ceux de Zelda n'y étaient pas, alors que la plupart avaient été compilés lors des sessions
  précédentes.
- Cause non établie : cache vidé ou plein. Le pont demande 1 Gio (`MTL_SHADER_CACHE_SIZE`) au
  lancement du jeu, peut-être trop tard : Flutter ouvre Metal dès le démarrage de l'application.
  Non vérifié sur iOS.

**Les fils.**
- Un créneau « observé » (2 voies) traduisait un shader puis compilait sa bibliothèque à la suite
  (`S2A_RB_URGENT_CONTINUATION`).
- Résultat : au plus 2 compilations à la fois, pendant que les traductions suivantes attendaient
  un créneau.
- L'iPhone compile 4 bibliothèques à la fois (`maximumConcurrentCompilationTaskCount`).

**Ce que font les autres.**
- **Outil hors ligne de S2Arm** : il regroupe plusieurs shaders dans une seule compilation, parce
  que l'instanciation des modèles de textures de Metal coûte 111 ms sur 163 pour un gros shader.
  Non repris sur l'appareil : des groupes qui varient d'une session à l'autre ne seraient jamais
  retrouvés par le cache système, qui est indexé par la source.
- **maxmetal** ([nxnative #812](https://github.com/seedds/nxnative/pull/812)) traduit en quelques
  millisecondes, mais seulement le code Maxwell de la Switch 1. Les shaders des jeux Switch 2 sont
  du code Ampere. Il compile toujours le MSL sur l'appareil. nxnative l'a refusé : régression GPU
  dans Tears of the Kingdom (6,5 → 6,8 à 7,9 ms).
- **[nxnative #751](https://github.com/seedds/nxnative/pull/751)** précompile les shaders de l'hôte
  à la construction.
- **S2Arm Android** (24 novembre) : groupe de 4 fils de compilation, l'image en cours passe devant.
  Attente maximale de 244 à 1 311 ms ramenée à 24 à 50 ms, mesurée sur Android, pas sur iOS.

**Patch 0347.**
- La compilation qui suit une traduction a ses propres voies, à côté du fil de rendu. Le
  créneau de traduction se libère tout de suite. `S2A_RB_COMPILE_LANES=0` rétablit l'ancien
  comportement ; `1` à `4` fixe le nombre de voies.
- Le journal donne la taille du cache système et l'espace libre au début et à la fin du
  préchauffage, ainsi que le coût réel des compilations du préchauffage (environ 1 ms chacune
  quand le cache les a).
- Relecture adverse, sept points corrigés :
  - Seules les compilations de fin de traduction vont sur les voies. Un chargement demandé par
    la soumission reste sur la file observée : il peut devoir traduire d'abord, et cette file
    le borne à 32.
  - Les gardes qui retiennent le travail spéculatif pendant les chargements observés voient
    aussi les voies, et le réveillent quand elles se vident.
  - Largeur par défaut : compilations simultanées de l'appareil moins les deux voies
    observées, soit 2 sur l'A18 Pro (4 à la fois) au lieu de 3, pour ne pas dépasser ce que
    l'appareil exécute.
  - Largeur relue à chaque session ; compteurs des voies sur la ligne `[rb-urgent]`.
  - Rapport du cache : dossier de cache de l'utilisateur sur macOS, comptage arrêté signalé.
  - Deux tests existants attendaient la bibliothèque à la fin de la traduction : ils attendent
    maintenant aussi les voies.
- Série vérifiée (elle reproduit l'arbre, 44 tests purs verts avec gcc et clang). Compilation
  iOS en CI à suivre ; ni livré ni mesuré sur iPhone.

**Suite.**
- Taille du cache Metal : rien à avancer au démarrage de l'application. Le pont la fixe à 1 Gio
  avant de charger le moteur, et 1 Gio est aussi la valeur par défaut (désassemblage tiers de
  Metal sur macOS ; iOS non vérifié) : la poser plus tôt ne changerait rien. Le rapport de 0347
  dira si le cache se vide (redémarrage, mise à jour d'iOS) ou s'il est plein.
- Fire Emblem : son fil de traduction tourne surtout sur les cœurs efficaces (environ 1,5 GHz)
  sans le groupe de travail d'image. Ce groupe est coupé depuis 0097 pour permettre la mise en
  pause. L'amont l'a mesuré : 1,69 → 2,47 W au même 60 i/s. À mesurer jeu par jeu.

## Repli à 30 stables (24 novembre)

Demande du mainteneur : 30 i/s constants comme repli, seulement quand un jeu manque vraiment de
performance et devient instable ; continuer d'essayer 60 sans régression.

**Ce que fait le moteur aujourd'hui** (journaux de Zelda, Fire Emblem et deux de Mario Kart World,
moteur jusqu'à 0340, A18 Pro) :
- un jeu qui passe lui-même à l'intervalle 2 (Mario Kart World en course) est suivi : garde
  anti-verrou (0319, 0344), essais de 60 (0309), lien d'affichage gardé à 60 Hz ;
- un jeu à 30 par conception (Fire Emblem, intervalle 2 dès l'image 7) n'est pas concerné ;
- un jeu qui reste à l'intervalle 1 sans tenir 60 (Zelda) n'a rien : il s'affiche à un rythme
  irrégulier.

| Jeu, phase | Images en retard à 60 | Rythme vu | i/s (médiane) |
|---|---|---|---|
| Zelda en jeu (44 fenêtres, état Serious) | 79 % | 21 % à 16,7 ms, 54 à 70 % à 33,3 ms, 9 à 25 % à 50 ms ou plus | 28,5 |
| Zelda, menus | 0,2 à 1,4 % | 60 | 60 |
| Mario Kart World hors course | 0 à 4,9 % | surtout 16,7 ms | 53 à 60 |
| Fire Emblem en jeu (lien à 30 Hz) | sans objet | 80 % à 33,3 ms, 20 % au-delà | 23,9 |

**Patch 0349** (`S2A_RB_FALLBACK30`, actif ; `=0` rétablit l'ancien comportement ;
`S2A_RB_FALLBACK30_OFF=<identifiant>` l'écarte pour un jeu) :
- entrée : jeu hébergé à l'intervalle 1, sans vidéo, pas d'image, limite sous 60 ni garde
  anti-verrou ; une fenêtre complète de 120 intervalles affichés dont au moins 60 en retard sur
  16,7 ms ; un retard expliqué par le coût (médiane au-dessus de 14,2 ms) et 30 à portée (temps
  GPU médian d'au plus 28,3 ms) ;
- pendant le repli : chaque image reste 33,3 ms sur le lien à 60 Hz (une image en retard sort à
  50 ms, pas 66,7) ; le jeu, sa cible, ses temps GPU lus et la résolution ne changent pas ;
  l'échéance déclarée reste 16,7 ms pour garder les cœurs performance ; pas d'interpolation ;
- retour à 60 : essai dès que 30 images de suite coûtent au plus 14,2 ms (attente 1 s, doublée
  jusqu'à 8 s après un échec) ; sinon sondes espacées de 10 s, doublées jusqu'à 160 s, et
  ramenées à 10 s quand le GPU s'allège d'un quart ; un essai échoue sur 5 retards de suite ou la
  moitié de ses images en retard ; un retour tenu 30 s remet les attentes à leur départ ;
- une présentation compte au plus 4 vsyncs : un gel de compilation ou un passage en arrière-plan
  ne compte ni comme temps tenu ni comme retour réussi ;
- sortie immédiate si une condition d'entrée tombe ;
- Mario Kart World (garde anti-verrou) et Fire Emblem (intervalle 2) ne sont jamais tenus ;
- ligne `[rb-fb30]` à chaque changement et toutes les 300 images.

Relecture adverse : mécanique saine (pas de blocage, pas d'attente de 3 vsyncs ou plus, rien de
changé avec `=0`), trois défauts de règles corrigés (retour jugé plus sévèrement que l'entrée,
entrée sur des retards que le coût n'explique pas, gels comptés comme du temps). Restent, de
faible portée : avec `S2A_WORKGROUP=1` (essai seulement), le groupe de travail reçoit une
échéance de 30 i/s ; une vidéo qui démarre pendant le repli passe le lien à 30 Hz sans délai.
Test pur de la machine d'état vert (gcc, clang). Non mesuré : entrée et sortie sur de vrais jeux,
tenue réelle des 33,3 ms, vitesse du jeu si sa logique suit les images, réaction d'une résolution
dynamique propre au jeu.

**Réglages d'essai restés dans env.txt.** Les journaux de Zelda, de Fire Emblem et l'un des deux de
Mario Kart World ont tourné avec `DM_RT`, `S2A_RB_ENC_RT` et `S2A_GUEST_QOS` venus de
`Documents/env.txt` (« DM_RT=0: the present thread gets no time-constraint policy »). Le fil qui
présente y perd sa priorité temps réel ; Fire Emblem et Zelda tournaient alors surtout sur les
cœurs efficaces (2 à 24 % du temps sur les cœurs performance). Pour le prochain essai : retirer
ces trois lignes, pour mesurer les réglages par défaut.

**Fire Emblem, essai sans code possible** : `S2A_RB_PROMOTION_PACING=0` et `S2A_RB_LINK_GAME30=1`
dans env.txt gardent le lien à 60 Hz avec un maintien de 33,3 ms. Une image en retard sortirait à
50 ms au lieu de 66,7, et le lien à 30 Hz n'a livré que 19 à 29 rappels par seconde dans 9 relevés
sur 24. Cela change l'affichage d'un jeu à 30 par conception : à décider après l'essai.

**Autre cause d'à-coups trouvée** : 8 images après chaque frontière de 300, la passe des textures
partagées sans référence (`alias_orphan_pass`) tourne sur le fil qui présente : 33,9 ms en médiane
(82,8 au pire) pour Mario Kart World, 11,3 pour Fire Emblem, 3,3 pour Zelda. Une image longue suit
chaque frontière (52,5 ms en médiane, 105 au pire dans Mario Kart World).
- Cause probable, lue dans le code : pour chaque texture candidate écrite par le GPU (0 à 13 par
  passe dans Mario Kart World, presque toutes gardées), `gpw_stale` re-hache toute sa mémoire, des
  mégaoctets, sous le verrou que le fil de soumission prend pour noter les écritures GPU. Or la
  passe ne veut savoir qu'une chose : reste-t-il au moins un bloc périmé ?
- **Patch 0350** (`S2A_RB_ORPHAN_EARLY`, actif ; `=0` rétablit l'ancien calcul) : la vérification
  s'arrête au premier bloc périmé ; même décision, même mise à jour du registre pour les blocs
  vus. Une ligne donne le temps de chaque étape de la passe (verrouillée, vérification,
  libération) pour les premières passes et toute passe de 2 ms ou plus : le prochain journal dira
  si la cause était bien là. Non mesuré.

## Recherche du 24 novembre : amont, nxnative et projets iOS

Lecture seule de S2Arm amont, de nxnative et d'une vingtaine de projets publics sous licence MIT
(NX18, HookLink, manosaba-ios, switch2ios, nxkit, MacNativeGames, Hermit…). Aucun émulateur JIT ne
fait tourner de jeu Switch 2 sur iOS. Chiffres mesurés par leurs auteurs, pas par nous :

| Piste | Mesure publiée | Chez nous |
| --- | --- | --- |
| Marquage d'écriture mémoire brute : lecture simple avant l'opération atomique (nxnative 99aafb48a) | passe couleur Switch 2 de 13,0 à 9,2 ms (iPad Pro M5) | absent ; vise les 7 à 16 ms de Zelda. Change l'empreinte du traducteur : paquets de shaders à régénérer |
| Multiplications étendues en ligne, chargements groupés (nxnative 2d3fc8bf6, b2d7c15e3) | 29,24 → 24,80 ms par image ; 15,55 → 14,76 ms GPU | absent ; une partie se fait hors empreinte (SPIRV-Cross) |
| Fonctions flottantes sans `optnone` (amont 7cfd7be8f) | non mesuré | absent ; s'applique sans conflit |
| Barrières plus légères entre passes (nxnative) | GPU 22,0 → 20,2 ms (Mac), 29,7 → 27,2 ms (iPhone, une course) | absent ; Mario Kart World a 126 à 138 barrières complètes par image |
| Un allocateur de commandes par image (amont d9cf7d16e) | 1 600 à 7 500 attentes GPU du fil de traduction par session | absent ; port facile |
| Dispatchs ordonnés par les barrières du jeu (amont 116fe90e2, a51b43f72) | encodeur de particules 6,6–9,8 → 0,4–1,2 ms | absent ; une barrière avant chaque dispatch |
| Échéance temps réel du fil de traduction (amont 656ce2c27, NX18) | résultats contradictoires selon l'appareil | absent ; à mesurer en A/B avec la consommation |
| Fils en attente endormis au lieu de boucler (NX18 7b02a3e7) | 43–53 → 45–58 i/s ; 0,31 → 0,10–0,14 W | partiel ; Zelda montre 13 700 réveils par seconde |
| Fichier de mémoire invitée découpé (20 fichiers de 1 Gio) | blocage médian toutes les ~30 s de 207 à 45 ms | absent : un seul fichier ; à vérifier dans nos images longues |
| Traduction en parallèle de la soumission (nxnative) | 76,1 → 81,7 i/s (Mac) | absent ; port difficile (étape 2 du plan) |
| Fusion de passes (nxnative) | GPU −1,0 à −1,2 ms sur Mario Kart World (Mac) | absent ; demande de nouveaux pipelines |

## Interpolation d'images (« Frame Generation ») : expertise

**Ce que c'est.** Le moteur calcule une image entre deux images réelles : le jeu rend 30 images par
seconde, l'écran en montre 60. La logique, les commandes et la physique restent à 30.

**Ce qui existe.** S2Arm amont l'a depuis le 14 novembre, après notre épingle du 10 novembre : nous
ne l'avons pas. Méthode : interpolation MetalFX (iOS 26, Metal 4), vecteurs de mouvement calculés
par le moteur sur une image réduite, profondeur constante, tout l'écran d'un bloc. Seuls les jeux
qui demandent 30 i/s et tiennent leur rythme sont interpolés ; un jeu qui demande 60 ne l'est jamais.
Mesures de l'amont : un jeu à 30 passe de 28,56 à 59,98 images affichées par seconde (iPhone) ;
une interpolation coûte 7,4 à 9,0 ms de GPU sur iPad M4 avant leur dernière refonte, 0,8 ms sur
M5 Max. Un autre projet mesure 3,5 ms par image générée. En dix jours, l'amont a corrigé une fuite
jusqu'à environ 10 Go de mémoire GPU (application tuée), des fautes de page GPU, un plantage avec le
lien d'affichage et un tiers d'interpolations sautées.

**Pour nos deux jeux :**
- **Mario Kart World** demande 60 et alterne avec 30. L'interpolation masquerait le passage à 30
  sans le corriger, et ajouterait 3,5 à 9 ms de GPU par image sur un GPU déjà plafonné par iOS : le
  jeu resterait plus souvent à 30. Ce serait contourner l'ennemi n°1, pas le corriger.
- **Zelda** a un GPU saturé à pleine fréquence (21 à 31 ms). Le coût de l'interpolation le ferait
  passer sous 30 ; or une image en retard n'est pas interpolée. Utile seulement après les gains GPU.
- **Latence** : l'image réelle part une demi-période plus tard (+16,7 ms à 30 i/s), plus le calcul.
- **Image** : tout l'écran est interpolé, interface comprise ; fantômes possibles sur le HUD et les
  mouvements rapides.
- **Énergie** : interpoler 30 → 60 coûte bien moins que rendre 60 (un projet mesure 3,8 W à 60 contre
  1,85 W à 30 pour tout l'appareil). C'est le vrai intérêt pour un jeu conçu pour 30.

**Avis.** Bonne piste en complément pour les jeux conçus pour 30 i/s et stables, pas une correction
de l'ennemi n°1.

**Ajouté le 24 novembre (patch 0345, à la demande du mainteneur).** Port de la dernière version
amont (`54c2f8870`, avec ses correctifs de mémoire, de fautes de page et de lien d'affichage).
Adaptations à notre moteur : pas de filtre FSR, pas d'aspect de patch communautaire, renversement
d'origine et copie d'affichage de notre moteur, calque BGRA8 uniquement. Réglage « Génération
d'images » dans l'application, désactivé par défaut ; activé, le lancement passe `S2A_RB_FI=1` et le
menu en jeu l'allume ou l'éteint en cours de partie (`s2a_rb_guest_set_frame_interp`). Seuls les jeux
qui demandent 30 i/s ou moins sont interpolés.

**Relecture adverse du 24 novembre : quatre défauts réels, corrigés dans 0345.**
- Rallumer l'interpolation en jeu ne faisait rien : notre crochet ne consultait plus le réglage
  pour les images fournies par le lien d'affichage. Il le fait maintenant pour chaque image, comme
  l'amont.
- L'arrêt de partie n'attendait pas les deux tampons de commandes de l'interpolation (faute de page
  GPU possible). Ils comptent maintenant comme une présentation en cours, et leurs erreurs passent
  par l'arrêt de sécurité GPU.
- Après un échec de l'interpolation, les parties suivantes du même processus perdaient le lien
  d'affichage. Elles le gardent.
- Une table d'arguments avait une place de moins que ce qui y est lié (5 au lieu de 4).

Risques traités dans le même lot :
- Une image du palier 60 i/s ne passe plus par l'interpolation : SMAA, agrandissement MetalFX,
  durée minimale d'affichage et lien restent ceux d'avant.
- Le palier se lit sur le maintien d'image de RewindBox. Les images à intervalle 2 passagères
  d'un jeu à 60 (Mario Kart World) restent donc hors interpolation.
- Une course rare pouvait geler le jeu, quand on éteignait puis rallumait vite.
- Une nouvelle session ne reprend pas l'historique de l'interpolation.
- Une image non interpolée reste affichée une période entière.

Limite connue : sur les jeux interpolés (palier 30), l'image réelle est copiée sans SMAA ni
agrandissement MetalFX, comme dans l'amont.

**À vérifier dans le prochain journal**, sur Fire Emblem en résolution 1 :
- ligne `present frame interpolation: on` au lancement, puis toutes les 300 images
  `present frame interpolation up to game frame …` : images interpolées, refusées par la règle, coût
  GPU moyen et maximal par interpolation ;
- la ligne de l'interpolation toutes les 300 images (images interpolées, montrées par le système).
  La répartition des intervalles affichés (`displayed distribution`) compte les images du jeu : il
  faut y attendre environ 33,3 ms, pas 16,7 ;
- GPU p50 et i/s du jeu, comparés à la session sans interpolation.

## Suivi

| Date | Étape | Statut |
| --- | --- | --- |
| 2026-11-24 | Diagnostic et épinglage | Écrit à partir des journaux 830 et de l'historique. Aucun correctif, aucun gain mesuré. |
| 2026-11-24 | Étape 1, patchs 0342 à 0344 | Écrits ; logique pure testée hors dépôt. Relecture, compilation iOS et IPA à suivre ; aucun gain mesuré. |
| 2026-11-24 | Relectures adverses de 0342 à 0344 | Deux défauts réels par patch, corrigés ; série reconstruite à l'identique, 40 tests purs (gcc, clang) et tests statiques du dépôt verts. Compilation iOS à suivre ; aucun gain mesuré. |
| 2026-11-24 | Diagnostic croisé Zelda / Mario Kart World, recherche, expertise interpolation | Écrits. Aucun correctif tiré de la recherche n'est encore porté. |
| 2026-11-24 | Journal Fire Emblem | Analysé : jeu à 30 par conception qui ne les tient pas (GPU, traduction sur cœurs efficaces, compilations). Aucun correctif dédié encore. |
| 2026-11-24 | Version relue de 0342–0344 | Compilée pour iOS (run 45378584979), tests thermiques, DRS et passes GPU verts. Rien sur iPhone. |
| 2026-11-24 | Compléments 0342–0344, Frame Generation (0345), marques (0346) | Écrits ; série reconstruite à l'identique, 44 tests purs (gcc, clang) et tests statiques verts. Compilation iOS à suivre ; aucun gain mesuré. |
