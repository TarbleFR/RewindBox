# Cœur MeloNX avec les douze correctifs mémoire — 29 octobre 2026

## Périmètre

À la suite du push `7ffdbaaecced8ebf5884b89f67e3279d5752a2e6`, le mainteneur
demande explicitement d'apporter les correctifs au cœur. Cette étape compile
les bibliothèques natives pour iPhone ARM64 et simulateur iOS ARM64. Elle ne
produit pas d'IPA et ne mesure pas Hogwarts Legacy sur iPhone.

La source reste le commit MeloNX
`13700519f3abc4e6d7ed8a065b118b2cc59bcd67`, arbre
`82a29e6f593f6244869481e9a489b8d5154175fe`, avec le SDK .NET 10.0.100.
Les douze adaptateurs, leurs 86 entrées et les 17 sources natives modifiées
sont ceux de [l'analyse et des validations Linux](melonx-hogwarts-followup-2026-10-29.md).
Les résultats de ce lot ne couvrent pas l'ancien lot local de onze adaptateurs
qui n'était plus disponible dans cette base.

## Validation des changements combinés

Les nouvelles portes Apple exécutent les douze corpus ciblés, sur la même
architecture ARM64 et avec la sélection effective du SDK verrouillée. Les
tests du curseur de régions utilisent désormais aussi le nouveau
`MultiRange.Slice`. Une treizième porte compare les uploads fragmentés déjà
corrigés, avec et sans le nouveau Slice, pour contrôler les octets transférés
et le nettoyage des lectures en cas d'exception.

Les scripts des attentes noyau, requêtes IPC et timers sélectionnent le SDK
depuis le répertoire qui contient leur `global.json`. Cette correction porte
sur l'exécution des validations et ne modifie pas le code du cœur.

Les deux corpus de composition passent d'abord en JIT Linux avec le SDK exact.
Le curseur composé conserve les 12 170 contrôles d'overlap et les 26 311
assertions de protocole ; le repli fragmenté passe de 864 à 624 octets alloués
par appel. Pour les uploads fragmentés, les deux variantes transmettent
220 200 960 octets avec le même digest, rendent leurs 219 emprunts et passent
les 14 assertions. Les allocations mesurées passent de 28 672 à 13 312 octets.
Ces chiffres proviennent de fixtures avec des frontières natives simulées,
pas de mesures de RAM dans le jeu. Reçus distincts dans
`docs/evidence/melonx-hogwarts-core-20261029/` ; aucune réexécution HLE locale.

Après compilation, `verify_core_candidate.py` authentifie les reçus, leurs
entrées et leurs sources. Les deux identités natives doivent porter le commit
du run et les 86 empreintes attendues. Les 17 postimages de production doivent
correspondre à l'intégration revue ; les écarts connus des extraits de test
restent explicitement décrits dans le reçu d'intégration. Les 47 exports et
les plateformes Mach-O iPhone/simulateur restent vérifiés par `build_core.sh`.

Le test de fonctionnement charge le nouveau binaire dans une application de
simulateur. Il exige une instruction SVC confirmée dans chacune de deux
sessions distinctes, leur fermeture et la libération de leurs backings mémoire.
Le résultat est lié au SHA-256 du nouveau binaire, aux deux sources Swift et
au script du test. Le test ne produit pas de vidéo de jeu et ne valide ni les
FPS ni la consommation mémoire de Hogwarts Legacy sur un appareil physique.

## Réutilisation des éléments inchangés

L'artefact `12883480724`, run `40841402428`, contient le moteur82 compilé et sa
validation séparée réussie. Son archive de 102 750 721 octets est authentifiée
par SHA-256 `be55d705ea93ae27c1756c29c3ec7a16ec51c60b9ace10556dcc751a00f5af45`.
La provenance du run, du job et de l'artefact est vérifiée avant réutilisation.
Les 73 anciennes entrées de préparation hors orchestrateur modifié restent
identiques ; les preuves anciennes sont conservées séparément, avec leurs
identités et leur portée d'origine. Elles ne sont pas présentées comme une
nouvelle exécution des chemins modifiés.

Seuls le paquet LibHac exact, ses sources correspondantes et ses preuves de
construction sont repris dans la sortie courante. Les cinq tests de layout
déjà réussis ne sont pas rejoués. Les anciens binaires et tests de démarrage
ne remplacent aucun résultat du nouveau moteur. Les dix frameworks natifs
inchangés du run `39854858591` sont réutilisés après contrôle de leurs
empreintes et de leurs pins. Les notices des paquets gérés sont collectées
sur la nouvelle publication.

Le premier échec de démarrage du moteur82 et sa validation ultérieure restent
des preuves historiques distinctes. La nouvelle recette conserve aussi ses
propres sorties en cas d'échec, afin qu'une compilation réussie ne masque pas
une validation de fonctionnement échouée.

## Résultat : Core84 compilé et vérifié

La [construction n° 84](https://github.com/TarbleFR/RewindBox/actions/runs/40895446303)
réussit dès la tentative 1 sur la source
`5045889ff9f1a872d238435293c50cacd7c127b5`, job `123523168026`.
L'artefact `12907831125` contient les bibliothèques iPhone et simulateur, les
sources correspondantes, les notices et les preuves de validation.

| Élément | Taille | SHA-256 |
|---|---:|---|
| Archive livrée | 87 444 668 octets | `03d98461351141dbc32a407591081a775c4c5298ab1df7ae8b72f39e6cf20493` |
| Cœur iPhone ARM64 | 37 585 128 octets | `a19229b27a949225dd6aebc03c6737b466f26f355ee0ec5f8418ec7857bfc6a4` |
| Cœur simulateur ARM64 | 37 911 912 octets | `a171296956d22e57d242b918ea262ac84fa0113591c46e69ce169cb200a10248` |

Les treize portes Apple réussissent en 94 secondes. La compilation NativeAOT
et la vérification d'ABI prennent 254 secondes ; le test de fonctionnement
prend 241 secondes. Le job complet dure 702 secondes, soit 11 min 42 s.
Ces durées proviennent des étapes GitHub, pas d'une estimation.

Le simulateur iOS 26.5 confirme deux sessions distinctes : génération 1,
séquence SVC 39 après la séquence initiale 23 ; génération 2, séquence SVC 56
après la séquence initiale 40. Les deux sessions ferment et libèrent leur
backing. Le SHA du binaire testé est celui du nouveau cœur simulateur ci-dessus.

### Vérification indépendante de l'archive téléchargée

Le contrôle hors ligne réussit sur les octets téléchargés, après comparaison
de leur taille et de leur SHA avec les métadonnées GitHub. Il relit les objets
Git du commit exact et les deux véritables images Mach-O : ARM64, type DYLIB,
plateformes iOS et simulateur, 47 exports requis chacune.

Les 127 membres de l'archive des sources préparées correspondent exactement
aux 17 postimages revues et aux 110 membres inchangés. Les treize reçus frais
lient 66 entrées du dépôt et 89 entrées amont ; les 22 postimages des portes
correspondent aux sources finales ou à l'une des cinq exceptions de composition
déjà documentées. Les 86 entrées de préparation, les quatre reçus de la recette,
le smoke, LibHac et les preuves des dix frameworks sont liés par empreinte.
Le contrôle ne reconstruit rien et ne rejoue aucun corpus.

Reçu principal : `docs/evidence/melonx-hogwarts-core-20261029/apple-core.json`.
Reçu indépendant : `independent-apple-verification.json`, SHA-256
`93444fdee86538389ea9923c23208d79f357827dcd22cc8523d7848106bed82c`.
Les 26 fichiers de preuve extraits de l'artefact sont conservés sous
`apple-core/`, et le vérificateur exact et ses métadonnées sous `verification/`.

### Mesures Apple et contreparties conservées

Les mesures ci-dessous proviennent des fixtures JIT .NET 10.0.100 sur Apple
ARM64. Elles caractérisent les chemins de production testés avec leurs
frontières natives simulées. Elles ne constituent pas une mesure de RAM ou
de FPS dans Hogwarts Legacy.

| Scénario ciblé | Témoin | Correctifs |
|---|---:|---:|
| Snapshot de 512 handles, allocation par événement après échauffement | 4 120 octets | 0 octet |
| Slice limité à un fragment dans une plage fragmentée | 120 octets | 0 octet |
| Slice à deux fragments | 176 octets | 56 octets |
| Propriétaire Vulkan `Auto`, allocation par instance | 88 octets | 56 octets |
| 20 000 recherches absentes dans le cache de conversions | 2 599 944 octets | 0 octet |
| 200 000 armements de timers après échauffement | 6 400 000 octets | 0 octet |
| Lot mesuré d'uploads fragmentés | 28 672 octets | 13 312 octets |
| Handles retirés encore retenus après 32 remappages | 32 | 0 |

Les timings ne s'améliorent pas partout. Le Slice en milieu et fin d'une longue
plage fragmentée passe respectivement de 231,865 à 339,255 ns et de 718,260 à
844,145 ns dans ce run. Le snapshot à 4 096 handles passe de 70,727 à 75,021 µs,
tout en supprimant ses 32 792 octets d'allocation par événement après
échauffement. Au-delà de la borne de pool, l'allocation temporaire reste permise.

Le timer réserve 32 octets par emplacement au lieu de 8 ; la médiane du corpus
d'armement passe de 8,633 à 9,362 ms. Pour l'allocateur, 10 000 cycles avec
2 048 blocs passent de 20,280 à 8,402 ms, mais le cas à 32 blocs passe de 5,280
à 6,756 ms. Un scénario de pool mixte atteint 255 356 octets simulés contre
251 260, soit 4 096 octets de plus. Les scénarios entièrement dédiés conservent
leurs traces et volumes natifs simulés. Les résultats complets restent dans les reçus,
avec un extrait dans `apple-measurements.json` ; aucun seuil de vitesse n'a
été relâché pour accepter ces mesures.

Le Core84 est prêt pour une intégration ultérieure dans une IPA utilisant les
mêmes entrées. Cette tâche n'a produit aucune nouvelle IPA ni release, et
n'établit aucun gain de FPS ou de RSS sur iPhone.
