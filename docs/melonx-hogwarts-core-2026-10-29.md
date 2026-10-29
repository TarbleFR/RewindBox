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

## État de la construction

La recette et ses contrôles sont préparés pour l'exécution Apple autorisée.
Le run, les identités des nouveaux binaires et le résultat effectif seront
consignés ici après vérification de l'artefact produit.
