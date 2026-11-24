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

**Statut :** écrits le 24 novembre 2026. Logique pure testée hors dépôt (gcc et clang), arbre moteur
reconstruit à l'identique depuis la série. Relecture adverse, compilation iOS, épingle et IPA : voir
le suivi plus bas. Rien n'est observé sur iPhone ; aucun gain n'est mesuré.

| Patch | Changement | Interrupteur (`env.txt`) |
| --- | --- | --- |
| 0342 | Quand le jeu rebinde les cibles déjà en place, la passe continue au lieu d'être fermée, écrite en mémoire puis rechargée. Idée reprise de l'amont S2Arm (`fb96ab7db`, section 3). Visé : 30 à 75 Mio réels par image. | `S2A_RB_RT_CONT=0` |
| 0343 | Pas de chargement d'une cible couleur que le premier dessin de la passe recouvre entièrement. Visé : 30 à 35 Mio réels par image. | `S2A_RB_COVER_LOAD=0` |
| 0344 | La garde anti-verrou à 30 i/s de 0319 vaut pour tout jeu vu alterner 60 et 30, plus seulement Mario Kart World. | `S2A_RB_NO_LOCK_SEEN=0` |

**Pourquoi c'est sûr malgré les textures lues par poignée indirecte (0342).** Avant chaque dessin
d'une passe continuée, le moteur résout les textures que ce dessin va lire, comme il le fait pour les
lier : emplacements liés, poignées lues dans les tampons d'uniformes, tableaux de poignées. Si l'une
est une cible déjà modifiée dans la passe, ou la profondeur, la passe est coupée avant ce dessin,
comme elle l'était avant le patch. Coupent aussi :
- une texture choisie par un index calculé dans le shader ;
- un shader sans liste de liaisons ;
- DrawTexture.

La preuve « couleur jamais écrite jusqu'à la fin de passe » suit la passe prolongée. Elle ne peut
qu'en prouver moins qu'avant, jamais plus ; elle ne faisait gagner que 0,7 à 1,4 Mio par image.

La passe n'est pas continuée s'il reste des effacements en attente, des mises à niveau d'images en
attente ou un effacement juste après. Même chose pour une passe en couches, l'écran élargi et les
cibles d'affichage, de vidéo, linéaires ou creuses.

**0343.** La preuve existante ne lit que l'état du dessin : pas de mélange, tous les canaux écrits,
aucun rejet de fragment, sommets lus côté processeur. Le patch ajoute des refus pour le test alpha,
le « rasterizer discard », les étages géométrie et tessellation, les passes en couches et le swizzle
de viewport. Un premier dessin peut être sauté pendant la compilation de son pipeline. Dans ce cas,
la cible n'est pas écrite en fin de passe et la mémoire garde son contenu.

**0344.** Un jeu est « vu alterner » après 8 changements d'intervalle en 600 images, le critère
de l'essai 0309. Un jeu à 30 i/s par conception ne change presque jamais d'intervalle : il garde son
maintien à 33,2 ms.

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
- pour un autre jeu : la ligne « the game alternates its present interval », puis les sorties de la
  garde.

## Suivi

| Date | Étape | Statut |
| --- | --- | --- |
| 2026-11-24 | Diagnostic et épinglage | Écrit à partir des journaux 830 et de l'historique. Aucun correctif, aucun gain mesuré. |
| 2026-11-24 | Étape 1, patchs 0342 à 0344 | Écrits ; logique pure testée hors dépôt. Relecture, compilation iOS et IPA à suivre ; aucun gain mesuré. |
